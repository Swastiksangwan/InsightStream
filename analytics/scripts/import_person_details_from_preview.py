#!/usr/bin/env python3
"""
Dry-run or apply safe person detail updates from a processed preview.

This script:
- reads analytics/processed/tmdb/person_details_preview.json
- fills only missing safe person fields such as biography, profile URL,
  known-for department, birthday, and place of birth
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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


REPO_ROOT = Path(__file__).resolve().parents[2]
PREVIEW_PATH = (
    REPO_ROOT / "analytics" / "processed" / "tmdb" / "person_details_preview.json"
)
DATABASE_URL_ENV = "DATABASE_URL"
SAFE_UPDATE_FIELDS = (
    "biography",
    "profile_url",
    "known_for_department",
    "birthday",
    "place_of_birth",
)
DATE_UPDATE_FIELDS = {"birthday"}
MAX_ROW_REPORT_ITEMS = 50
MAX_DISPLAY_VALUE_LENGTH = 120


@dataclass
class ImportStats:
    mode: str
    db_aware: bool
    people_checked: int = 0
    biography_updates: int = 0
    profile_url_updates: int = 0
    known_for_department_updates: int = 0
    birthday_updates: int = 0
    place_of_birth_updates: int = 0
    skipped_missing_biography: int = 0
    skipped_mismatch: int = 0
    skipped_missing_person: int = 0
    warnings: List[str] = field(default_factory=list)
    person_update_rows: List[Dict[str, Any]] = field(default_factory=list)


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


def display_value(value: Any) -> str:
    if value is None or value == "":
        return "<empty>"
    text = str(value)
    if len(text) <= MAX_DISPLAY_VALUE_LENGTH:
        return text
    return f"{text[:MAX_DISPLAY_VALUE_LENGTH - 1]}…"


def clean_date(value: Any) -> Optional[str]:
    text_value = clean_text(value)
    if not text_value:
        return None
    try:
        return datetime.strptime(text_value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def clean_preview_field(
    field_name: str,
    value: Any,
    warnings: List[str],
    name: str,
) -> Optional[str]:
    if field_name in DATE_UPDATE_FIELDS:
        cleaned = clean_date(value)
        if clean_text(value) and cleaned is None:
            warnings.append(f"{name}: preview {field_name} is not a valid YYYY-MM-DD date; skipped.")
        return cleaned
    return clean_text(value)


def comparable_existing_value(field_name: str, value: Any) -> Any:
    if field_name in DATE_UPDATE_FIELDS and value is not None:
        return str(value)
    return value


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
                p.birthday,
                p.place_of_birth,
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
        preview_value = clean_preview_field(field_name, item.get(field_name), warnings, name)
        existing_value = existing_person[field_name]
        existing_comparable = comparable_existing_value(field_name, existing_value)

        if is_empty(existing_value) and preview_value:
            updates[field_name] = preview_value
        elif (
            not is_empty(existing_value)
            and preview_value
            and existing_comparable != preview_value
        ):
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
    if "birthday" in updates:
        stats.birthday_updates += 1
    if "place_of_birth" in updates:
        stats.place_of_birth_updates += 1


def record_person_update_row(stats: ImportStats, existing_person, updates: Dict[str, str]) -> None:
    if not updates:
        return

    stats.person_update_rows.append(
        {
            "person_id": existing_person["id"],
            "name": existing_person["name"],
            "fields": [
                {
                    "field_name": field_name,
                    "old_value": existing_person[field_name],
                    "new_value": updates[field_name],
                }
                for field_name in updates
            ],
        }
    )


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
        if clean_preview_field("birthday", valid_item.get("birthday"), stats.warnings, clean_text(valid_item.get("name")) or "person"):
            stats.birthday_updates += 1
        if clean_text(valid_item.get("place_of_birth")):
            stats.place_of_birth_updates += 1

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
            record_person_update_row(stats, existing_person, updates)

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
    print(f"Birthday updates {'applied' if stats.mode == 'APPLY' else 'planned'}: {stats.birthday_updates}")
    print(
        "Place-of-birth updates "
        f"{'applied' if stats.mode == 'APPLY' else 'planned'}: "
        f"{stats.place_of_birth_updates}"
    )
    print(f"Skipped due to missing biography: {stats.skipped_missing_biography}")
    print(f"Skipped due to mismatch: {stats.skipped_mismatch}")
    print(f"Skipped due to missing local person: {stats.skipped_missing_person}")
    print_person_update_rows(stats)
    print(f"Warnings: {len(stats.warnings)}")
    for warning in stats.warnings:
        print(f"- {warning}")

    if stats.mode == "APPLY":
        print("Committed successfully.")
    else:
        print("No database changes were made.")

    print("No frontend/backend/schema/sample_data files were mutated by this script.")


def print_person_update_rows(stats: ImportStats) -> None:
    if not stats.person_update_rows:
        return

    heading = "Updated person rows:" if stats.mode == "APPLY" else "Would update person rows:"
    print(heading)

    for row in stats.person_update_rows[:MAX_ROW_REPORT_ITEMS]:
        print(f"- {row['name']} [id={row['person_id']}]")
        for field in row["fields"]:
            print(
                f"  - {field['field_name']}: "
                f"{display_value(field['old_value'])} -> {display_value(field['new_value'])}"
            )

    remaining = len(stats.person_update_rows) - MAX_ROW_REPORT_ITEMS
    if remaining > 0:
        print(f"... and {remaining} more")


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
