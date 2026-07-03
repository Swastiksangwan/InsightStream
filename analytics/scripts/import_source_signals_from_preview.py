#!/usr/bin/env python3
"""
Dry-run or write source-signal preview output into PostgreSQL.

This script:
- reads analytics/processed/source_signals/source_signal_preview.json
- reads analytics/processed/source_signals/run_reports/source_signal_preview_report.json
- stores current source signals and productized watch guidance only with --write
- is dry-run by default
- does not call TMDb or any external API
- does not expose raw TMDb keywords as user-facing output
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


REPO_ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL_ENV = "DATABASE_URL"
DEFAULT_PREVIEW_PATH = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "source_signals"
    / "source_signal_preview.json"
)
DEFAULT_SOURCE_REPORT_PATH = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "source_signals"
    / "run_reports"
    / "source_signal_preview_report.json"
)
DEFAULT_IMPORT_REPORT_PATH = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "source_signals"
    / "run_reports"
    / "source_signal_import_report.json"
)
VALID_DIMENSIONS = {
    "audience_expectation",
    "content_caution_proxy",
    "intensity",
    "mood",
    "pacing",
    "tone",
    "topic_theme",
}
VALID_CONFIDENCE = {"low", "medium", "high"}


@dataclass(frozen=True)
class SourceSignalRecord:
    content_id: int
    dimension: str
    value: str
    label: str
    confidence: str
    source_names: list[str]
    source_payload: dict[str, Any]

    @property
    def key(self) -> tuple[int, str, str]:
        return (self.content_id, self.dimension, self.value)


@dataclass(frozen=True)
class WatchGuidanceRecord:
    content_id: int
    watch_feel: str
    chips: list[str]
    best_for: list[str]
    consider_first: list[str]
    keyword_counts: dict[str, Any]
    signal_sources: list[str]
    curated_override_applied: bool
    metadata_fallback_applied: bool
    quality_summary: dict[str, Any]


@dataclass
class ImportPlan:
    mode: str
    preview_path: str
    report_path: str
    import_report_path: str
    db_write_performed: bool = False
    run_id: int | None = None
    run_key: str | None = None
    mapping_version: str | None = None
    override_version: str | None = None
    preview_generator_version: str | None = None
    semantic_qa_version: str | None = None
    preview_generated_at: str | None = None
    selected_titles: int = 0
    total_source_signal_ready_content: int = 0
    is_partial_preview: bool = False
    missing_content_rows: int = 0
    invalid_preview_rows: int = 0
    signals_to_insert: int = 0
    signals_to_update: int = 0
    signals_to_delete_or_deactivate: int = 0
    signals_unchanged: int = 0
    guidance_to_insert: int = 0
    guidance_to_update: int = 0
    guidance_unchanged: int = 0
    titles_imported: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    signal_records: list[SourceSignalRecord] = field(default_factory=list)
    guidance_records: list[WatchGuidanceRecord] = field(default_factory=list)
    obsolete_signal_ids: list[int] = field(default_factory=list)
    semantic_quality_summary: dict[str, Any] = field(default_factory=dict)
    coverage_by_content_type: dict[str, Any] = field(default_factory=dict)
    signals_by_source: dict[str, Any] = field(default_factory=dict)


class SourceSignalImportError(RuntimeError):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or write source-signal preview output into PostgreSQL."
    )
    parser.add_argument(
        "--preview",
        default=str(DEFAULT_PREVIEW_PATH.relative_to(REPO_ROOT)),
        help=(
            "Source signal preview JSON path. Defaults to "
            f"{DEFAULT_PREVIEW_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--report",
        default=str(DEFAULT_SOURCE_REPORT_PATH.relative_to(REPO_ROOT)),
        help=(
            "Source signal preview report JSON path. Defaults to "
            f"{DEFAULT_SOURCE_REPORT_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--import-report-output",
        default=str(DEFAULT_IMPORT_REPORT_PATH.relative_to(REPO_ROOT)),
        help=(
            "Import report JSON path. Defaults to "
            f"{DEFAULT_IMPORT_REPORT_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write source signals to PostgreSQL. Without this flag, no DB writes occur.",
    )
    parser.add_argument(
        "--allow-semantic-qa-issues",
        action="store_true",
        help="Allow writes when semantic QA counts are non-zero.",
    )
    parser.add_argument(
        "--allow-partial-preview",
        action="store_true",
        help="Allow importing a partial preview or selected subset.",
    )
    parser.add_argument(
        "--content-id",
        type=int,
        action="append",
        help="Import only this content ID. Can be passed more than once.",
    )
    parser.add_argument(
        "--content-type",
        choices=["movie", "series", "all"],
        default="all",
        help="Filter preview rows by content type. Defaults to all.",
    )
    return parser.parse_args(argv)


def resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def clean_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def parse_datetime(value: Any) -> datetime | None:
    text_value = clean_text(value)
    if not text_value:
        return None
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def json_param(value: Any) -> str:
    return json.dumps(json_safe(value), sort_keys=True)


def json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def json_equal(left: Any, right: Any) -> bool:
    return json_param(json_value(left)) == json_param(right)


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise SourceSignalImportError(f"Missing {label}: {relative_path(path)}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceSignalImportError(
            f"Malformed JSON in {relative_path(path)}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise SourceSignalImportError(f"{label} root must be a JSON object.")
    return data


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_safe(report), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


def source_names_from_signals(signals: dict[str, list[dict[str, Any]]]) -> list[str]:
    sources = {
        source
        for signal_list in signals.values()
        for signal in signal_list
        for source in signal.get("sources", [])
        if clean_text(source)
    }
    return sorted(sources)


def should_select_item(
    item: dict[str, Any],
    content_type_filter: str,
    content_id_filter: set[int] | None,
) -> bool:
    content_id = clean_int(item.get("content_id"))
    content_type = (clean_text(item.get("content_type")) or "").lower()
    if content_id_filter is not None and content_id not in content_id_filter:
        return False
    if content_type_filter != "all" and content_type != content_type_filter:
        return False
    return True


def semantic_qa_counts(summary: dict[str, Any]) -> dict[str, int]:
    return {
        "generic_watch_feel_count": int(summary.get("generic_watch_feel_count") or 0),
        "semantic_conflict_count": int(summary.get("semantic_conflict_count") or 0),
        "curated_review_candidate_count": int(
            summary.get("curated_review_candidate_count") or 0
        ),
    }


def validate_preview_and_report(
    preview: dict[str, Any],
    report: dict[str, Any],
    plan: ImportPlan,
    *,
    write_requested: bool,
    allow_semantic_qa_issues: bool,
) -> None:
    if not isinstance(preview.get("items"), list):
        plan.errors.append("Preview must contain an items list.")
    for field_name in (
        "mapping_version",
        "override_version",
        "preview_generator_version",
        "semantic_qa_version",
        "semantic_quality_summary",
        "errors",
        "warnings",
    ):
        if field_name not in report:
            plan.errors.append(f"Report missing required field: {field_name}.")

    report_errors = report.get("errors")
    report_warnings = report.get("warnings")
    if report_errors:
        plan.errors.append("Preview report contains errors; refusing import.")
    if not isinstance(report_errors, list):
        plan.errors.append("Report errors field must be a list.")
    if not isinstance(report_warnings, list):
        plan.errors.append("Report warnings field must be a list.")

    summary = report.get("semantic_quality_summary") or {}
    if not isinstance(summary, dict):
        plan.errors.append("Report semantic_quality_summary must be an object.")
        summary = {}
    plan.semantic_quality_summary = dict(summary)
    counts = semantic_qa_counts(summary)
    if write_requested and any(counts.values()) and not allow_semantic_qa_issues:
        plan.errors.append(
            "Semantic QA counts are non-zero; pass --allow-semantic-qa-issues to write anyway."
        )


def signal_records_from_item(
    item: dict[str, Any],
    report: dict[str, Any],
    plan: ImportPlan,
) -> list[SourceSignalRecord]:
    content_id = clean_int(item.get("content_id"))
    title = clean_text(item.get("title")) or f"content_id={content_id}"
    signals = item.get("signals")
    if content_id is None:
        plan.invalid_preview_rows += 1
        plan.errors.append(f"{title}: missing or invalid content_id.")
        return []
    if not isinstance(signals, dict):
        plan.invalid_preview_rows += 1
        plan.errors.append(f"{title}: signals must be an object.")
        return []

    records: list[SourceSignalRecord] = []
    seen_keys: set[tuple[int, str, str]] = set()
    for dimension, signal_list in signals.items():
        if dimension not in VALID_DIMENSIONS:
            plan.invalid_preview_rows += 1
            plan.errors.append(f"{title}: unknown signal dimension {dimension!r}.")
            continue
        if not isinstance(signal_list, list):
            plan.invalid_preview_rows += 1
            plan.errors.append(f"{title}: signal dimension {dimension!r} must be a list.")
            continue
        for signal in signal_list:
            if not isinstance(signal, dict):
                plan.invalid_preview_rows += 1
                plan.errors.append(f"{title}: signal row in {dimension!r} is invalid.")
                continue
            value = clean_text(signal.get("value"))
            label = clean_text(signal.get("label"))
            confidence = clean_text(signal.get("confidence"))
            sources = signal.get("sources")
            if not value or not label or confidence not in VALID_CONFIDENCE:
                plan.invalid_preview_rows += 1
                plan.errors.append(f"{title}: signal row in {dimension!r} is incomplete.")
                continue
            if not isinstance(sources, list) or not all(clean_text(item) for item in sources):
                plan.invalid_preview_rows += 1
                plan.errors.append(f"{title}: signal sources must be a non-empty string list.")
                continue
            key = (content_id, dimension, value)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            records.append(
                SourceSignalRecord(
                    content_id=content_id,
                    dimension=dimension,
                    value=value,
                    label=label,
                    confidence=confidence,
                    source_names=sorted({str(source) for source in sources}),
                    source_payload={
                        "mapping_version": report.get("mapping_version"),
                        "override_version": report.get("override_version"),
                        "preview_generator_version": report.get(
                            "preview_generator_version"
                        ),
                        "semantic_qa_version": report.get("semantic_qa_version"),
                        "content_type": item.get("content_type"),
                        "curated_override_applied": bool(
                            item.get("curated_override_applied")
                        ),
                        "metadata_fallback_applied": bool(
                            item.get("metadata_fallback_applied")
                        ),
                    },
                )
            )
    return records


def guidance_record_from_item(
    item: dict[str, Any],
    plan: ImportPlan,
) -> WatchGuidanceRecord | None:
    content_id = clean_int(item.get("content_id"))
    title = clean_text(item.get("title")) or f"content_id={content_id}"
    guidance = item.get("watch_guidance")
    signals = item.get("signals") if isinstance(item.get("signals"), dict) else {}
    if content_id is None or not isinstance(guidance, dict):
        plan.invalid_preview_rows += 1
        plan.errors.append(f"{title}: missing watch guidance.")
        return None

    watch_feel = clean_text(guidance.get("watch_feel"))
    chips = guidance.get("chips")
    best_for = guidance.get("best_for")
    consider_first = guidance.get("consider_first")
    if not watch_feel:
        plan.invalid_preview_rows += 1
        plan.errors.append(f"{title}: watch_guidance.watch_feel is required.")
        return None
    if not isinstance(chips, list) or not isinstance(best_for, list) or not isinstance(
        consider_first,
        list,
    ):
        plan.invalid_preview_rows += 1
        plan.errors.append(f"{title}: guidance chips/best_for/consider_first must be lists.")
        return None
    if not any(signals.values()) and not watch_feel:
        plan.invalid_preview_rows += 1
        plan.errors.append(f"{title}: item has no signals and no watch guidance.")
        return None

    return WatchGuidanceRecord(
        content_id=content_id,
        watch_feel=watch_feel,
        chips=[str(item) for item in chips if clean_text(item)],
        best_for=[str(item) for item in best_for if clean_text(item)],
        consider_first=[str(item) for item in consider_first if clean_text(item)],
        keyword_counts=item.get("keyword_counts") if isinstance(item.get("keyword_counts"), dict) else {},
        signal_sources=source_names_from_signals(signals),
        curated_override_applied=bool(item.get("curated_override_applied")),
        metadata_fallback_applied=bool(item.get("metadata_fallback_applied")),
        quality_summary={
            "mapping_version": item.get("mapping_version"),
        },
    )


def fetch_content_rows(conn: Any) -> dict[int, dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            SELECT id, title, content_type
            FROM content;
            """
        )
    ).mappings().all()
    return {int(row["id"]): dict(row) for row in rows}


