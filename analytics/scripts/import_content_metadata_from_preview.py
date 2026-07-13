#!/usr/bin/env python3
"""
Dry-run or apply normalized content metadata from a processed preview.

This script:
- reads analytics/processed/tmdb/sample_mapping_preview.json
- requires DATABASE_URL for both dry-run comparison and apply mode
- runs in dry-run mode by default
- requires --apply before writing to PostgreSQL
- does not call TMDb or any external API
- does not modify backend/frontend/schema/sample_data files

Dry run:
    python3 analytics/scripts/import_content_metadata_from_preview.py

Apply:
    python3 analytics/scripts/import_content_metadata_from_preview.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PREVIEW_PATH = (
    REPO_ROOT / "analytics" / "processed" / "tmdb" / "sample_mapping_preview.json"
)
DATABASE_URL_ENV = "DATABASE_URL"
MEDIA_TYPE_TO_CONTENT_TYPE = {
    "movie": "movie",
    "tv": "series",
}
LANGUAGE_MAP = {
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "ml": "Malayalam",
    "kn": "Kannada",
    "bn": "Bengali",
    "mr": "Marathi",
    "pa": "Punjabi",
    "gu": "Gujarati",
    "ur": "Urdu",
    "ko": "Korean",
    "ja": "Japanese",
    "zh": "Chinese",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
    "tr": "Turkish",
    "th": "Thai",
    "vi": "Vietnamese",
    "id": "Indonesian",
    "pl": "Polish",
    "nl": "Dutch",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
    "cs": "Czech",
    "el": "Greek",
    "he": "Hebrew",
    "fa": "Persian",
}
STATUS_MAP = {
    "Released": "Released",
    "Ended": "Ended",
    "Returning Series": "Ongoing",
    "Canceled": "Canceled",
    "In Production": "Upcoming",
    "Planned": "Upcoming",
    "Post Production": "Upcoming",
}
GENRE_MAP = {
    "Science Fiction": ("Sci-Fi",),
    "Sci-Fi & Fantasy": ("Sci-Fi", "Fantasy"),
    "Action & Adventure": ("Action", "Adventure"),
    "Action": ("Action",),
    "Adventure": ("Adventure",),
    "Animation": ("Animation",),
    "Comedy": ("Comedy",),
    "Crime": ("Crime",),
    "Drama": ("Drama",),
    "Fantasy": ("Fantasy",),
    "Horror": ("Horror",),
    "Mystery": ("Mystery",),
    "Romance": ("Romance",),
    "Thriller": ("Thriller",),
}
CONTENT_INSERT_COLUMNS = (
    "tmdb_id",
    "title",
    "original_title",
    "content_type",
    "overview",
    "poster_url",
    "backdrop_url",
    "release_date",
    "latest_activity_date",
    "year",
    "runtime",
    "language",
    "original_language",
    "status",
    "age_rating",
)
FILL_ONLY_FIELDS = (
    "tmdb_id",
    "title",
    "original_title",
    "overview",
    "poster_url",
    "backdrop_url",
    "release_date",
    "year",
    "runtime",
    "language",
    "original_language",
    "status",
    "age_rating",
)
ALWAYS_UPDATE_FIELDS = ("latest_activity_date",)
PROVIDER_SIGNAL_FIELDS = ("vote_average", "vote_count", "popularity")
SEPARATE_PIPELINE_FIELDS = ("top_cast_names", "director_or_creator_names")
NO_COLUMN_FIELDS = ("poster_path", "backdrop_path")
SERIES_STATUS_MAP = {
    "Returning Series": "ongoing",
    "In Production": "ongoing",
    "Planned": "upcoming",
    "Pilot": "upcoming",
    "Ended": "ended",
    "Canceled": "cancelled",
    "Cancelled": "cancelled",
}
SERIES_METADATA_FIELDS = (
    "number_of_seasons",
    "number_of_episodes",
    "series_status",
    "series_status_normalized",
    "in_production",
    "first_air_date",
    "last_air_date",
    "last_episode_air_date",
    "next_episode_air_date",
    "series_type",
    "released_seasons_count",
    "announced_seasons_count",
    "next_season_number",
    "next_season_air_date",
    "next_season_year",
    "has_announced_season",
    "season_summary_note",
    "source_name",
)
SEASON_SUMMARY_FIELDS = {
    "released_seasons_count",
    "announced_seasons_count",
    "next_season_number",
    "next_season_air_date",
    "next_season_year",
    "has_announced_season",
    "season_summary_note",
}
MAX_ROW_REPORT_ITEMS = 50
MAX_DISPLAY_VALUE_LENGTH = 120


@dataclass(frozen=True)
class FieldChange:
    field_name: str
    old_value: Any
    new_value: Any


@dataclass
class RowChange:
    content_id: Optional[int]
    title: str
    fields: List[FieldChange] = field(default_factory=list)


@dataclass(frozen=True)
class ContentPreviewRecord:
    title: str
    content_type: str
    tmdb_id: int
    tmdb_external_id: str
    imdb_id: Optional[str]
    content_values: Dict[str, Any]
    genres: List[str]
    series_metadata: Optional[Dict[str, Any]]


@dataclass
class ImportStats:
    mode: str
    preview_path: str
    items_processed: int = 0
    items_skipped: int = 0
    content_inserted: int = 0
    content_matched_existing: int = 0
    content_fields_updated: int = 0
    external_ids_inserted: int = 0
    genres_inserted: int = 0
    content_genres_inserted: int = 0
    series_metadata_inserted: int = 0
    series_metadata_updated: int = 0
    series_metadata_unchanged: int = 0
    season_summary_updates: int = 0
    latest_activity_date_updates: int = 0
    conflicts_preserved: int = 0
    skipped_fields: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    field_updates: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    content_update_messages: List[str] = field(default_factory=list)
    inserted_content_rows: List[RowChange] = field(default_factory=list)
    updated_content_rows: List[RowChange] = field(default_factory=list)
    inserted_series_metadata_rows: List[RowChange] = field(default_factory=list)
    updated_series_metadata_rows: List[RowChange] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class ContentMetadataImportError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run or apply normalized content metadata from "
            "analytics/processed/tmdb/sample_mapping_preview.json."
        )
    )
    parser.add_argument(
        "--preview",
        default=str(DEFAULT_PREVIEW_PATH.relative_to(REPO_ROOT)),
        help=(
            "Path to processed content metadata preview. Defaults to "
            f"{DEFAULT_PREVIEW_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write content metadata to PostgreSQL. Without this flag, no DB writes occur.",
    )
    return parser.parse_args()


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


def clean_text(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def clean_int(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def clean_date(value: Any) -> Optional[str]:
    text_value = clean_text(value)
    if not text_value:
        return None
    try:
        datetime.strptime(text_value, "%Y-%m-%d")
    except ValueError:
        return None
    return text_value


def clean_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "t", "1", "yes"}:
            return True
        if normalized in {"false", "f", "0", "no"}:
            return False
    return None


def db_value(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    return value


def values_equal(left: Any, right: Any) -> bool:
    left_value = db_value(left)
    right_value = db_value(right)
    return left_value == right_value


def is_empty(value: Any) -> bool:
    value = db_value(value)
    return value is None or (isinstance(value, str) and not value.strip())


def load_preview(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ContentMetadataImportError(
            f"Missing content metadata preview: {relative_path(path)}"
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContentMetadataImportError(
            f"Malformed content metadata preview JSON in {relative_path(path)}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ContentMetadataImportError("Content metadata preview root must be an object.")
    if data.get("source_provider") != "tmdb":
        raise ContentMetadataImportError(
            "Content metadata preview source_provider must be 'tmdb'."
        )
    if data.get("inspection_only") is not True:
        raise ContentMetadataImportError(
            "Content metadata preview must be marked inspection_only."
        )
    if not isinstance(data.get("items"), list):
        raise ContentMetadataImportError(
            "Content metadata preview must contain an items list."
        )

    return data


def content_type_from_item(item: Dict[str, Any]) -> Optional[str]:
    content_type = clean_text(item.get("content_type"))
    if content_type in {"movie", "series"}:
        return content_type

    media_type = clean_text(item.get("media_type"))
    if media_type:
        return MEDIA_TYPE_TO_CONTENT_TYPE.get(media_type)

    return None


def normalize_language(value: Any, title: str, warnings: List[str]) -> Optional[str]:
    code = clean_text(value)
    if not code:
        return None
    normalized_code = code.lower()
    if normalized_code in LANGUAGE_MAP:
        return LANGUAGE_MAP[normalized_code]

    warnings.append(
        f"{title}: unknown language code {code!r}; preserved as original_language but not applied to legacy language."
    )
    return None


def normalize_original_language(value: Any) -> Optional[str]:
    code = clean_text(value)
    if not code:
        return None
    return code.lower()


def normalize_status(value: Any, title: str, warnings: List[str]) -> Optional[str]:
    status = clean_text(value)
    if not status:
        return None
    if status in STATUS_MAP:
        return STATUS_MAP[status]

    warnings.append(
        f"{title}: unknown status {status!r}; mapped to Unknown for new rows and flagged for review."
    )
    return "Unknown"


def normalize_series_status(value: Any) -> str:
    status = clean_text(value)
    if not status:
        return "unknown"
    return SERIES_STATUS_MAP.get(status, "unknown")


def normalize_genres(raw_genres: Any, title: str, warnings: List[str]) -> List[str]:
    if not isinstance(raw_genres, list):
        warnings.append(f"{title}: preview genres field is not a list; skipped.")
        return []

    normalized: List[str] = []
    for raw_genre in raw_genres:
        genre_name = clean_text(raw_genre)
        if not genre_name:
            continue

        mapped_genres = GENRE_MAP.get(genre_name)
        if not mapped_genres:
            mapped_genres = (genre_name,)

        for mapped_genre in mapped_genres:
            if mapped_genre not in normalized:
                normalized.append(mapped_genre)

    return normalized


def series_metadata_from_item(
    item: Dict[str, Any],
    title: str,
    warnings: List[str],
) -> Optional[Dict[str, Any]]:
    raw_metadata = item.get("series_metadata")
    if raw_metadata is None:
        return None
    if not isinstance(raw_metadata, dict):
        warnings.append(f"{title}: series_metadata is not an object; skipped.")
        return None

    series_status = clean_text(raw_metadata.get("series_status"))
    normalized_status = clean_text(raw_metadata.get("series_status_normalized"))
    if normalized_status not in {"ongoing", "ended", "cancelled", "upcoming", "unknown"}:
        normalized_status = normalize_series_status(series_status)

    return {
        "number_of_seasons": clean_int(raw_metadata.get("number_of_seasons")),
        "number_of_episodes": clean_int(raw_metadata.get("number_of_episodes")),
        "series_status": series_status,
        "series_status_normalized": normalized_status or "unknown",
        "in_production": clean_bool(raw_metadata.get("in_production")),
        "first_air_date": clean_date(raw_metadata.get("first_air_date")),
        "last_air_date": clean_date(raw_metadata.get("last_air_date")),
        "last_episode_air_date": clean_date(raw_metadata.get("last_episode_air_date")),
        "next_episode_air_date": clean_date(raw_metadata.get("next_episode_air_date")),
        "series_type": clean_text(raw_metadata.get("series_type")),
        "released_seasons_count": clean_int(
            raw_metadata.get("released_seasons_count")
        ),
        "announced_seasons_count": clean_int(
            raw_metadata.get("announced_seasons_count")
        ),
        "next_season_number": clean_int(raw_metadata.get("next_season_number")),
        "next_season_air_date": clean_date(raw_metadata.get("next_season_air_date")),
        "next_season_year": clean_int(raw_metadata.get("next_season_year")),
        "has_announced_season": clean_bool(
            raw_metadata.get("has_announced_season")
        ),
        "season_summary_note": clean_text(raw_metadata.get("season_summary_note")),
        "source_name": clean_text(raw_metadata.get("source_name")) or "tmdb",
    }


def preview_genres(item: Dict[str, Any]) -> Any:
    genres = item.get("genres")
    if isinstance(genres, list):
        return genres
    return item.get("genre_names")


def collect_skipped_preview_fields(item: Dict[str, Any], stats: ImportStats) -> None:
    for field_name in PROVIDER_SIGNAL_FIELDS:
        if item.get(field_name) is not None:
            stats.skipped_fields[f"{field_name} (provider signal only)"] += 1

    for field_name in SEPARATE_PIPELINE_FIELDS:
        if item.get(field_name):
            stats.skipped_fields[f"{field_name} (credits/person pipeline)"] += 1

    for field_name in NO_COLUMN_FIELDS:
        if item.get(field_name):
            stats.skipped_fields[f"{field_name} (URL field imported instead)"] += 1


def preview_record_from_item(
    item: Any,
    index: int,
    stats: ImportStats,
) -> Optional[ContentPreviewRecord]:
    if not isinstance(item, dict):
        stats.warnings.append(f"Preview item {index} has invalid shape; skipped.")
        stats.items_skipped += 1
        return None

    title = clean_text(item.get("title")) or f"<item {index}>"
    content_type = content_type_from_item(item)
    tmdb_external_id = clean_text(item.get("source_id"))
    tmdb_id = clean_int(item.get("tmdb_id"))

    if not tmdb_external_id and tmdb_id is not None:
        tmdb_external_id = str(tmdb_id)
    if tmdb_id is None and tmdb_external_id:
        tmdb_id = clean_int(tmdb_external_id)

    if not clean_text(item.get("title")):
        stats.warnings.append(f"{title}: missing title; skipped.")
        stats.items_skipped += 1
        return None
    if content_type not in {"movie", "series"}:
        stats.warnings.append(f"{title}: missing or unsupported content_type; skipped.")
        stats.items_skipped += 1
        return None
    if tmdb_id is None or not tmdb_external_id:
        stats.warnings.append(f"{title}: missing usable TMDb ID; skipped.")
        stats.items_skipped += 1
        return None

    local_warnings: List[str] = []
    content_values: Dict[str, Any] = {
        "tmdb_id": tmdb_id,
        "title": clean_text(item.get("title")),
        "original_title": clean_text(item.get("original_title"))
        or clean_text(item.get("original_name")),
        "content_type": content_type,
        "overview": clean_text(item.get("overview")),
        "poster_url": clean_text(item.get("poster_url")),
        "backdrop_url": clean_text(item.get("backdrop_url")),
        "release_date": clean_date(item.get("release_date")),
        "latest_activity_date": clean_date(item.get("latest_activity_date")),
        "year": clean_int(item.get("year")),
        "runtime": clean_int(item.get("runtime")),
        "language": normalize_language(item.get("original_language"), title, local_warnings),
        "original_language": normalize_original_language(item.get("original_language")),
        "status": normalize_status(item.get("status"), title, local_warnings),
        "age_rating": clean_text(item.get("age_rating")),
    }
    genres = normalize_genres(preview_genres(item), title, local_warnings)
    series_metadata = (
        series_metadata_from_item(item, title, local_warnings)
        if content_type == "series"
        else None
    )

    stats.warnings.extend(local_warnings)
    collect_skipped_preview_fields(item, stats)

    return ContentPreviewRecord(
        title=title,
        content_type=content_type,
        tmdb_id=tmdb_id,
        tmdb_external_id=tmdb_external_id,
        imdb_id=clean_text(item.get("imdb_id")),
        content_values=content_values,
        genres=genres,
        series_metadata=series_metadata,
    )


def fetch_content_by_external_id(connection, source_name: str, external_id: str):
    return connection.execute(
        text(
            """
            SELECT c.*
            FROM external_ids ei
            JOIN content c ON c.id = ei.content_id
            WHERE ei.source_name = :source_name
              AND ei.external_id = :external_id;
            """
        ),
        {
            "source_name": source_name,
            "external_id": external_id,
        },
    ).mappings().first()


def fetch_content_by_title_type(connection, title: str, content_type: str):
    return connection.execute(
        text(
            """
            SELECT *
            FROM content
            WHERE title = :title
              AND content_type = :content_type
            ORDER BY id;
            """
        ),
        {
            "title": title,
            "content_type": content_type,
        },
    ).mappings().all()


def insert_content(connection, record: ContentPreviewRecord) -> int:
    row = connection.execute(
        text(
            """
            INSERT INTO content (
                tmdb_id,
                title,
                original_title,
                content_type,
                overview,
                poster_url,
                backdrop_url,
                release_date,
                latest_activity_date,
                year,
                runtime,
                language,
                original_language,
                status,
                age_rating
            )
            VALUES (
                :tmdb_id,
                :title,
                :original_title,
                :content_type,
                :overview,
                :poster_url,
                :backdrop_url,
                :release_date,
                :latest_activity_date,
                :year,
                :runtime,
                :language,
                :original_language,
                :status,
                :age_rating
            )
            RETURNING id;
            """
        ),
        {column: record.content_values.get(column) for column in CONTENT_INSERT_COLUMNS},
    ).mappings().first()
    return row["id"]


def is_valid_series_status_refresh(value: Any) -> bool:
    status = clean_text(value)
    return status is not None and status.lower() != "unknown"


def format_update_value(value: Any) -> str:
    if is_empty(value):
        return "empty"
    return repr(db_value(value))


def format_report_value(value: Any) -> str:
    if is_empty(value):
        return "empty"

    display_value = str(db_value(value))
    if len(display_value) > MAX_DISPLAY_VALUE_LENGTH:
        return f"{display_value[:MAX_DISPLAY_VALUE_LENGTH - 1]}…"
    return display_value


def display_content_id(content_id: Optional[int]) -> str:
    if content_id is None or content_id < 0:
        return "pending"
    return str(content_id)


def field_changes_from_updates(
    existing_values: Dict[str, Any],
    updates: Dict[str, Any],
) -> List[FieldChange]:
    return [
        FieldChange(
            field_name=field_name,
            old_value=existing_values.get(field_name),
            new_value=new_value,
        )
        for field_name, new_value in updates.items()
    ]


def record_inserted_content_row(
    stats: ImportStats,
    content_id: Optional[int],
    title: str,
) -> None:
    stats.inserted_content_rows.append(RowChange(content_id=content_id, title=title))


def record_updated_content_row(
    stats: ImportStats,
    content_id: int,
    title: str,
    existing_values: Dict[str, Any],
    updates: Dict[str, Any],
) -> None:
    if not updates:
        return
    stats.updated_content_rows.append(
        RowChange(
            content_id=content_id,
            title=title,
            fields=field_changes_from_updates(existing_values, updates),
        )
    )


def record_inserted_series_metadata_row(
    stats: ImportStats,
    content_id: Optional[int],
    title: str,
) -> None:
    stats.inserted_series_metadata_rows.append(
        RowChange(content_id=content_id, title=title)
    )


def record_updated_series_metadata_row(
    stats: ImportStats,
    content_id: int,
    title: str,
    existing_values: Dict[str, Any],
    updates: Dict[str, Any],
) -> None:
    if not updates:
        return
    stats.updated_series_metadata_rows.append(
        RowChange(
            content_id=content_id,
            title=title,
            fields=field_changes_from_updates(existing_values, updates),
        )
    )


def add_content_update_message(
    stats: ImportStats,
    title: str,
    field_name: str,
    existing_value: Any,
    preview_value: Any,
) -> None:
    action = "would update" if stats.mode == "DRY RUN" else "will update"
    stats.content_update_messages.append(
        f"{title}: content.{field_name} {action} from "
        f"{format_update_value(existing_value)} to {format_update_value(preview_value)}."
    )


def content_update_plan(
    existing: Dict[str, Any],
    record: ContentPreviewRecord,
    stats: ImportStats,
) -> Dict[str, Any]:
    updates: Dict[str, Any] = {}
    title = record.title

    for field_name in FILL_ONLY_FIELDS:
        preview_value = record.content_values.get(field_name)
        existing_value = existing.get(field_name)
        if field_name == "status" and record.content_type == "series":
            if is_valid_series_status_refresh(preview_value) and not values_equal(
                existing_value,
                preview_value,
            ):
                updates[field_name] = preview_value
                add_content_update_message(
                    stats,
                    title,
                    field_name,
                    existing_value,
                    preview_value,
                )
            continue
        if is_empty(existing_value) and not is_empty(preview_value):
            updates[field_name] = preview_value
        elif (
            not is_empty(existing_value)
            and not is_empty(preview_value)
            and not values_equal(existing_value, preview_value)
        ):
            stats.conflicts_preserved += 1
            stats.warnings.append(
                f"{title}: existing content.{field_name} differs from preview; preserved existing value."
            )

    for field_name in ALWAYS_UPDATE_FIELDS:
        preview_value = record.content_values.get(field_name)
        if (
            field_name == "latest_activity_date"
            and record.content_type == "movie"
            and not is_empty(existing.get("release_date"))
        ):
            # Movie recency follows the app's selected release_date. Provider
            # preview dates may differ by region, and release_date is preserved.
            preview_value = db_value(existing.get("release_date"))
        existing_value = existing.get(field_name)
        if not is_empty(preview_value) and not values_equal(existing_value, preview_value):
            updates[field_name] = preview_value

    return updates


def update_content_fields(
    connection,
    content_id: int,
    updates: Dict[str, Any],
) -> None:
    if not updates:
        return

    set_clauses = []
    params: Dict[str, Any] = {"content_id": content_id}
    for field_name, value in updates.items():
        set_clauses.append(f"{field_name} = :{field_name}")
        params[field_name] = value
    set_clauses.append("updated_at = CURRENT_TIMESTAMP")

    connection.execute(
        text(
            f"""
            UPDATE content
            SET {", ".join(set_clauses)}
            WHERE id = :content_id;
            """
        ),
        params,
    )


def fetch_external_id_for_content(connection, content_id: int, source_name: str):
    return connection.execute(
        text(
            """
            SELECT id, external_id
            FROM external_ids
            WHERE content_id = :content_id
              AND source_name = :source_name;
            """
        ),
        {
            "content_id": content_id,
            "source_name": source_name,
        },
    ).mappings().first()


def fetch_external_id_owner(connection, source_name: str, external_id: str):
    return connection.execute(
        text(
            """
            SELECT content_id
            FROM external_ids
            WHERE source_name = :source_name
              AND external_id = :external_id;
            """
        ),
        {
            "source_name": source_name,
            "external_id": external_id,
        },
    ).mappings().first()


def insert_external_id(
    connection,
    content_id: int,
    source_name: str,
    external_id: str,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO external_ids (
                content_id,
                source_name,
                external_id,
                source_url
            )
            VALUES (
                :content_id,
                :source_name,
                :external_id,
                NULL
            )
            ON CONFLICT DO NOTHING;
            """
        ),
        {
            "content_id": content_id,
            "source_name": source_name,
            "external_id": external_id,
        },
    )


