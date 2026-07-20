#!/usr/bin/env python3
"""Coordinate DB-planned, scope-isolated content refreshes."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

from build_content_refresh_plan import build_payload, load_database_url
from content_refresh_executor import execute_plan_item
from content_refresh_planner import ALL_SCOPE, SERIES_SCOPE, VALID_SCOPES, VIDEO_SCOPE
from fetch_tmdb_sample import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CONCURRENCY,
    DEFAULT_LANGUAGE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_VIDEO_LANGUAGES,
    RequestPolicy,
    normalize_video_languages,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAN = REPO_ROOT / "analytics/processed/tmdb/content_refresh_plan.json"
DEFAULT_REPORT = REPO_ROOT / "analytics/processed/tmdb/run_reports/content_refresh_run_report.json"
DEFAULT_PREVIEW_DIR = REPO_ROOT / "analytics/processed/tmdb/content_refresh_previews"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be a non-negative integer")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scoped InsightStream content refresh work.")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--plan-only", action="store_true")
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--apply", action="store_true")
    parser.add_argument("--scope", choices=tuple(sorted(VALID_SCOPES)), default=ALL_SCOPE)
    parser.add_argument("--plan", help="Read an existing generated refresh plan instead of querying PostgreSQL.")
    parser.add_argument("--source-id")
    parser.add_argument("--content-id", type=positive_int)
    parser.add_argument("--content-type", choices=("movie", "series"))
    parser.add_argument("--priority", choices=("high", "normal", "low"))
    parser.add_argument("--limit", type=positive_int)
    parser.add_argument("--include-not-due", action="store_true")
    parser.add_argument("--batch-size", type=positive_int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--concurrency", type=positive_int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--request-timeout", type=positive_float, default=DEFAULT_REQUEST_TIMEOUT)
    parser.add_argument("--max-retries", type=non_negative_int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--language", default=os.getenv("TMDB_LANGUAGE", DEFAULT_LANGUAGE))
    parser.add_argument("--video-languages", default=os.getenv("TMDB_VIDEO_LANGUAGES", DEFAULT_VIDEO_LANGUAGES))
    parser.add_argument("--database-url")
    parser.add_argument("--output", default=str(DEFAULT_PLAN.relative_to(REPO_ROOT)))
    parser.add_argument("--report", default=str(DEFAULT_REPORT.relative_to(REPO_ROOT)))
    return parser.parse_args(argv)


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def _planner_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        source_id=args.source_id,
        content_id=args.content_id,
        content_type=args.content_type,
        scope=args.scope,
        priority=args.priority,
        limit=args.limit,
        page_size=max(args.batch_size, 25),
        include_not_due=args.include_not_due,
    )


def load_or_build_plan(args: argparse.Namespace, database_url: str, now: datetime) -> dict[str, Any]:
    if args.plan:
        payload = json.loads(resolve_path(args.plan).read_text())
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("refresh plan must be an object containing an items list")
        return payload
    return build_payload(_planner_args(args), database_url, now)


def validate_plan_items(items: list[dict[str, Any]], requested_scope: str) -> None:
    for item in items:
        scopes = set(item.get("refresh_scopes") or [])
        if not scopes or not scopes.issubset({SERIES_SCOPE, VIDEO_SCOPE}):
            raise ValueError(f"invalid refresh scopes for content_id={item.get('content_id')}")
        if item.get("content_type") == "movie" and SERIES_SCOPE in scopes:
            raise ValueError("movies cannot receive the series_metadata refresh scope")
        if requested_scope != ALL_SCOPE and scopes - {requested_scope}:
            raise ValueError("plan contains work outside the requested scope")


def filter_plan_items(payload: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for source_item in payload.get("items", []):
        item = dict(source_item)
        if args.source_id and str(item.get("tmdb_id")) != str(args.source_id):
            continue
        if args.content_id and int(item.get("content_id", -1)) != args.content_id:
            continue
        if args.content_type and item.get("content_type") != args.content_type:
            continue
        if args.priority and item.get("priority") != args.priority:
            continue
        scopes = list(item.get("refresh_scopes") or [])
        if args.scope != ALL_SCOPE:
            scopes = [scope for scope in scopes if scope == args.scope]
        if item.get("content_type") == "movie":
            scopes = [scope for scope in scopes if scope == VIDEO_SCOPE]
        if not scopes:
            continue
        item["refresh_scopes"] = scopes
        item["reasons"] = {
            scope: (item.get("reasons") or {}).get(scope, "planned")
            for scope in scopes
        }
        filtered.append(item)
        if args.limit and len(filtered) >= args.limit:
            break
    return filtered


def group_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter()
    for item in items:
        scopes = set(item["refresh_scopes"])
        if item["content_type"] == "movie":
            counts["videos_only_movies"] += 1
        elif scopes == {SERIES_SCOPE, VIDEO_SCOPE}:
            counts["combined_series_scopes"] += 1
        elif scopes == {SERIES_SCOPE}:
            counts["series_metadata_only"] += 1
        else:
            counts["videos_only_series"] += 1
    return {
        key: counts[key]
        for key in (
            "series_metadata_only",
            "videos_only_movies",
            "videos_only_series",
            "combined_series_scopes",
        )
    }


def summarize_domains(items: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for scope in (SERIES_SCOPE, VIDEO_SCOPE):
        counts = Counter(
            item["domains"][scope]["status"]
            for item in items
            if scope in item.get("domains", {})
        )
        output[scope] = {
            "attempted": sum(counts.values()),
            "success": counts["success"],
            "failed": counts["failed"],
            "empty": counts["empty"],
            "incomplete": counts["incomplete"],
            "skipped": counts["skipped"],
            "no_change": counts["no_change"],
        }
    return output


def has_operational_failures(items: list[dict[str, Any]]) -> bool:
    """Failed/incomplete domains fail the run; valid empty snapshots do not."""
    return any(
        domain.get("status") in {"failed", "incomplete"}
        for item in items
        for domain in item.get("domains", {}).values()
    )


def split_follow_up_targets(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate bounded automatic retries from manual-review outcomes."""
    retry_targets: list[dict[str, Any]] = []
    review_targets: list[dict[str, Any]] = []
    for item in items:
        failed_domains = [
            domain
            for domain in item.get("domains", {}).values()
            if domain.get("status") in {"failed", "incomplete"}
        ]
        if any(
            domain.get("automatic_retry", domain.get("retryable")) is True
            for domain in failed_domains
        ):
            retry_targets.append(item)
        if any(
            domain.get("automatic_retry", domain.get("retryable")) is not True
            for domain in failed_domains
        ):
            review_targets.append(item)
    return retry_targets, review_targets