def count_source_signal_ready_content(conn: Any) -> int:
    row = conn.execute(
        text(
            """
            SELECT COUNT(DISTINCT c.id) AS total
            FROM content c
            JOIN content_keywords ck ON ck.content_id = c.id;
            """
        )
    ).mappings().first()
    return int((row or {}).get("total") or 0)


def fetch_existing_signals(
    conn: Any,
    selected_content_ids: set[int],
) -> dict[tuple[int, str, str], dict[str, Any]]:
    if not selected_content_ids:
        return {}
    rows = conn.execute(
        text(
            """
            SELECT
                id,
                content_id,
                dimension,
                value,
                label,
                confidence,
                source_names,
                source_payload,
                is_active
            FROM content_source_signals
            WHERE content_id = ANY(:content_ids);
            """
        ),
        {"content_ids": sorted(selected_content_ids)},
    ).mappings().all()
    return {
        (int(row["content_id"]), row["dimension"], row["value"]): dict(row)
        for row in rows
    }


def fetch_existing_guidance(
    conn: Any,
    selected_content_ids: set[int],
) -> dict[int, dict[str, Any]]:
    if not selected_content_ids:
        return {}
    rows = conn.execute(
        text(
            """
            SELECT
                content_id,
                watch_feel,
                chips,
                best_for,
                consider_first,
                keyword_counts,
                signal_sources,
                curated_override_applied,
                metadata_fallback_applied,
                storage_ready,
                frontend_ready,
                quality_summary
            FROM content_watch_guidance
            WHERE content_id = ANY(:content_ids);
            """
        ),
        {"content_ids": sorted(selected_content_ids)},
    ).mappings().all()
    return {int(row["content_id"]): dict(row) for row in rows}


