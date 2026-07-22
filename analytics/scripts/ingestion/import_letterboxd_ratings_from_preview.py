#!/usr/bin/env python3
"""
Dry-run or apply Letterboxd ratings from the reviewed match preview.

This script:
- reads analytics/processed/letterboxd/letterboxd_rating_match_preview.json
- requires DATABASE_URL for dry-run comparison and apply mode
- matches content by preview content_id only
- imports high-confidence matches by default
- imports ambiguous matches only with --include-ambiguous
- requires --apply before writing to PostgreSQL
- does not read raw Letterboxd reviews, scrape, or call external APIs

Dry run:
    python3 -m analytics.scripts.ingestion.import_letterboxd_ratings_from_preview

Apply reviewed high-confidence + ambiguous matches:
    python3 -m analytics.scripts.ingestion.import_letterboxd_ratings_from_preview \
        --include-ambiguous --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


from analytics.scripts.common.paths import REPO_ROOT
DEFAULT_PREVIEW_PATH = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "letterboxd"
    / "letterboxd_rating_match_preview.json"
)
DATABASE_URL_ENV = "DATABASE_URL"
LETTERBOXD_SOURCE = {
    "source_name": "letterboxd",
    "display_name": "Letterboxd",
    "source_category": "audience",
    "raw_score_scale_default": 5,
    "weight": 0.0,
    "is_active": True,
    "source_url": "https://letterboxd.com/",
    "notes": (
        "Letterboxd ratings imported from a manually reviewed local dataset "
        "match preview. Vote counts are unavailable, reviews are not imported, "
        "and this source is excluded from InsightStream Score v1."
    ),
}
IMPORTABLE_STATUSES = {"high_confidence", "ambiguous"}


@dataclass(frozen=True)
class ContentMatch:
    content_id: int
    title: str
    content_type: str


@dataclass(frozen=True)
class LetterboxdRatingRecord:
    content_id: int
    local_title: str
    match_status: str
    confidence_score: float
    raw_score: float
    raw_score_scale: float
    normalized_score: float
    vote_count: None
    rating_count_label: None
    rating_url: str | None
    source_payload: dict[str, Any]
    fetched_at: datetime


@dataclass
class ImportStats:
    mode: str
    preview_path: str
    preview_rows_scanned: int = 0
    eligible_rows: int = 0
    selected_high_confidence_rows: int = 0
    selected_ambiguous_rows: int = 0
    skipped_ambiguous_rows: int = 0
    skipped_unmatched_rows: int = 0
    skipped_invalid_rows: int = 0
    inserted_ratings: int = 0
    updated_ratings: int = 0
    unchanged_ratings: int = 0
    rating_sources_inserted: int = 0
    rating_sources_updated: int = 0
    missing_content_matches: int = 0
    warnings: list[str] = field(default_factory=list)


class LetterboxdRatingsImportError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply Letterboxd ratings from reviewed match preview."
    )
    parser.add_argument(
        "--preview-file",
        default=str(DEFAULT_PREVIEW_PATH.relative_to(REPO_ROOT)),
        help=(
            "Path to Letterboxd match preview JSON. Defaults to "
            f"{DEFAULT_PREVIEW_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--include-ambiguous",
        action="store_true",
        help="Import ambiguous preview rows that have been manually reviewed.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write Letterboxd ratings to PostgreSQL. Without this flag, no DB writes occur.",
    )
    return parser.parse_args()


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


def clean_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def clean_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def parse_preview_timestamp(value: Any) -> datetime:
    text_value = clean_text(value)
    if not text_value:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, Decimal):
        left = float(left)
    if isinstance(right, Decimal):
        right = float(right)
    if isinstance(left, float) or isinstance(right, float):
        if left is None or right is None:
            return left is right
        return round(float(left), 3) == round(float(right), 3)
    return left == right


def json_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, default=str) == json.dumps(
        right,
        sort_keys=True,
        default=str,
    )


def json_param(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True)


def load_preview(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise LetterboxdRatingsImportError(
            f"Missing Letterboxd match preview: {relative_path(path)}"
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LetterboxdRatingsImportError(
            f"Malformed Letterboxd preview JSON in {relative_path(path)}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise LetterboxdRatingsImportError("Letterboxd preview root must be an object.")
    if not isinstance(data.get("items"), list):
        raise LetterboxdRatingsImportError("Letterboxd preview must contain an items list.")

    return data


def fetch_rating_source(conn: Any, source_name: str):
    return conn.execute(
        text(
            """
            SELECT id, display_name, source_category, raw_score_scale_default, weight, is_active
            FROM rating_sources
            WHERE source_name = :source_name;
            """
        ),
        {"source_name": source_name},
    ).mappings().first()


def insert_or_update_letterboxd_rating_source(conn: Any) -> int:
    row = conn.execute(
        text(
            """
            INSERT INTO rating_sources (
                source_name,
                display_name,
                source_category,
                raw_score_scale_default,
                weight,
                is_active,
                source_url,
                notes
            )
            VALUES (
                :source_name,
                :display_name,
                :source_category,
                :raw_score_scale_default,
                :weight,
                :is_active,
                :source_url,
                :notes
            )
            ON CONFLICT (source_name) DO UPDATE
            SET
                display_name = EXCLUDED.display_name,
                source_category = EXCLUDED.source_category,
                raw_score_scale_default = EXCLUDED.raw_score_scale_default,
                weight = EXCLUDED.weight,
                is_active = EXCLUDED.is_active,
                source_url = EXCLUDED.source_url,
                notes = EXCLUDED.notes,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id;
            """
        ),
        LETTERBOXD_SOURCE,
    ).mappings().first()
    return row["id"]


def ensure_letterboxd_rating_source(conn: Any, stats: ImportStats, apply: bool) -> int:
    source = fetch_rating_source(conn, "letterboxd")
    if source is None:
        stats.rating_sources_inserted += 1
        if apply:
            return insert_or_update_letterboxd_rating_source(conn)
        return -1

    changed = any(
        not values_equal(source.get(field), LETTERBOXD_SOURCE[field])
        for field in (
            "display_name",
            "source_category",
            "raw_score_scale_default",
            "weight",
            "is_active",
        )
    )
    if changed:
        stats.rating_sources_updated += 1
        if apply:
            return insert_or_update_letterboxd_rating_source(conn)

    return source["id"]


def fetch_content(conn: Any, content_id: int) -> ContentMatch | None:
    row = conn.execute(
        text(
            """
            SELECT id, title, content_type
            FROM content
            WHERE id = :content_id;
            """
        ),
        {"content_id": content_id},
    ).mappings().first()

    if row is None:
        return None

    return ContentMatch(
        content_id=row["id"],
        title=row["title"],
        content_type=row["content_type"],
    )


def fetch_content_rating(conn: Any, content_id: int, rating_source_id: int):
    if rating_source_id < 0:
        return None
    return conn.execute(
        text(
            """
            SELECT
                id,
                raw_score,
                raw_score_scale,
                normalized_score,
                vote_count,
                rating_count_label,
                rating_url,
                source_payload
            FROM content_ratings
            WHERE content_id = :content_id
              AND rating_source_id = :rating_source_id;
            """
        ),
        {
            "content_id": content_id,
            "rating_source_id": rating_source_id,
        },
    ).mappings().first()


def rating_record_from_preview_item(
    item: Any,
    fetched_at: datetime,
    include_ambiguous: bool,
    dataset_file: str | None,
    stats: ImportStats,
) -> LetterboxdRatingRecord | None:
    stats.preview_rows_scanned += 1

    if not isinstance(item, dict):
        stats.skipped_invalid_rows += 1
        stats.warnings.append("Preview item is not an object; skipped.")
        return None

    local_title = clean_text(item.get("local_title")) or f"content_id={item.get('content_id')}"
    content_id = clean_int(item.get("content_id"))
    match_status = clean_text(item.get("match_status")) or "unknown"
    confidence_score = clean_float(item.get("confidence_score")) or 0
    letterboxd = item.get("letterboxd")

    if content_id is None:
        stats.skipped_invalid_rows += 1
        stats.warnings.append(f"{local_title}: missing content_id; skipped.")
        return None

    if match_status == "ambiguous" and not include_ambiguous:
        stats.skipped_ambiguous_rows += 1
        return None
    if match_status in {"unmatched", "no_match"}:
        stats.skipped_unmatched_rows += 1
        return None
    if match_status not in IMPORTABLE_STATUSES:
        stats.skipped_invalid_rows += 1
        stats.warnings.append(f"{local_title}: unsupported match_status {match_status!r}; skipped.")
        return None
    if not isinstance(letterboxd, dict):
        stats.skipped_invalid_rows += 1
        stats.warnings.append(f"{local_title}: missing Letterboxd match object; skipped.")
        return None

    raw_score = clean_float(letterboxd.get("raw_score"))
    raw_score_scale = clean_float(letterboxd.get("raw_score_scale"))
    if raw_score_scale is None:
        raw_score_scale = 5
    rating_url = clean_text(letterboxd.get("url"))
    if raw_score is None:
        stats.skipped_invalid_rows += 1
        stats.warnings.append(f"{local_title}: missing Letterboxd raw_score; skipped.")
        return None
    if raw_score_scale <= 0:
        stats.skipped_invalid_rows += 1
        stats.warnings.append(f"{local_title}: invalid Letterboxd raw_score_scale; skipped.")
        return None

    normalized_score = max(0, min(100, raw_score / raw_score_scale * 100))
    stats.eligible_rows += 1
    if match_status == "high_confidence":
        stats.selected_high_confidence_rows += 1
    elif match_status == "ambiguous":
        stats.selected_ambiguous_rows += 1

    source_payload = {
        "title": clean_text(letterboxd.get("title")),
        "year": letterboxd.get("year"),
        "directors": letterboxd.get("directors") or [],
        "url": rating_url,
        "match_status": match_status,
        "confidence_score": confidence_score,
        "dataset_snapshot_source": dataset_file,
    }

    return LetterboxdRatingRecord(
        content_id=content_id,
        local_title=local_title,
        match_status=match_status,
        confidence_score=confidence_score,
        raw_score=raw_score,
        raw_score_scale=raw_score_scale,
        normalized_score=round(normalized_score, 2),
        vote_count=None,
        rating_count_label=None,
        rating_url=rating_url,
        source_payload=source_payload,
        fetched_at=fetched_at,
    )


def rating_update_plan(
    existing: dict[str, Any],
    rating: LetterboxdRatingRecord,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    comparable_fields = {
        "raw_score": rating.raw_score,
        "raw_score_scale": rating.raw_score_scale,
        "normalized_score": rating.normalized_score,
        "vote_count": rating.vote_count,
        "rating_count_label": rating.rating_count_label,
        "rating_url": rating.rating_url,
    }

    for field_name, preview_value in comparable_fields.items():
        if not values_equal(existing.get(field_name), preview_value):
            updates[field_name] = preview_value

    if not json_equal(existing.get("source_payload"), rating.source_payload):
        updates["source_payload"] = rating.source_payload

    if updates:
        updates["fetched_at"] = rating.fetched_at

    return updates


def insert_content_rating(
    conn: Any,
    rating_source_id: int,
    rating: LetterboxdRatingRecord,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO content_ratings (
                content_id,
                rating_source_id,
                raw_score,
                raw_score_scale,
                normalized_score,
                vote_count,
                rating_count_label,
                rating_url,
                source_payload,
                fetched_at
            )
            VALUES (
                :content_id,
                :rating_source_id,
                :raw_score,
                :raw_score_scale,
                :normalized_score,
                NULL,
                NULL,
                :rating_url,
                CAST(:source_payload AS JSONB),
                :fetched_at
            )
            ON CONFLICT (content_id, rating_source_id) DO NOTHING;
            """
        ),
        {
            "content_id": rating.content_id,
            "rating_source_id": rating_source_id,
            "raw_score": rating.raw_score,
            "raw_score_scale": rating.raw_score_scale,
            "normalized_score": rating.normalized_score,
            "rating_url": rating.rating_url,
            "source_payload": json_param(rating.source_payload),
            "fetched_at": rating.fetched_at,
        },
    )


