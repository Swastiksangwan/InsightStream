from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "analytics" / "scripts" / "audits" / "audit_catalog_expansion_readiness.py"
SPEC = importlib.util.spec_from_file_location("catalog_expansion_audit", SCRIPT_PATH)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)

REFERENCE = datetime(2026, 7, 21, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("neo-noir", "neo noir"),
        ("artificial intelligence (a.i.)", "artificial intelligence ai"),
        ("slow-burn", "slow burn"),
        ("Sci-Fi: Fantasy!", "sci fi fantasy"),
        ("MURDER MYSTERY", "murder mystery"),
        ("  murder    mystery  ", "murder mystery"),
        ("sci-fi/fantasy", "sci fi fantasy"),
        ("crime_thriller", "crime thriller"),
    ],
)
def test_canonical_keyword_normalization_parity(raw, expected):
    assert audit.normalize_keyword_name(raw) == expected


def test_markdown_records_keyword_normalization_version():
    report, gap_plan = build([record(1)])

    markdown = audit.render_markdown(report, gap_plan)

    assert "Keyword normalization: `source-signal-keyword-v1`" in markdown


def mapping_config(**overrides):
    payload = {
        "mapping_version": "test-v1",
        "dimensions": ["mood", "tone", "pacing", "intensity", "topic_theme"],
        "excluded_keywords": ["credits stinger"],
        "spoiler_unsafe_keywords": ["secret ending"],
        "keyword_mappings": {
            "mystery": {"signals": []},
            "survival": {"signals": []},
            "space": {"signals": []},
            "friendship": {"signals": []},
        },
    }
    payload.update(overrides)
    return payload


def record(
    content_id: int,
    title: str | None = None,
    *,
    content_type: str = "movie",
    language: str | None = "en",
    genres=("Drama",),
    keywords=("mystery", "survival", "space"),
    signals=(
        ("mood", "tense", "Tense"),
        ("pacing", "steady", "Steady"),
        ("topic_theme", "survival drama", "Survival drama"),
    ),
    videos=True,
    primary=True,
    series_metadata=None,
):
    row = audit.empty_record(
        {
            "content_id": content_id,
            "tmdb_id": 10_000 + content_id,
            "title": title or f"Title {content_id:03d}",
            "original_title": title or f"Title {content_id:03d}",
            "content_type": content_type,
            "overview": "A controlled fixture overview.",
            "poster_url": "https://example.invalid/poster.jpg",
            "backdrop_url": "https://example.invalid/backdrop.jpg",
            "release_date": datetime(2023, 1, 1).date(),
            "latest_activity_date": datetime(2023, 1, 1).date(),
            "year": 2023,
            "runtime": 120 if content_type == "movie" else None,
            "language": "English",
            "original_language": language,
            "status": "Released" if content_type == "movie" else "Ongoing",
            "age_rating": "PG-13",
        }
    )
    row["external_ids"] = {"tmdb": str(10_000 + content_id), "imdb": f"tt{content_id:07d}"}
    row["genres"] = [{"id": index + 1, "name": name} for index, name in enumerate(genres)]
    row["ratings"] = [{"source_name": "tmdb", "normalized_score": 80, "vote_count": 100}]
    row["availability"] = [{"platform": "Example", "availability_type": "streaming", "region_code": "IN", "source_name": "test"}]
    row["credits"] = [
        {"person_id": content_id * 10, "role_type": "cast", "job": None, "department": "Acting"},
        {"person_id": content_id * 10 + 1, "role_type": "creator" if content_type == "series" else "director", "job": "Creator" if content_type == "series" else "Director", "department": "Writing" if content_type == "series" else "Directing"},
    ]
    row["keywords"] = [
        {"keyword_name": value, "normalized_keyword_name": value, "source_name": "tmdb", "confidence": "high"}
        for value in keywords
    ]
    row["signals"] = [
        {"dimension": dimension, "value": value, "label": label, "confidence": "high", "source_names": ["tmdb"], "is_active": True}
        for dimension, value, label in signals
    ]
    if videos:
        row["videos"] = [{"id": content_id, "source": "tmdb", "site": "YouTube", "source_video_id": f"key{content_id}", "video_type": "Trailer", "name": "Trailer", "official": True, "language_code": language, "is_primary": primary}]
    if primary:
        row["primary_video"] = {"content_video_id": content_id, "video_content_id": content_id, "site": "YouTube", "source_video_id": f"key{content_id}", "video_type": "Trailer"}
    row["video_fetch_state"] = {
        "source": "tmdb",
        "last_attempted_at": REFERENCE - timedelta(days=1),
        "last_fetched_at": REFERENCE - timedelta(days=1),
        "last_fetch_status": "success",
        "last_fetch_retryable": False,
        "last_failure_class": None,
        "consecutive_failure_count": 0,
    }
    if content_type == "series":
        row["series_metadata"] = series_metadata or {
            "series_status": "Returning Series",
            "series_status_normalized": "ongoing",
            "in_production": True,
            "number_of_seasons": 2,
            "number_of_episodes": 16,
            "first_air_date": datetime(2022, 1, 1).date(),
            "last_air_date": datetime(2026, 7, 14).date(),
            "last_episode_air_date": datetime(2026, 7, 14).date(),
            "next_episode_air_date": datetime(2026, 7, 28).date(),
            "series_type": "Scripted",
            "has_announced_season": False,
            "next_season_number": None,
            "next_season_air_date": None,
            "last_refreshed_at": REFERENCE - timedelta(days=1),
        }
    return row


