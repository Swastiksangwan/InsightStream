#!/usr/bin/env python3
"""
Preview local movie matches against a local Letterboxd JSONL dataset.

This script:
- reads local movie catalog metadata from PostgreSQL using DATABASE_URL
- reads a local Letterboxd JSONL or JSONL.GZ dataset file
- matches movie candidates by normalized title, year, and director overlap
- writes a preview JSON and run report for manual review
- does not write to PostgreSQL
- ignores review text and does not call external APIs

Example:
    python3 -m analytics.scripts.ingestion.preview_letterboxd_ratings_match \
        --dataset-file analytics/datasets/letterboxd/letterboxd_movies.jsonl
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import string
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency guidance for script-only runs.
    load_dotenv = None


DATABASE_URL_ENV = "DATABASE_URL"
from analytics.scripts.common.paths import REPO_ROOT
DEFAULT_OUTPUT_DIR = REPO_ROOT / "analytics" / "processed" / "letterboxd"
PREVIEW_FILENAME = "letterboxd_rating_match_preview.json"
REPORT_FILENAME = "letterboxd_match_report.json"
ARTICLES = {"the", "a", "an"}


class LetterboxdPreviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalMovie:
    content_id: int
    title: str
    year: int | None
    directors: list[str]
    external_ids: dict[str, str]


@dataclass(frozen=True)
class LetterboxdMovie:
    line_number: int
    url: str | None
    title: str
    normalized_title: str
    year: int | None
    directors: list[str]
    raw_score: float | None
    raw_score_scale: float | None
    normalized_score: float | None
    vote_count: None
    warnings: list[str]


@dataclass
class DatasetStats:
    dataset_rows_scanned: int = 0
    malformed_rows: int = 0
    rows_with_valid_rating: int = 0
    rows_without_rating: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MatchDecision:
    match_status: str
    confidence_score: float
    letterboxd: LetterboxdMovie | None
    warnings: list[str]
    candidates: list[LetterboxdMovie]

    @property
    def matched(self) -> bool:
        return self.match_status in {
            "high_confidence",
            "good_confidence",
            "ambiguous",
        }

    @property
    def import_ready(self) -> bool:
        return (
            self.match_status == "high_confidence"
            and self.letterboxd is not None
            and self.letterboxd.normalized_score is not None
        )


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def confidence_value(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a number between 0 and 1") from exc
    if parsed < 0 or parsed > 1:
        raise argparse.ArgumentTypeError("value must be a number between 0 and 1")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview local movie matches against a local Letterboxd JSONL dataset."
    )
    parser.add_argument(
        "--dataset-file",
        required=True,
        help="Path to local Letterboxd JSONL or JSONL.GZ dataset file.",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        help="Read only the first N non-empty dataset rows.",
    )
    parser.add_argument(
        "--title",
        help="Limit local movie matching to one title for inspection.",
    )
    parser.add_argument(
        "--min-confidence",
        type=confidence_value,
        default=0.85,
        help="Minimum confidence used for import-ready preview counts.",
    )
    parser.add_argument(
        "--include-ambiguous",
        action="store_true",
        help="Include compact candidate lists for ambiguous matches.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR.relative_to(REPO_ROOT)),
        help=(
            "Output directory. Defaults to "
            f"{DEFAULT_OUTPUT_DIR.relative_to(REPO_ROOT)}."
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


def json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, ensure_ascii=False) + "\n")


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def normalize_title(value: Any, remove_articles: bool = True) -> str:
    text_value = clean_text(value)
    if not text_value:
        return ""

    normalized = unicodedata.normalize("NFKD", text_value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = normalized.replace("&", " and ")
    translator = str.maketrans({char: " " for char in string.punctuation})
    normalized = normalized.translate(translator)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    if remove_articles:
        parts = normalized.split()
        if parts and parts[0] in ARTICLES:
            normalized = " ".join(parts[1:])

    return normalized


def normalize_person_name(value: Any) -> str:
    return normalize_title(value, remove_articles=False)


def parse_year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text_value = clean_text(value)
    if not text_value:
        return None
    match = re.search(r"\d{4}", text_value)
    if not match:
        return None
    return int(match.group(0))


def list_from_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text_value = clean_text(value)
        return [text_value] if text_value else []
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text_value = clean_text(item.get("name") or item.get("title"))
            else:
                text_value = clean_text(item)
            if text_value:
                values.append(text_value)
        return values
    return []


def parse_letterboxd_rating(value: Any) -> tuple[float | None, float | None, float | None, str | None]:
    text_value = clean_text(value)
    if not text_value:
        return None, None, None, "missing rating"

    match = re.search(
        r"(?P<score>\d+(?:\.\d+)?)\s*out\s+of\s+(?P<scale>\d+(?:\.\d+)?)",
        text_value,
        flags=re.IGNORECASE,
    )
    if not match:
        return None, None, None, f"invalid rating format: {text_value!r}"

    raw_score = float(match.group("score"))
    raw_score_scale = float(match.group("scale"))
    if raw_score_scale <= 0:
        return None, None, None, f"invalid rating scale: {text_value!r}"

    normalized_score = max(0, min(100, raw_score / raw_score_scale * 100))
    return raw_score, raw_score_scale, round(normalized_score, 2), None


def open_dataset_file(path: Path):
    if not path.exists():
        raise LetterboxdPreviewError(f"Missing Letterboxd dataset file: {relative_path(path)}")
    if path.suffix == ".gz":
        return gzip.open(path, mode="rt", encoding="utf-8")
    return path.open(mode="r", encoding="utf-8")


def letterboxd_movie_from_payload(
    payload: dict[str, Any],
    line_number: int,
    stats: DatasetStats,
) -> LetterboxdMovie | None:
    title = clean_text(payload.get("title"))
    if not title:
        stats.warnings.append(f"Line {line_number}: missing title; skipped.")
        return None

    warnings: list[str] = []
    raw_score, raw_score_scale, normalized_score, rating_warning = parse_letterboxd_rating(
        payload.get("rating")
    )
    if rating_warning:
        warnings.append(rating_warning)
        stats.rows_without_rating += 1
    else:
        stats.rows_with_valid_rating += 1

    directors = list_from_value(payload.get("directors"))
    url = clean_text(payload.get("url"))

    return LetterboxdMovie(
        line_number=line_number,
        url=url,
        title=title,
        normalized_title=normalize_title(title),
        year=parse_year(payload.get("year")),
        directors=directors,
        raw_score=raw_score,
        raw_score_scale=raw_score_scale,
        normalized_score=normalized_score,
        vote_count=None,
        warnings=warnings,
    )


def read_letterboxd_dataset(
    path: Path,
    local_title_keys: set[str],
    stats: DatasetStats,
    limit: int | None = None,
) -> dict[str, list[LetterboxdMovie]]:
    candidates_by_title: dict[str, list[LetterboxdMovie]] = defaultdict(list)

    with open_dataset_file(path) as file_obj:
        for line_number, line in enumerate(file_obj, start=1):
            if limit is not None and stats.dataset_rows_scanned >= limit:
                break

            line = line.strip()
            if not line:
                continue

            stats.dataset_rows_scanned += 1
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                stats.malformed_rows += 1
                stats.warnings.append(f"Line {line_number}: malformed JSON ({exc}).")
                continue

            if not isinstance(payload, dict):
                stats.malformed_rows += 1
                stats.warnings.append(f"Line {line_number}: expected JSON object.")
                continue

            movie = letterboxd_movie_from_payload(payload, line_number, stats)
            if movie is None:
                continue
            if movie.normalized_title in local_title_keys:
                candidates_by_title[movie.normalized_title].append(movie)

    return dict(candidates_by_title)


def load_database_url() -> str | None:
    if load_dotenv is not None:
        load_dotenv(REPO_ROOT / ".env")
        load_dotenv(REPO_ROOT / "backend" / ".env")
    return os.getenv(DATABASE_URL_ENV)


def read_local_movies(connection: Any, title_filter: str | None = None) -> list[LocalMovie]:
    rows = connection.execute(
        text(
            """
            SELECT
                c.id,
                c.title,
                COALESCE(c.year, EXTRACT(YEAR FROM c.release_date)::INTEGER) AS year,
                COALESCE(d.directors, ARRAY[]::TEXT[]) AS directors,
                COALESCE(e.external_ids, '{}'::JSONB) AS external_ids
            FROM content c
            LEFT JOIN (
                SELECT
                    cp.content_id,
                    ARRAY_AGG(DISTINCT p.name ORDER BY p.name) AS directors
                FROM content_people cp
                JOIN people p ON p.id = cp.person_id
                WHERE cp.role_type = 'director'
                   OR LOWER(COALESCE(cp.job, '')) = 'director'
                GROUP BY cp.content_id
            ) d ON d.content_id = c.id
            LEFT JOIN (
                SELECT
                    content_id,
                    JSONB_OBJECT_AGG(source_name, external_id) AS external_ids
                FROM external_ids
                GROUP BY content_id
            ) e ON e.content_id = c.id
            WHERE c.content_type = 'movie'
            ORDER BY c.title ASC;
            """
        )
    ).mappings().all()

    normalized_filter = normalize_title(title_filter) if title_filter else None
    movies: list[LocalMovie] = []
    for row in rows:
        if normalized_filter:
            title_key = normalize_title(row["title"])
            if normalized_filter != title_key and normalized_filter not in title_key:
                continue

        external_ids = dict(row["external_ids"] or {})
        movies.append(
            LocalMovie(
                content_id=row["id"],
                title=row["title"],
                year=row["year"],
                directors=list(row["directors"] or []),
                external_ids=external_ids,
            )
        )
    return movies


def director_overlap(local_directors: list[str], letterboxd_directors: list[str]) -> bool:
    local_names = {normalize_person_name(name) for name in local_directors}
    letterboxd_names = {normalize_person_name(name) for name in letterboxd_directors}
    local_names.discard("")
    letterboxd_names.discard("")
    return bool(local_names and letterboxd_names and local_names & letterboxd_names)


def compact_letterboxd_movie(movie: LetterboxdMovie | None) -> dict[str, Any] | None:
    if movie is None:
        return None
    return {
        "title": movie.title,
        "year": movie.year,
        "directors": movie.directors,
        "url": movie.url,
        "raw_score": movie.raw_score,
        "raw_score_scale": movie.raw_score_scale,
        "normalized_score": movie.normalized_score,
        "vote_count": movie.vote_count,
    }


def choose_best_candidate(candidates: list[LetterboxdMovie], local: LocalMovie) -> LetterboxdMovie | None:
    if not candidates:
        return None

    def sort_key(movie: LetterboxdMovie):
        year_delta = abs((movie.year or 0) - (local.year or 0)) if movie.year and local.year else 999
        has_director_overlap = director_overlap(local.directors, movie.directors)
        has_rating = movie.normalized_score is not None
        return (year_delta, not has_director_overlap, not has_rating, movie.line_number)

    return sorted(candidates, key=sort_key)[0]


def match_local_movie(
    local: LocalMovie,
    candidates_by_title: dict[str, list[LetterboxdMovie]],
    include_ambiguous: bool = False,
) -> MatchDecision:
    title_key = normalize_title(local.title)
    title_candidates = candidates_by_title.get(title_key, [])
    if not title_candidates:
        return MatchDecision(
            match_status="unmatched",
            confidence_score=0,
            letterboxd=None,
            warnings=["No Letterboxd candidate found for normalized title/year."],
            candidates=[],
        )

    exact_year_candidates = [
        candidate
        for candidate in title_candidates
        if local.year is not None and candidate.year == local.year
    ]

    if len(exact_year_candidates) == 1:
        candidate = exact_year_candidates[0]
        both_have_directors = bool(local.directors and candidate.directors)
        if both_have_directors and director_overlap(local.directors, candidate.directors):
            return MatchDecision(
                match_status="high_confidence",
                confidence_score=0.95,
                letterboxd=candidate,
                warnings=candidate.warnings,
                candidates=[],
            )
        if not both_have_directors:
            return MatchDecision(
                match_status="good_confidence",
                confidence_score=0.88,
                letterboxd=candidate,
                warnings=[
                    *candidate.warnings,
                    "Director data missing on one side; manual review recommended.",
                ],
                candidates=[],
            )
        return MatchDecision(
            match_status="ambiguous",
            confidence_score=0.65,
            letterboxd=candidate,
            warnings=[
                *candidate.warnings,
                "Title/year match but director mismatch; manual review required.",
            ],
            candidates=exact_year_candidates if include_ambiguous else [],
        )

    if len(exact_year_candidates) > 1:
        best = choose_best_candidate(exact_year_candidates, local)
        return MatchDecision(
            match_status="ambiguous",
            confidence_score=0.7,
            letterboxd=best,
            warnings=[
                "Multiple Letterboxd candidates found for the same title/year; manual review required.",
            ],
            candidates=exact_year_candidates if include_ambiguous else [],
        )

    near_year_candidates = [
        candidate
        for candidate in title_candidates
        if local.year is not None
        and candidate.year is not None
        and abs(candidate.year - local.year) <= 2
    ]
    if near_year_candidates:
        best = choose_best_candidate(near_year_candidates, local)
        return MatchDecision(
            match_status="ambiguous",
            confidence_score=0.55,
            letterboxd=best,
            warnings=["Title match with nearby year mismatch; manual review required."],
            candidates=near_year_candidates if include_ambiguous else [],
        )

    best = choose_best_candidate(title_candidates, local)
    return MatchDecision(
        match_status="ambiguous",
        confidence_score=0.45,
        letterboxd=best,
        warnings=["Title match without matching year; manual review required."],
        candidates=title_candidates if include_ambiguous else [],
    )


def preview_item(
    local: LocalMovie,
    decision: MatchDecision,
    include_ambiguous: bool,
) -> dict[str, Any]:
    item = {
        "content_id": local.content_id,
        "local_title": local.title,
        "local_year": local.year,
        "local_directors": local.directors,
        "external_ids": local.external_ids,
        "match_status": decision.match_status,
        "confidence_score": decision.confidence_score,
        "letterboxd": compact_letterboxd_movie(decision.letterboxd),
        "warnings": decision.warnings,
    }
    if include_ambiguous and decision.candidates:
        item["candidates"] = [
            compact_letterboxd_movie(candidate) for candidate in decision.candidates
        ]
    return item


def build_preview_and_report(
    local_movies: list[LocalMovie],
    candidates_by_title: dict[str, list[LetterboxdMovie]],
    dataset_stats: DatasetStats,
    dataset_file: Path,
    output_dir: Path,
    min_confidence: float = 0.85,
    include_ambiguous: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    generated_at = datetime.now(timezone.utc).isoformat()
    items: list[dict[str, Any]] = []
    decisions: list[MatchDecision] = []

    for local in local_movies:
        decision = match_local_movie(local, candidates_by_title, include_ambiguous)
        decisions.append(decision)
        items.append(preview_item(local, decision, include_ambiguous))

    status_counts = Counter(decision.match_status for decision in decisions)
    matched_count = sum(1 for decision in decisions if decision.matched)
    import_ready_count = sum(
        1
        for decision in decisions
        if decision.import_ready and decision.confidence_score >= min_confidence
    )
    warnings = list(dataset_stats.warnings)
    for item in items:
        for warning in item.get("warnings", []):
            warnings.append(f"{item['local_title']}: {warning}")

    preview = {
        "generated_at": generated_at,
        "dataset_file": relative_path(dataset_file),
        "local_movie_count": len(local_movies),
        "matched_count": matched_count,
        "high_confidence_count": status_counts.get("high_confidence", 0),
        "good_confidence_count": status_counts.get("good_confidence", 0),
        "ambiguous_count": status_counts.get("ambiguous", 0),
        "unmatched_count": status_counts.get("unmatched", 0),
        "min_confidence": min_confidence,
        "items": items,
    }
    report = {
        "generated_at": generated_at,
        "script_name": "preview_letterboxd_ratings_match.py",
        "dataset_file": relative_path(dataset_file),
        "output_dir": relative_path(output_dir),
        "dataset_rows_scanned": dataset_stats.dataset_rows_scanned,
        "malformed_rows": dataset_stats.malformed_rows,
        "rows_with_valid_rating": dataset_stats.rows_with_valid_rating,
        "rows_without_rating": dataset_stats.rows_without_rating,
        "local_movie_count": len(local_movies),
        "matched_count": matched_count,
        "high_confidence_count": status_counts.get("high_confidence", 0),
        "good_confidence_count": status_counts.get("good_confidence", 0),
        "ambiguous_count": status_counts.get("ambiguous", 0),
        "unmatched_count": status_counts.get("unmatched", 0),
        "import_ready_count": import_ready_count,
        "warnings": warnings[:200],
    }
    return preview, report


def print_summary(preview: dict[str, Any], report: dict[str, Any], preview_path: Path, report_path: Path) -> None:
    print("Letterboxd match preview complete")
    print(f"Dataset rows scanned: {report['dataset_rows_scanned']}")
    print(f"Local movies: {report['local_movie_count']}")
    print(f"High confidence matches: {report['high_confidence_count']}")
    print(f"Good matches: {report['good_confidence_count']}")
    print(f"Ambiguous: {report['ambiguous_count']}")
    print(f"Unmatched: {report['unmatched_count']}")
    print(f"Import-ready preview rows: {report['import_ready_count']}")
    print(f"Preview path: {relative_path(preview_path)}")
    print(f"Report path: {relative_path(report_path)}")
    print("No database changes were made.")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dataset_file = resolve_path(args.dataset_file)
    output_dir = resolve_path(args.output_dir)
    preview_path = output_dir / PREVIEW_FILENAME
    report_path = output_dir / "run_reports" / REPORT_FILENAME

    database_url = load_database_url()
    if not database_url:
        print(f"Missing {DATABASE_URL_ENV}. Export it before running this preview script.")
        print("No database changes were made.")
        return 1

    try:
        engine = create_engine(database_url)
        with engine.connect() as connection:
            local_movies = read_local_movies(connection, args.title)

        local_title_keys = {normalize_title(movie.title) for movie in local_movies}
        dataset_stats = DatasetStats()
        candidates_by_title = read_letterboxd_dataset(
            dataset_file,
            local_title_keys,
            dataset_stats,
            limit=args.limit,
        )
        preview, report = build_preview_and_report(
            local_movies,
            candidates_by_title,
            dataset_stats,
            dataset_file,
            output_dir,
            min_confidence=args.min_confidence,
            include_ambiguous=args.include_ambiguous,
        )
        write_json(preview_path, preview)
        write_json(report_path, report)
    except (LetterboxdPreviewError, SQLAlchemyError) as exc:
        print(f"Letterboxd match preview failed: {exc}")
        print("No database changes were made.")
        return 1

    print_summary(preview, report, preview_path, report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
