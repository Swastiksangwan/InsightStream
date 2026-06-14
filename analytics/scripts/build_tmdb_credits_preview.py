#!/usr/bin/env python3
"""
Build an inspection-only structured credits preview from existing TMDb raw files.

This script:
- reads the processed TMDb title preview
- reads local raw TMDb details/credits JSON
- writes a provider-neutral processed credits preview
- does not call TMDb or any external API
- does not connect to PostgreSQL
- does not modify backend, frontend, schema, or seed data

Run from repository root:

    python3 analytics/scripts/build_tmdb_credits_preview.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_INPUT_DIR = REPO_ROOT / "analytics" / "raw" / "tmdb"
PROCESSED_DIR = REPO_ROOT / "analytics" / "processed" / "tmdb"
TITLE_PREVIEW_PATH = PROCESSED_DIR / "sample_mapping_preview.json"
CREDITS_PREVIEW_PATH = PROCESSED_DIR / "credits_preview.json"
SOURCE_PROVIDER = "tmdb"
PROFILE_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w185"
CAST_LIMIT = 5


class CreditsPreviewError(RuntimeError):
    pass


def relative_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CreditsPreviewError(f"Missing required file: {relative_path(path)}") from exc
    except json.JSONDecodeError as exc:
        raise CreditsPreviewError(f"Malformed JSON in {relative_path(path)}: {exc}") from exc

    if not isinstance(data, dict):
        raise CreditsPreviewError(f"Unexpected JSON shape in {relative_path(path)}")

    return data


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def raw_filename(media_type: str, tmdb_id: int, payload_name: str) -> str:
    return f"{media_type}_{tmdb_id}_{payload_name}.json"


def normalize_title(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def title_matches(expected: Optional[str], actual: Optional[str]) -> bool:
    expected_normalized = normalize_title(expected)
    actual_normalized = normalize_title(actual)
    return bool(
        expected_normalized
        and actual_normalized
        and (
            expected_normalized in actual_normalized
            or actual_normalized in expected_normalized
        )
    )


def content_type_from_media_type(media_type: str) -> Optional[str]:
    if media_type == "movie":
        return "movie"
    if media_type == "tv":
        return "series"
    return None


def profile_url(profile_path: Optional[str]) -> Optional[str]:
    if not profile_path:
        return None
    return f"{PROFILE_IMAGE_BASE_URL}{profile_path}"


def as_source_person_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def map_cast_member(cast_member: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    source_person_id = as_source_person_id(cast_member.get("id"))
    name = cast_member.get("name")

    if not source_person_id:
        warnings.append(f"Missing source person ID for cast member {name or '<unknown>'}.")
    if not name:
        warnings.append("Missing cast member name.")

    return {
        "source_name": SOURCE_PROVIDER,
        "source_person_id": source_person_id,
        "source_credit_id": cast_member.get("credit_id"),
        "name": name,
        "character_name": cast_member.get("character"),
        "known_for_department": cast_member.get("known_for_department"),
        "profile_path": cast_member.get("profile_path"),
        "profile_url": profile_url(cast_member.get("profile_path")),
        "display_order": cast_member.get("order"),
        "role_type": "cast",
    }


def map_director(crew_member: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    source_person_id = as_source_person_id(crew_member.get("id"))
    name = crew_member.get("name")

    if not source_person_id:
        warnings.append(f"Missing source person ID for director {name or '<unknown>'}.")
    if not name:
        warnings.append("Missing director name.")

    return {
        "source_name": SOURCE_PROVIDER,
        "source_person_id": source_person_id,
        "source_credit_id": crew_member.get("credit_id"),
        "name": name,
        "job": crew_member.get("job"),
        "department": crew_member.get("department"),
        "known_for_department": crew_member.get("known_for_department"),
        "profile_path": crew_member.get("profile_path"),
        "profile_url": profile_url(crew_member.get("profile_path")),
        "role_type": "director",
    }


def map_creator(
    creator: dict[str, Any],
    warnings: list[str],
    people_by_id: dict[Any, dict[str, Any]],
) -> dict[str, Any]:
    source_person_id = as_source_person_id(creator.get("id"))
    name = creator.get("name")
    matching_credit = people_by_id.get(creator.get("id"), {})
    known_for_department = matching_credit.get("known_for_department")
    profile_path = creator.get("profile_path") or matching_credit.get("profile_path")

    if not source_person_id:
        warnings.append(f"Missing source person ID for creator {name or '<unknown>'}.")
    if not name:
        warnings.append("Missing creator name.")

    return {
        "source_name": SOURCE_PROVIDER,
        "source_person_id": source_person_id,
        "source_credit_id": creator.get("credit_id") or matching_credit.get("credit_id"),
        "name": name,
        "job": "Creator",
        "department": matching_credit.get("department"),
        "known_for_department": known_for_department,
        "profile_path": profile_path,
        "profile_url": profile_url(profile_path),
        "role_type": "creator",
    }


def people_index_from_credits(credits: dict[str, Any]) -> dict[Any, dict[str, Any]]:
    people_by_id: dict[Any, dict[str, Any]] = {}
    for group_name in ("cast", "crew"):
        group = credits.get(group_name, [])
        if not isinstance(group, list):
            continue
        for person in group:
            if isinstance(person, dict) and person.get("id") is not None:
                people_by_id.setdefault(person["id"], person)
    return people_by_id


def extract_cast(credits: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    cast = credits.get("cast")
    if not isinstance(cast, list):
        warnings.append("Missing or invalid cast array in credits file.")
        return []

    if not cast:
        warnings.append("Missing cast.")
        return []

    sorted_cast = sorted(
        cast,
        key=lambda item: item.get("order") if isinstance(item.get("order"), int) else 9999,
    )
    return [
        map_cast_member(cast_member, warnings)
        for cast_member in sorted_cast[:CAST_LIMIT]
        if isinstance(cast_member, dict)
    ]


def extract_directors(credits: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    crew = credits.get("crew")
    if not isinstance(crew, list):
        warnings.append("Missing or invalid crew array in credits file.")
        return []

    directors = [
        map_director(crew_member, warnings)
        for crew_member in crew
        if isinstance(crew_member, dict) and crew_member.get("job") == "Director"
    ]

    if not directors:
        warnings.append("Missing director for movie.")

    return directors


def extract_creators(
    details: dict[str, Any],
    credits: dict[str, Any],
    preview_item: dict[str, Any],
    warnings: list[str],
) -> list[dict[str, Any]]:
    created_by = details.get("created_by")
    if not isinstance(created_by, list):
        warnings.append("Missing or invalid created_by array in TV details file.")
        return []

    people_by_id = people_index_from_credits(credits)
    creators = [
        map_creator(creator, warnings, people_by_id)
        for creator in created_by
        if isinstance(creator, dict)
    ]

    if creators:
        return creators

    fallback_names = preview_item.get("director_or_creator_names") or []
    if fallback_names:
        warnings.append(
            "No structured creators found; preview names exist but are name-only and should not be imported without provider IDs."
        )
    else:
        warnings.append("Missing creator for series.")

    return []


def validate_item(
    preview_item: dict[str, Any],
    details: dict[str, Any],
    warnings: list[str],
) -> None:
    media_type = preview_item.get("media_type")
    expected_title = preview_item.get("title")
    details_title = details.get("title") if media_type == "movie" else details.get("name")

    if details.get("id") != preview_item.get("tmdb_id"):
        warnings.append(
            f"TMDb ID mismatch: preview has {preview_item.get('tmdb_id')}, details has {details.get('id')}."
        )

    if media_type not in {"movie", "tv"}:
        warnings.append(f"Unsupported media_type: {media_type}.")

    if not title_matches(expected_title, details_title):
        warnings.append(
            f"Title mismatch: preview has '{expected_title}', details has '{details_title}'."
        )


def build_item(preview_item: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    tmdb_id = preview_item.get("tmdb_id")
    media_type = preview_item.get("media_type")

    if not isinstance(tmdb_id, int):
        warnings.append("Invalid or missing tmdb_id.")
        tmdb_id = 0

    if not isinstance(media_type, str):
        warnings.append("Invalid or missing media_type.")
        media_type = ""

    details_path = RAW_INPUT_DIR / raw_filename(media_type, tmdb_id, "details")
    credits_path = RAW_INPUT_DIR / raw_filename(media_type, tmdb_id, "credits")

    details = load_json(details_path)
    credits = load_json(credits_path)
    validate_item(preview_item, details, warnings)

    cast = extract_cast(credits, warnings)
    directors: list[dict[str, Any]] = []
    creators: list[dict[str, Any]] = []

    if media_type == "movie":
        directors = extract_directors(credits, warnings)
    elif media_type == "tv":
        creators = extract_creators(details, credits, preview_item, warnings)

    credits_payload = {
        "cast": cast,
        "directors": directors,
        "creators": creators,
        "crew": [],
    }

    return {
        "tmdb_id": preview_item.get("tmdb_id"),
        "content_type": content_type_from_media_type(media_type),
        "media_type": media_type,
        "title": preview_item.get("title"),
        "credits": credits_payload,
        "counts": {
            "cast": len(cast),
            "directors": len(directors),
            "creators": len(creators),
            "crew": 0,
        },
        "warnings": warnings,
    }


def validate_required_raw_files(items: list[dict[str, Any]]) -> list[str]:
    missing_paths: list[str] = []
    for item in items:
        tmdb_id = item.get("tmdb_id")
        media_type = item.get("media_type")
        if not isinstance(tmdb_id, int) or not isinstance(media_type, str):
            missing_paths.append(
                f"Invalid preview item for title {item.get('title')!r}; missing usable tmdb_id/media_type."
            )
            continue

        for payload_name in ("details", "credits"):
            path = RAW_INPUT_DIR / raw_filename(media_type, tmdb_id, payload_name)
            if not path.exists():
                missing_paths.append(relative_path(path))

    return missing_paths


def build_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    titles_with_missing_cast = [
        item["title"] for item in items if item["counts"]["cast"] == 0
    ]
    titles_with_missing_director_or_creator = [
        item["title"]
        for item in items
        if item["content_type"] == "movie" and item["counts"]["directors"] == 0
        or item["content_type"] == "series" and item["counts"]["creators"] == 0
    ]
    titles_with_warnings = [
        item["title"] for item in items if item.get("warnings")
    ]

    return {
        "total_titles": len(items),
        "total_cast_people": sum(item["counts"]["cast"] for item in items),
        "total_directors": sum(item["counts"]["directors"] for item in items),
        "total_creators": sum(item["counts"]["creators"] for item in items),
        "titles_with_missing_cast": titles_with_missing_cast,
        "titles_with_missing_director_or_creator": titles_with_missing_director_or_creator,
        "total_warnings": sum(len(item.get("warnings", [])) for item in items),
        "titles_with_warnings": titles_with_warnings,
    }


def build_preview() -> dict[str, Any]:
    title_preview = load_json(TITLE_PREVIEW_PATH)
    title_items = title_preview.get("items")
    if not isinstance(title_items, list) or not title_items:
        raise CreditsPreviewError(
            f"No preview items found in {relative_path(TITLE_PREVIEW_PATH)}"
        )

    missing_paths = validate_required_raw_files(title_items)
    if missing_paths:
        missing_list = "\n".join(f"- {path}" for path in missing_paths)
        raise CreditsPreviewError(
            "Missing required raw TMDb files. Run "
            "`python3 analytics/scripts/fetch_tmdb_sample.py` first.\n"
            f"{missing_list}"
        )

    items = [build_item(item) for item in title_items]
    summary = build_summary(items)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inspection_only": True,
        "source_provider": SOURCE_PROVIDER,
        "source_preview_path": relative_path(TITLE_PREVIEW_PATH),
        "total_titles": len(items),
        "summary": summary,
        "items": items,
    }


def print_summary(preview: dict[str, Any]) -> None:
    summary = preview["summary"]
    print(f"Credits preview written to: {relative_path(CREDITS_PREVIEW_PATH)}")
    print(f"Total titles processed: {summary['total_titles']}")
    print(f"Total cast records: {summary['total_cast_people']}")
    print(f"Total directors: {summary['total_directors']}")
    print(f"Total creators: {summary['total_creators']}")
    print(f"Total warnings: {summary['total_warnings']}")
    if summary["titles_with_warnings"]:
        print("Titles with warnings:")
        for title in summary["titles_with_warnings"]:
            print(f"- {title}")
    else:
        print("Titles with warnings: none")
    print("No database, API, frontend, schema, or sample_data changes were made.")


def main() -> int:
    try:
        preview = build_preview()
        save_json(CREDITS_PREVIEW_PATH, preview)
        print_summary(preview)
    except CreditsPreviewError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
