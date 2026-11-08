"""Refresh-only cache policy and real, protected PostgreSQL domain transitions."""

import copy
from datetime import datetime, timedelta, timezone
import json
import os

import pytest
from sqlalchemy import text

from analytics.scripts.ingestion import fetch_tmdb_sample as fetcher
from analytics.scripts.refresh import content_refresh_executor as executor
from analytics.scripts.refresh import content_refresh_planner as planner
from analytics.scripts.refresh import series_refresh_state as state
from analytics.scripts.refresh import run_content_refresh as runner
from analytics.scripts.audits import audit_catalog_expansion_readiness as audit

NOW = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)
PARAMS = {"language": "en-US", "append_to_response": "videos", "include_video_language": "en,null"}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    path = tmp_path / "tv_123_details.json"
    monkeypatch.setattr(fetcher, "relative_path", lambda path: str(path))
    fetcher.save_json(path, {"id": 123})
    signature = fetcher.build_request_signature("/tv/123", PARAMS)
    fetcher.save_cache_metadata(path, "/tv/123", PARAMS, signature, NOW.isoformat())
    calls = []
    monkeypatch.setattr(fetcher, "fetch_tmdb_json", lambda *a, **k: calls.append(a) or {"id": 123, "fresh": True})
    return path, calls


def fetch(cache, *, age=0, **kwargs):
    path, _ = cache
    options = {"params": PARAMS, "cache_max_age_seconds": 3600, "now": NOW + timedelta(seconds=age), **kwargs}
    return fetcher.fetch_or_reuse_json("/tv/123", path, "synthetic-test-token", options.pop("refresh", False), **options)


@pytest.mark.parametrize("age,expected", [(0, "reused"), (3599, "reused"), (3600, "fetched"), (999999, "fetched")])
def test_refresh_cache_has_strict_source_age_boundary(cache, age, expected):
    _, result = fetch(cache, age=age)
    assert result["status"] == expected
    assert len(cache[1]) == int(expected == "fetched")
    if expected == "reused":
        assert result["source_fetched_at"] == NOW.isoformat()
        assert result["timestamp_origin"] == "sidecar"


def test_force_and_offline_are_explicit_and_never_confused(cache):
    _, replay = fetch(cache, age=999999, offline=True)
    assert replay["status"] == "reused"
    assert replay["cache_policy"] == "offline_replay"
    assert cache[1] == []
    _, forced = fetch(cache, refresh=True)
    assert forced["status"] == "fetched"
    assert len(cache[1]) == 1
    with pytest.raises(ValueError, match="mutually exclusive"):
        fetch(cache, refresh=True, offline=True)


@pytest.mark.parametrize("defect", ["missing", "broken_json", "timestamp", "naive", "future", "source", "path", "signature", "parameters", "status", "body"])
def test_bad_cache_provenance_fails_closed_offline_and_refetches_online(cache, defect):
    path, calls = cache
    sidecar = fetcher.cache_metadata_path(path)
    data = json.loads(sidecar.read_text())
    if defect == "missing":
        sidecar.unlink()
    elif defect == "broken_json":
        sidecar.write_text("{broken")
    elif defect == "body":
        path.write_text('{"id":456}')
    else:
        key, value = {
            "timestamp": ("fetched_at", "not a date"), "naive": ("fetched_at", "2026-07-20T12:00:00"),
            "future": ("fetched_at", (NOW + timedelta(seconds=1)).isoformat()),
            "source": ("source", "unknown"), "path": ("request_path", "/tv/999"),
            "signature": ("request_signature", "b" * 64), "parameters": ("request_parameters", {}),
            "status": ("response_status", 500),
        }[defect]
        data[key] = value
        sidecar.write_text(json.dumps(data))
    # Even a recent filesystem mtime cannot establish source freshness.
    os.utime(path, (NOW.timestamp(), NOW.timestamp()))
    with pytest.raises(fetcher.TmdbFetchError):
        fetch(cache, offline=True)
    assert calls == []
    assert fetch(cache)[1]["status"] == "fetched"
    assert len(calls) == 1


