#!/usr/bin/env python3
"""
Read-only ingestion health check for InsightStream metadata ingestion.

This script:
- reads the ingestion target config
- connects to PostgreSQL using DATABASE_URL
- checks config validity, duplicate rows, target coverage, metadata completeness,
  and person-detail summary metrics
- writes analytics/processed/tmdb/run_reports/ingestion_health_report.json
- does not modify PostgreSQL or project source files
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency guidance for script-only runs.
    load_dotenv = None


DATABASE_URL_ENV = "DATABASE_URL"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGETS_PATH = REPO_ROOT / "analytics" / "config" / "content_ingestion_targets.json"
DEFAULT_REPORT_PATH = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "tmdb"
    / "run_reports"
    / "ingestion_health_report.json"
)
SUPPORTED_CONTENT_TYPES = {"movie", "series"}
SUPPORTED_SOURCE_NAMES = {"tmdb"}
REQUIRED_TARGET_FIELDS = {
    "title",
    "content_type",
    "source_name",
    "source_id",
    "priority",
    "ingestion_status",
}


class HealthCheckError(RuntimeError):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run read-only ingestion health checks against target config and PostgreSQL."
    )
    parser.add_argument(
        "--targets",
        default=str(DEFAULT_TARGETS_PATH.relative_to(REPO_ROOT)),
        help=(
            "Target config JSON path. Defaults to "
            f"{DEFAULT_TARGETS_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--priority",
        help="Limit target-vs-DB and completeness checks to one priority batch.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_REPORT_PATH.relative_to(REPO_ROOT)),
        help=(
            "JSON report path. Defaults to "
            f"{DEFAULT_REPORT_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat important content metadata gaps as failures.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit non-zero when warnings exist.",
    )
    return parser.parse_args(argv)


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def resolve_path(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def normalize_title(value: Any) -> str:
    text_value = clean_text(value)
    if not text_value:
        return ""
    return re.sub(r"\s+", " ", text_value.lower())


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(report), indent=2, ensure_ascii=False) + "\n")


def load_database_url() -> str | None:
    if load_dotenv is not None:
        load_dotenv(REPO_ROOT / ".env")
        load_dotenv(REPO_ROOT / "backend" / ".env")
    return os.getenv(DATABASE_URL_ENV)


def load_targets(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HealthCheckError(f"Missing target config: {relative_path(path)}") from exc
    except json.JSONDecodeError as exc:
        raise HealthCheckError(f"Malformed JSON in {relative_path(path)}: {exc}") from exc

    if not isinstance(data, dict):
        raise HealthCheckError(f"Target config must contain a JSON object: {relative_path(path)}")

    targets = data.get("targets")
    if not isinstance(targets, list):
        raise HealthCheckError(
            f"Target config must contain a top-level 'targets' array: {relative_path(path)}"
        )

    return targets, data


def validate_target_config(
    targets: list[dict[str, Any]],
    priority: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], list[str]]:
    warnings: list[str] = []
    failures: list[str] = []
    priority_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    source_seen: dict[tuple[str, str], str] = {}
    title_seen: dict[tuple[str, str], str] = {}
    duplicate_sources: list[dict[str, str]] = []
    duplicate_titles: list[dict[str, str]] = []
    valid_targets: list[dict[str, Any]] = []
    invalid_count = 0

    for index, target in enumerate(targets, start=1):
        label = f"target #{index}"
        if not isinstance(target, dict):
            failures.append(f"{label}: expected object")
            invalid_count += 1
            continue

        title = clean_text(target.get("title"))
        content_type = (clean_text(target.get("content_type")) or "").lower()
        source_name = (clean_text(target.get("source_name")) or "").lower()
        source_id = clean_text(target.get("source_id"))
        target_priority = clean_text(target.get("priority"))
        ingestion_status = (clean_text(target.get("ingestion_status")) or "").lower()
        label = title or label

        missing_fields = sorted(
            field for field in REQUIRED_TARGET_FIELDS if is_blank(target.get(field))
        )
        if missing_fields:
            failures.append(f"{label}: missing required fields: {', '.join(missing_fields)}")

        if content_type and content_type not in SUPPORTED_CONTENT_TYPES:
            failures.append(f"{label}: content_type must be movie or series")
        if source_name and source_name not in SUPPORTED_SOURCE_NAMES:
            failures.append(f"{label}: source_name must be tmdb")

        if target_priority:
            priority_counts[target_priority] += 1
        if ingestion_status:
            status_counts[ingestion_status] += 1

        if source_name and source_id:
            source_key = (source_name, source_id)
            if source_key in source_seen:
                duplicate_sources.append(
                    {
                        "source_name": source_name,
                        "source_id": source_id,
                        "first_title": source_seen[source_key],
                        "duplicate_title": title or "",
                    }
                )
            else:
                source_seen[source_key] = title or label

        if title and content_type:
            title_key = (normalize_title(title), content_type)
            if title_key in title_seen:
                duplicate_titles.append(
                    {
                        "title": title,
                        "content_type": content_type,
                        "first_title": title_seen[title_key],
                    }
                )
            else:
                title_seen[title_key] = title

        target_errors = [
            not title,
            content_type not in SUPPORTED_CONTENT_TYPES,
            source_name not in SUPPORTED_SOURCE_NAMES,
            not source_id,
            not target_priority,
            not ingestion_status,
        ]
        if any(target_errors):
            invalid_count += 1
            continue

        valid_targets.append(target)

    if duplicate_sources:
        failures.append(f"Duplicate source_name/source_id targets: {len(duplicate_sources)}")
    if duplicate_titles:
        failures.append(f"Duplicate lowercase title/content_type targets: {len(duplicate_titles)}")

    selected_targets = [
        target
        for target in valid_targets
        if priority is None or clean_text(target.get("priority")) == priority
    ]

    if priority and not selected_targets:
        warnings.append(f"No valid targets found for priority {priority!r}.")

    summary = {
        "total_targets": len(targets),
        "valid_targets": len(valid_targets),
        "invalid_targets": invalid_count,
        "selected_targets": len(selected_targets),
        "priority_counts": dict(sorted(priority_counts.items())),
        "ingestion_status_counts": dict(sorted(status_counts.items())),
        "duplicate_source_targets": duplicate_sources,
        "duplicate_title_targets": duplicate_titles,
    }
    return summary, selected_targets, warnings, failures


def get_table_columns(connection: Any, table_name: str) -> set[str]:
    rows = connection.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name;
            """
        ),
        {"table_name": table_name},
    ).mappings().all()
    return {str(row["column_name"]) for row in rows}


