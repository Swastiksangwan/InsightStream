#!/usr/bin/env python3
"""Compare stored Decision Insight output with the current formatter, read-only."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from analytics.scripts.common.paths import REPO_ROOT, ensure_backend_import_path

ensure_backend_import_path()

from app.services.content_service import get_content_details_service  # noqa: E402
from analytics.scripts.audits.audit_decision_display_quality import (  # noqa: E402
    apply_template_overuse_issues,
    audit_content_detail,
    audit_display_record,
    primary_template_family,
)
from analytics.scripts.audits.decision_insight_report_metadata import (  # noqa: E402
    decision_insight_versions,
)


DATABASE_URL_ENV = "DATABASE_URL"
DEFAULT_BASELINE = (
    REPO_ROOT
    / "analytics/processed/source_signals/decision_insight_formatter_v2"
    / "baseline_catalog.json"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "analytics/processed/source_signals/decision_insight_formatter_v2"
    / "proposed_comparison_catalog.json"
)
DEFAULT_CONFLICT_OUTPUT = (
    REPO_ROOT
    / "analytics/processed/source_signals/decision_insight_formatter_v2"
    / "source_signal_identity_conflicts.json"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare a captured decision-insight baseline with the current "
            "global formatter. Reads PostgreSQL in a read-only transaction."
        )
    )
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE.relative_to(REPO_ROOT)),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT.relative_to(REPO_ROOT)),
    )
    parser.add_argument(
        "--conflict-output",
        default=str(DEFAULT_CONFLICT_OUTPUT.relative_to(REPO_ROOT)),
        help="Ignored report of source-signal identities rejected by metadata checks.",
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


def load_baseline(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("Baseline report records must be a list.")
    return payload


def before_display(record: dict[str, Any], supporting_facts: list[dict[str, Any]]):
    return {
        "primary_insight": record.get("current_primary_insight"),
        "profile": {
            "identity": record.get("compact_identity") or [],
            "themes": record.get("compact_themes") or [],
            "feel": record.get("compact_feel") or [],
            "pace": record.get("compact_pace"),
            "best_for": [],
            "consider_first": [],
        },
        "supporting_facts": supporting_facts,
    }


def issue_codes(record: dict[str, Any]) -> list[str]:
    return [item["code"] for item in record.get("issues") or []]


def selected_plan_components(plan: dict[str, Any]) -> list[dict[str, Any]]:
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


def issue_frequency(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counter = Counter()
    for record in records:
        counter.update(record.get(field) or [])
    return dict(sorted(counter.items()))


def template_distribution(records: list[dict[str, Any]], field: str):
    return dict(sorted(Counter(record[field] for record in records).items()))


def percentage(count: int, total: int) -> float:
    return round((count / total) * 100, 1) if total else 0.0


def rating_modifier_distribution(records: list[dict[str, Any]]) -> dict[str, int]:
    return dict(
        sorted(
            Counter(
                ((record.get("insight_plan") or {}).get("audience_modifier") or {}).get(
                    "text"
                )
                for record in records
                if ((record.get("insight_plan") or {}).get("audience_modifier") or {}).get(
                    "text"
                )
            ).items()
        )
    )


def build_identity_conflict_report(comparison: dict[str, Any]) -> dict[str, Any]:
    conflicts = []
    for record in comparison.get("records") or []:
        for rejected in record.get("rejected_candidate_components") or []:
            if (
                rejected.get("reason") != "identity_metadata_conflict"
                or not str(rejected.get("source") or "").startswith("source_signal:")
            ):
                continue
            conflicts.append(
                {
                    "content_id": record.get("content_id"),
                    "title": record.get("title"),
                    "conflicting_source_signal": rejected.get("candidate"),
                    "confidence": rejected.get("confidence"),
                    "metadata_overview_conflict": rejected.get("conflict_reason"),
                    "evidence": rejected.get("evidence"),
                    "formatter_rejected": True,
                    "display_ready": bool(record.get("display_ready")),
                    "source_signal_review_required": True,
                    "recommended_future_action": "review_source_signal_mapping",
                }
            )
    conflicts.sort(
        key=lambda item: (
            int(item.get("content_id") or 0),
            str(item.get("conflicting_source_signal") or "").casefold(),
        )
    )
    return {
        "report_version": "source-signal-identity-conflicts-v1",
        "versions": comparison.get("versions") or decision_insight_versions(),
        "generated_at": comparison.get("generated_at"),
        "db_write_performed": False,
        "catalog_size": (comparison.get("catalog_metrics") or {}).get("total_titles", 0),
        "conflict_count": len(conflicts),
        "records": conflicts,
    }


def build_comparison(
    baseline: dict[str, Any],
    details: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    before_records = []
    after_records = []
    comparison_records = []
    baseline_by_id = {
        int(record["content_id"]): record for record in baseline["records"]
    }
    for content_id in sorted(details):
        baseline_record = baseline_by_id.get(content_id) or {
            "content_id": content_id,
            "current_primary_insight": None,
            "compact_identity": [],
            "compact_themes": [],
            "compact_feel": [],
            "compact_pace": None,
        }
        detail = details.get(content_id)
        if not detail:
            raise ValueError(f"Missing current detail for content_id={content_id}.")
        content = detail["content"]
        decision_layer = detail.get("decision_layer") or {}
        proposed_display = decision_layer.get("display") or {}
        plan = (decision_layer.get("debug") or {}).get("insight_plan") or {}
        proposed_for_audit = dict(proposed_display)
        proposed_for_audit["_insight_plan"] = plan

        current_display = before_display(
            baseline_record,
            proposed_display.get("supporting_facts") or [],
        )
        before_audit = audit_display_record(content, current_display)
        after_audit = audit_display_record(content, proposed_for_audit)
        before_records.append(before_audit)
        after_records.append(after_audit)

        current_sentence = baseline_record.get("current_primary_insight")
        proposed_sentence = proposed_display.get("primary_insight")
        after_codes = issue_codes(after_audit)
        components = selected_plan_components(plan)
        comparison_records.append(
            {
                "content_id": content_id,
                "title": content.get("title"),
                "content_type": content.get("type") or content.get("content_type"),
                "original_language": content.get("original_language"),
                "genres": detail.get("genres") or [],
                "overview": content.get("overview"),
                "signal_count": len((decision_layer.get("debug") or {}).get("signals") or []),
                "source_signals": (decision_layer.get("debug") or {}).get("signals") or [],
                "baseline_status": (
                    "captured" if content_id in baseline_by_id else "new_title"
                ),
                "current_sentence": current_sentence,
                "proposed_sentence": proposed_sentence,
                "insight_plan": plan,
                "component_evidence": [
                    {
                        "text": component.get("text"),
                        "role": component.get("role"),
                        "source": component.get("source"),
                        "evidence": component.get("evidence"),
                    }
                    for component in components
                ],
                "rejected_candidate_components": plan.get(
                    "rejected_candidates"
                )
                or [],
                "before_quality_score": before_audit["display_quality_score"],
                "after_quality_score": after_audit["display_quality_score"],
                "before_issue_codes": issue_codes(before_audit),
                "after_issue_codes": after_codes,
                "before_template_family": primary_template_family(
                    current_sentence or "",
                    current_display,
                ),
                "after_template_family": plan.get("template_family")
                or primary_template_family(
                    proposed_sentence or "",
                    proposed_for_audit,
                ),
                "semantic_change": current_sentence != proposed_sentence,
                "display_ready": after_audit["display_ready"],
                "display_review_required": after_audit[
                    "display_review_required"
                ],
                "source_signal_review_required": after_audit[
                    "source_signal_review_required"
                ],
                "manual_review": after_audit["review_required"],
            }
        )

    before_records = apply_template_overuse_issues(before_records)
    after_records = apply_template_overuse_issues(after_records)
    before_by_id = {record["content_id"]: record for record in before_records}
    after_by_id = {record["content_id"]: record for record in after_records}
    for record in comparison_records:
        before = before_by_id[record["content_id"]]
        after = after_by_id[record["content_id"]]
        record["before_quality_score"] = before["display_quality_score"]
        record["after_quality_score"] = after["display_quality_score"]
        record["before_issue_codes"] = issue_codes(before)
        record["after_issue_codes"] = issue_codes(after)
        record["display_ready"] = after["display_ready"]
        record["display_review_required"] = after["display_review_required"]
        record["source_signal_review_required"] = after[
            "source_signal_review_required"
        ]
        record["manual_review"] = after["review_required"]

    total = len(comparison_records)
    changed = sum(record["semantic_change"] for record in comparison_records)
    context_count = sum(
        any(
            component.get("source") == "overview_rule"
            for component in selected_plan_components(record["insight_plan"])
        )
        for record in comparison_records
    )
    rejected_identity_conflicts = [
        candidate
        for record in comparison_records
        for candidate in record.get("rejected_candidate_components") or []
        if candidate.get("reason") == "identity_metadata_conflict"
    ]
    manual = [
        {
            "content_id": record["content_id"],
            "title": record["title"],
            "issue_codes": record["after_issue_codes"],
            "display_ready": record["display_ready"],
            "source_signal_review_required": record[
                "source_signal_review_required"
            ],
        }
        for record in comparison_records
        if record["manual_review"]
    ]
    return {
        "report_version": "decision-insight-comparison-v2",
        "versions": decision_insight_versions(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_write_performed": False,
        "catalog_metrics": {
            "total_titles": total,
            "sentences_changed": changed,
            "sentences_changed_percentage": percentage(changed, total),
            "safe_overview_context_titles": context_count,
            "safe_overview_context_percentage": percentage(context_count, total),
            "rating_modifier_usage": rating_modifier_distribution(comparison_records),
            "rating_modifier_plan_count": sum(
                bool((record.get("insight_plan") or {}).get("audience_modifier"))
                for record in comparison_records
            ),
            "rating_modifier_in_primary_count": sum(
                bool(
                    (modifier := (record.get("insight_plan") or {}).get("audience_modifier"))
                    and modifier.get("text")
                    and modifier["text"].casefold()
                    in (record.get("proposed_sentence") or "").casefold()
                )
                for record in comparison_records
            ),
            "spoiler_candidate_exclusions": sum(
                candidate.get("reason") == "spoiler_unsafe"
                for record in comparison_records
                for candidate in record.get("rejected_candidate_components") or []
            ),
            "manual_review_count": len(manual),
            "display_ready_count": sum(
                record["display_ready"] for record in comparison_records
            ),
            "display_review_required_count": sum(
                record["display_review_required"]
                for record in comparison_records
            ),
            "source_signal_review_required_count": sum(
                record["source_signal_review_required"]
                for record in comparison_records
            ),
            "identity_metadata_conflict_title_count": sum(
                "SOURCE_SIGNAL_IDENTITY_METADATA_CONFLICT"
                in record["after_issue_codes"]
                for record in comparison_records
            ),
            "rejected_incompatible_identity_count": len(
                rejected_identity_conflicts
            ),
            "adjective_stack_count": sum(
                "PRIMARY_INSIGHT_ADJECTIVE_STACK" in record["after_issue_codes"]
                for record in comparison_records
            ),
            "awkward_pacing_count": sum(
                "PRIMARY_INSIGHT_AWKWARD_PACING" in record["after_issue_codes"]
                for record in comparison_records
            ),
            "conjunction_chain_count": sum(
                "PRIMARY_INSIGHT_CONJUNCTION_CHAIN" in record["after_issue_codes"]
                for record in comparison_records
            ),
            "raw_taxonomy_count": sum(
                "PRIMARY_INSIGHT_RAW_TAXONOMY" in record["after_issue_codes"]
                for record in comparison_records
            ),
            "template_distribution_before": template_distribution(
                comparison_records,
                "before_template_family",
            ),
            "template_distribution_after": template_distribution(
                comparison_records,
                "after_template_family",
            ),
            "issue_frequency_before": issue_frequency(
                comparison_records,
                "before_issue_codes",
            ),
            "issue_frequency_after": issue_frequency(
                comparison_records,
                "after_issue_codes",
            ),
            "generic_identity_frequency_before": sum(
                "PRIMARY_INSIGHT_GENERIC" in record["before_issue_codes"]
                or "PRIMARY_INSIGHT_LOW_SPECIFICITY"
                in record["before_issue_codes"]
                for record in comparison_records
            ),
            "generic_identity_frequency_after": sum(
                "PRIMARY_INSIGHT_GENERIC" in record["after_issue_codes"]
                or "PRIMARY_INSIGHT_LOW_SPECIFICITY"
                in record["after_issue_codes"]
                for record in comparison_records
            ),
            "duplicate_concept_frequency_before": sum(
                "PRIMARY_INSIGHT_DUPLICATE_CONCEPTS"
                in record["before_issue_codes"]
                for record in comparison_records
            ),
            "duplicate_concept_frequency_after": sum(
                "PRIMARY_INSIGHT_DUPLICATE_CONCEPTS"
                in record["after_issue_codes"]
                for record in comparison_records
            ),
            "grammar_issue_frequency_before": sum(
                any(
                    code
                    in {
                        "PRIMARY_INSIGHT_PUNCTUATION",
                        "PRIMARY_INSIGHT_RAW_LABEL_GRAMMAR",
                        "PRIMARY_INSIGHT_REPEATED_WORD",
                    }
                    for code in record["before_issue_codes"]
                )
                for record in comparison_records
            ),
            "grammar_issue_frequency_after": sum(
                any(
                    code
                    in {
                        "PRIMARY_INSIGHT_PUNCTUATION",
                        "PRIMARY_INSIGHT_RAW_LABEL_GRAMMAR",
                        "PRIMARY_INSIGHT_REPEATED_WORD",
                    }
                    for code in record["after_issue_codes"]
                )
                for record in comparison_records
            ),
        },
        "manual_review_titles": manual,
        "baseline_content_ids_missing_from_catalog": sorted(
            set(baseline_by_id) - set(details)
        ),
        "records": comparison_records,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    database_url = os.getenv(DATABASE_URL_ENV)
    if not database_url:
        raise SystemExit(f"Missing {DATABASE_URL_ENV}.")

    baseline_path = resolve_path(args.baseline)
    output_path = resolve_path(args.output)
    conflict_output_path = resolve_path(args.conflict_output)
    baseline = load_baseline(baseline_path)
    engine = create_engine(database_url)
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        id_result = connection.execute(
            text("SELECT id FROM content ORDER BY id")
        )
        details = {}
        while True:
            rows = id_result.fetchmany(args.batch_size)
            if not rows:
                break
            for row in rows:
                content_id = int(row[0])
                details[content_id] = get_content_details_service(
                    content_id,
                    connection,
                    include_decision_debug=True,
                )
        connection.rollback()

    payload = build_comparison(baseline, details)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    conflict_payload = build_identity_conflict_report(payload)
    conflict_output_path.parent.mkdir(parents=True, exist_ok=True)
    conflict_output_path.write_text(
        json.dumps(conflict_payload, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(payload["catalog_metrics"], indent=2, sort_keys=True))
    print(f"DB writes: none")
    print(f"Output: {output_path.relative_to(REPO_ROOT)}")
    print(f"Conflict output: {conflict_output_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