def test_language_signature_change_does_not_reuse_other_response(cache):
    params = {**PARAMS, "language": "ja-JP"}
    with pytest.raises(fetcher.TmdbFetchError):
        fetch(cache, params=params, offline=True)
    assert fetch(cache, params=params)[1]["status"] == "fetched"


def details(source_id=123, **changes):
    return {"id": source_id, "name": "Source Freshness Fixture", "original_name": "Fixture",
            "status": "Returning Series", "in_production": True,
            "number_of_seasons": 1, "number_of_episodes": 8,
            "first_air_date": "2024-01-01", "last_air_date": "2026-07-01",
            "last_episode_to_air": None, "next_episode_to_air": None,
            "seasons": [], "videos": {"results": []}, **changes}


@pytest.fixture
def target(db_session):
    content_id = db_session.execute(text("INSERT INTO content(title,content_type) VALUES('Source Freshness Fixture','series') RETURNING id")).scalar_one()
    source_id = 999900000 + content_id
    db_session.execute(text("INSERT INTO external_ids(content_id,source_name,external_id) VALUES(:id,'tmdb',:source)"),
                       {"id": content_id, "source": str(source_id)})
    db_session.commit()
    return {"content_id": content_id, "tmdb_id": str(source_id), "content_type": "series",
            "title": "Source Freshness Fixture", "refresh_scopes": ["series_metadata", "videos"],
            "reasons": {}, "original_language": "en"}


def apply_snapshot(db_session, target, monkeypatch, tmp_path, *, collected=NOW, origin="fetched", apply=True, **changes):
    payload = details(int(target["tmdb_id"]), **changes)
    proof = {"status": origin, "source_fetched_at": collected.isoformat(),
             "timestamp_origin": "network" if origin == "fetched" else "sidecar", "request_signature": "a" * 64}
    monkeypatch.setattr(executor, "fetch_refresh_details", lambda *a, **k: (payload, proof, ("en", "null")))
    result = executor.execute_plan_item(target, database_url=db_session.get_bind().url.render_as_string(hide_password=False),
                                        token=None, apply=apply, preview_dir=tmp_path)
    db_session.expire_all()
    return result


def stored(db_session, table, target):
    assert table in {"content_series_fetch_state", "content_series_metadata", "content_video_fetch_state"}
    return dict(db_session.execute(text(f"SELECT * FROM {table} WHERE content_id=:id"), {"id": target["content_id"]}).mappings().one())


def test_unchanged_collection_advances_success_but_not_change_and_is_not_due(db_session, target, monkeypatch, tmp_path):
    first = apply_snapshot(db_session, target, monkeypatch, tmp_path)
    assert first["domains"]["series_metadata"]["status"] == "success"
    before = stored(db_session, "content_series_fetch_state", target)
    lifecycle = stored(db_session, "content_series_metadata", target)
    later = NOW + timedelta(days=1)
    result = apply_snapshot(db_session, target, monkeypatch, tmp_path, collected=later)
    after = stored(db_session, "content_series_fetch_state", target)
    assert result["domains"]["series_metadata"]["status"] == "no_change"
    assert after["last_successful_at"] == later
    assert after["last_changed_at"] == before["last_changed_at"]
    assert after["change_source_at"] == NOW
    assert stored(db_session, "content_series_metadata", target) == lifecycle
    row = next(planner.iter_content_rows(db_session.get_bind().url, content_id=target["content_id"]))
    assert planner.evaluate_series_refresh(row, later).selected is False
    repeat = apply_snapshot(db_session, target, monkeypatch, tmp_path, collected=later, origin="reused")
    assert repeat["collection_success"] is False
    assert repeat["verified_response_available"] is True
    assert repeat["domains"]["series_metadata"]["status"] == "no_change"
    assert stored(db_session, "content_series_fetch_state", target)["last_changed_at"] == before["last_changed_at"]


