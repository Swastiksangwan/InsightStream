#!/usr/bin/env python3
"""Dry-run or apply normalized TMDb videos from the metadata preview."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from tmdb_video_metadata import normalize_tmdb_video_record, select_primary_video


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PREVIEW_PATH = (
    REPO_ROOT / "analytics" / "processed" / "tmdb" / "sample_mapping_preview.json"
)
DATABASE_URL_ENV = "DATABASE_URL"
MAX_ROW_REPORT_ITEMS = 50
MAX_STORED_ERROR_LENGTH = 1000
VIDEO_COMPARE_FIELDS = (
    "video_type",
    "name",
    "official",
    "language_code",
    "country_code",
    "published_at",
    "size",
)


@dataclass
class ImportStats:
    mode: str
    items_seen: int = 0
    titles_resolved: int = 0
    titles_changed: int = 0
    titles_skipped: int = 0
    videos_inserted: int = 0
    videos_updated: int = 0
    videos_removed: int = 0
    primary_changes: int = 0
    fetch_states_updated: int = 0
    warnings: list[str] = field(default_factory=list)
    reports: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class VideoPlan:
    inserts: list[dict[str, Any]]
    updates: list[dict[str, Any]]
    stale_ids: list[int]
    selected_identity: tuple[str, str] | None
    primary_changed: bool
    primary_preserved: bool


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply TMDb video metadata from a processed preview."
    )
    parser.add_argument(
        "--preview",
        default=str(DEFAULT_PREVIEW_PATH.relative_to(REPO_ROOT)),
        help="Processed TMDb preview JSON path.",
    )
    parser.add_argument("--apply", action="store_true", help="Write planned changes.")
    parser.add_argument("--source-id", help="Filter by TMDb source ID.")
    parser.add_argument("--limit", type=positive_int)
    return parser.parse_args(argv)


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def load_preview(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Preview file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Preview JSON is malformed: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("Preview must contain an items array.")
    return payload, [item for item in payload["items"] if isinstance(item, dict)]


def normalize_database_url(value: str) -> str:
    if value.startswith("postgres://"):
        return "postgresql://" + value[len("postgres://") :]
    return value


def resolve_content_id(
    connection: Connection,
    item: dict[str, Any],
) -> int | None:
    source_id = str(item.get("source_id") or item.get("tmdb_id") or "").strip()
    if not source_id:
        return None
    row = connection.execute(
        text(
            """
            SELECT c.id
            FROM external_ids ei
            JOIN content c ON c.id = ei.content_id
            WHERE ei.source_name = 'tmdb'
              AND ei.external_id = :source_id
            LIMIT 1
            """
        ),
        {"source_id": source_id},
    ).mappings().first()
    return int(row["id"]) if row else None


def normalize_preview_videos(
    item: dict[str, Any],
    preferred_language: str | None,
) -> tuple[list[dict[str, Any]], list[str], bool]:
    normalized: list[dict[str, Any]] = []
    warnings: list[str] = []
    normalization_safe = True
    seen: set[tuple[str, str]] = set()
    raw_videos = item.get("videos")
    if not isinstance(raw_videos, list):
        return [], ["normalized videos field is not an array"], False

    for index, video in enumerate(raw_videos):
        if not isinstance(video, dict):
            warnings.append(f"video #{index + 1} is not an object")
            normalization_safe = False
            continue
        source_record = {
            "key": video.get("source_video_id"),
            "site": video.get("site"),
            "type": video.get("video_type"),
            "name": video.get("name"),
            "official": video.get("official"),
            "iso_639_1": video.get("language_code"),
            "iso_3166_1": video.get("country_code"),
            "published_at": video.get("published_at"),
            "size": video.get("size"),
        }
        result = normalize_tmdb_video_record(source_record)
        cleaned = result.video
        if cleaned is None:
            reason = result.rejection_reason or "video is not an accepted provider record"
            warnings.append(f"video #{index + 1}: {reason}")
            normalization_safe = False
            continue
        warnings.extend(f"video #{index + 1}: {warning}" for warning in result.warnings)
        identity = (cleaned["site"], cleaned["source_video_id"])
        if identity in seen:
            warnings.append(f"video #{index + 1}: duplicate source video")
            continue
        seen.add(identity)
        normalized.append(cleaned)

    primary_identity = select_primary_video(normalized, preferred_language)
    for video in normalized:
        video["is_primary"] = video_identity(video) == primary_identity
    return normalized, warnings, normalization_safe


def validate_snapshot_metadata(
    item: dict[str, Any],
    normalized_count: int,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    counts: dict[str, int] = {}
    for field in (
        "videos_raw_count",
        "videos_accepted_count",
        "videos_rejected_count",
        "videos_ignored_count",
    ):
        value = item.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"{field} must be a non-negative integer")
        else:
            counts[field] = value

    accepted_count = counts.get("videos_accepted_count")
    if accepted_count is not None and accepted_count != normalized_count:
        errors.append("preview accepted-video count does not match importer normalization")

    raw_count = counts.get("videos_raw_count")
    rejected_count = counts.get("videos_rejected_count")
    ignored_count = counts.get("videos_ignored_count")
    if (
        raw_count is not None
        and accepted_count is not None
        and rejected_count is not None
        and ignored_count is not None
        and raw_count != accepted_count + rejected_count + ignored_count
    ):
        errors.append(
            "raw video count does not equal accepted plus rejected plus ignored counts"
        )

    rejected = item.get("videos_rejected")
    if not isinstance(rejected, list):
        errors.append("videos_rejected must be an array")
    elif rejected_count is not None and rejected_count != len(rejected):
        errors.append("preview rejected-video count does not match rejection details")
    elif any(
        not isinstance(rejection, dict)
        or rejection.get("harmless_duplicate") is not True
        for rejection in rejected
    ):
        errors.append("snapshot contains a non-harmless rejected source record")

    ignored = item.get("videos_ignored")
    if not isinstance(ignored, list):
        errors.append("videos_ignored must be an array")
    elif ignored_count is not None and ignored_count != len(ignored):
        errors.append("preview ignored-video count does not match ignored details")

    if not isinstance(item.get("videos_warnings"), list):
        errors.append("videos_warnings must be an array")

    status = item.get("videos_fetch_status")
    if status == "empty" and any(
        counts.get(field) != 0
        for field in (
            "videos_raw_count",
            "videos_accepted_count",
            "videos_rejected_count",
            "videos_ignored_count",
        )
    ):
        errors.append("empty snapshot must have zero raw, accepted, and rejected videos")
    if status == "success" and raw_count == 0:
        errors.append("non-empty success snapshot must contain source videos")

    signature = item.get("videos_request_signature")
    if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature):
        errors.append("video request signature is missing or malformed")

    timestamp_origin = item.get("videos_timestamp_origin")
    if timestamp_origin not in {"network", "sidecar"}:
        errors.append("video source timestamp origin is not authoritative")

    preferred_language = item.get("videos_preferred_language")
    if not isinstance(preferred_language, str) or not re.fullmatch(
        r"[a-z]{2}", preferred_language
    ):
        errors.append("videos_preferred_language must be an ISO 639-1 code")

    requested_languages = item.get("videos_requested_languages")
    if not isinstance(requested_languages, list) or not requested_languages:
        errors.append("videos_requested_languages must be a non-empty array")
    elif len(requested_languages) > 8 or any(
        not isinstance(language, str)
        or (language != "null" and not re.fullmatch(r"[a-z]{2}", language))
        for language in requested_languages
    ):
        errors.append("videos_requested_languages contains invalid values")
    elif len(requested_languages) != len(set(requested_languages)):
        errors.append("videos_requested_languages must be deduplicated")
    elif preferred_language not in requested_languages:
        errors.append("videos_requested_languages must include the preferred language")

    return not errors, errors


def video_identity(video: dict[str, Any]) -> tuple[str, str]:
    return str(video["site"]), str(video["source_video_id"])


def comparable_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def build_video_plan(
    existing_rows: list[dict[str, Any]],
    desired_videos: list[dict[str, Any]],
    current_primary_identity: tuple[str, str] | None,
    stale_cleanup_safe: bool = True,
    preferred_language: str | None = "en",
    current_primary_exists: bool | None = None,
) -> VideoPlan:
    if current_primary_exists is None:
        current_primary_exists = current_primary_identity is not None
    existing = {video_identity(row): row for row in existing_rows}
    desired = {video_identity(row): row for row in desired_videos}
    inserts = [row for identity, row in desired.items() if identity not in existing]
    updates: list[dict[str, Any]] = []
    for identity, row in desired.items():
        current = existing.get(identity)
        if current and any(
            comparable_value(current.get(field)) != comparable_value(row.get(field))
            for field in VIDEO_COMPARE_FIELDS
        ):
            updates.append(row)
    stale_ids = (
        [
            int(row["id"])
            for identity, row in existing.items()
            if identity not in desired
        ]
        if stale_cleanup_safe
        else []
    )
    candidates = list(desired.values())
    if not stale_cleanup_safe:
        merged = {identity: dict(row) for identity, row in existing.items()}
        merged.update({identity: dict(row) for identity, row in desired.items()})
        candidates = list(merged.values())
    candidate_identities = {video_identity(video) for video in candidates}
    preserve_current_primary = not stale_cleanup_safe and current_primary_exists
    if preserve_current_primary:
        selected = (
            current_primary_identity
            if current_primary_identity in candidate_identities
            else None
        )
        primary_changed = False
    else:
        selected = select_primary_video(candidates, preferred_language)
        primary_changed = selected != current_primary_identity
    return VideoPlan(
        inserts=inserts,
        updates=updates,
        stale_ids=stale_ids,
        selected_identity=selected,
        primary_changed=primary_changed,
        primary_preserved=preserve_current_primary,
    )


def load_existing_state(
    connection: Connection,
    content_id: int,
) -> tuple[list[dict[str, Any]], tuple[str, str] | None, bool]:
    videos = list(
        connection.execute(
            text(
                """
                SELECT id, site, source_video_id, video_type, name, official,
                       language_code, country_code, published_at, size
                FROM content_videos
                WHERE content_id = :content_id AND source = 'tmdb'
                """
            ),
            {"content_id": content_id},
        ).mappings()
    )
    primary = connection.execute(
        text(
            """
            SELECT cv.source, cv.site, cv.source_video_id
            FROM content_primary_videos cpv
            JOIN content_videos cv ON cv.id = cpv.content_video_id
            WHERE cpv.content_id = :content_id
            """
        ),
        {"content_id": content_id},
    ).mappings().first()
    primary_identity = None
    if primary and primary["source"] == "tmdb":
        primary_identity = (str(primary["site"]), str(primary["source_video_id"]))
    return [dict(row) for row in videos], primary_identity, primary is not None


UPSERT_VIDEO_SQL = text(
    """
    INSERT INTO content_videos (
        content_id, source, source_video_id, site, video_type, name, official,
        language_code, country_code, published_at, size, created_at, updated_at
    ) VALUES (
        :content_id, 'tmdb', :source_video_id, :site, :video_type, :name, :official,
        :language_code, :country_code, :published_at, :size, NOW(), NOW()
    )
    ON CONFLICT (content_id, source, site, source_video_id) DO UPDATE
    SET video_type = EXCLUDED.video_type,
        name = EXCLUDED.name,
        official = EXCLUDED.official,
        language_code = EXCLUDED.language_code,
        country_code = EXCLUDED.country_code,
        published_at = EXCLUDED.published_at,
        size = EXCLUDED.size,
        updated_at = NOW()
    """
)


def update_fetch_state(
    connection: Connection,
    content_id: int,
    status: str,
    error: str | None,
    attempted_at: datetime,
    source_fetched_at: datetime | None,
    *,
    retryable: bool = False,
    failure_class: str | None = None,
) -> bool:
    stored_error = sanitize_fetch_error(error)
    stored_failure_class = normalize_failure_class(failure_class, status)
    result = connection.execute(
        text(
            """
            INSERT INTO content_video_fetch_state (
                content_id, source, last_attempted_at, last_fetched_at, last_fetch_status,
                last_fetch_error, last_fetch_retryable, last_failure_class,
                consecutive_failure_count, source_snapshot_empty, created_at, updated_at
            ) VALUES (
                :content_id, 'tmdb', :attempted_at, :source_fetched_at, :status, :error,
                :retryable, :failure_class, :failure_count, :snapshot_empty, NOW(), NOW()
            )
            ON CONFLICT (content_id, source) DO UPDATE
            SET last_attempted_at = EXCLUDED.last_attempted_at,
                last_fetched_at = CASE
                    WHEN EXCLUDED.last_fetch_status IN ('success', 'empty')
                    THEN EXCLUDED.last_fetched_at
                    ELSE content_video_fetch_state.last_fetched_at
                END,
                last_fetch_status = EXCLUDED.last_fetch_status,
                last_fetch_error = EXCLUDED.last_fetch_error,
                last_fetch_retryable = EXCLUDED.last_fetch_retryable,
                last_failure_class = EXCLUDED.last_failure_class,
                consecutive_failure_count = CASE
                    WHEN EXCLUDED.last_fetch_status IN ('success', 'empty') THEN 0
                    ELSE content_video_fetch_state.consecutive_failure_count + 1
                END,
                source_snapshot_empty = EXCLUDED.source_snapshot_empty,
                updated_at = NOW()
            RETURNING 1
            """
        ),
        {
            "content_id": content_id,
            "attempted_at": attempted_at,
            "source_fetched_at": source_fetched_at,
            "status": status,
            "error": stored_error,
            "retryable": bool(retryable) if status in {"failed", "incomplete"} else False,
            "failure_class": stored_failure_class,
            "failure_count": 1 if status in {"failed", "incomplete"} else 0,
            "snapshot_empty": status == "empty",
        },
    )
    return result.scalar_one_or_none() == 1


def sanitize_fetch_error(value: str | None) -> str | None:
    if not value:
        return None
    sanitized = re.sub(
        r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+",
        r"\1[REDACTED]",
        str(value),
    )
    sanitized = re.sub(
        r"(?i)(api[_-]?key|access[_-]?token|authorization)(\s*[=:]\s*)[^\s,;]+",
        r"\1\2[REDACTED]",
        sanitized,
    )
    sanitized = " ".join(sanitized.split())
    return sanitized[:MAX_STORED_ERROR_LENGTH] or None


def normalize_failure_class(value: str | None, status: str) -> str | None:
    if status in {"success", "empty"}:
        return None
    normalized = re.sub(
        r"[^a-z0-9_]+",
        "_",
        str(value or "unclassified_failure").casefold(),
    )
    return normalized.strip("_")[:50] or "unclassified_failure"


def apply_video_snapshot(
    connection: Connection,
    content_id: int,
    plan: VideoPlan,
) -> None:
    for video in [*plan.inserts, *plan.updates]:
        connection.execute(UPSERT_VIDEO_SQL, {"content_id": content_id, **video})

    if plan.stale_ids:
        connection.execute(
            text(
                """
                DELETE FROM content_videos
                WHERE content_id = :content_id
                  AND source = 'tmdb'
                  AND id = ANY(:stale_ids)
                """
            ),
            {"content_id": content_id, "stale_ids": plan.stale_ids},
        )

    if plan.selected_identity and plan.primary_changed:
        site, source_video_id = plan.selected_identity
        selected_id = connection.execute(
            text(
                """
                SELECT id FROM content_videos
                WHERE content_id = :content_id
                  AND source = 'tmdb'
                  AND site = :site
                  AND source_video_id = :source_video_id
                """
            ),
            {
                "content_id": content_id,
                "site": site,
                "source_video_id": source_video_id,
            },
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO content_primary_videos (content_id, content_video_id, selected_at)
                VALUES (:content_id, :video_id, NOW())
                ON CONFLICT (content_id) DO UPDATE
                SET content_video_id = EXCLUDED.content_video_id,
                    selected_at = NOW()
                """
            ),
            {"content_id": content_id, "video_id": selected_id},
        )
    elif plan.selected_identity is None and plan.primary_changed:
        connection.execute(
            text(
                """
                DELETE FROM content_primary_videos cpv
                USING content_videos cv
                WHERE cpv.content_id = :content_id
                  AND cv.id = cpv.content_video_id
                  AND cv.source = 'tmdb'
                """
            ),
            {"content_id": content_id},
        )


def parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                return None
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return None


def process_item(
    connection: Connection,
    item: dict[str, Any],
    attempted_at: datetime,
    apply: bool,
    stats: ImportStats,
) -> None:
    stats.items_seen += 1
    title = str(item.get("title") or "Untitled")
    source_id = str(item.get("source_id") or item.get("tmdb_id") or "unknown")
    content_id = resolve_content_id(connection, item)
    if content_id is None:
        stats.titles_skipped += 1
        stats.warnings.append(f"{title}: no local content matched TMDb ID {source_id}")
        return
    stats.titles_resolved += 1

    status = str(item.get("videos_fetch_status") or "incomplete")
    complete = item.get("videos_snapshot_complete") is True
    preview_cleanup_safe = item.get("videos_stale_cleanup_safe") is True
    source_fetched_at = parse_timestamp(item.get("videos_source_fetched_at"))
    error_messages = [str(item["videos_fetch_error"])] if item.get(
        "videos_fetch_error"
    ) else []
    retryable = item.get("videos_retryable") is True
    failure_class = str(item.get("videos_failure_class") or "unclassified_failure")

    preferred_language_value = item.get("videos_preferred_language")
    preferred_language = (
        preferred_language_value
        if isinstance(preferred_language_value, str)
        and re.fullmatch(r"[a-z]{2}", preferred_language_value)
        else None
    )
    videos, warnings, normalization_safe = normalize_preview_videos(
        item,
        preferred_language,
    )
    stats.warnings.extend(f"{title}: {warning}" for warning in warnings)
    snapshot_metadata_safe, snapshot_metadata_errors = validate_snapshot_metadata(
        item,
        len(videos),
    )
    error_messages.extend(snapshot_metadata_errors)

    stale_cleanup_safe = bool(
        status in {"success", "empty"}
        and complete
        and preview_cleanup_safe
        and normalization_safe
        and snapshot_metadata_safe
        and source_fetched_at is not None
    )
    effective_status = status
    if status not in {"success", "empty", "failed", "incomplete"}:
        effective_status = "incomplete"
        error_messages.append(f"unknown video fetch status {status!r}")
    elif status in {"success", "empty"} and not stale_cleanup_safe:
        effective_status = "incomplete"
        if source_fetched_at is None:
            error_messages.append("source fetch timestamp is missing or malformed")
        if not preview_cleanup_safe or not complete:
            error_messages.append("video snapshot is not authoritative")
        if not normalization_safe or not snapshot_metadata_safe:
            error_messages.append("preview videos failed importer validation")

    existing, current_primary, current_primary_exists = load_existing_state(
        connection,
        content_id,
    )
    plan = build_video_plan(
        existing,
        videos,
        current_primary,
        stale_cleanup_safe=stale_cleanup_safe,
        preferred_language=preferred_language,
        current_primary_exists=current_primary_exists,
    )
    changed = bool(
        plan.inserts or plan.updates or plan.stale_ids or plan.primary_changed
    )
    if changed:
        stats.titles_changed += 1
    stats.videos_inserted += len(plan.inserts)
    stats.videos_updated += len(plan.updates)
    stats.videos_removed += len(plan.stale_ids)
    stats.primary_changes += int(plan.primary_changed)
    stats.reports.append(
        {
            "title": title,
            "content_id": content_id,
            "tmdb_id": source_id,
            "status": status,
            "effective_status": effective_status,
            "stale_cleanup_safe": stale_cleanup_safe,
            "inserted": len(plan.inserts),
            "updated": len(plan.updates),
            "removed": len(plan.stale_ids),
            "primary": plan.selected_identity,
            "primary_changed": plan.primary_changed,
            "primary_preserved": plan.primary_preserved,
            "reason": "; ".join(dict.fromkeys(error_messages)) or None,
        }
    )

    if effective_status in {"failed", "incomplete"} and not videos:
        stats.titles_skipped += 1

    if apply:
        apply_video_snapshot(connection, content_id, plan)
        state_changed = update_fetch_state(
            connection,
            content_id,
            effective_status,
            "; ".join(dict.fromkeys(error_messages)) or None,
            attempted_at,
            source_fetched_at if effective_status in {"success", "empty"} else None,
            retryable=retryable if effective_status in {"failed", "incomplete"} else False,
            failure_class=failure_class,
        )
        stats.fetch_states_updated += int(state_changed)


