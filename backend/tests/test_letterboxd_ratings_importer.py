import importlib.util
import sys
from datetime import datetime
from pathlib import Path


def load_letterboxd_importer_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = (
        repo_root / "analytics" / "scripts" / "ingestion" / "import_letterboxd_ratings_from_preview.py"
    )
    spec = importlib.util.spec_from_file_location(
        "import_letterboxd_ratings_from_preview",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_letterboxd_ratings_from_preview"] = module
    spec.loader.exec_module(module)
    return module


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class FakeConnection:
    def __init__(self, existing_rating=None):
        self.existing_rating = existing_rating
        self.write_queries = []

    def execute(self, query, params=None):
        query_text = str(query)
        if "INSERT INTO" in query_text or "UPDATE " in query_text:
            self.write_queries.append(query_text)
            return FakeResult()
        if "FROM rating_sources" in query_text:
            return FakeResult(
                {
                    "id": 44,
                    "display_name": "Letterboxd",
                    "source_category": "audience",
                    "raw_score_scale_default": 5,
                    "weight": 0,
                    "is_active": True,
                }
            )
        if "FROM content_ratings" in query_text:
            return FakeResult(self.existing_rating)
        if "FROM content" in query_text:
            return FakeResult(
                {"id": params["content_id"], "title": "Oppenheimer", "content_type": "movie"}
            )
        return FakeResult()


def preview_item(match_status="high_confidence"):
    return {
        "content_id": 123,
        "local_title": "Oppenheimer",
        "local_year": 2023,
        "local_directors": ["Christopher Nolan"],
        "match_status": match_status,
        "confidence_score": 0.95 if match_status == "high_confidence" else 0.7,
        "letterboxd": {
            "title": "Oppenheimer",
            "year": 2023,
            "directors": ["Christopher Nolan"],
            "url": "https://letterboxd.com/film/oppenheimer-2023/",
            "raw_score": 4.62,
            "raw_score_scale": 5,
            "normalized_score": 92.4,
            "vote_count": None,
        },
        "warnings": [],
    }


def preview_payload(items):
    return {
        "generated_at": "2026-06-28T12:00:00+00:00",
        "dataset_file": "analytics/datasets/letterboxd/letterboxd_movies.jsonl",
        "items": items,
    }


def test_letterboxd_importer_maps_rating_from_preview():
    importer = load_letterboxd_importer_module()
    stats = importer.ImportStats(mode="DRY RUN", preview_path="preview.json")

    record = importer.rating_record_from_preview_item(
        preview_item(),
        datetime(2026, 6, 28),
        include_ambiguous=False,
        dataset_file="dataset.jsonl",
        stats=stats,
    )

    assert record is not None
    assert record.raw_score == 4.62
    assert record.raw_score_scale == 5
    assert record.normalized_score == 92.4
    assert record.vote_count is None
    assert record.rating_count_label is None
    assert record.rating_url == "https://letterboxd.com/film/oppenheimer-2023/"
    assert record.source_payload == {
        "title": "Oppenheimer",
        "year": 2023,
        "directors": ["Christopher Nolan"],
        "url": "https://letterboxd.com/film/oppenheimer-2023/",
        "match_status": "high_confidence",
        "confidence_score": 0.95,
        "dataset_snapshot_source": "dataset.jsonl",
    }


def test_letterboxd_importer_skips_ambiguous_by_default():
    importer = load_letterboxd_importer_module()
    stats = importer.ImportStats(mode="DRY RUN", preview_path="preview.json")

    record = importer.rating_record_from_preview_item(
        preview_item("ambiguous"),
        datetime(2026, 6, 28),
        include_ambiguous=False,
        dataset_file="dataset.jsonl",
        stats=stats,
    )

    assert record is None
    assert stats.skipped_ambiguous_rows == 1


def test_letterboxd_importer_imports_ambiguous_when_enabled():
    importer = load_letterboxd_importer_module()
    stats = importer.ImportStats(mode="DRY RUN", preview_path="preview.json")

    record = importer.rating_record_from_preview_item(
        preview_item("ambiguous"),
        datetime(2026, 6, 28),
        include_ambiguous=True,
        dataset_file="dataset.jsonl",
        stats=stats,
    )

    assert record is not None
    assert record.match_status == "ambiguous"
    assert stats.selected_ambiguous_rows == 1


def test_letterboxd_importer_skips_unmatched():
    importer = load_letterboxd_importer_module()
    stats = importer.ImportStats(mode="DRY RUN", preview_path="preview.json")

    record = importer.rating_record_from_preview_item(
        {**preview_item("unmatched"), "letterboxd": None},
        datetime(2026, 6, 28),
        include_ambiguous=True,
        dataset_file="dataset.jsonl",
        stats=stats,
    )

    assert record is None
    assert stats.skipped_unmatched_rows == 1


def test_letterboxd_importer_dry_run_does_not_write():
    importer = load_letterboxd_importer_module()
    conn = FakeConnection()

    stats = importer.process_preview(
        conn,
        preview_payload([preview_item()]),
        Path("preview.json"),
        include_ambiguous=False,
        apply=False,
    )

    assert stats.inserted_ratings == 1
    assert conn.write_queries == []


def test_letterboxd_importer_apply_writes_matching_rating():
    importer = load_letterboxd_importer_module()
    conn = FakeConnection()

    stats = importer.process_preview(
        conn,
        preview_payload([preview_item()]),
        Path("preview.json"),
        include_ambiguous=False,
        apply=True,
    )

    assert stats.inserted_ratings == 1
    assert any("INSERT INTO content_ratings" in query for query in conn.write_queries)


def test_letterboxd_importer_is_idempotent_when_existing_matches():
    importer = load_letterboxd_importer_module()
    conn = FakeConnection(
        existing_rating={
            "id": 1,
            "raw_score": 4.62,
            "raw_score_scale": 5,
            "normalized_score": 92.4,
            "vote_count": None,
            "rating_count_label": None,
            "rating_url": "https://letterboxd.com/film/oppenheimer-2023/",
            "source_payload": {
                "title": "Oppenheimer",
                "year": 2023,
                "directors": ["Christopher Nolan"],
                "url": "https://letterboxd.com/film/oppenheimer-2023/",
                "match_status": "high_confidence",
                "confidence_score": 0.95,
                "dataset_snapshot_source": "analytics/datasets/letterboxd/letterboxd_movies.jsonl",
            },
        }
    )

    stats = importer.process_preview(
        conn,
        preview_payload([preview_item()]),
        Path("preview.json"),
        include_ambiguous=False,
        apply=False,
    )

    assert stats.unchanged_ratings == 1
    assert conn.write_queries == []


def test_letterboxd_importer_does_not_store_review_text():
    importer = load_letterboxd_importer_module()
    item = {
        **preview_item(),
        "reviews": ["This review text should not be stored."],
        "letterboxd": {
            **preview_item()["letterboxd"],
            "reviews": ["Nor should this nested review text."],
        },
    }
    stats = importer.ImportStats(mode="DRY RUN", preview_path="preview.json")

    record = importer.rating_record_from_preview_item(
        item,
        datetime(2026, 6, 28),
        include_ambiguous=False,
        dataset_file="dataset.jsonl",
        stats=stats,
    )

    assert record is not None
    assert "review" not in str(record.source_payload).lower()
