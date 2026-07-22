import argparse
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from analytics.scripts.refresh import content_refresh_executor as executor
from analytics.scripts.refresh import content_refresh_planner as planner
from analytics.scripts.refresh import plan_series_refresh as legacy
from analytics.scripts.refresh import run_content_refresh as runner

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


def row(**overrides):
    value = {
        "content_id": 1,
        "title": "Neutral Fixture",
        "content_type": "series",
        "source_id": "12345",
        "original_language": "ja",
        "release_date": "2020-01-01",
        "latest_activity_date": None,
        "has_series_metadata": True,
        "series_status_normalized": "ongoing",
        "in_production": True,
        "last_episode_air_date": None,
        "next_episode_air_date": None,
        "next_season_air_date": None,
        "has_announced_season": False,
        "last_refreshed_at": NOW - timedelta(days=8),
        "video_last_attempted_at": None,
        "video_last_fetched_at": None,
        "video_last_fetch_status": None,
        "video_last_fetch_error": None,
        "video_last_fetch_retryable": False,
        "video_last_failure_class": None,
        "video_consecutive_failure_count": 0,
    }
    value.update(overrides)
    return value


def test_movie_never_fetched_gets_only_videos_scope():
    item = planner.build_plan_item(
        row(content_type="movie", has_series_metadata=False), NOW
    )
    assert item["refresh_scopes"] == ["videos"]
    assert item["reasons"] == {"videos": "never_fetched"}


def test_series_scope_selection_is_exactly_legacy_planner_decision():
    fixture = row()
    expected = legacy.evaluate_refresh_status(fixture, NOW)
    shared = planner.evaluate_series_refresh(fixture, NOW)
    assert shared.selected == expected.selected
    assert shared.reason == "; ".join(expected.reasons)


def test_series_not_due_parity_and_scope_isolation():
    fixture = row(last_refreshed_at=NOW, series_status_normalized="ongoing")
    expected = legacy.evaluate_refresh_status(fixture, NOW)
    item = planner.build_plan_item(fixture, NOW, scope="series_metadata")
    assert expected.selected is False
    assert item is None


def test_explicit_target_is_forced_and_movie_rejects_series_scope():
    movie = row(content_type="movie", has_series_metadata=False)
    assert planner.build_plan_item(movie, NOW, scope="series_metadata", forced=True) is None
    forced = planner.build_plan_item(movie, NOW, scope="videos", forced=True)
    assert forced["reasons"]["videos"] == "forced_by_cli"


def test_video_cadence_and_manual_review_disposition():
    upcoming = planner.evaluate_video_refresh(
        row(
            content_type="movie",
            release_date="2026-08-01",
            video_last_fetch_status="success",
            video_last_fetched_at=NOW - timedelta(days=2),
        ),
        NOW,
    )
    assert upcoming.selected is True
    assert upcoming.reason == "upcoming_release"
    assert upcoming.priority == "high"

    review = planner.evaluate_video_refresh(
        row(
            video_last_fetch_status="incomplete",
            video_last_fetched_at=NOW - timedelta(days=30),
        ),
        NOW,
    )
    assert review.selected is False
    assert review.reason == "normalization_review"


def test_video_retry_is_bounded_and_permanent_failures_require_review():
    first_failure = planner.evaluate_video_refresh(
        row(
            video_last_fetch_status="failed",
            video_last_attempted_at=NOW - timedelta(days=1),
            video_last_fetch_retryable=True,
            video_last_failure_class="network_transient",
            video_consecutive_failure_count=1,
        ),
        NOW,
    )
    assert first_failure.selected is True
    assert first_failure.reason == "previous_transient_failure"

    second_failure = planner.evaluate_video_refresh(
        row(
            video_last_fetch_status="failed",
            video_last_attempted_at=NOW - timedelta(days=1),
            video_last_fetch_retryable=True,
            video_last_failure_class="provider_server_error",
            video_consecutive_failure_count=2,
        ),
        NOW,
    )
    assert second_failure.selected is False
    assert second_failure.due_at == NOW + timedelta(days=1)

    exhausted = planner.evaluate_video_refresh(
        row(
            video_last_fetch_status="failed",
            video_last_attempted_at=NOW - timedelta(days=30),
            video_last_fetch_retryable=True,
            video_last_failure_class="network_transient",
            video_consecutive_failure_count=planner.MAX_AUTOMATIC_VIDEO_FAILURES,
        ),
        NOW,
    )
    assert exhausted.selected is False
    assert exhausted.reason == "manual_review_required"
    assert exhausted.due_at is None

    permanent = planner.evaluate_video_refresh(
        row(
            video_last_fetch_status="failed",
            video_last_attempted_at=NOW - timedelta(days=30),
            video_last_fetch_retryable=False,
            video_last_failure_class="source_not_found",
            video_consecutive_failure_count=1,
        ),
        NOW,
        include_not_due=True,
    )
    assert permanent.selected is False
    assert permanent.reason == "manual_review_required"


