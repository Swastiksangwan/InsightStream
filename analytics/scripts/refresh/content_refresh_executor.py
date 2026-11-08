"""Focused refresh execution built on the existing TMDb and importer functions."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from analytics.scripts.ingestion.fetch_tmdb_sample import (
    DEFAULT_LANGUAGE,
    DEFAULT_VIDEO_LANGUAGES,
    RAW_OUTPUT_DIR,
    RequestPolicy,
    SampleTitle,
    TmdbFetchError,
    TmdbLocalPreconditionError,
    build_series_metadata,
    fetch_or_reuse_json,
    latest_tv_activity_date,
    merge_video_languages,
    normalize_language_code,
    raw_filename,
)
from analytics.scripts.ingestion.import_content_metadata_from_preview import (
    process_preview as process_metadata_preview,
)
from analytics.scripts.ingestion.import_content_videos_from_preview import (
    normalize_database_url,
    process_preview_items as process_video_preview,
    sanitize_fetch_error,
    update_fetch_state,
)
from analytics.scripts.providers.tmdb.tmdb_video_metadata import normalize_video_snapshot

from analytics.scripts.refresh.content_refresh_planner import (
    MAX_AUTOMATIC_VIDEO_FAILURES,
    SERIES_SCOPE,
    VIDEO_SCOPE,
)
from analytics.scripts.refresh.series_refresh_state import OlderSeriesSnapshot, record_attempt

REFRESH_CACHE_MAX_AGE_SECONDS = 3600


def validate_series_details(details: dict[str, Any]) -> None:
    """Reject partial lifecycle responses before nulls can overwrite valid data."""
    if not isinstance(details.get("name"), str) or not details["name"].strip():
        raise ValueError("Series response is missing its name")
    if not isinstance(details.get("status"), str) or not details["status"].strip():
        raise ValueError("Series response is missing lifecycle status")
    for field in ("number_of_seasons", "number_of_episodes"):
        if type(details.get(field)) is not int or details[field] < 0:
            raise ValueError("Series response has invalid " + field)
    if type(details.get("in_production")) is not bool or not isinstance(details.get("seasons"), list):
        raise ValueError("Series response has invalid production/season data")
    for field in ("first_air_date", "last_air_date"):
        if field not in details:
            raise ValueError("Series response is missing " + field)
        if details[field] not in (None, ""):
            date.fromisoformat(details[field])
    for field in ("last_episode_to_air", "next_episode_to_air"):
        if field not in details or (details[field] is not None and not isinstance(details[field], dict)):
            raise ValueError("Series response has invalid " + field)
        if details[field] and details[field].get("air_date"):
            date.fromisoformat(details[field]["air_date"])
    for season in details["seasons"]:
        if not isinstance(season, dict) or type(season.get("season_number")) is not int:
            raise ValueError("Series response has malformed seasons")
        if season.get("air_date"):
            date.fromisoformat(season["air_date"])


def persist_video_fetch_failure(
    database_url: str,
    content_id: int,
    error: str,
    *,
    retryable: bool,
    failure_class: str,
    attempted_at: datetime | None = None,
) -> int:
    engine = create_engine(normalize_database_url(database_url), future=True)
    try:
        with engine.begin() as connection:
            update_fetch_state(
                connection,
                content_id,
                "failed",
                error,
                attempted_at or datetime.now(timezone.utc),
                None,
                retryable=retryable,
                failure_class=failure_class,
            )
            failure_count = connection.execute(
                text(
                    """
                    SELECT consecutive_failure_count
                    FROM content_video_fetch_state
                    WHERE content_id = :content_id AND source = 'tmdb'
                    """
                ),
                {"content_id": content_id},
            ).scalar_one()
    finally:
        engine.dispose()
    return int(failure_count)


def _sample_for_item(item: dict[str, Any]) -> SampleTitle:
    return SampleTitle(
        title=item["title"],
        media_type="tv" if item["content_type"] == "series" else "movie",
        tmdb_id=int(item["tmdb_id"]),
        content_type=item["content_type"],
        source_id=str(item["tmdb_id"]),
        original_language=item.get("original_language"),
        priority=item.get("priority"),
        ingestion_status="refresh_due",
    )


def build_series_preview_item(
    plan_item: dict[str, Any],
    details: dict[str, Any],
) -> dict[str, Any]:
    notes: list[str] = []
    episode_run_time = details.get("episode_run_time")
    runtime = episode_run_time[0] if isinstance(episode_run_time, list) and episode_run_time else None
    first_air_date = details.get("first_air_date")
    return {
        "source_provider": "tmdb",
        "source_name": "tmdb",
        "source_id": str(plan_item["tmdb_id"]),
        "tmdb_id": int(plan_item["tmdb_id"]),
        "media_type": "tv",
        "content_type": "series",
        "title": details.get("name") or plan_item["title"],
        "original_title": details.get("original_name"),
        "original_language": details.get("original_language"),
        "release_date": first_air_date,
        "latest_activity_date": latest_tv_activity_date(details),
        "year": int(first_air_date[:4]) if isinstance(first_air_date, str) and len(first_air_date) >= 4 else None,
        "runtime": runtime,
        "status": details.get("status"),
        "genres": [],
        "series_metadata": build_series_metadata(details, notes),
        "mapping_notes": notes,
    }


def build_video_preview_item(
    plan_item: dict[str, Any],
    details: dict[str, Any],
    file_result: dict[str, Any],
    *,
    detail_language: str,
    requested_languages: tuple[str, ...],
) -> dict[str, Any]:
    preferred_language = normalize_language_code(
        detail_language or DEFAULT_LANGUAGE,
        field_name="detail language",
    )
    snapshot = normalize_video_snapshot(details, preferred_language)
    preview = {
        "source_provider": "tmdb",
        "source_name": "tmdb",
        "source_id": str(plan_item["tmdb_id"]),
        "tmdb_id": int(plan_item["tmdb_id"]),
        "content_type": plan_item["content_type"],
        "title": plan_item["title"],
        "original_language": plan_item.get("original_language"),
        "videos_fetch_origin": file_result["status"],
        "videos_source_fetched_at": file_result.get("source_fetched_at"),
        "videos_timestamp_origin": file_result.get("timestamp_origin"),
        "videos_request_signature": file_result.get("request_signature"),
        "videos_preferred_language": preferred_language,
        "videos_requested_languages": list(requested_languages),
    }
    preview.update(snapshot.as_preview_fields())
    return preview


def fetch_refresh_details(
    plan_item: dict[str, Any],
    token: str | None,
    *,
    refresh: bool,
    language: str = DEFAULT_LANGUAGE,
    video_languages: tuple[str, ...] = ("en", "null"),
    request_policy: RequestPolicy | None = None,
    offline: bool = False,
    before_network=None,
) -> tuple[dict[str, Any], dict[str, Any], tuple[str, ...]]:
    sample = _sample_for_item(plan_item)
    requested_languages = merge_video_languages(
        language,
        sample.original_language,
        video_languages or DEFAULT_VIDEO_LANGUAGES,
    )
    # The legacy series fetch already appends videos. Keep one compatible details
    # cache shape for every scope while only normalizing/importing requested domains.
    params: dict[str, Any] = {
        "language": language,
        "append_to_response": "videos",
        "include_video_language": ",".join(requested_languages),
    }
    api_path = f"/{sample.media_type}/{sample.tmdb_id}"
    raw_path = RAW_OUTPUT_DIR / raw_filename(sample.media_type, sample.tmdb_id, "details")
    details, file_result = fetch_or_reuse_json(
        api_path,
        raw_path,
        token,
        refresh,
        params=params,
        request_policy=request_policy,
        cache_max_age_seconds=REFRESH_CACHE_MAX_AGE_SECONDS,
        offline=offline,
        before_network=before_network,
    )
    if type(details.get("id")) is not int or details["id"] != sample.tmdb_id:
        if file_result["status"] == "reused":
            raise TmdbLocalPreconditionError("Cached TMDb details identity does not match the refresh target")
        raise TmdbFetchError("TMDb details identity does not match the refresh target", failure_class="normalization_review")
    return details, file_result, requested_languages


def execute_plan_item(
    plan_item: dict[str, Any],
    *,
    database_url: str,
    token: str | None,
    apply: bool,
    refresh: bool = False,
    language: str = DEFAULT_LANGUAGE,
    video_languages: tuple[str, ...] = ("en", "null"),
    request_policy: RequestPolicy | None = None,
    preview_dir: Path,
    offline: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content_id": plan_item["content_id"],
        "title": plan_item["title"],
        "tmdb_id": plan_item["tmdb_id"],
        "content_type": plan_item["content_type"],
        "requested_scopes": plan_item["refresh_scopes"],
        "reasons": plan_item["reasons"],
        "domains": {},
        "database_writes": False,
    }
    attempted_at = datetime.now(timezone.utc)

    def before_network():
        # Local cache/token checks must succeed before a provider attempt exists.
        # Persist before HTTP so a genuinely interrupted request remains visible.
        if apply and SERIES_SCOPE in plan_item["refresh_scopes"]:
            record_attempt(database_url, int(plan_item["content_id"]), attempted_at=attempted_at)
            result["database_writes"] = True
    try:
        details, file_result, requested_languages = fetch_refresh_details(
            plan_item,
            token,
            refresh=refresh,
            language=language,
            video_languages=video_languages,
            request_policy=request_policy,
            offline=offline,
            before_network=before_network,
        )
    except TmdbFetchError as exc:
        safe_error = sanitize_fetch_error(str(exc)) or "TMDb request failed"
        if isinstance(exc, TmdbLocalPreconditionError) or exc.failure_class == "cache_incompatible":
            result.update(network_fetch="blocked", collection_success=False, verified_response_available=False)
            result["domains"] = {
                scope: {"status": "blocked", "error": safe_error, "failure_class": exc.failure_class,
                        "state_persisted": False, "database_writes": False,
                        "automatic_retry": False, "manual_review_required": False}
                for scope in plan_item["refresh_scopes"]
            }
            return result
        video_state_persisted = False
        failure_count: int | None = None
        state_error: str | None = None
        if apply and VIDEO_SCOPE in plan_item["refresh_scopes"]:
            try:
                failure_count = persist_video_fetch_failure(
                    database_url,
                    int(plan_item["content_id"]),
                    safe_error,
                    retryable=exc.retryable,
                    failure_class=exc.failure_class,
                )
                video_state_persisted = True
            except Exception as persistence_exc:
                state_error = sanitize_fetch_error(str(persistence_exc)) or "state update failed"
        for scope in plan_item["refresh_scopes"]:
            result["domains"][scope] = {
                "status": "failed",
                "error": safe_error,
                "retryable": exc.retryable,
                "failure_class": exc.failure_class,
                "database_writes": False,
            }
        if apply and SERIES_SCOPE in result["domains"]:
            domain = result["domains"][SERIES_SCOPE]
            try:
                count = record_attempt(database_url, int(plan_item["content_id"]), error=safe_error,
                                       retryable=exc.retryable, failure_class=exc.failure_class, attempted_at=attempted_at)
                domain.update(state_persisted=True, database_writes=True, consecutive_failure_count=count,
                              automatic_retry=exc.retryable and count < MAX_AUTOMATIC_VIDEO_FAILURES)
                result["database_writes"] = True
            except Exception:
                domain.update(state_persisted=False, automatic_retry=False, state_persistence_error="Series failure state could not be persisted")
        if VIDEO_SCOPE in result["domains"]:
            automatic_retry = exc.retryable and (
                failure_count is None
                or failure_count < MAX_AUTOMATIC_VIDEO_FAILURES
            )
            if apply and not video_state_persisted:
                automatic_retry = False
            result["domains"][VIDEO_SCOPE]["state_persisted"] = video_state_persisted
            result["domains"][VIDEO_SCOPE]["database_writes"] = video_state_persisted
            result["database_writes"] |= video_state_persisted
            result["domains"][VIDEO_SCOPE]["automatic_retry"] = automatic_retry
            result["domains"][VIDEO_SCOPE]["manual_review_required"] = not automatic_retry
            result["domains"][VIDEO_SCOPE]["consecutive_failure_count"] = failure_count
            if state_error:
                result["domains"][VIDEO_SCOPE]["state_persistence_error"] = state_error
        result.update({"network_fetch": "failed", "collection_success": False, "verified_response_available": False, "error": safe_error})
        return result

    result["network_fetch"] = file_result["status"]
    result["request_signature"] = file_result.get("request_signature")
    result["source_fetched_at"] = file_result.get("source_fetched_at")
    result["collection_success"] = file_result["status"] == "fetched"
    result["verified_response_available"] = True
    preview_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    if SERIES_SCOPE in plan_item["refresh_scopes"]:
        try:
            validate_series_details(details)
            series_item = build_series_preview_item(plan_item, details)
            payload = {
                "generated_at": generated_at,
                "inspection_only": True,
                "source_provider": "tmdb",
                "items": [series_item],
            }
            preview_path = preview_dir / f"content_{plan_item['content_id']}_series_metadata.json"
            import json
            preview_path.write_text(json.dumps(payload, indent=2) + "\n")
            stats = process_metadata_preview(payload, preview_path, database_url, apply,
                                             refresh_context={"content_id": int(plan_item["content_id"]), "response": file_result,
                                                              "attempted_at": attempted_at})
            changed = stats.series_metadata_inserted + stats.series_metadata_updated + getattr(stats, "content_fields_updated", 0)
            result["domains"][SERIES_SCOPE] = {
                "status": "success" if changed else "no_change",
                "inserted": stats.series_metadata_inserted,
                "updated": stats.series_metadata_updated,
                "unchanged": stats.series_metadata_unchanged,
                "content_fields_updated": getattr(stats, "content_fields_updated", 0),
                "database_writes": apply,
                "state_persisted": apply,
            }
        except OlderSeriesSnapshot as exc:
            result["domains"][SERIES_SCOPE] = {
                "status": "skipped", "reason": "older_snapshot", "detail": str(exc),
                "database_writes": False, "state_persisted": False,
            }
        except Exception as exc:  # domain isolation: video processing may continue
            error = "Series domain application failed; inspect validated preview" if not isinstance(exc, ValueError) else str(exc)
            domain = {"status": "failed", "error": error, "retryable": False, "database_writes": False}
            if apply:
                try:
                    record_attempt(database_url, int(plan_item["content_id"]), error=error,
                                   failure_class="normalization_review", response=file_result, attempted_at=attempted_at)
                    domain.update(state_persisted=True, database_writes=True)
                except Exception:
                    domain.update(state_persisted=False, state_persistence_error="Series failure state could not be persisted")
            result["domains"][SERIES_SCOPE] = domain

    if VIDEO_SCOPE in plan_item["refresh_scopes"]:
        try:
            video_item = build_video_preview_item(
                plan_item,
                details,
                file_result,
                detail_language=language,
                requested_languages=requested_languages,
            )
            payload = {
                "generated_at": generated_at,
                "inspection_only": True,
                "source_provider": "tmdb",
                "items": [video_item],
            }
            preview_path = preview_dir / f"content_{plan_item['content_id']}_videos.json"
            import json
            preview_path.write_text(json.dumps(payload, indent=2) + "\n")
            stats = process_video_preview([video_item], database_url, apply)
            changed = stats.videos_inserted + stats.videos_updated + stats.videos_removed + stats.primary_changes
            snapshot_status = (stats.reports[0]["effective_status"] if getattr(stats, "reports", None)
                               else video_item.get("videos_fetch_status"))
            if snapshot_status in {"incomplete", "failed", "empty", "skipped"}:
                status = snapshot_status
            else:
                status = "success" if changed else "no_change"
            result["domains"][VIDEO_SCOPE] = {
                "status": status,
                "inserted": stats.videos_inserted,
                "updated": stats.videos_updated,
                "removed": stats.videos_removed,
                "primary_changed": stats.primary_changes,
                "warnings": stats.warnings,
                "retryable": video_item.get("videos_retryable") is True,
                "failure_class": ("normalization_review" if snapshot_status == "incomplete" else video_item.get("videos_failure_class") or "none"),
                "database_writes": apply and snapshot_status != "skipped",
                "reason": stats.reports[0].get("reason") if getattr(stats, "reports", None) else None,
            }
        except Exception as exc:  # domain isolation: series result remains valid
            error = "Video domain application failed; inspect validated preview"
            domain = {"status": "failed", "error": error, "retryable": False, "database_writes": False}
            if apply:
                try:
                    persist_video_fetch_failure(database_url, int(plan_item["content_id"]), error,
                                                retryable=False, failure_class="normalization_review")
                    domain.update(state_persisted=True, database_writes=True)
                except Exception:
                    domain.update(state_persisted=False, state_persistence_error="Video failure state could not be persisted")
            result["domains"][VIDEO_SCOPE] = domain

    result["database_writes"] |= any(d.get("database_writes", False) for d in result["domains"].values())
    return result