def print_report(stats: ImportStats) -> None:
    heading = "Video metadata changes:" if stats.mode == "APPLY" else "Planned video metadata changes:"
    print(f"\n{heading}")
    for report in stats.reports[:MAX_ROW_REPORT_ITEMS]:
        print(
            f"- {report['title']} [content_id={report['content_id']}, "
            f"tmdb_id={report['tmdb_id']}]"
        )
        if report.get("skipped"):
            print(f"  - skipped: {report['reason']}")
            continue
        print(
            f"  - inserted: {report['inserted']}, updated: {report['updated']}, "
            f"removed stale: {report['removed']}"
        )
        if not report.get("stale_cleanup_safe", False):
            print("  - stale cleanup: disabled (snapshot is not authoritative)")
        if report.get("reason"):
            print(f"  - note: {report['reason']}")
        primary = report.get("primary")
        if report.get("primary_preserved") and primary is None:
            print("  - primary: existing non-TMDb selection preserved")
        elif report.get("primary_preserved"):
            print(f"  - primary: {primary[0]}/{primary[1]} (preserved)")
        else:
            print(f"  - primary: {primary[0]}/{primary[1]}" if primary else "  - primary: none")
    if len(stats.reports) > MAX_ROW_REPORT_ITEMS:
        print(f"... and {len(stats.reports) - MAX_ROW_REPORT_ITEMS} more")

    print("\nSummary:")
    print(f"- Mode: {stats.mode}")
    print(f"- Preview items seen: {stats.items_seen}")
    print(f"- Titles resolved: {stats.titles_resolved}")
    print(f"- Titles changed: {stats.titles_changed}")
    print(f"- Titles skipped: {stats.titles_skipped}")
    print(f"- Videos inserted: {stats.videos_inserted}")
    print(f"- Videos updated: {stats.videos_updated}")
    print(f"- Stale TMDb videos removed: {stats.videos_removed}")
    print(f"- Primary selections changed: {stats.primary_changes}")
    if stats.warnings:
        print("\nWarnings:")
        for warning in stats.warnings[:MAX_ROW_REPORT_ITEMS]:
            print(f"- {warning}")


