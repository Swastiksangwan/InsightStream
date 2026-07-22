#!/usr/bin/env python3
"""
Inspection-only TMDb sample fetch script.

- This script does not modify PostgreSQL.
- It uses TMDb as a prototype metadata provider.
- TMDb data must be used according to TMDb terms.
- Do not commit API tokens.
- Run from repository root:

    export TMDB_READ_ACCESS_TOKEN="..."
    python3 -m analytics.scripts.ingestion.fetch_tmdb_sample
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import requests
    from requests import RequestException
except ImportError:  # pragma: no cover - helpful when dependencies are not installed yet.
    requests = None

    class RequestException(Exception):
        pass


from analytics.scripts.providers.tmdb.tmdb_video_metadata import normalize_video_snapshot


API_BASE_URL = "https://api.themoviedb.org/3"
TOKEN_ENV_VAR = "TMDB_READ_ACCESS_TOKEN"
LANGUAGE_ENV_VAR = "TMDB_LANGUAGE"
VIDEO_LANGUAGES_ENV_VAR = "TMDB_VIDEO_LANGUAGES"
DEFAULT_LANGUAGE = "en-US"
DEFAULT_VIDEO_LANGUAGES = "en,null"
MAX_VIDEO_LANGUAGES = 8
DEFAULT_REQUEST_TIMEOUT = 15.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BATCH_SIZE = 25
DEFAULT_CONCURRENCY = 3
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
from analytics.scripts.common.paths import REPO_ROOT
RAW_OUTPUT_DIR = REPO_ROOT / "analytics" / "raw" / "tmdb"
PROCESSED_OUTPUT_DIR = REPO_ROOT / "analytics" / "processed" / "tmdb"
PREVIEW_OUTPUT_PATH = PROCESSED_OUTPUT_DIR / "sample_mapping_preview.json"
RUN_REPORT_DIR = PROCESSED_OUTPUT_DIR / "run_reports"
RUN_REPORT_OUTPUT_PATH = RUN_REPORT_DIR / "content_fetch_run_report.json"
VIDEO_RETRY_OUTPUT_PATH = RUN_REPORT_DIR / "content_video_retry_targets.json"
VIDEO_REVIEW_OUTPUT_PATH = RUN_REPORT_DIR / "content_video_review_targets.json"
DEFAULT_TARGETS_PATH = REPO_ROOT / "analytics" / "config" / "content_ingestion_targets.json"
CONTENT_TYPE_TO_MEDIA_TYPE = {
    "movie": "movie",
    "series": "tv",
}
MEDIA_TYPE_TO_CONTENT_TYPE = {
    "movie": "movie",
    "tv": "series",
}


@dataclass(frozen=True)
class SampleTitle:
    title: str
    media_type: str
    tmdb_id: int | None
    year: int | None = None
    content_type: str | None = None
    source_name: str = "tmdb"
    source_id: str | None = None
    priority: str | None = None
    ingestion_status: str | None = None
    notes: str | None = None
    original_language: str | None = None


@dataclass(frozen=True)
class TargetLoadResult:
    path: Path
    total_targets: int
    skipped_targets: int
    warnings: list[str]
    samples: list[SampleTitle]


@dataclass(frozen=True)
class RequestPolicy:
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_base_seconds: float = 0.5
    backoff_cap_seconds: float = 30.0


class TmdbFetchError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        failure_class: str = "normalization_review",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.failure_class = failure_class


class TargetConfigError(RuntimeError):
    pass


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--limit must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("--limit must be a positive integer")
    return parsed


def non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a non-negative integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be a non-negative integer")
    return parsed


def positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive number")
    return parsed


def normalize_video_languages(value: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    raw_values = value.split(",") if isinstance(value, str) else list(value)
    normalized: list[str] = []
    for raw_value in raw_values:
        language = str(raw_value).strip().casefold()
        if not language:
            continue
        if language != "null" and not re.fullmatch(r"[a-z]{2}", language):
            raise ValueError(
                "video languages must be ISO 639-1 codes or TMDb's null token"
            )
        if language not in normalized:
            normalized.append(language)
    if not normalized:
        raise ValueError("at least one video language is required")
    if len(normalized) > MAX_VIDEO_LANGUAGES:
        raise ValueError(f"at most {MAX_VIDEO_LANGUAGES} video languages are allowed")
    return tuple(normalized)


def normalize_language_code(value: str | None, *, field_name: str) -> str | None:
    if value is None or not str(value).strip():
        return None
    language = str(value).strip().casefold().split("-", 1)[0]
    if not re.fullmatch(r"[a-z]{2}", language):
        raise ValueError(f"{field_name} must start with an ISO 639-1 language code")
    return language


def merge_video_languages(
    detail_language: str,
    original_language: str | None,
    configured_languages: str | list[str] | tuple[str, ...],
) -> tuple[str, ...]:
    """Merge request languages by product priority without exceeding TMDb's cap."""
    display_language = normalize_language_code(
        detail_language or DEFAULT_LANGUAGE,
        field_name="detail language",
    )
    original = normalize_language_code(
        original_language,
        field_name="original language",
    )
    configured = normalize_video_languages(configured_languages)
    include_null = "null" in configured

    merged: list[str] = []
    for language in (display_language, original):
        if language and language not in merged:
            merged.append(language)
    for language in configured:
        if language != "null" and language not in merged:
            merged.append(language)

    available_slots = MAX_VIDEO_LANGUAGES - (1 if include_null else 0)
    merged = merged[:available_slots]
    if include_null:
        merged.append("null")
    return tuple(merged)


