#!/usr/bin/env python3
"""
Import people and credits from a processed credits preview.

This script:
- reads analytics/processed/tmdb/credits_preview.json
- runs in dry-run mode by default
- requires --apply before writing to PostgreSQL
- does not call TMDb or any external API
- does not modify backend/frontend/schema/sample_data files

Dry run:
    python3 analytics/scripts/import_people_credits_from_preview.py

Apply:
    python3 analytics/scripts/import_people_credits_from_preview.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


REPO_ROOT = Path(__file__).resolve().parents[2]
PREVIEW_PATH = REPO_ROOT / "analytics" / "processed" / "tmdb" / "credits_preview.json"
DATABASE_URL_ENV = "DATABASE_URL"
MEDIA_TYPE_TO_CONTENT_TYPE = {
    "movie": "movie",
    "tv": "series",
}
ROLE_GROUPS = ("cast", "directors", "creators", "crew")


@dataclass(frozen=True)
class RelationshipRecord:
    title: str
    tmdb_id: int
    content_type: str
    role_group: str
    source_name: str
    source_person_id: str
    source_credit_id: Optional[str]
    name: str
    profile_url: Optional[str]
    known_for_department: Optional[str]
    role_type: str
    character_name: Optional[str]
    job: Optional[str]
    department: Optional[str]
    display_order: Optional[int]


@dataclass
class ImportStats:
    mode: str
    db_aware: bool
    titles_processed: int = 0
    title_skips: int = 0
    people_insert_count: int = 0
    people_update_count: int = 0
    person_external_id_insert_count: int = 0
    content_people_insert_counts: Dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    duplicate_relationships_skipped: int = 0
    warnings: List[str] = field(default_factory=list)
    people_inserts: List[str] = field(default_factory=list)
    people_updates: List[str] = field(default_factory=list)


class ImportErrorWithMessage(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run or apply a normalized people/credits import from "
            "analytics/processed/tmdb/credits_preview.json."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write people and credits to PostgreSQL. Without this flag, no DB writes occur.",
    )
    return parser.parse_args()


def relative_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def load_preview(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ImportErrorWithMessage(f"Missing credits preview: {relative_path(path)}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ImportErrorWithMessage(
            f"Malformed credits preview JSON in {relative_path(path)}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ImportErrorWithMessage("Credits preview root must be an object.")
    if data.get("source_provider") != "tmdb":
        raise ImportErrorWithMessage("Credits preview source_provider must be 'tmdb'.")
    if data.get("inspection_only") is not True:
        raise ImportErrorWithMessage("Credits preview must be marked inspection_only.")
    if not isinstance(data.get("items"), list):
        raise ImportErrorWithMessage("Credits preview must contain an items list.")

    return data


def content_type_from_media_type(media_type: str) -> Optional[str]:
    return MEDIA_TYPE_TO_CONTENT_TYPE.get(media_type)


def clean_optional_text(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def clean_display_order(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    return None


def relationship_job(role_group: str, record: Dict[str, Any]) -> Optional[str]:
    if role_group == "cast":
        return clean_optional_text(record.get("job"))
    if role_group == "directors":
        return clean_optional_text(record.get("job")) or "Director"
    if role_group == "creators":
        return clean_optional_text(record.get("job")) or "Creator"
    return clean_optional_text(record.get("job"))


def iter_relationship_records(
    preview: Dict[str, Any],
    warnings: List[str],
) -> Iterable[RelationshipRecord]:
    items = preview.get("items", [])

    for item_index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            warnings.append(f"Preview item {item_index} has invalid shape; skipped.")
            continue

        title = clean_optional_text(item.get("title")) or f"<item {item_index}>"
        tmdb_id = item.get("tmdb_id")
        media_type = item.get("media_type")
        content_type = content_type_from_media_type(media_type)

        if not isinstance(tmdb_id, int):
            warnings.append(f"{title}: missing or invalid tmdb_id; title skipped.")
            continue
        if content_type is None:
            warnings.append(f"{title}: unsupported media_type {media_type!r}; title skipped.")
            continue

        credits = item.get("credits")
        if not isinstance(credits, dict):
            warnings.append(f"{title}: missing credits object; title skipped.")
            continue

        for role_group in ROLE_GROUPS:
            records = credits.get(role_group, [])
            if not isinstance(records, list):
                warnings.append(f"{title}: credits.{role_group} is not a list; skipped.")
                continue

            for record_index, raw_record in enumerate(records, start=1):
                if not isinstance(raw_record, dict):
                    warnings.append(
                        f"{title}: {role_group} record {record_index} has invalid shape; skipped."
                    )
                    continue

                source_name = clean_optional_text(raw_record.get("source_name")) or "tmdb"
                source_person_id = clean_optional_text(raw_record.get("source_person_id"))
                name = clean_optional_text(raw_record.get("name"))
                role_type = clean_optional_text(raw_record.get("role_type"))

                if not source_person_id:
                    warnings.append(
                        f"{title}: skipped {name or '<unknown>'} because source_person_id is missing."
                    )
                    continue
                if not name:
                    warnings.append(
                        f"{title}: skipped source person {source_person_id} because name is missing."
                    )
                    continue
                if role_type not in {"cast", "director", "creator", "crew"}:
                    warnings.append(
                        f"{title}: skipped {name} because role_type {role_type!r} is unsupported."
                    )
                    continue

                yield RelationshipRecord(
                    title=title,
                    tmdb_id=tmdb_id,
                    content_type=content_type,
                    role_group=role_group,
                    source_name=source_name,
                    source_person_id=source_person_id,
                    source_credit_id=clean_optional_text(raw_record.get("source_credit_id")),
                    name=name,
                    profile_url=clean_optional_text(raw_record.get("profile_url")),
                    known_for_department=clean_optional_text(
                        raw_record.get("known_for_department")
                    ),
                    role_type=role_type,
                    character_name=clean_optional_text(raw_record.get("character_name")),
                    job=relationship_job(role_group, raw_record),
                    department=clean_optional_text(raw_record.get("department")),
                    display_order=clean_display_order(raw_record.get("display_order")),
                )


def person_key(record: RelationshipRecord) -> Tuple[str, str]:
    return (record.source_name, record.source_person_id)


def relationship_key(
    content_id_or_key: Any,
    person_id_or_key: Any,
    record: RelationshipRecord,
) -> Tuple[Any, Any, str, str, str, str]:
    return (
        content_id_or_key,
        person_id_or_key,
        record.role_type,
        record.character_name or "",
        record.job or "",
        record.source_credit_id or "",
    )


def build_offline_stats(preview: Dict[str, Any], warning_prefix: Optional[str] = None) -> ImportStats:
    warnings: List[str] = []
    records = list(iter_relationship_records(preview, warnings))
    stats = ImportStats(mode="DRY RUN", db_aware=False)
    stats.titles_processed = len(preview.get("items", []))

    if warning_prefix:
        stats.warnings.append(warning_prefix)
    stats.warnings.extend(warnings)

    unique_people = {}
    unique_relationships = set()
    for record in records:
        unique_people.setdefault(person_key(record), record)
        key = relationship_key(record.tmdb_id, person_key(record), record)
        if key in unique_relationships:
            stats.duplicate_relationships_skipped += 1
            continue
        unique_relationships.add(key)
        stats.content_people_insert_counts[record.role_type] += 1

    stats.people_insert_count = len(unique_people)
    stats.person_external_id_insert_count = len(unique_people)
    stats.people_inserts = [
        f"{record.name} ({source_name}:{source_person_id})"
        for (source_name, source_person_id), record in sorted(unique_people.items())
    ]
    return stats


def fetch_content_row(connection, tmdb_id: int, content_type: str):
    return connection.execute(
        text(
            """
            SELECT id, title, content_type
            FROM content
            WHERE tmdb_id = :tmdb_id
              AND content_type = :content_type;
            """
        ),
        {
            "tmdb_id": tmdb_id,
            "content_type": content_type,
        },
    ).mappings().first()


def fetch_person_by_external_id(connection, source_name: str, external_id: str):
    return connection.execute(
        text(
            """
            SELECT
                p.id,
                p.name,
                p.profile_url,
                p.known_for_department
            FROM person_external_ids pei
            JOIN people p ON p.id = pei.person_id
            WHERE pei.source_name = :source_name
              AND pei.external_id = :external_id;
            """
        ),
        {
            "source_name": source_name,
            "external_id": external_id,
        },
    ).mappings().first()


def insert_person(connection, record: RelationshipRecord) -> int:
    row = connection.execute(
        text(
            """
            INSERT INTO people (
                name,
                profile_url,
                known_for_department,
                biography
            )
            VALUES (
                :name,
                :profile_url,
                :known_for_department,
                NULL
            )
            RETURNING id;
            """
        ),
        {
            "name": record.name,
            "profile_url": record.profile_url,
            "known_for_department": record.known_for_department,
        },
    ).mappings().first()
    return row["id"]


def insert_person_external_id(
    connection,
    person_id: int,
    record: RelationshipRecord,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO person_external_ids (
                person_id,
                source_name,
                external_id,
                source_url
            )
            VALUES (
                :person_id,
                :source_name,
                :external_id,
                NULL
            )
            ON CONFLICT ON CONSTRAINT uq_person_external_ids_source_external_id
            DO NOTHING;
            """
        ),
        {
            "person_id": person_id,
            "source_name": record.source_name,
            "external_id": record.source_person_id,
        },
    )


