#!/usr/bin/env python3
"""
Generate a basic metadata reconciliation report.

This script is analysis-only:
- It does not connect to PostgreSQL.
- It does not call TMDb or any external API.
- It does not mutate backend, frontend, schema, or seed data.
- It writes docs/basic_metadata_reconciliation_report.md and an optional JSON artifact.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from analytics.scripts.common.paths import REPO_ROOT
SEED_PATH = REPO_ROOT / "backend" / "sample_data.sql"
PREVIEW_PATH = REPO_ROOT / "analytics" / "processed" / "tmdb" / "sample_mapping_preview.json"
POLICY_PATH = REPO_ROOT / "docs" / "metadata_normalization_plan.md"
REPORT_PATH = REPO_ROOT / "docs" / "basic_metadata_reconciliation_report.md"
JSON_OUTPUT_PATH = REPO_ROOT / "analytics" / "processed" / "tmdb" / "basic_metadata_reconciliation.json"


CONTENT_COLUMNS = [
    "tmdb_id",
    "title",
    "content_type",
    "overview",
    "poster_url",
    "backdrop_url",
    "release_date",
    "year",
    "runtime",
    "language",
    "status",
    "age_rating",
]


GENRE_MAP = {
    "Science Fiction": ["Sci-Fi"],
    "Sci-Fi & Fantasy": ["Sci-Fi", "Fantasy"],
    "Action & Adventure": ["Action", "Adventure"],
    "Action": ["Action"],
    "Adventure": ["Adventure"],
    "Animation": ["Animation"],
    "Comedy": ["Comedy"],
    "Crime": ["Crime"],
    "Drama": ["Drama"],
    "Fantasy": ["Fantasy"],
    "Horror": ["Horror"],
    "Mystery": ["Mystery"],
    "Romance": ["Romance"],
    "Thriller": ["Thriller"],
}


LANGUAGE_MAP = {
    "en": "English",
    "ko": "Korean",
    "de": "German",
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


VALID_ACTIONS = {
    "keep_local",
    "update_from_provider",
    "add_provider_value",
    "keep_local_and_preserve_provider",
    "needs_manual_review",
    "needs_future_schema",
    "provider_signal_only",
    "no_action",
}


@dataclass
class SeedContent:
    tmdb_id: int
    title: str
    content_type: str
    overview: str
    poster_url: str
    backdrop_url: str
    release_date: str
    year: int
    runtime: int | None
    language: str
    status: str
    age_rating: str
    genres: list[str] = field(default_factory=list)


def extract_parenthesized_chunks(text: str) -> list[str]:
    chunks: list[str] = []
    in_string = False
    level = 0
    start: int | None = None
    index = 0

    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if char == "'":
            if in_string and next_char == "'":
                index += 2
                continue
            in_string = not in_string
        elif not in_string:
            if char == "(":
                if level == 0:
                    start = index + 1
                level += 1
            elif char == ")":
                level -= 1
                if level == 0 and start is not None:
                    chunks.append(text[start:index])
                    start = None

        index += 1

    return chunks


def split_sql_values(chunk: str) -> list[str]:
    values: list[str] = []
    current: list[str] = []
    in_string = False
    index = 0

    while index < len(chunk):
        char = chunk[index]
        next_char = chunk[index + 1] if index + 1 < len(chunk) else ""

        if char == "'":
            current.append(char)
            if in_string and next_char == "'":
                current.append(next_char)
                index += 2
                continue
            in_string = not in_string
        elif char == "," and not in_string:
            values.append("".join(current).strip())
            current = []
        else:
            current.append(char)

        index += 1

    values.append("".join(current).strip())
    return values


def parse_sql_value(raw_value: str) -> Any:
    value = raw_value.strip()
    if value.upper() == "NULL":
        return None
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def parse_seed_content(sql: str) -> dict[int, SeedContent]:
    match = re.search(
        r"INSERT INTO content\s*\((?P<columns>.*?)\)\s*VALUES(?P<values>.*?)\nON CONFLICT \(tmdb_id\)",
        sql,
        flags=re.DOTALL,
    )
    if not match:
        raise RuntimeError("Could not locate INSERT INTO content block in sample_data.sql.")

    columns = [column.strip() for column in match.group("columns").split(",")]
    if columns != CONTENT_COLUMNS:
        raise RuntimeError("Unexpected content column order in sample_data.sql.")

    seed_by_id: dict[int, SeedContent] = {}
    for chunk in extract_parenthesized_chunks(match.group("values")):
        values = [parse_sql_value(value) for value in split_sql_values(chunk)]
        row = dict(zip(columns, values))
        seed = SeedContent(**row)
        seed_by_id[seed.tmdb_id] = seed

    return seed_by_id


def parse_seed_genres(sql: str) -> dict[int, list[str]]:
    match = re.search(
        r"INSERT INTO content_genres.*?FROM\s*\(\s*VALUES(?P<values>.*?)\) AS seed\(tmdb_id, genre_name\)",
        sql,
        flags=re.DOTALL,
    )
    if not match:
        raise RuntimeError("Could not locate content_genres seed block in sample_data.sql.")

    genres_by_id: dict[int, list[str]] = defaultdict(list)
    for chunk in extract_parenthesized_chunks(match.group("values")):
        tmdb_id, genre = [parse_sql_value(value) for value in split_sql_values(chunk)]
        genres_by_id[int(tmdb_id)].append(str(genre))

    return dict(genres_by_id)


def load_seed_content() -> dict[int, SeedContent]:
    sql = SEED_PATH.read_text(encoding="utf-8")
    seed_by_id = parse_seed_content(sql)
    genres_by_id = parse_seed_genres(sql)
    for tmdb_id, seed in seed_by_id.items():
        seed.genres = genres_by_id.get(tmdb_id, [])
    return seed_by_id


def load_preview_items() -> dict[int, dict[str, Any]]:
    data = json.loads(PREVIEW_PATH.read_text(encoding="utf-8"))
    return {int(item["tmdb_id"]): item for item in data.get("items", [])}


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def media_type_to_content_type(media_type: str | None) -> str | None:
    if media_type == "movie":
        return "movie"
    if media_type == "tv":
        return "series"
    return None


def normalize_provider_genres(genres: list[str]) -> tuple[list[str], list[str]]:
    normalized: list[str] = []
    warnings: list[str] = []

    for genre in genres:
        mapped = GENRE_MAP.get(genre)
        if not mapped:
            warnings.append(f"Unmapped provider genre: {genre}")
            continue
        for local_genre in mapped:
            if local_genre not in normalized:
                normalized.append(local_genre)

    return normalized, warnings


def normalize_language(code: str | None) -> tuple[str | None, str | None]:
    if not code:
        return None, "Missing provider language code."
    mapped = LANGUAGE_MAP.get(code)
    if not mapped:
        return None, f"Unmapped provider language code: {code}"
    return mapped, None


def normalize_status(status: str | None) -> tuple[str | None, str | None]:
    if not status:
        return None, "Missing provider status."
    mapped = STATUS_MAP.get(status)
    if not mapped:
        return "Unknown", f"Unmapped provider status: {status}"
    return mapped, None


def action_detail(action: str, local: Any, provider: Any, note: str = "") -> dict[str, Any]:
    if action not in VALID_ACTIONS:
        raise ValueError(f"Invalid reconciliation action: {action}")
    return {
        "action": action,
        "local": local,
        "provider": provider,
        "note": note,
    }


def reconcile_title(seed: SeedContent, preview: dict[str, Any] | None) -> dict[str, Any]:
    if preview is None:
        return {
            "tmdb_id": seed.tmdb_id,
            "title": seed.title,
            "content_type": seed.content_type,
            "field_actions": {
                "preview": action_detail(
                    "needs_manual_review",
                    seed.tmdb_id,
                    None,
                    "No provider preview item matched this seeded tmdb_id.",
                )
            },
            "proposed_genre_additions": [],
            "retained_local_genres": seed.genres,
            "normalized_provider_genres": [],
            "normalized_language": None,
            "normalized_status": None,
            "notes": ["Missing provider preview item."],
        }

    notes: list[str] = []
    field_actions: dict[str, dict[str, Any]] = {}

    provider_title = preview.get("title")
    if normalize_title(seed.title) == normalize_title(provider_title):
        field_actions["title"] = action_detail("no_action", seed.title, provider_title)
    else:
        field_actions["title"] = action_detail(
            "needs_manual_review",
            seed.title,
            provider_title,
            "Title mismatch should be reviewed before any update.",
        )
        notes.append("Title mismatch.")

    provider_content_type = media_type_to_content_type(preview.get("media_type"))
    if seed.content_type == provider_content_type:
        field_actions["content_type"] = action_detail(
            "no_action",
            seed.content_type,
            provider_content_type,
        )
    else:
        field_actions["content_type"] = action_detail(
            "needs_manual_review",
            seed.content_type,
            provider_content_type,
            "Provider media type does not map cleanly to local content_type.",
        )
        notes.append("Content type/media type mismatch.")

    provider_overview = preview.get("overview")
    if provider_overview and provider_overview != seed.overview:
        field_actions["overview"] = action_detail(
            "keep_local_and_preserve_provider",
            f"{len(seed.overview)} chars",
            f"{len(provider_overview)} chars",
            "Keep curated overview for display; preserve provider overview for future review.",
        )
    elif provider_overview:
        field_actions["overview"] = action_detail("no_action", "present", "present")
    else:
        field_actions["overview"] = action_detail(
            "keep_local",
            "present",
            None,
            "Provider overview missing.",
        )

    provider_release_date = preview.get("release_date")
    if seed.release_date == provider_release_date:
        field_actions["release_date"] = action_detail("no_action", seed.release_date, provider_release_date)
    elif not seed.release_date and provider_release_date:
        field_actions["release_date"] = action_detail(
            "add_provider_value",
            seed.release_date,
            provider_release_date,
            "Provider has release date missing locally.",
        )
    else:
        field_actions["release_date"] = action_detail(
            "needs_manual_review",
            seed.release_date,
            provider_release_date,
            "Release dates can differ by source/region; preserve provider value for review.",
        )
        notes.append("Release date differs.")

    provider_year = preview.get("year")
    if seed.year == provider_year:
        field_actions["year"] = action_detail("no_action", seed.year, provider_year)
    elif not seed.year and provider_year:
        field_actions["year"] = action_detail(
            "add_provider_value",
            seed.year,
            provider_year,
            "Provider has year missing locally.",
        )
    else:
        field_actions["year"] = action_detail(
            "needs_manual_review",
            seed.year,
            provider_year,
            "Year follows release date and should be reviewed with it.",
        )

    provider_runtime = preview.get("runtime")
    if seed.content_type == "series" and provider_runtime is None:
        field_actions["runtime"] = action_detail(
            "keep_local",
            seed.runtime,
            provider_runtime,
            "Never replace known representative series runtime with null.",
        )
    elif seed.runtime == provider_runtime:
        field_actions["runtime"] = action_detail("no_action", seed.runtime, provider_runtime)
    elif seed.runtime is None and provider_runtime is not None:
        field_actions["runtime"] = action_detail(
            "update_from_provider",
            seed.runtime,
            provider_runtime,
            "Provider runtime can fill missing local runtime after validation.",
        )
    elif seed.content_type == "movie" and isinstance(seed.runtime, int) and isinstance(provider_runtime, int):
        diff = abs(seed.runtime - provider_runtime)
        action = "needs_manual_review" if diff <= 2 else "needs_manual_review"
        field_actions["runtime"] = action_detail(
            action,
            seed.runtime,
            provider_runtime,
            f"Movie runtime differs by {diff} minute(s); preserve provider value for review.",
        )
        notes.append("Runtime differs.")
    else:
        field_actions["runtime"] = action_detail(
            "needs_manual_review",
            seed.runtime,
            provider_runtime,
            "Runtime conflict cannot be safely resolved automatically.",
        )
        notes.append("Runtime differs.")

    normalized_language, language_warning = normalize_language(preview.get("original_language"))
    if language_warning:
        field_actions["language"] = action_detail(
            "needs_manual_review",
            seed.language,
            preview.get("original_language"),
            language_warning,
        )
        notes.append(language_warning)
    elif seed.language == normalized_language:
        field_actions["language"] = action_detail(
            "no_action",
            seed.language,
            preview.get("original_language"),
            f"Provider code normalizes to {normalized_language}.",
        )
    elif not seed.language and normalized_language:
        field_actions["language"] = action_detail(
            "update_from_provider",
            seed.language,
            normalized_language,
            "Provider language maps to readable local value.",
        )
    else:
        field_actions["language"] = action_detail(
            "needs_manual_review",
            seed.language,
            normalized_language,
            "Normalized provider language differs from local value.",
        )
        notes.append("Language differs after normalization.")

    normalized_status, status_warning = normalize_status(preview.get("status"))
    if status_warning:
        field_actions["status"] = action_detail(
            "needs_manual_review",
            seed.status,
            preview.get("status"),
            status_warning,
        )
        notes.append(status_warning)
    elif seed.status == normalized_status:
        field_actions["status"] = action_detail(
            "no_action",
            seed.status,
            preview.get("status"),
            f"Provider status normalizes to {normalized_status}.",
        )
    else:
        field_actions["status"] = action_detail(
            "needs_manual_review",
            seed.status,
            normalized_status,
            "Normalized provider status differs from current local display value.",
        )
        notes.append("Status differs after normalization.")

    provider_genres = list(preview.get("genres") or [])
    normalized_provider_genres, genre_warnings = normalize_provider_genres(provider_genres)
    notes.extend(genre_warnings)
    local_genres = set(seed.genres)
    provider_genre_set = set(normalized_provider_genres)
    proposed_additions = sorted(provider_genre_set - local_genres)
    retained_local = sorted(local_genres - provider_genre_set)
    if genre_warnings:
        genre_action = "needs_manual_review"
        genre_note = "; ".join(genre_warnings)
    elif proposed_additions and retained_local:
        genre_action = "keep_local_and_preserve_provider"
        genre_note = "Provider proposes additions; local genres should be retained unless reviewed."
    elif proposed_additions:
        genre_action = "add_provider_value"
        genre_note = "Provider has normalized genres missing locally; propose additions."
    elif retained_local:
        genre_action = "keep_local_and_preserve_provider"
        genre_note = "Local genres are useful decision-support metadata not present in provider genres."
    else:
        genre_action = "no_action"
        genre_note = "Normalized provider genres match local genres."
    field_actions["genres"] = action_detail(
        genre_action,
        seed.genres,
        normalized_provider_genres,
        genre_note,
    )

    if seed.poster_url == preview.get("poster_url"):
        field_actions["poster_url"] = action_detail("no_action", seed.poster_url, preview.get("poster_url"))
    else:
        field_actions["poster_url"] = action_detail(
            "needs_manual_review",
            seed.poster_url,
            preview.get("poster_url"),
            "Poster URL should already match processed preview.",
        )
        notes.append("Poster URL mismatch.")

    if seed.backdrop_url == preview.get("backdrop_url"):
        field_actions["backdrop_url"] = action_detail("no_action", seed.backdrop_url, preview.get("backdrop_url"))
    else:
        field_actions["backdrop_url"] = action_detail(
            "needs_manual_review",
            seed.backdrop_url,
            preview.get("backdrop_url"),
            "Backdrop URL should already match processed preview.",
        )
        notes.append("Backdrop URL mismatch.")

    imdb_id = preview.get("imdb_id")
    if imdb_id:
        field_actions["external_ids"] = action_detail(
            "no_action",
            {"tmdb": str(seed.tmdb_id), "imdb": imdb_id},
            {"tmdb": str(preview.get("tmdb_id")), "imdb": imdb_id},
            "Expected TMDb and IMDb external IDs are available.",
        )
    else:
        field_actions["external_ids"] = action_detail(
            "needs_manual_review",
            {"tmdb": str(seed.tmdb_id)},
            {"tmdb": str(preview.get("tmdb_id")), "imdb": None},
            "Provider preview is missing IMDb ID.",
        )
        notes.append("Missing IMDb ID.")

    field_actions["age_rating"] = action_detail(
        "keep_local",
        seed.age_rating,
        None,
        "TMDb preview does not provide the local age_rating field; future certification source needed.",
    )

    for signal in ["vote_average", "vote_count", "popularity"]:
        field_actions[signal] = action_detail(
            "provider_signal_only",
            None,
            preview.get(signal),
            "Provider-specific analytics signal; do not write into content_summary or ratings directly.",
        )

    field_actions["cast_crew"] = action_detail(
        "needs_future_schema",
        None,
        {
            "top_cast_names": preview.get("top_cast_names") or [],
            "director_or_creator_names": preview.get("director_or_creator_names") or [],
        },
        "Useful metadata exists but requires person/role schema before import/display.",
    )

    return {
        "tmdb_id": seed.tmdb_id,
        "title": seed.title,
        "content_type": seed.content_type,
        "field_actions": field_actions,
        "proposed_genre_additions": proposed_additions,
        "retained_local_genres": retained_local,
        "normalized_provider_genres": normalized_provider_genres,
        "normalized_language": normalized_language,
        "normalized_status": normalized_status,
        "notes": notes,
    }


def markdown_escape(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def format_list(values: list[str] | None) -> str:
    return ", ".join(values or []) if values else "-"


def action_counts(items: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in items:
        for action in item["field_actions"].values():
            counts[action["action"]] += 1
    return counts


def count_items_with_action(items: list[dict[str, Any]], action_name: str) -> int:
    return sum(
        1
        for item in items
        if any(action["action"] == action_name for action in item["field_actions"].values())
    )


def build_field_summary(items: list[dict[str, Any]]) -> dict[str, Counter[str]]:
    summary: dict[str, Counter[str]] = defaultdict(Counter)
    for item in items:
        for field, action in item["field_actions"].items():
            summary[field][action["action"]] += 1
    return dict(summary)


def build_report(
    generated_at: str,
    seed_by_id: dict[int, SeedContent],
    preview_by_id: dict[int, dict[str, Any]],
    items: list[dict[str, Any]],
    warnings: list[str],
) -> str:
    matched_titles = sum(1 for tmdb_id in seed_by_id if tmdb_id in preview_by_id)
    manual_review_items = count_items_with_action(items, "needs_manual_review")
    proposed_genre_additions = sum(len(item["proposed_genre_additions"]) for item in items)
    field_summary = build_field_summary(items)
    counts = action_counts(items)

    lines = [
        "# Basic Metadata Reconciliation Report",
        "",
        f"Generated at: `{generated_at}`",
        "",
        "## 1. Purpose",
        "",
        "This report compares current local seed metadata with the processed TMDb preview and classifies what should happen next for each basic metadata field.",
        "",
        "It is analysis-only. No database changes were made, no backend or frontend code changed, and no external APIs were called.",
        "",
        "Provider metadata is preserved and reviewed, not ignored. Normalization determines what can safely become user-facing local metadata later.",
        "",
        "## 2. Data Sources",
        "",
        f"- Seed data: `{SEED_PATH.relative_to(REPO_ROOT)}`",
        f"- Processed provider preview: `{PREVIEW_PATH.relative_to(REPO_ROOT)}`",
        f"- Policy reference: `{POLICY_PATH.relative_to(REPO_ROOT)}`",
        "",
        "## 3. Summary Counts",
        "",
        f"- Total seeded titles: {len(seed_by_id)}",
        f"- Total preview titles: {len(preview_by_id)}",
        f"- Matched titles: {matched_titles}",
        f"- Titles with manual review items: {manual_review_items}",
        f"- Proposed provider genre additions: {proposed_genre_additions}",
        f"- Warnings: {len(warnings)}",
        "",
        "Action totals:",
        "",
    ]

    for action_name in sorted(VALID_ACTIONS):
        lines.append(f"- `{action_name}`: {counts.get(action_name, 0)}")

    lines.extend(
        [
            "",
            "## 4. Normalization Rules Used",
            "",
            "Genre mapping:",
            "",
        ]
    )
    for provider_genre, local_genres in GENRE_MAP.items():
        lines.append(f"- `{provider_genre}` -> {', '.join(local_genres)}")

    lines.extend(["", "Language mapping:", ""])
    for code, value in LANGUAGE_MAP.items():
        lines.append(f"- `{code}` -> `{value}`")

    lines.extend(["", "Status mapping:", ""])
    for provider_status, local_status in STATUS_MAP.items():
        lines.append(f"- `{provider_status}` -> `{local_status}`")

    lines.extend(
        [
            "",
            "Unknown provider values are not applied directly to normalized fields. They are captured as warnings and preserved for review.",
            "",
            "## 5. Field-Level Recommendation Summary",
            "",
            "| Field | Action Counts | Recommendation |",
            "| --- | --- | --- |",
        ]
    )

    recommendations = {
        "title": "No update unless mismatch appears.",
        "content_type": "Keep local movie/series model; review mismatches.",
        "overview": "Keep curated local overview and preserve provider overview.",
        "release_date": "Review provider/local date differences before update.",
        "year": "Review with release date.",
        "runtime": "Display known runtime; never overwrite with null.",
        "language": "Map known provider codes to readable display values.",
        "status": "Normalize provider status, then review current seed differences.",
        "genres": "Use provider genres as normalized enrichment, not destructive replacement.",
        "poster_url": "Already aligned; review only if mismatch appears.",
        "backdrop_url": "Already aligned; review only if mismatch appears.",
        "external_ids": "Already safe as identity data.",
        "age_rating": "Keep local value until certification source exists.",
        "vote_average": "Provider signal only.",
        "vote_count": "Provider signal only.",
        "popularity": "Provider signal only.",
        "cast_crew": "Needs person/role schema.",
    }

    for field in sorted(field_summary):
        count_text = ", ".join(
            f"{action}: {count}" for action, count in sorted(field_summary[field].items())
        )
        lines.append(
            f"| `{field}` | {markdown_escape(count_text)} | {markdown_escape(recommendations.get(field, 'Review before import.'))} |"
        )

    lines.extend(
        [
            "",
            "## 6. Title-by-Title Reconciliation Table",
            "",
            "| Title | TMDb ID | Type | Manual Review? | Proposed Genre Additions | Retained Local Genres | Runtime Action | Status Action | Notes |",
            "| --- | ---: | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for item in items:
        has_manual_review = any(
            action["action"] == "needs_manual_review"
            for action in item["field_actions"].values()
        )
        runtime_action = item["field_actions"]["runtime"]["action"]
        status_action = item["field_actions"]["status"]["action"]
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(item["title"]),
                    str(item["tmdb_id"]),
                    item["content_type"],
                    "yes" if has_manual_review else "no",
                    markdown_escape(format_list(item["proposed_genre_additions"])),
                    markdown_escape(format_list(item["retained_local_genres"])),
                    runtime_action,
                    status_action,
                    markdown_escape("; ".join(item["notes"]) if item["notes"] else "OK"),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 7. Genre Reconciliation Details",
            "",
            "| Title | Local Genres To Retain | Normalized Provider Genres | Proposed Additions | Action |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in items:
        genre_action = item["field_actions"]["genres"]["action"]
        lines.append(
            f"| {markdown_escape(item['title'])} | {markdown_escape(format_list(item['retained_local_genres']))} | {markdown_escape(format_list(item['normalized_provider_genres']))} | {markdown_escape(format_list(item['proposed_genre_additions']))} | `{genre_action}` |"
        )

    lines.extend(
        [
            "",
            "No local genres should be silently removed. Provider genres can propose additions after normalization, while local decision-support genres should remain until reviewed.",
            "",
            "## 8. Runtime Reconciliation Details",
            "",
            "| Title | Local Runtime | Provider Runtime | Action | Note |",
            "| --- | ---: | ---: | --- | --- |",
        ]
    )
    for item in items:
        action = item["field_actions"]["runtime"]
        lines.append(
            f"| {markdown_escape(item['title'])} | {markdown_escape(action['local'])} | {markdown_escape(action['provider'])} | `{action['action']}` | {markdown_escape(action['note'])} |"
        )

    lines.extend(
        [
            "",
            "## 9. Language and Status Reconciliation Details",
            "",
            "| Title | Local Language | Normalized Language | Language Action | Local Status | Normalized Status | Status Action |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in items:
        language_action = item["field_actions"]["language"]
        status_action = item["field_actions"]["status"]
        lines.append(
            f"| {markdown_escape(item['title'])} | {markdown_escape(language_action['local'])} | {markdown_escape(item['normalized_language'])} | `{language_action['action']}` | {markdown_escape(status_action['local'])} | {markdown_escape(item['normalized_status'])} | `{status_action['action']}` |"
        )

    lines.extend(
        [
            "",
            "## 10. Metadata Preservation Notes",
            "",
            "- Provider metadata should not blindly overwrite local fields.",
            "- Provider metadata should also not be silently discarded.",
            "- Unknown/unmapped values should be preserved in reports, JSON artifacts, import logs, or future provenance tables.",
            "- Conflicting values should be reviewed, not ignored.",
            "- Local curated values and provider values should remain traceable.",
            "",
            "## 11. Safe Future Update Candidates",
            "",
            "- Missing normalized provider genres can be proposed for addition after review.",
            "- Series statuses such as `Ended` and `Ongoing` are likely useful but should be reviewed before changing seed data.",
            "- Missing local language values, if any appear later, can be filled from normalized provider codes.",
            "- Missing local movie runtime can be filled from a verified provider value.",
            "",
            "## 12. Fields Not To Update Yet",
            "",
            "- Curated overview text should not be overwritten.",
            "- Existing runtime should not be replaced by null.",
            "- Local genres should not be destructively removed.",
            "- `age_rating` needs a certification/source strategy before provider updates.",
            "- Cast/crew needs person/role schema before import or display.",
            "- TMDb vote average, vote count, and popularity are provider-specific signals only.",
            "- Ratings, summaries, verdicts, and InsightStream scores are out of scope for this metadata phase.",
            "",
            "## 13. Recommended Next Task",
            "",
            "Create a person/cast/crew schema plan, then return to a normalized metadata import plan that can apply safe updates with review/provenance support.",
            "",
        ]
    )

    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    parse_args(argv)
    policy_text = POLICY_PATH.read_text(encoding="utf-8")
    if "Metadata Preservation Rule" not in policy_text:
        raise RuntimeError("Policy reference does not include the Metadata Preservation Rule section.")

    seed_by_id = load_seed_content()
    preview_by_id = load_preview_items()
    generated_at = datetime.now(timezone.utc).isoformat()

    items = [
        reconcile_title(seed_by_id[tmdb_id], preview_by_id.get(tmdb_id))
        for tmdb_id in sorted(seed_by_id)
    ]

    warnings: list[str] = []
    for item in items:
        for note in item["notes"]:
            warnings.append(f"{item['title']}: {note}")

    payload = {
        "generated_at": generated_at,
        "source_preview_path": str(PREVIEW_PATH.relative_to(REPO_ROOT)),
        "source_seed_path": str(SEED_PATH.relative_to(REPO_ROOT)),
        "policy_reference_path": str(POLICY_PATH.relative_to(REPO_ROOT)),
        "total_titles": len(seed_by_id),
        "matched_titles": sum(1 for tmdb_id in seed_by_id if tmdb_id in preview_by_id),
        "warnings": warnings,
        "items": items,
    }

    JSON_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    report = build_report(
        generated_at=generated_at,
        seed_by_id=seed_by_id,
        preview_by_id=preview_by_id,
        items=items,
        warnings=warnings,
    )
    REPORT_PATH.write_text(report, encoding="utf-8")

    manual_review_items = count_items_with_action(items, "needs_manual_review")
    proposed_genre_additions = sum(len(item["proposed_genre_additions"]) for item in items)

    print(f"Report written: {REPORT_PATH.relative_to(REPO_ROOT)}")
    print(f"JSON written: {JSON_OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print(f"Total matched titles: {payload['matched_titles']}")
    print(f"Total manual review items: {manual_review_items}")
    print(f"Total provider values proposed for addition: {proposed_genre_additions}")
    print(f"Total warnings: {len(warnings)}")
    print("Suggested next task: create a person/cast/crew schema plan before metadata import.")
    print("No database, API, frontend, schema, or sample_data changes were made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
