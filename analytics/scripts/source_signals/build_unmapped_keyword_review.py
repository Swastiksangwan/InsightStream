#!/usr/bin/env python3
"""Build a deterministic, read-only review of unmapped TMDb keywords."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from analytics.scripts.common.paths import REPO_ROOT
from analytics.scripts.source_signals.build_keyword_signal_preview import (
    fetch_imported_tmdb_keywords,
    load_mapping_config,
)
from analytics.scripts.source_signals.source_signal_keyword_normalization import (
    keyword_normalization_metadata,
    normalize_keyword_name,
)


DEFAULT_MAPPING_PATH = (
    REPO_ROOT / "analytics" / "config" / "source_signal_keyword_mapping.json"
)
DEFAULT_DECISIONS_PATH = (
    REPO_ROOT / "analytics" / "config" / "source_signal_keyword_review_decisions.json"
)
DEFAULT_OUTPUT_PATH = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "source_signal_reviews"
    / "source_signal_unmapped_keyword_review.json"
)
DATABASE_URL_ENV = "DATABASE_URL"
MANY_KEYWORDS = 8
LOW_COVERAGE = 0.50
SAMPLE_LIMIT = 8
VALID_CLASSIFICATIONS = {
    "useful_product_signal",
    "canonical_metadata",
    "lifecycle_or_format",
    "location_or_setting",
    "franchise_or_universe",
    "award_or_marketing",
    "provider_artifact",
    "spoiler_unsafe",
    "irrelevant_or_too_generic",
    "ambiguous_manual_review",
}
VALID_ACTIONS = {"map", "exclude", "spoiler_unsafe", "leave_unmapped"}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a read-only review of high-impact unmapped TMDb keywords."
    )
    parser.add_argument("--database-url", help="PostgreSQL URL; defaults to DATABASE_URL.")
    parser.add_argument("--mapping-file", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument(
        "--baseline-mapping-file",
        type=Path,
        help="Optional prior mapping config used to describe before/after transitions.",
    )
    parser.add_argument("--decisions-file", type=Path, default=DEFAULT_DECISIONS_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--top", type=positive_int, default=100)
    parser.add_argument("--minimum-title-count", type=positive_int, default=3)
    parser.add_argument("--sample-limit", type=positive_int, default=SAMPLE_LIMIT)
    return parser.parse_args(argv)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def load_review_document(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"decisions": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_decisions = payload.get("decisions")
    if not isinstance(raw_decisions, dict):
        raise ValueError("Review decisions must contain an object named decisions")

    decisions: dict[str, dict[str, Any]] = {}
    for raw_keyword, raw_decision in raw_decisions.items():
        keyword = normalize_keyword_name(raw_keyword)
        if not keyword or not isinstance(raw_decision, dict):
            raise ValueError(f"Invalid review decision for {raw_keyword!r}")
        classification = str(raw_decision.get("classification") or "")
        action = str(raw_decision.get("action") or "")
        if classification not in VALID_CLASSIFICATIONS:
            raise ValueError(f"Invalid classification for {raw_keyword!r}: {classification}")
        if action not in VALID_ACTIONS:
            raise ValueError(f"Invalid action for {raw_keyword!r}: {action}")
        decisions[keyword] = {**raw_decision, "classification": classification, "action": action}
    return {**payload, "decisions": decisions}


def load_review_decisions(path: Path) -> dict[str, dict[str, Any]]:
    return load_review_document(path)["decisions"]


def normalized_signal_definition(signal: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "dimension": str(signal.get("dimension") or ""),
        "value": str(signal.get("value") or ""),
        "display_label": str(signal.get("display_label") or ""),
        "weight": int(signal.get("weight") or 1),
        "confidence": str(signal.get("confidence") or "low"),
        "spoiler_safe": bool(signal.get("spoiler_safe", True)),
    }


def runtime_mapping_signals(mapping: Mapping[str, Any], keyword: str) -> list[dict[str, Any]]:
    entry = mapping.get("keyword_mappings", {}).get(keyword) or {}
    return [normalized_signal_definition(signal) for signal in entry.get("signals", [])]


def validate_review_document(document: Mapping[str, Any], mapping: Mapping[str, Any]) -> None:
    mapping_version = mapping.get("mapping_version")
    if document.get("supports_mapping_version") != mapping_version:
        raise ValueError(
            "Review decisions support mapping version "
            f"{document.get('supports_mapping_version')!r}, not {mapping_version!r}"
        )
    if document.get("normalization_contract") != "source-signal-keyword-v1":
        raise ValueError("Review decisions use an unsupported normalization contract")

    mapped, excluded, spoiler = mapping_status_sets(mapping)
    for keyword, decision in document.get("decisions", {}).items():
        action = decision["action"]
        memberships = sum((keyword in mapped, keyword in excluded, keyword in spoiler))
        if memberships > 1:
            raise ValueError(f"{keyword}: runtime mapping status is ambiguous")
        if action == "map":
            proposed = decision.get("mapping")
            if not isinstance(proposed, list) or not proposed:
                raise ValueError(f"{keyword}: map decision must store an exact mapping")
            normalized_proposed = [normalized_signal_definition(signal) for signal in proposed]
            if keyword not in mapped or normalized_proposed != runtime_mapping_signals(mapping, keyword):
                raise ValueError(f"{keyword}: reviewed mapping differs from runtime mapping")
        elif action == "exclude" and keyword not in excluded:
            raise ValueError(f"{keyword}: exclude decision is absent from excluded_keywords")
        elif action == "spoiler_unsafe" and keyword not in spoiler:
            raise ValueError(f"{keyword}: spoiler decision is absent from spoiler_unsafe_keywords")
        elif action == "leave_unmapped" and memberships:
            raise ValueError(f"{keyword}: leave_unmapped decision exists in runtime config")


def mapping_status(mapping: Mapping[str, Any] | None, keyword: str) -> str | None:
    if mapping is None:
        return None
    mapped, excluded, spoiler = mapping_status_sets(mapping)
    if keyword in mapped:
        return "mapped"
    if keyword in excluded:
        return "excluded"
    if keyword in spoiler:
        return "spoiler_unsafe"
    return "unmapped"


def decision_consistency(
    decision: Mapping[str, Any] | None,
    mapping: Mapping[str, Any],
    keyword: str,
) -> str:
    if not decision:
        return "not_reviewed"
    action_status = {
        "map": "mapped",
        "exclude": "excluded",
        "spoiler_unsafe": "spoiler_unsafe",
        "leave_unmapped": "unmapped",
    }[str(decision["action"])]
    if mapping_status(mapping, keyword) != action_status:
        return "inconsistent"
    if decision["action"] == "map":
        proposed = [normalized_signal_definition(signal) for signal in decision.get("mapping", [])]
        if proposed != runtime_mapping_signals(mapping, keyword):
            return "inconsistent"
    return "consistent"


def fetch_review_rows_read_only(connection: Any) -> list[dict[str, Any]]:
    transaction = connection.begin()
    try:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SET TRANSACTION READ ONLY"))
        rows = fetch_imported_tmdb_keywords(connection)
        transaction.rollback()
        return rows
    except Exception:
        transaction.rollback()
        raise


def mapping_status_sets(mapping: Mapping[str, Any]) -> tuple[set[str], set[str], set[str]]:
    mapped = {normalize_keyword_name(value) for value in mapping.get("keyword_mappings", {})}
    excluded = {normalize_keyword_name(value) for value in mapping.get("excluded_keywords", set())}
    spoiler = {
        normalize_keyword_name(value) for value in mapping.get("spoiler_unsafe_keywords", set())
    }
    return mapped, excluded, spoiler


def build_review_report(
    rows: list[dict[str, Any]],
    mapping: Mapping[str, Any],
    decisions: Mapping[str, Mapping[str, Any]],
    baseline_mapping: Mapping[str, Any] | None = None,
    review_metadata: Mapping[str, Any] | None = None,
    *,
    top: int = 100,
    minimum_title_count: int = 3,
    sample_limit: int = SAMPLE_LIMIT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    mapped, excluded, spoiler = mapping_status_sets(mapping)
    keyword_titles: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    variants: dict[str, Counter[str]] = defaultdict(Counter)
    title_keywords: dict[int, set[str]] = defaultdict(set)

    for row in rows:
        raw_name = str(row.get("keyword_name") or "").strip()
        normalized = normalize_keyword_name(row.get("normalized_keyword_name") or raw_name)
        if not normalized:
            continue
        content_id = int(row["content_id"])
        variants[normalized][raw_name or normalized] += 1
        title_keywords[content_id].add(normalized)
        keyword_titles[normalized][content_id] = {
            "content_id": content_id,
            "title": str(row.get("title") or f"content_id={content_id}"),
            "content_type": str(row.get("content_type") or ""),
        }

    low_coverage_ids: set[int] = set()
    for content_id, keywords in title_keywords.items():
        mapped_count = sum(keyword in mapped for keyword in keywords)
        actionable_count = sum(
            keyword not in excluded and keyword not in spoiler for keyword in keywords
        )
        if (
            len(keywords) >= MANY_KEYWORDS
            and actionable_count
            and mapped_count / actionable_count < LOW_COVERAGE
        ):
            low_coverage_ids.add(content_id)

    unmapped_counts = {
        keyword: len(titles)
        for keyword, titles in keyword_titles.items()
        if keyword not in mapped and keyword not in excluded and keyword not in spoiler
    }
    ordered_unmapped = sorted(unmapped_counts, key=lambda value: (-unmapped_counts[value], value))
    selected = set(ordered_unmapped[:top])
    selected.update(
        keyword for keyword, count in unmapped_counts.items() if count >= minimum_title_count
    )
    selected.update(
        keyword
        for keyword, titles in keyword_titles.items()
        if keyword in unmapped_counts
        and sum(content_id in low_coverage_ids for content_id in titles) >= 2
    )
    selected.update(keyword for keyword in decisions if keyword in keyword_titles)

    entries: list[dict[str, Any]] = []
    for keyword in sorted(selected, key=lambda value: (-len(keyword_titles[value]), value)):
        decision = dict(decisions.get(keyword) or {})
        samples = sorted(
            keyword_titles[keyword].values(),
            key=lambda item: (item["title"].casefold(), item["content_id"]),
        )[:sample_limit]
        proposal = decision.get("mapping") if decision.get("action") == "map" else None
        before_status = mapping_status(baseline_mapping, keyword)
        after_status = mapping_status(mapping, keyword)
        baseline_signals = (
            runtime_mapping_signals(baseline_mapping, keyword)
            if baseline_mapping is not None and before_status == "mapped"
            else []
        )
        candidate_signals = runtime_mapping_signals(mapping, keyword) if after_status == "mapped" else []
        baseline_evaluated = baseline_mapping is not None
        mapping_changed = bool(
            baseline_evaluated
            and before_status == after_status == "mapped"
            and baseline_signals != candidate_signals
        )
        no_runtime_change = (
            before_status == after_status and not mapping_changed if baseline_evaluated else None
        )
        entries.append(
            {
                "normalized_keyword": keyword,
                "original_variants": [
                    {"value": value, "assignment_count": count}
                    for value, count in sorted(
                        variants[keyword].items(), key=lambda item: (-item[1], item[0].casefold())
                    )
                ],
                "affected_title_count": len(keyword_titles[keyword]),
                "low_coverage_title_count": sum(
                    content_id in low_coverage_ids for content_id in keyword_titles[keyword]
                ),
                "sample_affected_titles": samples,
                "runtime_mapping_status": after_status,
                "baseline_mapping_status": before_status,
                "candidate_mapping_status": after_status,
                "status_before": before_status,
                "status_after": after_status,
                "decision_action": decision.get("action", "leave_unmapped"),
                "decision_consistency": decision_consistency(decision or None, mapping, keyword),
                "mapping_added": bool(
                    baseline_evaluated and before_status != "mapped" and after_status == "mapped"
                ),
                "exclusion_added": bool(
                    baseline_evaluated and before_status != "excluded" and after_status == "excluded"
                ),
                "spoiler_rule_added": bool(
                    baseline_evaluated
                    and before_status != "spoiler_unsafe"
                    and after_status == "spoiler_unsafe"
                ),
                "mapping_changed": mapping_changed,
                "no_runtime_change": no_runtime_change,
                "proposed_classification": decision.get(
                    "classification", "ambiguous_manual_review"
                ),
                "proposed_action": decision.get("action", "leave_unmapped"),
                "proposed_mapping": proposal,
                "rationale": decision.get(
                    "rationale", "No reviewed decision has been recorded yet."
                ),
                "confidence": decision.get("confidence", "low"),
                "human_review_required": bool(decision.get("human_review_required", True)),
            }
        )

    classification_counts = Counter(entry["proposed_classification"] for entry in entries)
    action_counts = Counter(entry["proposed_action"] for entry in entries)
    return {
        "report_version": "2026-07-22-v1.1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "normalization": keyword_normalization_metadata(),
        "versions": {
            "baseline_mapping_version": (
                baseline_mapping.get("mapping_version") if baseline_mapping is not None else None
            ),
            "candidate_mapping_version": mapping.get("mapping_version"),
            "decision_review_version": (review_metadata or {}).get("review_version"),
            "decision_supports_mapping_version": (review_metadata or {}).get(
                "supports_mapping_version"
            ),
            "normalization_version": keyword_normalization_metadata()["version"],
        },
        "selection": {
            "top_unmapped_limit": top,
            "minimum_title_count": minimum_title_count,
            "many_keywords_threshold": MANY_KEYWORDS,
            "low_mapping_coverage_threshold": LOW_COVERAGE,
            "selected_keyword_count": len(entries),
        },
        "catalog_summary": {
            "title_count": len(title_keywords),
            "keyword_assignment_count": sum(len(values) for values in title_keywords.values()),
            "unique_keyword_count": len(keyword_titles),
            "unique_unmapped_keyword_count": len(unmapped_counts),
            "low_coverage_title_count": len(low_coverage_ids),
        },
        "classification_counts": dict(sorted(classification_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "keywords": entries,
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    mapping_path = resolve_path(args.mapping_file)
    baseline_mapping_path = (
        resolve_path(args.baseline_mapping_file) if args.baseline_mapping_file else None
    )
    decisions_path = resolve_path(args.decisions_file)
    output_path = resolve_path(args.output)
    try:
        mapping = load_mapping_config(mapping_path)
        review_document = load_review_document(decisions_path)
        decisions = review_document["decisions"]
        validate_review_document(review_document, mapping)
        baseline_mapping = (
            load_mapping_config(baseline_mapping_path) if baseline_mapping_path else None
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: Unable to load review configuration: {exc}", file=sys.stderr)
        return 1

    database_url = args.database_url or os.getenv(DATABASE_URL_ENV)
    if not database_url:
        print(f"ERROR: Missing {DATABASE_URL_ENV}.", file=sys.stderr)
        return 1
    try:
        engine = create_engine(database_url)
        with engine.connect() as connection:
            rows = fetch_review_rows_read_only(connection)
    except SQLAlchemyError as exc:
        print(f"ERROR: Unable to read imported keywords: {exc}", file=sys.stderr)
        return 1

    report = build_review_report(
        rows,
        mapping,
        decisions,
        baseline_mapping=baseline_mapping,
        review_metadata=review_document,
        top=args.top,
        minimum_title_count=args.minimum_title_count,
        sample_limit=args.sample_limit,
    )
    write_json(output_path, report)
    print("DB writes: none")
    print(f"Reviewed keywords: {report['selection']['selected_keyword_count']}")
    print(f"Low-coverage titles: {report['catalog_summary']['low_coverage_title_count']}")
    print(f"Output: {output_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
