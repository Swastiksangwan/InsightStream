import importlib.util
import sys
from pathlib import Path

import pytest


def load_importer_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = (
        repo_root / "analytics" / "scripts" / "import_content_metadata_from_preview.py"
    )
    spec = importlib.util.spec_from_file_location(
        "import_content_metadata_from_preview",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_content_metadata_from_preview"] = module
    spec.loader.exec_module(module)
    return module


def preview_record(module, content_type="series", status="Ended"):
    return module.ContentPreviewRecord(
        title="The Bear",
        content_type=content_type,
        tmdb_id=136315,
        tmdb_external_id="136315",
        imdb_id=None,
        content_values={
            "status": status,
            "latest_activity_date": None,
        },
        genres=[],
        series_metadata={} if content_type == "series" else None,
    )


def test_existing_series_status_updates_from_valid_tmdb_preview_status():
    importer = load_importer_module()
    stats = importer.ImportStats(
        mode="DRY RUN",
        preview_path="analytics/processed/tmdb/sample_mapping_preview.json",
    )

    updates = importer.content_update_plan(
        {"status": "Ongoing"},
        preview_record(importer, status="Ended"),
        stats,
    )

    assert updates["status"] == "Ended"
    assert stats.conflicts_preserved == 0
    assert any(
        "content.status would update" in message
        for message in stats.content_update_messages
    )


@pytest.mark.parametrize("preview_status", [None, "", "Unknown", "unknown"])
def test_existing_series_status_ignores_empty_or_unknown_preview_status(preview_status):
    importer = load_importer_module()
    stats = importer.ImportStats(
        mode="DRY RUN",
        preview_path="analytics/processed/tmdb/sample_mapping_preview.json",
    )

    updates = importer.content_update_plan(
        {"status": "Ongoing"},
        preview_record(importer, status=preview_status),
        stats,
    )

    assert "status" not in updates
    assert stats.conflicts_preserved == 0
    assert stats.content_update_messages == []


def test_existing_movie_status_preserves_existing_conflict_behavior():
    importer = load_importer_module()
    stats = importer.ImportStats(
        mode="DRY RUN",
        preview_path="analytics/processed/tmdb/sample_mapping_preview.json",
    )

    updates = importer.content_update_plan(
        {"status": "Released"},
        preview_record(importer, content_type="movie", status="Upcoming"),
        stats,
    )

    assert "status" not in updates
    assert stats.conflicts_preserved == 1
    assert any(
        "existing content.status differs from preview; preserved existing value"
        in warning
        for warning in stats.warnings
    )


def test_apply_mode_series_status_uses_existing_update_path_payload():
    importer = load_importer_module()
    stats = importer.ImportStats(
        mode="APPLY",
        preview_path="analytics/processed/tmdb/sample_mapping_preview.json",
    )

    updates = importer.content_update_plan(
        {"status": "Ongoing"},
        preview_record(importer, status="Canceled"),
        stats,
    )

    assert updates == {"status": "Canceled"}
    assert any(
        "content.status will update" in message
        for message in stats.content_update_messages
    )
