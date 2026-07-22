import importlib.util
import sys
from pathlib import Path

import pytest


def load_importer_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = (
        repo_root / "analytics" / "scripts" / "ingestion" / "import_content_metadata_from_preview.py"
    )
    spec = importlib.util.spec_from_file_location(
        "import_content_metadata_from_preview",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_content_metadata_from_preview"] = module
    spec.loader.exec_module(module)
    return module


def load_fetch_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "analytics" / "scripts" / "ingestion" / "fetch_tmdb_sample.py"
    spec = importlib.util.spec_from_file_location("fetch_tmdb_sample", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_tmdb_sample"] = module
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


def test_preview_record_maps_original_title_and_language_code():
    importer = load_importer_module()
    stats = importer.ImportStats(
        mode="DRY RUN",
        preview_path="analytics/processed/tmdb/sample_mapping_preview.json",
    )

    record = importer.preview_record_from_item(
        {
            "title": "Parasite",
            "content_type": "movie",
            "tmdb_id": 496243,
            "original_title": "기생충",
            "original_language": "ko",
            "status": "Released",
        },
        1,
        stats,
    )

    assert record.content_values["original_title"] == "기생충"
    assert record.content_values["original_language"] == "ko"
    assert record.content_values["language"] == "Korean"


def test_preview_record_maps_series_original_name_fallback():
    importer = load_importer_module()
    stats = importer.ImportStats(
        mode="DRY RUN",
        preview_path="analytics/processed/tmdb/sample_mapping_preview.json",
    )

    record = importer.preview_record_from_item(
        {
            "title": "Localized Series",
            "content_type": "series",
            "tmdb_id": 1234567,
            "original_name": "原題シリーズ",
            "original_language": "ja",
            "status": "Ended",
            "series_metadata": {},
        },
        1,
        stats,
    )

    assert record.content_values["original_title"] == "原題シリーズ"
    assert record.content_values["original_language"] == "ja"
    assert record.content_values["language"] == "Japanese"


def test_original_title_and_language_fill_empty_existing_values():
    importer = load_importer_module()
    stats = importer.ImportStats(
        mode="DRY RUN",
        preview_path="analytics/processed/tmdb/sample_mapping_preview.json",
    )
    record = preview_record(importer)
    record.content_values["original_title"] = "Original Bear"
    record.content_values["original_language"] = "en"

    updates = importer.content_update_plan(
        {"original_title": None, "original_language": None},
        record,
        stats,
    )

    assert updates["original_title"] == "Original Bear"
    assert updates["original_language"] == "en"
    assert stats.conflicts_preserved == 0


def test_original_title_preserves_existing_conflict_behavior():
    importer = load_importer_module()
    stats = importer.ImportStats(
        mode="DRY RUN",
        preview_path="analytics/processed/tmdb/sample_mapping_preview.json",
    )
    record = preview_record(importer)
    record.content_values["original_title"] = "Preview Original"

    updates = importer.content_update_plan(
        {"original_title": "Curated Original"},
        record,
        stats,
    )

    assert "original_title" not in updates
    assert stats.conflicts_preserved == 1
    assert any(
        "existing content.original_title differs from preview; preserved existing value"
        in warning
        for warning in stats.warnings
    )


def test_fetch_preview_includes_original_movie_and_series_titles():
    fetcher = load_fetch_module()
    configuration = {"images": {"secure_base_url": "https://image.tmdb.org/t/p/"}}

    movie_preview = fetcher.map_tmdb_movie_preview(
        {
            "id": 496243,
            "title": "Parasite",
            "original_title": "기생충",
            "original_language": "ko",
            "release_date": "2019-05-30",
            "genres": [],
        },
        {},
        {"cast": [], "crew": []},
        configuration,
        [],
    )
    series_preview = fetcher.map_tmdb_tv_preview(
        {
            "id": 123,
            "name": "Localized Series",
            "original_name": "原題シリーズ",
            "original_language": "ja",
            "first_air_date": "2024-01-01",
            "episode_run_time": [],
            "genres": [],
        },
        {},
        {"cast": [], "crew": []},
        configuration,
        [],
    )

    assert movie_preview["original_title"] == "기생충"
    assert movie_preview["original_language"] == "ko"
    assert series_preview["original_title"] == "原題シリーズ"
    assert series_preview["original_language"] == "ja"


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


def test_content_field_updates_are_tracked_and_printed(capsys):
    importer = load_importer_module()
    stats = importer.ImportStats(
        mode="DRY RUN",
        preview_path="analytics/processed/tmdb/sample_mapping_preview.json",
    )
    existing = {
        "id": 12,
        "status": "Ongoing",
        "latest_activity_date": "2024-07-19",
    }
    record = preview_record(importer, status="Ended")
    record.content_values["latest_activity_date"] = "2025-06-27"

    updates = importer.content_update_plan(existing, record, stats)
    importer.record_updated_content_row(
        stats,
        existing["id"],
        record.title,
        existing,
        updates,
    )
    stats.content_fields_updated += len(updates)
    for field_name in updates:
        stats.field_updates[field_name] += 1
        if field_name == "latest_activity_date":
            stats.latest_activity_date_updates += 1

    importer.print_summary(stats)
    output = capsys.readouterr().out

    assert "- Content fields updated: 2" in output
    assert "Would update content rows:" in output
    assert "- The Bear [id=12]" in output
    assert "  - status: Ongoing -> Ended" in output
    assert "  - latest_activity_date: 2024-07-19 -> 2025-06-27" in output


def test_series_metadata_updates_are_tracked_and_printed(capsys):
    importer = load_importer_module()
    stats = importer.ImportStats(
        mode="APPLY",
        preview_path="analytics/processed/tmdb/sample_mapping_preview.json",
    )
    existing = {
        "last_episode_air_date": "2024-07-19",
        "last_air_date": "2024-07-19",
    }
    updates = {
        "last_episode_air_date": "2025-06-27",
        "last_air_date": "2025-06-27",
    }

    importer.record_updated_series_metadata_row(
        stats,
        12,
        "Silo",
        existing,
        updates,
    )
    stats.series_metadata_updated = 1

    importer.print_summary(stats)
    output = capsys.readouterr().out

    assert "- Series metadata rows updated: 1" in output
    assert "Updated series metadata rows:" in output
    assert "- Silo [id=12]" in output
    assert "  - last_episode_air_date: 2024-07-19 -> 2025-06-27" in output
    assert "  - last_air_date: 2024-07-19 -> 2025-06-27" in output


def test_inserted_rows_are_tracked_and_printed(capsys):
    importer = load_importer_module()
    stats = importer.ImportStats(
        mode="APPLY",
        preview_path="analytics/processed/tmdb/sample_mapping_preview.json",
    )

    importer.record_inserted_content_row(stats, 42, "New Series")
    importer.record_inserted_series_metadata_row(stats, 42, "New Series")
    stats.content_inserted = 1
    stats.series_metadata_inserted = 1

    importer.print_summary(stats)
    output = capsys.readouterr().out

    assert "- Content inserted: 1" in output
    assert "- Series metadata rows inserted: 1" in output
    assert "Inserted content rows:" in output
    assert "- New Series [id=42]" in output
    assert "Inserted series metadata rows:" in output


def test_dry_run_inserted_rows_use_pending_id(capsys):
    importer = load_importer_module()
    stats = importer.ImportStats(
        mode="DRY RUN",
        preview_path="analytics/processed/tmdb/sample_mapping_preview.json",
    )

    importer.record_inserted_content_row(stats, None, "Preview Only")
    stats.content_inserted = 1

    importer.print_summary(stats)
    output = capsys.readouterr().out

    assert "Would insert content rows:" in output
    assert "- Preview Only [id=pending]" in output


def test_unchanged_rows_are_not_printed_as_updated(capsys):
    importer = load_importer_module()
    stats = importer.ImportStats(
        mode="DRY RUN",
        preview_path="analytics/processed/tmdb/sample_mapping_preview.json",
    )

    importer.print_summary(stats)
    output = capsys.readouterr().out

    assert "Would update content rows:" not in output
    assert "Would update series metadata rows:" not in output