def signal_needs_update(existing: dict[str, Any], record: SourceSignalRecord) -> bool:
    return any(
        (
            existing.get("label") != record.label,
            existing.get("confidence") != record.confidence,
            not json_equal(existing.get("source_names"), record.source_names),
            not json_equal(existing.get("source_payload"), record.source_payload),
            existing.get("is_active") is not True,
        )
    )


def guidance_needs_update(existing: dict[str, Any], record: WatchGuidanceRecord) -> bool:
    comparisons = {
        "watch_feel": record.watch_feel,
        "curated_override_applied": record.curated_override_applied,
        "metadata_fallback_applied": record.metadata_fallback_applied,
        "storage_ready": True,
        "frontend_ready": False,
    }
    if any(existing.get(field_name) != value for field_name, value in comparisons.items()):
        return True
    for field_name, value in {
        "chips": record.chips,
        "best_for": record.best_for,
        "consider_first": record.consider_first,
        "keyword_counts": record.keyword_counts,
        "signal_sources": record.signal_sources,
        "quality_summary": record.quality_summary,
    }.items():
        if not json_equal(existing.get(field_name), value):
            return True
    return False


def build_import_plan(
    conn: Any,
    preview: dict[str, Any],
    report: dict[str, Any],
    preview_path: Path,
    report_path: Path,
    import_report_path: Path,
    *,
    write_requested: bool,
    allow_semantic_qa_issues: bool = False,
    allow_partial_preview: bool = False,
    content_type_filter: str = "all",
    content_id_filter: set[int] | None = None,
) -> ImportPlan:
    plan = ImportPlan(
        mode="WRITE" if write_requested else "DRY RUN",
        preview_path=relative_path(preview_path),
        report_path=relative_path(report_path),
        import_report_path=relative_path(import_report_path),
        db_write_performed=False,
        mapping_version=report.get("mapping_version"),
        override_version=report.get("override_version"),
        preview_generator_version=report.get("preview_generator_version"),
        semantic_qa_version=report.get("semantic_qa_version"),
        preview_generated_at=preview.get("generated_at"),
        semantic_quality_summary=report.get("semantic_quality_summary") or {},
        coverage_by_content_type=report.get("coverage_by_content_type") or {},
        signals_by_source=report.get("signals_by_source") or {},
    )
    validate_preview_and_report(
        preview,
        report,
        plan,
        write_requested=write_requested,
        allow_semantic_qa_issues=allow_semantic_qa_issues,
    )

    content_rows = fetch_content_rows(conn)
    total_ready = count_source_signal_ready_content(conn)
    plan.total_source_signal_ready_content = total_ready
    selected_items: list[dict[str, Any]] = []
    for item in preview.get("items", []):
        if not isinstance(item, dict):
            plan.invalid_preview_rows += 1
            plan.errors.append("Preview contains a non-object item.")
            continue
        if should_select_item(item, content_type_filter, content_id_filter):
            selected_items.append(item)
    plan.selected_titles = len(selected_items)

    report_titles_seen = int(report.get("titles_seen") or 0)
    plan.is_partial_preview = (
        (total_ready and report_titles_seen < total_ready)
        or (total_ready and len(selected_items) < total_ready)
        or content_type_filter != "all"
        or bool(content_id_filter)
    )
    if write_requested and plan.is_partial_preview and not allow_partial_preview:
        plan.errors.append(
            "Preview is partial; pass --allow-partial-preview to write only selected content IDs."
        )

    signal_records: list[SourceSignalRecord] = []
    guidance_records: list[WatchGuidanceRecord] = []
    selected_content_ids: set[int] = set()
    for item in selected_items:
        content_id = clean_int(item.get("content_id"))
        title = clean_text(item.get("title")) or f"content_id={content_id}"
        if content_id is None:
            plan.invalid_preview_rows += 1
            plan.errors.append(f"{title}: missing or invalid content_id.")
            continue
        if content_id not in content_rows:
            plan.missing_content_rows += 1
            plan.errors.append(f"{title}: content_id {content_id} does not exist.")
            continue
        selected_content_ids.add(content_id)
        signal_records.extend(signal_records_from_item(item, report, plan))
        guidance_record = guidance_record_from_item(item, plan)
        if guidance_record:
            guidance_records.append(guidance_record)
        plan.titles_imported.append(
            {
                "content_id": content_id,
                "title": content_rows[content_id]["title"],
                "content_type": content_rows[content_id]["content_type"],
            }
        )

    plan.signal_records = signal_records
    plan.guidance_records = guidance_records

    desired_signal_keys = {record.key for record in signal_records}
    existing_signals = fetch_existing_signals(conn, selected_content_ids)
    for record in signal_records:
        existing = existing_signals.get(record.key)
        if not existing:
            plan.signals_to_insert += 1
        elif signal_needs_update(existing, record):
            plan.signals_to_update += 1
        else:
            plan.signals_unchanged += 1
    for key, existing in existing_signals.items():
        if key[0] in selected_content_ids and key not in desired_signal_keys:
            plan.signals_to_delete_or_deactivate += 1
            plan.obsolete_signal_ids.append(int(existing["id"]))

    existing_guidance = fetch_existing_guidance(conn, selected_content_ids)
    for record in guidance_records:
        existing = existing_guidance.get(record.content_id)
        if not existing:
            plan.guidance_to_insert += 1
        elif guidance_needs_update(existing, record):
            plan.guidance_to_update += 1
        else:
            plan.guidance_unchanged += 1

    return plan