def ensure_external_id(
    connection,
    content_id: int,
    source_name: str,
    external_id: Optional[str],
    title: str,
    stats: ImportStats,
    apply: bool,
    planned_external_ids: set[Tuple[int, str, str]],
) -> None:
    if not external_id:
        return

    existing_for_content = fetch_external_id_for_content(connection, content_id, source_name)
    if existing_for_content:
        if existing_for_content["external_id"] != external_id:
            stats.conflicts_preserved += 1
            stats.warnings.append(
                f"{title}: existing {source_name} external_id differs from preview; preserved existing value."
            )
        return

    existing_owner = fetch_external_id_owner(connection, source_name, external_id)
    if existing_owner and existing_owner["content_id"] != content_id:
        stats.conflicts_preserved += 1
        stats.warnings.append(
            f"{title}: {source_name}:{external_id} already belongs to content_id={existing_owner['content_id']}; skipped external ID insert."
        )
        return

    planned_key = (content_id, source_name, external_id)
    if planned_key in planned_external_ids:
        return
    planned_external_ids.add(planned_key)

    if apply:
        insert_external_id(connection, content_id, source_name, external_id)
    stats.external_ids_inserted += 1


def fetch_genre_by_name(connection, name: str):
    return connection.execute(
        text(
            """
            SELECT id, name
            FROM genres
            WHERE LOWER(name) = LOWER(:name);
            """
        ),
        {"name": name},
    ).mappings().first()


