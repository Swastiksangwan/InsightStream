#!/usr/bin/env python3
"""
Dry-run or apply TMDb keywords from the processed keyword preview.

This script:
- reads analytics/processed/tmdb_keywords/tmdb_keywords_preview.json
- requires DATABASE_URL for dry-run comparison and apply mode
- imports raw provider keywords only; it does not create source_signals
- runs in dry-run mode by default
- requires --apply before writing to PostgreSQL
- does not call TMDb or any external API
- does not delete or stale-mark missing keywords in v1

Dry run:
    python3 analytics/scripts/import_tmdb_keywords_from_preview.py

Apply:
    python3 analytics/scripts/import_tmdb_keywords_from_preview.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
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
    / "tmdb_keywords"
    / "tmdb_keywords_preview.json"
)
DEFAULT_REPORT_PATH = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "tmdb_keywords"
    / "run_reports"
    / "tmdb_keywords_import_report.json"
)
SUPPORTED_CONTENT_TYPES = {"movie", "series"}
KEYWORD_SOURCE = {
    "source_name": "tmdb",
    "display_name": "TMDb",
    "is_active": True,
}
DEFAULT_CONFIDENCE = "medium"


@dataclass(frozen=True)
class ContentMatch:
    content_id: int
    title: str
    content_type: str


@dataclass(frozen=True)
class KeywordPreviewRecord:
    content_id: int
    title: str
    content_type: str
    tmdb_id: str | None
    external_keyword_id: str
    keyword_name: str
    normalized_keyword_name: str
    confidence: str
    raw_payload: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime
    fetched_at: datetime
    source_preview_generated_at: datetime
    import_run_id: str
    import_report_path: str


@dataclass
class ImportStats:
    mode: str
    preview_file: str
    report_output: str
    preview_generated_at: str | None = None
    import_run_id: str | None = None
    db_write_performed: bool = False
    content_rows_seen: int = 0
    content_rows_selected: int = 0
    content_rows_importable: int = 0
    content_rows_skipped: int = 0
    failed_preview_rows: int = 0
    provider_keywords_inserted: int = 0
    provider_keywords_updated: int = 0
    provider_keywords_unchanged: int = 0
    content_keywords_inserted: int = 0
    content_keywords_updated: int = 0
    content_keywords_unchanged: int = 0
    duplicate_keywords_deduped: int = 0
    malformed_keywords_skipped: int = 0
    missing_content_rows_skipped: int = 0
    keyword_sources_inserted: int = 0
    keyword_sources_updated: int = 0
    provider_keyword_row_count_after: int = 0
    content_keyword_row_count_after: int = 0
    movie_titles_imported: int = 0
    series_titles_imported: int = 0
    titles_imported: list[dict[str, Any]] = field(default_factory=list)
    titles_skipped: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class TmdbKeywordImportError(RuntimeError):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply TMDb keywords from processed preview."
    )
    parser.add_argument(
        "--preview-file",
        default=str(DEFAULT_PREVIEW_PATH.relative_to(REPO_ROOT)),
        help=(
            "Path to TMDb keywords preview JSON. Defaults to "
            f"{DEFAULT_PREVIEW_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write TMDb keywords to PostgreSQL. Without this flag, no DB writes occur.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit selected preview content rows after filters.",
    )
    parser.add_argument(
        "--content-type",
        choices=["movie", "series", "all"],
        default="all",
        help="Filter preview rows by content type. Defaults to all.",
    )
    parser.add_argument(
        "--content-id",
        type=int,
        action="append",
        help="Import only this content ID. Can be passed more than once.",
    )
    parser.add_argument(
        "--only-content-ids-file",
        help="JSON file containing either a list of content IDs or {\"content_ids\": [...]}.",
    )
    parser.add_argument(
        "--report-output",
        default=str(DEFAULT_REPORT_PATH.relative_to(REPO_ROOT)),
        help=(
            "Import report JSON path. Defaults to "
            f"{DEFAULT_REPORT_PATH.relative_to(REPO_ROOT)}."
        ),
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


def normalize_keyword_name(value: Any) -> str | None:
    text_value = clean_text(value)
    if not text_value:
        return None
    return re.sub(r"\s+", " ", text_value.lower())


def parse_preview_timestamp(value: Any) -> datetime:
    text_value = clean_text(value)
    if not text_value:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def import_run_id_for_preview(source_preview_generated_at: datetime) -> str:
    return f"tmdb-keywords-{source_preview_generated_at.strftime('%Y%m%dT%H%M%S')}"


def values_equal(left: Any, right: Any) -> bool:
    return left == right


def json_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, default=str) == json.dumps(
        right,
        sort_keys=True,
        default=str,
    )


def json_param(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True)


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(report), indent=2, ensure_ascii=False) + "\n")


def load_preview(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise TmdbKeywordImportError(f"Missing TMDb keywords preview: {relative_path(path)}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TmdbKeywordImportError(
            f"Malformed TMDb keywords preview JSON in {relative_path(path)}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise TmdbKeywordImportError("TMDb keywords preview root must be an object.")
    if not isinstance(data.get("items"), list):
        raise TmdbKeywordImportError("TMDb keywords preview must contain an items list.")

    return data


def load_content_ids_file(path: Path) -> set[int]:
    if not path.exists():
        raise TmdbKeywordImportError(f"Missing content IDs file: {relative_path(path)}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TmdbKeywordImportError(
            f"Malformed content IDs file JSON in {relative_path(path)}: {exc}"
        ) from exc

    raw_ids = data.get("content_ids") if isinstance(data, dict) else data
    if not isinstance(raw_ids, list):
        raise TmdbKeywordImportError(
            "Content IDs file must be a JSON list or an object with content_ids."
        )

    content_ids: set[int] = set()
    for raw_id in raw_ids:
        content_id = clean_int(raw_id)
        if content_id is not None:
            content_ids.add(content_id)
    return content_ids


def selected_content_ids(args: argparse.Namespace) -> set[int] | None:
    content_ids: set[int] = set(args.content_id or [])
    if args.only_content_ids_file:
        content_ids.update(load_content_ids_file(resolve_path(args.only_content_ids_file)))
    return content_ids or None


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


def keyword_record_from_raw_keyword(
    raw_keyword: Any,
    item: dict[str, Any],
    source_preview_generated_at: datetime,
    import_run_id: str,
    import_report_path: str,
    stats: ImportStats,
) -> KeywordPreviewRecord | None:
    title = clean_text(item.get("title")) or f"content_id={item.get('content_id')}"
    if not isinstance(raw_keyword, dict):
        stats.malformed_keywords_skipped += 1
        stats.warnings.append(f"{title}: keyword row is not an object; skipped.")
        return None

    external_keyword_id = clean_int(raw_keyword.get("keyword_id"))
    keyword_name = clean_text(raw_keyword.get("keyword_name"))
    normalized_keyword_name = normalize_keyword_name(keyword_name)
    if external_keyword_id is None or not keyword_name or not normalized_keyword_name:
        stats.malformed_keywords_skipped += 1
        stats.warnings.append(f"{title}: malformed keyword row skipped.")
        return None

    content_id = clean_int(item.get("content_id"))
    content_type = (clean_text(item.get("content_type")) or "").lower()
    fetched_at = parse_preview_timestamp(item.get("fetched_at"))
    tmdb_id = clean_text(item.get("tmdb_id")) or clean_text(item.get("source_id"))
    seen_at = source_preview_generated_at or fetched_at
    raw_payload = {
        "tmdb_id": tmdb_id,
        "tmdb_keyword_id": external_keyword_id,
        "keyword_name": keyword_name,
        "preview_generated_at": source_preview_generated_at.isoformat(),
        "preview_source": "tmdb_keywords",
    }

    if content_id is None:
        stats.malformed_keywords_skipped += 1
        stats.warnings.append(f"{title}: keyword row has no valid content_id; skipped.")
        return None

    return KeywordPreviewRecord(
        content_id=content_id,
        title=title,
        content_type=content_type,
        tmdb_id=tmdb_id,
        external_keyword_id=str(external_keyword_id),
        keyword_name=keyword_name,
        normalized_keyword_name=normalized_keyword_name,
        confidence=DEFAULT_CONFIDENCE,
        raw_payload=raw_payload,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        fetched_at=fetched_at,
        source_preview_generated_at=source_preview_generated_at,
        import_run_id=import_run_id,
        import_report_path=import_report_path,
    )


def keyword_records_from_preview_item(
    item: dict[str, Any],
    source_preview_generated_at: datetime,
    import_run_id: str,
    import_report_path: str,
    stats: ImportStats,
) -> list[KeywordPreviewRecord]:
    keywords = item.get("keywords")
    title = clean_text(item.get("title")) or f"content_id={item.get('content_id')}"
    if not isinstance(keywords, list):
        stats.content_rows_skipped += 1
        stats.titles_skipped.append({"title": title, "reason": "keywords missing or invalid"})
        stats.warnings.append(f"{title}: keywords field is not a list; skipped.")
        return []

    records: list[KeywordPreviewRecord] = []
    seen_keyword_ids: set[str] = set()
    for raw_keyword in keywords:
        record = keyword_record_from_raw_keyword(
            raw_keyword,
            item,
            source_preview_generated_at,
            import_run_id,
            import_report_path,
            stats,
        )
        if record is None:
            continue
        if record.external_keyword_id in seen_keyword_ids:
            stats.duplicate_keywords_deduped += 1
            continue
        seen_keyword_ids.add(record.external_keyword_id)
        records.append(record)

    if not records:
        stats.content_rows_skipped += 1
        stats.titles_skipped.append({"title": title, "reason": "no usable keywords"})

    return records


def fetch_content(conn: Any, content_id: int) -> ContentMatch | None:
    row = conn.execute(
        text(
            """
            SELECT id, title, content_type
            FROM content
            WHERE id = :content_id;
            """
        ),
        {"content_id": content_id},
    ).mappings().first()
    if row is None:
        return None
    return ContentMatch(
        content_id=row["id"],
        title=row["title"],
        content_type=row["content_type"],
    )


def fetch_keyword_source(conn: Any, source_name: str):
    return conn.execute(
        text(
            """
            SELECT id, source_name, display_name, is_active
            FROM keyword_sources
            WHERE source_name = :source_name;
            """
        ),
        {"source_name": source_name},
    ).mappings().first()


def insert_or_update_keyword_source(conn: Any) -> int:
    row = conn.execute(
        text(
            """
            INSERT INTO keyword_sources (
                source_name,
                display_name,
                is_active
            )
            VALUES (
                :source_name,
                :display_name,
                :is_active
            )
            ON CONFLICT (source_name) DO UPDATE
            SET
                display_name = EXCLUDED.display_name,
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id;
            """
        ),
        KEYWORD_SOURCE,
    ).mappings().first()
    return row["id"]


def ensure_keyword_source(conn: Any, stats: ImportStats, apply: bool) -> int:
    source = fetch_keyword_source(conn, "tmdb")
    if source is None:
        stats.keyword_sources_inserted += 1
        if apply:
            return insert_or_update_keyword_source(conn)
        return -1

    changed = any(
        not values_equal(source.get(field), KEYWORD_SOURCE[field])
        for field in ("display_name", "is_active")
    )
    if changed:
        stats.keyword_sources_updated += 1
        if apply:
            return insert_or_update_keyword_source(conn)

    return source["id"]


def fetch_provider_keyword(conn: Any, source_id: int, external_keyword_id: str):
    if source_id < 0:
        return None
    return conn.execute(
        text(
            """
            SELECT id, keyword_name, normalized_keyword_name
            FROM provider_keywords
            WHERE source_id = :source_id
              AND external_keyword_id = :external_keyword_id;
            """
        ),
        {"source_id": source_id, "external_keyword_id": external_keyword_id},
    ).mappings().first()


def insert_provider_keyword(
    conn: Any,
    source_id: int,
    record: KeywordPreviewRecord,
) -> int:
    row = conn.execute(
        text(
            """
            INSERT INTO provider_keywords (
                source_id,
                external_keyword_id,
                keyword_name,
                normalized_keyword_name
            )
            VALUES (
                :source_id,
                :external_keyword_id,
                :keyword_name,
                :normalized_keyword_name
            )
            ON CONFLICT (source_id, external_keyword_id) DO UPDATE
            SET
                keyword_name = EXCLUDED.keyword_name,
                normalized_keyword_name = EXCLUDED.normalized_keyword_name,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id;
            """
        ),
        {
            "source_id": source_id,
            "external_keyword_id": record.external_keyword_id,
            "keyword_name": record.keyword_name,
            "normalized_keyword_name": record.normalized_keyword_name,
        },
    ).mappings().first()
    return row["id"]


def provider_keyword_update_plan(
    existing: dict[str, Any],
    record: KeywordPreviewRecord,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if not values_equal(existing.get("keyword_name"), record.keyword_name):
        updates["keyword_name"] = record.keyword_name
    if not values_equal(
        existing.get("normalized_keyword_name"),
        record.normalized_keyword_name,
    ):
        updates["normalized_keyword_name"] = record.normalized_keyword_name
    return updates


def update_provider_keyword(
    conn: Any,
    provider_keyword_row_id: int,
    updates: dict[str, Any],
) -> None:
    set_clauses = [f"{field_name} = :{field_name}" for field_name in updates]
    set_clauses.append("updated_at = CURRENT_TIMESTAMP")
    params = {"provider_keyword_row_id": provider_keyword_row_id, **updates}
    conn.execute(
        text(
            f"""
            UPDATE provider_keywords
            SET {", ".join(set_clauses)}
            WHERE id = :provider_keyword_row_id;
            """
        ),
        params,
    )


def fetch_content_keyword(
    conn: Any,
    content_id: int,
    keyword_id: int,
    source_id: int,
):
    if keyword_id < 0 or source_id < 0:
        return None
    return conn.execute(
        text(
            """
            SELECT
                id,
                confidence,
                raw_payload,
                first_seen_at,
                last_seen_at,
                fetched_at,
                source_preview_generated_at,
                import_run_id,
                import_report_path
            FROM content_keywords
            WHERE content_id = :content_id
              AND keyword_id = :keyword_id
              AND source_id = :source_id;
            """
        ),
        {
            "content_id": content_id,
            "keyword_id": keyword_id,
            "source_id": source_id,
        },
    ).mappings().first()


def content_keyword_update_plan(
    existing: dict[str, Any],
    record: KeywordPreviewRecord,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    comparable_fields = {
        "confidence": record.confidence,
        "last_seen_at": record.last_seen_at,
        "fetched_at": record.fetched_at,
        "source_preview_generated_at": record.source_preview_generated_at,
        "import_run_id": record.import_run_id,
        "import_report_path": record.import_report_path,
    }
    for field_name, value in comparable_fields.items():
        if not values_equal(existing.get(field_name), value):
            updates[field_name] = value

    if not json_equal(existing.get("raw_payload"), record.raw_payload):
        updates["raw_payload"] = record.raw_payload

    return updates


def insert_content_keyword(
    conn: Any,
    record: KeywordPreviewRecord,
    keyword_id: int,
    source_id: int,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO content_keywords (
                content_id,
                keyword_id,
                source_id,
                confidence,
                raw_payload,
                first_seen_at,
                last_seen_at,
                fetched_at,
                source_preview_generated_at,
                import_run_id,
                import_report_path
            )
            VALUES (
                :content_id,
                :keyword_id,
                :source_id,
                :confidence,
                CAST(:raw_payload AS JSONB),
                :first_seen_at,
                :last_seen_at,
                :fetched_at,
                :source_preview_generated_at,
                :import_run_id,
                :import_report_path
            )
            ON CONFLICT (content_id, keyword_id, source_id) DO NOTHING;
            """
        ),
        {
            "content_id": record.content_id,
            "keyword_id": keyword_id,
            "source_id": source_id,
            "confidence": record.confidence,
            "raw_payload": json_param(record.raw_payload),
            "first_seen_at": record.first_seen_at,
            "last_seen_at": record.last_seen_at,
            "fetched_at": record.fetched_at,
            "source_preview_generated_at": record.source_preview_generated_at,
            "import_run_id": record.import_run_id,
            "import_report_path": record.import_report_path,
        },
    )