def test_old_snapshot_keeps_source_time_and_cannot_regress_a_newer_success(db_session, target, monkeypatch, tmp_path):
    old = NOW - timedelta(days=30)
    apply_snapshot(db_session, target, monkeypatch, tmp_path, collected=old, origin="reused")
    initial = stored(db_session, "content_series_fetch_state", target)
    assert initial["last_successful_at"] == old
    assert initial["last_changed_at"] > old
    assert initial["change_source_at"] == old
    row = next(planner.iter_content_rows(db_session.get_bind().url, content_id=target["content_id"]))
    assert planner.evaluate_series_refresh(row, NOW).selected is True
    apply_snapshot(db_session, target, monkeypatch, tmp_path, number_of_episodes=9)
    success = stored(db_session, "content_series_fetch_state", target)
    result = apply_snapshot(db_session, target, monkeypatch, tmp_path, collected=old, origin="reused", number_of_episodes=5)
    assert result["domains"]["series_metadata"]["status"] == "skipped"
    assert result["domains"]["videos"]["status"] == "skipped"
    after = stored(db_session, "content_series_fetch_state", target)
    assert after["last_successful_at"] == NOW
    assert after["last_changed_at"] == success["last_changed_at"]
    assert stored(db_session, "content_series_metadata", target)["number_of_episodes"] == 9
    assert stored(db_session, "content_video_fetch_state", target)["last_fetched_at"] == NOW


@pytest.mark.parametrize("retryable,failure_class", [(True, "rate_limited"), (False, "source_not_found")])
def test_failed_http_preserves_lifecycle_and_success(db_session, target, monkeypatch, tmp_path, retryable, failure_class):
    apply_snapshot(db_session, target, monkeypatch, tmp_path)
    lifecycle = stored(db_session, "content_series_metadata", target)
    def failed(*args, **kwargs):
        raise fetcher.TmdbFetchError("Synthetic provider failure", retryable=retryable, failure_class=failure_class)
    monkeypatch.setattr(executor, "fetch_refresh_details", failed)
    result = executor.execute_plan_item(target, database_url=db_session.get_bind().url.render_as_string(hide_password=False),
                                        token=None, apply=True, preview_dir=tmp_path)
    value = stored(db_session, "content_series_fetch_state", target)
    assert value["last_successful_at"] == NOW
    assert value["last_status"] == "failed" and value["retryable"] is retryable
    assert value["failure_class"] == failure_class and value["consecutive_failure_count"] == 1
    assert stored(db_session, "content_series_metadata", target) == lifecycle
    assert result["domains"]["series_metadata"]["automatic_retry"] is retryable
    assert stored(db_session, "content_video_fetch_state", target)["last_fetched_at"] == NOW


@pytest.mark.parametrize("bad_domain", ["series_metadata", "videos"])
def test_partial_domain_success_is_persisted_independently(db_session, target, monkeypatch, tmp_path, bad_domain):
    changes = {"number_of_episodes": "bad"} if bad_domain == "series_metadata" else {"videos": None}
    result = apply_snapshot(db_session, target, monkeypatch, tmp_path, **changes)
    series = stored(db_session, "content_series_fetch_state", target)
    video = stored(db_session, "content_video_fetch_state", target)
    if bad_domain == "series_metadata":
        assert result["domains"]["series_metadata"]["status"] == "failed"
        assert series["last_successful_at"] is None and series["last_source_fetched_at"] == NOW
        assert video["last_fetch_status"] == "empty" and video["last_fetched_at"] == NOW
    else:
        assert series["last_status"] == "success" and series["last_successful_at"] == NOW
        assert result["domains"]["videos"]["status"] == "incomplete"
        assert video["last_fetched_at"] is None


def test_dry_run_reports_no_committed_writes(db_session, target, monkeypatch, tmp_path):
    result = apply_snapshot(db_session, target, monkeypatch, tmp_path, apply=False)
    assert result["database_writes"] is False
    assert all(domain["database_writes"] is False for domain in result["domains"].values())
    assert db_session.execute(text("SELECT count(*) FROM content_series_fetch_state")).scalar_one() == 0


