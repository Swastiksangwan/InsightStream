"""Shared, database-driven refresh planning for series metadata and videos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Iterator

from sqlalchemy import create_engine, text

from analytics.scripts.refresh.plan_series_refresh import (
    DEFAULT_RECENT_WINDOW_DAYS,
    DEFAULT_REFRESH_WINDOW_DAYS,
    evaluate_refresh_status,
    normalize_datetime,
)


SERIES_SCOPE = "series_metadata"
VIDEO_SCOPE = "videos"
ALL_SCOPE = "all"
VALID_SCOPES = {SERIES_SCOPE, VIDEO_SCOPE, ALL_SCOPE}
PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}
DEFAULT_PAGE_SIZE = 100
MAX_AUTOMATIC_VIDEO_FAILURES = 3

VIDEO_CADENCE_DAYS = {
    "upcoming_release": 1,
    "recently_released": 2,
    "currently_airing": 2,
    "future_season_announced": 7,
    "stale_older_title": 30,
    "previous_transient_failure": 1,
    "never_fetched": 0,
}


@dataclass(frozen=True)
class ScopeDecision:
    selected: bool
    reason: str
    priority: str
    last_refreshed_at: datetime | None
    due_at: datetime | None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _as_utc(value: Any) -> datetime | None:
    return normalize_datetime(value)


def _video_lifecycle(row: dict[str, Any], now: datetime) -> tuple[str, str]:
    today = now.date()
    release_date = _as_date(row.get("release_date"))
    latest_activity = _as_date(row.get("latest_activity_date"))
    next_episode = _as_date(row.get("next_episode_air_date"))
    next_season = _as_date(row.get("next_season_air_date"))
    status = str(row.get("series_status_normalized") or "").casefold()

    if release_date and today <= release_date <= today + timedelta(days=90):
        return "upcoming_release", "high"
    if release_date and today - timedelta(days=30) <= release_date <= today:
        return "recently_released", "high"
    if row.get("content_type") == "series":
        if status in {"ongoing", "upcoming", "unknown"} and next_episode:
            if today <= next_episode <= today + timedelta(days=21):
                return "currently_airing", "high"
        if bool(row.get("has_announced_season")) or (
            next_season and next_season >= today
        ):
            return "future_season_announced", "normal"
        if status == "ongoing" and latest_activity:
            if today - timedelta(days=45) <= latest_activity <= today:
                return "currently_airing", "high"
    return "stale_older_title", "low"


def evaluate_video_refresh(
    row: dict[str, Any],
    now: datetime,
    *,
    forced: bool = False,
    include_not_due: bool = False,
) -> ScopeDecision:
    last_status = str(row.get("video_last_fetch_status") or "").casefold()
    last_fetched = _as_utc(row.get("video_last_fetched_at"))
    last_attempted = _as_utc(row.get("video_last_attempted_at"))

    if forced:
        return ScopeDecision(True, "forced_by_cli", "high", last_fetched, now)

    if not last_status:
        return ScopeDecision(True, "never_fetched", "high", None, now)

    if last_status == "incomplete":
        return ScopeDecision(
            False,
            "normalization_review",
            "low",
            last_fetched,
            None,
        )

    if last_status == "failed":
        retryable = row.get("video_last_fetch_retryable") is True
        failure_count = max(int(row.get("video_consecutive_failure_count") or 0), 1)
        if not retryable or failure_count >= MAX_AUTOMATIC_VIDEO_FAILURES:
            return ScopeDecision(False, "manual_review_required", "low", last_fetched, None)
        backoff_days = min(2 ** (failure_count - 1), 7)
        due_at = (last_attempted or last_fetched or now) + timedelta(days=backoff_days)
        return ScopeDecision(
            include_not_due or due_at <= now,
            "previous_transient_failure",
            "high",
            last_fetched,
            due_at,
        )

    reason, priority = _video_lifecycle(row, now)
    cadence = VIDEO_CADENCE_DAYS[reason]
    due_at = (last_fetched or last_attempted or now) + timedelta(days=cadence)
    return ScopeDecision(
        include_not_due or due_at <= now,
        reason,
        priority,
        last_fetched,
        due_at,
    )


def evaluate_series_refresh(
    row: dict[str, Any],
    now: datetime,
    *,
    forced: bool = False,
    include_not_due: bool = False,
    refresh_window_days: int = DEFAULT_REFRESH_WINDOW_DAYS,
    recent_window_days: int = DEFAULT_RECENT_WINDOW_DAYS,
) -> ScopeDecision:
    last_refreshed = _as_utc(row.get("last_refreshed_at"))
    if forced:
        return ScopeDecision(True, "forced_by_cli", "high", last_refreshed, now)

    legacy = evaluate_refresh_status(
        row,
        now,
        refresh_window_days=refresh_window_days,
        recent_window_days=recent_window_days,
    )
    selected = legacy.selected or include_not_due
    reason = "; ".join(legacy.reasons)
    cadence_due_at = (
        last_refreshed + timedelta(days=refresh_window_days)
        if last_refreshed
        else now
    )
    due_at = min(cadence_due_at, now) if legacy.selected else cadence_due_at
    return ScopeDecision(selected, reason, "high" if legacy.selected else "low", last_refreshed, due_at)


def _scope_requested(scope: str, candidate: str) -> bool:
    return scope == ALL_SCOPE or scope == candidate


def build_plan_item(
    row: dict[str, Any],
    now: datetime,
    *,
    scope: str = ALL_SCOPE,
    forced: bool = False,
    include_not_due: bool = False,
) -> dict[str, Any] | None:
    if scope not in VALID_SCOPES:
        raise ValueError(f"Unsupported refresh scope: {scope}")

    decisions: dict[str, ScopeDecision] = {}
    content_type = row.get("content_type")
    if _scope_requested(scope, SERIES_SCOPE) and content_type == "series":
        decisions[SERIES_SCOPE] = evaluate_series_refresh(
            row, now, forced=forced, include_not_due=include_not_due
        )
    if _scope_requested(scope, VIDEO_SCOPE):
        decisions[VIDEO_SCOPE] = evaluate_video_refresh(
            row, now, forced=forced, include_not_due=include_not_due
        )

    selected = {name: decision for name, decision in decisions.items() if decision.selected}
    if not selected:
        return None

    scopes = [name for name in (SERIES_SCOPE, VIDEO_SCOPE) if name in selected]
    priority = min(
        (decision.priority for decision in selected.values()),
        key=lambda value: PRIORITY_ORDER[value],
    )
    return {
        "content_id": int(row["content_id"]),
        "title": str(row["title"]),
        "content_type": str(content_type),
        "tmdb_id": str(row["source_id"]),
        "original_language": row.get("original_language"),
        "refresh_scopes": scopes,
        "reasons": {name: selected[name].reason for name in scopes},
        "last_refreshed_at": {
            name: selected[name].last_refreshed_at.isoformat()
            if selected[name].last_refreshed_at
            else None
            for name in scopes
        },
        "due_at": {
            name: selected[name].due_at.isoformat() if selected[name].due_at else None
            for name in scopes
        },
        "priority": priority,
    }


CONTENT_PAGE_QUERY = text("""
    SELECT
        c.id AS content_id,
        c.title,
        c.content_type,
        c.original_language,
        c.release_date,
        c.latest_activity_date,
        ei.external_id AS source_id,
        csm.content_id IS NOT NULL AS has_series_metadata,
        csm.series_status_normalized,
        csm.in_production,
        csm.last_episode_air_date,
        csm.next_episode_air_date,
        csm.next_season_air_date,
        csm.has_announced_season,
        csm.last_refreshed_at,
        cvfs.last_attempted_at AS video_last_attempted_at,
        cvfs.last_fetched_at AS video_last_fetched_at,
        cvfs.last_fetch_status AS video_last_fetch_status,
        cvfs.last_fetch_error AS video_last_fetch_error,
        cvfs.last_fetch_retryable AS video_last_fetch_retryable,
        cvfs.last_failure_class AS video_last_failure_class,
        cvfs.consecutive_failure_count AS video_consecutive_failure_count
    FROM content c
    JOIN external_ids ei
      ON ei.content_id = c.id
     AND LOWER(ei.source_name) = 'tmdb'
    LEFT JOIN content_series_metadata csm ON csm.content_id = c.id
    LEFT JOIN content_video_fetch_state cvfs
      ON cvfs.content_id = c.id
     AND LOWER(cvfs.source) = 'tmdb'
    WHERE (:content_id IS NULL OR c.id = :content_id)
      AND (:source_id IS NULL OR ei.external_id = :source_id)
      AND (:content_type IS NULL OR c.content_type = :content_type)
      AND c.id > :after_id
    ORDER BY c.id ASC
    LIMIT :page_size
