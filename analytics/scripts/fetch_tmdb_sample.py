#!/usr/bin/env python3
"""
Inspection-only TMDb sample fetch script.

- This script does not modify PostgreSQL.
- It uses TMDb as a prototype metadata provider.
- TMDb data must be used according to TMDb terms.
- Do not commit API tokens.
- Run from repository root:

    export TMDB_READ_ACCESS_TOKEN="..."
    python3 analytics/scripts/fetch_tmdb_sample.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
    from requests import RequestException
except ImportError:  # pragma: no cover - helpful when dependencies are not installed yet.
    requests = None

    class RequestException(Exception):
        pass


API_BASE_URL = "https://api.themoviedb.org/3"
TOKEN_ENV_VAR = "TMDB_READ_ACCESS_TOKEN"
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_OUTPUT_DIR = REPO_ROOT / "analytics" / "raw" / "tmdb"
PROCESSED_OUTPUT_DIR = REPO_ROOT / "analytics" / "processed" / "tmdb"
PREVIEW_OUTPUT_PATH = PROCESSED_OUTPUT_DIR / "sample_mapping_preview.json"
RUN_REPORT_DIR = PROCESSED_OUTPUT_DIR / "run_reports"
RUN_REPORT_OUTPUT_PATH = RUN_REPORT_DIR / "content_fetch_run_report.json"
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


@dataclass(frozen=True)
class TargetLoadResult:
    path: Path
    total_targets: int
    skipped_targets: int
    warnings: list[str]
    samples: list[SampleTitle]


class TmdbFetchError(RuntimeError):
    pass


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
) -> dict[str, Any]:
    if requests is None:
        raise TmdbFetchError(
            "Missing dependency 'requests'. Run `pip install -r backend/requirements.txt`."
        )

    url = f"{API_BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
    except RequestException as exc:
        raise TmdbFetchError(f"Request failed for {path}: {exc}") from exc

    if response.status_code == 429:
        raise TmdbFetchError(
            f"TMDb rate limit hit for {path}. Wait and try again."
        )

    if not response.ok:
        raise TmdbFetchError(
            f"TMDb request failed for {path}: HTTP {response.status_code} - {response.text[:300]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise TmdbFetchError(f"TMDb returned malformed JSON for {path}") from exc

    if not isinstance(data, dict):
        raise TmdbFetchError(f"TMDb returned unexpected JSON shape for {path}")

    return data


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
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
) -> tuple[dict[str, Any], dict[str, str]]:
    if raw_path.exists() and not refresh:
        return load_cached_json(raw_path), {
            "path": relative_path(raw_path),
            "status": "reused",
        }

    if not token:
        raise TmdbFetchError(
            f"Missing {TOKEN_ENV_VAR}; cannot fetch {api_path} for {relative_path(raw_path)}."
        )

    data = fetch_tmdb_json(api_path, token, params=params)
    save_json(raw_path, data)
    return data, {
        "path": relative_path(raw_path),
        "status": "fetched",
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
        data = fetch_tmdb_json(search_path, token, params=params)
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


def attach_target_metadata(
    item: dict[str, Any],
    sample: SampleTitle,
) -> dict[str, Any]:
    item.update(target_metadata(sample))
    return item


def build_error_preview_item(sample: SampleTitle, error_message: str) -> dict[str, Any]:
    return attach_target_metadata({
        "source_provider": "tmdb",
        "tmdb_id": sample.tmdb_id,
        "media_type": sample.media_type,
        "title": sample.title,
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
        "popularity": None,
        "imdb_id": None,
        "top_cast_names": [],
        "director_or_creator_names": [],
        "series_metadata": None,
        "mapping_notes": [error_message],
    }, sample)


def fetch_title_payloads(
    sample: SampleTitle,
    token: str | None,
    refresh: bool,
) -> tuple[
    int,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any] | None,
    list[str],
    list[dict[str, str]],
]:
    notes: list[str] = []
    raw_file_results: list[dict[str, str]] = []
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

    details, file_result = fetch_or_reuse_json(
        details_path,
        raw_details_path,
        token,
        refresh,
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
    )
    raw_file_results.append(file_result)
    credits, file_result = fetch_or_reuse_json(
        credits_path,
        raw_credits_path,
        token,
        refresh,
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

    return {
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
        "popularity": details.get("popularity"),
        "imdb_id": external_ids.get("imdb_id"),
        "top_cast_names": top_cast_names(credits),
        "director_or_creator_names": [],
        "mapping_notes": notes,
    }


def map_tmdb_movie_preview(
    details: dict[str, Any],
    external_ids: dict[str, Any],
    credits: dict[str, Any],
    configuration: dict[str, Any],
    notes: list[str],
) -> dict[str, Any]:
    release_date = details.get("release_date")
    preview = map_common_preview_fields(
        details,
        external_ids,
        credits,
        configuration,
        "movie",
        notes,
    )
    preview.update(
        {
            "title": details.get("title"),
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
    )
    preview.update(
        {
            "title": details.get("name"),
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
    }


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
    total_with_notes = sum(1 for item in items if item.get("mapping_notes"))

    print("\nPreview totals:")
    print(f"- Total targets loaded: {total_targets_loaded}")
    print(f"- Total processed: {total_processed}")
    print(f"- Total skipped: {total_skipped}")
    print(f"- Total preview items: {len(items)}")
    print(f"- Total with poster_url: {total_with_poster}")
    print(f"- Total with backdrop_url: {total_with_backdrop}")
    print(f"- Total with imdb_id: {total_with_imdb}")
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

    try:
        configuration, configuration_file_result = fetch_or_reuse_json(
            "/configuration",
            RAW_OUTPUT_DIR / "configuration.json",
            token,
            args.refresh,
        )
    except TmdbFetchError as exc:
        print(f"Could not load TMDb configuration: {exc}")
        print("No database changes were made.")
        return 1

    mapped_items: list[dict[str, Any]] = []
    raw_files_fetched: list[str] = []
    raw_files_reused: list[str] = []
    per_target_statuses: list[dict[str, Any]] = []
    errors: list[str] = []
    run_warnings = target_result.warnings.copy()

    if configuration_file_result["status"] == "fetched":
        raw_files_fetched.append(configuration_file_result["path"])
    else:
        raw_files_reused.append(configuration_file_result["path"])

    print(f"Filters used: {filters_used(args)}")
    print(f"Targets selected: {len(selected_samples)}")
    print(f"Targets not selected: {len(target_result.samples) - len(selected_samples)}")

    for sample in selected_samples:
        print(f"Processing {sample.title} ({sample.media_type})...")
        try:
            (
                tmdb_id,
                details,
                external_ids,
                credits,
                aggregate_credits,
                notes,
                raw_file_results,
            ) = fetch_title_payloads(
                sample,
                token,
                args.refresh,
            )
        except TmdbFetchError as exc:
            message = f"{sample.title}: {exc}"
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
                    "warnings": [str(exc)],
                }
            )
            mapped_items.append(build_error_preview_item(sample, str(exc)))
            continue

        for result in raw_file_results:
            if result["status"] == "fetched":
                raw_files_fetched.append(result["path"])
            else:
                raw_files_reused.append(result["path"])

        if sample.media_type == "movie":
            mapped = map_tmdb_movie_preview(
                details,
                external_ids,
                credits,
                configuration,
                notes,
            )
        else:
            mapped = map_tmdb_tv_preview(
                details,
                external_ids,
                credits,
                configuration,
                notes,
            )
        mapped_items.append(attach_target_metadata(mapped, sample))
        run_warnings.extend(f"{sample.title}: {note}" for note in notes)
        target_status = (
            "fetched"
            if any(result["status"] == "fetched" for result in raw_file_results)
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
    print(f"- Report path: {RUN_REPORT_OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print("\nNo database changes were made.")
    return 0 if targets_processed else 1


if __name__ == "__main__":
    sys.exit(main())