def update_content_rating(conn: Any, rating_id: int, updates: dict[str, Any]) -> None:
    set_clauses = []
    params: dict[str, Any] = {"rating_id": rating_id}

    for field_name, value in updates.items():
        if field_name == "source_payload":
            set_clauses.append("source_payload = CAST(:source_payload AS JSONB)")
            params[field_name] = json_param(value)
        else:
            set_clauses.append(f"{field_name} = :{field_name}")
            params[field_name] = value

    set_clauses.append("updated_at = CURRENT_TIMESTAMP")

    conn.execute(
        text(
            f"""
            UPDATE content_ratings
            SET {", ".join(set_clauses)}
            WHERE id = :rating_id;
            """
        ),
        params,
    )


def process_preview(
    conn: Any,
    preview: dict[str, Any],
    preview_path: Path,
    include_ambiguous: bool,
    apply: bool,
) -> ImportStats:
    stats = ImportStats(
        mode="APPLY" if apply else "DRY RUN",
        preview_path=relative_path(preview_path),
    )
    fetched_at = parse_preview_timestamp(preview.get("generated_at"))
    dataset_file = clean_text(preview.get("dataset_file"))
    rating_source_id = ensure_letterboxd_rating_source(conn, stats, apply)

    for item in preview.get("items", []):
        rating = rating_record_from_preview_item(
            item,
            fetched_at,
            include_ambiguous,
            dataset_file,
            stats,
        )
        if rating is None:
            continue

        content = fetch_content(conn, rating.content_id)
        if content is None:
            stats.missing_content_matches += 1
            stats.warnings.append(
                f"{rating.local_title}: no content row found for content_id {rating.content_id}; skipped."
            )
            continue
        if content.content_type != "movie":
            stats.skipped_invalid_rows += 1
            stats.warnings.append(
                f"{rating.local_title}: content_id {rating.content_id} is not a movie; skipped."
            )
            continue

        existing = fetch_content_rating(conn, rating.content_id, rating_source_id)
        if existing is None:
            if apply:
                insert_content_rating(conn, rating_source_id, rating)
            stats.inserted_ratings += 1
            continue

        updates = rating_update_plan(dict(existing), rating)
        if updates:
            if apply:
                update_content_rating(conn, existing["id"], updates)
            stats.updated_ratings += 1
        else:
            stats.unchanged_ratings += 1

    return stats