def test_normalization_review_is_never_automatically_retried():
    decision = planner.evaluate_video_refresh(
        row(
            video_last_fetch_status="incomplete",
            video_last_fetch_retryable=False,
            video_last_failure_class="normalization_review",
            video_consecutive_failure_count=1,
        ),
        NOW,
        include_not_due=True,
    )
    assert decision.selected is False
    assert decision.reason == "normalization_review"


def test_plan_is_deterministic_without_duplicate_items():
    rows = [row(content_id=3), row(content_id=1), row(content_id=2)]
    items = planner.build_refresh_plan(rows, NOW, scope="videos")
    assert [item["content_id"] for item in items] == [1, 2, 3]
    assert len({item["content_id"] for item in items}) == len(items)
    assert all(item["due_at"]["videos"].endswith("+00:00") for item in items)


def test_plan_limit_keeps_highest_priority_regardless_of_database_page_order():
    rows = [
        row(
            content_id=1,
            content_type="movie",
            release_date="2020-01-01",
            video_last_fetch_status="success",
            video_last_fetched_at=NOW - timedelta(days=31),
        ),
        row(
            content_id=2,
            content_type="movie",
            release_date="2026-08-01",
            video_last_fetch_status="success",
            video_last_fetched_at=NOW - timedelta(days=2),
        ),
    ]
    items = planner.build_refresh_plan(rows, NOW, scope="videos", limit=1)
    assert [item["content_id"] for item in items] == [2]


def plan_item(scopes):
    return {
        "content_id": 84,
        "title": "Shared Request Fixture",
        "content_type": "series",
        "tmdb_id": "94997",
        "original_language": "ko",
        "refresh_scopes": scopes,
        "reasons": {scope: "forced_by_cli" for scope in scopes},
        "priority": "high",
    }


def test_video_only_uses_one_details_request_and_no_supporting_endpoints(monkeypatch):
    calls = []

    def fake_fetch(path, raw_path, token, refresh, params=None, request_policy=None):
        calls.append((path, params))
        return {"id": 94997, "videos": {"results": []}}, {
            "status": "fetched",
            "source_fetched_at": "2026-07-20T12:00:00Z",
            "timestamp_origin": "network",
            "request_signature": "a" * 64,
        }

    monkeypatch.setattr(executor, "fetch_or_reuse_json", fake_fetch)
    details, _, languages = executor.fetch_refresh_details(
        plan_item(["videos"]), "token", refresh=False
    )
    assert details["id"] == 94997
    assert len(calls) == 1
    assert calls[0][0] == "/tv/94997"
    assert calls[0][1]["append_to_response"] == "videos"
    assert "ko" in calls[0][1]["include_video_language"]
    assert "null" in languages
    assert not any(
        fragment in calls[0][0]
        for fragment in ("credits", "aggregate_credits", "external_ids", "keywords")
    )


def test_combined_series_uses_same_single_details_plus_videos_request(monkeypatch):
    calls = []

    def fake_fetch(path, raw_path, token, refresh, params=None, request_policy=None):
        calls.append((path, params))
        return {"id": 94997, "videos": {"results": []}}, {
            "status": "reused",
            "source_fetched_at": "2026-07-19T12:00:00Z",
            "timestamp_origin": "sidecar",
            "request_signature": "b" * 64,
        }

    monkeypatch.setattr(executor, "fetch_or_reuse_json", fake_fetch)
    executor.fetch_refresh_details(
        plan_item(["series_metadata", "videos"]), "token", refresh=False
    )
    assert len(calls) == 1
    assert calls[0][1]["append_to_response"] == "videos"


