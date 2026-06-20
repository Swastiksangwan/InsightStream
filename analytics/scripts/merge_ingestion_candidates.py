#!/usr/bin/env python3
"""
Merge validated ingestion candidates into the main target config.

Dry run is the default. Use --apply to write analytics/config/content_ingestion_targets.json.
This script does not fetch provider data and does not write to PostgreSQL.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATES_PATH = (
    REPO_ROOT / "analytics" / "config" / "content_ingestion_candidates_batch_2.json"
)
DEFAULT_TARGETS_PATH = REPO_ROOT / "analytics" / "config" / "content_ingestion_targets.json"
VERIFIED_NOTES = "Verified batch-2 scalable ingestion target."
SUPPORTED_CONTENT_TYPES = {"movie", "series"}
SUPPORTED_SOURCE_NAMES = {"tmdb"}


class MergeError(RuntimeError):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge validated ingestion candidates into the main target config."
    )
    parser.add_argument(
        "--candidates",
        default=str(DEFAULT_CANDIDATES_PATH.relative_to(REPO_ROOT)),
        help=(
            "Candidate JSON path. Defaults to "
            f"{DEFAULT_CANDIDATES_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--targets",
        default=str(DEFAULT_TARGETS_PATH.relative_to(REPO_ROOT)),
        help=(
            "Main target JSON path. Defaults to "
            f"{DEFAULT_TARGETS_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--priority",
        default="batch_test_2",
        help="Priority value to assign to merged candidates.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the updated target config. Without this flag, only dry-run.",
    )
    return parser.parse_args(argv)


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
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MergeError(f"Missing JSON file: {relative_path(path)}") from exc
    except json.JSONDecodeError as exc:
        raise MergeError(f"Malformed JSON in {relative_path(path)}: {exc}") from exc

    if not isinstance(data, dict):
        raise MergeError(f"JSON file must contain an object: {relative_path(path)}")

    targets = data.get("targets")
    if not isinstance(targets, list):
        raise MergeError(
            f"JSON file must contain a top-level 'targets' array: {relative_path(path)}"
        )

    return data


def source_key(target: dict[str, Any]) -> tuple[str, str] | None:
    source_name = (clean_text(target.get("source_name")) or "").lower()
    source_id = clean_text(target.get("source_id"))
    if not source_name or not source_id:
        return None
    return source_name, source_id


def title_type_key(target: dict[str, Any]) -> tuple[str, str] | None:
    title = clean_text(target.get("title"))
    content_type = (clean_text(target.get("content_type")) or "").lower()
    if not title or not content_type:
        return None
    return normalize_title(title), content_type


def validate_target_shape(target: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    title = clean_text(target.get("title"))
    content_type = (clean_text(target.get("content_type")) or "").lower()
    source_name = (clean_text(target.get("source_name")) or "").lower()
    source_id = clean_text(target.get("source_id"))

    if not title:
        errors.append(f"{label}: missing title")
    if content_type not in SUPPORTED_CONTENT_TYPES:
        errors.append(f"{label}: content_type must be movie or series")
    if source_name not in SUPPORTED_SOURCE_NAMES:
        errors.append(f"{label}: source_name must be tmdb")
    if not source_id:
        errors.append(f"{label}: missing source_id")
    elif not source_id.isdigit() or int(source_id) <= 0:
        errors.append(f"{label}: source_id must be a positive integer string")

    return errors


def duplicate_errors(targets: list[dict[str, Any]], label: str) -> list[str]:
    errors: list[str] = []
    seen_sources: dict[tuple[str, str], str] = {}
    seen_titles: dict[tuple[str, str], str] = {}

    for index, target in enumerate(targets, start=1):
        item_label = f"{label} #{index} ({target.get('title') or 'untitled'})"

        source = source_key(target)
        if source:
            if source in seen_sources:
                errors.append(
                    f"{item_label}: duplicate source_name/source_id also used by {seen_sources[source]}"
                )
            else:
                seen_sources[source] = item_label

        title_type = title_type_key(target)
        if title_type:
            if title_type in seen_titles:
                errors.append(
                    f"{item_label}: duplicate title/content_type also used by {seen_titles[title_type]}"
                )
            else:
                seen_titles[title_type] = item_label

    return errors


def cross_duplicate_errors(
    existing_targets: list[dict[str, Any]],
    candidate_targets: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    existing_sources = {
        source_key(target): target.get("title")
        for target in existing_targets
        if source_key(target) is not None
    }
    existing_titles = {
        title_type_key(target): target.get("title")
        for target in existing_targets
        if title_type_key(target) is not None
    }

    for candidate in candidate_targets:
        source = source_key(candidate)
        title_type = title_type_key(candidate)
        title = candidate.get("title") or "untitled"

        if source in existing_sources:
            errors.append(
                f"{title}: source_name/source_id already exists in targets as {existing_sources[source]}"
            )
        if title_type in existing_titles:
            errors.append(
                f"{title}: title/content_type already exists in targets as {existing_titles[title_type]}"
            )

    return errors


def normalized_candidate(candidate: dict[str, Any], priority: str) -> dict[str, str]:
    return {
        "title": clean_text(candidate.get("title")) or "",
        "content_type": (clean_text(candidate.get("content_type")) or "").lower(),
        "source_name": (clean_text(candidate.get("source_name")) or "").lower(),
        "source_id": clean_text(candidate.get("source_id")) or "",
        "priority": priority,
        "ingestion_status": "verified",
        "notes": VERIFIED_NOTES,
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    candidates_path = resolve_path(args.candidates)
    targets_path = resolve_path(args.targets)
    priority = clean_text(args.priority) or "batch_test_2"

    try:
        candidates_data = load_json_object(candidates_path)
        targets_data = load_json_object(targets_path)
    except MergeError as exc:
        print(f"Merge setup failed: {exc}", file=sys.stderr)
        return 1

    existing_targets = targets_data["targets"]
    raw_candidates = candidates_data["targets"]
    normalized_candidates = [
        normalized_candidate(candidate, priority)
        for candidate in raw_candidates
        if isinstance(candidate, dict)
    ]

    errors: list[str] = []
    for index, candidate in enumerate(raw_candidates, start=1):
        if not isinstance(candidate, dict):
            errors.append(f"candidate #{index}: expected object")
            continue
        errors.extend(validate_target_shape(candidate, f"candidate #{index}"))

    errors.extend(duplicate_errors(existing_targets, "existing target"))
    errors.extend(duplicate_errors(normalized_candidates, "candidate"))
    errors.extend(cross_duplicate_errors(existing_targets, normalized_candidates))

    previous_count = len(existing_targets)
    candidate_count = len(normalized_candidates)
    final_count = previous_count + candidate_count

    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"Candidates: {relative_path(candidates_path)}")
    print(f"Targets: {relative_path(targets_path)}")
    print(f"Previous target count: {previous_count}")
    print(f"Candidates to merge: {candidate_count}")
    print(f"Expected final target count: {final_count}")

    if errors:
        print("\nDuplicate/validation errors:")
        for error in errors:
            print(f"- {error}")
        print("\nNo files were changed.")
        return 1

    if args.apply:
        updated_data = dict(targets_data)
        updated_data["targets"] = [*existing_targets, *normalized_candidates]
        write_json(targets_path, updated_data)
        print("\nMerged candidates into target config.")
    else:
        print("\nDry run passed. Re-run with --apply to update the target config.")

    print("Duplicate check: passed")
    print("No database changes were made.")
    print("No backend, frontend, schema, or sample_data changes were made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