def missing_person_updates(existing_person, record: RelationshipRecord) -> Dict[str, str]:
    updates: Dict[str, str] = {}
    if not existing_person["profile_url"] and record.profile_url:
        updates["profile_url"] = record.profile_url
    if not existing_person["known_for_department"] and record.known_for_department:
        updates["known_for_department"] = record.known_for_department
    return updates


def update_missing_person_fields(
    connection,
    person_id: int,
    updates: Dict[str, str],
) -> None:
    if not updates:
        return

    set_clauses = []
    params: Dict[str, Any] = {"person_id": person_id}
    for field_name, value in updates.items():
        set_clauses.append(f"{field_name} = :{field_name}")
        params[field_name] = value
    set_clauses.append("updated_at = CURRENT_TIMESTAMP")

    connection.execute(
        text(
            f"""
            UPDATE people
            SET {", ".join(set_clauses)}
            WHERE id = :person_id;
            """
        ),
        params,
    )


def relationship_exists(
    connection,
    content_id: int,
    person_id: int,
    record: RelationshipRecord,
) -> bool:
    row = connection.execute(
        text(
            """
            SELECT id
            FROM content_people
            WHERE content_id = :content_id
              AND person_id = :person_id
              AND role_type = :role_type
              AND COALESCE(character_name, '') = :character_name
              AND COALESCE(job, '') = :job
              AND COALESCE(source_credit_id, '') = :source_credit_id
            LIMIT 1;
            """
        ),
        {
            "content_id": content_id,
            "person_id": person_id,
            "role_type": record.role_type,
            "character_name": record.character_name or "",
            "job": record.job or "",
            "source_credit_id": record.source_credit_id or "",
        },
    ).mappings().first()
    return row is not None