def test_shared_series_preview_uses_existing_series_normalizer_exactly():
    details = {
        "name": "Parity Fixture",
        "status": "Returning Series",
        "in_production": True,
        "first_air_date": "2024-01-01",
        "last_air_date": "2026-07-01",
        "number_of_seasons": 3,
        "number_of_episodes": 24,
        "episode_run_time": [],
        "last_episode_to_air": None,
        "next_episode_to_air": None,
        "seasons": [],
    }
    shared = executor.build_series_preview_item(plan_item(["series_metadata"]), details)
    assert shared["series_metadata"] == executor.build_series_metadata(details, [])


def test_series_metadata_only_preserves_legacy_appended_details_request(monkeypatch):
    calls = []

    def fake_fetch(path, raw_path, token, refresh, params=None, request_policy=None):
        calls.append((path, params))
        return {"id": 94997}, {
            "status": "fetched",
            "source_fetched_at": "2026-07-20T12:00:00Z",
            "timestamp_origin": "network",
            "request_signature": "c" * 64,
        }

    monkeypatch.setattr(executor, "fetch_or_reuse_json", fake_fetch)
    executor.fetch_refresh_details(
        plan_item(["series_metadata"]), "token", refresh=False
    )
    assert len(calls) == 1
    assert calls[0][1]["append_to_response"] == "videos"
    assert calls[0][1]["language"] == "en-US"


def test_request_failure_persists_video_attempt_only_during_apply(monkeypatch, tmp_path):
    persisted = []

    def fail_fetch(*args, **kwargs):
        raise executor.TmdbFetchError(
            "Authorization: Bearer secret-token provider unavailable",
            retryable=True,
            failure_class="provider_server_error",
        )

    monkeypatch.setattr(executor, "fetch_refresh_details", fail_fetch)
    monkeypatch.setattr(
        executor,
        "persist_video_fetch_failure",
        lambda *args, **kwargs: persisted.append((args, kwargs)) or 3,
    )
    result = executor.execute_plan_item(
        plan_item(["videos"]),
        database_url="postgresql://unused",
        token="secret-token",
        apply=True,
        preview_dir=tmp_path,
    )
    assert len(persisted) == 1
    assert persisted[0][0][1] == 84
    assert persisted[0][1]["retryable"] is True
    assert persisted[0][1]["failure_class"] == "provider_server_error"
    assert "secret-token" not in persisted[0][0][2]
    assert result["domains"]["videos"]["state_persisted"] is True
    assert result["domains"]["videos"]["automatic_retry"] is False
    assert result["domains"]["videos"]["manual_review_required"] is True
    assert result["domains"]["videos"]["consecutive_failure_count"] == 3
    retry_targets, review_targets = runner.split_follow_up_targets([result])
    assert retry_targets == []
    assert review_targets == [result]

    persisted.clear()
    executor.execute_plan_item(
        plan_item(["videos"]),
        database_url="postgresql://unused",
        token="secret-token",
        apply=False,
        preview_dir=tmp_path,
    )
    assert persisted == []


def test_request_failure_persists_retry_disposition_and_preserves_last_fetch(
    db_session,
    monkeypatch,
    tmp_path,
):
    content_id = db_session.execute(
        text(
            """
            INSERT INTO content (title, content_type)
            VALUES ('Refresh Failure State Fixture', 'movie') RETURNING id
            """
        )
    ).scalar_one()
    source_id = str(999992000 + content_id)
    db_session.execute(
        text(
            """
            INSERT INTO external_ids (content_id, source_name, external_id)
            VALUES (:content_id, 'tmdb', :source_id)
            """
        ),
        {"content_id": content_id, "source_id": source_id},
    )
    db_session.execute(
        text(
            """
            INSERT INTO content_video_fetch_state (
                content_id, source, last_attempted_at, last_fetched_at,
                last_fetch_status, source_snapshot_empty
            ) VALUES (
                :content_id, 'tmdb', '2026-07-01T00:00:00Z',
                '2026-07-01T00:00:00Z', 'success', FALSE
            )
            """
        ),
        {"content_id": content_id},
    )
    db_session.commit()

    def fail_fetch(*args, **kwargs):
        raise executor.TmdbFetchError(
            "Authorization: Bearer secret-token rate limited",
            status_code=429,
            retryable=True,
            failure_class="rate_limited",
        )

    monkeypatch.setattr(executor, "fetch_refresh_details", fail_fetch)
    try:
        result = executor.execute_plan_item(
            {
                "content_id": content_id,
                "title": "Refresh Failure State Fixture",
                "content_type": "movie",
                "tmdb_id": source_id,
                "original_language": "en",
                "refresh_scopes": ["videos"],
                "reasons": {"videos": "forced_by_cli"},
                "priority": "high",
            },
            database_url=db_session.get_bind().url.render_as_string(hide_password=False),
            token="secret-token",
            apply=True,
            preview_dir=tmp_path,
        )
        state = db_session.execute(
            text(
                """
                SELECT last_attempted_at, last_fetched_at, last_fetch_status,
                       last_fetch_error, last_fetch_retryable, last_failure_class,
                       consecutive_failure_count
                FROM content_video_fetch_state
                WHERE content_id = :content_id AND source = 'tmdb'
                """
            ),
            {"content_id": content_id},
        ).one()
        assert result["domains"]["videos"]["state_persisted"] is True
        assert state.last_attempted_at > datetime(2026, 7, 1, tzinfo=timezone.utc)
        assert state.last_fetched_at == datetime(2026, 7, 1, tzinfo=timezone.utc)
        assert state.last_fetch_status == "failed"
        assert state.last_fetch_retryable is True
        assert state.last_failure_class == "rate_limited"
        assert state.consecutive_failure_count == 1
        assert "secret-token" not in state.last_fetch_error
    finally:
        db_session.execute(text("DELETE FROM content WHERE id = :id"), {"id": content_id})
        db_session.commit()


