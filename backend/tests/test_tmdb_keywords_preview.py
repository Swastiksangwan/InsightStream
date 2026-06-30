import importlib.util
import sys
from pathlib import Path


def load_tmdb_keywords_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "analytics" / "scripts" / "build_tmdb_keywords_preview.py"
    spec = importlib.util.spec_from_file_location(
        "build_tmdb_keywords_preview",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_tmdb_keywords_preview"] = module
    spec.loader.exec_module(module)
    return module


def test_tmdb_keywords_endpoint_uses_movie_and_tv_paths():
    module = load_tmdb_keywords_module()

    assert module.tmdb_keywords_endpoint("movie", "438631") == "/movie/438631/keywords"
    assert module.tmdb_keywords_endpoint("series", "125988") == "/tv/125988/keywords"
    assert module.tmdb_keywords_endpoint("film", "603") == "/movie/603/keywords"


def test_normalize_keyword_response_supports_movie_keywords_shape():
    module = load_tmdb_keywords_module()

    keywords, raw_count = module.normalize_keyword_response(
        {
            "id": 438631,
            "keywords": [
                {"id": 4565, "name": "dystopia"},
                {"id": 9715, "name": "superhero"},
            ],
        }
    )

    assert raw_count == 2
    assert keywords == [
        {"keyword_id": 4565, "keyword_name": "dystopia"},
        {"keyword_id": 9715, "keyword_name": "superhero"},
    ]


def test_normalize_keyword_response_supports_tv_results_shape():
    module = load_tmdb_keywords_module()

    keywords, raw_count = module.normalize_keyword_response(
        {
            "id": 125988,
            "results": [
                {"id": 818, "name": "based on novel or book"},
                {"id": 9882, "name": "space"},
            ],
        }
    )

    assert raw_count == 2
    assert keywords == [
        {"keyword_id": 818, "keyword_name": "based on novel or book"},
        {"keyword_id": 9882, "keyword_name": "space"},
    ]


def test_normalize_keyword_response_dedupes_repeated_keywords():
    module = load_tmdb_keywords_module()

    keywords, raw_count = module.normalize_keyword_response(
        {
            "keywords": [
                {"id": 4565, "name": " dystopia "},
                {"id": 4565, "name": "dystopia"},
                {"id": None, "name": "Survival"},
                {"name": "survival"},
                {"id": 11, "name": ""},
            ],
        }
    )

    assert raw_count == 5
    assert keywords == [
        {"keyword_id": 4565, "keyword_name": "dystopia"},
        {"keyword_id": None, "keyword_name": "Survival"},
    ]


def test_build_run_report_calculates_keyword_counters(tmp_path):
    module = load_tmdb_keywords_module()
    selected_titles = [
        module.LocalTitle(1, "Dune", "movie", "438631"),
        module.LocalTitle(2, "Silo", "series", "125988"),
        module.LocalTitle(3, "No TMDb", "movie", None),
    ]
    items = [
        {
            "content_id": 1,
            "title": "Dune",
            "content_type": "movie",
            "tmdb_id": "438631",
            "fetch_status": "success",
            "keyword_count": 2,
            "keywords": [
                {"keyword_id": 4565, "keyword_name": "dystopia"},
                {"keyword_id": 9882, "keyword_name": "space"},
            ],
            "raw_keyword_count": 2,
            "fetched_at": "2026-06-29T00:00:00+00:00",
        },
        {
            "content_id": 2,
            "title": "Silo",
            "content_type": "series",
            "tmdb_id": "125988",
            "fetch_status": "success",
            "keyword_count": 0,
            "keywords": [],
            "raw_keyword_count": 0,
            "fetched_at": "2026-06-29T00:00:00+00:00",
        },
        {
            "content_id": 4,
            "title": "Missing",
            "content_type": "movie",
            "tmdb_id": "999",
            "fetch_status": "failed",
            "error_status_code": 404,
            "error_message": "not found",
            "fetched_at": "2026-06-29T00:00:00+00:00",
        },
    ]

    report = module.build_run_report(
        generated_at="2026-06-29T00:00:00+00:00",
        total_local_titles_checked=3,
        selected_titles=selected_titles,
        items=items,
        output_path=tmp_path / "preview.json",
        report_path=tmp_path / "report.json",
    )

    assert report["db_write_performed"] is False
    assert report["total_local_titles_checked"] == 3
    assert report["total_titles_selected"] == 3
    assert report["titles_with_tmdb_id"] == 2
    assert report["titles_without_tmdb_id"] == 1
    assert report["successful_fetches"] == 2
    assert report["failed_fetches"] == 1
    assert report["titles_with_zero_keywords"] == 1
    assert report["total_keywords_fetched"] == 2
    assert report["unique_keywords"] == 2
    assert report["movie_keyword_coverage_percent"] == 100.0
    assert report["series_keyword_coverage_percent"] == 0.0
    assert report["overall_keyword_coverage_percent"] == 50.0
    assert report["errors_by_status_code"] == {"404": 1}


def test_keyword_heuristics_separate_useful_and_noisy_keywords():
    module = load_tmdb_keywords_module()
    items = [
        {
            "fetch_status": "success",
            "keyword_count": 3,
            "keywords": [
                {"keyword_id": 1, "keyword_name": "murder"},
                {"keyword_id": 2, "keyword_name": "sequel"},
                {"keyword_id": 3, "keyword_name": "space opera"},
            ],
        }
    ]

    useful, noisy = module.classify_keywords(items)

    assert {"keyword_name": "murder", "title_count": 1} in useful
    assert {"keyword_name": "space opera", "title_count": 1} in useful
    assert {"keyword_name": "sequel", "title_count": 1} in noisy


def test_tmdb_keywords_transient_error_classification():
    module = load_tmdb_keywords_module()

    assert module.is_transient_fetch_error(
        module.TmdbKeywordFetchError("timeout", transient=True)
    )
    assert module.is_transient_fetch_error(
        module.TmdbKeywordFetchError("rate limit", status_code=429)
    )
    assert module.is_transient_fetch_error(
        module.TmdbKeywordFetchError("service unavailable", status_code=503)
    )
    assert not module.is_transient_fetch_error(
        module.TmdbKeywordFetchError("unauthorized", status_code=401)
    )
    assert not module.is_transient_fetch_error(
        module.TmdbKeywordFetchError("not found", status_code=404)
    )


def test_tmdb_keywords_fetch_retries_transient_failure(monkeypatch):
    module = load_tmdb_keywords_module()
    calls = {"count": 0}

    def fake_fetch_tmdb_json(path, token):
        calls["count"] += 1
        if calls["count"] == 1:
            raise module.TmdbKeywordFetchError("timeout", transient=True)
        return {"keywords": [{"id": 1, "name": "dream"}]}

    monkeypatch.setattr(module, "fetch_tmdb_json", fake_fetch_tmdb_json)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    item = module.fetch_keywords_for_title(
        module.LocalTitle(1, "Inception", "movie", "27205"),
        token="test-token",
        fetched_at="2026-06-30T00:00:00+00:00",
        max_retries=2,
    )

    assert item["fetch_status"] == "success"
    assert item["attempt_count"] == 2
    assert item["retry_performed"] is True
    assert item["retry_attempts_performed"] == 1


def test_tmdb_keywords_retry_targets_from_failed_rows():
    module = load_tmdb_keywords_module()
    retry_targets = module.build_retry_targets(
        [
            {
                "content_id": 6,
                "title": "Inception",
                "content_type": "movie",
                "tmdb_id": "27205",
                "fetch_status": "failed",
                "error_message": "timeout",
                "error_status_code": None,
            },
            {
                "content_id": 7,
                "title": "Dune",
                "content_type": "movie",
                "tmdb_id": "438631",
                "fetch_status": "success",
            },
        ],
        "2026-06-30T00:00:00+00:00",
    )

    assert retry_targets["targets"] == [
        {
            "content_id": 6,
            "title": "Inception",
            "content_type": "movie",
            "source_name": "tmdb",
            "source_id": "27205",
            "previous_error_message": "timeout",
            "previous_error_status_code": None,
        }
    ]
