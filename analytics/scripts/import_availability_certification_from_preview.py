#!/usr/bin/env python3
"""
Dry-run or apply availability/certification metadata from a processed preview.

This script:
- reads analytics/processed/tmdb/availability_certification_preview.json
- requires DATABASE_URL for dry-run comparison and apply mode
- runs in dry-run mode by default
- requires --apply before writing to PostgreSQL
- does not call TMDb or any external API
- does not modify backend/frontend/schema/sample_data files

Dry run:
    python3 analytics/scripts/import_availability_certification_from_preview.py

Apply:
    python3 analytics/scripts/import_availability_certification_from_preview.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PREVIEW_PATH = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "tmdb"
    / "availability_certification_preview.json"
)
DATABASE_URL_ENV = "DATABASE_URL"
PLATFORM_TYPE_DEFAULT = "ott"
ALLOWED_AVAILABILITY_TYPES = {"streaming", "rent", "buy", "ads", "free"}
AVAILABILITY_TYPE_ALIASES = {
    "flatrate": "streaming",
    "stream": "streaming",
    "streaming": "streaming",
    "rent": "rent",
    "buy": "buy",
    "ads": "ads",
    "free": "free",
}


@dataclass
class ImportStats:
    mode: str
    preview_path: str
    items_processed: int = 0
    items_skipped: int = 0
    content_matched: int = 0
    platforms_inserted: int = 0
    availability_inserted: int = 0
    availability_existing_skipped: int = 0
    certifications_inserted: int = 0
    certifications_existing_skipped: int = 0
    age_rating_updates: int = 0
    age_rating_unchanged: int = 0
    age_rating_conflicts_preserved: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ContentMatch:
    content_id: int
    title: str
    content_type: str
    age_rating: str | None


class AvailabilityCertificationImportError(RuntimeError):
    pass


class ImportContext:
    def __init__(self, apply: bool) -> None:
        self.apply = apply
        self.platform_cache: dict[str, int | str] = {}
        self.planned_platform_names: set[str] = set()
        self.planned_availability_keys: set[tuple[Any, ...]] = set()
        self.planned_certification_keys: set[tuple[Any, ...]] = set()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run or apply region-aware availability/certification metadata "
            "from analytics/processed/tmdb/availability_certification_preview.json."
        )
    )
    parser.add_argument(
        "--preview",
        default=str(DEFAULT_PREVIEW_PATH.relative_to(REPO_ROOT)),
        help=(
            "Path to processed availability/certification preview. Defaults to "
            f"{DEFAULT_PREVIEW_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write availability/certification metadata to PostgreSQL.",
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


def clean_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def normalize_availability_type(value: Any) -> str | None:
    text_value = clean_text(value)
    if not text_value:
        return None
    return AVAILABILITY_TYPE_ALIASES.get(text_value.lower())


def load_preview(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AvailabilityCertificationImportError(
            f"Missing availability/certification preview: {relative_path(path)}"
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AvailabilityCertificationImportError(
            f"Malformed preview JSON in {relative_path(path)}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise AvailabilityCertificationImportError("Preview root must be an object.")
    if data.get("inspection_only") is not True:
        raise AvailabilityCertificationImportError(
            "Preview must be marked inspection_only."
        )
    if not isinstance(data.get("items"), list):
        raise AvailabilityCertificationImportError("Preview must contain an items array.")

    return data


def validate_preview_item(item: Any, index: int) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(item, dict):
        return None, [f"Item #{index}: expected object; skipped."]

    warnings: list[str] = []
    title = clean_text(item.get("title"))
    content_type = clean_text(item.get("content_type"))
    source_name = clean_text(item.get("source_name"))
    source_id = clean_text(item.get("source_id"))

    if not title:
        warnings.append(f"Item #{index}: missing title.")
    if content_type not in {"movie", "series"}:
        warnings.append(f"{title or f'Item #{index}'}: content_type must be movie or series.")
    if not source_name:
        warnings.append(f"{title or f'Item #{index}'}: missing source_name.")
    if not source_id:
        warnings.append(f"{title or f'Item #{index}'}: missing source_id.")
    if not isinstance(item.get("availability", []), list):
        warnings.append(f"{title or f'Item #{index}'}: availability must be a list.")
    if not isinstance(item.get("certifications", []), list):
        warnings.append(f"{title or f'Item #{index}'}: certifications must be a list.")

    if warnings:
        return None, warnings

    return item, []


def find_content(conn: Any, item: dict[str, Any], stats: ImportStats) -> ContentMatch | None:
    source_name = clean_text(item.get("source_name"))
    source_id = clean_text(item.get("source_id"))
    title = clean_text(item.get("title"))
    content_type = clean_text(item.get("content_type"))

    row = conn.execute(
        text(
            """
            SELECT
                c.id,
                c.title,
                c.content_type,
                c.age_rating
            FROM external_ids ei
            JOIN content c ON c.id = ei.content_id
            WHERE LOWER(ei.source_name) = LOWER(:source_name)
              AND ei.external_id = :source_id
            LIMIT 1;
            """
        ),
        {"source_name": source_name, "source_id": source_id},
    ).mappings().first()

    if row is None:
        row = conn.execute(
            text(
                """
                SELECT
                    id,
                    title,
                    content_type,
                    age_rating
                FROM content
                WHERE title = :title
                  AND content_type = :content_type
                LIMIT 1;
                """
            ),
            {"title": title, "content_type": content_type},
        ).mappings().first()

        if row is not None:
            stats.warnings.append(
                f"{title}: matched content by title/content_type because external ID {source_name}:{source_id} was not found."
            )

    if row is None:
        stats.warnings.append(
            f"{title}: no content row found for {source_name}:{source_id}; skipped."
        )
        return None

    return ContentMatch(
        content_id=row["id"],
        title=row["title"],
        content_type=row["content_type"],
        age_rating=row["age_rating"],
    )


def platform_cache_key(name: str) -> str:
    return name.strip().lower()


def find_or_create_platform(
    conn: Any,
    ctx: ImportContext,
    stats: ImportStats,
    provider_name: str,
) -> int | str:
    key = platform_cache_key(provider_name)
    if key in ctx.platform_cache:
        return ctx.platform_cache[key]

    row = conn.execute(
        text(
            """
            SELECT id
            FROM platforms
            WHERE LOWER(name) = LOWER(:name)
            LIMIT 1;
            """
        ),
        {"name": provider_name},
    ).mappings().first()

    if row is not None:
        ctx.platform_cache[key] = row["id"]
        return row["id"]

    if ctx.apply:
        inserted = conn.execute(
            text(
                """
                INSERT INTO platforms (name, platform_type)
                VALUES (:name, :platform_type)
                RETURNING id;
                """
            ),
            {"name": provider_name, "platform_type": PLATFORM_TYPE_DEFAULT},
        ).mappings().first()
        platform_id = inserted["id"]
    else:
        platform_id = f"new-platform:{key}"

    ctx.platform_cache[key] = platform_id
    if key not in ctx.planned_platform_names:
        stats.platforms_inserted += 1
        ctx.planned_platform_names.add(key)
    return platform_id


def availability_exists(
    conn: Any,
    content_id: int,
    platform_id: int,
    availability_type: str,
    region_code: str,
    source_name: str,
) -> bool:
    row = conn.execute(
        text(
            """
            SELECT id
            FROM content_availability
            WHERE content_id = :content_id
              AND platform_id = :platform_id
              AND availability_type = :availability_type
              AND region_code = :region_code
              AND source_name = :source_name
            LIMIT 1;
            """
        ),
        {
            "content_id": content_id,
            "platform_id": platform_id,
            "availability_type": availability_type,
            "region_code": region_code,
            "source_name": source_name,
        },
    ).first()
    return row is not None


def process_availability_rows(
    conn: Any,
    ctx: ImportContext,
    stats: ImportStats,
    content: ContentMatch,
    item: dict[str, Any],
) -> None:
    rows = item.get("availability", [])
    if not isinstance(rows, list):
        stats.warnings.append(f"{content.title}: availability is not a list; skipped.")
        return

    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            stats.warnings.append(
                f"{content.title}: availability row #{index} is not an object; skipped."
            )
            continue

        provider_name = clean_text(row.get("provider_name"))
        availability_type = normalize_availability_type(row.get("availability_type"))
        region_code = clean_text(row.get("region_code"))
        source_name = clean_text(row.get("source_name")) or clean_text(item.get("source_name"))
        source_provider_id = clean_text(row.get("source_provider_id"))
        display_priority = clean_int(row.get("display_priority"))

        if not provider_name:
            stats.warnings.append(
                f"{content.title}: availability row #{index} missing provider_name; skipped."
            )
            continue
        if not availability_type or availability_type not in ALLOWED_AVAILABILITY_TYPES:
            stats.warnings.append(
                f"{content.title}: availability row #{index} has unknown availability_type {row.get('availability_type')!r}; skipped."
            )
            continue
        if not region_code:
            stats.warnings.append(
                f"{content.title}: availability row #{index} missing region_code; skipped."
            )
            continue
        if not source_name:
            stats.warnings.append(
                f"{content.title}: availability row #{index} missing source_name; skipped."
            )
            continue

        platform_id = find_or_create_platform(conn, ctx, stats, provider_name)
        planned_key = (
            content.content_id,
            platform_id,
            availability_type,
            region_code,
            source_name,
        )

        if planned_key in ctx.planned_availability_keys:
            stats.availability_existing_skipped += 1
            continue

        if isinstance(platform_id, int) and availability_exists(
            conn,
            content.content_id,
            platform_id,
            availability_type,
            region_code,
            source_name,
        ):
            stats.availability_existing_skipped += 1
            continue

        if ctx.apply:
            conn.execute(
                text(
                    """
                    INSERT INTO content_availability (
                        content_id,
                        platform_id,
                        availability_type,
                        region_code,
                        source_name,
                        source_provider_id,
                        display_priority
                    )
                    VALUES (
                        :content_id,
                        :platform_id,
                        :availability_type,
                        :region_code,
                        :source_name,
                        :source_provider_id,
                        :display_priority
                    )
                    ON CONFLICT ON CONSTRAINT uq_content_availability_content_platform_type_region_source
                    DO NOTHING;
                    """
                ),
                {
                    "content_id": content.content_id,
                    "platform_id": platform_id,
                    "availability_type": availability_type,
                    "region_code": region_code,
                    "source_name": source_name,
                    "source_provider_id": source_provider_id,
                    "display_priority": display_priority,
                },
            )

        ctx.planned_availability_keys.add(planned_key)
        stats.availability_inserted += 1


def certification_exists(
    conn: Any,
    content_id: int,
    country_code: str,
    rating_system: str | None,
    source_name: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        text(
            """
            SELECT id, certification
            FROM content_certifications
            WHERE content_id = :content_id
              AND country_code = :country_code
              AND rating_system IS NOT DISTINCT FROM :rating_system
              AND source_name = :source_name
            LIMIT 1;
            """
        ),
        {
            "content_id": content_id,
            "country_code": country_code,
            "rating_system": rating_system,
            "source_name": source_name,
        },
    ).mappings().first()
    return dict(row) if row is not None else None


def process_certification_rows(
    conn: Any,
    ctx: ImportContext,
    stats: ImportStats,
    content: ContentMatch,
    item: dict[str, Any],
) -> None:
    rows = item.get("certifications", [])
    if not isinstance(rows, list):
        stats.warnings.append(f"{content.title}: certifications is not a list; skipped.")
        return

    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            stats.warnings.append(
                f"{content.title}: certification row #{index} is not an object; skipped."
            )
            continue

        certification = clean_text(row.get("certification"))
        country_code = clean_text(row.get("country_code"))
        rating_system = clean_text(row.get("rating_system"))
        source_name = clean_text(row.get("source_name")) or clean_text(item.get("source_name"))
        source_priority = clean_int(row.get("source_priority"))
        notes = clean_text(row.get("notes"))

        if not certification:
            stats.warnings.append(
                f"{content.title}: certification row #{index} has empty certification; skipped."
            )
            continue
        if not country_code:
            stats.warnings.append(
                f"{content.title}: certification row #{index} missing country_code; skipped."
            )
            continue
        if not source_name:
            stats.warnings.append(
                f"{content.title}: certification row #{index} missing source_name; skipped."
            )
            continue

        planned_key = (
            content.content_id,
            country_code,
            rating_system or "",
            source_name,
        )
        if planned_key in ctx.planned_certification_keys:
            stats.certifications_existing_skipped += 1
            continue

        existing = certification_exists(
            conn,
            content.content_id,
            country_code,
            rating_system,
            source_name,
        )
        if existing is not None:
            stats.certifications_existing_skipped += 1
            if existing.get("certification") != certification:
                stats.warnings.append(
                    f"{content.title}: certification conflict for {country_code}/{rating_system or 'unknown'}; existing {existing.get('certification')!r} preserved over preview {certification!r}."
                )
            continue

        if ctx.apply:
            conn.execute(
                text(
                    """
                    INSERT INTO content_certifications (
                        content_id,
                        certification,
                        country_code,
                        rating_system,
                        source_name,
                        source_priority,
                        notes
                    )
                    VALUES (
                        :content_id,
                        :certification,
                        :country_code,
                        :rating_system,
                        :source_name,
                        :source_priority,
                        :notes
                    )
                    ON CONFLICT ON CONSTRAINT uq_content_certifications_content_country_system_source
                    DO NOTHING;
                    """
                ),
                {
                    "content_id": content.content_id,
                    "certification": certification,
                    "country_code": country_code,
                    "rating_system": rating_system,
                    "source_name": source_name,
                    "source_priority": source_priority,
                    "notes": notes,
                },
            )

        ctx.planned_certification_keys.add(planned_key)
        stats.certifications_inserted += 1


def process_age_rating(
    conn: Any,
    ctx: ImportContext,
    stats: ImportStats,
    content: ContentMatch,
    item: dict[str, Any],
) -> None:
    chosen = item.get("chosen_certification")
    if not isinstance(chosen, dict):
        return

    certification = clean_text(chosen.get("certification"))
    if not certification:
        return

    if is_empty(content.age_rating):
        if ctx.apply:
            conn.execute(
                text(
                    """
                    UPDATE content
                    SET age_rating = :age_rating,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :content_id;
                    """
                ),
                {
                    "age_rating": certification,
                    "content_id": content.content_id,
                },
            )
        stats.age_rating_updates += 1
        return

    if content.age_rating == certification:
        stats.age_rating_unchanged += 1
        return

    stats.age_rating_conflicts_preserved += 1
    stats.warnings.append(
        f"{content.title}: existing age_rating {content.age_rating!r} preserved over chosen certification {certification!r}."
    )


def process_preview(conn: Any, preview: dict[str, Any], apply: bool, stats: ImportStats) -> None:
    ctx = ImportContext(apply=apply)

    for index, raw_item in enumerate(preview.get("items", []), start=1):
        item, validation_warnings = validate_preview_item(raw_item, index)
        if item is None:
            stats.items_skipped += 1
            stats.warnings.extend(validation_warnings)
            continue

        content = find_content(conn, item, stats)
        if content is None:
            stats.items_skipped += 1
            continue

        stats.items_processed += 1
        stats.content_matched += 1
        process_availability_rows(conn, ctx, stats, content, item)
        process_certification_rows(conn, ctx, stats, content, item)
        process_age_rating(conn, ctx, stats, content, item)


def print_summary(stats: ImportStats) -> None:
    print("\nSummary")
    print(f"Mode: {stats.mode}")
    print(f"Preview path: {stats.preview_path}")
    print(f"Items processed: {stats.items_processed}")
    print(f"Items skipped: {stats.items_skipped}")
    print(f"Content matched: {stats.content_matched}")
    print(f"Platforms inserted: {stats.platforms_inserted}")
    print(f"Availability rows inserted: {stats.availability_inserted}")
    print(f"Availability rows existing/skipped: {stats.availability_existing_skipped}")
    print(f"Certifications inserted: {stats.certifications_inserted}")
    print(f"Certifications existing/skipped: {stats.certifications_existing_skipped}")
    print(f"content.age_rating updates: {stats.age_rating_updates}")
    print(f"content.age_rating unchanged: {stats.age_rating_unchanged}")
    print(
        "content.age_rating conflicts preserved: "
        f"{stats.age_rating_conflicts_preserved}"
    )
    print(f"Warnings: {len(stats.warnings)}")
    if stats.warnings:
        for warning in stats.warnings[:12]:
            print(f"  - {warning}")
        if len(stats.warnings) > 12:
            print(f"  ... {len(stats.warnings) - 12} more warnings")
    print("No backend, frontend, schema, or sample_data files were changed.")


def main() -> int:
    args = parse_args()
    preview_path = resolve_path(args.preview)
    mode = "APPLY" if args.apply else "DRY RUN"
    stats = ImportStats(mode=mode, preview_path=relative_path(preview_path))

    database_url = os.environ.get(DATABASE_URL_ENV)
    if not database_url:
        print(
            f"Missing {DATABASE_URL_ENV}. Export it before running this importer.",
            file=sys.stderr,
        )
        return 1

    try:
        preview = load_preview(preview_path)
    except AvailabilityCertificationImportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    engine = create_engine(database_url)

    try:
        if args.apply:
            with engine.begin() as conn:
                process_preview(conn, preview, apply=True, stats=stats)
        else:
            with engine.connect() as conn:
                process_preview(conn, preview, apply=False, stats=stats)
    except SQLAlchemyError as exc:
        print(f"Database error: {exc}", file=sys.stderr)
        return 1

    print_summary(stats)
    if args.apply:
        print("Database changes were committed successfully.")
    else:
        print("Dry run only. No database changes were made.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