def insert_import_run(
    conn: Any,
    plan: ImportPlan,
    preview_path: Path,
    report_path: Path,
) -> int:
    imported_at = datetime.now(timezone.utc)
    run_key = (
        "source-signals-"
        f"{imported_at.strftime('%Y%m%dT%H%M%S%f')}-"
        f"{plan.mapping_version or 'unknown'}-"
        f"{plan.override_version or 'unknown'}"
    )
    row = conn.execute(
        text(
            """
            INSERT INTO source_signal_import_runs (
                run_key,
                preview_path,
                report_path,
                mapping_version,
                override_version,
                preview_generator_version,
                semantic_qa_version,
                preview_generated_at,
                imported_at,
                db_write_performed,
                dry_run,
                titles_seen,
                titles_imported,
                signals_inserted,
                signals_updated,
                signals_deleted,
                signals_unchanged,
                guidance_inserted,
                guidance_updated,
                guidance_unchanged,
                semantic_quality_summary,
                coverage_by_content_type,
                signals_by_source,
                errors,
                warnings
            )
            VALUES (
                :run_key,
                :preview_path,
                :report_path,
                :mapping_version,
                :override_version,
                :preview_generator_version,
                :semantic_qa_version,
                :preview_generated_at,
                :imported_at,
                TRUE,
                FALSE,
                :titles_seen,
                :titles_imported,
                :signals_inserted,
                :signals_updated,
                :signals_deleted,
                :signals_unchanged,
                :guidance_inserted,
                :guidance_updated,
                :guidance_unchanged,
                CAST(:semantic_quality_summary AS JSONB),
                CAST(:coverage_by_content_type AS JSONB),
                CAST(:signals_by_source AS JSONB),
                CAST(:errors AS JSONB),
                CAST(:warnings AS JSONB)
            )
            RETURNING id;
            """
        ),
        {
            "run_key": run_key,
            "preview_path": relative_path(preview_path),
            "report_path": relative_path(report_path),
            "mapping_version": plan.mapping_version,
            "override_version": plan.override_version,
            "preview_generator_version": plan.preview_generator_version,
            "semantic_qa_version": plan.semantic_qa_version,
            "preview_generated_at": parse_datetime(plan.preview_generated_at),
            "imported_at": imported_at,
            "titles_seen": plan.selected_titles,
            "titles_imported": len(plan.guidance_records),
            "signals_inserted": plan.signals_to_insert,
            "signals_updated": plan.signals_to_update,
            "signals_deleted": plan.signals_to_delete_or_deactivate,
            "signals_unchanged": plan.signals_unchanged,
            "guidance_inserted": plan.guidance_to_insert,
            "guidance_updated": plan.guidance_to_update,
            "guidance_unchanged": plan.guidance_unchanged,
            "semantic_quality_summary": json_param(plan.semantic_quality_summary),
            "coverage_by_content_type": json_param(plan.coverage_by_content_type),
            "signals_by_source": json_param(plan.signals_by_source),
            "errors": json_param([]),
            "warnings": json_param(plan.warnings),
        },
    ).mappings().first()
    plan.run_key = run_key
    return int(row["id"])