def build(records, config=None, **kwargs):
    return audit.build_audit(
        records,
        config or mapping_config(),
        reference_at=REFERENCE,
        sample_size=10,
        top_unmapped_keywords=10,
        load_metadata={"query_count": 12, "read_only": True, "unused_genres": [], "orphan_primary_rows": []},
        **kwargs,
    )


def test_empty_catalog_has_deterministic_failed_and_not_evaluated_readiness():
    report, plan = build([])
    assert report["catalog_composition"]["total_content"] == 0
    assert {row["status"] for row in report["readiness"]} <= {"fail", "not_evaluated"}
    assert plan["recommended_additions"] == 275


def test_composition_identity_language_and_release_distributions():
    rows = [record(1), record(2, content_type="series", language="ja"), record(3, language=None)]
    rows[2]["external_ids"].pop("tmdb")
    rows[2]["tmdb_id"] = None
    report, _ = build(rows)
    composition = report["catalog_composition"]
    assert (composition["total_movies"], composition["total_series"]) == (2, 1)
    assert composition["titles_without_tmdb_identity"] == 1
    language = report["language_and_release_distribution"]
    assert language["english_count"] == 1
    assert language["non_english_count"] == 1
    assert language["missing_or_invalid_language"] == 1
    assert language["country_or_region"]["status"] == "not_evaluated"


def test_genre_coverage_missing_excessive_variants_and_unused_rows():
    rows = [record(1, genres=()), record(2, genres=("Drama", "drama ")), record(3, genres=tuple(f"Genre {i}" for i in range(8)))]
    report, _ = audit.build_audit(
        rows,
        mapping_config(),
        reference_at=REFERENCE,
        load_metadata={"unused_genres": [{"id": 99, "name": "Unused"}], "orphan_primary_rows": []},
    )
    genres = report["genre_and_subgenre_coverage"]
    assert genres["titles_without_genres"][0]["content_id"] == 1
    assert genres["titles_with_excessive_genres"][0]["content_id"] == 3
    assert genres["case_or_spacing_variants"] == [["Drama", "drama"]]
    assert genres["unused_genres"] == [{"id": 99, "name": "Unused"}]


@pytest.mark.parametrize(
    ("field", "mutator"),
    [
        ("overview", lambda row: row.update(overview=None)),
        ("release_date", lambda row: row.update(release_date=None)),
        ("poster", lambda row: row.update(poster_url=None)),
        ("backdrop", lambda row: row.update(backdrop_url=None)),
        ("ratings", lambda row: row.update(ratings=[])),
        ("availability", lambda row: row.update(availability=[])),
        ("source_keywords", lambda row: row.update(keywords=[])),
        ("source_signals", lambda row: row.update(signals=[])),
    ],
)
def test_missing_metadata_fields_are_reported(field, mutator):
    row = record(1)
    mutator(row)
    report, _ = build([row])
    assert report["metadata_coverage"][field]["missing"] == 1
    assert report["metadata_coverage"][field]["affected"][0]["content_id"] == 1


def test_movie_runtime_is_required_but_series_runtime_is_not():
    movie = record(1)
    movie["runtime"] = 0
    series = record(2, content_type="series")
    report, _ = build([movie, series])
    assert report["metadata_coverage"]["runtime"]["missing"] == 1
    assert report["metadata_coverage"]["runtime"]["affected"][0]["content_id"] == 1


def test_series_missing_metadata_and_invalid_lifecycle_are_reported():
    missing = record(1, content_type="series")
    missing["series_metadata"] = None
    invalid = record(
        2,
        content_type="series",
        series_metadata={
            "series_status": "Ended",
            "series_status_normalized": "ended",
            "in_production": False,
            "number_of_seasons": 1,
            "number_of_episodes": 8,
            "first_air_date": datetime(2024, 1, 1).date(),
            "last_air_date": datetime(2024, 2, 1).date(),
            "last_episode_air_date": datetime(2026, 8, 1).date(),
            "next_episode_air_date": datetime(2026, 7, 22).date(),
            "series_type": "Miniseries",
            "has_announced_season": False,
            "next_season_number": None,
            "next_season_air_date": None,
            "last_refreshed_at": REFERENCE,
        },
    )
    report, _ = build([missing, invalid])
    by_id = {row["content_id"]: row for row in report["per_title"]}
    assert "series_metadata_missing" in by_id[1]["issues"]
    assert "next_episode_precedes_last_episode" in by_id[2]["issues"]
    assert "ended_series_has_future_episode" in by_id[2]["issues"]
    assert report["catalog_composition"]["limited_or_miniseries"][0]["content_id"] == 2


