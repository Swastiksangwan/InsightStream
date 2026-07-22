#!/usr/bin/env python3
"""Build an ignored, database-driven shared content refresh plan."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

from analytics.scripts.refresh.content_refresh_planner import (
    ALL_SCOPE,
    DEFAULT_PAGE_SIZE,
    VALID_SCOPES,
    build_refresh_plan,
    estimate_request_count,
    iter_content_rows,
)


from analytics.scripts.common.paths import REPO_ROOT
DEFAULT_OUTPUT = REPO_ROOT / "analytics/processed/tmdb/content_refresh_plan.json"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan due InsightStream content refresh work.")
    parser.add_argument("--source-id")
    parser.add_argument("--content-id", type=positive_int)
    parser.add_argument("--content-type", choices=("movie", "series"))
    parser.add_argument("--scope", choices=tuple(sorted(VALID_SCOPES)), default=ALL_SCOPE)
    parser.add_argument("--priority", choices=("high", "normal", "low"))
    parser.add_argument("--limit", type=positive_int)
    parser.add_argument("--page-size", type=positive_int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--include-not-due", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT.relative_to(REPO_ROOT)))
    parser.add_argument("--database-url")
    return parser.parse_args(argv)


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def load_database_url(explicit: str | None) -> str | None:
    if load_dotenv is not None:
        load_dotenv(REPO_ROOT / ".env")
        load_dotenv(REPO_ROOT / "backend/.env")
    return explicit or os.getenv("DATABASE_URL")


def build_payload(args: argparse.Namespace, database_url: str, now: datetime) -> dict[str, Any]:
    rows = iter_content_rows(
        database_url,
        content_id=args.content_id,
        source_id=args.source_id,
        content_type=args.content_type,
        page_size=args.page_size,
    )
    explicit = args.content_id is not None or args.source_id is not None
    items = build_refresh_plan(
        rows,
        now,
        scope=args.scope,
        explicit_target=explicit,
        include_not_due=args.include_not_due,
        priority=args.priority,
        limit=args.limit,
    )
    return {
        "generated_at": now.isoformat(),
        "generated_by": "analytics/scripts/refresh/build_content_refresh_plan.py",
        "scope": args.scope,
        "filters": {
            "source_id": args.source_id,
            "content_id": args.content_id,
            "content_type": args.content_type,
            "priority": args.priority,
            "limit": args.limit,
            "include_not_due": args.include_not_due,
        },
        "plan_items": len(items),
        "estimated_tmdb_requests": estimate_request_count(items),
        "items": items,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    database_url = load_database_url(args.database_url)
    if not database_url:
        print("DATABASE_URL is required to build the refresh plan.")
        return 1
    payload = build_payload(args, database_url, datetime.now(timezone.utc))
    if (args.content_id is not None or args.source_id is not None) and not payload["items"]:
        print(
            "The explicit target was not found, lacks a canonical TMDb identity, "
            "or is incompatible with the requested scope."
        )
        return 1
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"Refresh plan: {output}")
    print(f"Plan items: {payload['plan_items']}")
    print(f"Estimated TMDb requests: {payload['estimated_tmdb_requests']}")
    print("No TMDb requests or database writes were made.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