def test_state_failure_rolls_back_lifecycle_and_restart_can_replay(db_session, target, monkeypatch, tmp_path):
    original = state.record_success
    monkeypatch.setattr(state, "record_success", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("interrupted commit")))
    result = apply_snapshot(db_session, target, monkeypatch, tmp_path)
    assert result["domains"]["series_metadata"]["status"] == "failed"
    assert db_session.execute(text("SELECT count(*) FROM content_series_metadata WHERE content_id=:id"), {"id": target["content_id"]}).scalar_one() == 0
    assert stored(db_session, "content_series_fetch_state", target)["last_successful_at"] is None
    monkeypatch.setattr(state, "record_success", original)
    assert apply_snapshot(db_session, target, monkeypatch, tmp_path, origin="reused")["domains"]["series_metadata"]["status"] == "success"
    assert stored(db_session, "content_series_fetch_state", target)["last_successful_at"] == NOW


def test_database_audit_and_execution_planner_agree_after_success(db_session, target, monkeypatch, tmp_path):
    apply_snapshot(db_session, target, monkeypatch, tmp_path)
    url = db_session.get_bind().url
    records, metadata = audit.load_catalog_records(url)
    assert metadata["read_only"] is True
    health = audit._video_health(records, NOW)
    rows = list(planner.iter_content_rows(url))
    for scope, key in (("series_metadata", "series_selected"), ("videos", "video_selected")):
        actual = {item["content_id"] for item in planner.build_refresh_plan(rows, NOW, scope=scope)}
        expected = {item["content_id"] for item in health["per_title_refresh"] if item[key]}
        assert actual == expected
        assert target["content_id"] not in actual


@pytest.mark.parametrize("status", ["ongoing", "ended", "cancelled"])
def test_legacy_source_unknown_and_audit_planner_parity(status):
    record = audit.empty_record({"content_id": 1, "title": "Legacy", "content_type": "series"})
    record.update(external_ids={"tmdb": "123"}, series_metadata={"series_status_normalized": status, "last_refreshed_at": NOW}, series_fetch_state=None)
    row = {**record, **record["series_metadata"], "has_series_metadata": True, "series_last_successful_at": None}
    expected = planner.evaluate_series_refresh(row, NOW)
    health = audit._video_health([record], NOW)["per_title_refresh"][0]
    assert expected.selected is (status == "ongoing")
    assert health["series_selected"] == expected.selected
    assert health["series_reason"] == expected.reason
    assert health["series_last_successful_source_collection"] is None


def test_duplicate_saved_plan_rejected_before_execution():
    item = {"content_id": 1, "content_type": "movie", "refresh_scopes": ["videos"]}
    with pytest.raises(ValueError, match="duplicate"):
        runner.validate_plan_items([item, copy.deepcopy(item)], "all")


@pytest.mark.parametrize("failure_count,retryable,expected,reason", [
    (1, True, True, "previous_transient_failure"),
    (2, True, False, "previous_transient_failure"),
    (3, True, False, "manual_review_required"),
    (1, False, False, "manual_review_required"),
])
def test_series_retry_cadence_matches_audit(failure_count, retryable, expected, reason):
    success = NOW - timedelta(days=20)
    record = audit.empty_record({"content_id": 1, "title": "Retry", "content_type": "series"})
    record.update(external_ids={"tmdb": "123"}, series_metadata={"series_status_normalized": "ongoing"},
                  series_fetch_state={"last_successful_at": success, "last_attempted_at": NOW-timedelta(days=1),
                                      "last_status": "failed", "retryable": retryable, "consecutive_failure_count": failure_count})
    result = audit._video_health([record], NOW)["per_title_refresh"][0]
    assert result["series_selected"] is expected
    assert result["series_reason"] == reason
    assert result["series_last_successful_source_collection"] == success.isoformat()