def insert_genre(connection, name: str) -> int:
    row = connection.execute(
        text(
            """
            INSERT INTO genres (name)
            VALUES (:name)
            ON CONFLICT (name) DO UPDATE
            SET name = EXCLUDED.name
            RETURNING id;
            """
        ),
        {"name": name},
    ).mappings().first()
    return row["id"]


def content_genre_exists(connection, content_id: int, genre_id: int) -> bool:
    row = connection.execute(
        text(
            """
            SELECT id
            FROM content_genres
            WHERE content_id = :content_id
              AND genre_id = :genre_id;
            """
        ),
        {
            "content_id": content_id,
            "genre_id": genre_id,
        },
    ).mappings().first()
    return row is not None


def insert_content_genre(connection, content_id: int, genre_id: int) -> None:
    connection.execute(
        text(
            """
            INSERT INTO content_genres (content_id, genre_id)
            VALUES (:content_id, :genre_id)
            ON CONFLICT (content_id, genre_id) DO NOTHING;
            """
        ),
        {
            "content_id": content_id,
            "genre_id": genre_id,
        },
    )


def ensure_genres(
    connection,
    content_id: int,
    record: ContentPreviewRecord,
    stats: ImportStats,
    apply: bool,
    planned_genres: Dict[str, Any],
    planned_content_genres: set[Tuple[int, Any]],
) -> None:
    for genre_name in record.genres:
        genre_key = genre_name.lower()
        genre_row = fetch_genre_by_name(connection, genre_name)

        if genre_row:
            genre_id_or_key: Any = genre_row["id"]
        elif genre_key in planned_genres:
            genre_id_or_key = planned_genres[genre_key]
        else:
            if apply:
                genre_id_or_key = insert_genre(connection, genre_name)
            else:
                genre_id_or_key = ("new_genre", genre_name)
            planned_genres[genre_key] = genre_id_or_key
            stats.genres_inserted += 1

        planned_key = (content_id, genre_id_or_key)
        if planned_key in planned_content_genres:
            continue
        planned_content_genres.add(planned_key)

        if isinstance(genre_id_or_key, int) and content_genre_exists(
            connection,
            content_id,
            genre_id_or_key,
        ):
            continue

        if apply:
            if not isinstance(genre_id_or_key, int):
                raise ContentMetadataImportError(
                    f"Could not resolve genre_id for {genre_name}."
                )
            insert_content_genre(connection, content_id, genre_id_or_key)

        stats.content_genres_inserted += 1


