#!/usr/bin/env python3
"""
Merge successful TMDb keyword retry preview rows into the main preview/report.

This helper only edits JSON preview/report artifacts. It never connects to the
database and never calls TMDb.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analytics.scripts.ingestion.build_tmdb_keywords_preview import (
    DEFAULT_OUTPUT_PATH,
    DEFAULT_REPORT_PATH,
    LocalTitle,
    build_run_report,
    relative_path,
    resolve_path,
    save_json,
)


from analytics.scripts.common.paths import REPO_ROOT
DEFAULT_RETRY_PREVIEW_PATH = (
    REPO_ROOT / "analytics" / "processed" / "tmdb_keywords" / "tmdb_keywords_retry_preview.json"
)
DEFAULT_RETRY_REPORT_PATH = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "tmdb_keywords"
    / "run_reports"
    / "tmdb_keywords_retry_report.json"
)
DEFAULT_RETRY_TARGETS_PATH = (
    REPO_ROOT / "analytics" / "config" / "tmdb_keywords_retry_targets.json"
)


class TmdbKeywordsMergeError(RuntimeError):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge TMDb keyword retry preview rows into the main preview/report."
    )
    parser.add_argument(
        "--main-preview",
        default=str(DEFAULT_OUTPUT_PATH.relative_to(REPO_ROOT)),
        help="Main TMDb keyword preview path.",
    )
    parser.add_argument(
        "--main-report",
        default=str(DEFAULT_REPORT_PATH.relative_to(REPO_ROOT)),
        help="Main TMDb keyword report path.",
    )
    parser.add_argument(
        "--retry-preview",
        default=str(DEFAULT_RETRY_PREVIEW_PATH.relative_to(REPO_ROOT)),
        help="Retry TMDb keyword preview path.",
    )
    parser.add_argument(
        "--retry-report",
        default=str(DEFAULT_RETRY_REPORT_PATH.relative_to(REPO_ROOT)),
        help="Retry TMDb keyword report path.",
    )
    parser.add_argument(
        "--retry-targets",
        default=str(DEFAULT_RETRY_TARGETS_PATH.relative_to(REPO_ROOT)),
        help="Retry target file to delete when --cleanup-temp is used.",
    )
    parser.add_argument(
        "--cleanup-temp",
        action="store_true",
        help="Delete retry/backup artifacts after a successful clean merge.",
    )
    return parser.parse_args(argv)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TmdbKeywordsMergeError(f"Missing JSON file: {relative_path(path)}") from exc
    except json.JSONDecodeError as exc:
        raise TmdbKeywordsMergeError(
            f"Malformed JSON file: {relative_path(path)} - {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise TmdbKeywordsMergeError(f"JSON root must be an object: {relative_path(path)}")
    return data


def backup_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.before_retry_merge{path.suffix}")


def backup_file(path: Path) -> Path:
    destination = backup_path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    return destination


def content_id_key(item: dict[str, Any]) -> str | None:
    content_id = item.get("content_id")
    if content_id is None:
        return None
    return str(content_id)


def failed_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if item.get("fetch_status") == "failed"]


def preview_errors(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "content_id": item.get("content_id"),
            "title": item.get("title"),
            "content_type": item.get("content_type"),
            "tmdb_id": item.get("tmdb_id"),
            "error_status_code": item.get("error_status_code"),
            "error_message": item.get("error_message"),
            "attempt_count": item.get("attempt_count"),
            "retry_performed": item.get("retry_performed"),
        }
        for item in failed_items(items)
    ]


def merge_preview_items(
    main_items: list[dict[str, Any]],
    retry_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    retry_by_content_id = {
        content_id: item
        for item in retry_items
        if (content_id := content_id_key(item)) is not None
    }

    merged_items: list[dict[str, Any]] = []
    seen_content_ids: set[str] = set()
    merged_successful_retry_items = 0
    unresolved_retry_failures = 0

    for item in main_items:
        content_id = content_id_key(item)
        if content_id is not None and content_id in seen_content_ids:
            continue

        replacement = item
        if (
            content_id is not None
            and item.get("fetch_status") == "failed"
            and content_id in retry_by_content_id
        ):
            replacement = retry_by_content_id[content_id]
            if replacement.get("fetch_status") == "success":
                merged_successful_retry_items += 1
            elif replacement.get("fetch_status") == "failed":
                unresolved_retry_failures += 1

        merged_items.append(replacement)
        if content_id is not None:
            seen_content_ids.add(content_id)

    return merged_items, merged_successful_retry_items, unresolved_retry_failures


def selected_titles_from_items(items: list[dict[str, Any]]) -> list[LocalTitle]:
    titles: list[LocalTitle] = []
    for item in items:
        try:
            content_id = int(item.get("content_id"))
        except (TypeError, ValueError):
            continue
        title = str(item.get("title") or f"content_id={content_id}")
        content_type = str(item.get("content_type") or "")
        tmdb_id = item.get("tmdb_id")
        titles.append(
            LocalTitle(
                content_id=content_id,
                title=title,
                content_type=content_type,
                tmdb_id=str(tmdb_id) if tmdb_id is not None else None,
            )
        )
    return titles


def build_merged_preview(
    main_preview: dict[str, Any],
    merged_items: list[dict[str, Any]],
    merge_metadata: dict[str, Any],
) -> dict[str, Any]:
    preview = dict(main_preview)
    preview["items"] = merged_items
    preview["errors"] = preview_errors(merged_items)
    preview.update(merge_metadata)
    return preview


def build_merged_report(
    main_report: dict[str, Any],
    merged_items: list[dict[str, Any]],
    main_preview_path: Path,
    main_report_path: Path,
    merge_metadata: dict[str, Any],
) -> dict[str, Any]:
    report = build_run_report(
        generated_at=str(main_report.get("generated_at") or merge_metadata["merged_retry_at"]),
        total_local_titles_checked=int(
            main_report.get("total_local_titles_checked") or len(merged_items)
        ),
        selected_titles=selected_titles_from_items(merged_items),
        items=merged_items,
        output_path=main_preview_path,
        report_path=main_report_path,
        warnings=list(main_report.get("warnings") or []),
    )
    report.update(merge_metadata)
    return report


def cleanup_temp_files(
    candidates: list[Path],
    protected_paths: list[Path],
    allow_cleanup: bool,
) -> list[Path]:
    if not allow_cleanup:
        return []

    protected = {path.resolve() for path in protected_paths}
    deleted: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved in protected:
            continue
        if path.exists():
            path.unlink()
            deleted.append(path)
    return deleted


def merge_retry_preview(args: argparse.Namespace) -> dict[str, Any]:
    main_preview_path = resolve_path(args.main_preview)
    main_report_path = resolve_path(args.main_report)
    retry_preview_path = resolve_path(args.retry_preview)
    retry_report_path = resolve_path(args.retry_report)
    retry_targets_path = resolve_path(args.retry_targets)

    main_preview = load_json(main_preview_path)
    main_report = load_json(main_report_path)
    retry_preview = load_json(retry_preview_path)
    load_json(retry_report_path)

    main_items = main_preview.get("items")
    retry_items = retry_preview.get("items")
    if not isinstance(main_items, list):
        raise TmdbKeywordsMergeError("Main preview must contain an items list.")
    if not isinstance(retry_items, list):
        raise TmdbKeywordsMergeError("Retry preview must contain an items list.")

    backup_preview_path = backup_file(main_preview_path)
    backup_report_path = backup_file(main_report_path)

    merged_items, merged_successful_retry_items, _unresolved_retry_failures = (
        merge_preview_items(main_items, retry_items)
    )
    remaining_failed_rows = len(failed_items(merged_items))
    merged_retry_at = datetime.now(timezone.utc).isoformat()
    merge_metadata = {
        "merged_retry_at": merged_retry_at,
        "merged_successful_retry_items": merged_successful_retry_items,
        "unresolved_retry_failures": remaining_failed_rows,
        "merged_retry_source_preview": relative_path(retry_preview_path),
        "merged_retry_source_report": relative_path(retry_report_path),
    }

    save_json(
        main_preview_path,
        build_merged_preview(main_preview, merged_items, merge_metadata),
    )
    save_json(
        main_report_path,
        build_merged_report(
            main_report,
            merged_items,
            main_preview_path,
            main_report_path,
            merge_metadata,
        ),
    )

    cleanup_candidates = [
        retry_targets_path,
        retry_preview_path,
        retry_report_path,
        backup_preview_path,
        backup_report_path,
    ]
    deleted_temp_files = cleanup_temp_files(
        cleanup_candidates,
        [main_preview_path, main_report_path],
        allow_cleanup=args.cleanup_temp and remaining_failed_rows == 0,
    )

    return {
        "merged_successful_retry_items": merged_successful_retry_items,
        "remaining_failed_rows": remaining_failed_rows,
        "updated_preview": main_preview_path,
        "updated_report": main_report_path,
        "backup_preview": backup_preview_path,
        "backup_report": backup_report_path,
        "deleted_temp_files": deleted_temp_files,
        "cleanup_requested": args.cleanup_temp,
    }


def print_summary(summary: dict[str, Any]) -> None:
    print(f"Merged retry rows: {summary['merged_successful_retry_items']}")
    print(f"Remaining failed rows: {summary['remaining_failed_rows']}")
    print(f"Updated preview: {relative_path(summary['updated_preview'])}")
    print(f"Updated report: {relative_path(summary['updated_report'])}")
    print(f"Backup preview: {relative_path(summary['backup_preview'])}")
    print(f"Backup report: {relative_path(summary['backup_report'])}")

    if summary["cleanup_requested"] and summary["remaining_failed_rows"] > 0:
        print("Cleanup skipped because failed rows remain.")
    elif summary["deleted_temp_files"]:
        print("Deleted temporary files:")
        for path in summary["deleted_temp_files"]:
            print(f"- {relative_path(path)}")

    print("No database changes were made.")


def main(argv: list[str] | None = None) -> int:
    try:
        summary = merge_retry_preview(parse_args(argv))
    except TmdbKeywordsMergeError as exc:
        print(f"TMDb keywords retry merge failed: {exc}", file=sys.stderr)
        return 1

    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