def test_interrupted_attempt_remains_due_without_manufacturing_success():
    decision = planner.evaluate_series_refresh({"has_series_metadata": True, "series_status_normalized": "ongoing",
                                               "series_last_successful_at": None, "series_last_status": "started"}, NOW)
    assert decision.selected is True
    assert decision.reason == "interrupted_attempt"
    assert decision.last_refreshed_at is None


@pytest.mark.parametrize("field,value", [("number_of_seasons", True), ("last_air_date", "bad-date"),
    ("seasons", [{}]), ("next_episode_to_air", []), ("in_production", "true"), ("name", "")])
def test_partial_lifecycle_data_is_rejected_before_import(field, value):
    with pytest.raises((ValueError, TypeError)):
        executor.validate_series_details(details(**{field: value}))


def test_saved_plan_identity_is_revalidated(monkeypatch):
    monkeypatch.setattr(runner, "iter_content_rows", lambda url: iter([{"content_id": 1, "source_id": "123", "content_type": "series"}]))
    runner.verify_execution_targets([{"content_id": 1, "tmdb_id": "123", "content_type": "series"}], "unused")
    with pytest.raises(ValueError, match="identity"):
        runner.verify_execution_targets([{"content_id": 1, "tmdb_id": "456", "content_type": "series"}], "unused")


def test_content_lifecycle_change_is_reported_even_when_series_values_match(monkeypatch, tmp_path):
    from types import SimpleNamespace
    target = {"content_id": 1, "tmdb_id": "123", "content_type": "series", "title": "Fixture",
              "refresh_scopes": ["series_metadata"], "reasons": {}}
    monkeypatch.setattr(executor, "fetch_refresh_details", lambda *a, **k: (details(), {
        "status": "reused", "source_fetched_at": NOW.isoformat(), "timestamp_origin": "sidecar", "request_signature": "a"*64}, ("en",)))
    monkeypatch.setattr(executor, "process_metadata_preview", lambda *a, **k: SimpleNamespace(
        series_metadata_inserted=0, series_metadata_updated=0, series_metadata_unchanged=1, content_fields_updated=1))
    result = executor.execute_plan_item(target, database_url="unused", token=None, apply=False, preview_dir=tmp_path)
    assert result["domains"]["series_metadata"]["status"] == "success"
    assert result["domains"]["series_metadata"]["content_fields_updated"] == 1
    assert result["database_writes"] is False and result["collection_success"] is False


def test_offline_cache_miss_preserves_healthy_persisted_state(db_session, target, monkeypatch, tmp_path):
    apply_snapshot(db_session, target, monkeypatch, tmp_path)
    before = stored(db_session, "content_series_fetch_state", target)
    previous_video = stored(db_session, "content_video_fetch_state", target)
    def missing(*args, **kwargs):
        raise fetcher.TmdbFetchError("Offline cache missing", failure_class="cache_incompatible")
    monkeypatch.setattr(executor, "fetch_refresh_details", missing)
    result = executor.execute_plan_item(target, database_url=db_session.get_bind().url.render_as_string(hide_password=False),
                                        token=None, apply=True, offline=True, preview_dir=tmp_path)
    assert stored(db_session, "content_series_fetch_state", target) == before
    assert stored(db_session, "content_video_fetch_state", target) == previous_video
    assert result["domains"]["series_metadata"]["status"] == "blocked"
    assert result["database_writes"] is False


