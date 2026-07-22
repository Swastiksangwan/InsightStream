"""Focused refresh execution built on the existing TMDb and importer functions."""

from __future__ import annotations

from datetime import datetime, timezone
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
    )
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
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content_id": plan_item["content_id"],
        "title": plan_item["title"],
        "tmdb_id": plan_item["tmdb_id"],
        "content_type": plan_item["content_type"],
        "requested_scopes": plan_item["refresh_scopes"],
        "reasons": plan_item["reasons"],
        "domains": {},
    }
    try:
        details, file_result, requested_languages = fetch_refresh_details(
            plan_item,
            token,
            refresh=refresh,
            language=language,
            video_languages=video_languages,
            request_policy=request_policy,
        )
    except TmdbFetchError as exc:
        safe_error = sanitize_fetch_error(str(exc)) or "TMDb request failed"
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
            }
        if VIDEO_SCOPE in result["domains"]:
            automatic_retry = exc.retryable and (
                failure_count is None
                or failure_count < MAX_AUTOMATIC_VIDEO_FAILURES
            )
            if apply and not video_state_persisted:
                automatic_retry = False
            result["domains"][VIDEO_SCOPE]["state_persisted"] = video_state_persisted
            result["domains"][VIDEO_SCOPE]["automatic_retry"] = automatic_retry
            result["domains"][VIDEO_SCOPE]["manual_review_required"] = not automatic_retry
            result["domains"][VIDEO_SCOPE]["consecutive_failure_count"] = failure_count
            if state_error:
                result["domains"][VIDEO_SCOPE]["state_persistence_error"] = state_error
        result.update({"network_fetch": "failed", "error": safe_error})
        return result

    result["network_fetch"] = file_result["status"]
    result["request_signature"] = file_result.get("request_signature")
    preview_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    if SERIES_SCOPE in plan_item["refresh_scopes"]:
        try:
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
            stats = process_metadata_preview(payload, preview_path, database_url, apply)
            changed = stats.series_metadata_inserted + stats.series_metadata_updated
            result["domains"][SERIES_SCOPE] = {
                "status": "success" if changed else "no_change",
                "inserted": stats.series_metadata_inserted,
                "updated": stats.series_metadata_updated,
                "unchanged": stats.series_metadata_unchanged,
            }
        except Exception as exc:  # domain isolation: video processing may continue
            result["domains"][SERIES_SCOPE] = {"status": "failed", "error": str(exc)}

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
            snapshot_status = video_item.get("videos_fetch_status")
            if snapshot_status in {"incomplete", "failed", "empty"}:
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
                "failure_class": video_item.get("videos_failure_class") or "none",
            }
        except Exception as exc:  # domain isolation: series result remains valid
            result["domains"][VIDEO_SCOPE] = {"status": "failed", "error": str(exc)}

    return result