def upsert_source_signal(conn: Any, record: SourceSignalRecord, run_id: int) -> None:
    conn.execute(
        text(
            """
            INSERT INTO content_source_signals (
                content_id,
                last_signal_run_id,
                dimension,
                value,
                label,
                confidence,
                source_names,
                source_payload,
                is_active
            )
            VALUES (
                :content_id,
                :last_signal_run_id,
                :dimension,
                :value,
                :label,
                :confidence,
                CAST(:source_names AS JSONB),
                CAST(:source_payload AS JSONB),
                TRUE
            )
            ON CONFLICT (content_id, dimension, value) DO UPDATE
            SET
                last_signal_run_id = EXCLUDED.last_signal_run_id,
                label = EXCLUDED.label,
                confidence = EXCLUDED.confidence,
                source_names = EXCLUDED.source_names,
                source_payload = EXCLUDED.source_payload,
                is_active = TRUE,
                updated_at = CURRENT_TIMESTAMP;
            """
        ),
        {
            "content_id": record.content_id,
            "last_signal_run_id": run_id,
            "dimension": record.dimension,
            "value": record.value,
            "label": record.label,
            "confidence": record.confidence,
            "source_names": json_param(record.source_names),
            "source_payload": json_param(record.source_payload),
        },
    )


def delete_obsolete_signals(conn: Any, obsolete_signal_ids: list[int]) -> None:
    for signal_id in obsolete_signal_ids:
        conn.execute(
            text(
                """
                DELETE FROM content_source_signals
                WHERE id = :signal_id;
                """
            ),
            {"signal_id": signal_id},
        )


