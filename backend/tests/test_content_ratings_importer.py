import importlib.util
import sys
from datetime import datetime
from pathlib import Path


def load_ratings_importer_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = (
        repo_root
        / "analytics"
        / "scripts"
        / "import_content_ratings_from_preview.py"
    )
    spec = importlib.util.spec_from_file_location(
        "import_content_ratings_from_preview",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_content_ratings_from_preview"] = module
    spec.loader.exec_module(module)
    return module


def test_rating_importer_calculates_normalized_score_when_missing():
    importer = load_ratings_importer_module()
    stats = importer.ImportStats(mode="DRY RUN", preview_path="preview.json")

    record = importer.rating_record_from_preview(
        {
            "source_name": "tmdb",
            "display_name": "TMDb",
            "source_category": "audience",
            "raw_score": 8.4,
            "raw_score_scale": 10,
            "normalized_score": None,
            "vote_count": 12000,
            "rating_count_label": "12,000 votes",
            "source_payload": {"vote_average": 8.4, "vote_count": 12000},
        },
        "Example",
        datetime(2026, 6, 25),
        stats,
    )

    assert record is not None
    assert record.normalized_score == 84
    assert record.vote_count == 12000
    assert stats.skipped_ratings == 0


def test_rating_importer_clamps_normalized_score():
    importer = load_ratings_importer_module()
    stats = importer.ImportStats(mode="DRY RUN", preview_path="preview.json")

    record = importer.rating_record_from_preview(
        {
            "source_name": "tmdb",
            "raw_score": 12,
            "raw_score_scale": 10,
            "normalized_score": 120,
        },
        "Example",
        datetime(2026, 6, 25),
        stats,
    )

    assert record is not None
    assert record.normalized_score == 100


def test_rating_importer_skips_non_tmdb_sources_for_v1():
    importer = load_ratings_importer_module()
    stats = importer.ImportStats(mode="DRY RUN", preview_path="preview.json")

    record = importer.rating_record_from_preview(
        {
            "source_name": "imdb",
            "raw_score": 8.7,
            "raw_score_scale": 10,
            "normalized_score": 87,
        },
        "Example",
        datetime(2026, 6, 25),
        stats,
    )

    assert record is None
    assert stats.skipped_ratings == 1
    assert stats.warnings