def duplicate_query_definitions(table_columns: dict[str, set[str]]) -> dict[str, str]:
    content_people_columns = table_columns.get("content_people", set())
    source_credit_expr = (
        "COALESCE(source_credit_id, '')"
        if "source_credit_id" in content_people_columns
        else "''"
    )

    return {
        "content": """
            SELECT title, content_type, COUNT(*) AS duplicate_count
            FROM content
            GROUP BY title, content_type
            HAVING COUNT(*) > 1;
        """,
        "external_ids": """
            SELECT source_name, external_id, COUNT(*) AS duplicate_count
            FROM external_ids
            GROUP BY source_name, external_id
            HAVING COUNT(*) > 1;
        """,
        "person_external_ids": """
            SELECT source_name, external_id, COUNT(*) AS duplicate_count
            FROM person_external_ids
            GROUP BY source_name, external_id
            HAVING COUNT(*) > 1;
        """,
        "genres": """
            SELECT LOWER(name) AS normalized_name, COUNT(*) AS duplicate_count
            FROM genres
            GROUP BY LOWER(name)
            HAVING COUNT(*) > 1;
        """,
        "platforms": """
            SELECT LOWER(name) AS normalized_name, COUNT(*) AS duplicate_count
            FROM platforms
            GROUP BY LOWER(name)
            HAVING COUNT(*) > 1;
        """,
        "content_genres": """
            SELECT content_id, genre_id, COUNT(*) AS duplicate_count
            FROM content_genres
            GROUP BY content_id, genre_id
            HAVING COUNT(*) > 1;
        """,
        "content_people": f"""
            SELECT
                content_id,
                person_id,
                role_type,
                COALESCE(character_name, '') AS character_name,
                COALESCE(job, '') AS job,
                {source_credit_expr} AS source_credit_id,
                COUNT(*) AS duplicate_count
            FROM content_people
            GROUP BY
                content_id,
                person_id,
                role_type,
                COALESCE(character_name, ''),
                COALESCE(job, ''),
                {source_credit_expr}
            HAVING COUNT(*) > 1;
        """,
        "content_availability": """
            SELECT content_id, platform_id, availability_type, region_code, source_name, COUNT(*) AS duplicate_count
            FROM content_availability
            GROUP BY content_id, platform_id, availability_type, region_code, source_name
            HAVING COUNT(*) > 1;
        """,
        "content_certifications": """
            SELECT content_id, country_code, rating_system, source_name, COUNT(*) AS duplicate_count
            FROM content_certifications
            GROUP BY content_id, country_code, rating_system, source_name
            HAVING COUNT(*) > 1;
        """,
        "content_ratings": """
            SELECT content_id, rating_source_id, COUNT(*) AS duplicate_count
            FROM content_ratings
            GROUP BY content_id, rating_source_id
            HAVING COUNT(*) > 1;
        """,
    }


