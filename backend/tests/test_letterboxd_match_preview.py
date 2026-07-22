import importlib.util
import json
import sys
from pathlib import Path


def load_letterboxd_preview_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = (
        repo_root / "analytics" / "scripts" / "ingestion" / "preview_letterboxd_ratings_match.py"
    )
    spec = importlib.util.spec_from_file_location(
        "preview_letterboxd_ratings_match",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["preview_letterboxd_ratings_match"] = module
    spec.loader.exec_module(module)
    return module


def local_movie(title="Oppenheimer", year=2023, directors=None):
    module = load_letterboxd_preview_module()
    return module.LocalMovie(
        content_id=123,
        title=title,
        year=year,
        directors=directors if directors is not None else ["Christopher Nolan"],
        external_ids={"tmdb": "872585", "imdb": "tt15398776"},
    )


def letterboxd_movie(title="Oppenheimer", year=2023, directors=None, rating=4.2):
    module = load_letterboxd_preview_module()
    return module.LetterboxdMovie(
        line_number=1,
        url="https://letterboxd.com/film/oppenheimer-2023/",
        title=title,
        normalized_title=module.normalize_title(title),
        year=year,
        directors=directors if directors is not None else ["Christopher Nolan"],
        raw_score=rating,
        raw_score_scale=5,
        normalized_score=rating / 5 * 100 if rating is not None else None,
        vote_count=None,
        warnings=[],
    )


def test_letterboxd_rating_parser_normalizes_score():
    module = load_letterboxd_preview_module()

    raw_score, raw_scale, normalized_score, warning = module.parse_letterboxd_rating(
        "4.62 out of 5"
    )

    assert raw_score == 4.62
    assert raw_scale == 5
    assert normalized_score == 92.4
    assert warning is None


def test_letterboxd_title_normalization_removes_articles_and_punctuation():
    module = load_letterboxd_preview_module()

    assert module.normalize_title("The Matrix: Reloaded!") == "matrix reloaded"
    assert module.normalize_title("An Education") == "education"
    assert module.normalize_title("Spider-Man: No Way Home") == "spider man no way home"


def test_letterboxd_high_confidence_match_by_title_year_director():
    module = load_letterboxd_preview_module()
    local = local_movie()
    candidate = letterboxd_movie()

    decision = module.match_local_movie(
        local,
        {candidate.normalized_title: [candidate]},
    )

    assert decision.match_status == "high_confidence"
    assert decision.confidence_score == 0.95
    assert decision.import_ready is True


def test_letterboxd_good_match_when_director_missing_on_one_side():
    module = load_letterboxd_preview_module()
    local = local_movie(directors=[])
    candidate = letterboxd_movie()

    decision = module.match_local_movie(
        local,
        {candidate.normalized_title: [candidate]},
    )

    assert decision.match_status == "good_confidence"
    assert decision.confidence_score == 0.88
    assert decision.import_ready is False


def test_letterboxd_ambiguous_when_multiple_candidates_exist():
    module = load_letterboxd_preview_module()
    local = local_movie()
    candidate_one = letterboxd_movie()
    candidate_two = letterboxd_movie(directors=["Different Director"])

    decision = module.match_local_movie(
        local,
        {candidate_one.normalized_title: [candidate_one, candidate_two]},
        include_ambiguous=True,
    )

    assert decision.match_status == "ambiguous"
    assert decision.import_ready is False
    assert len(decision.candidates) == 2


def test_letterboxd_unmatched_local_title():
    module = load_letterboxd_preview_module()

    decision = module.match_local_movie(local_movie(title="Missing Movie"), {})

    assert decision.match_status == "unmatched"
    assert decision.letterboxd is None
    assert decision.import_ready is False


def test_letterboxd_dataset_reader_warns_on_malformed_json(tmp_path):
    module = load_letterboxd_preview_module()
    dataset_path = tmp_path / "letterboxd_movies.jsonl"
    dataset_path.write_text(
        '{"title": "Oppenheimer", "year": "2023", "directors": ["Christopher Nolan"], "rating": "4.2 out of 5"}\n'
        "{not json}\n",
        encoding="utf-8",
    )
    stats = module.DatasetStats()

    candidates = module.read_letterboxd_dataset(
        dataset_path,
        {"oppenheimer"},
        stats,
    )

    assert stats.dataset_rows_scanned == 2
    assert stats.malformed_rows == 1
    assert stats.warnings
    assert "oppenheimer" in candidates


def test_letterboxd_preview_output_contains_no_review_text(tmp_path):
    module = load_letterboxd_preview_module()
    dataset_path = tmp_path / "letterboxd_movies.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "title": "Oppenheimer",
                "year": "2023",
                "directors": ["Christopher Nolan"],
                "rating": "4.2 out of 5",
                "reviews": ["This review text should never appear."],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    stats = module.DatasetStats()
    candidates = module.read_letterboxd_dataset(dataset_path, {"oppenheimer"}, stats)
    preview, report = module.build_preview_and_report(
        [local_movie()],
        candidates,
        stats,
        dataset_path,
        tmp_path,
    )

    serialized_preview = json.dumps(preview)
    serialized_report = json.dumps(report)
    assert "This review text should never appear." not in serialized_preview
    assert "This review text should never appear." not in serialized_report
    assert preview["high_confidence_count"] == 1


def test_letterboxd_preview_script_has_no_database_write_sql():
    repo_root = Path(__file__).resolve().parents[2]
    script_text = (
        repo_root / "analytics" / "scripts" / "ingestion" / "preview_letterboxd_ratings_match.py"
    ).read_text(encoding="utf-8")
    upper_script = script_text.upper()

    assert "INSERT INTO" not in upper_script
    assert "UPDATE " not in upper_script
    assert "DELETE FROM" not in upper_script
    assert "ALTER TABLE" not in upper_script