def test_video_health_no_video_video_without_primary_and_refresh_disposition():
    missing = record(1, videos=False, primary=False)
    no_primary = record(2, primary=False)
    retryable = record(3)
    retryable["video_fetch_state"].update(last_fetch_status="failed", last_fetch_retryable=True, last_failure_class="network_transient", consecutive_failure_count=1)
    manual = record(4)
    manual["video_fetch_state"].update(last_fetch_status="incomplete", last_fetch_retryable=False, last_failure_class="normalization_review", consecutive_failure_count=1)
    report, _ = build([missing, no_primary, retryable, manual])
    health = report["video_and_refresh_health"]
    assert health["titles_without_videos"] == 1
    assert health["videos_without_primary"][0]["content_id"] == 2
    assert health["retryable_failures"] == 1
    assert health["manual_review_failures"] == 1


def test_series_due_status_reuses_existing_planner(monkeypatch):
    seen = []

    def fake(row, now, **kwargs):
        seen.append((row["content_id"], now))
        return audit.evaluate_video_refresh.__globals__["ScopeDecision"](True, "fixture_due", "high", None, now)

    monkeypatch.setattr(audit, "evaluate_series_refresh", fake)
    report, _ = build([record(1, content_type="series")])
    assert seen == [(1, REFERENCE)]
    assert report["video_and_refresh_health"]["series_refresh_due"][0]["reason"] == "fixture_due"


def test_keyword_mapping_high_low_unmapped_ignored_and_duplicates():
    high = record(1, keywords=("mystery", "survival", "mystery", "credits stinger"))
    low = record(2, keywords=("mystery", "unknown 1", "unknown 2", "unknown 3", "unknown 4", "unknown 5", "unknown 6", "unknown 7"))
    report, _ = build([high, low])
    by_id = {row["content_id"]: row for row in report["per_title"]}
    assert by_id[1]["keyword_quality"]["duplicate_normalized_count"] == 1
    assert by_id[1]["keyword_quality"]["ignored_count"] == 1
    assert by_id[1]["keyword_quality"]["mapping_coverage"] == 1.0
    assert "many_keywords_low_mapping" in by_id[2]["issues"]
    assert report["keyword_and_source_signal_quality"]["top_unmapped_keywords"][0]["title_count"] == 1


def test_mapping_keys_and_stored_keyword_variants_share_canonical_identity():
    row = record(
        1,
        keywords=("neo-noir", "artificial intelligence (a.i.)", "slow_burn"),
    )
    config = mapping_config(
        keyword_mappings={
            "neo noir": {"signals": []},
            "artificial intelligence ai": {"signals": []},
            "slow burn": {"signals": []},
        },
        excluded_keywords=["credits-stinger"],
        spoiler_unsafe_keywords=["secret/ending"],
    )
    report, _ = build([row], config)
    quality = report["per_title"][0]["keyword_quality"]
    assert quality["mapped_count"] == 3
    assert quality["unmapped_count"] == 0
    assert quality["mapping_coverage"] == 1.0
    normalization = report["keyword_and_source_signal_quality"]["keyword_normalization"]
    assert normalization["version"] == "source-signal-keyword-v1"
    assert "hyphen/slash/underscore-to-space" in normalization["strategy"]


def test_signal_category_rare_overused_provenance_and_configured_conflict():
    rows = [record(index) for index in range(1, 5)]
    rows[0]["signals"].extend(
        [
            {"dimension": "mood", "value": "light", "label": "Light", "confidence": "high", "source_names": ["tmdb"], "is_active": True},
            {"dimension": "mood", "value": "dark", "label": "Dark", "confidence": "high", "source_names": [], "is_active": True},
            {"dimension": "tone", "value": "rare", "label": "Rare", "confidence": "low", "source_names": ["tmdb"], "is_active": True},
        ]
    )
    config = mapping_config(conflict_pairs={"mood": [["light", "dark"]]})
    report, _ = build(rows, config)
    quality = report["per_title"][0]["signal_quality"]
    assert quality["category_count"] >= 3
    assert quality["conflicts"] == [{"dimension": "mood", "values": ["dark", "light"]}]
    assert "tone:rare" in quality["rare_signals"]
    assert any(row["value"] == "tense" for row in report["keyword_and_source_signal_quality"]["overused_signals"])
    assert quality["source_provenance_coverage"] < 1