def update_content_keyword(
    conn: Any,
    content_keyword_id: int,
    updates: dict[str, Any],
) -> None:
    set_clauses = []
    params: dict[str, Any] = {"content_keyword_id": content_keyword_id}
    for field_name, value in updates.items():
        if field_name == "raw_payload":
            set_clauses.append("raw_payload = CAST(:raw_payload AS JSONB)")
            params[field_name] = json_param(value)
        else:
            set_clauses.append(f"{field_name} = :{field_name}")
            params[field_name] = value
    set_clauses.append("updated_at = CURRENT_TIMESTAMP")
    conn.execute(
        text(
            f"""
            UPDATE content_keywords
            SET {", ".join(set_clauses)}
            WHERE id = :content_keyword_id;
            """
        ),
        params,
    )


def count_rows_after_import(
    conn: Any,
    source_id: int,
    stats: ImportStats,
    apply: bool,
) -> tuple[int, int]:
    if source_id < 0:
        return (
            stats.provider_keywords_inserted,
            stats.content_keywords_inserted,
        )
    provider_count = conn.execute(
        text(
            """
            SELECT COUNT(*) AS total
            FROM provider_keywords
            WHERE source_id = :source_id;
            """
        ),
        {"source_id": source_id},
    ).mappings().first()["total"]
    content_keyword_count = conn.execute(
        text(
            """
            SELECT COUNT(*) AS total
            FROM content_keywords
            WHERE source_id = :source_id;
            """
        ),
        {"source_id": source_id},
    ).mappings().first()["total"]
    if apply:
        return provider_count, content_keyword_count
    return (
        provider_count + stats.provider_keywords_inserted,
        content_keyword_count + stats.content_keywords_inserted,
    )