def print_summary(stats: ImportStats, include_ambiguous: bool) -> None:
    print("\nLetterboxd ratings import summary:")
    print(f"- Mode: {stats.mode}")
    print(f"- Preview path: {stats.preview_path}")
    print(f"- Include ambiguous: {include_ambiguous}")
    print(f"- Preview rows scanned: {stats.preview_rows_scanned}")
    print(f"- Eligible rows: {stats.eligible_rows}")
    print(f"- High-confidence rows selected: {stats.selected_high_confidence_rows}")
    print(f"- Ambiguous rows selected: {stats.selected_ambiguous_rows}")
    print(f"- Skipped ambiguous rows: {stats.skipped_ambiguous_rows}")
    print(f"- Skipped unmatched rows: {stats.skipped_unmatched_rows}")
    print(f"- Skipped invalid rows: {stats.skipped_invalid_rows}")
    print(f"- Rating sources inserted: {stats.rating_sources_inserted}")
    print(f"- Rating sources updated: {stats.rating_sources_updated}")
    print(f"- Inserted ratings: {stats.inserted_ratings}")
    print(f"- Updated ratings: {stats.updated_ratings}")
    print(f"- Unchanged ratings: {stats.unchanged_ratings}")
    print(f"- Missing content matches: {stats.missing_content_matches}")
    print(f"- Warnings: {len(stats.warnings)}")

    if stats.warnings:
        print("\nWarnings:")
        for warning in stats.warnings[:20]:
            print(f"- {warning}")
        if len(stats.warnings) > 20:
            print(f"... {len(stats.warnings) - 20} more warnings")

    if stats.mode == "DRY RUN":
        print("\nDry run only. No database changes were made.")
    else:
        print("\nApply completed successfully.")

    print("No reviews, scraping, external calls, frontend changes, or sample_data changes were made.")


