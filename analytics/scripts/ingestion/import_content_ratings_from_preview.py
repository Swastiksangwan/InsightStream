#!/usr/bin/env python3
"""
Dry-run or apply content ratings from the processed TMDb content preview.

This script:
- reads analytics/processed/tmdb/sample_mapping_preview.json
- requires DATABASE_URL for dry-run comparison and apply mode
- runs in dry-run mode by default
- requires --apply before writing to PostgreSQL
- does not call TMDb or any external API
- does not modify backend/frontend/schema/sample_data files

Dry run:
    python3 -m analytics.scripts.ingestion.import_content_ratings_from_preview

Apply:
    python3 -m analytics.scripts.ingestion.import_content_ratings_from_preview --apply
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
    REPO_ROOT / "analytics" / "processed" / "tmdb" / "sample_mapping_preview.json"
)
DATABASE_URL_ENV = "DATABASE_URL"
TMDB_SOURCE = {
    "source_name": "tmdb",
    "display_name": "TMDb",
    "source_category": "audience",
    "raw_score_scale_default": 10,
    "weight": 1.0,
    "is_active": True,
    "source_url": "https://www.themoviedb.org/",
    "notes": "TMDb vote_average and vote_count imported through the metadata ingestion pipeline.",
}


@dataclass(frozen=True)
class ContentMatch:
    content_id: int
    title: str
    content_type: str


@dataclass(frozen=True)
class RatingPreviewRecord:
    title: str
    source_name: str
    display_name: str
    source_category: str
    raw_score: float | None
    raw_score_scale: float | None
    normalized_score: float | None
    vote_count: int | None
    rating_count_label: str | None
    rating_url: str | None
    source_payload: dict[str, Any] | None
    fetched_at: datetime


@dataclass
class ImportStats:
    mode: str
    preview_path: str
    items_processed: int = 0
    items_skipped: int = 0
    ratings_seen: int = 0
    inserted_ratings: int = 0
    updated_ratings: int = 0
    unchanged_ratings: int = 0
    skipped_ratings: int = 0
    missing_content_matches: int = 0
    rating_sources_inserted: int = 0
    rating_sources_updated: int = 0
    warnings: list[str] = field(default_factory=list)


class RatingsImportError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run or apply provider-neutral content ratings from "
            "analytics/processed/tmdb/sample_mapping_preview.json."
        )
    )
    parser.add_argument(
        "--preview",
        default=str(DEFAULT_PREVIEW_PATH.relative_to(REPO_ROOT)),
        help=(
            "Path to processed content metadata preview. Defaults to "
            f"{DEFAULT_PREVIEW_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write content ratings to PostgreSQL. Without this flag, no DB writes occur.",
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
    if isinstance(value, str) and value.strip():
        return value.strip()
    if value is not None:
        text_value = str(value).strip()
        return text_value or None
    return None


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
        raise RatingsImportError(f"Missing ratings preview: {relative_path(path)}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RatingsImportError(
            f"Malformed ratings preview JSON in {relative_path(path)}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise RatingsImportError("Ratings preview root must be an object.")
    if data.get("source_provider") != "tmdb":
        raise RatingsImportError("Ratings preview source_provider must be 'tmdb'.")
    if data.get("inspection_only") is not True:
        raise RatingsImportError("Ratings preview must be marked inspection_only.")
    if not isinstance(data.get("items"), list):
        raise RatingsImportError("Ratings preview must contain an items list.")

    return data


def find_content_by_tmdb_id(conn: Any, source_id: str) -> ContentMatch | None:
    row = conn.execute(
        text(
            """
            SELECT c.id, c.title, c.content_type
            FROM external_ids ei
            JOIN content c ON c.id = ei.content_id
            WHERE ei.source_name = 'tmdb'
              AND ei.external_id = :source_id;
            """
        ),
        {"source_id": source_id},
    ).mappings().first()

    if not row:
        return None

    return ContentMatch(
        content_id=row["id"],
        title=row["title"],
        content_type=row["content_type"],
    )


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


def insert_or_update_rating_source(conn: Any) -> int:
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
        TMDB_SOURCE,
    ).mappings().first()
    return row["id"]


def ensure_tmdb_rating_source(conn: Any, stats: ImportStats, apply: bool) -> int:
    source = fetch_rating_source(conn, "tmdb")
    if source is None:
        stats.rating_sources_inserted += 1
        if apply:
            return insert_or_update_rating_source(conn)
        return -1

    changed = any(
        not values_equal(source.get(field), TMDB_SOURCE[field])
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
            return insert_or_update_rating_source(conn)

    return source["id"]


def rating_record_from_preview(
    rating: Any,
    title: str,
    fetched_at: datetime,
    stats: ImportStats,
) -> RatingPreviewRecord | None:
    if not isinstance(rating, dict):
        stats.warnings.append(f"{title}: rating preview item is not an object; skipped.")
        stats.skipped_ratings += 1
        return None

    source_name = (clean_text(rating.get("source_name")) or "").lower()
    if source_name != "tmdb":
        stats.warnings.append(
            f"{title}: unsupported rating source {source_name!r}; only TMDb is imported in v1."
        )
        stats.skipped_ratings += 1
        return None

    raw_score = clean_float(rating.get("raw_score"))
    raw_score_scale = clean_float(rating.get("raw_score_scale"))
    normalized_score = clean_float(rating.get("normalized_score"))
    vote_count = clean_int(rating.get("vote_count"))

    if raw_score is None:
        stats.warnings.append(f"{title}: missing raw_score; TMDb rating skipped.")
        stats.skipped_ratings += 1
        return None
    if raw_score_scale is None or raw_score_scale <= 0:
        stats.warnings.append(f"{title}: invalid raw_score_scale; TMDb rating skipped.")
        stats.skipped_ratings += 1
        return None

    if normalized_score is None:
        normalized_score = raw_score / raw_score_scale * 100
    normalized_score = max(0, min(100, normalized_score))

    if vote_count is not None and vote_count < 0:
        stats.warnings.append(f"{title}: negative vote_count; preserving vote_count as null.")
        vote_count = None

    source_payload = rating.get("source_payload")
    if source_payload is not None and not isinstance(source_payload, dict):
        stats.warnings.append(f"{title}: source_payload is not an object; preserving null.")
        source_payload = None

    return RatingPreviewRecord(
        title=title,
        source_name=source_name,
        display_name=clean_text(rating.get("display_name")) or "TMDb",
        source_category=clean_text(rating.get("source_category")) or "audience",
        raw_score=raw_score,
        raw_score_scale=raw_score_scale,
        normalized_score=round(normalized_score, 2),
        vote_count=vote_count,
        rating_count_label=clean_text(rating.get("rating_count_label")),
        rating_url=clean_text(rating.get("rating_url")),
        source_payload=source_payload,
        fetched_at=fetched_at,
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


def rating_update_plan(existing: dict[str, Any], rating: RatingPreviewRecord) -> dict[str, Any]:
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
    content: ContentMatch,
    rating_source_id: int,
    rating: RatingPreviewRecord,
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
                :vote_count,
                :rating_count_label,
                :rating_url,
                CAST(:source_payload AS JSONB),
                :fetched_at
            )
            ON CONFLICT (content_id, rating_source_id) DO NOTHING;
            """
        ),
        {
            "content_id": content.content_id,
            "rating_source_id": rating_source_id,
            "raw_score": rating.raw_score,
            "raw_score_scale": rating.raw_score_scale,
            "normalized_score": rating.normalized_score,
            "vote_count": rating.vote_count,
            "rating_count_label": rating.rating_count_label,
            "rating_url": rating.rating_url,
            "source_payload": json_param(rating.source_payload),
            "fetched_at": rating.fetched_at,
        },
    )