def fetch_rows(connection: Any, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows = connection.execute(text(query), params or {}).mappings().all()
    return [dict(row) for row in rows]


def run_duplicate_checks(
    connection: Any,
    table_columns: dict[str, set[str]],
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    results: dict[str, Any] = {}

    for name, query in duplicate_query_definitions(table_columns).items():
        try:
            rows = fetch_rows(connection, query)
        except SQLAlchemyError as exc:
            failures.append(f"Duplicate check failed for {name}: {exc}")
            results[name] = {"status": "failed", "row_count": None, "rows": []}
            continue

        results[name] = {
            "status": "passed" if not rows else "failed",
            "row_count": len(rows),
            "rows": rows,
        }
        if rows:
            failures.append(f"Duplicate check failed for {name}: {len(rows)} duplicate group(s).")

    return results, failures


def read_database_snapshot(
    connection: Any,
    table_columns: dict[str, set[str]],
) -> dict[str, Any]:
    def series_column_expr(column_name: str) -> str:
        columns = table_columns.get("content_series_metadata", set())
        if column_name in columns:
            return column_name
        return f"NULL AS {column_name}"

    content_rows = fetch_rows(
        connection,
        """
        SELECT
            id,
            title,
            content_type,
            overview,
            poster_url,
            backdrop_url,
            release_date,
            latest_activity_date,
            age_rating
        FROM content
        ORDER BY id ASC;
        """,
    )
    external_rows = fetch_rows(
        connection,
        """
        SELECT content_id, source_name, external_id
        FROM external_ids
        ORDER BY content_id ASC, source_name ASC;
        """,
    )
    genre_counts = {
        row["content_id"]: row["total"]
        for row in fetch_rows(
            connection,
            """
            SELECT content_id, COUNT(*) AS total
            FROM content_genres
            GROUP BY content_id;
            """,
        )
    }
    content_people_counts = {
        row["content_id"]: row["total"]
        for row in fetch_rows(
            connection,
            """
            SELECT content_id, COUNT(*) AS total
            FROM content_people
            GROUP BY content_id;
            """,
        )
    }
    availability_counts = {
        row["content_id"]: row["total"]
        for row in fetch_rows(
            connection,
            """
            SELECT content_id, COUNT(*) AS total
            FROM content_availability
            GROUP BY content_id;
            """,
        )
    }
    certification_counts = {
        row["content_id"]: row["total"]
        for row in fetch_rows(
            connection,
            """
            SELECT content_id, COUNT(*) AS total
            FROM content_certifications
            GROUP BY content_id;
            """,
        )
    }
    rating_counts = {
        row["content_id"]: row["total"]
        for row in fetch_rows(
            connection,
            """
            SELECT content_id, COUNT(*) AS total
            FROM content_ratings
            GROUP BY content_id;
            """,
        )
    }
    series_metadata_rows: list[dict[str, Any]] = []
    if table_columns.get("content_series_metadata"):
        series_metadata_rows = fetch_rows(
            connection,
            f"""
            SELECT
                content_id,
                {series_column_expr("number_of_seasons")},
                {series_column_expr("number_of_episodes")},
                {series_column_expr("series_status")},
                {series_column_expr("series_status_normalized")},
                {series_column_expr("in_production")},
                {series_column_expr("first_air_date")},
                {series_column_expr("last_air_date")},
                {series_column_expr("last_episode_air_date")},
                {series_column_expr("next_episode_air_date")},
                {series_column_expr("series_type")},
                {series_column_expr("released_seasons_count")},
                {series_column_expr("announced_seasons_count")},
                {series_column_expr("next_season_number")},
                {series_column_expr("next_season_air_date")},
                {series_column_expr("next_season_year")},
                {series_column_expr("has_announced_season")},
                {series_column_expr("season_summary_note")}
            FROM content_series_metadata;
            """,
        )

    return {
        "content_rows": content_rows,
        "external_rows": external_rows,
        "genre_counts": genre_counts,
        "content_people_counts": content_people_counts,
        "availability_counts": availability_counts,
        "certification_counts": certification_counts,
        "rating_counts": rating_counts,
        "series_metadata_by_content": {
            row["content_id"]: row for row in series_metadata_rows
        },
    }


def database_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    content_rows = snapshot["content_rows"]
    external_rows = snapshot["external_rows"]
    source_counts = Counter(row["source_name"] for row in external_rows)
    content_type_counts = Counter(row["content_type"] for row in content_rows)
    return {
        "content_count": len(content_rows),
        "content_type_counts": dict(sorted(content_type_counts.items())),
        "external_id_counts": dict(sorted(source_counts.items())),
    }


def target_key(target: dict[str, Any]) -> tuple[str, str]:
    return (
        (clean_text(target.get("source_name")) or "").lower(),
        clean_text(target.get("source_id")) or "",
    )


def check_target_db_coverage(
    selected_targets: list[dict[str, Any]],
    snapshot: dict[str, Any],
    priority: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], list[str]]:
    warnings: list[str] = []
    failures: list[str] = []
    content_by_id = {row["id"]: row for row in snapshot["content_rows"]}
    external_map: dict[tuple[str, str], dict[str, Any]] = {}
    tmdb_external_ids: set[str] = set()

    for row in snapshot["external_rows"]:
        key = ((row["source_name"] or "").lower(), str(row["external_id"]))
        external_map[key] = row
        if key[0] == "tmdb":
            tmdb_external_ids.add(key[1])

    matched: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    selected_tmdb_ids: set[str] = set()

    for target in selected_targets:
        key = target_key(target)
        if key[0] == "tmdb":
            selected_tmdb_ids.add(key[1])

        external_row = external_map.get(key)
        if not external_row:
            missing.append(
                {
                    "title": target.get("title"),
                    "content_type": target.get("content_type"),
                    "source_name": key[0],
                    "source_id": key[1],
                    "priority": target.get("priority"),
                }
            )
            continue

        content_row = content_by_id.get(external_row["content_id"])
        if not content_row:
            missing.append(
                {
                    "title": target.get("title"),
                    "source_name": key[0],
                    "source_id": key[1],
                    "reason": "external ID exists but linked content row is missing",
                }
            )
            continue

        content_type = (clean_text(target.get("content_type")) or "").lower()
        if content_row["content_type"] != content_type:
            mismatches.append(
                {
                    "title": target.get("title"),
                    "source_id": key[1],
                    "target_content_type": content_type,
                    "db_content_type": content_row["content_type"],
                }
            )

        if normalize_title(content_row["title"]) != normalize_title(target.get("title")):
            warnings.append(
                f"Target title differs from DB title for TMDb {key[1]}: "
                f"{target.get('title')!r} vs {content_row['title']!r}."
            )

        matched.append(
            {
                "target_title": target.get("title"),
                "content_id": content_row["id"],
                "db_title": content_row["title"],
                "content_type": content_row["content_type"],
                "source_name": key[0],
                "source_id": key[1],
                "priority": target.get("priority"),
            }
        )

    if missing:
        failures.append(f"Missing DB coverage for {len(missing)} selected target(s).")
    if mismatches:
        failures.append(f"Content type mismatch for {len(mismatches)} selected target(s).")

    extra_db_tmdb_ids: list[str] = []
    if priority is None:
        extra_db_tmdb_ids = sorted(tmdb_external_ids - selected_tmdb_ids)
        if extra_db_tmdb_ids:
            failures.append(
                f"DB has {len(extra_db_tmdb_ids)} TMDb external ID(s) not present in target config."
            )

    summary = {
        "selected_targets": len(selected_targets),
        "matched_targets": len(matched),
        "missing_targets": len(missing),
        "content_type_mismatches": mismatches,
        "extra_db_tmdb_external_ids": extra_db_tmdb_ids,
        "missing_target_details": missing,
    }
    return summary, matched, warnings, failures


def check_metadata_completeness(
    matched_targets: list[dict[str, Any]],
    snapshot: dict[str, Any],
    strict: bool,
) -> tuple[dict[str, Any], list[str], list[str]]:
    warnings: list[str] = []
    failures: list[str] = []
    content_by_id = {row["id"]: row for row in snapshot["content_rows"]}
    external_by_content: dict[int, set[str]] = defaultdict(set)
    for row in snapshot["external_rows"]:
        external_by_content[row["content_id"]].add((row["source_name"] or "").lower())

    items: list[dict[str, Any]] = []
    strict_failure_codes = {
        "missing_poster_url",
        "missing_backdrop_url",
        "missing_overview",
        "missing_release_date",
        "missing_latest_activity_date",
        "missing_genres",
        "missing_imdb_external_id",
        "missing_content_people",
        "missing_series_metadata",
        "missing_series_number_of_seasons",
        "missing_series_status_normalized",
        "missing_released_seasons_count",
        "missing_has_announced_season",
        "season_count_exceeds_released_without_next_season",
    }

    for target in matched_targets:
        content_id = target["content_id"]
        content = content_by_id.get(content_id)
        if not content:
            continue

        issues: list[dict[str, Any]] = []

        checks = [
            ("missing_poster_url", is_blank(content.get("poster_url"))),
            ("missing_backdrop_url", is_blank(content.get("backdrop_url"))),
            ("missing_overview", is_blank(content.get("overview"))),
            ("missing_release_date", content.get("release_date") is None),
            ("missing_latest_activity_date", content.get("latest_activity_date") is None),
            ("missing_genres", snapshot["genre_counts"].get(content_id, 0) == 0),
            ("missing_imdb_external_id", "imdb" not in external_by_content.get(content_id, set())),
            ("missing_content_people", snapshot["content_people_counts"].get(content_id, 0) == 0),
            ("missing_availability", snapshot["availability_counts"].get(content_id, 0) == 0),
            (
                "missing_certification_and_age_rating",
                snapshot["certification_counts"].get(content_id, 0) == 0
                and is_blank(content.get("age_rating")),
            ),
            ("missing_ratings", snapshot["rating_counts"].get(content_id, 0) == 0),
        ]
        series_metadata = snapshot["series_metadata_by_content"].get(content_id)
        if content.get("content_type") == "series":
            checks.extend(
                [
                    ("missing_series_metadata", series_metadata is None),
                    (
                        "missing_series_number_of_seasons",
                        series_metadata is not None
                        and series_metadata.get("number_of_seasons") is None,
                    ),
                    (
                        "missing_series_status_normalized",
                        series_metadata is not None
                        and is_blank(series_metadata.get("series_status_normalized")),
                    ),
                    (
                        "missing_released_seasons_count",
                        series_metadata is not None
                        and series_metadata.get("released_seasons_count") is None,
                    ),
                    (
                        "missing_has_announced_season",
                        series_metadata is not None
                        and series_metadata.get("has_announced_season") is None,
                    ),
                    (
                        "season_count_exceeds_released_without_next_season",
                        series_metadata is not None
                        and series_metadata.get("number_of_seasons") is not None
                        and series_metadata.get("released_seasons_count") is not None
                        and series_metadata["number_of_seasons"]
                        > series_metadata["released_seasons_count"]
                        and series_metadata.get("next_season_number") is None,
                    ),
                ]
            )

        for code, failed in checks:
            if not failed:
                continue
            strict_failure = code in strict_failure_codes
            issue = {
                "code": code,
                "severity": "failure" if strict and strict_failure else "warning",
            }
            issues.append(issue)
            message = f"{content['title']}: {code.replace('_', ' ')}."
            if strict and strict_failure:
                failures.append(message)
            else:
                warnings.append(message)

        if issues:
            items.append(
                {
                    "content_id": content_id,
                    "title": content["title"],
                    "content_type": content["content_type"],
                    "issues": issues,
                }
            )

    return {
        "checked_content_count": len(matched_targets),
        "content_with_warnings_or_failures": len(items),
        "items": items,
    }, warnings, failures


def person_detail_summary(connection: Any) -> dict[str, Any]:
    summary_row = fetch_rows(
        connection,
        """
        SELECT
            COUNT(*) AS total_people,
            COUNT(*) FILTER (WHERE biography IS NOT NULL AND biography <> '') AS people_with_biography,
            COUNT(*) FILTER (WHERE biography IS NULL OR biography = '') AS people_without_biography,
            COUNT(*) FILTER (WHERE profile_url IS NOT NULL AND profile_url <> '') AS people_with_profile_url,
            COUNT(*) FILTER (WHERE profile_url IS NULL OR profile_url = '') AS people_without_profile_url,
            COUNT(*) FILTER (
                WHERE known_for_department IS NOT NULL AND known_for_department <> ''
            ) AS people_with_known_for_department,
            COUNT(*) FILTER (
                WHERE known_for_department IS NULL OR known_for_department = ''
            ) AS people_without_known_for_department
        FROM people;
        """,
    )[0]
    external_count_row = fetch_rows(
        connection,
        "SELECT COUNT(*) AS total FROM person_external_ids;",
    )[0]
    people_without_external_ids_row = fetch_rows(
        connection,
        """
        SELECT COUNT(*) AS total
        FROM people p
        LEFT JOIN person_external_ids pei ON pei.person_id = p.id
        WHERE pei.id IS NULL;
        """,
    )[0]

    return {
        **summary_row,
        "person_external_ids_count": external_count_row["total"],
        "people_without_external_ids": people_without_external_ids_row["total"],
    }


def series_lifecycle_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    content_rows = snapshot["content_rows"]
    series_rows = [row for row in content_rows if row.get("content_type") == "series"]
    metadata_by_content = snapshot["series_metadata_by_content"]
    series_metadata_rows = [
        metadata_by_content[row["id"]]
        for row in series_rows
        if row["id"] in metadata_by_content
    ]
    status_counts = Counter(
        (metadata_by_content.get(row["id"]) or {}).get("series_status_normalized")
        or "missing"
        for row in series_rows
    )
    season_summary_count = sum(
        1
        for row in series_metadata_rows
        if row.get("released_seasons_count") is not None
        and row.get("has_announced_season") is not None
    )

    return {
        "total_series": len(series_rows),
        "series_with_lifecycle_metadata": sum(
            1 for row in series_rows if row["id"] in metadata_by_content
        ),
        "series_missing_lifecycle_metadata": sum(
            1 for row in series_rows if row["id"] not in metadata_by_content
        ),
        "ongoing_series_count": status_counts.get("ongoing", 0),
        "ended_series_count": status_counts.get("ended", 0),
        "cancelled_series_count": status_counts.get("cancelled", 0),
        "upcoming_series_count": status_counts.get("upcoming", 0),
        "unknown_status_count": status_counts.get("unknown", 0),
        "missing_status_count": status_counts.get("missing", 0),
        "series_with_season_summary": season_summary_count,
        "series_with_announced_or_upcoming_seasons": sum(
            1 for row in series_metadata_rows if row.get("has_announced_season") is True
        ),
        "series_with_unknown_season_summary": len(series_rows) - season_summary_count,
    }


def ratings_summary(connection: Any) -> tuple[dict[str, Any], list[str], list[str]]:
    warnings: list[str] = []
    failures: list[str] = []
    source_row = fetch_rows(
        connection,
        """
        SELECT
            COUNT(*) AS rating_sources_count,
            COUNT(*) FILTER (WHERE source_name = 'tmdb') AS tmdb_source_count
        FROM rating_sources;
        """,
    )[0]
    ratings_row = fetch_rows(
        connection,
        """
        SELECT
            COUNT(*) AS total_content_ratings,
            COUNT(*) FILTER (
                WHERE normalized_score IS NOT NULL
                  AND (normalized_score < 0 OR normalized_score > 100)
            ) AS invalid_normalized_scores,
            COUNT(*) FILTER (
                WHERE raw_score_scale IS NOT NULL
                  AND raw_score_scale <= 0
            ) AS invalid_raw_score_scales,
            COUNT(*) FILTER (
                WHERE vote_count IS NOT NULL
                  AND vote_count < 0
            ) AS negative_vote_counts
        FROM content_ratings;
        """,
    )[0]
    coverage_row = fetch_rows(
        connection,
        """
        SELECT
            COUNT(DISTINCT c.id) AS provider_backed_content,
            COUNT(DISTINCT cr.content_id) AS provider_backed_content_with_ratings
        FROM content c
        JOIN external_ids ei
          ON ei.content_id = c.id
         AND ei.source_name = 'tmdb'
        LEFT JOIN content_ratings cr ON cr.content_id = c.id;
        """,
    )[0]

    provider_backed_content = coverage_row["provider_backed_content"] or 0
    provider_backed_with_ratings = (
        coverage_row["provider_backed_content_with_ratings"] or 0
    )
    coverage_percentage = (
        round(provider_backed_with_ratings / provider_backed_content * 100, 2)
        if provider_backed_content
        else 0
    )

    if source_row["tmdb_source_count"] == 0:
        warnings.append("Ratings: TMDb rating source is missing.")
    if ratings_row["invalid_normalized_scores"]:
        failures.append("Ratings: invalid normalized_score values found.")
    if ratings_row["invalid_raw_score_scales"]:
        failures.append("Ratings: invalid raw_score_scale values found.")
    if ratings_row["negative_vote_counts"]:
        failures.append("Ratings: negative vote_count values found.")

    return {
        **source_row,
        **ratings_row,
        "provider_backed_content": provider_backed_content,
        "provider_backed_content_with_ratings": provider_backed_with_ratings,
        "rating_coverage_percentage": coverage_percentage,
        "provider_backed_content_missing_ratings": (
            provider_backed_content - provider_backed_with_ratings
        ),
    }, warnings, failures


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    generated_at = datetime.now(timezone.utc).isoformat()
    targets_path = resolve_path(args.targets)
    output_path = resolve_path(args.output)
    filters = {
        "priority": args.priority,
        "strict": args.strict,
        "fail_on_warning": args.fail_on_warning,
    }
    warnings: list[str] = []
    failures: list[str] = []
    config_summary: dict[str, Any] = {}
    selected_targets: list[dict[str, Any]] = []
    database_summary_data: dict[str, Any] = {}
    duplicate_checks: dict[str, Any] = {}
    target_db_coverage: dict[str, Any] = {}
    metadata_completeness: dict[str, Any] = {}
    person_summary: dict[str, Any] = {}
    series_summary: dict[str, Any] = {}
    rating_summary: dict[str, Any] = {}

    try:
        raw_targets, _ = load_targets(targets_path)
        config_summary, selected_targets, config_warnings, config_failures = validate_target_config(
            raw_targets,
            args.priority,
        )
        warnings.extend(config_warnings)
        failures.extend(config_failures)
    except HealthCheckError as exc:
        failures.append(str(exc))
        raw_targets = []

    database_url = load_database_url()
    if not database_url:
        failures.append(f"Missing {DATABASE_URL_ENV}. Export it before running this health check.")
    else:
        try:
            engine = create_engine(database_url)
            with engine.connect() as connection:
                table_columns = {
                    table_name: get_table_columns(connection, table_name)
                    for table_name in [
                        "content",
                        "external_ids",
                        "person_external_ids",
                        "content_people",
                        "content_availability",
                        "content_certifications",
                        "content_series_metadata",
                        "rating_sources",
                        "content_ratings",
                    ]
                }
                missing_required_tables = [
                    table
                    for table, columns in table_columns.items()
                    if not columns
                ]
                if missing_required_tables:
                    failures.append(
                        "Missing required table(s): " + ", ".join(sorted(missing_required_tables))
                    )

                duplicate_checks, duplicate_failures = run_duplicate_checks(
                    connection,
                    table_columns,
                )
                failures.extend(duplicate_failures)

                snapshot = read_database_snapshot(connection, table_columns)
                database_summary_data = database_summary(snapshot)

                target_db_coverage, matched_targets, coverage_warnings, coverage_failures = (
                    check_target_db_coverage(selected_targets, snapshot, args.priority)
                )
                warnings.extend(coverage_warnings)
                failures.extend(coverage_failures)

                metadata_completeness, metadata_warnings, metadata_failures = (
                    check_metadata_completeness(matched_targets, snapshot, args.strict)
                )
                warnings.extend(metadata_warnings)
                failures.extend(metadata_failures)

                person_summary = person_detail_summary(connection)
                series_summary = series_lifecycle_summary(snapshot)
                rating_summary, rating_warnings, rating_failures = ratings_summary(
                    connection
                )
                if args.strict and rating_summary.get("tmdb_source_count", 0) == 0:
                    rating_failures.append(
                        "Ratings: strict mode requires the TMDb rating source."
                    )
                    rating_warnings = [
                        warning
                        for warning in rating_warnings
                        if "TMDb rating source is missing" not in warning
                    ]
                warnings.extend(rating_warnings)
                failures.extend(rating_failures)
        except SQLAlchemyError as exc:
            failures.append(f"Database health check failed: {exc}")

    status = "failed" if failures else "warning" if warnings else "healthy"
    report = {
        "generated_at": generated_at,
        "script_name": "check_ingestion_health.py",
        "target_config_path": relative_path(targets_path),
        "filters_used": filters,
        "config_summary": config_summary,
        "database_summary": database_summary_data,
        "duplicate_checks": duplicate_checks,
        "target_db_coverage": target_db_coverage,
        "metadata_completeness": metadata_completeness,
        "person_detail_summary": person_summary,
        "series_lifecycle_summary": series_summary,
        "ratings_summary": rating_summary,
        "warnings": warnings,
        "failures": failures,
        "status": status,
    }
    write_report(output_path, report)

    exit_code = 1 if failures or (args.fail_on_warning and warnings) else 0
    return report, exit_code


def print_summary(report: dict[str, Any], output_path: Path) -> None:
    config = report.get("config_summary") or {}
    database = report.get("database_summary") or {}
    coverage = report.get("target_db_coverage") or {}
    metadata = report.get("metadata_completeness") or {}
    person = report.get("person_detail_summary") or {}
    series = report.get("series_lifecycle_summary") or {}
    ratings = report.get("ratings_summary") or {}
    duplicate_checks = report.get("duplicate_checks") or {}
    duplicate_failures = [
        name for name, result in duplicate_checks.items() if result.get("status") != "passed"
    ]

    print("Ingestion Health Check")
    print("======================")
    print(f"Target count: {config.get('total_targets', 0)}")
    print(f"Selected target count: {config.get('selected_targets', 0)}")
    print(f"Content count: {database.get('content_count', 0)}")
    print(f"External ID coverage count: {coverage.get('matched_targets', 0)}")
    print(
        "Duplicate check status: "
        + ("passed" if not duplicate_failures else f"failed ({len(duplicate_failures)})")
    )
    print(f"Missing DB targets: {coverage.get('missing_targets', 0)}")
    print(
        "Metadata warning/failure items: "
        f"{metadata.get('content_with_warnings_or_failures', 0)}"
    )
    print(
        "People: "
        f"{person.get('total_people', 0)} total, "
        f"{person.get('people_with_biography', 0)} with biography, "
        f"{person.get('people_without_biography', 0)} without biography"
    )
    print(
        "Series lifecycle: "
        f"{series.get('series_with_lifecycle_metadata', 0)}/"
        f"{series.get('total_series', 0)} with metadata, "
        f"{series.get('ongoing_series_count', 0)} ongoing, "
        f"{series.get('ended_series_count', 0)} ended, "
        f"{series.get('cancelled_series_count', 0)} cancelled, "
        f"{series.get('upcoming_series_count', 0)} upcoming, "
        f"{series.get('unknown_status_count', 0)} unknown"
    )
    print(
        "Season summary: "
        f"{series.get('series_with_season_summary', 0)}/"
        f"{series.get('total_series', 0)} with summary, "
        f"{series.get('series_with_announced_or_upcoming_seasons', 0)} with announced/upcoming seasons, "
        f"{series.get('series_with_unknown_season_summary', 0)} unknown"
    )
    print(
        "Ratings: "
        f"{ratings.get('total_content_ratings', 0)} rows, "
        f"TMDb source {'present' if ratings.get('tmdb_source_count', 0) else 'missing'}, "
        f"{ratings.get('rating_coverage_percentage', 0)}% provider-backed coverage"
    )
    print(f"Warnings: {len(report.get('warnings') or [])}")
    print(f"Failures: {len(report.get('failures') or [])}")
    print(f"Final health status: {report.get('status')}")
    print(f"Report path: {relative_path(output_path)}")
    print("No database changes were made.")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_path = resolve_path(args.output)
    report, exit_code = build_report(args)
    print_summary(report, output_path)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