def upsert_watch_guidance(
    conn: Any,
    record: WatchGuidanceRecord,
    run_id: int,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO content_watch_guidance (
                content_id,
                last_signal_run_id,
                watch_feel,
                chips,
                best_for,
                consider_first,
                keyword_counts,
                signal_sources,
                curated_override_applied,
                metadata_fallback_applied,
                storage_ready,
                frontend_ready,
                quality_summary
            )
            VALUES (
                :content_id,
                :last_signal_run_id,
                :watch_feel,
                CAST(:chips AS JSONB),
                CAST(:best_for AS JSONB),
                CAST(:consider_first AS JSONB),
                CAST(:keyword_counts AS JSONB),
                CAST(:signal_sources AS JSONB),
                :curated_override_applied,
                :metadata_fallback_applied,
                TRUE,
                FALSE,
                CAST(:quality_summary AS JSONB)
            )
            ON CONFLICT (content_id) DO UPDATE
            SET
                last_signal_run_id = EXCLUDED.last_signal_run_id,
                watch_feel = EXCLUDED.watch_feel,
                chips = EXCLUDED.chips,
                best_for = EXCLUDED.best_for,
                consider_first = EXCLUDED.consider_first,
                keyword_counts = EXCLUDED.keyword_counts,
                signal_sources = EXCLUDED.signal_sources,
                curated_override_applied = EXCLUDED.curated_override_applied,
                metadata_fallback_applied = EXCLUDED.metadata_fallback_applied,
                storage_ready = TRUE,
                frontend_ready = FALSE,
                quality_summary = EXCLUDED.quality_summary,
                updated_at = CURRENT_TIMESTAMP;
            """
        ),
        {
            "content_id": record.content_id,
            "last_signal_run_id": run_id,
            "watch_feel": record.watch_feel,
            "chips": json_param(record.chips),
            "best_for": json_param(record.best_for),
            "consider_first": json_param(record.consider_first),
            "keyword_counts": json_param(record.keyword_counts),
            "signal_sources": json_param(record.signal_sources),
            "curated_override_applied": record.curated_override_applied,
            "metadata_fallback_applied": record.metadata_fallback_applied,
            "quality_summary": json_param(record.quality_summary),
        },
    )


def apply_import_plan(
    conn: Any,
    plan: ImportPlan,
    preview_path: Path,
    report_path: Path,
) -> ImportPlan:
    if plan.errors:
        return plan
    run_id = insert_import_run(conn, plan, preview_path, report_path)
    plan.run_id = run_id
    delete_obsolete_signals(conn, plan.obsolete_signal_ids)
    for record in plan.signal_records:
        upsert_source_signal(conn, record, run_id)
    for record in plan.guidance_records:
        upsert_watch_guidance(conn, record, run_id)
    plan.db_write_performed = True
    return plan


def report_from_plan(plan: ImportPlan) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_write_performed": plan.db_write_performed,
        "mode": plan.mode,
        "preview_path": plan.preview_path,
        "report_path": plan.report_path,
        "import_report_path": plan.import_report_path,
        "run_id": plan.run_id,
        "run_key": plan.run_key,
        "mapping_version": plan.mapping_version,
        "override_version": plan.override_version,
        "preview_generator_version": plan.preview_generator_version,
        "semantic_qa_version": plan.semantic_qa_version,
        "preview_generated_at": plan.preview_generated_at,
        "selected_titles": plan.selected_titles,
        "total_source_signal_ready_content": plan.total_source_signal_ready_content,
        "is_partial_preview": plan.is_partial_preview,
        "missing_content_rows": plan.missing_content_rows,
        "invalid_preview_rows": plan.invalid_preview_rows,
        "signals_to_insert": plan.signals_to_insert,
        "signals_to_update": plan.signals_to_update,
        "signals_to_delete_or_deactivate": plan.signals_to_delete_or_deactivate,
        "signals_unchanged": plan.signals_unchanged,
        "guidance_to_insert": plan.guidance_to_insert,
        "guidance_to_update": plan.guidance_to_update,
        "guidance_unchanged": plan.guidance_unchanged,
        "semantic_quality_summary": plan.semantic_quality_summary,
        "coverage_by_content_type": plan.coverage_by_content_type,
        "signals_by_source": plan.signals_by_source,
        "titles_imported": plan.titles_imported,
        "errors": plan.errors,
        "warnings": plan.warnings,
    }


def print_summary(plan: ImportPlan) -> None:
    if plan.db_write_performed:
        print("Source signal import applied.")
        print("DB writes: performed")
    else:
        print("Source signal import dry-run complete.")
        print("DB writes: none")
    print(f"Selected titles: {plan.selected_titles}")
    print(
        "Signals to insert/update/delete/unchanged: "
        f"{plan.signals_to_insert}/"
        f"{plan.signals_to_update}/"
        f"{plan.signals_to_delete_or_deactivate}/"
        f"{plan.signals_unchanged}"
    )
    print(
        "Guidance to insert/update/unchanged: "
        f"{plan.guidance_to_insert}/"
        f"{plan.guidance_to_update}/"
        f"{plan.guidance_unchanged}"
    )
    print(f"Missing content rows: {plan.missing_content_rows}")
    print(f"Invalid preview rows: {plan.invalid_preview_rows}")
    print(f"Report: {plan.import_report_path}")
    if plan.errors:
        print(f"Errors: {len(plan.errors)}")
        for error in plan.errors[:10]:
            print(f"- {error}")
    if plan.warnings:
        print(f"Warnings: {len(plan.warnings)}")
        for warning in plan.warnings[:10]:
            print(f"- {warning}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    preview_path = resolve_path(args.preview)
    source_report_path = resolve_path(args.report)
    import_report_path = resolve_path(args.import_report_output)
    content_id_filter = set(args.content_id or []) or None

    try:
        preview = load_json(preview_path, "source signal preview")
        source_report = load_json(source_report_path, "source signal preview report")
    except SourceSignalImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    database_url = os.getenv(DATABASE_URL_ENV)
    if not database_url:
        print(
            f"ERROR: Missing {DATABASE_URL_ENV}. Export it before running this importer.",
            file=sys.stderr,
        )
        return 1

    try:
        engine = create_engine(database_url)
        if args.write:
            with engine.begin() as conn:
                plan = build_import_plan(
                    conn,
                    preview,
                    source_report,
                    preview_path,
                    source_report_path,
                    import_report_path,
                    write_requested=True,
                    allow_semantic_qa_issues=args.allow_semantic_qa_issues,
                    allow_partial_preview=args.allow_partial_preview,
                    content_type_filter=args.content_type,
                    content_id_filter=content_id_filter,
                )
                if not plan.errors:
                    plan = apply_import_plan(conn, plan, preview_path, source_report_path)
        else:
            with engine.connect() as conn:
                plan = build_import_plan(
                    conn,
                    preview,
                    source_report,
                    preview_path,
                    source_report_path,
                    import_report_path,
                    write_requested=False,
                    allow_semantic_qa_issues=args.allow_semantic_qa_issues,
                    allow_partial_preview=args.allow_partial_preview,
                    content_type_filter=args.content_type,
                    content_id_filter=content_id_filter,
                )
    except SQLAlchemyError as exc:
        print(f"ERROR: Source signal import failed: {exc}", file=sys.stderr)
        return 1

    write_report(import_report_path, report_from_plan(plan))
    print_summary(plan)
    return 1 if plan.errors else 0


if __name__ == "__main__":
    sys.exit(main())