def process_preview(
    conn: Any,
    preview: dict[str, Any],
    preview_path: Path,
    report_output_path: Path,
    apply: bool,
    content_type_filter: str = "all",
    content_id_filter: set[int] | None = None,
    limit: int | None = None,
) -> ImportStats:
    source_preview_generated_at = parse_preview_timestamp(preview.get("generated_at"))
    import_run_id = import_run_id_for_preview(source_preview_generated_at)
    stats = ImportStats(
        mode="APPLY" if apply else "DRY RUN",
        preview_file=relative_path(preview_path),
        report_output=relative_path(report_output_path),
        preview_generated_at=source_preview_generated_at.isoformat(),
        import_run_id=import_run_id,
        db_write_performed=apply,
    )
    source_id = ensure_keyword_source(conn, stats, apply)
    keyword_ids_by_external_id: dict[str, int] = {}
    fake_keyword_id = -1
    seen_content_keyword_keys: set[tuple[int, str]] = set()
    selected_count = 0

    for index, item in enumerate(preview.get("items", []), start=1):
        stats.content_rows_seen += 1
        if not isinstance(item, dict):
            stats.content_rows_skipped += 1
            stats.titles_skipped.append({"title": f"item #{index}", "reason": "not object"})
            stats.warnings.append(f"Preview item {index}: expected object; skipped.")
            continue

        title = clean_text(item.get("title")) or f"content_id={item.get('content_id')}"
        if not should_select_item(item, content_type_filter, content_id_filter):
            continue
        if limit is not None and selected_count >= limit:
            continue

        selected_count += 1
        stats.content_rows_selected += 1
        if clean_text(item.get("fetch_status")) != "success":
            stats.failed_preview_rows += 1
            stats.content_rows_skipped += 1
            stats.titles_skipped.append({"title": title, "reason": "failed preview row"})
            continue

        records = keyword_records_from_preview_item(
            item,
            source_preview_generated_at,
            import_run_id,
            relative_path(report_output_path),
            stats,
        )
        if not records:
            continue

        content = fetch_content(conn, records[0].content_id)
        if content is None:
            stats.missing_content_rows_skipped += 1
            stats.content_rows_skipped += 1
            stats.titles_skipped.append({"title": title, "reason": "missing content row"})
            stats.warnings.append(
                f"{title}: no content row found for content_id {records[0].content_id}; skipped."
            )
            continue

        if content.content_type != records[0].content_type:
            stats.warnings.append(
                f"{title}: preview content_type {records[0].content_type!r} "
                f"differs from DB content_type {content.content_type!r}; importing by content_id."
            )

        stats.content_rows_importable += 1
        title_changed = False

        for record in records:
            content_keyword_key = (record.content_id, record.external_keyword_id)
            if content_keyword_key in seen_content_keyword_keys:
                stats.duplicate_keywords_deduped += 1
                continue
            seen_content_keyword_keys.add(content_keyword_key)

            keyword_id = keyword_ids_by_external_id.get(record.external_keyword_id)
            if keyword_id is None:
                existing_keyword = fetch_provider_keyword(
                    conn,
                    source_id,
                    record.external_keyword_id,
                )
                if existing_keyword is None:
                    stats.provider_keywords_inserted += 1
                    if apply:
                        keyword_id = insert_provider_keyword(conn, source_id, record)
                    else:
                        keyword_id = fake_keyword_id
                        fake_keyword_id -= 1
                else:
                    updates = provider_keyword_update_plan(dict(existing_keyword), record)
                    keyword_id = existing_keyword["id"]
                    if updates:
                        stats.provider_keywords_updated += 1
                        if apply:
                            update_provider_keyword(conn, keyword_id, updates)
                    else:
                        stats.provider_keywords_unchanged += 1
                keyword_ids_by_external_id[record.external_keyword_id] = keyword_id

            existing_content_keyword = fetch_content_keyword(
                conn,
                record.content_id,
                keyword_id,
                source_id,
            )
            if existing_content_keyword is None:
                stats.content_keywords_inserted += 1
                title_changed = True
                if apply:
                    insert_content_keyword(conn, record, keyword_id, source_id)
                continue

            updates = content_keyword_update_plan(dict(existing_content_keyword), record)
            if updates:
                stats.content_keywords_updated += 1
                title_changed = True
                if apply:
                    update_content_keyword(conn, existing_content_keyword["id"], updates)
            else:
                stats.content_keywords_unchanged += 1

        stats.titles_imported.append(
            {
                "content_id": content.content_id,
                "title": content.title,
                "content_type": content.content_type,
                "changed": title_changed,
            }
        )
        if content.content_type == "movie":
            stats.movie_titles_imported += 1
        elif content.content_type == "series":
            stats.series_titles_imported += 1

    provider_count, content_keyword_count = count_rows_after_import(
        conn,
        source_id,
        stats,
        apply,
    )
    stats.provider_keyword_row_count_after = provider_count
    stats.content_keyword_row_count_after = content_keyword_count
    return stats


