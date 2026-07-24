from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from analytics.scripts.ingestion import merge_ingestion_candidates as merger


def target(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "title": "Existing Title",
        "content_type": "movie",
        "source_name": "tmdb",
        "source_id": "100",
        "priority": "seed",
        "ingestion_status": "verified",
        "notes": "Existing canonical target.",
    }
    value.update(overrides)
    return value


def candidate(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "title": "Candidate Title",
        "content_type": "movie",
        "source_name": "tmdb",
        "source_id": "200",
        "priority": "batch_test_6",
        "ingestion_status": "candidate",
        "notes": "Curated catalog-gap rationale.",
    }
    value.update(overrides)
    return value


def write_manifest(path: Path, targets: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps({"description": "Test manifest.", "targets": targets}, indent=2)
        + "\n",
        encoding="utf-8",
    )


def run_merge(
    candidates_path: Path,
    targets_path: Path,
    *,
    priority: str = "batch_test_6",
    apply: bool = False,
) -> int:
    argv = [
        "--candidates",
        str(candidates_path),
        "--targets",
        str(targets_path),
        "--priority",
        priority,
    ]
    if apply:
        argv.append("--apply")
    return merger.main(argv)


def test_normalized_candidate_preserves_supported_metadata_and_notes():
    raw = candidate(
        title="  Mixed Case Title  ",
        content_type=" SERIES ",
        source_name=" TMDB ",
        source_id=321,
        notes="  Preserve this reason.  ",
        original_language="JA",
        year="2025",
        unsupported_field="do not copy",
    )

    normalized = merger.normalized_candidate(raw, "batch_test_6")

    assert normalized == {
        "title": "Mixed Case Title",
        "content_type": "series",
        "source_name": "tmdb",
        "source_id": "321",
        "priority": "batch_test_6",
        "ingestion_status": "verified",
        "notes": "Preserve this reason.",
        "original_language": "ja",
        "year": 2025,
    }
    assert normalized["notes"] != "Verified batch-2 scalable ingestion target."


def test_missing_optional_metadata_remains_absent():
    normalized = merger.normalized_candidate(candidate(), "batch_test_6")

    assert "original_language" not in normalized
    assert "year" not in normalized


def test_priority_mismatch_fails_without_modifying_targets(tmp_path, capsys):
    candidates_path = tmp_path / "candidates.json"
    targets_path = tmp_path / "targets.json"
    write_manifest(candidates_path, [candidate(priority="batch_test_7")])
    write_manifest(targets_path, [target()])
    original_bytes = targets_path.read_bytes()

    result = run_merge(candidates_path, targets_path, apply=True)

    assert result == 1
    assert targets_path.read_bytes() == original_bytes
    output = capsys.readouterr().out
    assert "Candidate Title" in output
    assert "actual priority is batch_test_7" in output
    assert "No files were changed." in output


def test_missing_and_mixed_priorities_fail(tmp_path, capsys):
    candidates_path = tmp_path / "candidates.json"
    targets_path = tmp_path / "targets.json"
    write_manifest(
        candidates_path,
        [
            candidate(title="Missing Priority", source_id="201", priority=None),
            candidate(
                title="Different Priority",
                source_id="202",
                priority="batch_test_7",
            ),
        ],
    )
    write_manifest(targets_path, [target()])
    original_bytes = targets_path.read_bytes()

    result = run_merge(candidates_path, targets_path, apply=True)

    assert result == 1
    assert targets_path.read_bytes() == original_bytes
    output = capsys.readouterr().out
    assert "Missing Priority" in output
    assert "actual priority is <missing>" in output
    assert "Different Priority" in output
    assert "actual priority is batch_test_7" in output


def test_duplicate_detection_still_blocks_apply(tmp_path, capsys):
    candidates_path = tmp_path / "candidates.json"
    targets_path = tmp_path / "targets.json"
    write_manifest(
        candidates_path,
        [
            candidate(title="First Candidate", source_id="200"),
            candidate(title="Second Candidate", source_id="200"),
        ],
    )
    write_manifest(targets_path, [target()])
    original_bytes = targets_path.read_bytes()

    result = run_merge(candidates_path, targets_path, apply=True)

    assert result == 1
    assert targets_path.read_bytes() == original_bytes
    assert "duplicate source_name/source_id" in capsys.readouterr().out


def test_dry_run_does_not_modify_targets(tmp_path, capsys):
    candidates_path = tmp_path / "candidates.json"
    targets_path = tmp_path / "targets.json"
    write_manifest(candidates_path, [candidate()])
    write_manifest(targets_path, [target()])
    original_bytes = targets_path.read_bytes()

    result = run_merge(candidates_path, targets_path)

    assert result == 0
    assert targets_path.read_bytes() == original_bytes
    assert "Dry run passed." in capsys.readouterr().out


def test_apply_appends_verified_candidate_without_rewriting_existing_objects(
    tmp_path,
    capsys,
):
    candidates_path = tmp_path / "candidates.json"
    targets_path = tmp_path / "targets.json"
    existing_targets = [
        target(),
        target(
            title="Second Existing Title",
            content_type="series",
            source_id="101",
            original_language="ko",
        ),
    ]
    write_manifest(
        candidates_path,
        [
            candidate(
                original_language="fr",
                year=2024,
                notes="French catalog-expansion rationale.",
            )
        ],
    )
    write_manifest(targets_path, existing_targets)

    result = run_merge(candidates_path, targets_path, apply=True)

    assert result == 0
    updated_targets = json.loads(targets_path.read_text(encoding="utf-8"))["targets"]
    assert updated_targets[: len(existing_targets)] == existing_targets
    assert updated_targets[-1] == {
        "title": "Candidate Title",
        "content_type": "movie",
        "source_name": "tmdb",
        "source_id": "200",
        "priority": "batch_test_6",
        "ingestion_status": "verified",
        "notes": "French catalog-expansion rationale.",
        "original_language": "fr",
        "year": 2024,
    }
    output = capsys.readouterr().out
    assert "Merged candidates into target config." in output
    assert "No database changes were made." in output


def test_invalid_supported_optional_metadata_fails_without_writing(
    tmp_path,
    capsys,
):
    candidates_path = tmp_path / "candidates.json"
    targets_path = tmp_path / "targets.json"
    write_manifest(
        candidates_path,
        [candidate(original_language="japanese", year="unknown")],
    )
    write_manifest(targets_path, [target()])
    original_bytes = targets_path.read_bytes()

    result = run_merge(candidates_path, targets_path, apply=True)

    assert result == 1
    assert targets_path.read_bytes() == original_bytes
    output = capsys.readouterr().out
    assert "original_language must be an ISO 639-1 code" in output
    assert "year must be an integer from 1800 through 3000" in output