def main() -> int:
    args = parse_args()
    preview_path = resolve_path(args.preview_file)
    database_url = os.environ.get(DATABASE_URL_ENV)

    if not database_url:
        print(
            f"Missing {DATABASE_URL_ENV}. Export it before running this DB-aware import script."
        )
        print("No database changes were made.")
        return 1

    try:
        preview = load_preview(preview_path)
    except LetterboxdRatingsImportError as exc:
        print(f"Letterboxd ratings import failed: {exc}")
        return 1

    engine = create_engine(database_url)
    try:
        if args.apply:
            with engine.begin() as conn:
                stats = process_preview(
                    conn,
                    preview,
                    preview_path,
                    include_ambiguous=args.include_ambiguous,
                    apply=True,
                )
        else:
            with engine.connect() as conn:
                stats = process_preview(
                    conn,
                    preview,
                    preview_path,
                    include_ambiguous=args.include_ambiguous,
                    apply=False,
                )
    except (LetterboxdRatingsImportError, SQLAlchemyError) as exc:
        print(f"Letterboxd ratings import failed: {exc}")
        if args.apply:
            print("Transaction rolled back.")
        return 1

    print_summary(stats, include_ambiguous=args.include_ambiguous)
    return 0


if __name__ == "__main__":
    sys.exit(main())
