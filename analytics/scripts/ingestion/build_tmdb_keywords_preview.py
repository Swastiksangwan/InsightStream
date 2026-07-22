#!/usr/bin/env python3
"""
Preview-only TMDb keyword fetcher for local catalog titles.

- Reads local content and TMDb IDs from PostgreSQL.
- Fetches TMDb movie/TV keyword endpoints.
- Writes processed preview and run report JSON files.
- Does not modify the database.
- Does not fetch reviews.

Run from repository root:

    export DATABASE_URL="..."
    export TMDB_READ_ACCESS_TOKEN="..."
    python3 -m analytics.scripts.ingestion.build_tmdb_keywords_preview --limit 25
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
    from requests import ConnectionError as RequestsConnectionError
    from requests import RequestException, Timeout
except ImportError:  # pragma: no cover - helpful when dependencies are not installed yet.
    requests = None

    class RequestException(Exception):
        pass

    class Timeout(RequestException):
        pass

    class RequestsConnectionError(RequestException):
        pass

try:
    from sqlalchemy import create_engine, text
except ImportError:  # pragma: no cover - helper tests should not require DB dependencies.
    create_engine = None
    text = None


API_BASE_URL = "https://api.themoviedb.org/3"
TOKEN_ENV_VAR = "TMDB_READ_ACCESS_TOKEN"
DATABASE_URL_ENV_VAR = "DATABASE_URL"
from analytics.scripts.common.paths import REPO_ROOT
DEFAULT_OUTPUT_PATH = (
    REPO_ROOT / "analytics" / "processed" / "tmdb_keywords" / "tmdb_keywords_preview.json"
)
DEFAULT_REPORT_PATH = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "tmdb_keywords"
    / "run_reports"
    / "tmdb_keywords_report.json"
)
DEFAULT_MAX_RETRIES = 2
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

CONTENT_TYPE_ALIASES = {
    "movie": "movie",
    "film": "movie",
    "series": "series",
    "tv": "series",
    "show": "series",
}

NOISY_KEYWORDS = {
    "aftercreditsstinger",
    "based on novel or book",
    "based on true story",
    "duringcreditsstinger",
    "female protagonist",
    "male protagonist",
    "remake",
    "sequel",
    "spin off",
    "woman director",
}

USEFUL_KEYWORD_HINTS = {
    "alien",
    "artificial intelligence",
    "bleak",
    "coming of age",
    "dark comedy",
    "detective",
    "dystopia",
    "family comedy",
    "feel-good",
    "haunting",
    "investigation",
    "murder",
    "political drama",
    "revenge",
    "serial killer",
    "slow burn",
    "space",
    "survival",
    "suspense",
    "time travel",
}


@dataclass(frozen=True)
class LocalTitle:
    content_id: int
    title: str
    content_type: str
    tmdb_id: str | None


@dataclass(frozen=True)
class TargetSelectors:
    content_ids: set[int]
    tmdb_ids: set[str]
    titles: set[str]
    warnings: list[str]

    @property
    def has_selectors(self) -> bool:
        return bool(self.content_ids or self.tmdb_ids or self.titles)


class TmdbKeywordsError(RuntimeError):
    pass


class TmdbKeywordFetchError(TmdbKeywordsError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        transient: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.transient = transient


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be zero or a positive integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be zero or a positive integer")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a preview-only TMDb keywords file for local catalog content."
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        help="Cap selected local titles after filtering.",
    )
    parser.add_argument(
        "--content-type",
        choices=["movie", "series", "all"],
        default="all",
        help="Limit local catalog selection by content type. Defaults to all.",
    )
    parser.add_argument(
        "--target-file",
        help=(
            "Optional JSON target file used to select local titles by content_id/id, "
            "tmdb_id/source_id/external_id, or title. Target files are selection-only."
        ),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH.relative_to(REPO_ROOT)),
        help=(
            "Preview output path. Defaults to "
            f"{DEFAULT_OUTPUT_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--report-output",
        default=str(DEFAULT_REPORT_PATH.relative_to(REPO_ROOT)),
        help=(
            "Run report output path. Defaults to "
            f"{DEFAULT_REPORT_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--max-retries",
        type=non_negative_int,
        default=DEFAULT_MAX_RETRIES,
        help=(
            "Retry transient TMDb request failures this many times. Defaults to "
            f"{DEFAULT_MAX_RETRIES}, for {DEFAULT_MAX_RETRIES + 1} total attempts."
        ),
    )
    parser.add_argument(
        "--write-retry-targets",
        help=(
            "Optional path for a target file containing failed rows that can be "
            "passed back with --target-file."
        ),
    )
    return parser.parse_args(argv)


def resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def normalize_content_type(value: str | None) -> str | None:
    if value is None:
        return None
    return CONTENT_TYPE_ALIASES.get(str(value).strip().lower())


def tmdb_keywords_endpoint(content_type: str, tmdb_id: str | int) -> str:
    normalized_type = normalize_content_type(content_type)
    if normalized_type == "movie":
        return f"/movie/{tmdb_id}/keywords"
    if normalized_type == "series":
        return f"/tv/{tmdb_id}/keywords"
    raise ValueError(f"Unsupported content type for TMDb keywords: {content_type}")


def normalize_keyword_response(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    raw_keywords = payload.get("keywords")
    if not isinstance(raw_keywords, list):
        raw_keywords = payload.get("results")
    if not isinstance(raw_keywords, list):
        return [], 0

    keywords: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw_keyword in raw_keywords:
        if not isinstance(raw_keyword, dict):
            continue
        name_value = raw_keyword.get("name")
        if name_value is None:
            continue
        keyword_name = str(name_value).strip()
        if not keyword_name:
            continue

        keyword_id = raw_keyword.get("id")
        keyword_id_key = "" if keyword_id is None else str(keyword_id).strip()
        dedupe_key = (keyword_id_key, keyword_name.casefold())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        keywords.append(
            {
                "keyword_id": keyword_id,
                "keyword_name": keyword_name,
            }
        )

    return keywords, len(raw_keywords)


def fetch_tmdb_json(path: str, token: str) -> dict[str, Any]:
    if requests is None:
        raise TmdbKeywordFetchError(
            "Missing dependency 'requests'. Run `pip install -r backend/requirements.txt`."
        )

    url = f"{API_BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=20)
    except (Timeout, RequestsConnectionError) as exc:
        raise TmdbKeywordFetchError(
            f"Transient request failed for {path}: {exc}",
            transient=True,
        ) from exc
    except RequestException as exc:
        raise TmdbKeywordFetchError(f"Request failed for {path}: {exc}") from exc

    if response.status_code == 429:
        raise TmdbKeywordFetchError(
            f"TMDb rate limit hit for {path}. Wait and try again.",
            status_code=429,
            transient=True,
        )

    if not response.ok:
        raise TmdbKeywordFetchError(
            f"TMDb request failed for {path}: HTTP {response.status_code} - {response.text[:300]}",
            status_code=response.status_code,
            transient=response.status_code in TRANSIENT_STATUS_CODES,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise TmdbKeywordFetchError(f"TMDb returned malformed JSON for {path}") from exc

    if not isinstance(payload, dict):
        raise TmdbKeywordFetchError(f"TMDb returned unexpected JSON shape for {path}")

    return payload


def is_transient_fetch_error(error: TmdbKeywordFetchError) -> bool:
    return error.transient or error.status_code in TRANSIENT_STATUS_CODES


def retry_sleep_seconds(retry_number: int) -> float:
    return min(0.4 * (2 ** max(retry_number - 1, 0)), 2.0)


def read_local_catalog(database_url: str, content_type_filter: str) -> list[LocalTitle]:
    if create_engine is None or text is None:
        raise TmdbKeywordsError(
            "Missing dependency 'sqlalchemy'. Run `pip install -r backend/requirements.txt`."
        )

    query = text(
        """
        SELECT
            c.id AS content_id,
            c.title AS title,
            c.content_type AS content_type,
            ei.external_id AS tmdb_id
        FROM content c
        LEFT JOIN external_ids ei
            ON ei.content_id = c.id
            AND LOWER(ei.source_name) = 'tmdb'
        ORDER BY c.id ASC
        """
    )

    engine = create_engine(database_url)
    titles: list[LocalTitle] = []
    with engine.connect() as connection:
        rows = connection.execute(query).mappings().all()

    for row in rows:
        normalized_type = normalize_content_type(row["content_type"])
        if normalized_type is None:
            continue
        if content_type_filter != "all" and normalized_type != content_type_filter:
            continue
        tmdb_id = row["tmdb_id"]
        titles.append(
            LocalTitle(
                content_id=int(row["content_id"]),
                title=str(row["title"]),
                content_type=normalized_type,
                tmdb_id=str(tmdb_id).strip() if tmdb_id is not None else None,
            )
        )

    return titles


def load_target_selectors(path: Path) -> TargetSelectors:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TmdbKeywordsError(f"Target file not found: {relative_path(path)}") from exc
    except json.JSONDecodeError as exc:
        raise TmdbKeywordsError(
            f"Target file is not valid JSON: {relative_path(path)} - {exc}"
        ) from exc

    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("targets"), list):
            rows = payload["targets"]
        elif isinstance(payload.get("items"), list):
            rows = payload["items"]
        else:
            rows = []
    else:
        rows = []

    content_ids: set[int] = set()
    tmdb_ids: set[str] = set()
    titles: set[str] = set()
    warnings: list[str] = []

    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            warnings.append(f"Target row {index} is not an object and was ignored.")
            continue

        content_id = row.get("content_id", row.get("id"))
        if content_id is not None:
            try:
                content_ids.add(int(content_id))
            except (TypeError, ValueError):
                warnings.append(f"Target row {index} has invalid content_id: {content_id}")

        source_name = str(row.get("source_name", "tmdb")).strip().lower()
        if source_name and source_name != "tmdb":
            continue

        tmdb_id = row.get("tmdb_id", row.get("source_id", row.get("external_id")))
        if tmdb_id is not None and str(tmdb_id).strip():
            tmdb_ids.add(str(tmdb_id).strip())

        title = row.get("title")
        if title is not None and str(title).strip():
            titles.add(str(title).strip().casefold())

    if not rows:
        warnings.append(
            f"Target file {relative_path(path)} did not contain a list, targets, or items array."
        )

    return TargetSelectors(
        content_ids=content_ids,
        tmdb_ids=tmdb_ids,
        titles=titles,
        warnings=warnings,
    )


def apply_target_selectors(
    titles: list[LocalTitle],
    selectors: TargetSelectors,
) -> list[LocalTitle]:
    if not selectors.has_selectors:
        return []

    selected: list[LocalTitle] = []
    for title in titles:
        title_tmdb_id = title.tmdb_id or ""
        if (
            title.content_id in selectors.content_ids
            or title_tmdb_id in selectors.tmdb_ids
            or title.title.casefold() in selectors.titles
        ):
            selected.append(title)

    return selected


def fetch_keywords_for_title(
    title: LocalTitle,
    token: str,
    fetched_at: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    try:
        endpoint = tmdb_keywords_endpoint(title.content_type, title.tmdb_id or "")
    except (ValueError, TypeError) as exc:
        return {
            "content_id": title.content_id,
            "title": title.title,
            "content_type": title.content_type,
            "tmdb_id": title.tmdb_id,
            "fetch_status": "failed",
            "error_status_code": None,
            "error_message": str(exc),
            "attempt_count": 0,
            "retry_performed": False,
            "retry_attempts_performed": 0,
            "fetched_at": fetched_at,
        }

    attempt_count = 0
    retry_attempts_performed = 0
    total_attempts = max_retries + 1

    for attempt in range(1, total_attempts + 1):
        attempt_count = attempt
        try:
            payload = fetch_tmdb_json(endpoint, token)
            keywords, raw_keyword_count = normalize_keyword_response(payload)
            return {
                "content_id": title.content_id,
                "title": title.title,
                "content_type": title.content_type,
                "tmdb_id": title.tmdb_id,
                "fetch_status": "success",
                "keyword_count": len(keywords),
                "keywords": keywords,
                "raw_keyword_count": raw_keyword_count,
                "attempt_count": attempt_count,
                "retry_performed": retry_attempts_performed > 0,
                "retry_attempts_performed": retry_attempts_performed,
                "fetched_at": fetched_at,
            }
        except TmdbKeywordFetchError as exc:
            can_retry = attempt <= max_retries and is_transient_fetch_error(exc)
            if can_retry:
                retry_attempts_performed += 1
                time.sleep(retry_sleep_seconds(retry_attempts_performed))
                continue

            return {
                "content_id": title.content_id,
                "title": title.title,
                "content_type": title.content_type,
                "tmdb_id": title.tmdb_id,
                "fetch_status": "failed",
                "error_status_code": exc.status_code,
                "error_message": str(exc),
                "attempt_count": attempt_count,
                "retry_performed": retry_attempts_performed > 0,
                "retry_attempts_performed": retry_attempts_performed,
                "fetched_at": fetched_at,
            }
        except (ValueError, TypeError) as exc:
            return {
                "content_id": title.content_id,
                "title": title.title,
                "content_type": title.content_type,
                "tmdb_id": title.tmdb_id,
                "fetch_status": "failed",
                "error_status_code": None,
                "error_message": str(exc),
                "attempt_count": attempt_count,
                "retry_performed": retry_attempts_performed > 0,
                "retry_attempts_performed": retry_attempts_performed,
                "fetched_at": fetched_at,
            }

    return {
        "content_id": title.content_id,
        "title": title.title,
        "content_type": title.content_type,
        "tmdb_id": title.tmdb_id,
        "fetch_status": "failed",
        "error_status_code": None,
        "error_message": f"TMDb request failed after {attempt_count} attempts.",
        "attempt_count": attempt_count,
        "retry_performed": retry_attempts_performed > 0,
        "retry_attempts_performed": retry_attempts_performed,
        "fetched_at": fetched_at,
    }


def build_retry_targets(
    items: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    targets = []
    for item in items:
        if item.get("fetch_status") != "failed":
            continue
        targets.append(
            {
                "content_id": item.get("content_id"),
                "title": item.get("title"),
                "content_type": item.get("content_type"),
                "source_name": "tmdb",
                "source_id": item.get("tmdb_id"),
                "previous_error_message": item.get("error_message"),
                "previous_error_status_code": item.get("error_status_code"),
            }
        )

    return {
        "description": (
            "Retry targets generated from failed TMDb keyword preview rows. "
            "Pass this file to build_tmdb_keywords_preview.py with --target-file."
        ),
        "generated_at": generated_at,
        "source": "tmdb_keywords_retry_targets",
        "targets": targets,
    }


def keyword_name(keyword: dict[str, Any]) -> str:
    return str(keyword.get("keyword_name", "")).strip()


def keyword_frequency(items: list[dict[str, Any]]) -> tuple[Counter[str], dict[str, str]]:
    frequency: Counter[str] = Counter()
    display_names: dict[str, str] = {}

    for item in items:
        if item.get("fetch_status") != "success":
            continue
        seen_for_title: set[str] = set()
        for keyword in item.get("keywords", []):
            name = keyword_name(keyword)
            if not name:
                continue
            normalized_name = name.casefold()
            display_names.setdefault(normalized_name, name)
            seen_for_title.add(normalized_name)
        frequency.update(seen_for_title)

    return frequency, display_names


def top_repeated_keywords(
    items: list[dict[str, Any]],
    limit: int = 25,
) -> list[dict[str, Any]]:
    frequency, display_names = keyword_frequency(items)
    return [
        {
            "keyword_name": display_names[name],
            "title_count": count,
        }
        for name, count in frequency.most_common(limit)
    ]


def classify_keywords(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    frequency, display_names = keyword_frequency(items)
    useful: list[dict[str, Any]] = []
    noisy: list[dict[str, Any]] = []

    for name, count in frequency.most_common():
        display_name = display_names[name]
        is_noisy = name in NOISY_KEYWORDS or (count >= 5 and len(name) <= 3)
        is_useful = name in USEFUL_KEYWORD_HINTS or any(
            hint in name for hint in USEFUL_KEYWORD_HINTS
        )
        record = {
            "keyword_name": display_name,
            "title_count": count,
        }
        if is_noisy:
            noisy.append(record)
        elif is_useful:
            useful.append(record)

    return useful[:25], noisy[:25]


def sample_keyword_rows(
    items: list[dict[str, Any]],
    limit: int = 25,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if item.get("fetch_status") != "success":
            continue
        for keyword in item.get("keywords", []):
            rows.append(
                {
                    "content_id": item.get("content_id"),
                    "title": item.get("title"),
                    "content_type": item.get("content_type"),
                    "keyword_id": keyword.get("keyword_id"),
                    "keyword_name": keyword.get("keyword_name"),
                }
            )
            if len(rows) >= limit:
                return rows
    return rows


def coverage_percent(titles_with_keywords: int, successful_fetches: int) -> float:
    if successful_fetches <= 0:
        return 0.0
    return round(titles_with_keywords / successful_fetches * 100, 2)


def build_run_report(
    *,
    generated_at: str,
    total_local_titles_checked: int,
    selected_titles: list[LocalTitle],
    items: list[dict[str, Any]],
    output_path: Path,
    report_path: Path,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    warnings = warnings or []
    successful_items = [
        item for item in items if item.get("fetch_status") == "success"
    ]
    failed_items = [item for item in items if item.get("fetch_status") == "failed"]
    items_with_keywords = [
        item for item in successful_items if int(item.get("keyword_count") or 0) > 0
    ]

    movie_selected = [title for title in selected_titles if title.content_type == "movie"]
    series_selected = [title for title in selected_titles if title.content_type == "series"]
    movie_successful = [
        item for item in successful_items if item.get("content_type") == "movie"
    ]
    series_successful = [
        item for item in successful_items if item.get("content_type") == "series"
    ]
    movie_with_keywords = [
        item for item in movie_successful if int(item.get("keyword_count") or 0) > 0
    ]
    series_with_keywords = [
        item for item in series_successful if int(item.get("keyword_count") or 0) > 0
    ]

    unique_keyword_names = {
        keyword_name(keyword).casefold()
        for item in successful_items
        for keyword in item.get("keywords", [])
        if keyword_name(keyword)
    }
    useful_keywords, noisy_keywords = classify_keywords(successful_items)

    errors_by_status_code: Counter[str] = Counter()
    errors: list[dict[str, Any]] = []
    for item in failed_items:
        status_code = item.get("error_status_code")
        status_key = str(status_code) if status_code is not None else "unknown"
        errors_by_status_code[status_key] += 1
        errors.append(
            {
                "content_id": item.get("content_id"),
                "title": item.get("title"),
                "content_type": item.get("content_type"),
                "tmdb_id": item.get("tmdb_id"),
                "error_status_code": status_code,
                "error_message": item.get("error_message"),
                "attempt_count": item.get("attempt_count"),
                "retry_performed": item.get("retry_performed"),
            }
        )

    return {
        "generated_at": generated_at,
        "db_write_performed": False,
        "total_local_titles_checked": total_local_titles_checked,
        "total_titles_selected": len(selected_titles),
        "titles_with_tmdb_id": len([title for title in selected_titles if title.tmdb_id]),
        "titles_without_tmdb_id": len([title for title in selected_titles if not title.tmdb_id]),
        "successful_fetches": len(successful_items),
        "failed_fetches": len(failed_items),
        "titles_with_keywords": len(items_with_keywords),
        "titles_with_zero_keywords": len(
            [
                item
                for item in successful_items
                if int(item.get("keyword_count") or 0) == 0
            ]
        ),
        "retry_attempts_performed": sum(
            int(item.get("retry_attempts_performed") or 0) for item in items
        ),
        "items_succeeded_after_retry": len(
            [item for item in successful_items if item.get("retry_performed") is True]
        ),
        "total_keywords_fetched": sum(
            int(item.get("keyword_count") or 0) for item in successful_items
        ),
        "unique_keywords": len(unique_keyword_names),
        "movie_titles_checked": len(movie_selected),
        "series_titles_checked": len(series_selected),
        "movie_successful_fetches": len(movie_successful),
        "series_successful_fetches": len(series_successful),
        "movie_keyword_coverage_percent": coverage_percent(
            len(movie_with_keywords),
            len(movie_successful),
        ),
        "series_keyword_coverage_percent": coverage_percent(
            len(series_with_keywords),
            len(series_successful),
        ),
        "overall_keyword_coverage_percent": coverage_percent(
            len(items_with_keywords),
            len(successful_items),
        ),
        "top_repeated_keywords": top_repeated_keywords(successful_items),
        "sample_keyword_rows": sample_keyword_rows(successful_items),
        "possible_useful_keywords": useful_keywords,
        "likely_noisy_keywords": noisy_keywords,
        "errors_by_status_code": dict(sorted(errors_by_status_code.items())),
        "errors": errors,
        "warnings": warnings,
        "output_path": relative_path(output_path),
        "report_path": relative_path(report_path),
    }


def build_preview(
    *,
    generated_at: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "source": "tmdb_keywords",
        "db_write_performed": False,
        "items": items,
        "errors": [
            {
                "content_id": item.get("content_id"),
                "title": item.get("title"),
                "content_type": item.get("content_type"),
                "tmdb_id": item.get("tmdb_id"),
                "error_status_code": item.get("error_status_code"),
                "error_message": item.get("error_message"),
                "attempt_count": item.get("attempt_count"),
                "retry_performed": item.get("retry_performed"),
            }
            for item in items
            if item.get("fetch_status") == "failed"
        ],
    }


def run(args: argparse.Namespace) -> int:
    database_url = os.getenv(DATABASE_URL_ENV_VAR)
    if not database_url:
        print(
            f"Missing {DATABASE_URL_ENV_VAR}. Export it before building the keywords preview.",
            file=sys.stderr,
        )
        return 1

    token = os.getenv(TOKEN_ENV_VAR)
    if not token:
        print(
            f"Missing {TOKEN_ENV_VAR}. Export a TMDb read access token before running this script.",
            file=sys.stderr,
        )
        return 1

    output_path = resolve_path(args.output)
    report_path = resolve_path(args.report_output)
    generated_at = datetime.now(timezone.utc).isoformat()
    warnings: list[str] = []

    try:
        local_titles = read_local_catalog(database_url, args.content_type)
    except TmdbKeywordsError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    selected_titles = local_titles
    if args.target_file:
        try:
            selectors = load_target_selectors(resolve_path(args.target_file))
            warnings.extend(selectors.warnings)
            selected_titles = apply_target_selectors(local_titles, selectors)
        except TmdbKeywordsError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    if args.limit:
        selected_titles = selected_titles[: args.limit]

    fetchable_titles = [title for title in selected_titles if title.tmdb_id]
    items = [
        fetch_keywords_for_title(
            title,
            token,
            generated_at,
            max_retries=args.max_retries,
        )
        for title in fetchable_titles
    ]

    preview = build_preview(generated_at=generated_at, items=items)
    report = build_run_report(
        generated_at=generated_at,
        total_local_titles_checked=len(local_titles),
        selected_titles=selected_titles,
        items=items,
        output_path=output_path,
        report_path=report_path,
        warnings=warnings,
    )

    save_json(output_path, preview)
    save_json(report_path, report)

    retry_targets_path = None
    retry_targets = None
    if args.write_retry_targets:
        retry_targets_path = resolve_path(args.write_retry_targets)
        retry_targets = build_retry_targets(items, generated_at)
        save_json(retry_targets_path, retry_targets)

    print("TMDb keywords preview complete.")
    print("DB writes: none")
    print(f"Selected titles: {report['total_titles_selected']}")
    print(f"Successful fetches: {report['successful_fetches']}")
    print(f"Failed fetches: {report['failed_fetches']}")
    print(f"Retry attempts performed: {report['retry_attempts_performed']}")
    print(f"Items succeeded after retry: {report['items_succeeded_after_retry']}")
    print(
        "Titles with keywords: "
        f"{report['titles_with_keywords']}"
    )
    print(f"Unique keywords: {report['unique_keywords']}")
    print(f"Preview: {relative_path(output_path)}")
    print(f"Report: {relative_path(report_path)}")
    if retry_targets_path and retry_targets is not None:
        if retry_targets["targets"]:
            print(f"Retry targets: {relative_path(retry_targets_path)}")
        else:
            print("Retry targets: none needed")
    print("No database changes were made.")

    return 0


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