""")


def iter_content_rows(
    database_url: str,
    *,
    content_id: int | None = None,
    source_id: str | None = None,
    content_type: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Iterator[dict[str, Any]]:
    engine = create_engine(database_url, future=True)
    after_id = 0
    try:
        with engine.connect() as connection:
            while True:
                rows = connection.execute(
                    CONTENT_PAGE_QUERY,
                    {
                        "content_id": content_id,
                        "source_id": source_id,
                        "content_type": content_type,
                        "after_id": after_id,
                        "page_size": page_size,
                    },
                ).mappings().all()
                if not rows:
                    break
                for row in rows:
                    item = dict(row)
                    after_id = int(item["content_id"])
                    yield item
                if len(rows) < page_size:
                    break
    finally:
        engine.dispose()


def build_refresh_plan(
    rows: Iterable[dict[str, Any]],
    now: datetime,
    *,
    scope: str = ALL_SCOPE,
    explicit_target: bool = False,
    include_not_due: bool = False,
    priority: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        item = build_plan_item(
            row,
            now,
            scope=scope,
            forced=explicit_target,
            include_not_due=include_not_due,
        )
        if item is None or (priority and item["priority"] != priority):
            continue
        items.append(item)
        if limit and len(items) > limit:
            items.sort(
                key=lambda entry: (
                    PRIORITY_ORDER[entry["priority"]],
                    int(entry["content_id"]),
                )
            )
            items.pop()
    return sorted(
        items,
        key=lambda item: (
            PRIORITY_ORDER[item["priority"]],
            int(item["content_id"]),
        ),
    )


def estimate_request_count(items: list[dict[str, Any]]) -> int:
    # Every selected title uses one details request; combined series scopes share it.
    return len(items)
