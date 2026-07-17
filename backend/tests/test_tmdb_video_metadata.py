import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "analytics" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tmdb_video_metadata import (
    normalize_tmdb_video,
    normalize_tmdb_video_record,
    normalize_video_snapshot,
    safe_video_urls,
    select_primary_video,
)


def load_fetcher():
    path = SCRIPTS_DIR / "fetch_tmdb_sample.py"
    spec = importlib.util.spec_from_file_location("video_fetch_tmdb_sample", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def raw_video(
    key="abcDEF_123",
    video_type="Trailer",
    official=True,
    language="en",
    site="YouTube",
    name="Official Trailer",
    published_at="2026-01-02T03:04:05.000Z",
):
    return {
        "id": f"tmdb-{key}",
        "key": key,
        "site": site,
        "type": video_type,
        "name": name,
        "official": official,
        "iso_639_1": language,
        "iso_3166_1": "US",
        "published_at": published_at,
        "size": 1080,
    }


def test_movie_and_tv_details_use_appended_videos_without_separate_request(monkeypatch):
    module = load_fetcher()
    calls = []

    def fake_fetch(api_path, raw_path, token, refresh, params=None, request_policy=None):
        calls.append((api_path, params))
        if api_path in {"/movie/101", "/tv/202"}:
            title_field = {"title": "Movie"} if api_path.startswith("/movie") else {"name": "Series"}
            return {"id": int(api_path.rsplit("/", 1)[1]), **title_field, "videos": {"results": []}}, {
                "path": str(raw_path),
                "status": "fetched",
            }
        if api_path.endswith("aggregate_credits"):
            return {"cast": [], "crew": []}, {"path": str(raw_path), "status": "fetched"}
        if api_path.endswith("credits"):
            return {"cast": [], "crew": []}, {"path": str(raw_path), "status": "fetched"}
        return {}, {"path": str(raw_path), "status": "fetched"}

    monkeypatch.setattr(module, "fetch_or_reuse_json", fake_fetch)
    movie = module.SampleTitle("Movie", "movie", 101)
    series = module.SampleTitle("Series", "tv", 202)

    module.fetch_title_payloads(movie, "token", False)
    module.fetch_title_payloads(series, "token", False)

    detail_calls = [call for call in calls if call[0] in {"/movie/101", "/tv/202"}]
    assert detail_calls == [
        (
            "/movie/101",
            {
                "append_to_response": "videos",
                "language": "en-US",
                "include_video_language": "en,null",
            },
        ),
        (
            "/tv/202",
            {
                "append_to_response": "videos",
                "language": "en-US",
                "include_video_language": "en,null",
            },
        ),
    ]
    assert not any(call[0].endswith("/videos") for call in calls)


def test_video_retry_target_can_be_reused_as_fetch_input_without_secrets():
    module = load_fetcher()
    sample = module.SampleTitle(
        title="Retry Fixture",
        media_type="movie",
        tmdb_id=101,
        content_type="movie",
        source_id="101",
        priority="refresh",
    )

    target = module.build_video_retry_target(sample, "temporary failure")

    assert target == {
        "title": "Retry Fixture",
        "content_type": "movie",
        "source_name": "tmdb",
        "source_id": "101",
        "priority": "refresh",
        "ingestion_status": "retry",
        "notes": "temporary failure",
    }
    assert "token" not in str(target).lower()


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = "response body"
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


def test_bearer_header_and_retry_after_are_used_without_token_in_payload(monkeypatch):
    module = load_fetcher()
    responses = [
        FakeResponse(429, headers={"Retry-After": "2"}),
        FakeResponse(200, {"id": 1, "videos": {"results": []}}),
    ]
    calls = []
    sleeps = []

    def fake_get(url, headers, params, timeout):
        calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        return responses.pop(0)

    monkeypatch.setattr(module.requests, "get", fake_get)
    payload = module.fetch_tmdb_json(
        "/movie/1",
        "secret-token",
        params={"append_to_response": "videos"},
        request_policy=module.RequestPolicy(max_retries=2),
        sleep_fn=sleeps.append,
        jitter_fn=lambda _start, _end: 0,
    )

    assert len(calls) == 2
    assert calls[0]["headers"]["Authorization"] == "Bearer secret-token"
    assert calls[0]["timeout"] == 15
    assert sleeps == [2.0]
    assert "secret-token" not in str(payload)


@pytest.mark.parametrize("status_code", [400, 401, 403, 404])
def test_permanent_errors_are_not_retried(monkeypatch, status_code):
    module = load_fetcher()
    calls = []

    def fake_get(*_args, **_kwargs):
        calls.append(True)
        return FakeResponse(status_code)

    monkeypatch.setattr(module.requests, "get", fake_get)
    with pytest.raises(module.TmdbFetchError) as exc_info:
        module.fetch_tmdb_json(
            "/movie/1",
            "token",
            request_policy=module.RequestPolicy(max_retries=3),
            sleep_fn=lambda _delay: None,
        )
    assert exc_info.value.retryable is False
    assert len(calls) == 1


def test_transient_connection_failures_have_bounded_retries(monkeypatch):
    module = load_fetcher()
    calls = []

    def fail(*_args, **_kwargs):
        calls.append(True)
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(module.requests, "get", fail)
    with pytest.raises(module.TmdbFetchError) as exc_info:
        module.fetch_tmdb_json(
            "/tv/2",
            "token",
            request_policy=module.RequestPolicy(max_retries=2),
            sleep_fn=lambda _delay: None,
            jitter_fn=lambda _start, _end: 0,
        )
    assert exc_info.value.retryable is True
    assert len(calls) == 3


def test_normalization_maps_fields_and_keeps_valid_identity_with_bad_optional_timestamp():
    normalized, reason = normalize_tmdb_video(raw_video())
    assert reason is None
    assert normalized == {
        "source": "tmdb",
        "source_video_id": "abcDEF_123",
        "site": "YouTube",
        "video_type": "Trailer",
        "name": "Official Trailer",
        "official": True,
        "language_code": "en",
        "country_code": "US",
        "published_at": "2026-01-02T03:04:05Z",
        "size": 1080,
        "is_primary": False,
    }
    assert normalize_tmdb_video(raw_video(key=""))[0] is None
    malformed_timestamp = normalize_tmdb_video_record(
        raw_video(published_at="not-a-date")
    )
    assert malformed_timestamp.video is not None
    assert malformed_timestamp.video["published_at"] is None
    assert malformed_timestamp.warnings == (
        "published_at is malformed and was preserved as null",
    )


def test_snapshot_handles_missing_empty_malformed_and_duplicate_records():
    missing = normalize_video_snapshot({})
    assert missing.status == "incomplete"
    assert missing.is_complete is False

    empty = normalize_video_snapshot({"videos": {"results": []}})
    assert empty.status == "empty"
    assert empty.is_complete is True
    assert empty.stale_cleanup_safe is True

    duplicate = normalize_video_snapshot(
        {"videos": {"results": [raw_video(), raw_video(), {"bad": True}]}}
    )
    assert duplicate.accepted_count == 1
    assert duplicate.rejected_count == 2
    assert duplicate.status == "incomplete"
    assert duplicate.stale_cleanup_safe is False
    assert duplicate.primary_source_video_id == "abcDEF_123"


def test_duplicate_only_snapshot_is_authoritative_but_malformed_snapshots_are_not():
    duplicate_only = normalize_video_snapshot(
        {"videos": {"results": [raw_video(), raw_video()]}}
    )
    assert duplicate_only.status == "success"
    assert duplicate_only.is_complete is True
    assert duplicate_only.stale_cleanup_safe is True

    all_rejected = normalize_video_snapshot(
        {"videos": {"results": [{"site": "YouTube", "key": ""}]}}
    )
    assert all_rejected.raw_count == 1
    assert all_rejected.accepted_count == 0
    assert all_rejected.status == "incomplete"
    assert all_rejected.stale_cleanup_safe is False

    mixed = normalize_video_snapshot(
        {"videos": {"results": [raw_video(), {"site": "Unknown", "key": "id"}]}}
    )
    assert mixed.accepted_count == 1
    assert mixed.rejected_count == 1
    assert mixed.status == "incomplete"
    assert mixed.stale_cleanup_safe is False

    ignored_provider = normalize_video_snapshot(
        {
            "videos": {
                "results": [raw_video(site="Dailymotion", key="stable_identity")]
            }
        }
    )
    assert ignored_provider.status == "success"
    assert ignored_provider.ignored_count == 1
    assert ignored_provider.rejected_count == 0
    assert ignored_provider.stale_cleanup_safe is True


def test_optional_timestamp_warning_does_not_reduce_snapshot_authority():
    snapshot = normalize_video_snapshot(
        {"videos": {"results": [raw_video(published_at="not-a-date")]}}
    )
    assert snapshot.status == "success"
    assert snapshot.accepted_count == 1
    assert snapshot.stale_cleanup_safe is True
    assert snapshot.videos[0]["published_at"] is None
    assert snapshot.warnings[0]["field"] == "published_at"


def normalized_video(key, video_type, official, language="en", name=None, published_at=None, site="YouTube"):
    video, reason = normalize_tmdb_video(
        raw_video(
            key=key,
            video_type=video_type,
            official=official,
            language=language,
            name=name or video_type,
            published_at=published_at,
            site=site,
        )
    )
    assert reason is None
    return video


def test_primary_selection_is_deterministic_and_prefers_trailers_official_and_language():
    videos = [
        normalized_video("teaser01", "Teaser", True, name="Official Teaser"),
        normalized_video("other001", "Trailer", True, language="fr", name="Official Trailer"),
        normalized_video("unoff001", "Trailer", False, name="Trailer"),
        normalized_video("winner01", "Trailer", True, name="Official Trailer"),
    ]
    assert select_primary_video(videos, "en") == ("YouTube", "winner01")
    assert select_primary_video(list(reversed(videos)), "en") == (
        "YouTube",
        "winner01",
    )


def test_primary_selection_falls_back_to_official_teaser_and_rejects_nonplayable_types():
    teaser = normalized_video("teaser02", "Teaser", True)
    clip = normalized_video("clip0001", "Clip", True)
    vimeo = normalized_video("12345678", "Trailer", True, site="Vimeo")
    assert select_primary_video([clip, vimeo, teaser]) == ("YouTube", "teaser02")
    assert select_primary_video([clip, vimeo]) is None


def test_primary_selection_prioritizes_trust_class_before_video_type():
    official_teaser = normalized_video("official1", "Teaser", True)
    unofficial_trailer = normalized_video("unoff002", "Trailer", False)
    unofficial_teaser = normalized_video("unoff003", "Teaser", False)
    assert select_primary_video([unofficial_trailer, official_teaser]) == (
        "YouTube",
        "official1",
    )
    assert select_primary_video([unofficial_teaser, unofficial_trailer]) == (
        "YouTube",
        "unoff002",
    )


def test_non_english_videos_are_accepted_and_trust_precedes_language():
    official_hindi = normalized_video(
        "hindi001", "Trailer", True, language="hi", name="Official Trailer"
    )
    unofficial_english = normalized_video(
        "english1", "Trailer", False, language="en", name="Trailer"
    )
    assert select_primary_video([unofficial_english, official_hindi], "en") == (
        "YouTube",
        "hindi001",
    )

    hindi_only = normalize_video_snapshot(
        {"videos": {"results": [raw_video(key="hindi002", language="hi")]}},
        preferred_language="en",
    )
    assert hindi_only.accepted_count == 1
    assert hindi_only.videos[0]["language_code"] == "hi"
    assert hindi_only.primary_source_video_id == "hindi002"


def test_language_preference_only_breaks_ties_and_neutral_is_a_fallback():
    english = normalized_video("english2", "Trailer", True, language="en")
    hindi = normalized_video("hindi003", "Trailer", True, language="hi")
    neutral = normalized_video("neutral1", "Trailer", True, language=None)
    assert select_primary_video([hindi, english], "en") == ("YouTube", "english2")
    assert select_primary_video([english, hindi], "hi") == ("YouTube", "hindi003")
    assert select_primary_video([neutral], "en") == ("YouTube", "neutral1")

    snapshot = normalize_video_snapshot(
        {
            "videos": {
                "results": [
                    raw_video(key="english3", language="en"),
                    raw_video(key="hindi004", language="hi"),
                ]
            }
        },
        preferred_language="en",
    )
    assert {video["language_code"] for video in snapshot.videos} == {"en", "hi"}


def test_primary_identity_includes_provider_when_source_keys_collide():
    snapshot = normalize_video_snapshot(
        {
            "videos": {
                "results": [
                    raw_video(key="12345678", site="Vimeo"),
                    raw_video(key="12345678", site="YouTube"),
                ]
            }
        }
    )

    assert select_primary_video(snapshot.videos) == ("YouTube", "12345678")
    assert snapshot.primary_site == "YouTube"
    assert snapshot.primary_source_video_id == "12345678"
    assert snapshot.as_preview_fields()["primary_video_site"] == "YouTube"
    assert [
        (video["site"], video["source_video_id"])
        for video in snapshot.videos
        if video["is_primary"]
    ] == [("YouTube", "12345678")]


def test_video_languages_are_normalized_deduped_and_validated():
    module = load_fetcher()
    assert module.normalize_video_languages("EN,null,en,fr") == ("en", "null", "fr")
    with pytest.raises(ValueError):
        module.normalize_video_languages("en-US,null")
    with pytest.raises(ValueError):
        module.normalize_video_languages("en,<script>")


def test_video_language_merge_is_priority_ordered_bounded_and_deterministic():
    module = load_fetcher()
    configured = ("en", "fr", "de", "es", "it", "pt", "ja", "null")
    assert module.merge_video_languages("en-US", "ko", configured) == (
        "en",
        "ko",
        "fr",
        "de",
        "es",
        "it",
        "pt",
        "null",
    )
    assert module.merge_video_languages("en-US", "fr", configured) == configured
    assert module.merge_video_languages("en-US", None, configured) == configured


def test_original_language_is_requested_without_replacing_primary_language(monkeypatch):
    module = load_fetcher()
    calls = []

    def fake_fetch(api_path, raw_path, token, refresh, params=None, request_policy=None):
        calls.append((api_path, params))
        if api_path == "/movie/303":
            return {"id": 303, "title": "Japanese Fixture", "videos": {"results": []}}, {
                "path": str(raw_path),
                "status": "fetched",
            }
        return {}, {"path": str(raw_path), "status": "fetched"}

    monkeypatch.setattr(module, "fetch_or_reuse_json", fake_fetch)
    sample = module.SampleTitle(
        "Japanese Fixture",
        "movie",
        303,
        original_language="ja",
    )
    module.fetch_title_payloads(sample, "token", False, "en-US", ("en", "null"))
    detail_params = calls[0][1]
    assert detail_params == {
        "append_to_response": "videos",
        "language": "en-US",
        "include_video_language": "en,ja,null",
    }


def test_video_language_environment_default_is_validated(monkeypatch):
    module = load_fetcher()
    monkeypatch.setenv("TMDB_VIDEO_LANGUAGES", "EN,null,en,fr")
    assert module.parse_args([]).video_languages == ("en", "null", "fr")


def test_network_cache_sidecar_and_reuse_preserve_source_fetch_time(monkeypatch, tmp_path):
    module = load_fetcher()
    raw_path = tmp_path / "movie_1_details.json"
    calls = []

    def fake_fetch(path, token, params=None, request_policy=None):
        calls.append((path, token, params))
        return {"id": 1, "videos": {"results": []}}

    monkeypatch.setattr(module, "fetch_tmdb_json", fake_fetch)
    params = {
        "append_to_response": "videos",
        "language": "en-US",
        "include_video_language": "en,null",
    }
    _, fetched = module.fetch_or_reuse_json(
        "/movie/1", raw_path, "secret-token", False, params=params
    )
    sidecar = json.loads(module.cache_metadata_path(raw_path).read_text())
    assert fetched["status"] == "fetched"
    assert fetched["source_fetched_at"] == sidecar["fetched_at"]
    assert fetched["timestamp_origin"] == "network"
    assert sidecar["request_signature"] == fetched["request_signature"]
    assert "secret-token" not in json.dumps(sidecar)

    _, reused = module.fetch_or_reuse_json(
        "/movie/1", raw_path, None, False, params=params
    )
    assert reused["status"] == "reused"
    assert reused["source_fetched_at"] == fetched["source_fetched_at"]
    assert reused["timestamp_origin"] == "sidecar"
    assert len(calls) == 1


def test_malformed_sidecar_timestamp_refetches_with_token(monkeypatch, tmp_path):
    module = load_fetcher()
    raw_path = tmp_path / "movie_3_details.json"
    raw_path.write_text('{"id": 3, "videos": {"results": []}}')
    params = {"append_to_response": "videos", "language": "en-US"}
    signature = module.build_request_signature("/movie/3", params)
    module.save_cache_metadata(
        raw_path,
        "/movie/3",
        params,
        signature,
        "not-a-time",
    )
    calls = []

    def fake_fetch(*_args, **_kwargs):
        calls.append(True)
        return {"id": 3, "videos": {"results": []}}

    monkeypatch.setattr(module, "fetch_tmdb_json", fake_fetch)
    _, result = module.fetch_or_reuse_json(
        "/movie/3", raw_path, "token", False, params=params
    )
    assert calls == [True]
    assert result["status"] == "fetched"
    assert result["timestamp_origin"] == "network"


def test_malformed_sidecar_timestamp_without_token_uses_file_mtime(tmp_path):
    module = load_fetcher()
    raw_path = tmp_path / "movie_4_details.json"
    raw_path.write_text('{"id": 4, "videos": {"results": []}}')
    legacy_time = datetime(2025, 2, 3, 4, 5, 6, tzinfo=timezone.utc).timestamp()
    os.utime(raw_path, (legacy_time, legacy_time))
    params = {"append_to_response": "videos", "language": "en-US"}
    module.save_cache_metadata(
        raw_path,
        "/movie/4",
        params,
        module.build_request_signature("/movie/4", params),
        "2026-07-17 10:00:00",
    )
    _, result = module.fetch_or_reuse_json(
        "/movie/4", raw_path, None, False, params=params
    )
    assert result["status"] == "reused"
    assert result["timestamp_origin"] == "legacy_file_mtime"
    assert datetime.fromisoformat(result["source_fetched_at"]).timestamp() == legacy_time


def test_retry_and_review_failures_have_distinct_dispositions(monkeypatch):
    module = load_fetcher()
    monkeypatch.setattr(module.requests, "get", lambda *_args, **_kwargs: FakeResponse(429))
    with pytest.raises(module.TmdbFetchError) as retry_exc:
        module.fetch_tmdb_json(
            "/movie/5",
            "token",
            request_policy=module.RequestPolicy(max_retries=0),
        )
    assert retry_exc.value.retryable is True
    assert retry_exc.value.failure_class == "rate_limited"

    review = module.build_error_preview_item(
        module.SampleTitle("Review Fixture", "movie", 5),
        "malformed source",
        failure_class="normalization_review",
    )
    assert review["videos_retryable"] is False
    assert review["videos_failure_class"] == "normalization_review"
    assert module.video_failure_disposition(review) == "review"

    retry = dict(review, videos_retryable=True, videos_failure_class="rate_limited")
    assert module.video_failure_disposition(retry) == "retry"
    assert module.video_failure_disposition(
        dict(review, videos_snapshot_complete=True, videos_failure_class="none")
    ) is None


def test_worker_exception_is_converted_to_review_result_and_batch_can_continue():
    module = load_fetcher()

    class FailedFuture:
        def result(self):
            raise RuntimeError("fixture failure")

    failed = module.resolve_worker_future(
        FailedFuture(),
        module.SampleTitle("Broken", "movie", 6),
        "en-US",
        ("en", "null"),
    )
    assert failed["error"] == "Unexpected worker failure: fixture failure"
    assert failed["mapped"]["videos_failure_class"] == "normalization_review"

    class SuccessfulFuture:
        def result(self):
            return {"sample": "next", "error": None}

    assert module.resolve_worker_future(
        SuccessfulFuture(),
        module.SampleTitle("Next", "movie", 7),
        "en-US",
        ("en", "null"),
    )["sample"] == "next"


def test_invalid_target_language_becomes_controlled_review_without_stopping_next_target():
    module = load_fetcher()
    invalid = module.process_sample(
        module.SampleTitle(
            "Invalid Language",
            "movie",
            8,
            original_language="not-a-language",
        ),
        None,
        False,
        {},
        "en-US",
        ("en", "null"),
        module.RequestPolicy(),
    )
    assert "Invalid video language policy" in invalid["error"]
    assert invalid["mapped"]["videos_failure_class"] == "normalization_review"

    next_result = module.build_worker_failure_result(
        module.SampleTitle("Next Target", "movie", 9),
        RuntimeError("separate fixture"),
        "en-US",
        ("en", "null"),
    )
    assert next_result["sample"].title == "Next Target"


def test_cache_signature_mismatch_refetches_or_fails_clearly(monkeypatch, tmp_path):
    module = load_fetcher()
    raw_path = tmp_path / "movie_2_details.json"
    raw_path.write_text('{"id": 2, "videos": {"results": []}}')
    module.save_cache_metadata(
        raw_path,
        "/movie/2",
        {"language": "en-US"},
        module.build_request_signature("/movie/2", {"language": "en-US"}),
        "2026-01-01T00:00:00+00:00",
    )
    current_params = {
        "append_to_response": "videos",
        "language": "en-US",
        "include_video_language": "en,null",
    }
    with pytest.raises(module.TmdbFetchError, match="incompatible"):
        module.fetch_or_reuse_json(
            "/movie/2", raw_path, None, False, params=current_params
        )

    monkeypatch.setattr(
        module,
        "fetch_tmdb_json",
        lambda *_args, **_kwargs: {"id": 2, "videos": {"results": []}},
    )
    _, result = module.fetch_or_reuse_json(
        "/movie/2", raw_path, "token", False, params=current_params
    )
    assert result["status"] == "fetched"
    assert result["request_signature"] == module.build_request_signature(
        "/movie/2", current_params
    )


def test_legacy_parameterless_cache_uses_mtime_without_claiming_network_time(tmp_path):
    module = load_fetcher()
    raw_path = tmp_path / "configuration.json"
    raw_path.write_text("{}")
    legacy_time = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc).timestamp()
    os.utime(raw_path, (legacy_time, legacy_time))

    _, result = module.fetch_or_reuse_json(
        "/configuration", raw_path, None, False
    )
    assert result["status"] == "reused"
    assert result["timestamp_origin"] == "legacy_file_mtime"
    assert datetime.fromisoformat(result["source_fetched_at"]).timestamp() == legacy_time


def test_safe_urls_only_allow_valid_youtube_keys():
    assert safe_video_urls("YouTube", "safe_KEY-1") == (
        "https://www.youtube.com/watch?v=safe_KEY-1",
        "https://www.youtube-nocookie.com/embed/safe_KEY-1",
    )
    assert safe_video_urls("Vimeo", "12345678") == (None, None)
    assert safe_video_urls("YouTube", "javascript:alert(1)") == (None, None)
