import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def load_planner_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "analytics" / "scripts" / "plan_series_refresh.py"
    spec = importlib.util.spec_from_file_location("plan_series_refresh", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["plan_series_refresh"] = module
    spec.loader.exec_module(module)
    return module


def test_refresh_planner_selects_missing_series_metadata():
    planner = load_planner_module()
    decision = planner.evaluate_refresh_status(
        {"has_series_metadata": False},
        datetime(2026, 6, 23, tzinfo=timezone.utc),
    )

    assert decision.selected is True
    assert "missing content_series_metadata row" in decision.reasons


def test_refresh_planner_selects_stale_ongoing_series():
    planner = load_planner_module()
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)
    decision = planner.evaluate_refresh_status(
        {
            "has_series_metadata": True,
            "series_status_normalized": "ongoing",
            "last_refreshed_at": now - timedelta(days=8),
            "last_episode_air_date": None,
            "next_episode_air_date": None,
            "latest_activity_date": None,
        },
        now,
    )

    assert decision.selected is True
    assert any("ongoing status" in reason for reason in decision.reasons)


def test_refresh_planner_skips_fresh_ended_series_by_default():
    planner = load_planner_module()
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)
    decision = planner.evaluate_refresh_status(
        {
            "has_series_metadata": True,
            "series_status_normalized": "ended",
            "last_refreshed_at": now - timedelta(days=30),
            "last_episode_air_date": now.date() - timedelta(days=10),
            "next_episode_air_date": None,
            "latest_activity_date": now.date() - timedelta(days=10),
        },
        now,
    )

    assert decision.selected is False
    assert decision.reasons == ["ended series skipped by default"]


def test_refresh_planner_can_include_stale_ended_series():
    planner = load_planner_module()
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)
    decision = planner.evaluate_refresh_status(
        {
            "has_series_metadata": True,
            "series_status_normalized": "ended",
            "last_refreshed_at": now - timedelta(days=30),
            "last_episode_air_date": now.date() - timedelta(days=10),
            "next_episode_air_date": None,
            "latest_activity_date": now.date() - timedelta(days=10),
        },
        now,
        include_ended=True,
    )

    assert decision.selected is True
    assert any("ended status included" in reason for reason in decision.reasons)


def test_refresh_planner_selects_upcoming_next_episode_window():
    planner = load_planner_module()
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)
    decision = planner.evaluate_refresh_status(
        {
            "has_series_metadata": True,
            "series_status_normalized": "upcoming",
            "last_refreshed_at": now,
            "last_episode_air_date": None,
            "next_episode_air_date": now.date() + timedelta(days=5),
            "latest_activity_date": None,
        },
        now,
    )

    assert decision.selected is True
    assert any("within next 14 days" in reason for reason in decision.reasons)


def test_refresh_planner_selects_passed_episode_after_last_refresh():
    planner = load_planner_module()
    now = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)
    decision = planner.evaluate_refresh_status(
        {
            "has_series_metadata": True,
            "series_status_normalized": "ongoing",
            "last_refreshed_at": "2026-06-23T23:51:49",
            "last_episode_air_date": None,
            "next_episode_air_date": "2026-06-28",
            "latest_activity_date": None,
        },
        now,
    )

    assert decision.selected is True
    assert any("passed since last refresh" in reason for reason in decision.reasons)


def test_refresh_planner_keeps_future_episode_window_rule():
    planner = load_planner_module()
    now = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)
    decision = planner.evaluate_refresh_status(
        {
            "has_series_metadata": True,
            "series_status_normalized": "ongoing",
            "last_refreshed_at": "2026-06-29T10:00:00Z",
            "last_episode_air_date": None,
            "next_episode_air_date": "2026-07-05",
            "latest_activity_date": None,
        },
        now,
    )

    assert decision.selected is True
    assert any("within next 14 days" in reason for reason in decision.reasons)


def test_refresh_planner_skips_passed_episode_already_refreshed_after_air_date():
    planner = load_planner_module()
    now = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)
    decision = planner.evaluate_refresh_status(
        {
            "has_series_metadata": True,
            "series_status_normalized": "ongoing",
            "last_refreshed_at": "2026-06-26T01:00:00Z",
            "last_episode_air_date": None,
            "next_episode_air_date": "2026-06-25",
            "latest_activity_date": None,
        },
        now,
    )

    assert decision.selected is False
    assert not any("passed since last refresh" in reason for reason in decision.reasons)


def test_refresh_planner_skips_ended_series_with_passed_episode_by_default():
    planner = load_planner_module()
    now = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)
    decision = planner.evaluate_refresh_status(
        {
            "has_series_metadata": True,
            "series_status_normalized": "ended",
            "last_refreshed_at": "2026-06-23T23:51:49Z",
            "last_episode_air_date": None,
            "next_episode_air_date": "2026-06-28",
            "latest_activity_date": None,
        },
        now,
    )

    assert decision.selected is False
    assert not any("passed since last refresh" in reason for reason in decision.reasons)


def test_refresh_planner_skips_recent_ongoing_series_without_next_episode():
    planner = load_planner_module()
    now = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)
    decision = planner.evaluate_refresh_status(
        {
            "has_series_metadata": True,
            "series_status_normalized": "ongoing",
            "last_refreshed_at": "2026-06-29T10:00:00Z",
            "last_episode_air_date": None,
            "next_episode_air_date": None,
            "latest_activity_date": None,
        },
        now,
    )

    assert decision.selected is False
    assert not any("next_episode_air_date" in reason for reason in decision.reasons)
