#!/usr/bin/env python3
"""Read-only catalog baseline and expansion-readiness audit for InsightStream."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import create_engine, text

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local convenience
    load_dotenv = None


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from content_refresh_planner import evaluate_series_refresh, evaluate_video_refresh  # noqa: E402
from source_signal_keyword_normalization import (  # noqa: E402
    keyword_normalization_metadata,
    normalize_keyword_name,
)


DEFAULT_OUTPUT_DIR = REPO_ROOT / "analytics" / "processed" / "catalog_audits"
DEFAULT_JSON_OUTPUT = DEFAULT_OUTPUT_DIR / "catalog_baseline.json"
DEFAULT_MARKDOWN_OUTPUT = DEFAULT_OUTPUT_DIR / "catalog_baseline.md"
DEFAULT_GAP_OUTPUT = DEFAULT_OUTPUT_DIR / "catalog_expansion_gap_plan.json"
DEFAULT_MAPPING_PATH = (
    REPO_ROOT / "analytics" / "config" / "source_signal_keyword_mapping.json"
)

REQUIRED_TABLES = {
    "content",
    "external_ids",
    "genres",
    "content_genres",
    "content_ratings",
    "content_people",
    "content_availability",
    "content_series_metadata",
    "content_videos",
    "content_primary_videos",
    "content_video_fetch_state",
    "provider_keywords",
    "content_keywords",
    "content_source_signals",
}

VALID_SIGNAL_DIMENSIONS = {
    "audience_expectation",
    "content_caution_proxy",
    "intensity",
    "mood",
    "pacing",
    "tone",
    "topic_theme",
}
SUBGENRE_DIMENSIONS = {"audience_expectation", "topic_theme"}
SUBGENRE_TERMS = {
    "coming-of-age",
    "comedy",
    "cyberpunk",
    "dark fantasy",
    "documentary",
    "epic",
    "folk horror",
    "horror",
    "mystery",
    "political thriller",
    "procedural",
    "psychological thriller",
    "romance",
    "romantic comedy",
    "space opera",
    "supernatural horror",
    "survival drama",
    "thriller",
}

MANY_KEYWORDS = 8
LOW_MAPPING_COVERAGE = 0.50
WEAK_SIGNAL_COUNT = 3
RARE_SIGNAL_MAX = 1
OVERUSED_SIGNAL_SHARE = 0.35
EXCESSIVE_GENRE_COUNT = 7
GENRE_DISCOVERY_MIN = 5
GENRE_SIMILARITY_MIN = 8
READY_PLAUSIBLE_MIN = 8
READY_STRONG_MIN = 4
LIMITED_PLAUSIBLE_MIN = 4
DISCOVERY_READY_COVERAGE = 0.80
DISCOVERY_GAPPED_COVERAGE = 0.50

READINESS_AREAS = (
    "ingestion_readiness",
    "metadata_readiness",
    "source_signal_readiness",
    "recommendation_readiness",
    "discovery_readiness",
    "refresh_readiness",
    "expansion_readiness",
    "performance_test_readiness",
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit catalog composition and expansion readiness without writes or provider requests."
    )
    parser.add_argument("--database-url", help="PostgreSQL URL; defaults to DATABASE_URL.")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    parser.add_argument("--output-gap-plan", type=Path, default=DEFAULT_GAP_OUTPUT)
    parser.add_argument("--content-type", choices=("movie", "series"))
    parser.add_argument("--limit", type=positive_int)
    parser.add_argument("--sample-size", type=positive_int, default=12)
    parser.add_argument("--top-unmapped-keywords", type=positive_int, default=25)
    parser.add_argument("--performance-check", action="store_true")
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--reference-date",
        type=parse_reference_date,
        default=datetime.now(timezone.utc),
        help="Deterministic date or timestamp (ISO 8601).",
    )
    return parser.parse_args(argv)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def parse_reference_date(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("reference date must be ISO 8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def safe_percent(count: int, total: int) -> float:
    return round((count / total) * 100, 2) if total else 0.0


def iso_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def distribution(values: Iterable[str], total: int) -> list[dict[str, Any]]:
    counts = Counter(values)
    return [
        {"value": value, "count": count, "percentage": safe_percent(count, total)}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def load_mapping_config(path: Path = DEFAULT_MAPPING_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to read keyword mapping config {path}: {exc}") from exc
    if not isinstance(payload.get("keyword_mappings"), dict):
        raise RuntimeError("Keyword mapping config is missing keyword_mappings")
    return payload


def mapping_sets(config: Mapping[str, Any]) -> tuple[set[str], set[str], set[str]]:
    mapped = {normalize_keyword_name(value) for value in config.get("keyword_mappings", {})}
    ignored = {normalize_keyword_name(value) for value in config.get("excluded_keywords", [])}
    ignored.update(
        normalize_keyword_name(value) for value in config.get("spoiler_unsafe_keywords", [])
    )
    valid_dimensions = {
        normalize_text(value).replace(" ", "_") for value in config.get("dimensions", [])
    }
    return mapped, ignored, valid_dimensions


def empty_record(row: Mapping[str, Any]) -> dict[str, Any]:
    record = dict(row)
    record.update(
        {
            "external_ids": {},
            "genres": [],
            "ratings": [],
            "availability": [],
            "credits": [],
            "keywords": [],
            "signals": [],
            "videos": [],
            "primary_video": None,
            "video_fetch_state": None,
            "series_metadata": None,
        }
    )
    return record


def _query_rows(connection: Any, sql: str, ids: list[int]) -> list[dict[str, Any]]:
    if not ids:
        return []
    return [dict(row) for row in connection.execute(text(sql), {"ids": ids}).mappings()]


def _attach_grouped(
    records: dict[int, dict[str, Any]], rows: Iterable[dict[str, Any]], key: str
) -> None:
    for row in rows:
        content_id = int(row.pop("content_id"))
        if content_id in records:
            records[content_id][key].append(row)


def validate_required_tables(connection: Any) -> None:
    rows = connection.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ANY(:tables)
            """
        ),
        {"tables": sorted(REQUIRED_TABLES)},
    ).scalars()
    present = set(rows)
    missing = sorted(REQUIRED_TABLES - present)
    if missing:
        raise RuntimeError(f"Required catalog tables are missing: {', '.join(missing)}")


BASE_CONTENT_SQL = """
    SELECT c.id AS content_id, c.tmdb_id, c.title, c.original_title,
           c.content_type, c.overview, c.poster_url, c.backdrop_url,
           c.release_date, c.latest_activity_date, c.year, c.runtime,
           c.language, c.original_language, c.status, c.age_rating
    FROM content c
    WHERE (:content_type IS NULL OR c.content_type = :content_type)
    ORDER BY c.id
    LIMIT :row_limit
"""