def fetch_series_metadata(connection, content_id: int):
    return connection.execute(
        text(
            """
            SELECT
                content_id,
                number_of_seasons,
                number_of_episodes,
                series_status,
                series_status_normalized,
                in_production,
                first_air_date,
                last_air_date,
                last_episode_air_date,
                next_episode_air_date,
                series_type,
                released_seasons_count,
                announced_seasons_count,
                next_season_number,
                next_season_air_date,
                next_season_year,
                has_announced_season,
                season_summary_note,
                source_name
            FROM content_series_metadata
            WHERE content_id = :content_id;
            """
        ),
        {"content_id": content_id},
    ).mappings().first()


def insert_series_metadata(
    connection,
    content_id: int,
    series_metadata: Dict[str, Any],
) -> None:
    params = {"content_id": content_id, **series_metadata}
    connection.execute(
        text(
            """
            INSERT INTO content_series_metadata (
                content_id,
                number_of_seasons,
                number_of_episodes,
                series_status,
                series_status_normalized,
                in_production,
                first_air_date,
                last_air_date,
                last_episode_air_date,
                next_episode_air_date,
                series_type,
                released_seasons_count,
                announced_seasons_count,
                next_season_number,
                next_season_air_date,
                next_season_year,
                has_announced_season,
                season_summary_note,
                source_name,
                last_refreshed_at
            )
            VALUES (
                :content_id,
                :number_of_seasons,
                :number_of_episodes,
                :series_status,
                :series_status_normalized,
                :in_production,
                :first_air_date,
                :last_air_date,
                :last_episode_air_date,
                :next_episode_air_date,
                :series_type,
                :released_seasons_count,
                :announced_seasons_count,
                :next_season_number,
                :next_season_air_date,
                :next_season_year,
                :has_announced_season,
                :season_summary_note,
                :source_name,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (content_id) DO NOTHING;
            """
        ),
        params,
    )