def insert_relationship(
    connection,
    content_id: int,
    person_id: int,
    record: RelationshipRecord,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO content_people (
                content_id,
                person_id,
                role_type,
                character_name,
                job,
                department,
                display_order,
                source_name,
                source_credit_id
            )
            VALUES (
                :content_id,
                :person_id,
                :role_type,
                :character_name,
                :job,
                :department,
                :display_order,
                :source_name,
                :source_credit_id
            );
            """
        ),
        {
            "content_id": content_id,
            "person_id": person_id,
            "role_type": record.role_type,
            "character_name": record.character_name,
            "job": record.job,
            "department": record.department,
            "display_order": record.display_order,
            "source_name": record.source_name,
            "source_credit_id": record.source_credit_id,
        },
    )


def process_db_import(preview: Dict[str, Any], database_url: str, apply: bool) -> ImportStats:
    stats = ImportStats(mode="APPLY" if apply else "DRY RUN", db_aware=True)
    warnings: List[str] = []
    records = list(iter_relationship_records(preview, warnings))
    stats.warnings.extend(warnings)
    stats.titles_processed = len(preview.get("items", []))

    content_cache: Dict[Tuple[int, str], Optional[int]] = {}
    person_cache: Dict[Tuple[str, str], Tuple[Optional[int], Optional[Dict[str, Any]]]] = {}
    planned_new_people: Dict[Tuple[str, str], RelationshipRecord] = {}
    planned_person_updates = set()
    planned_relationships = set()

    engine = create_engine(database_url)
    context = engine.begin() if apply else engine.connect()

    with context as connection:
        for record in records:
            content_key = (record.tmdb_id, record.content_type)
            if content_key not in content_cache:
                content_row = fetch_content_row(
                    connection,
                    record.tmdb_id,
                    record.content_type,
                )
                if not content_row:
                    stats.title_skips += 1
                    stats.warnings.append(
                        f"{record.title}: no matching content row for tmdb_id={record.tmdb_id}, content_type={record.content_type}."
                    )
                    content_cache[content_key] = None
                else:
                    content_cache[content_key] = content_row["id"]

            content_id = content_cache[content_key]
            if content_id is None:
                continue

            key = person_key(record)
            if key not in person_cache:
                person_row = fetch_person_by_external_id(
                    connection,
                    record.source_name,
                    record.source_person_id,
                )
                if person_row:
                    person_cache[key] = (person_row["id"], dict(person_row))
                    if person_row["name"] != record.name:
                        stats.warnings.append(
                            f"{record.name}: existing person name differs for {record.source_name}:{record.source_person_id} ({person_row['name']})."
                        )
                else:
                    person_cache[key] = (None, None)

            existing_person_id, existing_person = person_cache[key]
            person_id_or_key: Any = existing_person_id if existing_person_id else key

            if existing_person_id:
                updates = missing_person_updates(existing_person, record)
                update_key = (key, tuple(sorted(updates)))
                if updates and update_key not in planned_person_updates:
                    planned_person_updates.add(update_key)
                    if apply:
                        update_missing_person_fields(connection, existing_person_id, updates)
                        person_cache[key] = (
                            existing_person_id,
                            {**existing_person, **updates},
                        )
                    stats.people_update_count += 1
                    stats.people_updates.append(
                        f"{record.name} ({record.source_name}:{record.source_person_id}) -> {', '.join(sorted(updates))}"
                    )
                elif existing_person and existing_person["profile_url"] and record.profile_url:
                    if existing_person["profile_url"] != record.profile_url:
                        stats.warnings.append(
                            f"{record.name}: existing profile_url differs; preserved existing value."
                        )
            else:
                if key not in planned_new_people:
                    planned_new_people[key] = record
                    stats.people_insert_count += 1
                    stats.person_external_id_insert_count += 1
                    stats.people_inserts.append(
                        f"{record.name} ({record.source_name}:{record.source_person_id})"
                    )
                    if apply:
                        inserted_person_id = insert_person(connection, record)
                        insert_person_external_id(connection, inserted_person_id, record)
                        person_cache[key] = (
                            inserted_person_id,
                            {
                                "id": inserted_person_id,
                                "name": record.name,
                                "profile_url": record.profile_url,
                                "known_for_department": record.known_for_department,
                            },
                        )
                        person_id_or_key = inserted_person_id
                elif apply:
                    inserted_person_id, _ = person_cache[key]
                    person_id_or_key = inserted_person_id

            if apply and not isinstance(person_id_or_key, int):
                existing_person_id, _ = person_cache[key]
                if not existing_person_id:
                    raise ImportErrorWithMessage(
                        f"Could not resolve person_id for {record.name} during apply."
                    )
                person_id_or_key = existing_person_id

            planned_key = relationship_key(content_id, person_id_or_key, record)
            if planned_key in planned_relationships:
                stats.duplicate_relationships_skipped += 1
                continue
            planned_relationships.add(planned_key)

            if isinstance(person_id_or_key, int) and relationship_exists(
                connection,
                content_id,
                person_id_or_key,
                record,
            ):
                stats.duplicate_relationships_skipped += 1
                continue

            stats.content_people_insert_counts[record.role_type] += 1
            if apply:
                insert_relationship(connection, content_id, person_id_or_key, record)

    return stats


def print_stats(stats: ImportStats) -> None:
    mode_suffix = "DB-aware" if stats.db_aware else "offline preview"
    print(f"{stats.mode} mode ({mode_suffix})")
    print(f"Titles processed: {stats.titles_processed}")
    print(f"Title skips: {stats.title_skips}")

    if stats.mode == "APPLY":
        print(f"People inserted: {stats.people_insert_count}")
        print(f"People updated: {stats.people_update_count}")
        print(f"Person external IDs inserted: {stats.person_external_id_insert_count}")
        print("Content_people inserted:")
    else:
        print(f"People to insert: {stats.people_insert_count}")
        print(f"People to update missing profile/department: {stats.people_update_count}")
        print(f"Person external IDs to insert: {stats.person_external_id_insert_count}")
        print("Content_people relationships to insert:")

    for role_type in ("cast", "creator", "director", "crew"):
        print(f"- {role_type}: {stats.content_people_insert_counts.get(role_type, 0)}")

    print(f"Duplicate relationships skipped: {stats.duplicate_relationships_skipped}")
    print(f"Warnings: {len(stats.warnings)}")
    for warning in stats.warnings:
        print(f"- {warning}")

    if not stats.db_aware:
        print(
            "DATABASE_URL was not used, so this dry run estimated inserts from the preview only."
        )

    print("No backend/frontend/schema/sample_data files were mutated by this script.")


def main() -> int:
    args = parse_args()

    try:
        preview = load_preview(PREVIEW_PATH)
    except ImportErrorWithMessage as exc:
        print(f"Error: {exc}")
        return 1

    database_url = os.getenv(DATABASE_URL_ENV)
    if args.apply and not database_url:
        print(f"Error: Missing {DATABASE_URL_ENV}. Export it before running --apply.")
        return 1

    if not database_url:
        stats = build_offline_stats(preview)
        print_stats(stats)
        return 0

    try:
        stats = process_db_import(preview, database_url, args.apply)
    except SQLAlchemyError as exc:
        if args.apply:
            print(f"Error: database import failed; transaction rolled back: {exc}")
            return 1
        stats = build_offline_stats(
            preview,
            warning_prefix=(
                f"Database dry-run comparison failed, so offline preview counts were used: {exc}"
            ),
        )
    except ImportErrorWithMessage as exc:
        print(f"Error: {exc}")
        return 1

    print_stats(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
