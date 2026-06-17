#!/usr/bin/env python3
"""
Fetch TMDb person details into an inspection-only processed preview.

This script:
- reads local people with TMDb person external IDs from PostgreSQL
- fetches /person/{person_id} from TMDb
- writes analytics/processed/tmdb/person_details_preview.json
- does not update PostgreSQL
- does not modify backend/frontend/schema/sample_data files
- keeps TMDb as a replaceable prototype metadata provider

Run from repository root:

    export DATABASE_URL="..."
    export TMDB_READ_ACCESS_TOKEN="..."
    python3 analytics/scripts/fetch_tmdb_person_details.py
"""

from __future__ import annotations

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
OUTPUT_PATH = (
    REPO_ROOT / "analytics" / "processed" / "tmdb" / "person_details_preview.json"
)
PROFILE_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w185"


@dataclass(frozen=True)
class LocalPerson:
    person_id: int
    source_person_id: str
    name: str


@dataclass
class FetchStats:
    total_people_found: int = 0
    total_fetched: int = 0
    people_with_biography: int = 0
    people_without_biography: int = 0
    warnings: List[str] = field(default_factory=list)


class PersonDetailsFetchError(RuntimeError):
    pass


def relative_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def clean_text(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def read_tmdb_people(database_url: str) -> List[LocalPerson]:
    query = text(
        """
        SELECT
            p.id AS person_id,
            p.name,
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
            )
        )

    return people


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
        "birthday": clean_text(details.get("birthday")),
        "deathday": clean_text(details.get("deathday")),
        "place_of_birth": clean_text(details.get("place_of_birth")),
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
        "total_people": stats.total_people_found,
        "people_with_biography": stats.people_with_biography,
        "people_without_biography": stats.people_without_biography,
        "warnings": stats.warnings,
        "items": items,
    }


def print_summary(stats: FetchStats) -> None:
    print(f"Total people found: {stats.total_people_found}")
    print(f"Total fetched: {stats.total_fetched}")
    print(f"People with biography: {stats.people_with_biography}")
    print(f"People without biography: {stats.people_without_biography}")
    print(f"Warnings: {len(stats.warnings)}")
    for warning in stats.warnings:
        print(f"- {warning}")
    print(f"Output path: {relative_path(OUTPUT_PATH)}")
    print("No database/frontend/backend/schema changes were made.")


def main() -> int:
    database_url = os.getenv(DATABASE_URL_ENV)
    token = os.getenv(TOKEN_ENV_VAR)

    if not database_url:
        print(
            f"Error: Missing {DATABASE_URL_ENV}. Export it before fetching TMDb person details."
        )
        return 1

    if not token:
        print(
            f"Error: Missing {TOKEN_ENV_VAR}. Export it before fetching TMDb person details."
        )
        return 1

    try:
        people = read_tmdb_people(database_url)
    except PersonDetailsFetchError as exc:
        print(f"Error: {exc}")
        return 1

    stats = FetchStats(total_people_found=len(people))
    items: List[Dict[str, Any]] = []

    for person in people:
        try:
            details = fetch_tmdb_person(person.source_person_id, token)
            item = map_person_preview(person, details)
            items.append(item)
            stats.total_fetched += 1
            if item["biography"]:
                stats.people_with_biography += 1
            else:
                stats.people_without_biography += 1
            stats.warnings.extend(
                f"{person.name}: {warning}" for warning in item.get("warnings", [])
            )
        except PersonDetailsFetchError as exc:
            stats.warnings.append(f"{person.name} ({person.source_person_id}): {exc}")

    write_json(OUTPUT_PATH, build_preview(items, stats))
    print_summary(stats)
    return 0 if stats.total_fetched == stats.total_people_found else 1


if __name__ == "__main__":
    sys.exit(main())