def update_content_rating(
    conn: Any,
    rating_id: int,
    updates: dict[str, Any],
) -> None:
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
    apply: bool,
) -> ImportStats:
    stats = ImportStats(
        mode="APPLY" if apply else "DRY RUN",
        preview_path=relative_path(preview_path),
    )
    fetched_at = parse_preview_timestamp(preview.get("generated_at"))
    tmdb_rating_source_id = ensure_tmdb_rating_source(conn, stats, apply)

    for index, item in enumerate(preview.get("items", []), start=1):
        stats.items_processed += 1
        if not isinstance(item, dict):
            stats.items_skipped += 1
            stats.warnings.append(f"Preview item {index}: expected object; skipped.")
            continue

        title = clean_text(item.get("title")) or f"Preview item {index}"
        source_id = clean_text(item.get("source_id")) or clean_text(item.get("tmdb_id"))
        if not source_id:
            stats.items_skipped += 1
            stats.warnings.append(f"{title}: missing TMDb source_id; skipped.")
            continue

        content = find_content_by_tmdb_id(conn, source_id)
        if content is None:
            stats.missing_content_matches += 1
            stats.warnings.append(
                f"{title}: no content row matched TMDb external ID {source_id}; skipped ratings."
            )
            continue

        ratings = item.get("ratings")
        if not isinstance(ratings, list) or not ratings:
            stats.skipped_ratings += 1
            stats.warnings.append(f"{title}: no rating preview rows found.")
            continue

        for raw_rating in ratings:
            stats.ratings_seen += 1
            rating = rating_record_from_preview(raw_rating, title, fetched_at, stats)
            if rating is None:
                continue

            existing = fetch_content_rating(
                conn,
                content.content_id,
                tmdb_rating_source_id,
            )
            if existing is None:
                if apply:
                    insert_content_rating(
                        conn,
                        content,
                        tmdb_rating_source_id,
                        rating,
                    )
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


def print_summary(stats: ImportStats) -> None:
    print("\nContent ratings import summary:")
    print(f"- Mode: {stats.mode}")
    print(f"- Preview path: {stats.preview_path}")
    print(f"- Items processed: {stats.items_processed}")
    print(f"- Items skipped: {stats.items_skipped}")
    print(f"- Rating preview rows seen: {stats.ratings_seen}")
    print(f"- Rating sources inserted: {stats.rating_sources_inserted}")
    print(f"- Rating sources updated: {stats.rating_sources_updated}")
    print(f"- Inserted ratings: {stats.inserted_ratings}")
    print(f"- Updated ratings: {stats.updated_ratings}")
    print(f"- Unchanged ratings: {stats.unchanged_ratings}")
    print(f"- Skipped ratings: {stats.skipped_ratings}")
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

    print("No backend, frontend, schema, or sample_data files were changed.")


def main() -> int:
    args = parse_args()
    preview_path = resolve_path(args.preview)
    database_url = os.environ.get(DATABASE_URL_ENV)

    if not database_url:
        print(
            f"Missing {DATABASE_URL_ENV}. Export it before running this DB-aware import script."
        )
        print("No database changes were made.")
        return 1

    try:
        preview = load_preview(preview_path)
    except RatingsImportError as exc:
        print(f"Content ratings import failed: {exc}")
        return 1

    engine = create_engine(database_url)
    try:
        if args.apply:
            with engine.begin() as conn:
                stats = process_preview(conn, preview, preview_path, apply=True)
        else:
            with engine.connect() as conn:
                stats = process_preview(conn, preview, preview_path, apply=False)
    except (RatingsImportError, SQLAlchemyError) as exc:
        print(f"Content ratings import failed: {exc}")
        if args.apply:
            print("Transaction rolled back.")
        return 1

    print_summary(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