def report_from_stats(stats: ImportStats) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_write_performed": stats.db_write_performed,
        "preview_file": stats.preview_file,
        "preview_generated_at": stats.preview_generated_at,
        "import_run_id": stats.import_run_id,
        "import_report_path": stats.report_output,
        "content_rows_seen": stats.content_rows_seen,
        "content_rows_selected": stats.content_rows_selected,
        "content_rows_importable": stats.content_rows_importable,
        "content_rows_skipped": stats.content_rows_skipped,
        "failed_preview_rows": stats.failed_preview_rows,
        "provider_keywords_inserted": stats.provider_keywords_inserted,
        "provider_keywords_updated": stats.provider_keywords_updated,
        "provider_keywords_unchanged": stats.provider_keywords_unchanged,
        "content_keywords_inserted": stats.content_keywords_inserted,
        "content_keywords_updated": stats.content_keywords_updated,
        "content_keywords_unchanged": stats.content_keywords_unchanged,
        "duplicate_keywords_deduped": stats.duplicate_keywords_deduped,
        "malformed_keywords_skipped": stats.malformed_keywords_skipped,
        "missing_content_rows_skipped": stats.missing_content_rows_skipped,
        "titles_imported": stats.titles_imported,
        "titles_skipped": stats.titles_skipped,
        "movie_titles_imported": stats.movie_titles_imported,
        "series_titles_imported": stats.series_titles_imported,
        "provider_keyword_row_count_after": stats.provider_keyword_row_count_after,
        "content_keyword_row_count_after": stats.content_keyword_row_count_after,
        "errors": stats.errors,
        "warnings": stats.warnings,
    }


