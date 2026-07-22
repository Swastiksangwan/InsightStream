#!/usr/bin/env python3
"""
Read-only planner for series lifecycle metadata refreshes.

This script:
- connects to PostgreSQL using DATABASE_URL
- reads existing series with TMDb external IDs
- inspects content_series_metadata freshness/status fields
- writes analytics/config/series_refresh_targets.json for fetch_tmdb_sample.py
- writes analytics/processed/tmdb/run_reports/series_refresh_plan_report.json
- does not modify PostgreSQL
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency guidance for script-only runs.
    load_dotenv = None


DATABASE_URL_ENV = "DATABASE_URL"
from analytics.scripts.common.paths import REPO_ROOT
DEFAULT_OUTPUT_PATH = REPO_ROOT / "analytics" / "config" / "series_refresh_targets.json"
DEFAULT_REPORT_PATH = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "tmdb"
    / "run_reports"
    / "series_refresh_plan_report.json"
)
REFRESH_PRIORITY = "series_refresh"
REFRESH_STATUS = "refresh_due"
DEFAULT_REFRESH_WINDOW_DAYS = 7
DEFAULT_RECENT_WINDOW_DAYS = 60
NEXT_EPISODE_WINDOW_DAYS = 14
ACTIVE_REFRESH_STATUSES = {"ongoing", "upcoming", "unknown"}
INACTIVE_REFRESH_STATUSES = {"ended", "cancelled"}


class SeriesRefreshPlannerError(RuntimeError):
    pass


@dataclass(frozen=True)
class RefreshDecision:
    selected: bool
    reasons: list[str]


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan read-only refresh targets for existing catalog series."
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH.relative_to(REPO_ROOT)),
        help=(
            "Refresh target JSON output path. Defaults to "
            f"{DEFAULT_OUTPUT_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--report",
        default=str(DEFAULT_REPORT_PATH.relative_to(REPO_ROOT)),
        help=(
            "JSON report output path. Defaults to "
            f"{DEFAULT_REPORT_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--due-only",
        action="store_true",
        help="Select only due series. This is the default behavior.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Select all filtered series regardless of freshness/status.",
    )
    parser.add_argument(
        "--include-ended",
        action="store_true",
        help="Allow ended/cancelled series to be selected by freshness rules.",
    )
    parser.add_argument(
        "--status",
        help=(
            "Limit evaluation to one normalized series status, for example "
            "ongoing, ended, cancelled, upcoming, or unknown."
        ),
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        help="Cap selected refresh targets after due/all selection.",
    )
    parser.add_argument(
        "--refresh-window-days",
        type=positive_int,
        default=DEFAULT_REFRESH_WINDOW_DAYS,
        help="Series with stale refresh timestamps older than this are due.",
    )
    parser.add_argument(
        "--recent-window-days",
        type=positive_int,
        default=DEFAULT_RECENT_WINDOW_DAYS,
        help="Recently aired/activity series window used for refresh decisions.",
    )
    return parser.parse_args(argv)


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def resolve_path(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, ensure_ascii=False) + "\n")


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def normalize_status(value: Any) -> str:
    return (clean_text(value) or "unknown").lower()


def load_database_url() -> str | None:
    if load_dotenv is not None:
        load_dotenv(REPO_ROOT / ".env")
        load_dotenv(REPO_ROOT / "backend" / ".env")
    return os.getenv(DATABASE_URL_ENV)


def normalize_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        try:
            text_value = value.strip()
            if text_value.endswith("Z"):
                text_value = f"{text_value[:-1]}+00:00"
            parsed = datetime.fromisoformat(text_value)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def is_older_than(value: Any, now: datetime, days: int) -> bool:
    parsed = normalize_datetime(value)
    if parsed is None:
        return False
    return parsed < now - timedelta(days=days)


def is_within_next_days(value: Any, today: date, days: int) -> bool:
    parsed = normalize_date(value)
    if parsed is None:
        return False
    return today <= parsed <= today + timedelta(days=days)


def aired_after_last_refresh(
    air_date_value: Any,
    last_refreshed_value: Any,
    today: date,
) -> bool:
    air_date = normalize_date(air_date_value)
    last_refreshed_at = normalize_datetime(last_refreshed_value)
    if air_date is None or last_refreshed_at is None:
        return False
    if air_date > today:
        return False
    return last_refreshed_at.date() < air_date


def is_within_recent_days(value: Any, today: date, days: int) -> bool:
    parsed = normalize_date(value)
    if parsed is None:
        return False
    return today - timedelta(days=days) <= parsed <= today


def evaluate_refresh_status(
    series: dict[str, Any],
    now: datetime,
    refresh_window_days: int = DEFAULT_REFRESH_WINDOW_DAYS,
    recent_window_days: int = DEFAULT_RECENT_WINDOW_DAYS,
    include_ended: bool = False,
    select_all: bool = False,
) -> RefreshDecision:
    if select_all:
        return RefreshDecision(True, ["selected by --all"])

    has_series_metadata = bool(series.get("has_series_metadata"))
    if not has_series_metadata:
        return RefreshDecision(True, ["missing content_series_metadata row"])

    last_refreshed_at = series.get("last_refreshed_at")
    if last_refreshed_at is None:
        return RefreshDecision(True, ["last_refreshed_at is null"])

    status = normalize_status(series.get("series_status_normalized"))
    today = now.date()
    is_stale = is_older_than(last_refreshed_at, now, refresh_window_days)

    if status in INACTIVE_REFRESH_STATUSES and not include_ended:
        return RefreshDecision(False, [f"{status} series skipped by default"])

    reasons: list[str] = []

    if status in ACTIVE_REFRESH_STATUSES and is_stale:
        reasons.append(
            f"{status} status and last_refreshed_at older than {refresh_window_days} days"
        )

    if status in INACTIVE_REFRESH_STATUSES and include_ended and is_stale:
        reasons.append(
            f"{status} status included and last_refreshed_at older than {refresh_window_days} days"
        )

    # If TMDb previously reported a next episode date and that date has passed,
    # refresh even if the normal freshness window has not elapsed.
    next_episode_passed_since_refresh = (
        status in ACTIVE_REFRESH_STATUSES
        or (include_ended and status in INACTIVE_REFRESH_STATUSES)
    ) and aired_after_last_refresh(
        series.get("next_episode_air_date"),
        last_refreshed_at,
        today,
    )
    if next_episode_passed_since_refresh:
        reasons.append("next_episode_air_date has passed since last refresh")
    elif is_within_next_days(
        series.get("next_episode_air_date"),
        today,
        NEXT_EPISODE_WINDOW_DAYS,
    ):
        reasons.append(
            f"next_episode_air_date within next {NEXT_EPISODE_WINDOW_DAYS} days"
        )

    if is_stale and is_within_recent_days(
        series.get("last_episode_air_date"),
        today,
        recent_window_days,
    ):
        reasons.append(
            f"last_episode_air_date within last {recent_window_days} days and refresh is stale"
        )

    if is_stale and is_within_recent_days(
        series.get("latest_activity_date"),
        today,
        recent_window_days,
    ):
        reasons.append(
            f"latest_activity_date within last {recent_window_days} days and refresh is stale"
        )

    if reasons:
        return RefreshDecision(True, reasons)

    return RefreshDecision(False, ["not due by refresh rules"])


def fetch_series_rows(database_url: str) -> list[dict[str, Any]]:
    engine = create_engine(database_url)
    query = text("""
        SELECT
            c.id AS content_id,
            c.title,
            c.latest_activity_date,
            ei.external_id AS source_id,
            csm.content_id IS NOT NULL AS has_series_metadata,
            csm.series_status_normalized,
            csm.last_episode_air_date,
            csm.next_episode_air_date,
            csm.last_refreshed_at
        FROM content c
        JOIN external_ids ei
            ON ei.content_id = c.id
           AND LOWER(ei.source_name) = 'tmdb'
        LEFT JOIN content_series_metadata csm
            ON csm.content_id = c.id
        WHERE c.content_type = 'series'
        ORDER BY c.title ASC;
    """)

    try:
        with engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
    except SQLAlchemyError as exc:
        raise SeriesRefreshPlannerError(f"Database query failed: {exc}") from exc
    finally:
        engine.dispose()

    return [dict(row) for row in rows]


def filters_used(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "due_only": True if not args.all else False,
        "all": args.all,
        "include_ended": args.include_ended,
        "status": args.status,
        "limit": args.limit,
        "refresh_window_days": args.refresh_window_days,
        "recent_window_days": args.recent_window_days,
    }


def status_counts(series_rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in series_rows:
        if not row.get("has_series_metadata"):
            counts["missing_metadata"] += 1
        else:
            counts[normalize_status(row.get("series_status_normalized"))] += 1
    return dict(sorted(counts.items()))


def status_matches(row: dict[str, Any], status_filter: str | None) -> bool:
    if not status_filter:
        return True
    return normalize_status(row.get("series_status_normalized")) == status_filter.lower()


def target_for_series(row: dict[str, Any], reasons: list[str]) -> dict[str, str]:
    return {
        "title": row["title"],
        "content_type": "series",
        "source_name": "tmdb",
        "source_id": str(row["source_id"]),
        "priority": REFRESH_PRIORITY,
        "ingestion_status": REFRESH_STATUS,
        "notes": f"Selected for series refresh: {'; '.join(reasons)}.",
    }


def build_plan(
    series_rows: list[dict[str, Any]],
    args: argparse.Namespace,
    now: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    warnings: list[str] = []
    failures: list[str] = []
    targets: list[dict[str, str]] = []
    per_series: list[dict[str, Any]] = []
    skipped_not_due = 0
    selected_count_before_limit = 0
    status_filter = args.status.lower() if args.status else None
    filtered_rows = [row for row in series_rows if status_matches(row, status_filter)]

    for row in filtered_rows:
        decision = evaluate_refresh_status(
            row,
            now,
            refresh_window_days=args.refresh_window_days,
            recent_window_days=args.recent_window_days,
            include_ended=args.include_ended,
            select_all=args.all,
        )
        selected = decision.selected
        reason = "; ".join(decision.reasons)

        if selected:
            selected_count_before_limit += 1
            if args.limit and selected_count_before_limit > args.limit:
                selected = False
                reason = f"selected by rules but skipped by --limit {args.limit}"

        if selected:
            targets.append(target_for_series(row, decision.reasons))
        else:
            skipped_not_due += 1

        per_series.append(
            {
                "title": row["title"],
                "source_id": str(row["source_id"]),
                "series_status_normalized": row.get("series_status_normalized"),
                "last_episode_air_date": row.get("last_episode_air_date"),
                "next_episode_air_date": row.get("next_episode_air_date"),
                "latest_activity_date": row.get("latest_activity_date"),
                "last_refreshed_at": row.get("last_refreshed_at"),
                "refresh_reason": reason,
                "selected": selected,
            }
        )

    report = {
        "generated_at": now.isoformat(),
        "script_name": "plan_series_refresh.py",
        "filters_used": filters_used(args),
        "total_series": len(series_rows),
        "series_after_filters": len(filtered_rows),
        "selected_for_refresh": len(targets),
        "skipped_not_due": skipped_not_due,
        "status_counts": status_counts(series_rows),
        "warnings": warnings,
        "failures": failures,
        "per_series": per_series,
    }

    return targets, report


def build_target_file(targets: list[dict[str, str]], now: datetime) -> dict[str, Any]:
    return {
        "description": (
            "Read-only generated refresh targets for existing InsightStream series. "
            "Do not add new catalog titles from this file."
        ),
        "generated_at": now.isoformat(),
        "generated_by": "analytics/scripts/refresh/plan_series_refresh.py",
        "targets": targets,
    }


def print_summary(
    report: dict[str, Any],
    output_path: Path,
    report_path: Path,
) -> None:
    print("\nSeries refresh plan summary:")
    print(f"- Total series: {report['total_series']}")
    print(f"- Series after filters: {report['series_after_filters']}")
    print(f"- Selected for refresh: {report['selected_for_refresh']}")
    print(f"- Skipped/not due: {report['skipped_not_due']}")
    print("- Status counts:")
    for status, count in report["status_counts"].items():
        print(f"  - {status}: {count}")
    print(f"- Output target path: {relative_path(output_path)}")
    print(f"- Report path: {relative_path(report_path)}")
    print("- No database changes were made.")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_path = resolve_path(args.output)
    report_path = resolve_path(args.report)
    database_url = load_database_url()

    if not database_url:
        print(
            f"Missing {DATABASE_URL_ENV}. Export it before running the series refresh planner.",
            file=sys.stderr,
        )
        return 1

    now = datetime.now(timezone.utc)

    try:
        series_rows = fetch_series_rows(database_url)
        targets, report = build_plan(series_rows, args, now)
        write_json(output_path, build_target_file(targets, now))
        write_json(report_path, report)
    except SeriesRefreshPlannerError as exc:
        print(f"Series refresh planner failed: {exc}", file=sys.stderr)
        return 1

    print_summary(report, output_path, report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
