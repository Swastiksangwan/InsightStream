#!/usr/bin/env python3
"""Explain one runtime Decision Insight plan using read-only local data."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from analytics.scripts.common.paths import REPO_ROOT, ensure_backend_import_path

ensure_backend_import_path()

from app.services.content_service import get_content_details_service  # noqa: E402
from app.services.source_signal_service import (  # noqa: E402
    fetch_active_source_signals,
    runtime_signal_rows,
)
from analytics.scripts.audits.audit_decision_display_quality import (  # noqa: E402
    audit_content_detail,
)
from analytics.scripts.audits.decision_insight_report_metadata import (  # noqa: E402
    decision_insight_versions,
)


DATABASE_URL_ENV = "DATABASE_URL"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Explain one Decision Insight Formatter v2 result. PostgreSQL is "
            "opened in a read-only transaction."
        )
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--title", help="Exact case-insensitive catalog title.")
    target.add_argument("--content-id", type=int, help="Positive local content ID.")
    parser.add_argument(
        "--json-output",
        help="Optional JSON output path. Use analytics/processed for ignored output.",
    )
    args = parser.parse_args(argv)
    if args.content_id is not None and args.content_id <= 0:
        parser.error("--content-id must be positive")
    return args


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def json_default(value: Any) -> str:
    if isinstance(value, (date, datetime, Decimal)):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def grouped_signals(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("dimension") or "unknown")].append(dict(row))
    return {key: grouped[key] for key in sorted(grouped)}


def identity_candidates(plan: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = []
    selected = plan.get("primary_identity")
    if isinstance(selected, dict):
        candidates.append(
            {
                "candidate": selected.get("text"),
                "source": selected.get("source"),
                "trust_tier": selected.get("trust_tier"),
                "confidence": selected.get("confidence"),
                "compatibility": "accepted",
                "centrality_or_corroboration": selected.get("evidence"),
                "corroboration_sources": selected.get("corroboration_sources") or [],
                "corroboration_count": selected.get("corroboration_count") or 0,
                "centrality_class": selected.get("centrality_class"),
                "explicit_premise_evidence": bool(
                    selected.get("explicit_premise_evidence")
                ),
                "incidental_context": bool(selected.get("incidental_context")),
                "ranking_rationale": selected.get("selection_rationale"),
                "selection_result": "selected",
                "rejection_reason": None,
            }
        )
    for item in plan.get("rejected_candidates") or []:
        if item.get("role") != "primary_identity":
            continue
        conflict = item.get("reason") == "identity_metadata_conflict"
        candidates.append(
            {
                "candidate": item.get("candidate"),
                "source": item.get("source"),
                "trust_tier": item.get("trust_tier"),
                "confidence": item.get("confidence"),
                "compatibility": "rejected" if conflict else "accepted",
                "centrality_or_corroboration": item.get("evidence"),
                "corroboration_sources": item.get("corroboration_sources") or [],
                "corroboration_count": item.get("corroboration_count") or 0,
                "centrality_class": item.get("centrality_class"),
                "explicit_premise_evidence": bool(
                    item.get("explicit_premise_evidence")
                ),
                "incidental_context": bool(item.get("incidental_context")),
                "ranking_rationale": item.get("ranking_rationale"),
                "selection_result": "rejected",
                "rejection_reason": item.get("conflict_reason")
                if conflict
                else item.get("reason"),
            }
        )
    return candidates


def build_explanation(
    detail: dict[str, Any],
    active_signal_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    decision_layer = detail.get("decision_layer") or {}
    debug = decision_layer.get("debug") or {}
    plan = debug.get("insight_plan") or {}
    display = decision_layer.get("display") or {}
    profile = display.get("profile") or {}
    audit = audit_content_detail(detail)
    rejected = plan.get("rejected_candidates") or []
    source_conflicts = [
        item
        for item in rejected
        if item.get("reason") == "identity_metadata_conflict"
        and str(item.get("source") or "").startswith("source_signal:")
    ]
    selected_differentiators = [
        plan.get("primary_differentiator"),
        plan.get("secondary_differentiator"),
    ]
    return {
        "report_version": "decision-insight-explanation-v1",
        "db_write_performed": False,
        "versions": decision_insight_versions(),
        "content": detail.get("content") or {},
        "genres": detail.get("genres") or [],
        "overview": (detail.get("content") or {}).get("overview"),
        "active_signals_by_dimension": grouped_signals(active_signal_rows),
        "identity_candidates": identity_candidates(plan),
        "selected_modifier": plan.get("tone_modifier") or plan.get("mood_modifier"),
        "selected_differentiators": [
            item for item in selected_differentiators if isinstance(item, dict)
        ],
        "rejected_differentiators": [
            item
            for item in rejected
            if item.get("role") in {"about_phrase", "pacing_phrase"}
        ],
        "insight_plan": plan,
        "template_family": plan.get("template_family"),
        "final_primary_insight": display.get("primary_insight"),
        "public_fields": {
            "identity": profile.get("identity") or [],
            "themes": profile.get("themes") or [],
            "feel": profile.get("feel") or [],
            "pace": profile.get("pace"),
            "best_for": profile.get("best_for") or [],
            "decision_support_headline": (
                decision_layer.get("decision_support") or {}
            ).get("headline"),
            "compatibility_watch_feel": (
                decision_layer.get("watch_profile") or {}
            ).get("watch_feel"),
        },
        "source_signal_conflicts": source_conflicts,
        "display_ready": audit["display_ready"],
        "source_signal_review_required": audit[
            "source_signal_review_required"
        ],
        "display_issue_codes": [
            item["code"] for item in audit.get("display_issues") or []
        ],
        "source_signal_review_issue_codes": [
            item["code"]
            for item in audit.get("source_signal_review_issues") or []
        ],
    }


def resolve_content_id(connection, args: argparse.Namespace) -> int:
    if args.content_id is not None:
        return args.content_id
    rows = connection.execute(
        text(
            """
            SELECT id
            FROM content
            WHERE LOWER(title) = LOWER(:title)
            ORDER BY id
            """
        ),
        {"title": args.title},
    ).fetchall()
    if not rows:
        raise ValueError(f"No content title matched {args.title!r}.")
    if len(rows) > 1:
        ids = ", ".join(str(row[0]) for row in rows)
        raise ValueError(
            f"Title {args.title!r} is ambiguous; use --content-id ({ids})."
        )
    return int(rows[0][0])


def print_explanation(payload: dict[str, Any]) -> None:
    content = payload["content"]
    print(f"Title: {content.get('title')} (content_id={content.get('id')})")
    print(f"Formatter version: {payload['versions']['formatter_version']}")
    print(f"Genres: {', '.join(payload['genres']) or 'none'}")
    print("Identity candidates:")
    for candidate in payload["identity_candidates"]:
        print(
            "- "
            f"{candidate.get('candidate')} | tier={candidate.get('trust_tier')} | "
            f"source={candidate.get('source')} | "
            f"compatibility={candidate.get('compatibility')} | "
            f"centrality={candidate.get('centrality_class')} | "
            f"corroboration={candidate.get('corroboration_sources')} | "
            f"result={candidate.get('selection_result')} | "
            f"reason={candidate.get('rejection_reason') or 'selected/compatible'}"
        )
    print(f"Template: {payload.get('template_family')}")
    print(f"Primary insight: {payload.get('final_primary_insight')}")
    print(f"Display ready: {str(payload['display_ready']).lower()}")
    print(
        "Source-signal review required: "
        f"{str(payload['source_signal_review_required']).lower()}"
    )
    print("DB writes: none")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    database_url = os.getenv(DATABASE_URL_ENV)
    if not database_url:
        raise SystemExit(f"Missing {DATABASE_URL_ENV}.")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        try:
            content_id = resolve_content_id(connection, args)
            detail = get_content_details_service(
                content_id,
                connection,
                include_decision_debug=True,
            )
            if not detail:
                raise ValueError(f"No content found for content_id={content_id}.")
            active_rows = runtime_signal_rows(
                fetch_active_source_signals(connection, content_id)
            )
            payload = build_explanation(detail, active_rows)
        finally:
            connection.rollback()
    print_explanation(payload)
    if args.json_output:
        output = resolve_path(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                default=json_default,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"JSON output: {output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