def test_domain_failures_are_isolated(monkeypatch, tmp_path):
    details = {
        "id": 94997,
        "name": "Shared Request Fixture",
        "first_air_date": "2022-01-01",
        "status": "Returning Series",
        "seasons": [],
        "videos": {"results": []},
    }
    monkeypatch.setattr(
        executor,
        "fetch_refresh_details",
        lambda *args, **kwargs: (
            details,
            {
                "status": "fetched",
                "source_fetched_at": "2026-07-20T12:00:00Z",
                "timestamp_origin": "network",
                "request_signature": "d" * 64,
            },
            ("en", "ko", "null"),
        ),
    )
    monkeypatch.setattr(executor, "process_metadata_preview", lambda *args: (_ for _ in ()).throw(ValueError("series invalid")))

    class VideoStats:
        videos_inserted = 0
        videos_updated = 0
        videos_removed = 0
        primary_changes = 0
        warnings = []

    monkeypatch.setattr(executor, "process_video_preview", lambda *args: VideoStats())
    result = executor.execute_plan_item(
        plan_item(["series_metadata", "videos"]),
        database_url="postgresql://unused",
        token="token",
        apply=False,
        preview_dir=tmp_path,
    )
    assert result["domains"]["series_metadata"]["status"] == "failed"
    assert result["domains"]["videos"]["status"] in {"empty", "no_change"}


def test_video_failure_does_not_erase_successful_series_outcome(monkeypatch, tmp_path):
    details = {
        "id": 94997,
        "name": "Shared Request Fixture",
        "first_air_date": "2022-01-01",
        "status": "Returning Series",
        "seasons": [],
        "videos": {"results": []},
    }
    monkeypatch.setattr(
        executor,
        "fetch_refresh_details",
        lambda *args, **kwargs: (
            details,
            {
                "status": "fetched",
                "source_fetched_at": "2026-07-20T12:00:00Z",
                "timestamp_origin": "network",
                "request_signature": "e" * 64,
            },
            ("en", "ko", "null"),
        ),
    )

    class SeriesStats:
        series_metadata_inserted = 0
        series_metadata_updated = 1
        series_metadata_unchanged = 0

    monkeypatch.setattr(executor, "process_metadata_preview", lambda *args: SeriesStats())
    monkeypatch.setattr(executor, "process_video_preview", lambda *args: (_ for _ in ()).throw(ValueError("video invalid")))
    result = executor.execute_plan_item(
        plan_item(["series_metadata", "videos"]),
        database_url="postgresql://unused",
        token="token",
        apply=False,
        preview_dir=tmp_path,
    )
    assert result["domains"]["series_metadata"]["status"] == "success"
    assert result["domains"]["videos"]["status"] == "failed"


def test_plan_filter_removes_all_tab_leakage_and_preserves_requested_scope():
    args = argparse.Namespace(
        source_id=None,
        content_id=None,
        content_type=None,
        priority=None,
        scope="videos",
        limit=None,
    )
    items = runner.filter_plan_items({"items": [plan_item(["series_metadata", "videos"])]}, args)
    assert items[0]["refresh_scopes"] == ["videos"]


