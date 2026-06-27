import gzip
import importlib.util
import sys
from datetime import datetime
from pathlib import Path


def load_imdb_importer_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "analytics" / "scripts" / "import_imdb_ratings.py"
    spec = importlib.util.spec_from_file_location("import_imdb_ratings", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_imdb_ratings"] = module
    spec.loader.exec_module(module)
    return module


def write_ratings_tsv(path, rows):
    lines = ["tconst\taverageRating\tnumVotes"]
    lines.extend(f"{row[0]}\t{row[1]}\t{row[2]}" for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_imdb_importer_normalizes_rating_row():
    importer = load_imdb_importer_module()
    stats = importer.ImportStats(mode="DRY RUN", ratings_file="ratings.tsv")

    record = importer.imdb_rating_from_row(
        {"tconst": "tt15398776", "averageRating": "8.3", "numVotes": "6226"},
        datetime(2026, 6, 25),
        stats,
    )

    assert record is not None
    assert record.tconst == "tt15398776"
    assert record.raw_score == 8.3
    assert record.raw_score_scale == 10
    assert record.normalized_score == 83
    assert record.vote_count == 6226
    assert record.rating_count_label == "6,226 votes"
    assert record.rating_url == "https://www.imdb.com/title/tt15398776/"
    assert record.source_payload == {
        "tconst": "tt15398776",
        "averageRating": 8.3,
        "numVotes": 6226,
    }


def test_imdb_importer_clamps_normalized_score():
    importer = load_imdb_importer_module()
    stats = importer.ImportStats(mode="DRY RUN", ratings_file="ratings.tsv")

    record = importer.imdb_rating_from_row(
        {"tconst": "tt9999999", "averageRating": "12", "numVotes": "100"},
        datetime(2026, 6, 25),
        stats,
    )

    assert record is not None
    assert record.normalized_score == 100


def test_imdb_importer_scans_only_catalog_imdb_ids(tmp_path):
    importer = load_imdb_importer_module()
    ratings_path = tmp_path / "title.ratings.tsv"
    write_ratings_tsv(
        ratings_path,
        [
            ("tt0133093", "8.7", "2100000"),
            ("tt9999999", "9.9", "1"),
        ],
    )
    stats = importer.ImportStats(mode="DRY RUN", ratings_file=str(ratings_path))

    matched = importer.scan_imdb_ratings_file(
        ratings_path,
        {"tt0133093"},
        stats,
        datetime(2026, 6, 25),
    )

    assert stats.dataset_rows_scanned == 2
    assert set(matched) == {"tt0133093"}
    assert matched["tt0133093"].normalized_score == 87


def test_imdb_importer_does_not_title_match_unmatched_tconst(tmp_path):
    importer = load_imdb_importer_module()
    ratings_path = tmp_path / "title.ratings.tsv"
    write_ratings_tsv(ratings_path, [("tt9999999", "9.9", "1")])
    stats = importer.ImportStats(mode="DRY RUN", ratings_file=str(ratings_path))

    matched = importer.scan_imdb_ratings_file(
        ratings_path,
        {"tt0133093"},
        stats,
        datetime(2026, 6, 25),
    )

    assert matched == {}
    assert stats.matched_imdb_ratings == 0


def test_imdb_importer_supports_gzip_fixture(tmp_path):
    importer = load_imdb_importer_module()
    ratings_path = tmp_path / "title.ratings.tsv.gz"
    payload = "tconst\taverageRating\tnumVotes\ntt0111161\t9.3\t3000000\n"
    with gzip.open(ratings_path, "wt", encoding="utf-8", newline="") as file_obj:
        file_obj.write(payload)
    stats = importer.ImportStats(mode="DRY RUN", ratings_file=str(ratings_path))

    matched = importer.scan_imdb_ratings_file(
        ratings_path,
        {"tt0111161"},
        stats,
        datetime(2026, 6, 25),
    )

    assert stats.dataset_rows_scanned == 1
    assert matched["tt0111161"].vote_count == 3000000


def test_imdb_importer_detects_rating_updates():
    importer = load_imdb_importer_module()
    rating = importer.ImdbRatingRecord(
        tconst="tt0133093",
        raw_score=8.7,
        raw_score_scale=10,
        normalized_score=87,
        vote_count=2100000,
        rating_count_label="2,100,000 votes",
        rating_url="https://www.imdb.com/title/tt0133093/",
        source_payload={
            "tconst": "tt0133093",
            "averageRating": 8.7,
            "numVotes": 2100000,
        },
        fetched_at=datetime(2026, 6, 25),
    )

    updates = importer.rating_update_plan(
        {
            "raw_score": 8.6,
            "raw_score_scale": 10,
            "normalized_score": 86,
            "vote_count": 2000000,
            "rating_count_label": "2,000,000 votes",
            "rating_url": None,
            "source_payload": {
                "tconst": "tt0133093",
                "averageRating": 8.6,
                "numVotes": 2000000,
            },
        },
        rating,
    )

    assert updates["raw_score"] == 8.7
    assert updates["normalized_score"] == 87
    assert updates["vote_count"] == 2100000
    assert updates["source_payload"] == rating.source_payload


def test_imdb_importer_updates_existing_rating_missing_url():
    importer = load_imdb_importer_module()
    rating = importer.ImdbRatingRecord(
        tconst="tt0133093",
        raw_score=8.7,
        raw_score_scale=10,
        normalized_score=87,
        vote_count=2100000,
        rating_count_label="2,100,000 votes",
        rating_url="https://www.imdb.com/title/tt0133093/",
        source_payload={
            "tconst": "tt0133093",
            "averageRating": 8.7,
            "numVotes": 2100000,
        },
        fetched_at=datetime(2026, 6, 25),
    )

    updates = importer.rating_update_plan(
        {
            "raw_score": 8.7,
            "raw_score_scale": 10,
            "normalized_score": 87,
            "vote_count": 2100000,
            "rating_count_label": "2,100,000 votes",
            "rating_url": None,
            "source_payload": {
                "tconst": "tt0133093",
                "averageRating": 8.7,
                "numVotes": 2100000,
            },
        },
        rating,
    )

    assert updates["rating_url"] == "https://www.imdb.com/title/tt0133093/"