def video_languages_arg(value: str) -> tuple[str, ...]:
    try:
        return normalize_video_languages(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch inspection-only TMDb metadata for configured content targets."
    )
    parser.add_argument(
        "--targets",
        default=str(DEFAULT_TARGETS_PATH.relative_to(REPO_ROOT)),
        help=(
            "Path to ingestion target JSON. Defaults to "
            f"{DEFAULT_TARGETS_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--priority",
        help="Process only targets with this priority value.",
    )
    parser.add_argument(
        "--source-id",
        help="Process only one target by provider source ID.",
    )
    parser.add_argument(
        "--title",
        help="Process only one target by exact title match, case-insensitive.",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        help="Cap selected targets after filtering.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refetch raw files even when cached raw files already exist.",
    )
    parser.add_argument(
        "--language",
        default=os.getenv(LANGUAGE_ENV_VAR, DEFAULT_LANGUAGE),
        help=f"TMDb response language (default: {DEFAULT_LANGUAGE}).",
    )
    parser.add_argument(
        "--video-languages",
        type=video_languages_arg,
        default=os.getenv(VIDEO_LANGUAGES_ENV_VAR, DEFAULT_VIDEO_LANGUAGES),
        help=(
            "Comma-separated ISO 639-1 video languages plus optional null "
            f"(default: {DEFAULT_VIDEO_LANGUAGES})."
        ),
    )
    parser.add_argument(
        "--request-timeout",
        type=positive_float,
        default=DEFAULT_REQUEST_TIMEOUT,
        help=f"Per-request timeout in seconds (default: {DEFAULT_REQUEST_TIMEOUT:g}).",
    )
    parser.add_argument(
        "--max-retries",
        type=non_negative_int,
        default=DEFAULT_MAX_RETRIES,
        help=f"Retries for transient failures (default: {DEFAULT_MAX_RETRIES}).",
    )
    parser.add_argument(
        "--batch-size",
        type=positive_int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Maximum targets held in a processing batch (default: {DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--concurrency",
        type=positive_int,
        default=DEFAULT_CONCURRENCY,
        help=f"Maximum concurrent title fetches (default: {DEFAULT_CONCURRENCY}).",
    )
    return parser.parse_args(argv)


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def resolve_target_path(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def config_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip()


def parse_optional_year(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    if 1800 <= year <= 3000:
        return year
    return None


def parse_source_id(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    if parsed <= 0:
        return None
    return parsed


def load_targets(path: Path) -> TargetLoadResult:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TargetConfigError(f"Missing target file: {relative_path(path)}") from exc
    except json.JSONDecodeError as exc:
        raise TargetConfigError(
            f"Malformed target JSON in {relative_path(path)}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise TargetConfigError(
            f"Target file must contain a JSON object: {relative_path(path)}"
        )

    targets = data.get("targets")
    if not isinstance(targets, list):
        raise TargetConfigError(
            f"Target file must contain a 'targets' array: {relative_path(path)}"
        )

    warnings: list[str] = []
    samples: list[SampleTitle] = []
    skipped_targets = 0

    for index, target in enumerate(targets, start=1):
        if not isinstance(target, dict):
            warnings.append(f"Target #{index}: expected an object; skipped.")
            skipped_targets += 1
            continue

        title = config_text(target.get("title"))
        content_type = (config_text(target.get("content_type")) or "").lower()
        source_name = (config_text(target.get("source_name")) or "").lower()
        source_id = config_text(target.get("source_id"))
        priority = config_text(target.get("priority"))
        ingestion_status = config_text(target.get("ingestion_status"))
        notes = config_text(target.get("notes"))
        original_language = config_text(target.get("original_language"))
        label = title or f"target #{index}"

        if (ingestion_status or "").lower() == "skip":
            warnings.append(f"{label}: ingestion_status is skip; skipped.")
            skipped_targets += 1
            continue

        validation_errors: list[str] = []
        if not title:
            validation_errors.append("missing title")
        if content_type not in CONTENT_TYPE_TO_MEDIA_TYPE:
            validation_errors.append("content_type must be movie or series")
        if source_name != "tmdb":
            validation_errors.append("source_name must be tmdb")
        if not source_id:
            validation_errors.append("missing source_id")
        if original_language and not re.fullmatch(
            r"[a-z]{2}", original_language.casefold()
        ):
            validation_errors.append("original_language must be an ISO 639-1 code")

        tmdb_id = parse_source_id(source_id)
        if source_id and tmdb_id is None:
            validation_errors.append("source_id must be a positive integer TMDb ID")

        if validation_errors:
            warnings.append(
                f"{label}: invalid target ({'; '.join(validation_errors)}); skipped."
            )
            skipped_targets += 1
            continue

        samples.append(
            SampleTitle(
                title=title or "",
                media_type=CONTENT_TYPE_TO_MEDIA_TYPE[content_type],
                tmdb_id=tmdb_id,
                year=parse_optional_year(target.get("year")),
                content_type=content_type,
                source_name=source_name,
                source_id=source_id,
                priority=priority,
                ingestion_status=ingestion_status,
                notes=notes,
                original_language=(
                    original_language.casefold() if original_language else None
                ),
            )
        )

    return TargetLoadResult(
        path=path,
        total_targets=len(targets),
        skipped_targets=skipped_targets,
        warnings=warnings,
        samples=samples,
    )


def fetch_tmdb_json(
    path: str,
    token: str,
    params: dict[str, Any] | None = None,
    request_policy: RequestPolicy | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    jitter_fn: Callable[[float, float], float] = random.uniform,
) -> dict[str, Any]:
    if requests is None:
        raise TmdbFetchError(
            "Missing dependency 'requests'. Run `pip install -r backend/requirements.txt`."
        )

    policy = request_policy or RequestPolicy()
    url = f"{API_BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "application/json",
    }

    response = None
    for attempt in range(policy.max_retries + 1):
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=policy.timeout_seconds,
            )
        except RequestException as exc:
            if attempt >= policy.max_retries:
                raise TmdbFetchError(
                    f"Request failed for {path} after {attempt + 1} attempts: {exc}",
                    retryable=True,
                    failure_class="network_transient",
                ) from exc
            delay = min(
                policy.backoff_cap_seconds,
                policy.backoff_base_seconds * (2**attempt),
            )
            sleep_fn(delay + jitter_fn(0, min(0.5, delay)))
            continue

        if response.ok:
            break

        retryable = response.status_code in RETRYABLE_STATUS_CODES
        if not retryable or attempt >= policy.max_retries:
            if response.status_code == 429:
                failure_class = "rate_limited"
            elif response.status_code in {500, 502, 503, 504}:
                failure_class = "provider_server_error"
            elif response.status_code == 404:
                failure_class = "source_not_found"
            else:
                failure_class = "provider_request_error"
            raise TmdbFetchError(
                f"TMDb request failed for {path}: HTTP {response.status_code} - "
                f"{response.text[:300]}",
                status_code=response.status_code,
                retryable=retryable,
                failure_class=failure_class,
            )

        retry_after = response.headers.get("Retry-After")
        delay = None
        if response.status_code == 429 and retry_after:
            try:
                delay = max(0.0, float(retry_after))
            except ValueError:
                delay = None
        if delay is None:
            delay = min(
                policy.backoff_cap_seconds,
                policy.backoff_base_seconds * (2**attempt),
            ) + jitter_fn(0, 0.5)
        sleep_fn(min(delay, policy.backoff_cap_seconds))

    if response is None:  # pragma: no cover - the loop returns or raises.
        raise TmdbFetchError(f"TMDb request failed for {path}")

    try:
        data = response.json()
    except ValueError as exc:
        raise TmdbFetchError(
            f"TMDb returned malformed JSON for {path}",
            failure_class="normalization_review",
        ) from exc

    if not isinstance(data, dict):
        raise TmdbFetchError(
            f"TMDb returned unexpected JSON shape for {path}",
            failure_class="normalization_review",
        )

    return data


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def cache_metadata_path(raw_path: Path) -> Path:
    return raw_path.with_suffix(".meta.json")


def normalized_request_params(params: dict[str, Any] | None) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in sorted((params or {}).items()):
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            normalized[str(key)] = value
            continue
        raise ValueError(f"Unsupported request parameter type for {key!r}")
    return normalized


def build_request_signature(api_path: str, params: dict[str, Any] | None) -> str:
    fingerprint_payload = {
        "source": "tmdb",
        "api_path": api_path,
        "params": normalized_request_params(params),
    }
    serialized = json.dumps(
        fingerprint_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def utc_timestamp_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def normalize_aware_iso_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat()


def load_cache_metadata(raw_path: Path) -> dict[str, Any]:
    metadata_path = cache_metadata_path(raw_path)
    if not metadata_path.exists():
        return {
            "source_fetched_at": utc_timestamp_from_mtime(raw_path),
            "timestamp_origin": "legacy_file_mtime",
            "request_signature": None,
            "metadata_path": relative_path(metadata_path),
            "timestamp_valid": False,
        }
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TmdbFetchError(
            f"Malformed cache metadata in {relative_path(metadata_path)}: {exc}"
        ) from exc
    if not isinstance(metadata, dict):
        raise TmdbFetchError(
            f"Cache metadata has unexpected shape: {relative_path(metadata_path)}"
        )
    fetched_at = normalize_aware_iso_timestamp(metadata.get("fetched_at"))
    if fetched_at is None:
        fetched_at = utc_timestamp_from_mtime(raw_path)
        timestamp_origin = "legacy_file_mtime"
        timestamp_valid = False
    else:
        timestamp_origin = "sidecar"
        timestamp_valid = True
    return {
        "source_fetched_at": fetched_at,
        "timestamp_origin": timestamp_origin,
        "request_signature": metadata.get("request_signature"),
        "metadata_path": relative_path(metadata_path),
        "timestamp_valid": timestamp_valid,
    }


def save_cache_metadata(
    raw_path: Path,
    api_path: str,
    params: dict[str, Any] | None,
    request_signature: str,
    fetched_at: str,
) -> None:
    save_json(
        cache_metadata_path(raw_path),
        {
            "source": "tmdb",
            "fetched_at": fetched_at,
            "request_path": api_path,
            "request_parameters": normalized_request_params(params),
            "request_signature": request_signature,
            "response_status": 200,
        },
    )


def load_cached_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TmdbFetchError(f"Missing cached raw file: {relative_path(path)}") from exc
    except json.JSONDecodeError as exc:
        raise TmdbFetchError(
            f"Malformed cached raw JSON in {relative_path(path)}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise TmdbFetchError(
            f"Cached raw JSON has unexpected shape: {relative_path(path)}"
        )

    return data


def fetch_or_reuse_json(
    api_path: str,
    raw_path: Path,
    token: str | None,
    refresh: bool,
    params: dict[str, Any] | None = None,
    request_policy: RequestPolicy | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_signature = build_request_signature(api_path, params)
    if raw_path.exists() and not refresh:
        try:
            cache_metadata = load_cache_metadata(raw_path)
        except TmdbFetchError:
            if not token:
                raise
            cache_metadata = None
        if cache_metadata is not None:
            if token and cache_metadata.get("timestamp_valid") is not True:
                cache_metadata = None
        if cache_metadata is not None:
            cached_signature = cache_metadata.get("request_signature")
            signature_matches = cached_signature == expected_signature
            legacy_parameterless_cache = cached_signature is None and not params
            if signature_matches or legacy_parameterless_cache:
                return load_cached_json(raw_path), {
                    "path": relative_path(raw_path),
                    "status": "reused",
                    **cache_metadata,
                }
        if not token:
            raise TmdbFetchError(
                "Cached raw response is incompatible with the current request "
                f"parameters for {api_path}; set {TOKEN_ENV_VAR} to refetch it.",
                failure_class="cache_incompatible",
            )

    if not token:
        raise TmdbFetchError(
            f"Missing {TOKEN_ENV_VAR}; cannot fetch {api_path} for {relative_path(raw_path)}.",
            failure_class="cache_incompatible",
        )

    data = fetch_tmdb_json(
        api_path,
        token,
        params=params,
        request_policy=request_policy,
    )
    fetched_at = datetime.now(timezone.utc).isoformat()
    save_json(raw_path, data)
    save_cache_metadata(
        raw_path,
        api_path,
        params,
        expected_signature,
        fetched_at,
    )
    return data, {
        "path": relative_path(raw_path),
        "status": "fetched",
        "source_fetched_at": fetched_at,
        "timestamp_origin": "network",
        "request_signature": expected_signature,
        "metadata_path": relative_path(cache_metadata_path(raw_path)),
        "timestamp_valid": True,
    }


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def title_matches(expected: str, actual: str | None) -> bool:
    expected_normalized = normalize_title(expected)
    actual_normalized = normalize_title(actual)
    return bool(
        expected_normalized
        and actual_normalized
        and (
            expected_normalized in actual_normalized
            or actual_normalized in expected_normalized
        )
    )


def year_from_date(date_value: str | None) -> int | None:
    if not date_value or len(date_value) < 4:
        return None
    try:
        return int(date_value[:4])
    except ValueError:
        return None


def is_date_string(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def is_non_future_date_string(value: Any) -> bool:
    if not is_date_string(value):
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return False
    return parsed <= date.today()


def parse_date_string(value: Any) -> date | None:
    if not is_date_string(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def latest_tv_activity_date(details: dict[str, Any]) -> str | None:
    last_episode = details.get("last_episode_to_air")
    if (
        isinstance(last_episode, dict)
        and is_non_future_date_string(last_episode.get("air_date"))
    ):
        return last_episode.get("air_date")

    last_air_date = details.get("last_air_date")
    if is_non_future_date_string(last_air_date):
        return last_air_date

    first_air_date = details.get("first_air_date")
    if is_non_future_date_string(first_air_date):
        return first_air_date

    return None


SERIES_STATUS_MAP = {
    "Returning Series": "ongoing",
    "In Production": "ongoing",
    "Planned": "upcoming",
    "Pilot": "upcoming",
    "Ended": "ended",
    "Canceled": "cancelled",
    "Cancelled": "cancelled",
}


def normalize_series_status(status: Any) -> str:
    text_value = status.strip() if isinstance(status, str) else ""
    if not text_value:
        return "unknown"
    return SERIES_STATUS_MAP.get(text_value, "unknown")


def nested_air_date(details: dict[str, Any], field_name: str) -> str | None:
    value = details.get(field_name)
    if isinstance(value, dict) and is_date_string(value.get("air_date")):
        return value.get("air_date")
    return None


def build_season_summary(
    details: dict[str, Any],
    notes: list[str],
) -> dict[str, Any]:
    seasons = details.get("seasons")
    if not isinstance(seasons, list):
        notes.append("Missing or invalid seasons array in TV details.")
        return {
            "released_seasons_count": None,
            "announced_seasons_count": None,
            "next_season_number": None,
            "next_season_air_date": None,
            "next_season_year": None,
            "has_announced_season": None,
            "season_summary_note": None,
        }

    regular_seasons = [
        season
        for season in seasons
        if isinstance(season, dict)
        and isinstance(season.get("season_number"), int)
        and season.get("season_number") > 0
    ]
    today = date.today()
    released: list[dict[str, Any]] = []
    announced: list[dict[str, Any]] = []

    for season in regular_seasons:
        air_date = parse_date_string(season.get("air_date"))
        if air_date and air_date <= today:
            released.append(season)
        else:
            announced.append(season)

    next_season = None
    if announced:
        next_season = sorted(
            announced,
            key=lambda season: (
                parse_date_string(season.get("air_date")) or date.max,
                season.get("season_number") or 9999,
            ),
        )[0]

    next_air_date = (
        next_season.get("air_date")
        if next_season and is_date_string(next_season.get("air_date"))
        else None
    )
    next_year = year_from_date(next_air_date)
    next_number = next_season.get("season_number") if next_season else None
    summary_note = None

    if isinstance(next_number, int):
        if next_year:
            summary_note = f"Season {next_number} expected in {next_year}"
        else:
            summary_note = f"Season {next_number} announced"

    return {
        "released_seasons_count": len(released),
        "announced_seasons_count": len(announced),
        "next_season_number": next_number,
        "next_season_air_date": next_air_date,
        "next_season_year": next_year,
        "has_announced_season": bool(announced),
        "season_summary_note": summary_note,
    }


def build_series_metadata(
    details: dict[str, Any],
    notes: list[str],
) -> dict[str, Any]:
    series_status = details.get("status")
    season_summary = build_season_summary(details, notes)
    metadata = {
        "number_of_seasons": details.get("number_of_seasons"),
        "number_of_episodes": details.get("number_of_episodes"),
        "series_status": series_status,
        "series_status_normalized": normalize_series_status(series_status),
        "in_production": details.get("in_production"),
        "first_air_date": details.get("first_air_date")
        if is_date_string(details.get("first_air_date"))
        else None,
        "last_air_date": details.get("last_air_date")
        if is_date_string(details.get("last_air_date"))
        else None,
        "last_episode_air_date": nested_air_date(details, "last_episode_to_air"),
        "next_episode_air_date": nested_air_date(details, "next_episode_to_air"),
        "series_type": details.get("type"),
        "source_name": "tmdb",
    }
    metadata.update(season_summary)
    return metadata


def format_rating_count_label(vote_count: int | None) -> str | None:
    if vote_count is None:
        return None
    return f"{vote_count:,} votes"


def build_tmdb_rating_preview(
    details: dict[str, Any],
    notes: list[str],
) -> list[dict[str, Any]]:
    vote_average = details.get("vote_average")
    vote_count = details.get("vote_count")

    if vote_average is None:
        notes.append("Missing vote_average; TMDb rating skipped.")
        return []

    if not isinstance(vote_average, (int, float)):
        notes.append("Invalid vote_average; TMDb rating skipped.")
        return []

    if vote_average < 0 or vote_average > 10:
        notes.append(
            "vote_average outside expected 0-10 range; normalized score was clamped."
        )

    cleaned_vote_count = None
    if vote_count is None:
        notes.append("Missing vote_count; TMDb rating vote_count preserved as null.")
    elif isinstance(vote_count, int) and vote_count >= 0:
        cleaned_vote_count = vote_count
    else:
        notes.append("Invalid vote_count; TMDb rating vote_count preserved as null.")

    normalized_score = max(0, min(100, float(vote_average) * 10))

    return [
        {
            "source_name": "tmdb",
            "display_name": "TMDb",
            "source_category": "audience",
            "raw_score": float(vote_average),
            "raw_score_scale": 10,
            "normalized_score": round(normalized_score, 2),
            "vote_count": cleaned_vote_count,
            "rating_count_label": format_rating_count_label(cleaned_vote_count),
            "rating_url": None,
            "source_payload": {
                "vote_average": vote_average,
                "vote_count": vote_count,
            },
        }
    ]


def choose_image_size(
    available_sizes: list[str],
    preferred_size: str,
    fallback_size: str = "original",
) -> str | None:
    if preferred_size in available_sizes:
        return preferred_size
    if fallback_size in available_sizes:
        return fallback_size
    if available_sizes:
        return available_sizes[-1]
    return None


def build_tmdb_image_url(
    configuration: dict[str, Any],
    image_path: str | None,
    image_kind: str,
) -> str | None:
    if not image_path:
        return None

    images = configuration.get("images", {})
    secure_base_url = images.get("secure_base_url")
    if not secure_base_url:
        return None

    if image_kind == "poster":
        size = choose_image_size(images.get("poster_sizes", []), "w500")
    elif image_kind == "backdrop":
        size = choose_image_size(images.get("backdrop_sizes", []), "w1280")
    else:
        size = "original"

    if not size:
        return None

    return f"{secure_base_url}{size}{image_path}"


def find_first_reasonable_search_result(
    sample: SampleTitle,
    token: str,
    request_policy: RequestPolicy | None = None,
) -> tuple[int | None, str | None]:
    search_path = "/search/movie" if sample.media_type == "movie" else "/search/tv"
    params: dict[str, Any] = {
        "query": sample.title,
        "include_adult": "false",
    }

    if sample.year:
        if sample.media_type == "movie":
            params["year"] = sample.year
        else:
            params["first_air_date_year"] = sample.year

    try:
        data = fetch_tmdb_json(
            search_path,
            token,
            params=params,
            request_policy=request_policy,
        )
    except TmdbFetchError as exc:
        return None, f"Fallback search failed: {exc}"

    results = data.get("results", [])
    if not isinstance(results, list) or not results:
        return None, "Fallback search returned no results."

    for result in results:
        result_title = result.get("title") or result.get("name")
        if title_matches(sample.title, result_title):
            result_id = result.get("id")
            if isinstance(result_id, int):
                return result_id, "TMDb ID came from fallback search; manually verify before database use."

    first_result = results[0]
    result_id = first_result.get("id")
    if isinstance(result_id, int):
        return result_id, "TMDb ID came from first fallback search result; manually verify before database use."

    return None, "Fallback search did not return a usable TMDb ID."


def get_details_title(details: dict[str, Any], media_type: str) -> str | None:
    if media_type == "movie":
        return details.get("title")
    return details.get("name")


def content_type_from_media_type(media_type: str) -> str | None:
    return MEDIA_TYPE_TO_CONTENT_TYPE.get(media_type)


def target_metadata(sample: SampleTitle) -> dict[str, Any]:
    return {
        "content_type": sample.content_type
        or content_type_from_media_type(sample.media_type),
        "source_name": sample.source_name,
        "source_id": sample.source_id or (
            str(sample.tmdb_id) if sample.tmdb_id is not None else None
        ),
        "priority": sample.priority,
        "ingestion_status": sample.ingestion_status,
        "target_notes": sample.notes,
    }


def build_video_retry_target(
    sample: SampleTitle,
    reason: str,
) -> dict[str, Any]:
    target = {
        "title": sample.title,
        "content_type": sample.content_type
        or content_type_from_media_type(sample.media_type),
        "source_name": sample.source_name,
        "source_id": sample.source_id
        or (str(sample.tmdb_id) if sample.tmdb_id is not None else None),
        "priority": sample.priority,
        "ingestion_status": "retry",
        "notes": reason,
    }
    if sample.original_language:
        target["original_language"] = sample.original_language
    return target


def build_video_review_target(
    sample: SampleTitle,
    reason: str,
    failure_class: str,
) -> dict[str, Any]:
    target = build_video_retry_target(sample, reason)
    target["ingestion_status"] = "review"
    target["videos_failure_class"] = failure_class
    return target


def video_failure_disposition(mapped: dict[str, Any]) -> str | None:
    if mapped.get("videos_snapshot_complete") is True:
        return None
    return "retry" if mapped.get("videos_retryable") is True else "review"


def attach_target_metadata(
    item: dict[str, Any],
    sample: SampleTitle,
) -> dict[str, Any]:
    item.update(target_metadata(sample))
    return item


def build_error_preview_item(
    sample: SampleTitle,
    error_message: str,
    *,
    preferred_language: str | None = None,
    requested_languages: tuple[str, ...] = (),
    retryable: bool = False,
    failure_class: str = "normalization_review",
) -> dict[str, Any]:
    return attach_target_metadata({
        "source_provider": "tmdb",
        "tmdb_id": sample.tmdb_id,
        "media_type": sample.media_type,
        "title": sample.title,
        "original_title": None,
        "overview": None,
        "release_date": None,
        "latest_activity_date": None,
        "year": sample.year,
        "runtime": None,
        "original_language": None,
        "status": None,
        "poster_path": None,
        "backdrop_path": None,
        "poster_url": None,
        "backdrop_url": None,
        "genres": [],
        "vote_average": None,
        "vote_count": None,
        "ratings": [],
        "popularity": None,
        "imdb_id": None,
        "top_cast_names": [],
        "director_or_creator_names": [],
        "series_metadata": None,
        "videos_fetch_status": "failed",
        "videos_snapshot_complete": False,
        "videos_stale_cleanup_safe": False,
        "videos_fetch_error": error_message,
        "videos_fetch_origin": "failed",
        "videos_source_fetched_at": None,
        "videos_timestamp_origin": None,
        "videos_request_signature": None,
        "videos_preferred_language": preferred_language,
        "videos_requested_languages": list(requested_languages),
        "videos_raw_count": 0,
        "videos_accepted_count": 0,
        "videos_rejected_count": 0,
        "videos_rejected": [],
        "videos_ignored_count": 0,
        "videos_ignored": [],
        "videos_warnings": [],
        "videos_retryable": retryable,
        "videos_failure_class": failure_class,
        "videos": [],
        "primary_video_site": None,
        "primary_video_source_id": None,
        "mapping_notes": [error_message],
    }, sample)


def fetch_title_payloads(
    sample: SampleTitle,
    token: str | None,
    refresh: bool,
    language: str = DEFAULT_LANGUAGE,
    video_languages: tuple[str, ...] = ("en", "null"),
    request_policy: RequestPolicy | None = None,
) -> tuple[
    int,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any] | None,
    list[str],
    list[dict[str, Any]],
]:
    notes: list[str] = []
    raw_file_results: list[dict[str, Any]] = []
    tmdb_id = sample.tmdb_id

    if sample.media_type not in {"movie", "tv"}:
        raise TmdbFetchError(
            f"Unsupported media_type '{sample.media_type}' for {sample.title}."
        )

    if not tmdb_id:
        raise TmdbFetchError(f"No usable TMDb ID for {sample.title}.")

    details_path = f"/{sample.media_type}/{tmdb_id}"
    external_ids_path = f"/{sample.media_type}/{tmdb_id}/external_ids"
    credits_path = f"/{sample.media_type}/{tmdb_id}/credits"
    aggregate_credits_path = f"/tv/{tmdb_id}/aggregate_credits"
    raw_details_path = RAW_OUTPUT_DIR / raw_filename(sample.media_type, tmdb_id, "details")
    raw_external_ids_path = RAW_OUTPUT_DIR / raw_filename(
        sample.media_type,
        tmdb_id,
        "external_ids",
    )
    raw_credits_path = RAW_OUTPUT_DIR / raw_filename(
        sample.media_type,
        tmdb_id,
        "credits",
    )
    raw_aggregate_credits_path = RAW_OUTPUT_DIR / raw_filename(
        sample.media_type,
        tmdb_id,
        "aggregate_credits",
    )

    requested_video_languages = merge_video_languages(
        language,
        sample.original_language,
        video_languages,
    )
    detail_params = {
        "append_to_response": "videos",
        "language": language,
        "include_video_language": ",".join(requested_video_languages),
    }
    details, file_result = fetch_or_reuse_json(
        details_path,
        raw_details_path,
        token,
        refresh,
        params=detail_params,
        request_policy=request_policy,
    )
    raw_file_results.append(file_result)
    actual_title = get_details_title(details, sample.media_type)

    if not actual_title:
        notes.append(
            f"Media type validation warning: expected TMDb {sample.media_type} payload for {sample.title}, but no title/name field was returned."
        )

    if not title_matches(sample.title, actual_title):
        note = (
            f"Title mismatch: seed expected '{sample.title}', "
            f"TMDb returned '{actual_title}'. Manually verify tmdb_id {tmdb_id}."
        )
        notes.append(note)
        print(f"  Warning: {note}")

    external_ids, file_result = fetch_or_reuse_json(
        external_ids_path,
        raw_external_ids_path,
        token,
        refresh,
        request_policy=request_policy,
    )
    raw_file_results.append(file_result)
    credits, file_result = fetch_or_reuse_json(
        credits_path,
        raw_credits_path,
        token,
        refresh,
        request_policy=request_policy,
    )
    raw_file_results.append(file_result)
    aggregate_credits = None

    if sample.media_type == "tv":
        try:
            aggregate_credits, file_result = fetch_or_reuse_json(
                aggregate_credits_path,
                raw_aggregate_credits_path,
                token,
                refresh,
                request_policy=request_policy,
            )
            raw_file_results.append(file_result)
        except TmdbFetchError as exc:
            note = (
                "TV aggregate credits fetch failed; regular TV credits remain available "
                f"as fallback: {exc}"
            )
            notes.append(note)
            print(f"  Warning: {note}")

    return tmdb_id, details, external_ids, credits, aggregate_credits, notes, raw_file_results


def top_cast_names(credits: dict[str, Any], limit: int = 5) -> list[str]:
    cast = credits.get("cast", [])
    if not isinstance(cast, list):
        return []
    names = [item.get("name") for item in cast if item.get("name")]
    return names[:limit]


def crew_names_by_jobs(
    credits: dict[str, Any],
    jobs: set[str],
    limit: int = 8,
) -> list[str]:
    crew = credits.get("crew", [])
    if not isinstance(crew, list):
        return []

    names: list[str] = []
    for item in crew:
        job = item.get("job")
        name = item.get("name")
        if job in jobs and name and name not in names:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def map_common_preview_fields(
    details: dict[str, Any],
    external_ids: dict[str, Any],
    credits: dict[str, Any],
    configuration: dict[str, Any],
    media_type: str,
    notes: list[str],
    preferred_video_language: str | None = "en",
) -> dict[str, Any]:
    poster_path = details.get("poster_path")
    backdrop_path = details.get("backdrop_path")
    genres = details.get("genres", [])

    genre_names = []
    if isinstance(genres, list):
        genre_names = [genre.get("name") for genre in genres if genre.get("name")]

    if not poster_path:
        notes.append("Missing poster_path.")
    if not backdrop_path:
        notes.append("Missing backdrop_path.")
    if not genre_names:
        notes.append("No genres returned.")
    if not external_ids.get("imdb_id"):
        notes.append("No imdb_id returned.")

    video_snapshot = normalize_video_snapshot(details, preferred_video_language)
    if not video_snapshot.is_complete:
        notes.append(video_snapshot.error or "Video snapshot is incomplete.")
    elif video_snapshot.rejected_count:
        notes.append(
            f"Rejected {video_snapshot.rejected_count} malformed or duplicate video records."
        )

    preview = {
        "source_provider": "tmdb",
        "tmdb_id": details.get("id"),
        "media_type": media_type,
        "content_type": content_type_from_media_type(media_type),
        "overview": details.get("overview"),
        "runtime": None,
        "original_language": details.get("original_language"),
        "status": details.get("status"),
        "poster_path": poster_path,
        "backdrop_path": backdrop_path,
        "poster_url": build_tmdb_image_url(configuration, poster_path, "poster"),
        "backdrop_url": build_tmdb_image_url(configuration, backdrop_path, "backdrop"),
        "genres": genre_names,
        "vote_average": details.get("vote_average"),
        "vote_count": details.get("vote_count"),
        "ratings": build_tmdb_rating_preview(details, notes),
        "popularity": details.get("popularity"),
        "imdb_id": external_ids.get("imdb_id"),
        "top_cast_names": top_cast_names(credits),
        "director_or_creator_names": [],
        "mapping_notes": notes,
    }
    preview.update(video_snapshot.as_preview_fields())
    return preview


def map_tmdb_movie_preview(
    details: dict[str, Any],
    external_ids: dict[str, Any],
    credits: dict[str, Any],
    configuration: dict[str, Any],
    notes: list[str],
    preferred_video_language: str | None = "en",
) -> dict[str, Any]:
    release_date = details.get("release_date")
    preview = map_common_preview_fields(
        details,
        external_ids,
        credits,
        configuration,
        "movie",
        notes,
        preferred_video_language,
    )
    preview.update(
        {
            "title": details.get("title"),
            "original_title": details.get("original_title"),
            "release_date": release_date,
            "latest_activity_date": release_date,
            "year": year_from_date(release_date),
            "runtime": details.get("runtime"),
            "director_or_creator_names": crew_names_by_jobs(credits, {"Director"}),
            "series_metadata": None,
        }
    )

    if not preview["runtime"]:
        notes.append("Missing runtime.")
    if not preview["director_or_creator_names"]:
        notes.append("No director found in credits.")

    return preview


def map_tmdb_tv_preview(
    details: dict[str, Any],
    external_ids: dict[str, Any],
    credits: dict[str, Any],
    configuration: dict[str, Any],
    notes: list[str],
    preferred_video_language: str | None = "en",
) -> dict[str, Any]:
    release_date = details.get("first_air_date")
    episode_run_time = details.get("episode_run_time")
    runtime = None
    if isinstance(episode_run_time, list) and episode_run_time:
        runtime = episode_run_time[0]

    created_by = details.get("created_by", [])
    creator_names = []
    if isinstance(created_by, list):
        creator_names = [
            creator.get("name") for creator in created_by if creator.get("name")
        ]

    crew_creator_names = crew_names_by_jobs(
        credits,
        {"Creator", "Showrunner", "Director"},
    )
    director_or_creator_names = []
    for name in creator_names + crew_creator_names:
        if name not in director_or_creator_names:
            director_or_creator_names.append(name)

    preview = map_common_preview_fields(
        details,
        external_ids,
        credits,
        configuration,
        "tv",
        notes,
        preferred_video_language,
    )
    preview.update(
        {
            "title": details.get("name"),
            "original_title": details.get("original_name"),
            "release_date": release_date,
            "latest_activity_date": latest_tv_activity_date(details),
            "year": year_from_date(release_date),
            "runtime": runtime,
            "director_or_creator_names": director_or_creator_names,
            "series_metadata": build_series_metadata(details, notes),
        }
    )

    if not runtime:
        notes.append("Missing or empty episode_run_time; runtime is approximate/null.")
    if not director_or_creator_names:
        notes.append("No creator/director names found.")

    return preview


def raw_filename(media_type: str, tmdb_id: int, payload_name: str) -> str:
    return f"{media_type}_{tmdb_id}_{payload_name}.json"


def filter_samples(
    samples: list[SampleTitle],
    args: argparse.Namespace,
) -> list[SampleTitle]:
    selected = samples

    if args.priority:
        priority = str(args.priority).strip().lower()
        selected = [
            sample for sample in selected if (sample.priority or "").lower() == priority
        ]

    if args.source_id:
        source_id = str(args.source_id).strip()
        selected = [sample for sample in selected if sample.source_id == source_id]

    if args.title:
        title = str(args.title).strip().lower()
        selected = [sample for sample in selected if sample.title.lower() == title]

    if args.limit:
        selected = selected[: args.limit]

    return selected


def filters_used(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "priority": args.priority,
        "source_id": args.source_id,
        "title": args.title,
        "limit": args.limit,
        "refresh": args.refresh,
        "language": args.language,
        "video_languages": list(args.video_languages),
        "request_timeout": args.request_timeout,
        "max_retries": args.max_retries,
        "batch_size": args.batch_size,
        "concurrency": args.concurrency,
    }


def process_sample(
    sample: SampleTitle,
    token: str | None,
    refresh: bool,
    configuration: dict[str, Any],
    language: str,
    video_languages: tuple[str, ...],
    request_policy: RequestPolicy,
) -> dict[str, Any]:
    try:
        preferred_language = normalize_language_code(
            language or DEFAULT_LANGUAGE,
            field_name="detail language",
        )
        requested_video_languages = merge_video_languages(
            language or DEFAULT_LANGUAGE,
            sample.original_language,
            video_languages,
        )
    except ValueError as exc:
        error = f"Invalid video language policy for {sample.title}: {exc}"
        return {
            "sample": sample,
            "error": error,
            "mapped": build_error_preview_item(
                sample,
                error,
                failure_class="normalization_review",
            ),
            "notes": [error],
            "raw_file_results": [],
        }

    try:
        (
            _tmdb_id,
            details,
            external_ids,
            credits,
            _aggregate_credits,
            notes,
            raw_file_results,
        ) = fetch_title_payloads(
            sample,
            token,
            refresh,
            language,
            video_languages,
            request_policy,
        )
    except TmdbFetchError as exc:
        return {
            "sample": sample,
            "error": str(exc),
            "mapped": build_error_preview_item(
                sample,
                str(exc),
                preferred_language=preferred_language,
                requested_languages=requested_video_languages,
                retryable=exc.retryable,
                failure_class=exc.failure_class,
            ),
            "notes": [str(exc)],
            "raw_file_results": [],
        }

    if sample.media_type == "movie":
        mapped = map_tmdb_movie_preview(
            details,
            external_ids,
            credits,
            configuration,
            notes,
            preferred_language,
        )
    else:
        mapped = map_tmdb_tv_preview(
            details,
            external_ids,
            credits,
            configuration,
            notes,
            preferred_language,
        )

    details_file_result = raw_file_results[0]
    mapped.update(
        {
            "videos_fetch_origin": details_file_result["status"],
            "videos_source_fetched_at": details_file_result.get(
                "source_fetched_at"
            ),
            "videos_timestamp_origin": details_file_result.get(
                "timestamp_origin"
            ),
            "videos_request_signature": details_file_result.get(
                "request_signature"
            ),
            "videos_preferred_language": preferred_language,
            "videos_requested_languages": list(requested_video_languages),
        }
    )

    return {
        "sample": sample,
        "error": None,
        "mapped": attach_target_metadata(mapped, sample),
        "notes": notes,
        "raw_file_results": raw_file_results,
    }


def build_worker_failure_result(
    sample: SampleTitle,
    error: Exception,
    language: str,
    video_languages: tuple[str, ...],
) -> dict[str, Any]:
    try:
        preferred_language = normalize_language_code(
            language or DEFAULT_LANGUAGE,
            field_name="detail language",
        )
        requested_languages = merge_video_languages(
            language or DEFAULT_LANGUAGE,
            sample.original_language,
            video_languages,
        )
    except ValueError:
        preferred_language = None
        requested_languages = ()
    message = f"Unexpected worker failure: {error}"
    return {
        "sample": sample,
        "error": message,
        "mapped": build_error_preview_item(
            sample,
            message,
            preferred_language=preferred_language,
            requested_languages=requested_languages,
            retryable=False,
            failure_class="normalization_review",
        ),
        "notes": [message],
        "raw_file_results": [],
    }


def resolve_worker_future(
    future: Any,
    sample: SampleTitle,
    language: str,
    video_languages: tuple[str, ...],
) -> dict[str, Any]:
    try:
        return future.result()
    except Exception as exc:  # A single target must not terminate a bounded batch.
        return build_worker_failure_result(
            sample,
            exc,
            language,
            video_languages,
        )


def print_preview_table(items: list[dict[str, Any]]) -> None:
    print("\nMapped preview:")
    header = (
        "Title",
        "Type",
        "Year",
        "Latest",
        "Runtime",
        "Genres",
        "Poster",
        "Backdrop",
        "IMDb",
        "Notes",
    )
    print(
        f"{header[0]:34} {header[1]:6} {header[2]:6} {header[3]:10} {header[4]:8} "
        f"{header[5]:34} {header[6]:7} {header[7]:8} {header[8]:5} {header[9]:5}"
    )
    print("-" * 142)
    for item in items:
        genres = ", ".join(item.get("genres") or [])
        if len(genres) > 32:
            genres = genres[:29] + "..."
        notes_count = len(item.get("mapping_notes") or [])
        print(
            f"{str(item.get('title') or '')[:34]:34} "
            f"{str(item.get('media_type') or '')[:6]:6} "
            f"{str(item.get('year') or '')[:6]:6} "
            f"{str(item.get('latest_activity_date') or '')[:10]:10} "
            f"{str(item.get('runtime') or '')[:8]:8} "
            f"{genres[:34]:34} "
            f"{'yes' if item.get('poster_url') else 'no':7} "
            f"{'yes' if item.get('backdrop_url') else 'no':8} "
            f"{'yes' if item.get('imdb_id') else 'no':5} "
            f"{notes_count if notes_count else '-':5}"
        )


def print_preview_totals(
    items: list[dict[str, Any]],
    total_targets_loaded: int,
    total_processed: int,
    total_skipped: int,
) -> None:
    total_with_poster = sum(1 for item in items if item.get("poster_url"))
    total_with_backdrop = sum(1 for item in items if item.get("backdrop_url"))
    total_with_imdb = sum(1 for item in items if item.get("imdb_id"))
    total_with_tmdb_rating = sum(1 for item in items if item.get("ratings"))
    total_with_videos = sum(1 for item in items if item.get("videos"))
    total_with_primary_video = sum(
        1 for item in items if item.get("primary_video_source_id")
    )
    total_with_notes = sum(1 for item in items if item.get("mapping_notes"))

    print("\nPreview totals:")
    print(f"- Total targets loaded: {total_targets_loaded}")
    print(f"- Total processed: {total_processed}")
    print(f"- Total skipped: {total_skipped}")
    print(f"- Total preview items: {len(items)}")
    print(f"- Total with poster_url: {total_with_poster}")
    print(f"- Total with backdrop_url: {total_with_backdrop}")
    print(f"- Total with imdb_id: {total_with_imdb}")
    print(f"- Total with TMDb rating preview: {total_with_tmdb_rating}")
    print(f"- Total with accepted videos: {total_with_videos}")
    print(f"- Total with a primary video: {total_with_primary_video}")
    print(f"- Total with warnings/mapping_notes: {total_with_notes}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target_path = resolve_target_path(args.targets)

    try:
        target_result = load_targets(target_path)
    except TargetConfigError as exc:
        print(f"Could not load ingestion targets: {exc}")
        print("No TMDb requests were made.")
        print("No database changes were made.")
        return 1

    print(f"Target file used: {relative_path(target_result.path)}")
    print(f"Total targets loaded: {target_result.total_targets}")
    print(f"Valid fetch targets: {len(target_result.samples)}")
    print(f"Targets skipped before fetch: {target_result.skipped_targets}")

    if target_result.warnings:
        print("\nTarget warnings:")
        for warning in target_result.warnings:
            print(f"- {warning}")

    if not target_result.samples:
        print("No valid targets were loaded. Check the target config file.")
        print("No TMDb requests were made.")
        print("No database changes were made.")
        return 1

    selected_samples = filter_samples(target_result.samples, args)
    if not selected_samples:
        print("No targets matched the requested fetch filters.")
        print("No TMDb requests were made.")
        print("No database changes were made.")
        return 1

    token = os.getenv(TOKEN_ENV_VAR)
    if not token:
        print(
            f"{TOKEN_ENV_VAR} is not set. Existing raw files can still be reused, "
            "but missing raw files or --refresh will fail."
        )

    RAW_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    request_policy = RequestPolicy(
        timeout_seconds=args.request_timeout,
        max_retries=args.max_retries,
    )

    try:
        configuration, configuration_file_result = fetch_or_reuse_json(
            "/configuration",
            RAW_OUTPUT_DIR / "configuration.json",
            token,
            args.refresh,
            request_policy=request_policy,
        )
    except TmdbFetchError as exc:
        print(f"Could not load TMDb configuration: {exc}")
        print("No database changes were made.")
        return 1

    mapped_items: list[dict[str, Any]] = []
    raw_files_fetched: list[str] = []
    raw_files_reused: list[str] = []
    per_target_statuses: list[dict[str, Any]] = []
    video_retry_targets: list[dict[str, Any]] = []
    video_review_targets: list[dict[str, Any]] = []
    errors: list[str] = []
    run_warnings = target_result.warnings.copy()

    if configuration_file_result["status"] == "fetched":
        raw_files_fetched.append(configuration_file_result["path"])
    else:
        raw_files_reused.append(configuration_file_result["path"])

    print(f"Filters used: {filters_used(args)}")
    print(f"Targets selected: {len(selected_samples)}")
    print(f"Targets not selected: {len(target_result.samples) - len(selected_samples)}")

    def record_processed_result(result: dict[str, Any]) -> None:
        sample = result["sample"]
        print(f"Processing {sample.title} ({sample.media_type})...")
        error = result["error"]
        if error:
            message = f"{sample.title}: {error}"
            print(f"  Error: {message}")
            errors.append(message)
            per_target_statuses.append(
                {
                    "title": sample.title,
                    "content_type": sample.content_type,
                    "source_name": sample.source_name,
                    "source_id": sample.source_id,
                    "priority": sample.priority,
                    "status": "failed",
                    "raw_files": [],
                    "warnings": [error],
                }
            )
            mapped_items.append(result["mapped"])
            if video_failure_disposition(result["mapped"]) == "retry":
                video_retry_targets.append(build_video_retry_target(sample, error))
            else:
                video_review_targets.append(
                    build_video_review_target(
                        sample,
                        error,
                        str(
                            result["mapped"].get("videos_failure_class")
                            or "normalization_review"
                        ),
                    )
                )
            return

        notes = result["notes"]
        raw_file_results = result["raw_file_results"]
        for file_result in raw_file_results:
            if file_result["status"] == "fetched":
                raw_files_fetched.append(file_result["path"])
            else:
                raw_files_reused.append(file_result["path"])

        mapped_items.append(result["mapped"])
        if not result["mapped"].get("videos_snapshot_complete"):
            disposition_reason = (
                result["mapped"].get("videos_fetch_error")
                or "The appended videos snapshot was incomplete."
            )
            if video_failure_disposition(result["mapped"]) == "retry":
                video_retry_targets.append(
                    build_video_retry_target(sample, disposition_reason)
                )
            else:
                video_review_targets.append(
                    build_video_review_target(
                        sample,
                        disposition_reason,
                        str(
                            result["mapped"].get("videos_failure_class")
                            or "normalization_review"
                        ),
                    )
                )
        run_warnings.extend(f"{sample.title}: {note}" for note in notes)
        target_status = (
            "fetched"
            if any(file_result["status"] == "fetched" for file_result in raw_file_results)
            else "reused"
        )
        per_target_statuses.append(
            {
                "title": sample.title,
                "content_type": sample.content_type,
                "source_name": sample.source_name,
                "source_id": sample.source_id,
                "priority": sample.priority,
                "status": target_status,
                "raw_files": raw_file_results,
                "warnings": notes,
            }
        )

    max_workers = min(args.concurrency, args.batch_size)
    for batch_start in range(0, len(selected_samples), args.batch_size):
        batch = selected_samples[batch_start : batch_start + args.batch_size]
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    process_sample,
                    sample,
                    token,
                    args.refresh,
                    configuration,
                    args.language,
                    args.video_languages,
                    request_policy,
                ): (index, sample)
                for index, sample in enumerate(batch)
            }
            ordered: list[dict[str, Any] | None] = [None] * len(batch)
            for future in as_completed(futures):
                index, sample = futures[future]
                ordered[index] = resolve_worker_future(
                    future,
                    sample,
                    args.language,
                    args.video_languages,
                )
            for result in ordered:
                if result is not None:
                    record_processed_result(result)

    if not mapped_items:
        print("No titles were mapped. Check the token, network, and TMDb IDs.")
        return 1

    preview_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inspection_only": True,
        "source_provider": "tmdb",
        "source_target_path": relative_path(target_result.path),
        "total_targets_loaded": target_result.total_targets,
        "licensing_note": (
            "Prototype/non-commercial inspection only. Follow TMDb terms, do not commit API keys, "
            "do not use TMDb content for ML/AI training, and do not assume permanent storage rights."
        ),
        "items": mapped_items,
    }
    save_json(PREVIEW_OUTPUT_PATH, preview_payload)
    retry_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_run_report": relative_path(RUN_REPORT_OUTPUT_PATH),
        "description": (
            "Titles whose appended TMDb videos request failed with an automatic "
            "retry disposition. This file can be passed back to --targets for a "
            "bounded retry run."
        ),
        "targets": video_retry_targets,
    }
    save_json(VIDEO_RETRY_OUTPUT_PATH, retry_payload)
    review_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_run_report": relative_path(RUN_REPORT_OUTPUT_PATH),
        "description": (
            "Titles requiring manual source or normalization review. These targets "
            "are not scheduled for automatic retry."
        ),
        "targets": video_review_targets,
    }
    save_json(VIDEO_REVIEW_OUTPUT_PATH, review_payload)

    targets_fetched = sum(
        1 for status in per_target_statuses if status.get("status") == "fetched"
    )
    targets_reused = sum(
        1 for status in per_target_statuses if status.get("status") == "reused"
    )
    targets_processed = targets_fetched + targets_reused
    total_skipped = target_result.skipped_targets

    report_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "script_name": Path(__file__).name,
        "target_config_path": relative_path(target_result.path),
        "filters_used": filters_used(args),
        "targets_loaded": target_result.total_targets,
        "targets_selected": len(selected_samples),
        "targets_processed": targets_processed,
        "targets_skipped": total_skipped,
        "ratings_preview_count": sum(1 for item in mapped_items if item.get("ratings")),
        "videos_preview_count": sum(1 for item in mapped_items if item.get("videos")),
        "primary_video_count": sum(
            1 for item in mapped_items if item.get("primary_video_source_id")
        ),
        "video_retry_target_count": len(video_retry_targets),
        "video_retry_target_path": relative_path(VIDEO_RETRY_OUTPUT_PATH),
        "video_review_target_count": len(video_review_targets),
        "video_review_target_path": relative_path(VIDEO_REVIEW_OUTPUT_PATH),
        "raw_files_fetched": raw_files_fetched,
        "raw_files_reused": raw_files_reused,
        "warnings": run_warnings,
        "failures": errors,
        "per_target": per_target_statuses,
    }
    save_json(RUN_REPORT_OUTPUT_PATH, report_payload)

    print("\nTitles processed:")
    for item in mapped_items:
        print(f"- {item.get('title')} ({item.get('media_type')}, {item.get('tmdb_id')})")

    if raw_files_fetched:
        print("\nRaw files fetched:")
        for path in raw_files_fetched:
            print(f"- {path}")
    if raw_files_reused:
        print("\nRaw files reused:")
        for path in raw_files_reused:
            print(f"- {path}")

    print(f"\nProcessed preview saved: {PREVIEW_OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print(f"Run report saved: {RUN_REPORT_OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print(
        "Video retry targets saved: "
        f"{VIDEO_RETRY_OUTPUT_PATH.relative_to(REPO_ROOT)} "
        f"({len(video_retry_targets)} targets)"
    )
    print(
        "Video review targets saved: "
        f"{VIDEO_REVIEW_OUTPUT_PATH.relative_to(REPO_ROOT)} "
        f"({len(video_review_targets)} targets)"
    )
    print_preview_table(mapped_items)
    print_preview_totals(
        mapped_items,
        target_result.total_targets,
        targets_processed,
        total_skipped,
    )

    warning_items = [
        item for item in mapped_items if item.get("mapping_notes")
    ]
    if warning_items:
        print("\nMapping warnings:")
        for item in warning_items:
            print(f"- {item.get('title')}:")
            for note in item.get("mapping_notes") or []:
                print(f"  - {note}")

    if errors:
        print("\nWarnings/errors:")
        for error in errors:
            print(f"- {error}")

    print("\nRun summary:")
    print(f"- Filters used: {filters_used(args)}")
    print(f"- Selected target count: {len(selected_samples)}")
    print(f"- Fetched count: {targets_fetched}")
    print(f"- Reused count: {targets_reused}")
    print(f"- Skipped count: {total_skipped}")
    print(f"- Failure count: {len(errors)}")
    print(f"- Video retry target count: {len(video_retry_targets)}")
    print(f"- Video review target count: {len(video_review_targets)}")
    print(f"- Report path: {RUN_REPORT_OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print("\nNo database changes were made.")
    return 0 if targets_processed else 1


if __name__ == "__main__":
    sys.exit(main())