@pytest.fixture
def local_execution(db_session, target, monkeypatch, tmp_path):
    """Use real cache/HTTP classification and importers; HTTP itself is mocked."""
    original_fetch = executor.fetch_refresh_details
    raw_dir = tmp_path / "raw"
    monkeypatch.setattr(executor, "RAW_OUTPUT_DIR", raw_dir)
    monkeypatch.setattr(fetcher, "relative_path", str)
    video = {"id": "synthetic-video", "key": "fixturekey1", "name": "Trailer",
             "site": "YouTube", "type": "Trailer", "official": True,
             "iso_639_1": "en", "published_at": "2026-07-01T00:00:00Z"}
    payload = details(int(target["tmdb_id"]), videos={"results": [video]})
    calls = []

    def no_http(*args, **kwargs):
        calls.append(args)
        pytest.fail("Unexpected HTTP; local preconditions/replay must never use the provider")

    monkeypatch.setattr(fetcher.requests, "get", no_http)

    def seed(age_days=0):
        source_at = datetime.now(timezone.utc) - timedelta(days=age_days, minutes=5)
        apply_snapshot(db_session, target, monkeypatch, tmp_path, collected=source_at, videos=payload["videos"])
        monkeypatch.setattr(executor, "fetch_refresh_details", original_fetch)
        return source_at

    def write_cache(collected, defect=None):
        path = raw_dir / fetcher.raw_filename("tv", int(target["tmdb_id"]), "details")
        data = {**payload, "id": 1} if defect == "wrong_identity" else payload
        fetcher.save_json(path, data)
        signature = fetcher.build_request_signature(f"/tv/{target['tmdb_id']}", PARAMS)
        fetcher.save_cache_metadata(path, f"/tv/{target['tmdb_id']}", PARAMS, signature, collected.isoformat())
        metadata_path = fetcher.cache_metadata_path(path)
        if defect == "signature":
            meta = json.loads(metadata_path.read_text())
            meta["request_signature"] = "f" * 64
            metadata_path.write_text(json.dumps(meta))
        elif defect == "provenance":
            metadata_path.unlink()
        elif defect == "corrupt_sidecar":
            metadata_path.write_text("{broken")
        elif defect == "corrupt_body":
            path.write_text("{broken")
        return path

    def snapshot():
        result = {}
        for table, column in (("content", "id"), ("content_series_metadata", "content_id"),
                              ("content_series_fetch_state", "content_id"), ("content_video_fetch_state", "content_id"),
                              ("content_videos", "content_id"), ("content_primary_videos", "content_id")):
            result[table] = [dict(row) for row in db_session.execute(
                text(f"SELECT * FROM {table} WHERE {column}=:id"), {"id": target["content_id"]}).mappings()]
        return result

    def decisions(reference):
        row = next(planner.iter_content_rows(db_session.get_bind().url, content_id=target["content_id"]))
        series = planner.evaluate_series_refresh(row, reference)
        videos = planner.evaluate_video_refresh(row, reference)
        records, _ = audit.load_catalog_records(db_session.get_bind().url)
        disposition = next(row for row in audit._video_health(records, reference)["per_title_refresh"] if row["content_id"] == target["content_id"])
        assert disposition["series_selected"] == series.selected
        assert disposition["series_reason"] == series.reason
        assert disposition["video_selected"] == videos.selected
        assert disposition["video_reason"] == videos.reason
        return series, videos

    def run(**kwargs):
        return executor.execute_plan_item(target, database_url=db_session.get_bind().url.render_as_string(hide_password=False),
                                          apply=True, preview_dir=tmp_path / "previews", request_policy=fetcher.RequestPolicy(max_retries=0),
                                          **{"token": None, "offline": True, **kwargs})

    return seed, write_cache, snapshot, decisions, run, calls, payload


@pytest.mark.parametrize("age_days", [0, 40])
@pytest.mark.parametrize("defect", ["missing", "signature", "provenance", "corrupt_sidecar", "corrupt_body", "wrong_identity", "expired_without_token", "forced_without_token"])
def test_local_preconditions_leave_all_domain_state_and_eligibility_unchanged(local_execution, defect, age_days):
    seed, cache, snapshot, decisions, run, calls, _ = local_execution
    source_at = seed(age_days)
    if defect not in {"missing", "forced_without_token"}:
        cache(source_at - timedelta(days=60) if defect == "expired_without_token" else source_at, defect)
    before = snapshot()
    reference = datetime.now(timezone.utc)
    eligibility = decisions(reference)
    result = run(offline=defect not in {"expired_without_token", "forced_without_token"}, refresh=defect == "forced_without_token")
    assert snapshot() == before
    assert decisions(reference) == eligibility
    assert calls == []
    assert all(domain["status"] == "blocked" and not domain["manual_review_required"] for domain in result["domains"].values())
    assert result["database_writes"] is False and result["collection_success"] is False
    assert runner.has_operational_failures([result]) is True
    assert runner.split_follow_up_targets([result]) == ([], [])
    assert runner.summarize_domains([result])["series_metadata"]["blocked"] == 1