def update_series_metadata(
    connection,
    content_id: int,
    updates: Dict[str, Any],
) -> None:
    if not updates:
        return

    set_clauses = []
    params: Dict[str, Any] = {"content_id": content_id}
    for field_name, value in updates.items():
        set_clauses.append(f"{field_name} = :{field_name}")
        params[field_name] = value
    set_clauses.append("last_refreshed_at = CURRENT_TIMESTAMP")

    connection.execute(
        text(
            f"""
            UPDATE content_series_metadata
            SET {", ".join(set_clauses)}
            WHERE content_id = :content_id;
            """
        ),
        params,
    )


def ensure_series_metadata(
    connection,
    content_id: int,
    record: ContentPreviewRecord,
    stats: ImportStats,
    apply: bool,
) -> None:
    if record.content_type != "series":
        return

    if not record.series_metadata:
        stats.warnings.append(
            f"{record.title}: missing series_metadata in preview; skipped lifecycle upsert."
        )
        return

    existing = fetch_series_metadata(connection, content_id)
    if not existing:
        if apply:
            insert_series_metadata(connection, content_id, record.series_metadata)
        stats.series_metadata_inserted += 1
        record_inserted_series_metadata_row(
            stats,
            content_id if content_id > 0 else None,
            record.title,
        )
        return

    existing_values = dict(existing)
    updates = {
        field_name: record.series_metadata.get(field_name)
        for field_name in SERIES_METADATA_FIELDS
        if not values_equal(existing_values.get(field_name), record.series_metadata.get(field_name))
    }

    if updates:
        if apply:
            update_series_metadata(connection, content_id, updates)
        stats.series_metadata_updated += 1
        record_updated_series_metadata_row(
            stats,
            content_id,
            record.title,
            existing_values,
            updates,
        )
        if SEASON_SUMMARY_FIELDS.intersection(updates):
            stats.season_summary_updates += 1
        return

    stats.series_metadata_unchanged += 1