def process_preview_items(
    items: list[dict[str, Any]],
    database_url: str,
    apply: bool,
    *,
    attempted_at: datetime | None = None,
) -> ImportStats:
    """Run the established video importer for an in-memory preview item list."""
    stats = ImportStats(mode="APPLY" if apply else "DRY RUN")
    attempt_time = attempted_at or datetime.now(timezone.utc)
    engine = create_engine(normalize_database_url(database_url), future=True)

    try:
        for item in items:
            if apply:
                with engine.begin() as connection:
                    process_item(connection, item, attempt_time, True, stats)
            else:
                with engine.connect() as connection:
                    process_item(connection, item, attempt_time, False, stats)
    finally:
        engine.dispose()
    return stats


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    preview_path = resolve_path(args.preview)
    database_url = os.getenv(DATABASE_URL_ENV)
    if not database_url:
        print(f"{DATABASE_URL_ENV} is required for dry-run and apply modes.")
        return 1

    try:
        _payload, items = load_preview(preview_path)
    except ValueError as exc:
        print(exc)
        return 1

    if args.source_id:
        items = [
            item
            for item in items
            if str(item.get("source_id") or item.get("tmdb_id")) == args.source_id
        ]
    if args.limit:
        items = items[: args.limit]

    try:
        stats = process_preview_items(items, database_url, args.apply)
    except SQLAlchemyError as exc:
        print(f"Database operation failed: {exc}")
        return 1

    print_report(stats)
    if not args.apply:
        print("\nDry run only. No database changes were made.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
