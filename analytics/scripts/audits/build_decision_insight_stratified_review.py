#!/usr/bin/env python3
"""Build a deterministic, ignored QA sample for Decision Insight Formatter v2."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analytics.scripts.common.paths import REPO_ROOT


DEFAULT_COMPARISON = (
    REPO_ROOT
    / "analytics/processed/source_signals/decision_insight_formatter_v2"
    / "proposed_comparison_catalog.json"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "analytics/processed/source_signals/decision_insight_formatter_v2"
    / "stratified_catalog_review.json"
)

GENRE_STRATA = {
    "drama_comedy_romance": {"drama", "comedy", "romance"},
    "horror_crime_thriller": {"horror", "crime", "thriller"},
    "documentary_music": {"documentary", "music"},
    "war_history": {"war", "war & politics", "history"},
    "animation_fantasy": {"animation", "fantasy"},
}
INDIAN_LANGUAGES = {"bn", "gu", "hi", "kn", "ml", "mr", "pa", "ta", "te", "ur"}
EUROPEAN_LANGUAGES = {
    "da",
    "de",
    "es",
    "fi",
    "fr",
    "it",
    "nl",
    "no",
    "pl",
    "pt",
    "ro",
    "ru",
    "sv",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a deterministic stratified formatter QA report."
    )
    parser.add_argument(
        "--comparison",
        default=str(DEFAULT_COMPARISON.relative_to(REPO_ROOT)),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT.relative_to(REPO_ROOT)),
    )
    parser.add_argument("--minimum", type=int, default=40)
    args = parser.parse_args(argv)
    if args.minimum <= 0:
        parser.error("--minimum must be positive")
    return args


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def selected_components(record: dict[str, Any]) -> list[dict[str, Any]]:
    plan = record.get("insight_plan") or {}
    return [
        component
        for key in (
            "primary_identity",
            "tone_modifier",
            "mood_modifier",
            "primary_differentiator",
            "secondary_differentiator",
            "pacing_modifier",
            "audience_modifier",
        )
        if isinstance((component := plan.get(key)), dict)
    ]


def uses_overview(record: dict[str, Any]) -> bool:
    return any(
        component.get("source") == "overview_rule"
        for component in selected_components(record)
    )


def add_first_matching(
    records: list[dict[str, Any]],
    selected: dict[int, set[str]],
    stratum: str,
    predicate,
) -> None:
    for record in records:
        if predicate(record):
            selected.setdefault(int(record["content_id"]), set()).add(stratum)
            return


def stratify_records(
    records: list[dict[str, Any]],
    minimum: int = 40,
) -> list[dict[str, Any]]:
    ordered = sorted(
        records,
        key=lambda row: (int(row.get("content_id") or 0), row.get("title") or ""),
    )
    selected: dict[int, set[str]] = {}

    for record in ordered:
        if record.get("manual_review"):
            selected.setdefault(int(record["content_id"]), set()).add("manual_review")
        if uses_overview(record):
            selected.setdefault(int(record["content_id"]), set()).add(
                "overview_context"
            )

    for content_type in ("movie", "series"):
        add_first_matching(
            ordered,
            selected,
            f"content_type:{content_type}",
            lambda row, value=content_type: row.get("content_type") == value,
        )

    templates = sorted(
        {
            record.get("after_template_family")
            for record in ordered
            if record.get("after_template_family")
        }
    )
    for template in templates:
        add_first_matching(
            ordered,
            selected,
            f"template:{template}",
            lambda row, value=template: row.get("after_template_family") == value,
        )

    for name, genres in GENRE_STRATA.items():
        add_first_matching(
            ordered,
            selected,
            f"genre:{name}",
            lambda row, values=genres: bool(
                {str(value).casefold() for value in row.get("genres") or []}
                & values
            ),
        )

    for name, predicate in (
        (
            "region:indian_language",
            lambda row: (row.get("original_language") or "").casefold()
            in INDIAN_LANGUAGES,
        ),
        (
            "region:korean",
            lambda row: (row.get("original_language") or "").casefold() == "ko",
        ),
        (
            "region:european_language",
            lambda row: (row.get("original_language") or "").casefold()
            in EUROPEAN_LANGUAGES,
        ),
        ("signal_density:sparse", lambda row: int(row.get("signal_count") or 0) <= 3),
        ("signal_density:rich", lambda row: int(row.get("signal_count") or 0) >= 10),
        ("context:no_overview_rule", lambda row: not uses_overview(row)),
    ):
        add_first_matching(ordered, selected, name, predicate)

    for record in ordered:
        if len(selected) >= min(minimum, len(ordered)):
            break
        selected.setdefault(int(record["content_id"]), set()).add(
            "deterministic_fill"
        )

    return [
        {
            **record,
            "strata": sorted(selected[int(record["content_id"])]),
            "automated_status": (
                "display_and_source_signal_review"
                if record.get("display_review_required")
                and record.get("source_signal_review_required")
                else "display_review"
                if record.get("display_review_required")
                else "source_signal_review"
                if record.get("source_signal_review_required")
                else "passing_with_nonblocking_findings"
                if record.get("after_issue_codes")
                else "passing"
            ),
            "human_review_status": "unreviewed",
            "human_review_notes": None,
        }
        for record in ordered
        if int(record["content_id"]) in selected
    ]


def overview_provenance(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for record in sorted(
        records,
        key=lambda row: (int(row["content_id"]), row.get("title") or ""),
    ):
        for component in selected_components(record):
            if component.get("source") != "overview_rule":
                continue
            evidence_parts = {}
            for part in str(component.get("evidence") or "").split(";"):
                key, separator, value = part.partition("=")
                if separator:
                    evidence_parts[key] = value
            output.append(
                {
                    "content_id": record["content_id"],
                    "title": record.get("title"),
                    "phrase": component.get("text"),
                    "governing_rule": evidence_parts.get("rule"),
                    "matched_local_evidence": evidence_parts.get("matched"),
                    "evidence_scope": evidence_parts.get("scope"),
                    "overview": record.get("overview"),
                }
            )
    return output


def build_payload(comparison: dict[str, Any], minimum: int) -> dict[str, Any]:
    records = comparison.get("records") or []
    sample = stratify_records(records, minimum=minimum)
    return {
        "report_version": "decision-insight-stratified-review-v1",
        "versions": comparison.get("versions") or {},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_write_performed": False,
        "catalog_size": len(records),
        "sample_size": len(sample),
        "display_ready_count": sum(
            bool(record.get("display_ready")) for record in records
        ),
        "source_signal_review_required_count": sum(
            bool(record.get("source_signal_review_required"))
            for record in records
        ),
        "minimum_requested": minimum,
        "template_distribution": dict(
            sorted(
                Counter(
                    row.get("after_template_family") or "unknown"
                    for row in sample
                ).items()
            )
        ),
        "overview_context_provenance": overview_provenance(records),
        "records": sample,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    comparison_path = resolve_path(args.comparison)
    output_path = resolve_path(args.output)
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    payload = build_payload(comparison, args.minimum)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "catalog_size": payload["catalog_size"],
                "sample_size": payload["sample_size"],
                "overview_context_count": len(
                    payload["overview_context_provenance"]
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    print("DB writes: none")
    print(f"Output: {output_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
