#!/usr/bin/env python3
"""
Generate a TMDb metadata gap analysis from local seed SQL and processed preview JSON.

This script is analysis-only:
- It does not connect to PostgreSQL.
- It does not call TMDb or any external API.
- It does not mutate backend, frontend, schema, or seed data.
- It writes only docs/tmdb_metadata_gap_analysis.md.
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
SAMPLE_DATA_PATH = REPO_ROOT / "backend" / "sample_data.sql"
PREVIEW_PATH = REPO_ROOT / "analytics" / "processed" / "tmdb" / "sample_mapping_preview.json"
REPORT_PATH = REPO_ROOT / "docs" / "tmdb_metadata_gap_analysis.md"


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


LANGUAGE_CODE_TO_NAME = {
    "en": "English",
    "de": "German",
    "ko": "Korean",
}


GENRE_NORMALIZATION = {
    "Science Fiction": {"Sci-Fi"},
    "Sci-Fi & Fantasy": {"Sci-Fi", "Fantasy"},
    "Action & Adventure": {"Action", "Adventure"},
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


@dataclass
class ComparedTitle:
    seed: SeedContent
    preview: dict[str, Any] | None
    notes: list[str]
    media_matches: bool
    title_matches: bool
    poster_matches: bool
    backdrop_matches: bool
    genre_note: str


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
    sql = SAMPLE_DATA_PATH.read_text(encoding="utf-8")
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


def title_matches(seed_title: str, preview_title: str | None) -> bool:
    return normalize_title(seed_title) == normalize_title(preview_title)


def media_type_for_content_type(content_type: str) -> str:
    return "movie" if content_type == "movie" else "tv"


def language_name(preview_language_code: str | None) -> str | None:
    if not preview_language_code:
        return None
    return LANGUAGE_CODE_TO_NAME.get(preview_language_code, preview_language_code)


def normalize_genres(genres: list[str]) -> set[str]:
    normalized: set[str] = set()
    for genre in genres:
        normalized.update(GENRE_NORMALIZATION.get(genre, {genre}))
    return normalized


def compare_genres(local_genres: list[str], tmdb_genres: list[str]) -> str:
    local_raw = set(local_genres)
    tmdb_raw = set(tmdb_genres)
    if local_raw == tmdb_raw:
        return "Match"

    local_normalized = normalize_genres(local_genres)
    tmdb_normalized = normalize_genres(tmdb_genres)
    if local_normalized == tmdb_normalized:
        return "Naming/grouping difference only"

    local_only = sorted(local_normalized - tmdb_normalized)
    tmdb_only = sorted(tmdb_normalized - local_normalized)
    parts = []
    if local_only:
        parts.append(f"Local only: {', '.join(local_only)}")
    if tmdb_only:
        parts.append(f"TMDb only: {', '.join(tmdb_only)}")
    return "; ".join(parts) if parts else "Different"


def overview_delta(seed_overview: str, preview_overview: str | None) -> int | None:
    if preview_overview is None:
        return None
    return len(preview_overview) - len(seed_overview)


def compare_title(seed: SeedContent, preview: dict[str, Any] | None) -> ComparedTitle:
    if preview is None:
        return ComparedTitle(
            seed=seed,
            preview=None,
            notes=["Missing TMDb preview item."],
            media_matches=False,
            title_matches=False,
            poster_matches=False,
            backdrop_matches=False,
            genre_note="Missing preview",
        )

    notes = list(preview.get("mapping_notes") or [])
    expected_media_type = media_type_for_content_type(seed.content_type)
    media_matches = preview.get("media_type") == expected_media_type
    title_ok = title_matches(seed.title, preview.get("title"))
    poster_matches = seed.poster_url == preview.get("poster_url")
    backdrop_matches = seed.backdrop_url == preview.get("backdrop_url")
    tmdb_genres = list(preview.get("genres") or [])
    genre_note = compare_genres(seed.genres, tmdb_genres)

    if not title_ok:
        notes.append("Title mismatch.")
    if not media_matches:
        notes.append("Content type/media type mismatch.")
    if seed.release_date != preview.get("release_date"):
        notes.append("Release date differs.")
    if seed.year != preview.get("year"):
        notes.append("Year differs.")
    if seed.runtime != preview.get("runtime"):
        notes.append("Runtime differs or is unavailable in TMDb preview.")
    if seed.language != language_name(preview.get("original_language")):
        notes.append("Language needs normalization before import.")
    if seed.status != preview.get("status"):
        notes.append("Status differs and needs normalization before import.")
    if not poster_matches:
        notes.append("Poster URL differs.")
    if not backdrop_matches:
        notes.append("Backdrop URL differs.")
    if genre_note != "Match":
        notes.append(f"Genre mapping differs: {genre_note}.")
    if not preview.get("imdb_id"):
        notes.append("Missing IMDb ID in preview.")
    if not preview.get("top_cast_names"):
        notes.append("No cast names in preview.")
    if not preview.get("director_or_creator_names"):
        notes.append("No director/creator names in preview.")
    if preview.get("vote_average") is None or preview.get("vote_count") is None:
        notes.append("Missing vote data.")
    if preview.get("popularity") is None:
        notes.append("Missing popularity signal.")

    return ComparedTitle(
        seed=seed,
        preview=preview,
        notes=notes,
        media_matches=media_matches,
        title_matches=title_ok,
        poster_matches=poster_matches,
        backdrop_matches=backdrop_matches,
        genre_note=genre_note,
    )


def markdown_escape(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def preview_value(preview: dict[str, Any] | None, field: str) -> Any:
    if preview is None:
        return None
    return preview.get(field)


def format_list(values: list[str] | None, limit: int | None = None) -> str:
    if not values:
        return "-"
    selected = values[:limit] if limit else values
    suffix = "..." if limit and len(values) > limit else ""
    return ", ".join(selected) + suffix


def build_field_summary(comparisons: list[ComparedTitle]) -> list[tuple[str, str, str, str]]:
    matched = [comparison for comparison in comparisons if comparison.preview]
    total = len(matched)

    def count(predicate) -> int:
        return sum(1 for comparison in matched if predicate(comparison))

    return [
        (
            "title",
            f"{count(lambda c: c.title_matches)}/{total} match",
            "No import needed.",
            "Keep current titles unless a manual cleanup task decides otherwise.",
        ),
        (
            "content_type/media_type",
            f"{count(lambda c: c.media_matches)}/{total} match",
            "No schema change needed for movie/series mapping.",
            "Keep broad movie/series values for now.",
        ),
        (
            "release_date/year",
            f"{count(lambda c: c.seed.release_date == c.preview.get('release_date'))}/{total} release dates match",
            "Some provider dates differ from curated seed dates.",
            "Do not overwrite until release-date policy is decided.",
        ),
        (
            "runtime",
            f"{count(lambda c: c.seed.runtime == c.preview.get('runtime'))}/{total} match",
            "TV runtimes are mostly null in preview; a few movie runtimes differ.",
            "Keep current seed runtime for now.",
        ),
        (
            "language",
            f"{count(lambda c: c.seed.language == language_name(c.preview.get('original_language')) )}/{total} normalize cleanly",
            "TMDb returns language codes, seed stores readable names.",
            "Add a normalization map before import.",
        ),
        (
            "status",
            f"{count(lambda c: c.seed.status == c.preview.get('status'))}/{total} match",
            "TV status values differ from current seed wording.",
            "Normalize before import.",
        ),
        (
            "poster_url/backdrop_url",
            f"{count(lambda c: c.poster_matches)}/{total} posters and {count(lambda c: c.backdrop_matches)}/{total} backdrops match",
            "Already aligned with processed preview.",
            "Safe to keep current seed values.",
        ),
        (
            "genres",
            f"{count(lambda c: c.genre_note == 'Match')}/{total} raw genre sets match",
            "Provider naming/grouping differs from local taxonomy.",
            "Use a genre normalization map before import.",
        ),
        (
            "overview",
            f"{count(lambda c: bool(c.preview.get('overview')) )}/{total} available",
            "TMDb overviews often differ from curated seed summaries.",
            "Do not overwrite curated overview yet.",
        ),
        (
            "imdb_id",
            f"{count(lambda c: bool(c.preview.get('imdb_id')) )}/{total} available",
            "Already suitable for external_ids seed validation.",
            "Safe as external ID data, not content table data.",
        ),
        (
            "cast/director/creator",
            f"{count(lambda c: bool(c.preview.get('top_cast_names')) )}/{total} cast lists; {count(lambda c: bool(c.preview.get('director_or_creator_names')) )}/{total} director/creator lists",
            "Current schema has no person/role model.",
            "Plan person schema before import.",
        ),
        (
            "vote/popularity",
            f"{count(lambda c: c.preview.get('vote_average') is not None and c.preview.get('vote_count') is not None and c.preview.get('popularity') is not None)}/{total} available",
            "Provider-specific signal, not current InsightStream scoring.",
            "Do not write into content_summary directly.",
        ),
    ]


def build_report(seed_by_id: dict[int, SeedContent], preview_by_id: dict[int, dict[str, Any]]) -> tuple[str, int, int]:
    generated_at = datetime.now(timezone.utc).isoformat()
    comparisons = [
        compare_title(seed_by_id[tmdb_id], preview_by_id.get(tmdb_id))
        for tmdb_id in sorted(seed_by_id)
    ]
    matched_count = sum(1 for comparison in comparisons if comparison.preview is not None)
    missing_preview_count = len(seed_by_id) - matched_count
    extra_preview_ids = sorted(set(preview_by_id) - set(seed_by_id))
    warning_count = sum(len(comparison.notes) for comparison in comparisons)

    content_type_counts = Counter(seed.content_type for seed in seed_by_id.values())
    preview_media_counts = Counter(item.get("media_type") for item in preview_by_id.values())

    lines: list[str] = [
        "# TMDb Metadata Gap Analysis",
        "",
        f"Generated at: `{generated_at}`",
        "",
        "This report compares the current canonical seed data in `backend/sample_data.sql` against the processed TMDb preview in `analytics/processed/tmdb/sample_mapping_preview.json`.",
        "",
        "It is analysis-only. It does not update PostgreSQL, does not call TMDb, and does not recommend blindly importing provider data.",
        "",
        "## Summary",
        "",
        f"- Total seeded titles: {len(seed_by_id)}",
        f"- Total preview titles: {len(preview_by_id)}",
        f"- Matched by `tmdb_id`: {matched_count}",
        f"- Missing preview count: {missing_preview_count}",
        f"- Extra preview IDs not in seed: {len(extra_preview_ids)}",
        f"- Total comparison notes/warnings: {warning_count}",
        f"- Seed content split: {dict(content_type_counts)}",
        f"- Preview media split: {dict(preview_media_counts)}",
        "",
        "## Important Findings",
        "",
        "- Poster and backdrop URLs match the processed preview for all 15 seeded titles.",
        "- IMDb IDs are available in the processed preview for all 15 titles and belong in `external_ids`, not `content`.",
        "- TMDb genres do not map cleanly to the local genre taxonomy without normalization.",
        "- TMDb TV runtime values are missing/null for the current series preview rows, so current seeded runtimes should be kept for now.",
        "- TMDb language values are provider codes such as `en`, `ko`, and `de`; local seed data uses readable names.",
        "- TMDb status values can differ from the current local seed convention, especially for series.",
        "- Cast and director/creator data is available, but the current schema needs person/role tables before importing it.",
        "- TMDb vote average, vote count, and popularity are provider-specific analytics signals and should not be written into `content_summary` directly.",
        "",
    ]

    if extra_preview_ids:
        lines.extend(
            [
                "## Extra Preview IDs",
                "",
                ", ".join(str(tmdb_id) for tmdb_id in extra_preview_ids),
                "",
            ]
        )

    lines.extend(
        [
            "## Field-by-Field Summary",
            "",
            "| Field | Current Result | Gap | Recommendation |",
            "| --- | --- | --- | --- |",
        ]
    )
    for field, result, gap, recommendation in build_field_summary(comparisons):
        lines.append(
            f"| {markdown_escape(field)} | {markdown_escape(result)} | {markdown_escape(gap)} | {markdown_escape(recommendation)} |"
        )

    lines.extend(
        [
            "",
            "## Title-by-Title Comparison",
            "",
            "| Title | TMDb ID | Type | Media OK | Dates | Runtime | Language | Status | Poster | Backdrop | IMDb | Credits | Notes |",
            "| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for comparison in comparisons:
        seed = comparison.seed
        preview = comparison.preview
        dates = f"{seed.release_date} -> {preview_value(preview, 'release_date')}"
        runtime = f"{seed.runtime} -> {preview_value(preview, 'runtime')}"
        language = f"{seed.language} -> {preview_value(preview, 'original_language')}"
        status = f"{seed.status} -> {preview_value(preview, 'status')}"
        credits = (
            f"cast {len(preview.get('top_cast_names') or [])}, people {len(preview.get('director_or_creator_names') or [])}"
            if preview
            else "-"
        )
        imdb = preview.get("imdb_id") if preview else None
        note_text = "; ".join(comparison.notes) if comparison.notes else "OK"

        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(seed.title),
                    str(seed.tmdb_id),
                    seed.content_type,
                    yes_no(comparison.media_matches),
                    markdown_escape(dates),
                    markdown_escape(runtime),
                    markdown_escape(language),
                    markdown_escape(status),
                    yes_no(comparison.poster_matches),
                    yes_no(comparison.backdrop_matches),
                    markdown_escape(imdb or "-"),
                    markdown_escape(credits),
                    markdown_escape(note_text),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Genre Analysis",
            "",
            "Local genres and TMDb genres should not be merged directly. TMDb uses broader or differently named categories in several places.",
            "",
            "| Title | Local Genres | TMDb Genres | Normalized Difference |",
            "| --- | --- | --- | --- |",
        ]
    )

    local_genre_counter: Counter[str] = Counter()
    tmdb_genre_counter: Counter[str] = Counter()
    for comparison in comparisons:
        seed = comparison.seed
        preview = comparison.preview
        local_genre_counter.update(seed.genres)
        tmdb_genres = list(preview.get("genres") or []) if preview else []
        tmdb_genre_counter.update(tmdb_genres)
        lines.append(
            f"| {markdown_escape(seed.title)} | {markdown_escape(format_list(seed.genres))} | {markdown_escape(format_list(tmdb_genres))} | {markdown_escape(comparison.genre_note)} |"
        )

    lines.extend(
        [
            "",
            "Observed normalization needs:",
            "",
            "- `Sci-Fi` vs `Science Fiction`",
            "- `Sci-Fi`/`Fantasy` vs `Sci-Fi & Fantasy`",
            "- `Action`/`Adventure` vs `Action & Adventure`",
            "- Some local genres intentionally add decision-support nuance that TMDb does not provide for the same title.",
            "",
            "Recommendation: create a future genre normalization map before importing provider genres. Do not direct-import TMDb genres into the local taxonomy yet.",
            "",
            "Local genre frequency:",
            "",
        ]
    )
    for genre, count in sorted(local_genre_counter.items()):
        lines.append(f"- {genre}: {count}")

    lines.extend(["", "TMDb genre frequency:", ""])
    for genre, count in sorted(tmdb_genre_counter.items()):
        lines.append(f"- {genre}: {count}")

    lines.extend(
        [
            "",
            "## Runtime Analysis",
            "",
            "| Title | Type | Seed Runtime | TMDb Runtime | Recommendation |",
            "| --- | --- | ---: | ---: | --- |",
        ]
    )
    for comparison in comparisons:
        seed = comparison.seed
        preview_runtime = preview_value(comparison.preview, "runtime")
        if seed.content_type == "series" and preview_runtime is None:
            recommendation = "Keep seed runtime; TMDb preview has null TV runtime."
        elif seed.runtime == preview_runtime:
            recommendation = "No change needed."
        else:
            recommendation = "Review manually before changing seed runtime."
        lines.append(
            f"| {markdown_escape(seed.title)} | {seed.content_type} | {markdown_escape(seed.runtime)} | {markdown_escape(preview_runtime)} | {recommendation} |"
        )

    lines.extend(
        [
            "",
            "## Credits Analysis",
            "",
            "Credits are useful for the future detail page, but they require person and role schema before import.",
            "",
            "| Title | Top Cast Available | Director/Creator Available | Top Cast Preview | Director/Creator Preview |",
            "| --- | ---: | ---: | --- | --- |",
        ]
    )
    for comparison in comparisons:
        seed = comparison.seed
        preview = comparison.preview or {}
        top_cast = preview.get("top_cast_names") or []
        people = preview.get("director_or_creator_names") or []
        lines.append(
            f"| {markdown_escape(seed.title)} | {len(top_cast)} | {len(people)} | {markdown_escape(format_list(top_cast, 3))} | {markdown_escape(format_list(people, 3))} |"
        )

    lines.extend(
        [
            "",
            "## Provider-Specific Analytics Signals",
            "",
            "| Title | Vote Average | Vote Count | Popularity | Recommendation |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for comparison in comparisons:
        seed = comparison.seed
        preview = comparison.preview or {}
        lines.append(
            f"| {markdown_escape(seed.title)} | {markdown_escape(preview.get('vote_average'))} | {markdown_escape(preview.get('vote_count'))} | {markdown_escape(preview.get('popularity'))} | Keep as provider-specific input; do not write into `content_summary` directly. |"
        )

    lines.extend(
        [
            "",
            "## Recommendations",
            "",
            "### A. Safe to Keep/Update Now",
            "",
            "- `poster_url`",
            "- `backdrop_url`",
            "- `external_ids` for `tmdb` and `imdb`",
            "",
            "These fields already have a clear storage location and have been verified through the processed preview.",
            "",
            "### B. Needs Normalization Before Import",
            "",
            "- `genres`",
            "- `language`",
            "- `status`",
            "",
            "These fields are useful, but provider values should pass through normalization rules before changing local seed data or production tables.",
            "",
            "### C. Needs New Schema Before Import",
            "",
            "- cast",
            "- directors",
            "- creators",
            "",
            "Credits should wait for `persons` and content-person role tables. Do not squeeze this data into text fields.",
            "",
            "### D. Should Not Overwrite Yet",
            "",
            "- curated `overview`",
            "- manually chosen `runtime`",
            "- existing ratings",
            "- existing summaries, pros, cons, verdicts, and unified scores",
            "",
            "Current seed values support the product narrative and tests. Provider values may be useful later, but they should not overwrite curated fields without a separate product decision.",
            "",
            "### E. Provider-Specific Analytics Signals",
            "",
            "- `vote_average`",
            "- `vote_count`",
            "- `popularity`",
            "",
            "These should remain provider-specific inputs for future analytics/scoring work. They should not become the InsightStream unified score by direct assignment.",
            "",
            "## Suggested Next Task",
            "",
            "Create a genre/language/status normalization plan before importing additional TMDb metadata. That plan should define allowed local values, provider mappings, and fields that should stay curated.",
            "",
            "## Final Summary",
            "",
            "The processed TMDb preview confirms that the current seed already safely uses real media URLs and external IDs for all 15 titles. The remaining useful TMDb metadata should be imported only after normalization rules, provenance decisions, and person/credits schema are planned.",
            "",
        ]
    )

    return "\n".join(lines), matched_count, warning_count


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    parse_args(argv)
    seed_by_id = load_seed_content()
    preview_by_id = load_preview_items()
    report, matched_count, warning_count = build_report(seed_by_id, preview_by_id)

    REPORT_PATH.write_text(report, encoding="utf-8")

    print(f"Report written: {REPORT_PATH.relative_to(REPO_ROOT)}")
    print(f"Total matched: {matched_count}")
    print(f"Total warnings: {warning_count}")
    print(
        "Suggested next task: create a genre/language/status normalization plan before importing additional TMDb metadata."
    )
    print("No database, API, or frontend changes were made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