def load_catalog_records(
    database_url: str, *, content_type: str | None = None, limit: int | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load one bounded catalog snapshot using read-only, set-based queries."""
    engine = create_engine(database_url)
    query_count = 0
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION READ ONLY"))
            validate_required_tables(connection)
            query_count += 1
            base_rows = connection.execute(
                text(BASE_CONTENT_SQL),
                {"content_type": content_type, "row_limit": limit or 2_147_483_647},
            ).mappings()
            records = {int(row["content_id"]): empty_record(row) for row in base_rows}
            query_count += 1
            ids = sorted(records)
            if not ids:
                transaction.rollback()
                return [], {"query_count": query_count, "read_only": True, "orphan_primary_rows": []}

            external_rows = _query_rows(
                connection,
                "SELECT content_id, source_name, external_id FROM external_ids WHERE content_id = ANY(:ids)",
                ids,
            )
            query_count += 1
            for row in external_rows:
                records[int(row["content_id"])]["external_ids"][normalize_text(row["source_name"])] = str(row["external_id"])

            grouped_queries = {
                "genres": """
                    SELECT cg.content_id, g.id, g.name
                    FROM content_genres cg JOIN genres g ON g.id = cg.genre_id
                    WHERE cg.content_id = ANY(:ids) ORDER BY cg.content_id, LOWER(g.name), g.id
                """,
                "ratings": """
                    SELECT cr.content_id, rs.source_name, cr.normalized_score, cr.vote_count
                    FROM content_ratings cr JOIN rating_sources rs ON rs.id = cr.rating_source_id
                    WHERE cr.content_id = ANY(:ids) ORDER BY cr.content_id, rs.source_name
                """,
                "availability": """
                    SELECT ca.content_id, p.name AS platform, ca.availability_type, ca.region_code, ca.source_name
                    FROM content_availability ca JOIN platforms p ON p.id = ca.platform_id
                    WHERE ca.content_id = ANY(:ids)
                    UNION ALL
                    SELECT cp.content_id, p.name, cp.availability_type, NULL, 'legacy'
                    FROM content_platforms cp JOIN platforms p ON p.id = cp.platform_id
                    WHERE cp.content_id = ANY(:ids)
                    ORDER BY content_id, platform, availability_type
                """,
                "credits": """
                    SELECT cp.content_id, cp.person_id, cp.role_type, cp.job, cp.department
                    FROM content_people cp WHERE cp.content_id = ANY(:ids)
                    ORDER BY cp.content_id, cp.role_type, cp.display_order NULLS LAST, cp.person_id
                """,
                "keywords": """
                    SELECT ck.content_id, pk.keyword_name, pk.normalized_keyword_name,
                           ks.source_name, ck.confidence
                    FROM content_keywords ck
                    JOIN provider_keywords pk ON pk.id = ck.keyword_id
                    JOIN keyword_sources ks ON ks.id = ck.source_id
                    WHERE ck.content_id = ANY(:ids)
                    ORDER BY ck.content_id, pk.normalized_keyword_name, pk.id
                """,
                "signals": """
                    SELECT css.content_id, css.dimension, css.value, css.label,
                           css.confidence, css.source_names, css.is_active
                    FROM content_source_signals css
                    WHERE css.content_id = ANY(:ids) AND css.is_active
                    ORDER BY css.content_id, css.dimension, css.value
                """,
                "videos": """
                    SELECT cv.content_id, cv.id, cv.source, cv.site, cv.source_video_id,
                           cv.video_type, cv.name, cv.official, cv.language_code,
                           (cpv.content_video_id = cv.id) AS is_primary
                    FROM content_videos cv
                    LEFT JOIN content_primary_videos cpv
                      ON cpv.content_id = cv.content_id AND cpv.content_video_id = cv.id
                    WHERE cv.content_id = ANY(:ids)
                    ORDER BY cv.content_id, cv.id
                """,
            }
            for key, sql in grouped_queries.items():
                _attach_grouped(records, _query_rows(connection, sql, ids), key)
                query_count += 1

            primary_rows = _query_rows(
                connection,
                """
                SELECT cpv.content_id, cpv.content_video_id, cv.content_id AS video_content_id,
                       cv.site, cv.source_video_id, cv.video_type
                FROM content_primary_videos cpv
                LEFT JOIN content_videos cv ON cv.id = cpv.content_video_id
                WHERE cpv.content_id = ANY(:ids)
                """,
                ids,
            )
            query_count += 1
            orphan_primary_rows = []
            for row in primary_rows:
                content_id = int(row["content_id"])
                if row["video_content_id"] != content_id:
                    orphan_primary_rows.append(row)
                elif content_id in records:
                    records[content_id]["primary_video"] = row

            fetch_rows = _query_rows(
                connection,
                "SELECT * FROM content_video_fetch_state WHERE content_id = ANY(:ids) AND LOWER(source) = 'tmdb'",
                ids,
            )
            query_count += 1
            for row in fetch_rows:
                content_id = int(row.pop("content_id"))
                if content_id in records:
                    records[content_id]["video_fetch_state"] = row

            series_rows = _query_rows(
                connection,
                "SELECT * FROM content_series_metadata WHERE content_id = ANY(:ids)",
                ids,
            )
            query_count += 1
            for row in series_rows:
                content_id = int(row.pop("content_id"))
                if content_id in records:
                    records[content_id]["series_metadata"] = row

            unused_genres = [
                dict(row)
                for row in connection.execute(
                    text(
                        """
                        SELECT g.id, g.name FROM genres g
                        LEFT JOIN content_genres cg ON cg.genre_id = g.id
                        GROUP BY g.id, g.name HAVING COUNT(cg.content_id) = 0
                        ORDER BY LOWER(g.name), g.id
                        """
                    )
                ).mappings()
            ]
            query_count += 1
            transaction.rollback()
        except Exception:
            transaction.rollback()
            raise
    return [records[key] for key in sorted(records)], {
        "query_count": query_count,
        "read_only": True,
        "orphan_primary_rows": orphan_primary_rows,
        "unused_genres": unused_genres,
    }


def is_subgenre_proxy(signal: Mapping[str, Any]) -> bool:
    if normalize_text(signal.get("dimension")).replace(" ", "_") not in SUBGENRE_DIMENSIONS:
        return False
    text_value = f"{normalize_text(signal.get('value'))} {normalize_text(signal.get('label'))}"
    return any(term in text_value for term in SUBGENRE_TERMS)


def series_lifecycle_issues(record: Mapping[str, Any], reference_day: date) -> list[str]:
    metadata = record.get("series_metadata")
    if record.get("content_type") != "series":
        return []
    if not metadata:
        return ["series_metadata_missing"]
    issues = []
    last_episode = as_date(metadata.get("last_episode_air_date"))
    next_episode = as_date(metadata.get("next_episode_air_date"))
    status = normalize_text(metadata.get("series_status_normalized"))
    if last_episode and next_episode and next_episode < last_episode:
        issues.append("next_episode_precedes_last_episode")
    if status in {"ended", "canceled", "cancelled"} and next_episode and next_episode >= reference_day:
        issues.append("ended_series_has_future_episode")
    seasons = metadata.get("number_of_seasons")
    episodes = metadata.get("number_of_episodes")
    if seasons is not None and int(seasons) < 0:
        issues.append("negative_season_count")
    if episodes is not None and int(episodes) < 0:
        issues.append("negative_episode_count")
    return issues


def _metadata_flags(record: Mapping[str, Any]) -> dict[str, bool]:
    release_date = as_date(record.get("release_date"))
    year = record.get("year")
    release_consistent = not release_date or not year or int(year) == release_date.year
    credits = record.get("credits", [])
    is_series = record.get("content_type") == "series"
    has_leadership = any(
        row.get("role_type") in ({"creator"} if is_series else {"director"}) for row in credits
    )
    return {
        "title": bool(str(record.get("title") or "").strip()),
        "original_title": bool(str(record.get("original_title") or "").strip()),
        "original_language": bool(re.fullmatch(r"[a-z]{2,3}", normalize_text(record.get("original_language")))),
        "overview": bool(str(record.get("overview") or "").strip()),
        "release_date": release_date is not None,
        "year": isinstance(year, int) and 1870 <= year <= 2200,
        "release_year_consistent": release_consistent,
        # The canonical content runtime is a movie field in the current model.
        # Series episode runtimes are not stored here and are not counted missing.
        "runtime": record.get("content_type") != "movie" or (
            isinstance(record.get("runtime"), int) and record["runtime"] > 0
        ),
        "poster": bool(record.get("poster_url")),
        "backdrop": bool(record.get("backdrop_url")),
        "genres": bool(record.get("genres")),
        "tmdb_identity": bool(record.get("external_ids", {}).get("tmdb") or record.get("tmdb_id")),
        "imdb_identity": bool(record.get("external_ids", {}).get("imdb")),
        "latest_activity_date": as_date(record.get("latest_activity_date")) is not None,
        "ratings": bool(record.get("ratings")),
        "availability": bool(record.get("availability")),
        "cast": any(row.get("role_type") == "cast" for row in credits),
        "director_or_creator": has_leadership,
        "source_keywords": bool(record.get("keywords")),
        "source_signals": bool(record.get("signals")),
        "videos": bool(record.get("videos")),
        "primary_video": record.get("primary_video") is not None,
        "series_metadata": (not is_series) or record.get("series_metadata") is not None,
    }


def _keyword_quality(
    record: Mapping[str, Any], mapped: set[str], ignored: set[str]
) -> dict[str, Any]:
    raw = []
    for row in record.get("keywords", []):
        stored_normalized = normalize_keyword_name(row.get("normalized_keyword_name"))
        provider_name = normalize_keyword_name(row.get("keyword_name"))
        raw.append(stored_normalized or provider_name)
    raw = [value for value in raw if value]
    unique = sorted(set(raw))
    mapped_values = [value for value in unique if value in mapped]
    ignored_values = [value for value in unique if value in ignored]
    unmapped_values = [value for value in unique if value not in mapped and value not in ignored]
    denominator = len(mapped_values) + len(unmapped_values)
    return {
        "raw_count": len(raw),
        "unique_normalized_count": len(unique),
        "duplicate_normalized_count": len(raw) - len(unique),
        "mapped_count": len(mapped_values),
        "unmapped_count": len(unmapped_values),
        "ignored_count": len(ignored_values),
        "mapping_coverage": round(len(mapped_values) / denominator, 4) if denominator else None,
        "mapped_keywords": mapped_values,
        "unmapped_keywords": unmapped_values,
        "ignored_keywords": ignored_values,
    }


def _signal_quality(
    record: Mapping[str, Any], signal_frequency: Counter[tuple[str, str]], total: int,
    conflict_pairs: Mapping[str, Sequence[Sequence[str]]] | None = None,
) -> dict[str, Any]:
    signals = record.get("signals", [])
    categories = Counter(str(row.get("dimension")) for row in signals)
    identities = [(str(row.get("dimension")), str(row.get("value"))) for row in signals]
    duplicate_count = len(identities) - len(set(identities))
    rare = [f"{dimension}:{value}" for dimension, value in identities if signal_frequency[(dimension, value)] <= RARE_SIGNAL_MAX]
    overused = [
        f"{dimension}:{value}"
        for dimension, value in identities
        if total and signal_frequency[(dimension, value)] / total >= OVERUSED_SIGNAL_SHARE
    ]
    source_covered = sum(1 for row in signals if row.get("source_names"))
    conflicts = []
    values_by_dimension: dict[str, set[str]] = defaultdict(set)
    for dimension, value in identities:
        values_by_dimension[dimension].add(value)
    for dimension, pairs in (conflict_pairs or {}).items():
        for pair in pairs:
            normalized_pair = {normalize_text(value) for value in pair}
            if normalized_pair and normalized_pair.issubset({normalize_text(value) for value in values_by_dimension.get(dimension, set())}):
                conflicts.append({"dimension": dimension, "values": sorted(normalized_pair)})
    warnings = []
    if signals and len(categories) == 1:
        warnings.append("single_category_concentration")
    if len(signals) < WEAK_SIGNAL_COUNT and record.get("keywords"):
        warnings.append("weak_signal_count")
    if duplicate_count:
        warnings.append("duplicate_signals")
    if conflicts:
        warnings.append("configured_signal_conflict")
    return {
        "total": len(signals),
        "category_count": len(categories),
        "categories": dict(sorted(categories.items())),
        "source_provenance_coverage": round(source_covered / len(signals), 4) if signals else None,
        "confidence": dict(sorted(Counter(str(row.get("confidence")) for row in signals).items())),
        "duplicate_count": duplicate_count,
        "rare_signals": sorted(set(rare)),
        "overused_signals": sorted(set(overused)),
        "conflicts": conflicts,
        "subgenre_proxies": sorted({str(row.get("label") or row.get("value")) for row in signals if is_subgenre_proxy(row)}),
        "warnings": warnings,
    }


def _recommendation_readiness(records: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    feature_sets: dict[int, dict[str, set[Any]]] = {}
    metadata_sufficient = {}
    for record in records:
        content_id = int(record["content_id"])
        genres = {normalize_text(row.get("name")) for row in record.get("genres", []) if row.get("name")}
        signals = {(str(row.get("dimension")), str(row.get("value"))) for row in record.get("signals", [])}
        subgenres = {normalize_text(row.get("label") or row.get("value")) for row in record.get("signals", []) if is_subgenre_proxy(row)}
        people = {int(row["person_id"]) for row in record.get("credits", []) if row.get("role_type") in {"cast", "director", "creator"}}
        feature_sets[content_id] = {
            "genres": genres,
            "signals": signals,
            "subgenres": subgenres,
            "people": people,
        }
        metadata_sufficient[content_id] = bool(genres) and len(signals) >= WEAK_SIGNAL_COUNT

    output = {}
    for record in records:
        content_id = int(record["content_id"])
        source = feature_sets[content_id]
        counters = Counter()
        plausible_ids = []
        strong_ids = []
        for candidate in records:
            candidate_id = int(candidate["content_id"])
            if candidate_id == content_id:
                continue
            target = feature_sets[candidate_id]
            genre_overlap = len(source["genres"] & target["genres"])
            signal_overlap = len(source["signals"] & target["signals"])
            shared_people = len(source["people"] & target["people"])
            shared_subgenre = bool(source["subgenres"] & target["subgenres"])
            if genre_overlap >= 1:
                counters["genre_1"] += 1
            if genre_overlap >= 2:
                counters["genre_2"] += 1
            if signal_overlap >= 1:
                counters["signal_1"] += 1
            if signal_overlap >= 2:
                counters["signal_2"] += 1
            if shared_subgenre:
                counters["subgenre"] += 1
            if candidate.get("content_type") == record.get("content_type"):
                counters["content_type"] += 1
            if record.get("original_language") and candidate.get("original_language") == record.get("original_language"):
                counters["language"] += 1
            if shared_people:
                counters["people"] += 1
            feature_count = sum((genre_overlap > 0, signal_overlap > 0, shared_subgenre, shared_people > 0))
            if feature_count > 0 and metadata_sufficient.get(candidate_id):
                plausible_ids.append(candidate_id)
            if feature_count >= 2 and (genre_overlap >= 2 or signal_overlap >= 2 or shared_subgenre):
                strong_ids.append(candidate_id)

        if not metadata_sufficient[content_id]:
            status = "insufficient_data"
        elif len(plausible_ids) >= READY_PLAUSIBLE_MIN and len(strong_ids) >= READY_STRONG_MIN:
            status = "ready"
        elif len(plausible_ids) >= LIMITED_PLAUSIBLE_MIN:
            status = "limited"
        else:
            status = "sparse"
        output[content_id] = {
            "genre_candidates": counters["genre_1"],
            "two_genre_candidates": counters["genre_2"],
            "signal_candidates": counters["signal_1"],
            "two_signal_candidates": counters["signal_2"],
            "subgenre_candidates": counters["subgenre"],
            "same_type_candidates": counters["content_type"],
            "same_language_candidates": counters["language"],
            "shared_credit_candidates": counters["people"],
            "plausible_candidates": len(plausible_ids),
            "strong_candidates": len(strong_ids),
            "status": status,
        }
    return output


def _coverage_summary(per_title: list[dict[str, Any]], field: str) -> dict[str, Any]:
    applicable = [row for row in per_title if field in row["metadata_coverage"]]
    populated = [row for row in applicable if row["metadata_coverage"][field]]
    missing = [row for row in applicable if not row["metadata_coverage"][field]]
    by_type = {}
    for content_type in ("movie", "series"):
        subset = [row for row in applicable if row["content_type"] == content_type]
        count = sum(1 for row in subset if row["metadata_coverage"][field])
        by_type[content_type] = {"populated": count, "total": len(subset), "coverage_percentage": safe_percent(count, len(subset))}
    return {
        "populated": len(populated),
        "missing": len(missing),
        "coverage_percentage": safe_percent(len(populated), len(applicable)),
        "affected": [{"content_id": row["content_id"], "title": row["title"]} for row in missing],
        "by_content_type": by_type,
    }


def _genre_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    names = defaultdict(list)
    variants = defaultdict(set)
    for record in records:
        for genre in record.get("genres", []):
            name = str(genre.get("name") or "").strip()
            if name:
                names[name].append(record)
                variants[normalize_text(name)].add(name)
    rows = []
    for name, members in names.items():
        languages = {row.get("original_language") for row in members if row.get("original_language")}
        decades = {int(row["year"]) // 10 * 10 for row in members if isinstance(row.get("year"), int)}
        movie_count = sum(row.get("content_type") == "movie" for row in members)
        series_count = len(members) - movie_count
        rows.append(
            {
                "genre": name,
                "title_count": len(members),
                "movie_count": movie_count,
                "series_count": series_count,
                "language_diversity": len(languages),
                "decade_diversity": len(decades),
                "catalog_percentage": safe_percent(len(members), total),
                "discovery_density": "ready" if len(members) >= GENRE_DISCOVERY_MIN else "sparse",
                "similarity_density": "ready" if len(members) >= GENRE_SIMILARITY_MIN else "sparse",
                "single_language_dominated": bool(members) and max(Counter(row.get("original_language") or "missing" for row in members).values()) / len(members) >= 0.8,
            }
        )
    return {
        "genres": sorted(rows, key=lambda row: (-row["title_count"], row["genre"].casefold())),
        "titles_without_genres": [
            {"content_id": row["content_id"], "title": row["title"]}
            for row in records if not row.get("genres")
        ],
        "titles_with_excessive_genres": [
            {"content_id": row["content_id"], "title": row["title"], "count": len(row["genres"])}
            for row in records if len(row.get("genres", [])) > EXCESSIVE_GENRE_COUNT
        ],
        "case_or_spacing_variants": [sorted(value) for value in variants.values() if len(value) > 1],
    }


def _video_health(records: list[dict[str, Any]], reference_at: datetime) -> dict[str, Any]:
    statuses = Counter()
    provider = Counter()
    types = Counter()
    languages = Counter()
    due = []
    series_due = []
    videos_without_primary = []
    original_language_mismatches = []
    for record in records:
        videos = record.get("videos", [])
        if videos and not record.get("primary_video"):
            videos_without_primary.append({"content_id": record["content_id"], "title": record["title"]})
        for video in videos:
            provider[str(video.get("site") or "missing")] += 1
            types[str(video.get("video_type") or "missing")] += 1
            languages[str(video.get("language_code") or "neutral")] += 1
        video_languages = {
            normalize_text(video.get("language_code"))
            for video in videos
            if normalize_text(video.get("language_code"))
        }
        original_language = normalize_text(record.get("original_language"))
        if videos and original_language and original_language != "en" and video_languages == {"en"}:
            original_language_mismatches.append(
                {"content_id": record["content_id"], "title": record["title"], "original_language": original_language}
            )
        state = record.get("video_fetch_state") or {}
        statuses[str(state.get("last_fetch_status") or "missing")] += 1
        metadata = record.get("series_metadata") or {}
        planner_row = {
            **record,
            **metadata,
            "video_last_attempted_at": state.get("last_attempted_at"),
            "video_last_fetched_at": state.get("last_fetched_at"),
            "video_last_fetch_status": state.get("last_fetch_status"),
            "video_last_fetch_retryable": state.get("last_fetch_retryable"),
            "video_consecutive_failure_count": state.get("consecutive_failure_count"),
        }
        video_decision = evaluate_video_refresh(planner_row, reference_at)
        if video_decision.selected:
            due.append({"content_id": record["content_id"], "title": record["title"], "reason": video_decision.reason, "due_at": iso_value(video_decision.due_at)})
        if record.get("content_type") == "series":
            series_decision = evaluate_series_refresh(planner_row, reference_at)
            if series_decision.selected:
                series_due.append({"content_id": record["content_id"], "title": record["title"], "reason": series_decision.reason, "due_at": iso_value(series_decision.due_at)})
    return {
        "titles_with_videos": sum(bool(row.get("videos")) for row in records),
        "titles_without_videos": sum(not row.get("videos") for row in records),
        "titles_with_primary": sum(row.get("primary_video") is not None for row in records),
        "videos_without_primary": videos_without_primary,
        "provider_distribution": dict(sorted(provider.items())),
        "type_distribution": dict(sorted(types.items())),
        "language_distribution": dict(sorted(languages.items())),
        "titles_with_only_non_english_videos": sum(
            bool(row.get("videos"))
            and all(normalize_text(video.get("language_code")) not in {"", "en"} for video in row["videos"])
            for row in records
        ),
        "non_english_titles_with_only_english_videos": original_language_mismatches,
        "fetch_status_distribution": dict(sorted(statuses.items())),
        "retryable_failures": sum(bool((row.get("video_fetch_state") or {}).get("last_fetch_retryable")) for row in records),
        "manual_review_failures": sum(
            (row.get("video_fetch_state") or {}).get("last_fetch_status") in {"failed", "incomplete"}
            and not (row.get("video_fetch_state") or {}).get("last_fetch_retryable")
            for row in records
        ),
        "video_refresh_due": due,
        "series_refresh_due": series_due,
    }


def _discovery_readiness(per_title: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = len(per_title)
    fields = {
        "content_type": lambda row: bool(row.get("content_type")),
        "genre": lambda row: row["metadata_coverage"]["genres"],
        "platform": lambda row: row["metadata_coverage"]["availability"],
        "availability_type": lambda row: row["metadata_coverage"]["availability"],
        "language": lambda row: row["metadata_coverage"]["original_language"],
        "release_year_or_decade": lambda row: row["metadata_coverage"]["year"],
        "rating": lambda row: row["metadata_coverage"]["ratings"],
        "mood": lambda row: row["signal_quality"]["categories"].get("mood", 0) > 0,
        "pace": lambda row: row["signal_quality"]["categories"].get("pacing", 0) > 0,
        "intensity": lambda row: row["signal_quality"]["categories"].get("intensity", 0) > 0,
        "subgenre_proxy": lambda row: bool(row["signal_quality"]["subgenre_proxies"]),
        "series_status": lambda row: row["content_type"] != "series" or row["metadata_coverage"]["series_metadata"],
    }
    output = []
    for name, check in fields.items():
        count = sum(check(row) for row in per_title)
        ratio = count / total if total else 0
        if not total:
            status = "not_evaluated"
        elif ratio >= DISCOVERY_READY_COVERAGE:
            status = "production_ready"
        elif ratio >= DISCOVERY_GAPPED_COVERAGE:
            status = "usable_with_gaps"
        else:
            status = "too_sparse"
        output.append({"filter": name, "status": status, "covered": count, "total": total, "coverage_percentage": safe_percent(count, total)})
    output.append({"filter": "production_country_or_region", "status": "unsupported", "covered": 0, "total": total, "coverage_percentage": None, "reason": "No canonical production-country/origin-country field is stored; language is not used as a proxy."})
    return output


def _readiness(
    total: int,
    metadata: Mapping[str, Any],
    keyword: Mapping[str, Any],
    recommendations: Counter[str],
    discovery: list[dict[str, Any]],
    video: Mapping[str, Any],
    performance: Mapping[str, Any] | None,
    integrity_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    def entry(area: str, status: str, reasons: list[str], evidence: Mapping[str, Any]) -> dict[str, Any]:
        return {"area": area, "status": status, "reasons": reasons, "evidence": dict(evidence)}

    if not total:
        return [entry(area, "fail" if area in {"ingestion_readiness", "expansion_readiness"} else "not_evaluated", ["The selected catalog is empty."], {"total_titles": 0}) for area in READINESS_AREAS]

    tmdb_missing = metadata["tmdb_identity"]["missing"]
    ingestion_status = "fail" if integrity_issues else ("warning" if tmdb_missing else "pass")
    metadata_critical = sum(metadata[field]["missing"] for field in ("overview", "release_date", "poster", "genres"))
    metadata_status = "pass" if metadata_critical == 0 else ("warning" if metadata_critical / total < 0.15 else "fail")
    low_mapping = keyword["titles_many_keywords_low_mapping"]
    signal_status = "pass" if not low_mapping and keyword["titles_without_useful_signals"] == 0 else ("warning" if len(low_mapping) < max(3, total * 0.2) else "fail")
    ready_share = recommendations.get("ready", 0) / total
    rec_status = "pass" if ready_share >= 0.8 else ("warning" if ready_share >= 0.5 else "fail")
    sparse_filters = [row["filter"] for row in discovery if row["status"] == "too_sparse"]
    discovery_status = "pass" if not sparse_filters else ("warning" if len(sparse_filters) <= 3 else "fail")
    refresh_failures = video["fetch_status_distribution"].get("failed", 0) + video["fetch_status_distribution"].get("incomplete", 0)
    refresh_status = "pass" if not refresh_failures else ("warning" if refresh_failures < max(3, total * 0.1) else "fail")
    expansion_status = "pass" if ingestion_status == "pass" and metadata_status != "fail" else "warning"
    performance_status = "pass" if performance and performance.get("completed") else "not_evaluated"
    return [
        entry("ingestion_readiness", ingestion_status, [f"{tmdb_missing} titles lack canonical TMDb identity."] + ([f"{len(integrity_issues)} relationship integrity issues detected."] if integrity_issues else []), {"missing_tmdb_identity": tmdb_missing, "integrity_issue_count": len(integrity_issues)}),
        entry("metadata_readiness", metadata_status, [f"{metadata_critical} missing values across overview, release date, poster and genre coverage."], {"critical_missing_values": metadata_critical}),
        entry("source_signal_readiness", signal_status, [f"{len(low_mapping)} titles have many keywords with low mapping coverage.", f"{keyword['titles_without_useful_signals']} titles have no useful signals."], {"low_mapping_titles": len(low_mapping), "titles_without_signals": keyword["titles_without_useful_signals"]}),
        entry("recommendation_readiness", rec_status, [f"{recommendations.get('ready', 0)} of {total} titles meet current audit candidate thresholds."], dict(recommendations)),
        entry("discovery_readiness", discovery_status, [f"Sparse supported filters: {', '.join(sparse_filters) if sparse_filters else 'none'}."], {"sparse_filters": sparse_filters}),
        entry("refresh_readiness", refresh_status, [f"{refresh_failures} video refresh states require retry or review.", f"{len(video['video_refresh_due'])} titles are due under existing video cadence."], {"failed_or_incomplete": refresh_failures, "video_due": len(video["video_refresh_due"]), "series_due": len(video["series_refresh_due"])}),
        entry("expansion_readiness", expansion_status, ["Expansion targets are derived from measured type, language, decade, genre, lifecycle and candidate-density gaps."], {"current_catalog_size": total}),
        entry("performance_test_readiness", performance_status, ["Read-only performance baseline completed." if performance_status == "pass" else "Run with --performance-check to evaluate query structure and current-catalog timing."], {"performance_check_requested": bool(performance)}),
    ]


def build_expansion_gap_plan(report: Mapping[str, Any]) -> dict[str, Any]:
    composition = report["catalog_composition"]
    current = composition["total_content"]
    target = 275 if current < 250 else (400 if current < 350 else current)
    additions = max(target - current, 0)
    movies = composition["total_movies"]
    series = composition["total_series"]
    target_movie_share = 0.55
    movie_target = round(target * target_movie_share)
    movie_additions = min(additions, max(movie_target - movies, 0))
    series_additions = additions - movie_additions
    languages = report["language_and_release_distribution"]["languages"]
    language_targets = []
    for row in sorted(languages, key=lambda value: (value["count"], value["value"])):
        if row["value"] not in {"missing", "invalid", "en"} and row["count"] < 5:
            language_targets.append({"language": row["value"], "minimum_additions": min(8, max(3, 6 - row["count"])), "reason": f"Only {row['count']} current titles; candidate density is fragile."})
    if not language_targets:
        language_targets.append({"language": "non-English (reviewed mix)", "minimum_additions": max(10, round(additions * 0.2)), "reason": "Protect language diversity without inferring region from language."})
    sparse_genres = [row for row in report["genre_and_subgenre_coverage"]["genres"] if row["title_count"] < GENRE_SIMILARITY_MIN]
    genre_targets = [{"genre": row["genre"], "minimum_additions": min(8, GENRE_SIMILARITY_MIN - row["title_count"]), "reason": f"{row['title_count']} current titles; below the {GENRE_SIMILARITY_MIN}-title similarity audit threshold."} for row in sparse_genres[:12]]
    sparse_subgenres = [row for row in report["genre_and_subgenre_coverage"]["subgenre_proxies"] if row["title_count"] < 4]
    subgenre_targets = [{"subgenre_proxy": row["label"], "minimum_additions": 4 - row["title_count"], "reason": "Stored mapped signal proxy has fewer than four candidate titles."} for row in sparse_subgenres[:12]]
    readiness = report["more_like_this_readiness"]["status_distribution"]
    return {
        "generated_at": report["generated_at"],
        "reference_date": report["reference_date"],
        "basis": "Derived only from the audited local catalog; contains no invented provider IDs or automatic title selections.",
        "recommended_next_catalog_size": target,
        "recommended_additions": additions,
        "targets": {
            "content_type": {"movies": movie_additions, "series": series_additions},
            "languages": language_targets[:8],
            "genres": genre_targets,
            "subgenres": subgenre_targets,
            "decades": report["language_and_release_distribution"]["underrepresented_decades"][:8],
            "lifecycle": {"upcoming": max(5, round(additions * 0.08)), "currently_airing": max(6, round(additions * 0.1)), "ended_series": max(8, round(series_additions * 0.35))},
            "recommendation_density": {"limited_sparse_or_insufficient_titles": readiness.get("limited", 0) + readiness.get("sparse", 0) + readiness.get("insufficient_data", 0), "principle": "Prioritize additions that create multiple genre and mapped-signal overlaps for currently weak titles."},
            "difficult_ingestion_cases": ["missing poster/backdrop", "non-English original title", "limited/miniseries lifecycle", "future season announcement", "valid empty video snapshot", "multiple availability regions"],
            "niche_representation": {"principle": "Reserve a reviewed share for lower-popularity and niche titles within measured sparse genres/languages; popularity is not currently stored canonically enough to set a numeric quota."},
        },
        "selection_principles": [
            "Select reviewed categories before exact titles.",
            "Improve candidate density across at least two independent features.",
            "Preserve movie/series, language, decade and lifecycle diversity.",
            "Do not infer production country from language.",
            "Run the audit again after each bounded import wave.",
        ],
    }


def build_audit(
    records: list[dict[str, Any]],
    mapping_config: Mapping[str, Any],
    *,
    reference_at: datetime,
    sample_size: int = 12,
    top_unmapped_keywords: int = 25,
    load_metadata: Mapping[str, Any] | None = None,
    performance: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    records = sorted(records, key=lambda row: (int(row["content_id"]), str(row.get("title") or "")))
    total = len(records)
    mapped, ignored, configured_dimensions = mapping_sets(mapping_config)
    signal_frequency = Counter(
        (str(signal.get("dimension")), str(signal.get("value")))
        for record in records for signal in record.get("signals", [])
    )
    recommendation = _recommendation_readiness(records)
    per_title = []
    unmapped_frequency = Counter()
    raw_frequency = Counter()
    ignored_frequency = Counter()
    mapped_signal_frequency = Counter()
    subgenre_frequency = Counter()
    lifecycle_issues = []
    for record in records:
        flags = _metadata_flags(record)
        keywords = _keyword_quality(record, mapped, ignored)
        for value in set(keywords["mapped_keywords"] + keywords["unmapped_keywords"] + keywords["ignored_keywords"]):
            raw_frequency[value] += 1
        unmapped_frequency.update(keywords["unmapped_keywords"])
        ignored_frequency.update(keywords["ignored_keywords"])
        signals = _signal_quality(record, signal_frequency, total, mapping_config.get("conflict_pairs"))
        for signal in record.get("signals", []):
            mapped_signal_frequency[(str(signal.get("dimension")), str(signal.get("value")), str(signal.get("label")))] += 1
        subgenre_frequency.update(signals["subgenre_proxies"])
        issues = [field for field, populated in flags.items() if not populated]
        issues.extend(series_lifecycle_issues(record, reference_at.date()))
        if keywords["raw_count"] >= MANY_KEYWORDS and (keywords["mapping_coverage"] or 0) < LOW_MAPPING_COVERAGE:
            issues.append("many_keywords_low_mapping")
        issues.extend(signals["warnings"])
        if record.get("videos") and not record.get("primary_video"):
            issues.append("videos_without_primary")
        if any(issue in {"next_episode_precedes_last_episode", "ended_series_has_future_episode"} for issue in issues):
            lifecycle_issues.append({"content_id": record["content_id"], "title": record["title"], "issues": [issue for issue in issues if "episode" in issue or "ended_series" in issue]})
        priority = "high" if any(issue in {"tmdb_identity", "series_metadata_missing", "next_episode_precedes_last_episode", "ended_series_has_future_episode"} for issue in issues) else ("review" if issues else "normal")
        per_title.append(
            {
                "content_id": int(record["content_id"]),
                "title": str(record.get("title") or ""),
                "content_type": str(record.get("content_type") or ""),
                "original_language": record.get("original_language"),
                "genres": [str(row.get("name")) for row in record.get("genres", [])],
                "metadata_coverage": flags,
                "keyword_quality": keywords,
                "signal_quality": signals,
                "recommendation_readiness": recommendation[int(record["content_id"])],
                "issues": sorted(set(issues)),
                "review_priority": priority,
            }
        )

    lifecycle_statuses = Counter()
    currently_airing = []
    returning = []
    ended = []
    cancelled = []
    limited = []
    upcoming = []
    recently_released = []
    old_catalog = []
    for record in records:
        release = as_date(record.get("release_date"))
        if release and release > reference_at.date():
            upcoming.append({"content_id": record["content_id"], "title": record["title"], "release_date": release.isoformat()})
        elif release and release >= reference_at.date() - timedelta(days=90):
            recently_released.append({"content_id": record["content_id"], "title": record["title"], "release_date": release.isoformat()})
        elif release and release < reference_at.date() - timedelta(days=3650):
            old_catalog.append({"content_id": record["content_id"], "title": record["title"], "release_date": release.isoformat()})
        if record.get("content_type") != "series":
            continue
        metadata = record.get("series_metadata") or {}
        lifecycle = normalize_text(metadata.get("series_status_normalized")) or "missing"
        lifecycle_statuses[lifecycle] += 1
        last_episode = as_date(metadata.get("last_episode_air_date"))
        next_episode = as_date(metadata.get("next_episode_air_date"))
        next_season = as_date(metadata.get("next_season_air_date"))
        if lifecycle == "ongoing" and (
            (next_episode and reference_at.date() <= next_episode <= reference_at.date() + timedelta(days=21))
            or (last_episode and reference_at.date() - timedelta(days=45) <= last_episode <= reference_at.date())
        ):
            currently_airing.append({"content_id": record["content_id"], "title": record["title"]})
        elif lifecycle in {"ongoing", "upcoming"} and (
            metadata.get("has_announced_season") or (next_season and next_season >= reference_at.date())
        ):
            returning.append({"content_id": record["content_id"], "title": record["title"]})
        if lifecycle == "ended":
            ended.append({"content_id": record["content_id"], "title": record["title"]})
        if lifecycle in {"canceled", "cancelled"}:
            cancelled.append({"content_id": record["content_id"], "title": record["title"]})
        if normalize_text(metadata.get("series_type")) in {"miniseries", "limited series", "limited"}:
            limited.append({"content_id": record["content_id"], "title": record["title"]})

    composition = {
        "total_content": total,
        "total_movies": sum(row.get("content_type") == "movie" for row in records),
        "total_series": sum(row.get("content_type") == "series" for row in records),
        "titles_with_tmdb_identity": sum(row["metadata_coverage"]["tmdb_identity"] for row in per_title),
        "titles_without_tmdb_identity": sum(not row["metadata_coverage"]["tmdb_identity"] for row in per_title),
        "by_year": distribution((str(row["year"]) if row.get("year") else "missing" for row in records), total),
        "by_content_status": distribution((normalize_text(row.get("status")) or "missing" for row in records), total),
        "series_by_normalized_lifecycle": [
            {"value": value, "count": count, "percentage_of_series": safe_percent(count, composition_total)}
            for value, count in sorted(lifecycle_statuses.items(), key=lambda item: (-item[1], item[0]))
            for composition_total in [sum(lifecycle_statuses.values())]
        ],
        "upcoming_titles": upcoming,
        "recently_released_titles": recently_released,
        "currently_airing_series": currently_airing,
        "returning_series": returning,
        "ended_series": ended,
        "cancelled_series": cancelled,
        "limited_or_miniseries": limited,
        "old_catalog_titles": old_catalog,
        "recent_catalog_titles": [
            {"content_id": row["content_id"], "title": row["title"]}
            for row in records
            if as_date(row.get("release_date"))
            and as_date(row.get("release_date")) >= reference_at.date() - timedelta(days=3650)
        ],
    }
    languages = [normalize_text(row.get("original_language")) if re.fullmatch(r"[a-z]{2,3}", normalize_text(row.get("original_language"))) else ("missing" if not row.get("original_language") else "invalid") for row in records]
    decades = [f"{int(row['year']) // 10 * 10}s" if isinstance(row.get("year"), int) else "missing" for row in records]
    decade_dist = distribution(decades, total)
    language_release = {
        "languages": distribution(languages, total),
        "english_count": languages.count("en"),
        "non_english_count": sum(value not in {"en", "missing", "invalid"} for value in languages),
        "rare_languages": [row for row in distribution(languages, total) if row["value"] not in {"missing", "invalid"} and row["count"] <= 2],
        "missing_or_invalid_language": languages.count("missing") + languages.count("invalid"),
        "decades": decade_dist,
        "underrepresented_decades": [row for row in decade_dist if row["value"] != "missing" and row["count"] < 5],
        "missing_release_dates": sum(as_date(row.get("release_date")) is None for row in records),
        "country_or_region": {"status": "not_evaluated", "reason": "No canonical production-country/origin-country data is stored; language is not used as a proxy."},
    }
    genre_report = _genre_report(records)
    genre_report["unused_genres"] = list((load_metadata or {}).get("unused_genres", []))
    genre_report["subgenre_taxonomy"] = {"status": "proxy_only", "reason": "No canonical subgenre dimension is stored. Reported values are conservative labels from active audience_expectation/topic_theme signals."}
    genre_report["subgenre_proxies"] = [{"label": value, "title_count": count, "similarity_density": "ready" if count >= 4 else "sparse"} for value, count in sorted(subgenre_frequency.items(), key=lambda item: (-item[1], item[0]))]
    metadata_fields = sorted(per_title[0]["metadata_coverage"] if per_title else _metadata_flags(empty_record({"content_type": "movie"})))
    metadata_coverage = {field: _coverage_summary(per_title, field) for field in metadata_fields}
    series_records = [row for row in records if row.get("content_type") == "series"]
    series_fields = (
        "series_status",
        "series_status_normalized",
        "in_production",
        "number_of_seasons",
        "number_of_episodes",
        "first_air_date",
        "last_air_date",
        "last_episode_air_date",
        "next_episode_air_date",
        "has_announced_season",
        "next_season_number",
        "next_season_air_date",
        "last_refreshed_at",
    )
    series_coverage = {}
    for field in series_fields:
        populated = sum(
            (record.get("series_metadata") or {}).get(field) is not None
            for record in series_records
        )
        series_coverage[field] = {
            "populated": populated,
            "missing": len(series_records) - populated,
            "coverage_percentage": safe_percent(populated, len(series_records)),
            "affected": [
                {"content_id": record["content_id"], "title": record["title"]}
                for record in series_records
                if (record.get("series_metadata") or {}).get(field) is None
            ],
            "interpretation": (
                "optional_by_lifecycle; null is not automatically an ingestion defect"
                if field in {"next_episode_air_date", "next_season_number", "next_season_air_date"}
                else "expected_for_series"
            ),
        }
    metadata_coverage["series_fields"] = series_coverage
    metadata_coverage["malformed_or_inconsistent"] = {
        "invalid_runtime": [{"content_id": row["content_id"], "title": row["title"]} for row in per_title if not row["metadata_coverage"]["runtime"]],
        "release_year_mismatch": [{"content_id": row["content_id"], "title": row["title"]} for row in per_title if not row["metadata_coverage"]["release_year_consistent"]],
        "series_lifecycle": lifecycle_issues,
        "primary_relationship": list((load_metadata or {}).get("orphan_primary_rows", [])),
    }
    keyword_signal = {
        "mapping_version": mapping_config.get("mapping_version"),
        "keyword_normalization": keyword_normalization_metadata(),
        "configured_dimensions": sorted(configured_dimensions),
        "raw_keyword_title_frequency": [{"keyword": value, "title_count": count} for value, count in raw_frequency.most_common(top_unmapped_keywords)],
        "top_unmapped_keywords": [{"keyword": value, "title_count": count} for value, count in unmapped_frequency.most_common(top_unmapped_keywords)],
        "top_ignored_keywords": [{"keyword": value, "title_count": count} for value, count in ignored_frequency.most_common(top_unmapped_keywords)],
        "mapped_signals": [{"dimension": dimension, "value": value, "label": label, "title_count": count, "catalog_percentage": safe_percent(count, total)} for (dimension, value, label), count in sorted(mapped_signal_frequency.items(), key=lambda item: (-item[1], item[0]))],
        "rare_signals": [{"dimension": dimension, "value": value, "title_count": count} for (dimension, value), count in sorted(signal_frequency.items()) if count <= RARE_SIGNAL_MAX],
        "overused_signals": [{"dimension": dimension, "value": value, "title_count": count, "catalog_percentage": safe_percent(count, total)} for (dimension, value), count in sorted(signal_frequency.items(), key=lambda item: (-item[1], item[0])) if total and count / total >= OVERUSED_SIGNAL_SHARE],
        "titles_many_keywords_low_mapping": [{"content_id": row["content_id"], "title": row["title"], "raw_count": row["keyword_quality"]["raw_count"], "mapping_coverage": row["keyword_quality"]["mapping_coverage"]} for row in per_title if "many_keywords_low_mapping" in row["issues"]],
        "titles_without_useful_signals": sum(row["signal_quality"]["total"] == 0 for row in per_title),
        "titles_with_single_signal_category": sum("single_category_concentration" in row["signal_quality"]["warnings"] for row in per_title),
        "conflict_detection": {"status": "evaluated" if mapping_config.get("conflict_pairs") else "not_evaluated", "reason": None if mapping_config.get("conflict_pairs") else "The current mapping config defines no mutually exclusive signal pairs; conflicts are not invented."},
    }
    video_health = _video_health(records, reference_at)
    recommendation_status = Counter(value["status"] for value in recommendation.values())
    more_like = {
        "thresholds": {"ready": {"plausible": READY_PLAUSIBLE_MIN, "strong": READY_STRONG_MIN}, "limited": {"plausible": LIMITED_PLAUSIBLE_MIN}},
        "status_distribution": dict(sorted(recommendation_status.items())),
        "weak_examples": [{"content_id": row["content_id"], "title": row["title"], **row["recommendation_readiness"]} for row in per_title if row["recommendation_readiness"]["status"] != "ready"][:sample_size],
    }
    discovery = _discovery_readiness(per_title)
    integrity_issues = list((load_metadata or {}).get("orphan_primary_rows", []))
    readiness = _readiness(total, metadata_coverage, keyword_signal, recommendation_status, discovery, video_health, performance, integrity_issues)
    report = {
        "audit_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reference_date": reference_at.isoformat(),
        "scope": {"content_type": records[0].get("_scope_content_type") if records and records[0].get("_scope_content_type") else None, "limit_applied": None},
        "safety": {"database_mode": "read_only_transaction", "external_requests": 0, "database_writes": 0, "set_based_query_count": (load_metadata or {}).get("query_count")},
        "thresholds": {"many_keywords": MANY_KEYWORDS, "low_mapping_coverage": LOW_MAPPING_COVERAGE, "weak_signal_count": WEAK_SIGNAL_COUNT, "rare_signal_max_titles": RARE_SIGNAL_MAX, "overused_signal_share": OVERUSED_SIGNAL_SHARE, "genre_discovery_min": GENRE_DISCOVERY_MIN, "genre_similarity_min": GENRE_SIMILARITY_MIN},
        "catalog_composition": composition,
        "language_and_release_distribution": language_release,
        "genre_and_subgenre_coverage": genre_report,
        "metadata_coverage": metadata_coverage,
        "video_and_refresh_health": video_health,
        "keyword_and_source_signal_quality": keyword_signal,
        "more_like_this_readiness": more_like,
        "discovery_readiness": discovery,
        "performance_baseline": performance or {"completed": False, "reason": "Run with --performance-check."},
        "readiness": readiness,
        "high_priority_review": [row for row in per_title if row["review_priority"] == "high"][:sample_size],
        "per_title": per_title,
    }
    gap_plan = build_expansion_gap_plan(report)
    report["expansion_gap_summary"] = {"recommended_next_catalog_size": gap_plan["recommended_next_catalog_size"], "recommended_additions": gap_plan["recommended_additions"], "gap_plan_output": str(DEFAULT_GAP_OUTPUT)}
    return report, gap_plan


PERFORMANCE_QUERIES = {
    "catalog_listing": "SELECT id, title, content_type, year FROM content ORDER BY id LIMIT 50",
    "recent_content": "SELECT id, title, release_date, latest_activity_date FROM content ORDER BY COALESCE(latest_activity_date, release_date) DESC NULLS LAST, id LIMIT 25",
    "top_rated": "SELECT c.id, c.title, cs.unified_score FROM content c JOIN content_summary cs ON cs.content_id = c.id WHERE cs.unified_score IS NOT NULL ORDER BY cs.unified_score DESC, c.id LIMIT 25",
    "genre_filter": "SELECT c.id, c.title FROM content c JOIN content_genres cg ON cg.content_id = c.id JOIN genres g ON g.id = cg.genre_id WHERE g.id = (SELECT MIN(id) FROM genres) ORDER BY c.id LIMIT 50",
    "platform_filter": "SELECT DISTINCT c.id, c.title FROM content c JOIN content_availability ca ON ca.content_id = c.id WHERE ca.platform_id = (SELECT MIN(platform_id) FROM content_availability) ORDER BY c.id LIMIT 50",
    "content_details": "SELECT c.id, c.title, c.overview FROM content c WHERE c.id = (SELECT MIN(id) FROM content)",
    "watch_later_list": "SELECT wl.content_id, c.title FROM watch_later wl JOIN content c ON c.id = wl.content_id WHERE wl.user_id = (SELECT MIN(id) FROM users) ORDER BY wl.added_at DESC, wl.content_id LIMIT 50",
    "watched_list": "SELECT w.content_id, c.title FROM watched w JOIN content c ON c.id = w.content_id WHERE w.user_id = (SELECT MIN(id) FROM users) ORDER BY w.watched_at DESC, w.content_id LIMIT 50",
    "genre_metadata": "SELECT id, name FROM genres ORDER BY LOWER(name), id LIMIT 100",
}


def run_performance_baseline(database_url: str, *, explain: bool = False) -> dict[str, Any]:
    engine = create_engine(database_url)
    rows = []
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION READ ONLY"))
            for name, sql in PERFORMANCE_QUERIES.items():
                started = time.perf_counter()
                result = connection.execute(text(sql)).fetchall()
                elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
                item = {"query": name, "elapsed_ms": elapsed_ms, "returned_rows": len(result), "bounded": "LIMIT" in sql.upper() or "WHERE c.id" in sql}
                if explain:
                    plan = connection.execute(text(f"EXPLAIN (FORMAT JSON) {sql}")).scalar()
                    item["explain"] = plan
                rows.append(item)
            transaction.rollback()
        except Exception:
            transaction.rollback()
            raise
    return {
        "completed": True,
        "read_only": True,
        "queries": rows,
        "observations": [
            "Timings describe the current local catalog only and are not a production scalability claim.",
            "Sequential scans may be reasonable at current size; repeat EXPLAIN review at 300–400 titles.",
            "Separate synthetic-scale testing is still required for recommendation candidate generation and user-list growth.",
        ],
    }


def render_markdown(report: Mapping[str, Any], gap_plan: Mapping[str, Any]) -> str:
    composition = report["catalog_composition"]
    readiness = report["readiness"]
    metadata = report["metadata_coverage"]
    lines = [
        "# InsightStream Catalog Baseline and Expansion Readiness",
        "",
        f"Generated: `{report['generated_at']}`  ",
        f"Reference date: `{report['reference_date']}`",
        "",
        "## Executive Summary",
        "",
        f"The audited scope contains **{composition['total_content']} titles**: {composition['total_movies']} movies and {composition['total_series']} series. This is a read-only baseline; it made no provider requests and no database writes.",
        "",
        "## Readiness",
        "",
        "| Area | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    for row in readiness:
        lines.append(f"| {row['area'].replace('_', ' ').title()} | **{row['status']}** | {' '.join(row['reasons'])} |")
    lines.extend(["", "## Catalog Composition", "", "| Metric | Value |", "| --- | ---: |", f"| Total | {composition['total_content']} |", f"| Movies | {composition['total_movies']} |", f"| Series | {composition['total_series']} |", f"| Missing TMDb identity | {composition['titles_without_tmdb_identity']} |"])
    lines.extend(["", "## Core Metadata Coverage", "", "| Field | Populated | Missing | Coverage |", "| --- | ---: | ---: | ---: |"])
    for field in ("overview", "release_date", "poster", "backdrop", "genres", "ratings", "availability", "cast", "director_or_creator", "source_keywords", "source_signals", "videos", "primary_video"):
        row = metadata[field]
        lines.append(f"| {field.replace('_', ' ').title()} | {row['populated']} | {row['missing']} | {row['coverage_percentage']}% |")
    lines.extend(["", "## Language and Decade Distribution", "", "| Language | Titles | Share |", "| --- | ---: | ---: |"])
    for row in report["language_and_release_distribution"]["languages"][:12]:
        lines.append(f"| {row['value']} | {row['count']} | {row['percentage']}% |")
    lines.extend(["", "Country/region representation is **not evaluated** because no canonical production-country/origin-country field is stored. Language is not used as a proxy.", "", "## Genre and Subgenre Coverage", "", "| Genre | Titles | Movies | Series | Discovery | Similarity |", "| --- | ---: | ---: | ---: | --- | --- |"])
    for row in report["genre_and_subgenre_coverage"]["genres"][:20]:
        lines.append(f"| {row['genre']} | {row['title_count']} | {row['movie_count']} | {row['series_count']} | {row['discovery_density']} | {row['similarity_density']} |")
    lines.extend(["", "Subgenres are reported only as a conservative proxy from active mapped `audience_expectation` and `topic_theme` signals; they are not a canonical genre taxonomy.", "", "## Video and Refresh Health", ""])
    video = report["video_and_refresh_health"]
    lines.extend([f"- Titles with videos: **{video['titles_with_videos']}**", f"- Titles with a primary video: **{video['titles_with_primary']}**", f"- Video refresh due: **{len(video['video_refresh_due'])}**", f"- Series refresh due: **{len(video['series_refresh_due'])}**"])
    keyword = report["keyword_and_source_signal_quality"]
    lines.extend(
        [
            "",
            "## Keyword and Source-Signal Quality",
            "",
            f"- Mapping version: `{keyword['mapping_version']}`",
            (
                "- Keyword normalization: "
                f"`{keyword['keyword_normalization']['version']}`"
            ),
            f"- Titles with many keywords and low mapping coverage: **{len(keyword['titles_many_keywords_low_mapping'])}**",
            f"- Titles without useful signals: **{keyword['titles_without_useful_signals']}**",
            f"- Rare signals: **{len(keyword['rare_signals'])}**",
            f"- Overused signals: **{len(keyword['overused_signals'])}**",
        ]
    )
    lines.extend(["", "### Top Unmapped Keywords", "", "| Keyword | Titles |", "| --- | ---: |"])
    for row in keyword["top_unmapped_keywords"][:15]:
        lines.append(f"| {row['keyword']} | {row['title_count']} |")
    lines.extend(["", "## More Like This Readiness", ""])
    for status, count in report["more_like_this_readiness"]["status_distribution"].items():
        lines.append(f"- {status}: **{count}**")
    lines.extend(["", "## Discovery Readiness", "", "| Filter | Status | Coverage |", "| --- | --- | ---: |"])
    for row in report["discovery_readiness"]:
        coverage = "n/a" if row["coverage_percentage"] is None else f"{row['coverage_percentage']}%"
        lines.append(f"| {row['filter']} | {row['status']} | {coverage} |")
    lines.extend(["", "## Expansion Gap Plan", "", f"Recommended next size: **{gap_plan['recommended_next_catalog_size']}** ({gap_plan['recommended_additions']} additions).", "", f"Type target for additions: {gap_plan['targets']['content_type']['movies']} movies and {gap_plan['targets']['content_type']['series']} series.", "", "The machine-readable gap plan contains measured language, genre, subgenre-proxy, decade, lifecycle and candidate-density targets. It does not invent provider IDs or select exact titles.", "", "## Basic Performance", ""])
    perf = report["performance_baseline"]
    if perf.get("completed"):
        lines.extend(["| Query | Rows | Elapsed (ms) | Bounded |", "| --- | ---: | ---: | --- |"])
        for row in perf["queries"]:
            lines.append(f"| {row['query']} | {row['returned_rows']} | {row['elapsed_ms']} | {row['bounded']} |")
    else:
        lines.append("Not evaluated. Run with `--performance-check`.")
    high = report["high_priority_review"]
    lines.extend(["", "## Highest-Priority Review", ""])
    if not high:
        lines.append("No high-priority records in the configured sample.")
    else:
        for row in high:
            lines.append(f"- `{row['content_id']}` {row['title']}: {', '.join(row['issues'])}")
    lines.extend(["", "## Recommended Actions Before Expansion", "", "1. Resolve high-priority identity and lifecycle inconsistencies.", "2. Improve mappings for frequent unmapped keywords and rerun source-signal previews.", "3. Add reviewed titles in sparse genres, language groups and lifecycle states.", "4. Prefer additions that strengthen weak More Like This candidate pools across multiple features.", "5. Rerun this audit after each bounded expansion wave and run separate synthetic-scale tests before claiming production scalability.", ""])
    return "\n".join(lines)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=iso_value) + "\n", encoding="utf-8")


def write_reports(
    report: Mapping[str, Any], gap_plan: Mapping[str, Any], *, json_path: Path, markdown_path: Path, gap_path: Path
) -> None:
    write_json(json_path, report)
    write_json(gap_path, gap_plan)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report, gap_plan), encoding="utf-8")


def strict_exit_code(report: Mapping[str, Any]) -> int:
    return 2 if any(row["status"] == "fail" for row in report["readiness"]) else 0


def main(argv: Sequence[str] | None = None) -> int:
    if load_dotenv is not None:
        load_dotenv(REPO_ROOT / "backend" / ".env")
    args = parse_args(argv)
    database_url = args.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required (or pass --database-url).", file=sys.stderr)
        return 2
    try:
        records, load_metadata = load_catalog_records(database_url, content_type=args.content_type, limit=args.limit)
        for record in records:
            record["_scope_content_type"] = args.content_type
        performance = run_performance_baseline(database_url, explain=args.explain) if args.performance_check or args.explain else None
        report, gap_plan = build_audit(
            records,
            load_mapping_config(),
            reference_at=args.reference_date,
            sample_size=args.sample_size,
            top_unmapped_keywords=args.top_unmapped_keywords,
            load_metadata=load_metadata,
            performance=performance,
        )
        report["scope"] = {"content_type": args.content_type or "all", "limit_applied": args.limit}
        report["expansion_gap_summary"]["gap_plan_output"] = str(args.output_gap_plan)
        write_reports(report, gap_plan, json_path=args.output_json, markdown_path=args.output_markdown, gap_path=args.output_gap_plan)
    except Exception as exc:
        print(f"Catalog audit failed: {exc}", file=sys.stderr)
        return 2
    print(f"Audited {report['catalog_composition']['total_content']} titles (read-only).")
    print(f"JSON: {args.output_json}")
    print(f"Markdown: {args.output_markdown}")
    print(f"Expansion plan: {args.output_gap_plan}")
    for row in report["readiness"]:
        print(f"- {row['area']}: {row['status']}")
    return strict_exit_code(report) if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
