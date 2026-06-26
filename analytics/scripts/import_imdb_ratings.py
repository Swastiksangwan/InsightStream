#!/usr/bin/env python3
"""
Dry-run or apply IMDb ratings from the official title.ratings.tsv dataset.

This script:
- reads a local IMDb title.ratings.tsv or title.ratings.tsv.gz file
- requires DATABASE_URL for dry-run comparison and apply mode
- matches ratings only through external_ids.source_name = 'imdb'
- runs in dry-run mode by default
- requires --apply before writing to PostgreSQL
- does not call IMDb, TMDb, or any external API

Dry run:
    python3 analytics/scripts/import_imdb_ratings.py \
        --ratings-file analytics/datasets/imdb/title.ratings.tsv

Apply:
    python3 analytics/scripts/import_imdb_ratings.py \
        --ratings-file analytics/datasets/imdb/title.ratings.tsv \
        --apply
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


REPO_ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL_ENV = "DATABASE_URL"
IMDB_SOURCE = {
    "source_name": "imdb",
    "display_name": "IMDb",
    "source_category": "audience",
    "raw_score_scale_default": 10,
    "weight": 1.0,
    "is_active": True,
    "source_url": "https://developer.imdb.com/non-commercial-datasets/",
    "notes": (
        "IMDb ratings imported from the official non-commercial "
        "title.ratings.tsv dataset."
    ),
}


@dataclass(frozen=True)
class CatalogImdbId:
    content_id: int
    title: str
    content_type: str
    imdb_id: str


@dataclass(frozen=True)
class ImdbRatingRecord:
    tconst: str
    raw_score: float
    raw_score_scale: float
    normalized_score: float
    vote_count: int
    rating_count_label: str
    source_payload: dict[str, Any]
    fetched_at: datetime


@dataclass
class ImportStats:
    mode: str
    ratings_file: str
    dataset_rows_scanned: int = 0
    catalog_imdb_external_ids_found: int = 0
    matched_imdb_ratings: int = 0
    inserted_ratings: int = 0
    updated_ratings: int = 0
    unchanged_ratings: int = 0
    skipped_ratings: int = 0
    unmatched_catalog_imdb_ids: int = 0
    rating_sources_inserted: int = 0
    rating_sources_updated: int = 0
    warnings: list[str] = field(default_factory=list)


class ImdbRatingsImportError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run or apply IMDb ratings from a local official "
            "title.ratings.tsv dataset file."
        )
    )
    parser.add_argument(
        "--ratings-file",
        required=True,
        help="Path to IMDb title.ratings.tsv or title.ratings.tsv.gz.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write IMDb ratings to PostgreSQL. Without this flag, no DB writes occur.",
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


def format_vote_count(vote_count: int | None) -> str | None:
    if vote_count is None:
        return None
    return f"{vote_count:,} votes"


def open_ratings_file(path: Path):
    if not path.exists():
        raise ImdbRatingsImportError(f"Missing IMDb ratings file: {relative_path(path)}")
    if path.suffix == ".gz":
        return gzip.open(path, mode="rt", encoding="utf-8", newline="")
    return path.open(mode="r", encoding="utf-8", newline="")


def imdb_rating_from_row(
    row: dict[str, Any],
    fetched_at: datetime,
    stats: ImportStats,
) -> ImdbRatingRecord | None:
    tconst = clean_text(row.get("tconst"))
    raw_score = clean_float(row.get("averageRating"))
    vote_count = clean_int(row.get("numVotes"))

    if not tconst:
        stats.skipped_ratings += 1
        stats.warnings.append("IMDb row missing tconst; skipped.")
        return None
    if raw_score is None:
        stats.skipped_ratings += 1
        stats.warnings.append(f"{tconst}: missing averageRating; skipped.")
        return None
    if vote_count is None or vote_count < 0:
        stats.skipped_ratings += 1
        stats.warnings.append(f"{tconst}: invalid numVotes; skipped.")
        return None

    normalized_score = max(0, min(100, raw_score * 10))

    return ImdbRatingRecord(
        tconst=tconst,
        raw_score=raw_score,
        raw_score_scale=10,
        normalized_score=round(normalized_score, 2),
        vote_count=vote_count,
        rating_count_label=format_vote_count(vote_count) or "",
        source_payload={
            "tconst": tconst,
            "averageRating": raw_score,
            "numVotes": vote_count,
        },
        fetched_at=fetched_at,
    )


def scan_imdb_ratings_file(
    path: Path,
    catalog_imdb_ids: set[str],
    stats: ImportStats,
    fetched_at: datetime,
) -> dict[str, ImdbRatingRecord]:
    matched: dict[str, ImdbRatingRecord] = {}

    with open_ratings_file(path) as file_obj:
        reader = csv.DictReader(file_obj, delimiter="\t")
        expected_columns = {"tconst", "averageRating", "numVotes"}
        if not reader.fieldnames or not expected_columns <= set(reader.fieldnames):
            raise ImdbRatingsImportError(
                "IMDb ratings file must contain tconst, averageRating, and numVotes columns."
            )

        for row in reader:
            stats.dataset_rows_scanned += 1
            tconst = clean_text(row.get("tconst"))
            if not tconst or tconst not in catalog_imdb_ids:
                continue

            record = imdb_rating_from_row(row, fetched_at, stats)
            if record is None:
                continue

            matched[tconst] = record

    stats.matched_imdb_ratings = len(matched)
    return matched


def fetch_catalog_imdb_ids(conn: Any) -> list[CatalogImdbId]:
    rows = conn.execute(
        text(
            """
            SELECT
                c.id AS content_id,
                c.title,
                c.content_type,
                ei.external_id AS imdb_id
            FROM external_ids ei
            JOIN content c ON c.id = ei.content_id
            WHERE ei.source_name = 'imdb'
              AND ei.external_id IS NOT NULL
              AND TRIM(ei.external_id) <> ''
            ORDER BY c.id ASC;
            """
        )
    ).mappings().all()

    return [
        CatalogImdbId(
            content_id=row["content_id"],
            title=row["title"],
            content_type=row["content_type"],
            imdb_id=row["imdb_id"],
        )
        for row in rows
    ]


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


def insert_or_update_imdb_rating_source(conn: Any) -> int:
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
        IMDB_SOURCE,
    ).mappings().first()
    return row["id"]


def ensure_imdb_rating_source(conn: Any, stats: ImportStats, apply: bool) -> int:
    source = fetch_rating_source(conn, "imdb")
    if source is None:
        stats.rating_sources_inserted += 1
        if apply:
            return insert_or_update_imdb_rating_source(conn)
        return -1

    changed = any(
        not values_equal(source.get(field), IMDB_SOURCE[field])
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
            return insert_or_update_imdb_rating_source(conn)

    return source["id"]


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


def rating_update_plan(existing: dict[str, Any], rating: ImdbRatingRecord) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    comparable_fields = {
        "raw_score": rating.raw_score,
        "raw_score_scale": rating.raw_score_scale,
        "normalized_score": rating.normalized_score,
        "vote_count": rating.vote_count,
        "rating_count_label": rating.rating_count_label,
        "rating_url": None,
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
    catalog_item: CatalogImdbId,
    rating_source_id: int,
    rating: ImdbRatingRecord,
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
                NULL,
                CAST(:source_payload AS JSONB),
                :fetched_at
            )
            ON CONFLICT (content_id, rating_source_id) DO NOTHING;
            """
        ),
        {
            "content_id": catalog_item.content_id,
            "rating_source_id": rating_source_id,
            "raw_score": rating.raw_score,
            "raw_score_scale": rating.raw_score_scale,
            "normalized_score": rating.normalized_score,
            "vote_count": rating.vote_count,
            "rating_count_label": rating.rating_count_label,
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


def duplicate_imdb_ids(catalog_items: Iterable[CatalogImdbId]) -> dict[str, list[str]]:
    seen: dict[str, list[str]] = {}
    for item in catalog_items:
        seen.setdefault(item.imdb_id, []).append(item.title)
    return {imdb_id: titles for imdb_id, titles in seen.items() if len(titles) > 1}


def process_imdb_ratings(
    conn: Any,
    ratings_file: Path,
    apply: bool,
) -> ImportStats:
    stats = ImportStats(
        mode="APPLY" if apply else "DRY RUN",
        ratings_file=relative_path(ratings_file),
    )
    fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    rating_source_id = ensure_imdb_rating_source(conn, stats, apply)
    catalog_items = fetch_catalog_imdb_ids(conn)
    stats.catalog_imdb_external_ids_found = len(catalog_items)

    duplicates = duplicate_imdb_ids(catalog_items)
    for imdb_id, titles in sorted(duplicates.items()):
        stats.warnings.append(
            f"Duplicate catalog IMDb external ID {imdb_id}: {', '.join(titles)}."
        )

    catalog_ids = {item.imdb_id for item in catalog_items}
    imdb_ratings = scan_imdb_ratings_file(ratings_file, catalog_ids, stats, fetched_at)
    matched_ids = set(imdb_ratings)
    unmatched_ids = sorted(catalog_ids - matched_ids)
    stats.unmatched_catalog_imdb_ids = len(unmatched_ids)
    for imdb_id in unmatched_ids[:20]:
        matching_items = [item.title for item in catalog_items if item.imdb_id == imdb_id]
        stats.warnings.append(
            f"No IMDb rating row found for {imdb_id} ({', '.join(matching_items)})."
        )
    if len(unmatched_ids) > 20:
        stats.warnings.append(
            f"{len(unmatched_ids) - 20} more catalog IMDb IDs were not found in the dataset."
        )

    for catalog_item in catalog_items:
        rating = imdb_ratings.get(catalog_item.imdb_id)
        if rating is None:
            continue

        existing = fetch_content_rating(conn, catalog_item.content_id, rating_source_id)
        if existing is None:
            if apply:
                insert_content_rating(conn, catalog_item, rating_source_id, rating)
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
    print("\nIMDb ratings import summary:")
    print(f"- Mode: {stats.mode}")
    print(f"- Ratings file: {stats.ratings_file}")
    print(f"- Dataset rows scanned: {stats.dataset_rows_scanned}")
    print(f"- Catalog IMDb external IDs found: {stats.catalog_imdb_external_ids_found}")
    print(f"- Matched IMDb ratings: {stats.matched_imdb_ratings}")
    print(f"- Rating sources inserted: {stats.rating_sources_inserted}")
    print(f"- Rating sources updated: {stats.rating_sources_updated}")
    print(f"- Inserted ratings: {stats.inserted_ratings}")
    print(f"- Updated ratings: {stats.updated_ratings}")
    print(f"- Unchanged ratings: {stats.unchanged_ratings}")
    print(f"- Skipped ratings: {stats.skipped_ratings}")
    print(f"- Unmatched catalog IMDb IDs: {stats.unmatched_catalog_imdb_ids}")
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

    print("No scraping, external API calls, backend/frontend changes, or sample_data changes were made.")


def main() -> int:
    args = parse_args()
    ratings_file = resolve_path(args.ratings_file)
    database_url = os.environ.get(DATABASE_URL_ENV)

    if not database_url:
        print(
            f"Missing {DATABASE_URL_ENV}. Export it before running this DB-aware import script."
        )
        print("No database changes were made.")
        return 1

    engine = create_engine(database_url)
    try:
        if args.apply:
            with engine.begin() as conn:
                stats = process_imdb_ratings(conn, ratings_file, apply=True)
        else:
            with engine.connect() as conn:
                stats = process_imdb_ratings(conn, ratings_file, apply=False)
    except (ImdbRatingsImportError, SQLAlchemyError) as exc:
        print(f"IMDb ratings import failed: {exc}")
        if args.apply:
            print("Transaction rolled back.")
        return 1

    print_summary(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