def resolve_content(
    connection,
    record: ContentPreviewRecord,
    stats: ImportStats,
) -> Optional[Dict[str, Any]]:
    row = fetch_content_by_external_id(connection, "tmdb", record.tmdb_external_id)
    if row:
        existing = dict(row)
        if existing.get("content_type") != record.content_type:
            stats.conflicts_preserved += 1
            stats.warnings.append(
                f"{record.title}: TMDb external ID matched content_id={existing['id']} with content_type={existing.get('content_type')}; skipped item."
            )
            return None
        return existing

    title_matches = fetch_content_by_title_type(
        connection,
        record.title,
        record.content_type,
    )
    if len(title_matches) > 1:
        stats.conflicts_preserved += 1
        stats.warnings.append(
            f"{record.title}: multiple content rows match title/content_type; skipped item."
        )
        return None
    if len(title_matches) == 1:
        return dict(title_matches[0])

    return None


def process_preview(
    preview: Dict[str, Any],
    preview_path: Path,
    database_url: str,
    apply: bool,
) -> ImportStats:
    stats = ImportStats(
        mode="APPLY" if apply else "DRY RUN",
        preview_path=relative_path(preview_path),
    )
    engine = create_engine(database_url)
    context = engine.begin() if apply else engine.connect()
    planned_external_ids: set[Tuple[int, str, str]] = set()
    planned_genres: Dict[str, Any] = {}
    planned_content_genres: set[Tuple[int, Any]] = set()

    with context as connection:
        for index, item in enumerate(preview.get("items", []), start=1):
            stats.items_processed += 1
            record = preview_record_from_item(item, index, stats)
            if record is None:
                continue

            existing_content = resolve_content(connection, record, stats)
            if existing_content:
                content_id = existing_content["id"]
                stats.content_matched_existing += 1
                updates = content_update_plan(existing_content, record, stats)
                if updates:
                    if apply:
                        update_content_fields(connection, content_id, updates)
                    stats.content_fields_updated += len(updates)
                    record_updated_content_row(
                        stats,
                        content_id,
                        record.title,
                        existing_content,
                        updates,
                    )
                    for field_name in updates:
                        stats.field_updates[field_name] += 1
                        if field_name == "latest_activity_date":
                            stats.latest_activity_date_updates += 1
            else:
                if apply:
                    content_id = insert_content(connection, record)
                else:
                    content_id = -record.tmdb_id
                stats.content_inserted += 1
                record_inserted_content_row(
                    stats,
                    content_id if apply else None,
                    record.title,
                )

            ensure_external_id(
                connection,
                content_id,
                "tmdb",
                record.tmdb_external_id,
                record.title,
                stats,
                apply,
                planned_external_ids,
            )
            ensure_external_id(
                connection,
                content_id,
                "imdb",
                record.imdb_id,
                record.title,
                stats,
                apply,
                planned_external_ids,
            )
            ensure_genres(
                connection,
                content_id,
                record,
                stats,
                apply,
                planned_genres,
                planned_content_genres,
            )
            ensure_series_metadata(
                connection,
                content_id,
                record,
                stats,
                apply,
            )

    return stats


