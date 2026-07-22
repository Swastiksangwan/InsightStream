import importlib.util
import sys
from pathlib import Path


def load_health_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "analytics" / "scripts" / "audits" / "check_ingestion_health.py"
    spec = importlib.util.spec_from_file_location("check_ingestion_health", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_ingestion_health"] = module
    spec.loader.exec_module(module)
    return module


def test_tmdb_keyword_health_summary_reports_coverage(monkeypatch):
    health = load_health_module()

    def fake_fetch_rows(_connection, query, _params=None):
        if "FROM keyword_sources" in query and "COUNT(*) FILTER" in query:
            return [{"tmdb_keyword_source_count": 1}]
        if "FROM provider_keywords" in query and "COUNT(*) AS provider_keyword_row_count" in query:
            return [{"provider_keyword_row_count": 42}]
        if "FROM content_keywords ck" in query and "MAX(last_seen_at)" in query:
            return [
                {
                    "content_keyword_relationship_count": 100,
                    "latest_keyword_import_timestamp": "2026-07-01T12:00:00",
                }
            ]
        if "content_with_tmdb_external_id" in query:
            return [
                {
                    "content_with_tmdb_external_id": 150,
                    "movie_content_with_tmdb_external_id": 80,
                    "series_content_with_tmdb_external_id": 70,
                    "content_with_imported_tmdb_keywords": 149,
                    "movie_content_with_imported_tmdb_keywords": 80,
                    "series_content_with_imported_tmdb_keywords": 69,
                }
            ]
        if "HAVING COUNT(ck.id) = 0" in query:
            return [
                {
                    "content_id": 7,
                    "title": "Missing Keywords",
                    "content_type": "series",
                    "tmdb_id": "12345",
                }
            ]
        return []

    monkeypatch.setattr(health, "fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(
        health,
        "load_tmdb_keywords_preview_report",
        lambda: {"report_exists": True, "failed_preview_rows": 0},
    )

    summary, warnings, failures = health.tmdb_keyword_summary(
        object(),
        {
            "keyword_sources": {"id"},
            "provider_keywords": {"id"},
            "content_keywords": {"id"},
        },
        expect_tmdb_keywords=True,
    )

    assert summary["tmdb_keyword_source_count"] == 1
    assert summary["provider_keyword_row_count"] == 42
    assert summary["content_keyword_relationship_count"] == 100
    assert summary["overall_keyword_coverage_percent"] == 99.33
    assert summary["movie_keyword_coverage_percent"] == 100.0
    assert summary["series_keyword_coverage_percent"] == 98.57
    assert summary["titles_with_zero_imported_keywords"] == 1
    assert warnings
    assert failures == []


def test_tmdb_keyword_health_summary_fails_when_expected_tables_missing():
    health = load_health_module()

    summary, warnings, failures = health.tmdb_keyword_summary(
        object(),
        {
            "keyword_sources": set(),
            "provider_keywords": set(),
            "content_keywords": set(),
        },
        expect_tmdb_keywords=True,
    )

    assert summary["keyword_tables_present"] is False
    assert "keyword_sources" in summary["missing_keyword_tables"]
    assert warnings == []
    assert failures


def test_source_signal_health_summary_reports_coverage(monkeypatch):
    health = load_health_module()

    def fake_fetch_rows(_connection, query, _params=None):
        if "FROM source_signal_import_runs" in query:
            return [{"source_signal_import_run_count": 1}]
        if "source_signal_ready_content" in query:
            return [
                {
                    "source_signal_ready_content": 150,
                    "content_with_watch_guidance": 150,
                    "content_with_active_source_signals": 150,
                    "frontend_ready_guidance_count": 0,
                    "active_source_signal_count": 620,
                }
            ]
        if "FROM content_source_signals" in query and "HAVING COUNT(*) > 1" in query:
            return []
        if "missing_source_signal_details" in query:
            return []
        if "JOIN content_keywords" in query and "HAVING" in query:
            return []
        return []

    monkeypatch.setattr(health, "fetch_rows", fake_fetch_rows)

    summary, warnings, failures = health.source_signal_summary(
        object(),
        {
            "source_signal_import_runs": {"id"},
            "content_source_signals": {"id"},
            "content_watch_guidance": {"content_id"},
        },
        expect_source_signals=True,
    )

    assert summary["source_signal_tables_present"] is True
    assert summary["source_signal_import_run_count"] == 1
    assert summary["source_signal_guidance_coverage_percent"] == 100.0
    assert summary["source_signal_active_signal_coverage_percent"] == 100.0
    assert warnings == []
    assert failures == []


def test_source_signal_health_summary_fails_when_expected_tables_missing():
    health = load_health_module()

    summary, warnings, failures = health.source_signal_summary(
        object(),
        {
            "source_signal_import_runs": set(),
            "content_source_signals": set(),
            "content_watch_guidance": set(),
        },
        expect_source_signals=True,
    )

    assert summary["source_signal_tables_present"] is False
    assert "content_source_signals" in summary["missing_source_signal_tables"]
    assert warnings == []
    assert failures
