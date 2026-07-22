from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from analytics.scripts.audits import audit_catalog_expansion_readiness as catalog_audit
from analytics.scripts.audits import audit_source_signal_mapping_quality as signal_audit
from analytics.scripts.common.paths import (
    ANALYTICS_CONFIG_DIR,
    ANALYTICS_PROCESSED_DIR,
    ANALYTICS_RAW_DIR,
    ANALYTICS_ROOT,
    BACKEND_ROOT,
    REPO_ROOT,
)
from analytics.scripts.ingestion import fetch_tmdb_sample
from analytics.scripts.refresh import content_refresh_planner, plan_series_refresh
from analytics.scripts.refresh import run_content_refresh
from analytics.scripts.source_signals import build_keyword_signal_preview
from analytics.scripts.source_signals.source_signal_keyword_normalization import (
    normalize_keyword_name,
)


PUBLIC_MODULES = [
    "analytics.scripts.audits.analyze_tmdb_metadata_gap",
    "analytics.scripts.audits.audit_catalog_expansion_readiness",
    "analytics.scripts.audits.audit_decision_display_quality",
    "analytics.scripts.audits.audit_source_signal_mapping_quality",
    "analytics.scripts.audits.check_ingestion_health",
    "analytics.scripts.audits.reconcile_basic_metadata",
    "analytics.scripts.ingestion.build_tmdb_credits_preview",
    "analytics.scripts.ingestion.build_tmdb_keywords_preview",
    "analytics.scripts.ingestion.fetch_tmdb_availability_certification",
    "analytics.scripts.ingestion.fetch_tmdb_person_details",
    "analytics.scripts.ingestion.fetch_tmdb_sample",
    "analytics.scripts.ingestion.import_availability_certification_from_preview",
    "analytics.scripts.ingestion.import_content_metadata_from_preview",
    "analytics.scripts.ingestion.import_content_ratings_from_preview",
    "analytics.scripts.ingestion.import_content_videos_from_preview",
    "analytics.scripts.ingestion.import_imdb_ratings",
    "analytics.scripts.ingestion.import_letterboxd_ratings_from_preview",
    "analytics.scripts.ingestion.import_people_credits_from_preview",
    "analytics.scripts.ingestion.import_person_details_from_preview",
    "analytics.scripts.ingestion.import_tmdb_keywords_from_preview",
    "analytics.scripts.ingestion.merge_ingestion_candidates",
    "analytics.scripts.ingestion.merge_tmdb_keywords_retry_preview",
    "analytics.scripts.ingestion.preview_letterboxd_ratings_match",
    "analytics.scripts.ingestion.update_posters_from_tmdb_preview",
    "analytics.scripts.ingestion.validate_ingestion_candidates",
    "analytics.scripts.refresh.build_content_refresh_plan",
    "analytics.scripts.refresh.plan_series_refresh",
    "analytics.scripts.refresh.refresh_content_videos",
    "analytics.scripts.refresh.run_content_refresh",
    "analytics.scripts.source_signals.build_keyword_signal_preview",
    "analytics.scripts.source_signals.import_source_signals_from_preview",
]


@pytest.mark.parametrize(
    "module_name",
    PUBLIC_MODULES,
)
def test_public_module_help_works_without_database_or_provider_access(module_name):
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    environment.pop("TMDB_READ_ACCESS_TOKEN", None)

    result = subprocess.run(
        [sys.executable, "-m", module_name, "--help"],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_shared_repository_paths_are_exact_and_cwd_independent():
    expected_root = Path(__file__).resolve().parents[2]

    assert REPO_ROOT == expected_root
    assert ANALYTICS_ROOT == expected_root / "analytics"
    assert ANALYTICS_CONFIG_DIR == expected_root / "analytics" / "config"
    assert ANALYTICS_PROCESSED_DIR == expected_root / "analytics" / "processed"
    assert ANALYTICS_RAW_DIR == expected_root / "analytics" / "raw"
    assert BACKEND_ROOT == expected_root / "backend"


def test_default_config_and_output_paths_did_not_move():
    assert catalog_audit.DEFAULT_MAPPING_PATH == (
        ANALYTICS_CONFIG_DIR / "source_signal_keyword_mapping.json"
    )
    assert catalog_audit.DEFAULT_JSON_OUTPUT == (
        ANALYTICS_PROCESSED_DIR / "catalog_audits" / "catalog_baseline.json"
    )
    assert build_keyword_signal_preview.DEFAULT_OUTPUT_PATH == (
        ANALYTICS_PROCESSED_DIR / "source_signals" / "source_signal_preview.json"
    )
    assert fetch_tmdb_sample.RAW_OUTPUT_DIR == ANALYTICS_RAW_DIR / "tmdb"
    assert fetch_tmdb_sample.PREVIEW_OUTPUT_PATH == (
        ANALYTICS_PROCESSED_DIR / "tmdb" / "sample_mapping_preview.json"
    )
    assert run_content_refresh.DEFAULT_PLAN == (
        ANALYTICS_PROCESSED_DIR / "tmdb" / "content_refresh_plan.json"
    )
    assert run_content_refresh.DEFAULT_REPORT == (
        ANALYTICS_PROCESSED_DIR
        / "tmdb"
        / "run_reports"
        / "content_refresh_run_report.json"
    )


def test_refresh_and_audit_reuse_canonical_dependencies():
    assert content_refresh_planner.evaluate_refresh_status is plan_series_refresh.evaluate_refresh_status
    assert catalog_audit.evaluate_video_refresh is content_refresh_planner.evaluate_video_refresh
    assert catalog_audit.evaluate_series_refresh is content_refresh_planner.evaluate_series_refresh


def test_source_signal_tools_share_keyword_normalizer():
    assert build_keyword_signal_preview.normalize_keyword_name is normalize_keyword_name
    assert signal_audit.normalize_keyword_name is normalize_keyword_name


def test_no_implementation_scripts_remain_in_flat_root():
    flat_scripts = {
        path.name
        for path in (ANALYTICS_ROOT / "scripts").glob("*.py")
        if path.name != "__init__.py"
    }

    assert flat_scripts == set()
