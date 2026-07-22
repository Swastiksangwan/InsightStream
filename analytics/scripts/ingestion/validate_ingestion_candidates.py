#!/usr/bin/env python3
"""
Validate candidate ingestion targets before merging them into the main target file.

This script:
- reads a candidate target file
- checks local shape, uniqueness, and duplicate conflicts
- optionally verifies TMDb IDs when TMDB_READ_ACCESS_TOKEN is available
- writes a run report
- does not fetch ingestion payloads
- does not write to PostgreSQL
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
    from requests import RequestException
except ImportError:  # pragma: no cover - helpful when dependencies are not installed.
    requests = None

    class RequestException(Exception):
        pass


API_BASE_URL = "https://api.themoviedb.org/3"
TOKEN_ENV_VAR = "TMDB_READ_ACCESS_TOKEN"
from analytics.scripts.common.paths import REPO_ROOT
DEFAULT_CANDIDATES_PATH = (
    REPO_ROOT / "analytics" / "config" / "content_ingestion_candidates_batch_2.json"
)
DEFAULT_TARGETS_PATH = REPO_ROOT / "analytics" / "config" / "content_ingestion_targets.json"
RUN_REPORT_DIR = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "tmdb"
    / "run_reports"
)
SUPPORTED_CONTENT_TYPES = {"movie", "series"}
SUPPORTED_SOURCE_NAMES = {"tmdb"}
SUPPORTED_STATUSES = {"candidate", "verified", "needs_review"}


@dataclass(frozen=True)
class Candidate:
    index: int
    title: str | None
    content_type: str | None
    source_name: str | None
    source_id: str | None
    priority: str | None
    ingestion_status: str | None
    notes: str | None
    raw: dict[str, Any]


class ValidationError(RuntimeError):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate candidate ingestion targets before merging them."
    )
    parser.add_argument(
        "--candidates",
        required=True,
        help=(
            "Candidate JSON path, for example "
            f"{DEFAULT_CANDIDATES_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--targets",
        default=str(DEFAULT_TARGETS_PATH.relative_to(REPO_ROOT)),
        help=(
            "Existing target JSON path. Defaults to "
            f"{DEFAULT_TARGETS_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--priority",
        help=(
            "Expected priority for all candidates. If omitted, the validator "
            "infers it when all candidates share one priority."
        ),
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


def title_matches(expected: str | None, actual: str | None) -> bool:
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


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "candidate"


def report_path_for_priority(priority: str) -> Path:
    batch_match = re.fullmatch(r"batch_test_(\d+)", priority)
    if batch_match:
        filename = f"batch_{batch_match.group(1)}_target_validation_report.json"
    else:
        filename = f"{safe_slug(priority)}_target_validation_report.json"
    return RUN_REPORT_DIR / filename


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"Missing JSON file: {relative_path(path)}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Malformed JSON in {relative_path(path)}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValidationError(f"JSON file must contain an object: {relative_path(path)}")

    return data


def candidate_from_raw(index: int, raw: Any) -> tuple[Candidate | None, str | None]:
    if not isinstance(raw, dict):
        return None, f"Candidate #{index}: expected an object."

    return Candidate(
        index=index,
        title=clean_text(raw.get("title")),
        content_type=(clean_text(raw.get("content_type")) or "").lower() or None,
        source_name=(clean_text(raw.get("source_name")) or "").lower() or None,
        source_id=clean_text(raw.get("source_id")),
        priority=clean_text(raw.get("priority")),
        ingestion_status=(clean_text(raw.get("ingestion_status")) or "").lower() or None,
        notes=clean_text(raw.get("notes")),
        raw=raw,
    ), None


def load_candidates(path: Path) -> list[Candidate]:
    data = load_json_object(path)
    raw_targets = data.get("targets")
    if not isinstance(raw_targets, list):
        raise ValidationError(
            f"Candidate file must contain a top-level 'targets' array: {relative_path(path)}"
        )

    candidates: list[Candidate] = []
    shape_errors: list[str] = []
    for index, raw in enumerate(raw_targets, start=1):
        candidate, error = candidate_from_raw(index, raw)
        if error:
            shape_errors.append(error)
        elif candidate:
            candidates.append(candidate)

    if shape_errors:
        raise ValidationError("; ".join(shape_errors))

    return candidates


def infer_expected_priority(
    candidates: list[Candidate],
    explicit_priority: str | None,
) -> str:
    if explicit_priority:
        return explicit_priority

    priorities = sorted({candidate.priority for candidate in candidates if candidate.priority})
    missing_priority_count = sum(1 for candidate in candidates if not candidate.priority)

    if missing_priority_count:
        raise ValidationError(
            f"Cannot infer priority because {missing_priority_count} candidate(s) are missing priority."
        )

    if len(priorities) != 1:
        values = ", ".join(priorities) if priorities else "none"
        raise ValidationError(
            f"Cannot infer expected priority from mixed candidate priorities: {values}."
        )

    return priorities[0]


def load_existing_targets(path: Path) -> tuple[set[str], set[tuple[str, str]], list[str]]:
    data = load_json_object(path)
    raw_targets = data.get("targets")
    if not isinstance(raw_targets, list):
        raise ValidationError(
            f"Existing target file must contain a top-level 'targets' array: {relative_path(path)}"
        )

    source_ids: set[str] = set()
    title_types: set[tuple[str, str]] = set()
    warnings: list[str] = []

    for index, raw_target in enumerate(raw_targets, start=1):
        if not isinstance(raw_target, dict):
            warnings.append(f"Existing target #{index}: expected object; ignored.")
            continue

        source_name = (clean_text(raw_target.get("source_name")) or "").lower()
        source_id = clean_text(raw_target.get("source_id"))
        title = clean_text(raw_target.get("title"))
        content_type = (clean_text(raw_target.get("content_type")) or "").lower()

        if source_name == "tmdb" and source_id:
            source_ids.add(source_id)
        if title and content_type:
            title_types.add((normalize_title(title), content_type))

    return source_ids, title_types, warnings


def tmdb_path(candidate: Candidate) -> str:
    media_type = "movie" if candidate.content_type == "movie" else "tv"
    return f"/{media_type}/{candidate.source_id}"


def fetch_tmdb_details(candidate: Candidate, token: str) -> dict[str, Any]:
    if requests is None:
        raise ValidationError(
            "Missing dependency 'requests'. Run `pip install -r backend/requirements.txt`."
        )

    path = tmdb_path(candidate)
    url = f"{API_BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=20)
    except RequestException as exc:
        raise ValidationError(f"TMDb validation request failed for {path}: {exc}") from exc

    if not response.ok:
        raise ValidationError(
            f"TMDb validation failed for {path}: HTTP {response.status_code} - "
            f"{response.text[:200]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise ValidationError(f"TMDb returned malformed JSON for {path}") from exc

    if not isinstance(data, dict):
        raise ValidationError(f"TMDb returned unexpected JSON shape for {path}")

    return data


def validate_remote_candidate(
    candidate: Candidate,
    token: str,
) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    failures: list[str] = []

    try:
        details = fetch_tmdb_details(candidate, token)
    except ValidationError as exc:
        failures.append(str(exc))
        return warnings, failures

    returned_title = details.get("title") if candidate.content_type == "movie" else details.get("name")
    if not returned_title:
        failures.append("TMDb detail payload did not include expected title/name field.")
    elif not title_matches(candidate.title, returned_title):
        warnings.append(
            f"TMDb title/name differs: candidate '{candidate.title}', returned '{returned_title}'."
        )

    returned_id = details.get("id")
    if returned_id is not None and str(returned_id) != candidate.source_id:
        failures.append(
            f"TMDb detail payload returned id {returned_id}, expected {candidate.source_id}."
        )

    return warnings, failures


def base_candidate_status(
    candidate: Candidate,
    expected_priority: str,
    seen_source_ids: set[str],
    seen_title_types: set[tuple[str, str]],
    existing_source_ids: set[str],
    existing_title_types: set[tuple[str, str]],
) -> tuple[list[str], list[str], int]:
    warnings: list[str] = []
    failures: list[str] = []
    duplicate_count = 0

    if not candidate.title:
        failures.append("Missing title.")
    if candidate.content_type not in SUPPORTED_CONTENT_TYPES:
        failures.append("content_type must be movie or series.")
    if candidate.source_name not in SUPPORTED_SOURCE_NAMES:
        failures.append("source_name must be tmdb.")
    if not candidate.source_id:
        failures.append("Missing source_id.")
    elif not candidate.source_id.isdigit() or int(candidate.source_id) <= 0:
        failures.append("source_id must be a positive integer string.")
    if candidate.priority != expected_priority:
        failures.append(f"priority must be {expected_priority}.")
    if candidate.ingestion_status not in SUPPORTED_STATUSES:
        failures.append(
            "ingestion_status must be candidate, verified, or needs_review."
        )
    if not candidate.notes:
        warnings.append("notes are empty.")

    if candidate.source_id:
        if candidate.source_id in seen_source_ids:
            failures.append("Duplicate source_id within candidate file.")
            duplicate_count += 1
        if candidate.source_id in existing_source_ids:
            failures.append("source_id already exists in main target config.")
            duplicate_count += 1
        seen_source_ids.add(candidate.source_id)

    title_type = (
        normalize_title(candidate.title),
        candidate.content_type or "",
    )
    if title_type[0] and title_type[1]:
        if title_type in seen_title_types:
            failures.append("Duplicate title + content_type within candidate file.")
            duplicate_count += 1
        if title_type in existing_title_types:
            failures.append("title + content_type already exists in main target config.")
            duplicate_count += 1
        seen_title_types.add(title_type)

    return warnings, failures, duplicate_count


def validation_status(warnings: list[str], failures: list[str]) -> str:
    if failures:
        return "failed"
    if warnings:
        return "warning"
    return "valid"


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    candidates_path = resolve_path(args.candidates)
    targets_path = resolve_path(args.targets)

    try:
        candidates = load_candidates(candidates_path)
        expected_priority = infer_expected_priority(candidates, clean_text(args.priority))
        existing_source_ids, existing_title_types, existing_warnings = load_existing_targets(
            targets_path
        )
    except ValidationError as exc:
        print(f"Validation setup failed: {exc}", file=sys.stderr)
        return 1

    report_path = report_path_for_priority(expected_priority)
    token = os.environ.get(TOKEN_ENV_VAR)
    remote_validation_ran = bool(token)
    top_level_warnings = existing_warnings.copy()
    if not token:
        top_level_warnings.append(
            f"{TOKEN_ENV_VAR} is not set; remote TMDb validation was skipped."
        )

    seen_source_ids: set[str] = set()
    seen_title_types: set[tuple[str, str]] = set()
    per_candidate: list[dict[str, Any]] = []
    duplicate_count = 0

    for candidate in candidates:
        warnings, failures, candidate_duplicates = base_candidate_status(
            candidate,
            expected_priority,
            seen_source_ids,
            seen_title_types,
            existing_source_ids,
            existing_title_types,
        )
        duplicate_count += candidate_duplicates

        if token and not failures:
            remote_warnings, remote_failures = validate_remote_candidate(candidate, token)
            warnings.extend(remote_warnings)
            failures.extend(remote_failures)

        per_candidate.append(
            {
                "title": candidate.title,
                "content_type": candidate.content_type,
                "source_name": candidate.source_name,
                "source_id": candidate.source_id,
                "priority": candidate.priority,
                "ingestion_status": candidate.ingestion_status,
                "validation_status": validation_status(warnings, failures),
                "warnings": warnings,
                "failures": failures,
            }
        )

    valid_candidates = sum(
        1 for item in per_candidate if item["validation_status"] == "valid"
    )
    candidates_needing_review = sum(
        1
        for item in per_candidate
        if item.get("ingestion_status") == "needs_review"
        or item["validation_status"] == "warning"
    )
    all_warnings = top_level_warnings + [
        f"{item['title']}: {warning}"
        for item in per_candidate
        for warning in item["warnings"]
    ]
    all_failures = [
        f"{item['title']}: {failure}"
        for item in per_candidate
        for failure in item["failures"]
    ]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_file": relative_path(candidates_path),
        "existing_target_file": relative_path(targets_path),
        "expected_priority": expected_priority,
        "remote_validation_ran": remote_validation_ran,
        "total_candidates": len(candidates),
        "valid_candidates": valid_candidates,
        "candidates_needing_review": candidates_needing_review,
        "duplicate_count": duplicate_count,
        "warnings": all_warnings,
        "failures": all_failures,
        "per_candidate": per_candidate,
    }
    write_report(report_path, report)

    print(f"Candidate file: {relative_path(candidates_path)}")
    print(f"Existing target file: {relative_path(targets_path)}")
    print(f"Expected priority: {expected_priority}")
    print(f"Remote TMDb validation ran: {'yes' if remote_validation_ran else 'no'}")
    print(f"Total candidates: {len(candidates)}")
    print(f"Valid candidates: {valid_candidates}")
    print(f"Needs review: {candidates_needing_review}")
    print(f"Duplicates: {duplicate_count}")
    print(f"Warnings: {len(all_warnings)}")
    print(f"Failures: {len(all_failures)}")
    print(f"Report path: {relative_path(report_path)}")

    if all_warnings:
        print("\nWarnings:")
        for warning in all_warnings[:10]:
            print(f"- {warning}")
        if len(all_warnings) > 10:
            print(f"- ... {len(all_warnings) - 10} more warnings")

    if all_failures:
        print("\nFailures:")
        for failure in all_failures:
            print(f"- {failure}")

    print("\nNo database changes were made.")
    print("No backend, frontend, schema, or sample_data changes were made.")
    return 0 if not all_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