@pytest.mark.parametrize("scope", ["all", "series_metadata", "videos"])
@pytest.mark.parametrize("age_days", [0, 40])
def test_offline_older_compatible_replay_is_a_persisted_noop(local_execution, target, scope, age_days):
    seed, cache, snapshot, decisions, run, calls, _ = local_execution
    source_at = seed(age_days)
    cache(source_at - timedelta(days=10))
    if scope != "all":
        target["refresh_scopes"] = [scope]
    before = snapshot()
    reference = datetime.now(timezone.utc)
    eligibility = decisions(reference)
    result = run()
    assert snapshot() == before
    assert decisions(reference) == eligibility
    assert all(domain["status"] == "skipped" and domain["reason"] == "older_snapshot" for domain in result["domains"].values())
    assert result["database_writes"] is False and result["collection_success"] is False
    assert runner.has_operational_failures([result]) is False
    assert calls == []


def test_online_collection_after_offline_block_remains_eligible(local_execution, db_session, target, monkeypatch):
    from types import SimpleNamespace
    seed, _, snapshot, decisions, run, calls, payload = local_execution
    source_at = seed(40)
    before = snapshot()
    assert decisions(datetime.now(timezone.utc))[0].selected is True
    assert run()["domains"]["series_metadata"]["status"] == "blocked"
    assert snapshot() == before

    def response(*args, **kwargs):
        calls.append(args)
        attempted = stored(db_session, "content_series_fetch_state", target)
        assert attempted["last_status"] == "started"  # committed immediately before HTTP
        assert attempted["last_successful_at"] == source_at
        return SimpleNamespace(ok=True, status_code=200, json=lambda: payload)

    monkeypatch.setattr(fetcher.requests, "get", response)
    result = run(offline=False, token="synthetic-test-token")
    after = snapshot()
    assert len(calls) == 1
    assert result["collection_success"] is True
    assert after["content_series_metadata"] == before["content_series_metadata"]
    assert stored(db_session, "content_series_fetch_state", target)["last_successful_at"] > source_at
    assert stored(db_session, "content_series_fetch_state", target)["last_status"] == "success"
    assert all(not decision.selected for decision in decisions(datetime.now(timezone.utc)))


def test_offline_expired_but_newer_snapshot_keeps_its_original_source_age(local_execution, db_session, target):
    seed, cache, snapshot, decisions, run, calls, _ = local_execution
    prior_source = seed(40)
    replay_source = prior_source + timedelta(days=10)
    cache(replay_source)
    before = snapshot()
    result = run()
    series = stored(db_session, "content_series_fetch_state", target)
    video = stored(db_session, "content_video_fetch_state", target)
    assert series["last_successful_at"] == replay_source
    assert video["last_fetched_at"] == replay_source
    assert series["last_source_origin"] == "reused" and series["consecutive_failure_count"] == 0
    assert series["last_changed_at"] == before["content_series_fetch_state"][0]["last_changed_at"]
    assert snapshot()["content_series_metadata"] == before["content_series_metadata"]
    assert all(decision.selected for decision in decisions(datetime.now(timezone.utc)))
    assert result["collection_success"] is False and result["verified_response_available"] is True
    assert result["database_writes"] is True and calls == []