def test_cli_modes_are_mutually_exclusive():
    try:
        runner.parse_args(["--dry-run", "--apply"])
    except SystemExit as exc:
        assert exc.code != 0
    else:  # pragma: no cover
        raise AssertionError("conflicting modes must fail")


def test_run_report_totals_keep_domains_separate():
    results = [
        {"domains": {"series_metadata": {"status": "success"}, "videos": {"status": "incomplete"}}},
        {"domains": {"videos": {"status": "no_change"}}},
    ]
    totals = runner.summarize_domains(results)
    assert totals["series_metadata"]["success"] == 1
    assert totals["videos"]["incomplete"] == 1
    assert totals["videos"]["no_change"] == 1


def test_operational_exit_status_treats_incomplete_as_failure_but_empty_as_success():
    assert runner.has_operational_failures(
        [{"domains": {"videos": {"status": "incomplete"}}}]
    ) is True
    assert runner.has_operational_failures(
        [{"domains": {"series_metadata": {"status": "failed"}}}]
    ) is True
    assert runner.has_operational_failures(
        [{"domains": {"videos": {"status": "empty"}}}]
    ) is False


def test_main_returns_nonzero_for_incomplete_and_zero_for_valid_empty(
    monkeypatch,
    tmp_path,
):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps({"items": [plan_item(["videos"])]}))
    monkeypatch.setattr(runner, "load_database_url", lambda value: "postgresql://unused")
    monkeypatch.setattr(runner, "load_dotenv", None)

    def run_with(status):
        monkeypatch.setattr(
            runner,
            "execute_items",
            lambda *args: [{"domains": {"videos": {"status": status}}}],
        )
        return runner.main(
            [
                "--dry-run",
                "--scope",
                "videos",
                "--plan",
                str(plan_path),
                "--output",
                str(tmp_path / f"{status}-plan.json"),
                "--report",
                str(tmp_path / f"{status}-report.json"),
            ]
        )

    assert run_with("incomplete") == 1
    assert run_with("empty") == 0