def print_row_change_section(
    header: str,
    rows: List[RowChange],
    include_field_values: bool,
) -> None:
    if not rows:
        return

    print(f"\n{header}:")
    visible_rows = rows[:MAX_ROW_REPORT_ITEMS]
    for row in visible_rows:
        fields = ", ".join(field.field_name for field in row.fields)
        suffix = f": {fields}" if fields and not include_field_values else ""
        print(f"- {row.title} [id={display_content_id(row.content_id)}]{suffix}")

        if include_field_values:
            for field in row.fields:
                print(
                    f"  - {field.field_name}: "
                    f"{format_report_value(field.old_value)} -> "
                    f"{format_report_value(field.new_value)}"
                )

    remaining = len(rows) - len(visible_rows)
    if remaining > 0:
        print(f"... and {remaining} more")


def print_summary(stats: ImportStats) -> None:
    print("\nContent metadata import summary:")
    print(f"- Mode: {stats.mode}")
    print(f"- Preview path: {stats.preview_path}")
    print(f"- Items processed: {stats.items_processed}")
    print(f"- Items skipped: {stats.items_skipped}")
    print(f"- Content inserted: {stats.content_inserted}")
    print(f"- Content matched existing: {stats.content_matched_existing}")
    print(f"- Content fields updated: {stats.content_fields_updated}")
    print(f"- External IDs inserted: {stats.external_ids_inserted}")
    print(f"- Genres inserted: {stats.genres_inserted}")
    print(f"- Content genre relationships inserted: {stats.content_genres_inserted}")
    print(f"- Series metadata rows inserted: {stats.series_metadata_inserted}")
    print(f"- Series metadata rows updated: {stats.series_metadata_updated}")
    print(f"- Series metadata rows unchanged: {stats.series_metadata_unchanged}")
    print(f"- Season summary rows updated: {stats.season_summary_updates}")
    print(f"- Latest activity date updates: {stats.latest_activity_date_updates}")
    print(f"- Conflicts preserved: {stats.conflicts_preserved}")

    insert_prefix = "Would insert" if stats.mode == "DRY RUN" else "Inserted"
    update_prefix = "Would update" if stats.mode == "DRY RUN" else "Updated"
    print_row_change_section(
        f"{insert_prefix} content rows",
        stats.inserted_content_rows,
        include_field_values=False,
    )
    print_row_change_section(
        f"{update_prefix} content rows",
        stats.updated_content_rows,
        include_field_values=True,
    )
    print_row_change_section(
        f"{insert_prefix} series metadata rows",
        stats.inserted_series_metadata_rows,
        include_field_values=False,
    )
    print_row_change_section(
        f"{update_prefix} series metadata rows",
        stats.updated_series_metadata_rows,
        include_field_values=True,
    )

    if stats.field_updates:
        print("\nField update counts:")
        for field_name, count in sorted(stats.field_updates.items()):
            print(f"- {field_name}: {count}")

    if stats.content_update_messages and not stats.updated_content_rows:
        print("\nContent field update details:")
        for message in stats.content_update_messages:
            print(f"- {message}")

    if stats.skipped_fields:
        print("\nSkipped preview fields:")
        for field_name, count in sorted(stats.skipped_fields.items()):
            print(f"- {field_name}: {count}")

    if stats.warnings:
        print("\nWarnings/conflicts:")
        for warning in stats.warnings:
            print(f"- {warning}")

    if stats.mode == "DRY RUN":
        print("\nDry run only. No database changes were made.")
    else:
        print("\nApply completed successfully.")

    print("No backend, frontend, schema, or sample_data files were changed.")


def main() -> int:
    args = parse_args()
    preview_path = resolve_path(args.preview)
    database_url = os.getenv(DATABASE_URL_ENV)

    if not database_url:
        print(
            f"Missing {DATABASE_URL_ENV}. Export it before running this DB-aware import script."
        )
        print("No database changes were made.")
        return 1

    try:
        preview = load_preview(preview_path)
        stats = process_preview(preview, preview_path, database_url, args.apply)
    except (ContentMetadataImportError, SQLAlchemyError) as exc:
        print(f"Content metadata import failed: {exc}")
        if args.apply:
            print("Transaction rolled back.")
        return 1

    print_summary(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