@pytest.mark.parametrize("status_code,expected_class", [(429, "rate_limited"), (404, "source_not_found")])
def test_genuine_http_failures_preserve_success_and_keep_retry_policy(local_execution, db_session, target, monkeypatch, status_code, expected_class):
    from types import SimpleNamespace
    seed, _, snapshot, decisions, run, calls, _ = local_execution
    source_at = seed(40)
    before = snapshot()

    def response(*args, **kwargs):
        calls.append(args)
        assert stored(db_session, "content_series_fetch_state", target)["last_status"] == "started"
        return SimpleNamespace(ok=False, status_code=status_code, text="Synthetic HTTP failure", headers={})

    monkeypatch.setattr(fetcher.requests, "get", response)
    for count in range(1, 4 if status_code == 429 else 2):
        result = run(offline=False, token="synthetic-test-token")
        series = stored(db_session, "content_series_fetch_state", target)
        video = stored(db_session, "content_video_fetch_state", target)
        assert series["last_status"] == "failed" and video["last_fetch_status"] == "failed"
        assert series["last_successful_at"] == source_at and video["last_fetched_at"] == source_at
        assert series["failure_class"] == expected_class and video["last_failure_class"] == expected_class
        assert series["consecutive_failure_count"] == count and video["consecutive_failure_count"] == count
        assert series["retryable"] is (status_code == 429)
        assert result["domains"]["series_metadata"]["status"] == "failed"
        current = decisions(datetime.now(timezone.utc))
        if status_code == 429 and count < 3:
            assert all(d.reason == "previous_transient_failure" and not d.selected for d in current)
            future = max(d.due_at for d in current)
            assert all(d.selected for d in decisions(future))
        else:
            assert all(d.reason == "manual_review_required" and not d.selected for d in current)
        after = snapshot()
        assert all(after[table] == before[table] for table in before if table not in {"content_series_fetch_state", "content_video_fetch_state"})
    # A later local offline block must neither clear nor increase a genuine failure.
    failed_state = snapshot()
    failed_policy = decisions(datetime.now(timezone.utc))
    assert run()["domains"]["series_metadata"]["status"] == "blocked"
    assert snapshot() == failed_state
    reference = datetime.now(timezone.utc)
    assert [d.reason for d in decisions(reference)] == [d.reason for d in failed_policy]


def test_real_016_is_additive_transactional_idempotent_and_does_not_backfill(migration_targets, tmp_path):
    import shutil
    from scripts import migration_management as manager
    from scripts.database_snapshot import connect, snapshot

    entry = migration_targets["existing"]
    connection = connect(entry["url"])
    root = tmp_path / "repository"
    root.mkdir()
    for name in ("schema.sql", "indexes.sql"):
        shutil.copyfile(manager.ROOT / name, root / name)
    shutil.copytree(manager.ROOT / "migrations", root / "migrations")
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO content(title,content_type) VALUES('016 preservation sentinel','series') RETURNING id")
                content_id = cursor.fetchone()[0]
                cursor.execute("INSERT INTO content_series_metadata(content_id,last_refreshed_at,number_of_episodes) VALUES(%s,'2026-07-01',8)", (content_id,))
        before = snapshot(connection)
        connection.rollback()
        broken = root / "migrations/managed/017_deliberate_failure.sql"
        broken.write_text(manager.HEADER + "\nCREATE INDEX deliberate_failure ON public.content(nonexistent_column);\n")
        with pytest.raises(manager.MigrationError, match="rolled back"):
            manager.execute(connection, entry["database"], "apply", entry["database"], root=root)
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.content_series_fetch_state')")
            assert cursor.fetchone()[0] is None
        connection.rollback()
        broken.unlink()
        result = manager.execute(connection, entry["database"], "apply", entry["database"], root=root)
        assert result["executed_now"] == [16]
        assert manager.execute(connection, entry["database"], "apply", entry["database"], root=root)["executed_now"] == []
        after = snapshot(connection)
        assert all(after["tables"][table] == value for table, value in before["tables"].items())
        assert before["sequences_sha256"] == after["sequences_sha256"]
        assert after["tables"]["content_series_fetch_state"]["rows"] == 0
        # Retain the disposable sandbox and its synthetic preservation sentinel.
    finally:
        connection.rollback()
        connection.close()
