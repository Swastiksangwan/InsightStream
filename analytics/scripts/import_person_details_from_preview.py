#!/usr/bin/env python3
"""
Dry-run or apply safe person detail updates from a processed preview.

This script:
- reads analytics/processed/tmdb/person_details_preview.json
- fills only missing people.biography, people.profile_url, and people.known_for_department
- never overwrites non-empty existing fields
- does not create people, person external IDs, or content_people rows
- does not call TMDb or any external API

Dry run:
    python3 analytics/scripts/import_person_details_from_preview.py

Apply:
    python3 analytics/scripts/import_person_details_from_preview.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


REPO_ROOT = Path(__file__).resolve().parents[2]
PREVIEW_PATH = (
    REPO_ROOT / "analytics" / "processed" / "tmdb" / "person_details_preview.json"
)
DATABASE_URL_ENV = "DATABASE_URL"
SAFE_UPDATE_FIELDS = ("biography", "profile_url", "known_for_department")


@dataclass
class ImportStats:
    mode: str
    db_aware: bool
    people_checked: int = 0
    biography_updates: int = 0
    profile_url_updates: int = 0
    known_for_department_updates: int = 0
    skipped_missing_biography: int = 0
    skipped_mismatch: int = 0
    skipped_missing_person: int = 0
    warnings: List[str] = field(default_factory=list)


class PersonDetailsImportError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run or apply safe person detail updates from "
            "analytics/processed/tmdb/person_details_preview.json."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write missing person fields to PostgreSQL. Without this flag, no DB writes occur.",
    )
    return parser.parse_args()


def relative_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def clean_text(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def load_preview(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise PersonDetailsImportError(
            f"Missing person details preview: {relative_path(path)}"
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PersonDetailsImportError(
            f"Malformed person details preview JSON in {relative_path(path)}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise PersonDetailsImportError("Person details preview root must be an object.")
    if data.get("source_provider") != "tmdb":
        raise PersonDetailsImportError(
            "Person details preview source_provider must be 'tmdb'."
        )
    if data.get("inspection_only") is not True:
        raise PersonDetailsImportError(
            "Person details preview must be marked inspection_only."
        )
    if not isinstance(data.get("items"), list):
        raise PersonDetailsImportError("Person details preview must contain an items list.")

    return data


def valid_preview_item(item: Any, warnings: List[str]) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        warnings.append("Skipped preview item with invalid shape.")
        return None

    person_id = item.get("person_id")
    source_name = clean_text(item.get("source_name"))
    source_person_id = clean_text(item.get("source_person_id"))
    name = clean_text(item.get("name")) or f"person_id={person_id}"

    if not isinstance(person_id, int):
        warnings.append(f"{name}: skipped because person_id is missing or invalid.")
        return None
    if source_name != "tmdb":
        warnings.append(f"{name}: skipped because source_name is not tmdb.")
        return None
    if not source_person_id:
        warnings.append(f"{name}: skipped because source_person_id is missing.")
        return None

    return item


def fetch_existing_person(connection, person_id: int, source_person_id: str):
    return connection.execute(
        text(
            """
            SELECT
                p.id,
                p.name,
                p.biography,
                p.profile_url,
                p.known_for_department,
                pei.external_id AS source_person_id
            FROM people p
            JOIN person_external_ids pei ON pei.person_id = p.id
            WHERE p.id = :person_id
              AND pei.source_name = 'tmdb';
            """
        ),
        {
            "person_id": person_id,
            "source_person_id": source_person_id,
        },
    ).mappings().first()


def planned_updates(existing_person, item: Dict[str, Any], warnings: List[str]) -> Dict[str, str]:
    updates: Dict[str, str] = {}
    name = clean_text(item.get("name")) or existing_person["name"]

    for field_name in SAFE_UPDATE_FIELDS:
        preview_value = clean_text(item.get(field_name))
        existing_value = existing_person[field_name]

        if is_empty(existing_value) and preview_value:
            updates[field_name] = preview_value
        elif not is_empty(existing_value) and preview_value and existing_value != preview_value:
            warnings.append(
                f"{name}: existing {field_name} differs from preview; preserved existing value."
            )

    return updates


def apply_updates(connection, person_id: int, updates: Dict[str, str]) -> None:
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


def increment_update_counts(stats: ImportStats, updates: Dict[str, str]) -> None:
    if "biography" in updates:
        stats.biography_updates += 1
    if "profile_url" in updates:
        stats.profile_url_updates += 1
    if "known_for_department" in updates:
        stats.known_for_department_updates += 1


def process_preview_offline(preview: Dict[str, Any]) -> ImportStats:
    stats = ImportStats(mode="DRY RUN", db_aware=False)
    stats.warnings.append(
        "DATABASE_URL is missing, so this dry run counted preview importable fields without comparing the database."
    )

    for item in preview.get("items", []):
        valid_item = valid_preview_item(item, stats.warnings)
        if valid_item is None:
            stats.skipped_mismatch += 1
            continue

        stats.people_checked += 1
        if not clean_text(valid_item.get("biography")):
            stats.skipped_missing_biography += 1
        if clean_text(valid_item.get("biography")):
            stats.biography_updates += 1
        if clean_text(valid_item.get("profile_url")):
            stats.profile_url_updates += 1
        if clean_text(valid_item.get("known_for_department")):
            stats.known_for_department_updates += 1

    return stats


def process_preview_db(
    preview: Dict[str, Any],
    database_url: str,
    apply: bool,
) -> ImportStats:
    stats = ImportStats(mode="APPLY" if apply else "DRY RUN", db_aware=True)
    engine = create_engine(database_url)
    context = engine.begin() if apply else engine.connect()

    with context as connection:
        for raw_item in preview.get("items", []):
            item = valid_preview_item(raw_item, stats.warnings)
            if item is None:
                stats.skipped_mismatch += 1
                continue

            stats.people_checked += 1
            person_id = item["person_id"]
            source_person_id = clean_text(item.get("source_person_id"))
            name = clean_text(item.get("name")) or f"person_id={person_id}"

            if not clean_text(item.get("biography")):
                stats.skipped_missing_biography += 1

            existing_person = fetch_existing_person(
                connection,
                person_id,
                source_person_id,
            )

            if not existing_person:
                stats.skipped_missing_person += 1
                stats.warnings.append(
                    f"{name}: no local person row with a TMDb external ID was found; skipped."
                )
                continue

            if existing_person["source_person_id"] != source_person_id:
                stats.skipped_mismatch += 1
                stats.warnings.append(
                    f"{name}: TMDb source_person_id mismatch; preview={source_person_id}, database={existing_person['source_person_id']}; skipped."
                )
                continue

            updates = planned_updates(existing_person, item, stats.warnings)
            increment_update_counts(stats, updates)

            if apply and updates:
                apply_updates(connection, person_id, updates)

    return stats


def print_stats(stats: ImportStats) -> None:
    mode_suffix = "DB-aware" if stats.db_aware else "offline preview"
    print(f"{stats.mode} mode ({mode_suffix})")
    print(f"People checked: {stats.people_checked}")
    print(f"Biography updates {'applied' if stats.mode == 'APPLY' else 'planned'}: {stats.biography_updates}")
    print(f"Profile URL updates {'applied' if stats.mode == 'APPLY' else 'planned'}: {stats.profile_url_updates}")
    print(
        "Known-for department updates "
        f"{'applied' if stats.mode == 'APPLY' else 'planned'}: "
        f"{stats.known_for_department_updates}"
    )
    print(f"Skipped due to missing biography: {stats.skipped_missing_biography}")
    print(f"Skipped due to mismatch: {stats.skipped_mismatch}")
    print(f"Skipped due to missing local person: {stats.skipped_missing_person}")
    print(f"Warnings: {len(stats.warnings)}")
    for warning in stats.warnings:
        print(f"- {warning}")

    if stats.mode == "APPLY":
        print("Committed successfully.")
    else:
        print("No database changes were made.")

    print("No frontend/backend/schema/sample_data files were mutated by this script.")


def main() -> int:
    args = parse_args()

    try:
        preview = load_preview(PREVIEW_PATH)
    except PersonDetailsImportError as exc:
        print(f"Error: {exc}")
        return 1

    database_url = os.getenv(DATABASE_URL_ENV)
    if args.apply and not database_url:
        print(f"Error: Missing {DATABASE_URL_ENV}. Export it before running --apply.")
        return 1

    try:
        if database_url:
            stats = process_preview_db(preview, database_url, args.apply)
        else:
            stats = process_preview_offline(preview)
    except SQLAlchemyError as exc:
        if args.apply:
            print(f"Error: person details import failed; transaction rolled back: {exc}")
            return 1
        print(f"Error: database dry run failed: {exc}")
        return 1

    print_stats(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
