#!/usr/bin/env python3
"""
Fetch TMDb person details into an inspection-only processed preview.

This script:
- reads local people with TMDb person external IDs from PostgreSQL
- defaults to people missing useful details
- reuses raw cached person details when available
- writes analytics/processed/tmdb/person_details_preview.json
- writes analytics/processed/tmdb/run_reports/person_details_fetch_run_report.json
- does not update PostgreSQL
- does not modify backend/frontend/schema/sample_data files
- keeps TMDb as a replaceable prototype metadata provider

Run from repository root:

    export DATABASE_URL="..."
    export TMDB_READ_ACCESS_TOKEN="..."
    python3 analytics/scripts/fetch_tmdb_person_details.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

try:
    import requests
    from requests import RequestException
except ImportError:  # pragma: no cover - dependency guidance for local runs.
    requests = None

    class RequestException(Exception):
        pass


API_BASE_URL = "https://api.themoviedb.org/3"
DATABASE_URL_ENV = "DATABASE_URL"
TOKEN_ENV_VAR = "TMDB_READ_ACCESS_TOKEN"
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_OUTPUT_DIR = REPO_ROOT / "analytics" / "raw" / "tmdb"
PROCESSED_OUTPUT_DIR = REPO_ROOT / "analytics" / "processed" / "tmdb"
OUTPUT_PATH = PROCESSED_OUTPUT_DIR / "person_details_preview.json"
RUN_REPORT_DIR = PROCESSED_OUTPUT_DIR / "run_reports"
RUN_REPORT_PATH = RUN_REPORT_DIR / "person_details_fetch_run_report.json"
PROFILE_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w185"


@dataclass(frozen=True)
class LocalPerson:
    person_id: int
    source_person_id: str
    name: str
    biography: Optional[str]
    profile_url: Optional[str]
    known_for_department: Optional[str]
    birthday: Optional[str]
    place_of_birth: Optional[str]


@dataclass
class FetchStats:
    total_people_found: int = 0
    people_selected: int = 0
    people_skipped_complete: int = 0
    raw_files_fetched: List[str] = field(default_factory=list)
    raw_files_reused: List[str] = field(default_factory=list)
    people_with_biography: int = 0
    people_without_biography: int = 0
    warnings: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    per_person: List[Dict[str, Any]] = field(default_factory=list)


class PersonDetailsFetchError(RuntimeError):
    pass


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch TMDb person details for local people with TMDb external IDs."
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Process only people missing biography, profile URL, or known-for department. This is the default.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all local TMDb people regardless of existing detail completeness.",
    )
    parser.add_argument(
        "--source-person-id",
        help="Process one TMDb person ID if present in the local database.",
    )
    parser.add_argument(
        "--person-id",
        type=positive_int,
        help="Process one local people.id value.",
    )
    parser.add_argument(
        "--name",
        help="Filter local people by exact name, case-insensitive.",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        help="Cap selected people after filtering and missing-only selection.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refetch TMDb person details even when a raw cache file exists.",
    )
    args = parser.parse_args(argv)

    if args.all and args.missing_only:
        parser.error("--all and --missing-only cannot be used together.")

    return args


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def clean_text(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def clean_db_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return clean_text(value)
    return str(value)


def is_non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def person_complete(person: LocalPerson) -> bool:
    return (
        is_non_empty(person.biography)
        and is_non_empty(person.profile_url)
        and is_non_empty(person.known_for_department)
        and is_non_empty(person.birthday)
        and is_non_empty(person.place_of_birth)
    )


def filters_used(args: argparse.Namespace) -> Dict[str, Any]:
    skip_complete = should_skip_complete(args)
    mode = "all" if args.all else "missing_only" if skip_complete else "targeted"
    return {
        "mode": mode,
        "missing_only": skip_complete,
        "all": args.all,
        "source_person_id": args.source_person_id,
        "person_id": args.person_id,
        "name": args.name,
        "limit": args.limit,
        "refresh": args.refresh,
    }


def should_skip_complete(args: argparse.Namespace) -> bool:
    if args.all:
        return False
    if args.missing_only:
        return True
    if args.source_person_id or args.person_id:
        return False
    return True


def read_tmdb_people(database_url: str) -> List[LocalPerson]:
    query = text(
        """
        SELECT
            p.id AS person_id,
            p.name,
            p.biography,
            p.profile_url,
            p.known_for_department,
            p.birthday,
            p.place_of_birth,
            pei.external_id AS source_person_id
        FROM person_external_ids pei
        JOIN people p ON p.id = pei.person_id
        WHERE pei.source_name = 'tmdb'
        ORDER BY p.id ASC;
        """
    )

    try:
        engine = create_engine(database_url)
        with engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
    except SQLAlchemyError as exc:
        raise PersonDetailsFetchError(f"Could not read person_external_ids: {exc}") from exc

    people: List[LocalPerson] = []
    for row in rows:
        source_person_id = clean_text(row["source_person_id"])
        if not source_person_id:
            continue
        people.append(
            LocalPerson(
                person_id=row["person_id"],
                source_person_id=source_person_id,
                name=row["name"],
                biography=clean_text(row["biography"]),
                profile_url=clean_text(row["profile_url"]),
                known_for_department=clean_text(row["known_for_department"]),
                birthday=clean_db_value(row["birthday"]),
                place_of_birth=clean_db_value(row["place_of_birth"]),
            )
        )

    return people


def apply_person_filters(
    people: List[LocalPerson],
    args: argparse.Namespace,
    stats: FetchStats,
) -> List[LocalPerson]:
    filtered = people

    if args.source_person_id:
        source_person_id = str(args.source_person_id).strip()
        filtered = [
            person
            for person in filtered
            if person.source_person_id == source_person_id
        ]

    if args.person_id:
        filtered = [
            person for person in filtered if person.person_id == args.person_id
        ]

    if args.name:
        name = str(args.name).strip().lower()
        filtered = [
            person for person in filtered if person.name.lower() == name
        ]

    if should_skip_complete(args):
        incomplete: List[LocalPerson] = []
        for person in filtered:
            if person_complete(person):
                stats.people_skipped_complete += 1
                stats.per_person.append(
                    {
                        "person_id": person.person_id,
                        "source_person_id": person.source_person_id,
                        "name": person.name,
                        "status": "skipped_complete",
                        "raw_file": relative_path(raw_person_path(person.source_person_id)),
                        "warnings": [],
                    }
                )
            else:
                incomplete.append(person)
        filtered = incomplete

    if args.limit:
        filtered = filtered[: args.limit]

    return filtered


def raw_person_path(source_person_id: str) -> Path:
    return RAW_OUTPUT_DIR / f"person_{source_person_id}_details.json"


def fetch_tmdb_person(source_person_id: str, token: str) -> Dict[str, Any]:
    if requests is None:
        raise PersonDetailsFetchError(
            "Missing dependency 'requests'. Run `pip install -r backend/requirements.txt`."
        )

    url = f"{API_BASE_URL}/person/{source_person_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "application/json",
    }
    params = {"language": "en-US"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
    except RequestException as exc:
        raise PersonDetailsFetchError(
            f"Request failed for TMDb person {source_person_id}: {exc}"
        ) from exc

    if response.status_code == 429:
        raise PersonDetailsFetchError(
            f"TMDb rate limit hit for person {source_person_id}. Wait and try again."
        )

    if not response.ok:
        raise PersonDetailsFetchError(
            f"TMDb person {source_person_id} failed: HTTP {response.status_code} - {response.text[:300]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise PersonDetailsFetchError(
            f"TMDb returned malformed JSON for person {source_person_id}"
        ) from exc

    if not isinstance(data, dict):
        raise PersonDetailsFetchError(
            f"TMDb returned unexpected JSON shape for person {source_person_id}"
        )

    return data


def load_cached_person_details(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PersonDetailsFetchError(f"Missing raw cache file: {relative_path(path)}") from exc
    except json.JSONDecodeError as exc:
        raise PersonDetailsFetchError(
            f"Malformed raw cache JSON in {relative_path(path)}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise PersonDetailsFetchError(
            f"Raw cache JSON has unexpected shape: {relative_path(path)}"
        )

    return data


def fetch_or_reuse_person_details(
    source_person_id: str,
    token: str | None,
    refresh: bool,
) -> tuple[Dict[str, Any], str, Path]:
    raw_path = raw_person_path(source_person_id)

    if raw_path.exists() and not refresh:
        return load_cached_person_details(raw_path), "reused", raw_path

    if not token:
        raise PersonDetailsFetchError(
            f"Missing {TOKEN_ENV_VAR}; cannot fetch TMDb person {source_person_id}."
        )

    details = fetch_tmdb_person(source_person_id, token)
    RAW_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        json.dumps(details, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return details, "fetched", raw_path


def build_profile_url(profile_path: Optional[str]) -> Optional[str]:
    if not profile_path:
        return None
    return f"{PROFILE_IMAGE_BASE_URL}{profile_path}"


def map_person_preview(
    local_person: LocalPerson,
    details: Dict[str, Any],
) -> Dict[str, Any]:
    warnings: List[str] = []
    tmdb_name = clean_text(details.get("name"))
    biography = clean_text(details.get("biography"))
    profile_path = clean_text(details.get("profile_path"))
    known_for_department = clean_text(details.get("known_for_department"))
    birthday = clean_text(details.get("birthday"))
    place_of_birth = clean_text(details.get("place_of_birth"))

    if tmdb_name and tmdb_name != local_person.name:
        warnings.append(
            f"Local name differs from TMDb name: {local_person.name!r} vs {tmdb_name!r}."
        )

    return {
        "person_id": local_person.person_id,
        "source_name": "tmdb",
        "source_person_id": local_person.source_person_id,
        "name": tmdb_name or local_person.name,
        "biography": biography,
        "profile_path": profile_path,
        "profile_url": build_profile_url(profile_path),
        "known_for_department": known_for_department,
        "birthday": birthday,
        "deathday": clean_text(details.get("deathday")),
        "place_of_birth": place_of_birth,
        "also_known_as": details.get("also_known_as")
        if isinstance(details.get("also_known_as"), list)
        else [],
        "adult": details.get("adult") if isinstance(details.get("adult"), bool) else None,
        "popularity": details.get("popularity")
        if isinstance(details.get("popularity"), (int, float))
        else None,
        "homepage": clean_text(details.get("homepage")),
        "imdb_id": clean_text(details.get("imdb_id")),
        "importable_fields": {
            "biography": bool(biography),
            "profile_url": bool(profile_path),
            "known_for_department": bool(known_for_department),
            "birthday": bool(birthday),
            "place_of_birth": bool(place_of_birth),
        },
        "warnings": warnings,
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_preview(items: List[Dict[str, Any]], stats: FetchStats) -> Dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inspection_only": True,
        "source_provider": "tmdb",
        "total_people": stats.people_selected,
        "people_with_biography": stats.people_with_biography,
        "people_without_biography": stats.people_without_biography,
        "warnings": stats.warnings,
        "items": items,
    }


def build_run_report(args: argparse.Namespace, stats: FetchStats) -> Dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "script_name": Path(__file__).name,
        "filters_used": filters_used(args),
        "total_people_found": stats.total_people_found,
        "people_selected": stats.people_selected,
        "people_skipped_complete": stats.people_skipped_complete,
        "raw_files_fetched": stats.raw_files_fetched,
        "raw_files_reused": stats.raw_files_reused,
        "total_fetched_or_reused": len(stats.raw_files_fetched) + len(stats.raw_files_reused),
        "people_with_biography": stats.people_with_biography,
        "people_without_biography": stats.people_without_biography,
        "warnings": stats.warnings,
        "failures": stats.failures,
        "per_person": stats.per_person,
    }


def print_summary(args: argparse.Namespace, stats: FetchStats) -> None:
    print(f"Mode: {filters_used(args)['mode']}")
    print(f"Filters used: {filters_used(args)}")
    print(f"Total people found: {stats.total_people_found}")
    print(f"Selected people: {stats.people_selected}")
    print(f"Skipped complete: {stats.people_skipped_complete}")
    print(f"Fetched raw files: {len(stats.raw_files_fetched)}")
    print(f"Reused raw files: {len(stats.raw_files_reused)}")
    print(f"People with biography: {stats.people_with_biography}")
    print(f"People without biography: {stats.people_without_biography}")
    print(f"Warnings: {len(stats.warnings)}")
    print(f"Failures: {len(stats.failures)}")
    for warning in stats.warnings[:10]:
        print(f"- {warning}")
    if len(stats.warnings) > 10:
        print(f"- ... {len(stats.warnings) - 10} more warnings")
    for failure in stats.failures:
        print(f"- {failure}")
    print(f"Preview output path: {relative_path(OUTPUT_PATH)}")
    print(f"Run report path: {relative_path(RUN_REPORT_PATH)}")
    print("No database changes were made.")
    print("No frontend/backend/schema/sample_data files were changed.")


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    database_url = os.getenv(DATABASE_URL_ENV)
    token = os.getenv(TOKEN_ENV_VAR)

    if not database_url:
        print(
            f"Error: Missing {DATABASE_URL_ENV}. Export it before fetching TMDb person details."
        )
        return 1

    if not token:
        print(
            f"{TOKEN_ENV_VAR} is not set. Existing raw files can still be reused, "
            "but missing raw files or --refresh will fail."
        )

    try:
        people = read_tmdb_people(database_url)
    except PersonDetailsFetchError as exc:
        print(f"Error: {exc}")
        return 1

    stats = FetchStats(total_people_found=len(people))
    selected_people = apply_person_filters(people, args, stats)
    stats.people_selected = len(selected_people)
    items: List[Dict[str, Any]] = []

    for person in selected_people:
        raw_path = raw_person_path(person.source_person_id)
        try:
            details, status, raw_path = fetch_or_reuse_person_details(
                person.source_person_id,
                token,
                args.refresh,
            )
            item = map_person_preview(person, details)
            items.append(item)

            if status == "fetched":
                stats.raw_files_fetched.append(relative_path(raw_path))
            else:
                stats.raw_files_reused.append(relative_path(raw_path))

            if item["biography"]:
                stats.people_with_biography += 1
            else:
                stats.people_without_biography += 1

            person_warnings = item.get("warnings", [])
            stats.warnings.extend(
                f"{person.name}: {warning}" for warning in person_warnings
            )
            stats.per_person.append(
                {
                    "person_id": person.person_id,
                    "source_person_id": person.source_person_id,
                    "name": person.name,
                    "status": status,
                    "raw_file": relative_path(raw_path),
                    "warnings": person_warnings,
                }
            )
        except PersonDetailsFetchError as exc:
            message = f"{person.name} ({person.source_person_id}): {exc}"
            stats.failures.append(message)
            stats.per_person.append(
                {
                    "person_id": person.person_id,
                    "source_person_id": person.source_person_id,
                    "name": person.name,
                    "status": "failed",
                    "raw_file": relative_path(raw_path),
                    "warnings": [str(exc)],
                }
            )

    if items or not stats.failures:
        write_json(OUTPUT_PATH, build_preview(items, stats))
    else:
        stats.warnings.append(
            "No person details were fetched or reused; existing person_details_preview.json was left unchanged."
        )

    write_json(RUN_REPORT_PATH, build_run_report(args, stats))
    print_summary(args, stats)
    return 0 if not stats.failures else 1


if __name__ == "__main__":
    sys.exit(main())