def test_series_metadata_scope_changes_only_legacy_series_domain(
    db_session,
    monkeypatch,
    tmp_path,
):
    content_id = db_session.execute(
        text(
            """
            INSERT INTO content (
                tmdb_id, title, original_title, content_type, overview,
                release_date, latest_activity_date, year, runtime, language,
                original_language, status
            ) VALUES (
                999991234, 'Series Scope Isolation Fixture',
                'Series Scope Isolation Fixture', 'series', 'Existing overview',
                '2024-01-01', '2026-07-01', 2024, 50, 'English', 'en', 'Ongoing'
            ) RETURNING id
            """
        )
    ).scalar_one()
    genre_id = db_session.execute(
        text("INSERT INTO genres (name) VALUES (:name) RETURNING id"),
        {"name": f"Refresh Isolation {content_id}"},
    ).scalar_one()
    db_session.execute(
        text(
            """
            INSERT INTO external_ids (content_id, source_name, external_id)
            VALUES (:content_id, 'tmdb', '999991234')
            """
        ),
        {"content_id": content_id},
    )
    db_session.execute(
        text(
            """
            INSERT INTO content_genres (content_id, genre_id)
            VALUES (:content_id, :genre_id)
            """
        ),
        {"content_id": content_id, "genre_id": genre_id},
    )
    db_session.execute(
        text(
            """
            INSERT INTO content_series_metadata (
                content_id, number_of_seasons, number_of_episodes,
                series_status, series_status_normalized, in_production,
                first_air_date, last_air_date, source_name, last_refreshed_at
            ) VALUES (
                :content_id, 1, 8, 'Returning Series', 'ongoing', TRUE,
                '2024-01-01', '2026-07-01', 'tmdb', '2026-07-01T00:00:00Z'
            )
            """
        ),
        {"content_id": content_id},
    )
    video_id = db_session.execute(
        text(
            """
            INSERT INTO content_videos (
                content_id, source, source_video_id, site, video_type, name
            ) VALUES (
                :content_id, 'tmdb', 'scopeiso01', 'YouTube', 'Trailer',
                'Existing Trailer'
            ) RETURNING id
            """
        ),
        {"content_id": content_id},
    ).scalar_one()
    db_session.execute(
        text(
            """
            INSERT INTO content_primary_videos (content_id, content_video_id)
            VALUES (:content_id, :video_id)
            """
        ),
        {"content_id": content_id, "video_id": video_id},
    )
    db_session.execute(
        text(
            """
            INSERT INTO content_video_fetch_state (
                content_id, source, last_attempted_at, last_fetched_at,
                last_fetch_status, source_snapshot_empty
            ) VALUES (
                :content_id, 'tmdb', '2026-07-10T00:00:00Z',
                '2026-07-10T00:00:00Z', 'success', FALSE
            )
            """
        ),
        {"content_id": content_id},
    )
    db_session.commit()

    def rows(query):
        return [dict(row) for row in db_session.execute(text(query), {"id": content_id}).mappings()]

    snapshots = {
        "content": rows("SELECT * FROM content WHERE id = :id"),
        "genres": rows("SELECT * FROM content_genres WHERE content_id = :id ORDER BY id"),
        "videos": rows("SELECT * FROM content_videos WHERE content_id = :id ORDER BY id"),
        "primary": rows("SELECT * FROM content_primary_videos WHERE content_id = :id"),
        "video_state": rows(
            "SELECT * FROM content_video_fetch_state WHERE content_id = :id ORDER BY source"
        ),
    }
    details = {
        "id": 999991234,
        "name": "Provider Renamed Series",
        "original_name": "Provider Original Name",
        "original_language": "en",
        "first_air_date": "2025-02-03",
        "last_air_date": "2026-07-15",
        "number_of_seasons": 2,
        "number_of_episodes": 16,
        "episode_run_time": [61],
        "status": "Ended",
        "in_production": False,
        "type": "Scripted",
        "last_episode_to_air": {"air_date": "2026-07-15"},
        "next_episode_to_air": None,
        "seasons": [],
        "videos": {"results": []},
    }
    monkeypatch.setattr(
        executor,
        "fetch_refresh_details",
        lambda *args, **kwargs: (
            details,
            {
                "status": "reused",
                "source_fetched_at": "2026-07-20T12:00:00Z",
                "timestamp_origin": "sidecar",
                "request_signature": "f" * 64,
            },
            ("en", "null"),
        ),
    )

    try:
        scope_args = argparse.Namespace(
            source_id=None,
            content_id=None,
            content_type=None,
            priority=None,
            scope="series_metadata",
            limit=None,
        )
        scoped_items = runner.filter_plan_items(
            {
                "items": [
                    {
                        "content_id": content_id,
                        "title": "Series Scope Isolation Fixture",
                        "content_type": "series",
                        "tmdb_id": "999991234",
                        "original_language": "en",
                        "refresh_scopes": ["series_metadata", "videos"],
                        "reasons": {
                            "series_metadata": "forced_by_cli",
                            "videos": "forced_by_cli",
                        },
                        "priority": "high",
                    }
                ]
            },
            scope_args,
        )
        assert scoped_items[0]["refresh_scopes"] == ["series_metadata"]
        result = executor.execute_plan_item(
            scoped_items[0],
            database_url=db_session.get_bind().url.render_as_string(hide_password=False),
            token="unused",
            apply=True,
            preview_dir=tmp_path,
        )
        assert result["domains"]["series_metadata"]["status"] == "success"
        content_after = rows("SELECT * FROM content WHERE id = :id")[0]
        content_before = snapshots["content"][0]
        for field_name, value in content_before.items():
            if field_name not in {"latest_activity_date", "status", "updated_at"}:
                assert content_after[field_name] == value
        assert str(content_after["latest_activity_date"]) == "2026-07-15"
        assert content_after["status"] == "Ended"
        assert rows(
            "SELECT * FROM content_genres WHERE content_id = :id ORDER BY id"
        ) == snapshots["genres"]
        assert rows(
            "SELECT * FROM content_videos WHERE content_id = :id ORDER BY id"
        ) == snapshots["videos"]
        assert rows(
            "SELECT * FROM content_primary_videos WHERE content_id = :id"
        ) == snapshots["primary"]
        assert rows(
            "SELECT * FROM content_video_fetch_state WHERE content_id = :id ORDER BY source"
        ) == snapshots["video_state"]
        series_row = rows(
            "SELECT * FROM content_series_metadata WHERE content_id = :id"
        )[0]
        assert series_row["number_of_seasons"] == 2
        assert series_row["number_of_episodes"] == 16
        assert series_row["series_status"] == "Ended"
        assert series_row["series_status_normalized"] == "ended"
    finally:
        db_session.execute(text("DELETE FROM content WHERE id = :id"), {"id": content_id})
        db_session.execute(text("DELETE FROM genres WHERE id = :id"), {"id": genre_id})
        db_session.commit()