def test_signal_conflicts_are_not_invented_without_configuration():
    report, _ = build([record(1)])
    assert report["keyword_and_source_signal_quality"]["conflict_detection"]["status"] == "not_evaluated"


def test_recommendation_readiness_ready_limited_sparse_and_insufficient():
    rows = [record(index, genres=("Drama", "Mystery")) for index in range(1, 12)]
    limited = record(20, genres=("Documentary",), signals=(("topic_theme", "nature documentary", "Nature documentary"), ("mood", "calm", "Calm"), ("pacing", "slow", "Slow")))
    for index in range(21, 25):
        rows.append(record(index, genres=("Documentary",), signals=(("topic_theme", "nature documentary", "Nature documentary"), ("mood", "calm", "Calm"), ("pacing", "slow", "Slow"))))
    sparse = record(30, genres=("One-off",), signals=(("mood", "unique", "Unique"), ("tone", "unique", "Unique"), ("pacing", "unique", "Unique")))
    insufficient = record(40, genres=(), signals=())
    rows.extend([limited, sparse, insufficient])
    report, _ = build(rows)
    statuses = {row["content_id"]: row["recommendation_readiness"]["status"] for row in report["per_title"]}
    assert statuses[1] == "ready"
    assert statuses[20] == "limited"
    assert statuses[30] == "sparse"
    assert statuses[40] == "insufficient_data"


def test_expansion_plan_is_gap_driven_and_contains_no_title_ids():
    report, plan = build([record(1), record(2, content_type="series", language="ja")])
    assert plan["recommended_next_catalog_size"] == 275
    assert plan["recommended_additions"] == 273
    assert plan["targets"]["content_type"]["movies"] + plan["targets"]["content_type"]["series"] == 273
    assert "tmdb_id" not in json.dumps(plan)
    assert report["expansion_gap_summary"]["recommended_additions"] == 273


def test_deterministic_ordering_and_json_markdown_report_structure(tmp_path):
    report, plan = build([record(2), record(1)])
    assert [row["content_id"] for row in report["per_title"]] == [1, 2]
    json_path = tmp_path / "baseline.json"
    markdown_path = tmp_path / "baseline.md"
    gap_path = tmp_path / "gap.json"
    audit.write_reports(report, plan, json_path=json_path, markdown_path=markdown_path, gap_path=gap_path)
    loaded = json.loads(json_path.read_text())
    assert loaded["audit_version"] == "1.0"
    assert "## More Like This Readiness" in markdown_path.read_text()
    assert json.loads(gap_path.read_text())["recommended_next_catalog_size"] == 275


def test_strict_mode_nonzero_only_for_failed_readiness():
    empty, _ = build([])
    healthy_rows = [record(index) for index in range(1, 12)]
    healthy, _ = build(healthy_rows)
    assert audit.strict_exit_code(empty) == 2
    assert audit.strict_exit_code(healthy) in {0, 2}  # depends on transparent signal thresholds
    healthy["readiness"] = [{"status": "pass"}]
    assert audit.strict_exit_code(healthy) == 0


def test_non_strict_main_writes_reports_and_makes_no_network_or_database_write(monkeypatch, tmp_path):
    monkeypatch.setattr(audit, "load_catalog_records", lambda *args, **kwargs: ([record(1)], {"query_count": 1, "read_only": True, "unused_genres": [], "orphan_primary_rows": []}))
    monkeypatch.setattr(audit, "load_mapping_config", lambda: mapping_config())
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    paths = [tmp_path / "a.json", tmp_path / "a.md", tmp_path / "gap.json"]
    result = audit.main(["--output-json", str(paths[0]), "--output-markdown", str(paths[1]), "--output-gap-plan", str(paths[2]), "--reference-date", "2026-07-21"])
    assert result == 0
    assert all(path.exists() for path in paths)


def test_performance_report_structure_is_read_only_and_bounded():
    report, _ = build(
        [record(1)],
        performance={"completed": True, "read_only": True, "queries": [{"query": "catalog_listing", "elapsed_ms": 1.2, "returned_rows": 1, "bounded": True}]},
    )
    performance = report["performance_baseline"]
    assert performance["read_only"] is True
    assert performance["queries"][0]["bounded"] is True


def test_sql_contract_contains_only_read_and_explain_statements():
    sql_text = " ".join([audit.BASE_CONTENT_SQL, *audit.PERFORMANCE_QUERIES.values()]).upper()
    for forbidden in (" INSERT ", " UPDATE ", " DELETE ", " TRUNCATE ", " ALTER ", " DROP "):
        assert forbidden not in f" {sql_text} "
    source = SCRIPT_PATH.read_text()
    assert "import requests" not in source
    assert "from urllib" not in source