def execute_items(
    items: list[dict[str, Any]],
    args: argparse.Namespace,
    database_url: str,
) -> list[dict[str, Any]]:
    token = os.getenv("TMDB_READ_ACCESS_TOKEN")
    languages = normalize_video_languages(args.video_languages)
    policy = RequestPolicy(
        timeout_seconds=args.request_timeout,
        max_retries=args.max_retries,
    )
    results: list[dict[str, Any]] = []
    workers = min(args.concurrency, args.batch_size)

    for start in range(0, len(items), args.batch_size):
        batch = items[start : start + args.batch_size]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    execute_plan_item,
                    item,
                    database_url=database_url,
                    token=token,
                    apply=args.apply,
                    refresh=args.refresh,
                    language=args.language,
                    video_languages=languages,
                    request_policy=policy,
                    preview_dir=DEFAULT_PREVIEW_DIR,
                ): index
                for index, item in enumerate(batch)
            }
            ordered: list[dict[str, Any] | None] = [None] * len(batch)
            for future in as_completed(futures):
                index = futures[future]
                try:
                    ordered[index] = future.result()
                except Exception as exc:  # one target never terminates the batch
                    item = batch[index]
                    ordered[index] = {
                        "content_id": item["content_id"],
                        "title": item["title"],
                        "tmdb_id": item["tmdb_id"],
                        "content_type": item["content_type"],
                        "requested_scopes": item["refresh_scopes"],
                        "reasons": item["reasons"],
                        "network_fetch": "failed",
                        "domains": {
                            scope: {"status": "failed", "error": str(exc)}
                            for scope in item["refresh_scopes"]
                        },
                    }
            results.extend(result for result in ordered if result is not None)
    return results


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if load_dotenv is not None:
        load_dotenv(REPO_ROOT / ".env")
        load_dotenv(REPO_ROOT / "backend/.env")
    database_url = load_database_url(args.database_url)
    if not database_url:
        print("DATABASE_URL is required.")
        return 1

    now = datetime.now(timezone.utc)
    try:
        plan = load_or_build_plan(args, database_url, now)
        items = filter_plan_items(plan, args)
        plan["items"] = items
        plan["plan_items"] = len(items)
        plan["estimated_tmdb_requests"] = len(items)
        validate_plan_items(items, args.scope)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Could not prepare refresh plan: {exc}")
        return 1

    if (args.content_id is not None or args.source_id is not None) and not items:
        print(
            "The explicit target was not found, lacks a canonical TMDb identity, "
            "or is incompatible with the requested scope."
        )
        return 1

    output_path = resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan, indent=2) + "\n")
    print(f"Plan items: {len(items)}")
    print(f"Estimated TMDb requests: {len(items)}")

    if args.plan_only:
        print(f"Plan written to {output_path}")
        print("Plan-only mode made no TMDb requests and no database writes.")
        return 0

    results = execute_items(items, args, database_url)
    retry_targets, review_targets = split_follow_up_targets(results)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry_run",
        "scope": args.scope,
        "plan_items": len(items),
        "estimated_tmdb_requests": len(items),
        "groups": group_counts(items),
        "scope_results": summarize_domains(results),
        "retry_targets": retry_targets,
        "review_targets": review_targets,
        "items": results,
    }
    report_path = resolve_path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(f"Run report: {report_path}")
    if args.dry_run:
        print("Dry-run mode made no database writes.")
    return 1 if has_operational_failures(results) else 0


if __name__ == "__main__":
    sys.exit(main())
