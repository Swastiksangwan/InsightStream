#!/usr/bin/env python3
"""Capture the current catalog Decision Insight output in a read-only report."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from analytics.scripts.common.paths import REPO_ROOT, ensure_backend_import_path

ensure_backend_import_path()

from app.services.content_service import get_content_details_service  # noqa: E402
from app.services.source_signal_service import (  # noqa: E402
    fetch_active_source_signals,
    fetch_watch_guidance,
)
from analytics.scripts.audits.audit_decision_display_quality import (  # noqa: E402
    audit_content_detail,
    primary_template_family,
)
from analytics.scripts.audits.decision_insight_report_metadata import (  # noqa: E402
    decision_insight_versions,
)


DEFAULT_OUTPUT = (
    REPO_ROOT
    / "analytics/processed/source_signals/decision_insight_formatter_v2"
    / "baseline_catalog.json"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Capture one deterministic Decision Insight record per catalog "
            "title. PostgreSQL is opened in a read-only transaction."
        )
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT.relative_to(REPO_ROOT)),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Positive number of catalog IDs fetched at a time. Defaults to 100.",
    )
    args = parser.parse_args(argv)
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")
    return args


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def length_bucket(sentence: str | None) -> str:
    length = len(sentence or "")
    if length < 40:
        return "under_40"
    if length < 80:
        return "40_79"
    if length < 120:
        return "80_119"
    return "120_plus"


def grouped_signals(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["dimension"], []).append(
            {
                "value": row["value"],
                "label": row["label"],
                "confidence": row["confidence"],
            }
        )
    return grouped


def build_record(content_id: int, connection) -> dict[str, Any]:
    detail = get_content_details_service(content_id, connection)
    guidance = fetch_watch_guidance(connection, content_id) or {}
    signals = fetch_active_source_signals(connection, content_id)
    audit = audit_content_detail(detail)
    display = (detail.get("decision_layer") or {}).get("display") or {}
    profile = display.get("profile") or {}
    insight = display.get("primary_insight")
    return {
        "content_id": content_id,
        "title": detail["content"]["title"],
        "overview": detail["content"].get("overview"),
        "genres": detail.get("genres") or [],
        "current_primary_insight": insight,
        "compact_identity": profile.get("identity") or [],
        "compact_themes": profile.get("themes") or [],
        "compact_feel": profile.get("feel") or [],
        "compact_pace": profile.get("pace"),
        "source_signals": grouped_signals(signals),
        "fallback_dependencies": {
            "metadata_fallback_applied": bool(
                guidance.get("metadata_fallback_applied")
            ),
            "signal_sources": guidance.get("signal_sources") or [],
        },
        "title_override_involved": bool(
            guidance.get("curated_override_applied")
        ),
        "selected_sentence_template": primary_template_family(
            insight or "",
            display,
        ),
        "quality_score": audit["display_quality_score"],
        "quality_issue_codes": [
            item["code"] for item in audit.get("issues") or []
        ],
    }


def build_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    templates = Counter(
        record["selected_sentence_template"] for record in records
    )
    lengths = Counter(
        length_bucket(record["current_primary_insight"]) for record in records
    )
    generic_codes = {
        "GENERIC_DOMINANT_IDENTITY",
        "EMPTY_THEMES_WITH_GENERIC_PRIMARY",
        "PRIMARY_INSIGHT_GENERIC",
        "PRIMARY_INSIGHT_LOW_SPECIFICITY",
    }
    duplicate_codes = {
        "IDENTITY_REPEATED_AS_THEME",
        "PRIMARY_INSIGHT_DUPLICATE_CONCEPTS",
        "PRIMARY_INSIGHT_REPETITIVE",
    }
    grammar_codes = {
        "BAD_BUILT_AROUND_TARGET",
        "PRIMARY_INSIGHT_PUNCTUATION",
        "PRIMARY_INSIGHT_RAW_LABEL_GRAMMAR",
    }
    return {
        "report_version": "decision-insight-baseline-v2",
        "versions": decision_insight_versions(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_write_performed": False,
        "catalog_metrics": {
            "total_titles": len(records),
            "empty_insights": sum(
                not record["current_primary_insight"] for record in records
            ),
            "generic_only_insights": sum(
                bool(generic_codes & set(record["quality_issue_codes"]))
                for record in records
            ),
            "duplicate_concept_insights": sum(
                bool(duplicate_codes & set(record["quality_issue_codes"]))
                for record in records
            ),
            "grammatical_problems": sum(
                bool(grammar_codes & set(record["quality_issue_codes"]))
                or ", and " in (record["current_primary_insight"] or "")
                for record in records
            ),
            "fallback_only_insights": sum(
                "PRIMARY_INSIGHT_FALLBACK_ONLY"
                in record["quality_issue_codes"]
                for record in records
            ),
            "repeated_word_problems": sum(
                bool(
                    re.search(
                        r"\b([a-z][a-z-]+)\b(?:\W+\w+){0,5}\W+\1\b",
                        (record["current_primary_insight"] or "").lower(),
                    )
                )
                for record in records
            ),
            "sentence_length_distribution": dict(sorted(lengths.items())),
            "template_distribution": dict(sorted(templates.items())),
            "titles_requiring_review": sum(
                bool(record["quality_issue_codes"]) for record in records
            ),
        },
        "records": records,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("Missing DATABASE_URL.")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        result = connection.execute(text("SELECT id FROM content ORDER BY id"))
        records = []
        while True:
            rows = result.fetchmany(args.batch_size)
            if not rows:
                break
            records.extend(
                build_record(int(row[0]), connection) for row in rows
            )
        connection.rollback()

    payload = build_payload(records)
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload["catalog_metrics"], indent=2, sort_keys=True))
    print("DB writes: none")
    print(f"Output: {output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