def print_summary(stats: ImportStats) -> None:
    if stats.db_write_performed:
        print("TMDb keyword import applied.")
        print("DB writes: performed")
    else:
        print("TMDb keyword import dry-run complete.")
        print("DB writes: none")
    print(f"Selected titles: {stats.content_rows_selected}")
    print(
        "Provider keywords to insert/update/unchanged: "
        f"{stats.provider_keywords_inserted}/"
        f"{stats.provider_keywords_updated}/"
        f"{stats.provider_keywords_unchanged}"
    )
    print(
        "Content keyword relationships to insert/update/unchanged: "
        f"{stats.content_keywords_inserted}/"
        f"{stats.content_keywords_updated}/"
        f"{stats.content_keywords_unchanged}"
    )
    print(f"Skipped failed preview rows: {stats.failed_preview_rows}")
    print(f"Malformed keywords skipped: {stats.malformed_keywords_skipped}")
    print(f"Missing content rows skipped: {stats.missing_content_rows_skipped}")
    print(f"Report: {stats.report_output}")
    if stats.warnings:
        print(f"Warnings: {len(stats.warnings)}")
        for warning in stats.warnings[:10]:
            print(f"- {warning}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    preview_path = resolve_path(args.preview_file)
    report_output_path = resolve_path(args.report_output)

    try:
        preview = load_preview(preview_path)
        content_id_filter = selected_content_ids(args)
    except TmdbKeywordImportError as exc:
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
        if args.apply:
            with engine.begin() as conn:
                stats = process_preview(
                    conn,
                    preview,
                    preview_path,
                    report_output_path,
                    apply=True,
                    content_type_filter=args.content_type,
                    content_id_filter=content_id_filter,
                    limit=args.limit,
                )
        else:
            with engine.connect() as conn:
                stats = process_preview(
                    conn,
                    preview,
                    preview_path,
                    report_output_path,
                    apply=False,
                    content_type_filter=args.content_type,
                    content_id_filter=content_id_filter,
                    limit=args.limit,
                )
    except SQLAlchemyError as exc:
        print(f"ERROR: TMDb keyword import failed: {exc}", file=sys.stderr)
        return 1

    write_report(report_output_path, report_from_stats(stats))
    print_summary(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
