#!/usr/bin/env python3
"""
Audit source-signal mapping and genre/subgenre quality for local catalog content.

This script:
- reads local catalog rows through DATABASE_URL
- inspects raw imported TMDb keywords, stored source signals, watch guidance, and
  the current backend decision_layer.display output
- writes local-only JSON/CSV/summary reports under analytics/processed/source_signals/
- performs no database writes
- does not call TMDb, scrape, or use LLM generation
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, create_engine, text

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional convenience dependency
    load_dotenv = None


from analytics.scripts.common.paths import REPO_ROOT, ensure_backend_import_path
from analytics.scripts.source_signals.source_signal_keyword_normalization import (
    normalize_keyword_name,
)

ensure_backend_import_path()

from app.services.content_service import get_content_details_service  # noqa: E402


DATABASE_URL_ENV = "DATABASE_URL"
DEFAULT_MAPPING_PATH = (
    REPO_ROOT / "analytics" / "config" / "source_signal_keyword_mapping.json"
)
DEFAULT_JSON_OUTPUT = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "source_signals"
    / "source_signal_mapping_quality_report.json"
)
DEFAULT_CSV_OUTPUT = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "source_signals"
    / "source_signal_mapping_quality_report.csv"
)
DEFAULT_SUMMARY_OUTPUT = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "source_signals"
    / "run_reports"
    / "source_signal_mapping_quality_summary.json"
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
DIMENSION_ORDER = [
    "audience_expectation",
    "topic_theme",
    "mood",
    "tone",
    "pacing",
    "intensity",
    "content_caution_proxy",
]
SEVERITY_PENALTIES = {
    "critical": 35,
    "high": 20,
    "medium": 10,
    "low": 4,
}
SEVERITIES = ("critical", "high", "medium", "low")

TECHNICAL_LEAK_TERMS = (
    "tmdb_keywords",
    "source_names",
    "mapping_version",
    "provider keyword",
    "source_signal",
    "source signal",
    "confidence",
)
WEAK_LABELS = {
    "story",
    "drama",
    "complex story",
    "dark story",
    "serious story",
    "serious stories",
    "all themes",
    "bleak mood",
    "dark mood",
    "heavier watch",
    "platform viewers",
    "serialized drama viewers",
    "availability viewers",
    "content",
}
BROAD_GENRE_LABELS = {
    "action",
    "adventure",
    "crime",
    "drama",
    "fantasy",
    "sci-fi",
    "science fiction",
    "thriller",
}
BROAD_GENRES = {
    "Action",
    "Adventure",
    "Crime",
    "Drama",
    "Fantasy",
    "Science Fiction",
    "Sci-Fi",
    "Thriller",
}
INTENSE_LABEL_HINTS = {
    "bleak",
    "brutal",
    "dark",
    "foreboding",
    "high intensity",
    "high-stakes",
    "intense",
}
STRONG_CAUTION_HINTS = {
    "blood",
    "body horror",
    "brutal",
    "disturbing",
    "dystopian oppression",
    "graphic",
    "horror",
    "psychological horror",
    "serial killer",
    "serial-killer",
    "suicide",
    "violent",
    "violence",
    "war violence",
}
TENSE_CAUTION_CONTEXT_HINTS = {
    "bleak",
    "crime",
    "dark thriller",
    "horror",
    "murder",
    "psychological thriller",
    "serial killer",
    "serial-killer",
    "thriller",
}
WAR_CONTEXT_PATTERNS = (
    r"\bworld war\b",
    r"\bwwii\b",
    r"\bww2\b",
    r"\bvietnam war\b",
    r"\bcivil war\b",
    r"\banti war\b",
    r"\bwartime\b",
    r"\bwar violence\b",
    r"\bbattlefield\b",
    r"\bbattlefields\b",
    r"\bbattle\b",
    r"\bbattles\b",
    r"\bsoldier\b",
    r"\bsoldiers\b",
    r"\bmilitary combat\b",
    r"\bcombat\b",
    r"\barmy\b",
    r"\bnaval battle\b",
    r"\bnavy\b",
)
WORLD_WAR_II_PATTERNS = (
    r"\bworld war ii\b",
    r"\bwwii\b",
    r"\bww2\b",
)
GENERIC_MAPPING_NOISE = {
    "aftercreditsstinger",
    "duringcreditsstinger",
    "sequel",
    "remake",
    "spin off",
    "woman director",
    "based on novel or book",
}


@dataclass(frozen=True)
class MappingIssue:
    code: str
    severity: str
    field: str
    value: str
    message: str
    suggested_action: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "field": self.field,
            "value": self.value,
            "message": self.message,
            "suggested_action": self.suggested_action,
        }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit stored source-signal mapping and genre/subgenre quality."
    )
    parser.add_argument(
        "--content-id",
        type=int,
        action="append",
        help="Audit one content ID. Can be passed more than once.",
    )
    parser.add_argument(
        "--content-type",
        choices=["movie", "series", "all"],
        default="all",
        help="Filter by content type. Defaults to all.",
    )
    parser.add_argument("--limit", type=positive_int, help="Maximum titles to audit.")
    parser.add_argument(
        "--offset",
        type=non_negative_int,
        default=0,
        help="Catalog offset for batch audits. Defaults to 0.",
    )
    parser.add_argument(
        "--include-passing",
        action="store_true",
        help="Include clean/passing titles in JSON details.",
    )
    parser.add_argument(
        "--min-score",
        type=score_value,
        default=None,
        help="Only include titles below this score in JSON details.",
    )
    parser.add_argument(
        "--output-json",
        default=str(DEFAULT_JSON_OUTPUT.relative_to(REPO_ROOT)),
        help=(
            "Detailed JSON report path. Defaults to "
            f"{DEFAULT_JSON_OUTPUT.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--output-csv",
        default=str(DEFAULT_CSV_OUTPUT.relative_to(REPO_ROOT)),
        help=(
            "Spreadsheet-friendly CSV report path. Defaults to "
            f"{DEFAULT_CSV_OUTPUT.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--summary-output",
        default=str(DEFAULT_SUMMARY_OUTPUT.relative_to(REPO_ROOT)),
        help=(
            "Summary JSON path. Defaults to "
            f"{DEFAULT_SUMMARY_OUTPUT.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--fail-on-critical",
        action="store_true",
        help="Exit non-zero if any critical issue is found.",
    )
    parser.add_argument(
        "--fail-under-score",
        type=score_value,
        default=None,
        help="Exit non-zero if any audited title scores below this threshold.",
    )
    return parser.parse_args(argv)


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be zero or a positive integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be zero or a positive integer")
    return parsed


def score_value(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("score must be an integer between 0 and 100") from exc
    if parsed < 0 or parsed > 100:
        raise argparse.ArgumentTypeError("score must be an integer between 0 and 100")
    return parsed


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_database_url() -> str | None:
    if load_dotenv is not None:
        load_dotenv(REPO_ROOT / ".env")
        load_dotenv(REPO_ROOT / "backend" / ".env")
    return os.getenv(DATABASE_URL_ENV)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def lower_text(value: Any) -> str:
    return clean_text(value).lower()


def pipe_join(values: list[Any]) -> str:
    return " | ".join(clean_text(value) for value in values or [] if clean_text(value))


def json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def json_list(value: Any) -> list[Any]:
    parsed = json_value(value, [])
    return parsed if isinstance(parsed, list) else []


def json_dict(value: Any) -> dict[str, Any]:
    parsed = json_value(value, {})
    return parsed if isinstance(parsed, dict) else {}


def issue(
    code: str,
    severity: str,
    field: str,
    value: Any,
    message: str,
    suggested_action: str,
) -> MappingIssue:
    return MappingIssue(
        code=code,
        severity=severity,
        field=field,
        value=clean_text(value),
        message=message,
        suggested_action=suggested_action,
    )


def add_unique_issue(issues: list[MappingIssue], new_issue: MappingIssue) -> None:
    key = (
        new_issue.code,
        new_issue.severity,
        new_issue.field,
        new_issue.value.lower(),
    )
    existing = {
        (item.code, item.severity, item.field, item.value.lower())
        for item in issues
    }
    if key not in existing:
        issues.append(new_issue)


def issue_counts(issues: list[MappingIssue]) -> dict[str, int]:
    counts = {severity: 0 for severity in SEVERITIES}
    for item in issues:
        counts[item.severity] = counts.get(item.severity, 0) + 1
    return counts


def calculate_score(issues: list[MappingIssue]) -> int:
    score = 100
    for item in issues:
        score -= SEVERITY_PENALTIES.get(item.severity, 0)
    return max(0, min(100, score))


def grade_for_score(score: int, issues: list[MappingIssue]) -> str:
    if any(item.severity == "critical" for item in issues) or score < 60:
        return "blocked"
    if score >= 90:
        return "excellent"
    if score >= 80:
        return "good"
    return "needs_review"


def mapping_ready_for(
    score: int,
    issues: list[MappingIssue],
    dimensions: set[str] | None = None,
) -> bool:
    if score < 80:
        return False
    if any(item.severity in {"critical", "high"} for item in issues):
        return False
    if dimensions is None:
        return True
    if not {"audience_expectation", "topic_theme"} <= dimensions:
        return False
    practical_dimensions = {"mood", "tone", "pacing"}
    return len(practical_dimensions & dimensions) >= 2


def unique_preserve_order(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text_value = clean_text(value)
        key = text_value.lower()
        if text_value and key not in seen:
            seen.add(key)
            result.append(text_value)
    return result


def labels_from_signals(signals: list[dict[str, Any]]) -> list[str]:
    return unique_preserve_order([signal.get("label") for signal in signals])


def signals_by_dimension(signals: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for dimension in DIMENSION_ORDER:
        labels = [
            clean_text(signal.get("label"))
            for signal in signals
            if signal.get("dimension") == dimension and clean_text(signal.get("label"))
        ]
        if labels:
            grouped[dimension] = unique_preserve_order(labels)
    return grouped


def signal_dimensions_present(signals: list[dict[str, Any]]) -> list[str]:
    present = {
        clean_text(signal.get("dimension"))
        for signal in signals
        if clean_text(signal.get("dimension"))
    }
    return [dimension for dimension in DIMENSION_ORDER if dimension in present]


def signal_dimensions_missing(signals: list[dict[str, Any]]) -> list[str]:
    present = set(signal_dimensions_present(signals))
    return [dimension for dimension in DIMENSION_ORDER if dimension not in present]


def flattened_display_text(display: dict[str, Any] | None) -> str:
    values: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            if value.strip():
                values.append(value.strip())
            return
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if isinstance(value, dict):
            for item in value.values():
                walk(item)

    walk(display or {})
    return " ".join(values).lower()


def has_text_hint(values: list[str], hints: set[str] | tuple[str, ...]) -> bool:
    text_value = " ".join(lower_text(value) for value in values)
    return any(hint in text_value for hint in hints)


def has_genre(genres: list[str], *candidates: str) -> bool:
    normalized = {lower_text(genre) for genre in genres}
    return any(lower_text(candidate) in normalized for candidate in candidates)


def regex_any(patterns: tuple[str, ...], text_value: str) -> bool:
    return any(re.search(pattern, text_value) for pattern in patterns)


def has_war_context(genres: list[str], context: str) -> bool:
    if has_genre(genres, "War", "War & Politics"):
        return True
    if has_genre(genres, "Animation", "Family", "Comedy", "Fantasy", "Sci-Fi", "Science Fiction"):
        return False
    if has_genre(genres, "History", "Drama") and regex_any(WAR_CONTEXT_PATTERNS, context):
        return True
    return False


def has_world_war_ii_context(context: str) -> bool:
    return regex_any(WORLD_WAR_II_PATTERNS, context)


def all_context_terms(
    genres: list[str],
    raw_keywords: list[str],
    signals: list[dict[str, Any]],
    display: dict[str, Any] | None,
) -> list[str]:
    values = []
    values.extend(genres)
    values.extend(raw_keywords)
    values.extend(labels_from_signals(signals))
    values.append(flattened_display_text(display))
    return values


def source_context_terms(
    genres: list[str],
    raw_keywords: list[str],
    signals: list[dict[str, Any]],
) -> list[str]:
    values = []
    values.extend(genres)
    values.extend(raw_keywords)
    values.extend(labels_from_signals(signals))
    return values


def context_has_any(context: str, terms: tuple[str, ...]) -> bool:
    return any(term in context for term in terms)


def has_kitchen_workplace_context(context: str) -> bool:
    culinary_terms = (
        "kitchen",
        "restaurant",
        "chef",
        "culinary",
        "food industry",
        "fine dining",
        "cooking",
        "cuisine",
    )
    workplace_terms = (
        "workplace",
        "service",
        "small business",
        "restaurant",
        "chef",
        "kitchen",
        "culinary",
        "food industry",
        "fine dining",
    )
    return context_has_any(context, culinary_terms) and context_has_any(context, workplace_terms)


def has_serial_killer_investigation_context(genres: list[str], context: str) -> bool:
    if "serial killer" in context or "serial-killer" in context:
        return True
    if has_genre(genres, "Comedy"):
        return False
    return (
        has_genre(genres, "Crime")
        and has_genre(genres, "Mystery", "Thriller")
        and context_has_any(context, ("murder", "homicide"))
        and context_has_any(context, ("detective", "investigation", "procedural"))
    )


def has_space_survival_context(context: str) -> bool:
    space_terms = (
        "space",
        "spacecraft",
        "astronaut",
        "nasa",
        "interplanetary",
        "mars",
        "space sci-fi",
    )
    survival_terms = (
        "survival",
        "stranded",
        "mission",
        "rescue",
        "isolated",
        "humanity's future",
        "humanitys future",
        "survival-driven",
    )
    return context_has_any(context, space_terms) and context_has_any(context, survival_terms)


def detect_subgenre_candidates(
    genres: list[str],
    raw_keywords: list[str],
    signals: list[dict[str, Any]],
    display: dict[str, Any] | None = None,
) -> list[str]:
    # Detect opportunities from source evidence, not from display fallback text.
    # The compact display is itself an audit target, so using it here can create
    # circular false positives such as workplace or space-survival candidates.
    values = source_context_terms(genres, raw_keywords, signals)
    context = " ".join(lower_text(value) for value in values)
    candidates: list[str] = []

    if has_genre(genres, "Sci-Fi", "Science Fiction") and "heist" in context:
        candidates.append("Sci-fi heist")
    if has_genre(genres, "Crime") and has_genre(genres, "Mystery", "Thriller"):
        if has_serial_killer_investigation_context(genres, context):
            candidates.append("Serial-killer investigation")
    if has_genre(genres, "Fantasy") and any(
        term in context
        for term in (
            "political",
            "power struggle",
            "court intrigue",
            "dynasty",
            "throne",
            "kingdom",
        )
    ):
        candidates.append("Political dark fantasy")
    if has_kitchen_workplace_context(context):
        candidates.append("Kitchen workplace drama")
    if has_war_context(genres, context):
        if has_world_war_ii_context(context):
            candidates.append("World War II drama")
        else:
            candidates.append("War drama")
    if any(term in context for term in ("post apocalyptic", "post-apocalyptic")) and "survival" in context:
        candidates.append("Post-apocalyptic survival drama")
    if "superhero" in context and any(
        term in context for term in ("mythology", "mythic", "egypt", "gods", "identity", "mystery")
    ):
        candidates.append("Mythic superhero mystery")
    if has_space_survival_context(context):
        candidates.append("Space survival sci-fi")

    return unique_preserve_order(candidates)


def candidate_already_covered(candidate: str, signals: list[dict[str, Any]], display: dict[str, Any] | None) -> bool:
    candidate_key = lower_text(candidate)
    label_text = " ".join(lower_text(label) for label in labels_from_signals(signals))
    display_text = flattened_display_text(display)
    return candidate_key in label_text or candidate_key in display_text


def is_weak_label(label: Any) -> bool:
    lower_label = lower_text(label)
    if not lower_label:
        return False
    if lower_label in WEAK_LABELS:
        return True
    if lower_label.endswith(" viewers"):
        return True
    if lower_label in BROAD_GENRE_LABELS:
        return True
    return False


def weak_labels(labels: list[str]) -> list[str]:
    return [label for label in labels if is_weak_label(label)]


def source_names_for_signal(signal: dict[str, Any]) -> list[str]:
    raw_sources = signal.get("source_names") or signal.get("sources")
    return [clean_text(value) for value in json_list(raw_sources) if clean_text(value)]


def all_signal_sources(signals: list[dict[str, Any]], guidance: dict[str, Any] | None) -> set[str]:
    sources: set[str] = set()
    for signal in signals:
        sources.update(source_names_for_signal(signal))
    sources.update(clean_text(value) for value in json_list((guidance or {}).get("signal_sources")))
    return {source for source in sources if source}


def fallback_dependency(
    guidance: dict[str, Any] | None,
    signals: list[dict[str, Any]],
    display: dict[str, Any] | None,
) -> dict[str, bool]:
    sources = all_signal_sources(signals, guidance)
    signal_labels = {lower_text(label) for label in labels_from_signals(signals)}
    display_profile = (display or {}).get("profile") or {}
    display_labels = {
        lower_text(label)
        for key in ("identity", "themes", "feel")
        for label in display_profile.get(key, [])
    }
    display_only_labels = display_labels - signal_labels
    return {
        "uses_curated_override": bool((guidance or {}).get("curated_override_applied"))
        or "curated_override" in sources,
        "uses_metadata_fallback": bool((guidance or {}).get("metadata_fallback_applied"))
        or "metadata_fallback" in sources,
        "uses_backend_display_fallback": bool(display_only_labels),
    }


def keyword_opportunity(keyword: str) -> dict[str, str] | None:
    normalized = normalize_keyword_name(keyword)
    if not normalized or normalized in GENERIC_MAPPING_NOISE:
        return None

    if normalized in {"slow burn", "contemplative", "meditative"}:
        return {
            "suggested_dimension": "pacing",
            "suggested_label": "Slow-burn",
        }
    if normalized in {"investigation", "detective", "procedural"}:
        return {
            "suggested_dimension": "topic_theme",
            "suggested_label": "Investigation",
        }
    if normalized in {"heist", "puzzle", "nonlinear", "non linear"}:
        return {
            "suggested_dimension": "pacing",
            "suggested_label": "Plot-driven and puzzle-like",
        }
    if normalized in {"survival", "stranded", "escape"}:
        return {
            "suggested_dimension": "topic_theme",
            "suggested_label": "Survival",
        }
    if normalized in {"war", "soldier", "battle"}:
        return {
            "suggested_dimension": "topic_theme",
            "suggested_label": "Human cost",
        }
    if normalized in {"satire", "absurd", "dark comedy"}:
        return {
            "suggested_dimension": "tone",
            "suggested_label": "Darkly funny",
        }
    if normalized in {"tense", "suspense", "thriller"}:
        return {
            "suggested_dimension": "mood",
            "suggested_label": "Tense",
        }
    if normalized in {"ensemble", "workplace", "family"}:
        return {
            "suggested_dimension": "topic_theme",
            "suggested_label": normalized.replace("workplace", "Workplace").title(),
        }
    return None


def unmapped_keywords_for_record(raw_keywords: list[str], mapped_keywords: set[str]) -> list[str]:
    unmapped = []
    for keyword in raw_keywords:
        normalized = normalize_keyword_name(keyword)
        if not normalized or normalized in mapped_keywords or normalized in GENERIC_MAPPING_NOISE:
            continue
        unmapped.append(keyword)
    return unique_preserve_order(unmapped)


def load_mapped_keywords(path: Path = DEFAULT_MAPPING_PATH) -> set[str]:
    try:
        raw_config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    mappings = raw_config.get("keyword_mappings") or {}
    excluded = raw_config.get("excluded_keywords") or []
    unsafe = raw_config.get("spoiler_unsafe_keywords") or []
    return {
        normalize_keyword_name(keyword)
        for keyword in [*mappings.keys(), *excluded, *unsafe]
        if normalize_keyword_name(keyword)
    }


def detect_genre_signal_conflict(genres: list[str], labels: list[str]) -> str | None:
    label_text = " ".join(lower_text(label) for label in labels)
    if has_genre(genres, "Documentary") and any(
        term in label_text for term in ("superhero", "heist", "crime thriller")
    ):
        return "Documentary genre conflicts with fiction-heavy signal labels."
    if has_genre(genres, "Animation") and "grim war drama" in label_text:
        return "Animation genre conflicts with grim war-drama identity."
    return None


def has_strong_caution_context(
    genres: list[str],
    raw_keywords: list[str],
    labels: list[str],
    display: dict[str, Any] | None,
) -> bool:
    context = " ".join(
        lower_text(value)
        for value in [
            *genres,
            *raw_keywords,
            *labels,
        ]
    )
    if any(hint in context for hint in STRONG_CAUTION_HINTS):
        return True
    if "tense" in context and any(
        hint in context for hint in TENSE_CAUTION_CONTEXT_HINTS
    ):
        return True
    if has_war_context(genres, context) and any(
        hint in context for hint in ("violence", "violent", "battle", "combat")
    ):
        return True
    return False


def low_mapping_density(raw_count: int, mapped_count: int) -> bool:
    return raw_count >= 8 and (mapped_count == 0 or mapped_count / raw_count < 0.25)


def low_mapping_density_severity(raw_count: int, mapped_count: int) -> str:
    if mapped_count <= 3:
        return "medium"
    if raw_count >= 20 and mapped_count <= 4:
        return "medium"
    if raw_count and mapped_count / raw_count < 0.15:
        return "medium"
    return "low"


def sparse_mapping_for_display_fallback(
    dimensions: set[str],
    signals: list[dict[str, Any]],
    raw_keywords: list[str],
) -> bool:
    if len(signals) < 4:
        return True
    if not {"audience_expectation", "topic_theme"} <= dimensions:
        return True
    return low_mapping_density(len(raw_keywords), len(signals))


def future_dimension_gaps_for_dimensions(dimensions: set[str]) -> list[str]:
    gaps = []
    if "content_caution_proxy" not in dimensions:
        gaps.append("content_caution_proxy")
    return gaps


def detect_mapping_issues(
    *,
    genres: list[str],
    raw_keywords: list[str],
    signals: list[dict[str, Any]],
    guidance: dict[str, Any] | None,
    display: dict[str, Any] | None,
    unmapped_keywords: list[str],
    subgenre_candidates: list[str],
    global_label_counts: Counter | None = None,
) -> list[MappingIssue]:
    issues: list[MappingIssue] = []
    labels = labels_from_signals(signals)
    grouped = signals_by_dimension(signals)
    dimensions = set(signal_dimensions_present(signals))
    global_label_counts = global_label_counts or Counter()

    if not signals:
        add_unique_issue(
            issues,
            issue(
                "MISSING_SOURCE_SIGNALS",
                "critical",
                "content_source_signals",
                "",
                "No active source signals are stored for this title.",
                "source_signal_quality_review",
            ),
        )

    if not guidance:
        add_unique_issue(
            issues,
            issue(
                "MISSING_WATCH_GUIDANCE",
                "critical",
                "content_watch_guidance",
                "",
                "No productized watch guidance is stored for this title.",
                "source_signal_quality_review",
            ),
        )

    for index, signal in enumerate(signals):
        dimension = clean_text(signal.get("dimension"))
        label = clean_text(signal.get("label"))
        value = clean_text(signal.get("value"))
        confidence = clean_text(signal.get("confidence"))
        if (
            dimension not in VALID_DIMENSIONS
            or confidence not in VALID_CONFIDENCE
            or not label
            or not value
        ):
            add_unique_issue(
                issues,
                issue(
                    "MALFORMED_SIGNAL_ROW",
                    "critical",
                    f"content_source_signals.{index}",
                    pipe_join([dimension, value, label, confidence]),
                    "Signal row is missing required fields or has an unknown dimension/confidence.",
                    "source_signal_quality_review",
                ),
            )
        signal_text = " ".join([dimension, value, label]).lower()
        for term in TECHNICAL_LEAK_TERMS:
            if term in signal_text:
                add_unique_issue(
                    issues,
                    issue(
                        "TECHNICAL_LEAK_IN_SIGNALS",
                        "critical",
                        f"content_source_signals.{index}",
                        term,
                        "Technical implementation wording appears in stored signal fields.",
                        "mapping_config_review",
                    ),
                )

    if "audience_expectation" not in dimensions:
        add_unique_issue(
            issues,
            issue(
                "EMPTY_AUDIENCE_EXPECTATION",
                "high",
                "signals_by_dimension.audience_expectation",
                "",
                "No audience expectation/identity signal is stored.",
                "mapping_config_review",
            ),
        )
    if "topic_theme" not in dimensions:
        add_unique_issue(
            issues,
            issue(
                "EMPTY_TOPIC_THEME",
                "high",
                "signals_by_dimension.topic_theme",
                "",
                "No topic/theme signal is stored.",
                "mapping_config_review",
            ),
        )
    if signals and labels and all(is_weak_label(label) for label in labels):
        add_unique_issue(
            issues,
            issue(
                "ALL_SIGNALS_GENERIC",
                "high",
                "content_source_signals.label",
                pipe_join(labels[:5]),
                "All mapped labels are too generic to support product-quality guidance.",
                "mapping_config_review",
            ),
        )

    sources = all_signal_sources(signals, guidance)
    if signals and sources and sources <= {"metadata_fallback"}:
        add_unique_issue(
            issues,
            issue(
                "ONLY_METADATA_FALLBACK",
                "high",
                "source_names",
                pipe_join(sorted(sources)),
                "Signals are entirely dependent on metadata fallback.",
                "mapping_config_review",
            ),
        )

    fallback = fallback_dependency(guidance, signals, display)
    if fallback["uses_curated_override"] and (
        len(signals) <= 3 or "audience_expectation" not in dimensions or "topic_theme" not in dimensions
    ):
        add_unique_issue(
            issues,
            issue(
                "CURATED_OVERRIDE_DEPENDENCY_HIGH",
                "high",
                "content_watch_guidance.curated_override_applied",
                "true",
                "Curated override is carrying a weak or sparse signal profile.",
                "curated_title_override_candidate",
            ),
        )
    if fallback["uses_backend_display_fallback"] and sparse_mapping_for_display_fallback(
        dimensions,
        signals,
        raw_keywords,
    ):
        add_unique_issue(
            issues,
            issue(
                "BACKEND_DISPLAY_FALLBACK_COMPENSATING",
                "low",
                "fallback_dependency.uses_backend_display_fallback",
                "true",
                "Backend display fallback appears to be compensating for sparse stored mapping.",
                "mapping_config_review",
            ),
        )

    conflict = detect_genre_signal_conflict(genres, labels)
    if conflict:
        add_unique_issue(
            issues,
            issue(
                "GENRE_SIGNAL_CONFLICT",
                "high",
                "genres",
                pipe_join(genres),
                conflict,
                "mapping_config_review",
            ),
        )

    missing_practical_dimensions = [
        (dimension, code)
        for dimension, code in (
            ("pacing", "MISSING_PACING_SIGNAL"),
            ("tone", "MISSING_TONE_SIGNAL"),
            ("mood", "MISSING_MOOD_SIGNAL"),
        )
        if dimension not in dimensions
    ]
    practical_missing_severity = (
        "medium" if len(missing_practical_dimensions) >= 2 else "low"
    )
    for dimension, code in missing_practical_dimensions:
        add_unique_issue(
            issues,
            issue(
                code,
                practical_missing_severity,
                f"signals_by_dimension.{dimension}",
                "",
                f"No {dimension.replace('_', ' ')} signal found.",
                "mapping_config_review",
            ),
        )

    for label in weak_labels(labels):
        add_unique_issue(
            issues,
            issue(
                "WEAK_LABEL",
                "low",
                "content_source_signals.label",
                label,
                "Mapped label is too weak or generic for product signal quality.",
                "mapping_config_review",
            ),
        )

    for label in labels:
        if global_label_counts.get(label, 0) >= 30 and is_weak_label(label):
            add_unique_issue(
                issues,
                issue(
                    "OVERUSED_LABEL",
                    "low",
                    "content_source_signals.label",
                    label,
                    "Vague label appears too often across the catalog.",
                    "mapping_config_review",
                ),
            )

    raw_count = len(raw_keywords)
    mapped_count = len(signals)
    if low_mapping_density(raw_count, mapped_count):
        add_unique_issue(
            issues,
            issue(
                "LOW_MAPPING_DENSITY",
                low_mapping_density_severity(raw_count, mapped_count),
                "raw_keywords",
                f"{mapped_count}/{raw_count}",
                "Many raw keywords produce relatively few mapped signals.",
                "mapping_config_review",
            ),
        )

    opportunity_keywords = [keyword for keyword in unmapped_keywords if keyword_opportunity(keyword)]
    if opportunity_keywords:
        add_unique_issue(
            issues,
            issue(
                "RAW_KEYWORDS_UNMAPPED",
                "medium",
                "provider_keywords.normalized_keyword_name",
                pipe_join(opportunity_keywords[:5]),
                "High-opportunity raw keywords are not mapped yet.",
                "mapping_config_review",
            ),
        )

    missing_subgenres = [
        candidate
        for candidate in subgenre_candidates
        if not candidate_already_covered(candidate, signals, display)
    ]
    if missing_subgenres:
        add_unique_issue(
            issues,
            issue(
                "SUBGENRE_MISSING",
                "low",
                "genre_quality.subgenre_candidates",
                pipe_join(missing_subgenres),
                "Genre/keyword context suggests a useful enriched subgenre label.",
                "genre_enrichment_needed",
            ),
        )

    label_text = " ".join(lower_text(label) for label in labels)
    if (
        has_strong_caution_context(genres, raw_keywords, labels, display)
        and "content_caution_proxy" not in dimensions
    ):
        add_unique_issue(
            issues,
            issue(
                "CONTENT_CAUTION_MISSING_FOR_INTENSE_TITLE",
                "low",
                "signals_by_dimension.content_caution_proxy",
                "",
                "Intense/darker signal profile has no content-caution proxy.",
                "mapping_config_review",
            ),
        )

    if raw_count < 3:
        add_unique_issue(
            issues,
            issue(
                "LOW_RAW_KEYWORD_COUNT",
                "low",
                "raw_keywords",
                str(raw_count),
                "Few raw keywords are available for this title.",
                "source_keyword_gap",
            ),
        )
    for label in labels:
        if lower_text(label) in BROAD_GENRE_LABELS:
            add_unique_issue(
                issues,
                issue(
                    "LABEL_CAN_BE_MORE_SPECIFIC",
                    "low",
                    "content_source_signals.label",
                    label,
                    "Signal label can likely be made more specific.",
                    "mapping_config_review",
                ),
            )

    return issues


def suggested_next_step(record: dict[str, Any], issues: list[MappingIssue]) -> str:
    if not issues:
        return "ready_for_catalog_expansion"
    codes = {item.code for item in issues}
    if all(item.severity == "low" for item in issues):
        return "ready_for_catalog_expansion"
    if codes & {"MISSING_SOURCE_SIGNALS", "MISSING_WATCH_GUIDANCE", "MALFORMED_SIGNAL_ROW"}:
        return "source_signal_quality_review"
    if codes & {
        "EMPTY_AUDIENCE_EXPECTATION",
        "EMPTY_TOPIC_THEME",
        "ALL_SIGNALS_GENERIC",
        "BACKEND_DISPLAY_FALLBACK_COMPENSATING",
        "MISSING_PACING_SIGNAL",
        "MISSING_TONE_SIGNAL",
        "MISSING_MOOD_SIGNAL",
        "RAW_KEYWORDS_UNMAPPED",
        "LOW_MAPPING_DENSITY",
        "WEAK_LABEL",
        "OVERUSED_LABEL",
    }:
        return "mapping_config_review"
    if codes & {"SUBGENRE_MISSING"}:
        return "genre_enrichment_needed"
    if codes & {"LOW_RAW_KEYWORD_COUNT"}:
        return "source_keyword_gap"
    if codes & {"CURATED_OVERRIDE_DEPENDENCY_HIGH"}:
        return "curated_title_override_candidate"
    return issues[0].suggested_action


def audit_mapping_record(
    content: dict[str, Any],
    *,
    genres: list[str] | None = None,
    raw_keywords: list[str] | None = None,
    signals: list[dict[str, Any]] | None = None,
    guidance: dict[str, Any] | None = None,
    display: dict[str, Any] | None = None,
    supporting_data: dict[str, Any] | None = None,
    mapped_keywords: set[str] | None = None,
    global_label_counts: Counter | None = None,
) -> dict[str, Any]:
    genres = unique_preserve_order(genres or [])
    raw_keywords = unique_preserve_order(raw_keywords or [])
    signals = signals or []
    mapped_keywords = mapped_keywords or set()
    grouped = signals_by_dimension(signals)
    present = signal_dimensions_present(signals)
    dimensions = set(present)
    missing = signal_dimensions_missing(signals)
    labels = labels_from_signals(signals)
    unmapped = unmapped_keywords_for_record(raw_keywords, mapped_keywords)
    candidates = detect_subgenre_candidates(genres, raw_keywords, signals, display)
    fallback = fallback_dependency(guidance, signals, display)
    issues = detect_mapping_issues(
        genres=genres,
        raw_keywords=raw_keywords,
        signals=signals,
        guidance=guidance,
        display=display,
        unmapped_keywords=unmapped,
        subgenre_candidates=candidates,
        global_label_counts=global_label_counts,
    )
    score = calculate_score(issues)
    grade = grade_for_score(score, issues)
    ready = mapping_ready_for(score, issues, dimensions)
    future_dimension_gaps = future_dimension_gaps_for_dimensions(dimensions)
    genre_quality = {
        "primary_genre": genres[0] if genres else None,
        "subgenre_candidates": candidates,
        "has_subgenre_candidate": bool(candidates),
        "no_subgenre_candidate": not bool(candidates),
        "is_too_generic": bool(
            genres
            and all(genre in BROAD_GENRES for genre in genres)
            and not candidates
        ),
    }
    overused = [
        label
        for label in labels
        if (global_label_counts or Counter()).get(label, 0) >= 30 and is_weak_label(label)
    ]

    record = {
        "content_id": content.get("id") or content.get("content_id"),
        "title": content.get("title"),
        "content_type": content.get("type") or content.get("content_type"),
        "year": content.get("year"),
        "mapping_quality_score": score,
        "grade": grade,
        "mapping_ready": ready,
        "review_required": not ready,
        "genres": genres,
        "raw_keyword_count": len(raw_keywords),
        "mapped_signal_count": len(signals),
        "signal_dimensions_present": present,
        "signal_dimensions_missing": missing,
        "signals_by_dimension": grouped,
        "genre_quality": genre_quality,
        "future_dimension_gaps": future_dimension_gaps,
        "supporting_data": supporting_data or {},
        "unmapped_keywords": unmapped,
        "weak_labels": weak_labels(labels),
        "overused_labels": unique_preserve_order(overused),
        "fallback_dependency": fallback,
        "issues": [item.as_dict() for item in issues],
        "issue_counts": issue_counts(issues),
    }
    record["suggested_next_step"] = suggested_next_step(record, issues)
    return record


def should_include_in_json(record: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.include_passing:
        return True
    if args.min_score is not None and record["mapping_quality_score"] < args.min_score:
        return True
    return record["review_required"]


def count_issue_codes(records: list[dict[str, Any]]) -> Counter:
    counter: Counter = Counter()
    for record in records:
        for item in record.get("issues") or []:
            counter[item["code"]] += 1
    return counter


def count_issue_severities(records: list[dict[str, Any]]) -> Counter:
    counter: Counter = Counter()
    for record in records:
        for severity, count in (record.get("issue_counts") or {}).items():
            counter[severity] += count
    return counter


def grade_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(record["grade"] for record in records)
    return {
        "excellent": counter.get("excellent", 0),
        "good": counter.get("good", 0),
        "needs_review": counter.get("needs_review", 0),
        "blocked": counter.get("blocked", 0),
    }


def primary_issue_codes(record: dict[str, Any], limit: int = 5) -> list[str]:
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    issues = sorted(
        record.get("issues") or [],
        key=lambda item: (severity_order.get(item["severity"], 99), item["code"]),
    )
    return [item["code"] for item in issues[:limit]]


def issue_severities(record: dict[str, Any]) -> list[str]:
    severities = {
        item["severity"]
        for item in record.get("issues") or []
    }
    return sorted(
        severities,
        key=lambda value: SEVERITIES.index(value) if value in SEVERITIES else 99,
    )


def top_issue_examples(records: list[dict[str, Any]], limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        for item in record.get("issues") or []:
            if len(examples[item["code"]]) >= limit:
                continue
            examples[item["code"]].append(
                {
                    "content_id": record["content_id"],
                    "title": record["title"],
                    "content_type": record["content_type"],
                    "score": record["mapping_quality_score"],
                    "field": item["field"],
                    "value": item["value"],
                    "message": item["message"],
                }
            )
    return dict(sorted(examples.items()))


def top_unmapped_keyword_opportunities(records: list[dict[str, Any]], limit: int = 25) -> list[dict[str, Any]]:
    counts: Counter = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for record in records:
        for keyword in record.get("unmapped_keywords") or []:
            opportunity = keyword_opportunity(keyword)
            if not opportunity:
                continue
            normalized = normalize_keyword_name(keyword)
            counts[normalized] += 1
            if len(examples[normalized]) < 5:
                examples[normalized].append(record.get("title") or "")

    rows = []
    for keyword, count in counts.most_common(limit):
        opportunity = keyword_opportunity(keyword) or {}
        rows.append(
            {
                "keyword": keyword,
                "count": count,
                "example_titles": examples[keyword],
                "suggested_dimension": opportunity.get("suggested_dimension"),
                "suggested_label": opportunity.get("suggested_label"),
            }
        )
    return rows


def label_counter(records: list[dict[str, Any]]) -> Counter:
    counter: Counter = Counter()
    for record in records:
        for values in (record.get("signals_by_dimension") or {}).values():
            counter.update(values)
    return counter


def top_overused_labels(records: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    counter = label_counter(records)
    return [
        {"label": label, "count": count}
        for label, count in counter.most_common(limit)
        if is_weak_label(label)
    ]


def top_weak_labels(records: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    counter: Counter = Counter()
    for record in records:
        counter.update(record.get("weak_labels") or [])
    return [
        {"label": label, "count": count}
        for label, count in counter.most_common(limit)
    ]


def signals_by_dimension_summary(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        dimension: sum(
            1 for record in records if dimension in record.get("signal_dimensions_present", [])
        )
        for dimension in DIMENSION_ORDER
    }


def titles_missing_by_dimension(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        dimension: sum(
            1 for record in records if dimension in record.get("signal_dimensions_missing", [])
        )
        for dimension in DIMENSION_ORDER
    }


def genre_quality_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_counter: Counter = Counter()
    too_generic = 0
    no_candidate = 0
    for record in records:
        quality = record.get("genre_quality") or {}
        if quality.get("is_too_generic"):
            too_generic += 1
        if quality.get("no_subgenre_candidate"):
            no_candidate += 1
        candidate_counter.update(quality.get("subgenre_candidates") or [])
    return {
        "titles_with_generic_genres_only": too_generic,
        "titles_without_subgenre_candidate": no_candidate,
        "top_subgenre_candidates": [
            {"label": label, "count": count}
            for label, count in candidate_counter.most_common(20)
        ],
    }


def future_dimension_gap_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter = Counter()
    for record in records:
        counter.update(record.get("future_dimension_gaps") or [])
    return dict(sorted(counter.items()))


def fallback_dependency_summary(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "uses_curated_override": sum(
            1 for record in records if record.get("fallback_dependency", {}).get("uses_curated_override")
        ),
        "uses_metadata_fallback": sum(
            1 for record in records if record.get("fallback_dependency", {}).get("uses_metadata_fallback")
        ),
        "uses_backend_display_fallback": sum(
            1 for record in records if record.get("fallback_dependency", {}).get("uses_backend_display_fallback")
        ),
    }


def build_summary(records: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    titles_seen = len(records)
    average_score = (
        round(sum(row["mapping_quality_score"] for row in records) / titles_seen, 1)
        if titles_seen
        else 0
    )
    weakest = sorted(
        records,
        key=lambda row: (row["mapping_quality_score"], row["title"] or ""),
    )[:10]

    return {
        "titles_seen": titles_seen,
        "titles_with_source_signals": sum(
            1 for row in records if row.get("mapped_signal_count", 0) > 0
        ),
        "average_mapping_quality_score": average_score,
        "mapping_ready_count": sum(1 for row in records if row["mapping_ready"]),
        "review_required_count": sum(1 for row in records if row["review_required"]),
        "grade_counts": grade_counts(records),
        "signals_by_dimension": signals_by_dimension_summary(records),
        "titles_missing_by_dimension": titles_missing_by_dimension(records),
        "top_unmapped_keywords": top_unmapped_keyword_opportunities(records),
        "top_overused_labels": top_overused_labels(records),
        "top_weak_labels": top_weak_labels(records),
        "genre_quality_summary": genre_quality_summary(records),
        "future_dimension_gap_counts": future_dimension_gap_counts(records),
        "fallback_dependency_summary": fallback_dependency_summary(records),
        "issue_counts_by_code": dict(sorted(count_issue_codes(records).items())),
        "issue_counts_by_severity": {
            severity: count_issue_severities(records).get(severity, 0)
            for severity in SEVERITIES
        },
        "weakest_titles": [
            {
                "content_id": row["content_id"],
                "title": row["title"],
                "content_type": row["content_type"],
                "mapping_quality_score": row["mapping_quality_score"],
                "grade": row["grade"],
                "primary_issue_codes": primary_issue_codes(row),
                "suggested_next_step": row["suggested_next_step"],
            }
            for row in weakest
        ],
        "top_issue_examples": top_issue_examples(records),
        "generated_at": generated_at,
        "db_write_performed": False,
    }


def csv_row(record: dict[str, Any]) -> dict[str, Any]:
    grouped = record.get("signals_by_dimension") or {}
    issues = record.get("issues") or []
    return {
        "content_id": record.get("content_id"),
        "title": record.get("title"),
        "content_type": record.get("content_type"),
        "year": record.get("year"),
        "mapping_quality_score": record.get("mapping_quality_score"),
        "grade": record.get("grade"),
        "mapping_ready": record.get("mapping_ready"),
        "review_required": record.get("review_required"),
        "genres": pipe_join(record.get("genres") or []),
        "raw_keyword_count": record.get("raw_keyword_count"),
        "mapped_signal_count": record.get("mapped_signal_count"),
        "signal_dimensions_present": pipe_join(record.get("signal_dimensions_present") or []),
        "signal_dimensions_missing": pipe_join(record.get("signal_dimensions_missing") or []),
        "audience_expectation": pipe_join(grouped.get("audience_expectation") or []),
        "topic_theme": pipe_join(grouped.get("topic_theme") or []),
        "mood": pipe_join(grouped.get("mood") or []),
        "tone": pipe_join(grouped.get("tone") or []),
        "pacing": pipe_join(grouped.get("pacing") or []),
        "content_caution_proxy": pipe_join(grouped.get("content_caution_proxy") or []),
        "unmapped_keywords": pipe_join(record.get("unmapped_keywords") or []),
        "weak_labels": pipe_join(record.get("weak_labels") or []),
        "overused_labels": pipe_join(record.get("overused_labels") or []),
        "uses_curated_override": record.get("fallback_dependency", {}).get("uses_curated_override"),
        "uses_metadata_fallback": record.get("fallback_dependency", {}).get("uses_metadata_fallback"),
        "uses_backend_display_fallback": record.get("fallback_dependency", {}).get("uses_backend_display_fallback"),
        "primary_issue_codes": pipe_join(primary_issue_codes(record)),
        "primary_issue_severities": pipe_join(issue_severities(record)),
        "suggested_next_step": record.get("suggested_next_step"),
    }


CSV_COLUMNS = [
    "content_id",
    "title",
    "content_type",
    "year",
    "mapping_quality_score",
    "grade",
    "mapping_ready",
    "review_required",
    "genres",
    "raw_keyword_count",
    "mapped_signal_count",
    "signal_dimensions_present",
    "signal_dimensions_missing",
    "audience_expectation",
    "topic_theme",
    "mood",
    "tone",
    "pacing",
    "content_caution_proxy",
    "unmapped_keywords",
    "weak_labels",
    "overused_labels",
    "uses_curated_override",
    "uses_metadata_fallback",
    "uses_backend_display_fallback",
    "primary_issue_codes",
    "primary_issue_severities",
    "suggested_next_step",
]


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow(csv_row(record))


def query_catalog_targets(connection, args: argparse.Namespace) -> list[dict[str, Any]]:
    where = []
    params: dict[str, Any] = {
        "limit": args.limit,
        "offset": args.offset,
    }
    query_suffix = ""

    if args.content_id:
        where.append("c.id IN :content_ids")
        params["content_ids"] = args.content_id
    if args.content_type != "all":
        where.append("c.content_type = :content_type")
        params["content_type"] = args.content_type

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    if args.limit is not None:
        query_suffix += "\nLIMIT :limit"
    if args.offset:
        query_suffix += "\nOFFSET :offset"

    query = text(f"""
        SELECT
            c.id,
            c.title,
            c.content_type,
            c.year,
            c.overview
        FROM content c
        {where_sql}
        ORDER BY c.content_type, c.title, c.id
        {query_suffix};
    """)
    if args.content_id:
        query = query.bindparams(bindparam("content_ids", expanding=True))

    result = connection.execute(query, params)
    return [dict(row) for row in result.mappings().all()]


def fetch_genres(connection, content_id: int) -> list[str]:
    rows = connection.execute(
        text(
            """
            SELECT g.name
            FROM content_genres cg
            JOIN genres g ON g.id = cg.genre_id
            WHERE cg.content_id = :content_id
            ORDER BY g.name;
            """
        ),
        {"content_id": content_id},
    ).mappings().all()
    return [row["name"] for row in rows]


def fetch_raw_keywords(connection, content_id: int) -> list[str]:
    rows = connection.execute(
        text(
            """
            SELECT pk.keyword_name
            FROM content_keywords ck
            JOIN provider_keywords pk ON pk.id = ck.keyword_id
            WHERE ck.content_id = :content_id
            ORDER BY pk.normalized_keyword_name;
            """
        ),
        {"content_id": content_id},
    ).mappings().all()
    return [row["keyword_name"] for row in rows]


def fetch_source_signals(connection, content_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        text(
            """
            SELECT
                dimension,
                value,
                label,
                confidence,
                source_names
            FROM content_source_signals
            WHERE content_id = :content_id
              AND is_active = TRUE
            ORDER BY dimension, label;
            """
        ),
        {"content_id": content_id},
    ).mappings().all()
    return [
        {
            "dimension": row["dimension"],
            "value": row["value"],
            "label": row["label"],
            "confidence": row["confidence"],
            "source_names": json_list(row["source_names"]),
        }
        for row in rows
    ]


def fetch_watch_guidance(connection, content_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        text(
            """
            SELECT
                content_id,
                keyword_counts,
                signal_sources,
                curated_override_applied,
                metadata_fallback_applied,
                storage_ready,
                frontend_ready
            FROM content_watch_guidance
            WHERE content_id = :content_id;
            """
        ),
        {"content_id": content_id},
    ).mappings().first()
    if not row:
        return None
    return {
        "content_id": row["content_id"],
        "keyword_counts": json_dict(row["keyword_counts"]),
        "signal_sources": json_list(row["signal_sources"]),
        "curated_override_applied": bool(row["curated_override_applied"]),
        "metadata_fallback_applied": bool(row["metadata_fallback_applied"]),
        "storage_ready": bool(row["storage_ready"]),
        "frontend_ready": bool(row["frontend_ready"]),
    }


def count_availability_entries(platforms: Any) -> int:
    if isinstance(platforms, list):
        return len(platforms)
    if isinstance(platforms, dict):
        return sum(
            len(value) if isinstance(value, list) else 1
            for value in platforms.values()
            if value
        )
    return 0


def fetch_detail_context(connection, content_id: int) -> dict[str, Any]:
    detail = get_content_details_service(content_id, connection)
    if not detail:
        return {
            "display": None,
            "supporting_data": {},
        }
    decision_layer = detail.get("decision_layer") or {}
    ratings = detail.get("ratings") or {}
    return {
        "display": decision_layer.get("display") if decision_layer else None,
        "supporting_data": {
            "unified_score": ratings.get("unified_score"),
            "source_count": ratings.get("source_count"),
            "scoring_source_count": ratings.get("scoring_source_count"),
            "availability_count": count_availability_entries(detail.get("platforms")),
        },
    }


def audit_catalog(connection, args: argparse.Namespace, mapped_keywords: set[str]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    label_counts: Counter = Counter()
    for target in query_catalog_targets(connection, args):
        content_id = target["id"]
        genres = fetch_genres(connection, content_id)
        raw_keywords = fetch_raw_keywords(connection, content_id)
        signals = fetch_source_signals(connection, content_id)
        guidance = fetch_watch_guidance(connection, content_id)
        detail_context = fetch_detail_context(connection, content_id)
        label_counts.update(labels_from_signals(signals))
        contexts.append(
            {
                "content": {
                    "id": target["id"],
                    "title": target["title"],
                    "content_type": target["content_type"],
                    "year": target["year"],
                    "overview": target.get("overview"),
                },
                "genres": genres,
                "raw_keywords": raw_keywords,
                "signals": signals,
                "guidance": guidance,
                "display": detail_context["display"],
                "supporting_data": detail_context["supporting_data"],
            }
        )

    return [
        audit_mapping_record(
            context["content"],
            genres=context["genres"],
            raw_keywords=context["raw_keywords"],
            signals=context["signals"],
            guidance=context["guidance"],
            display=context["display"],
            supporting_data=context["supporting_data"],
            mapped_keywords=mapped_keywords,
            global_label_counts=label_counts,
        )
        for context in contexts
    ]


def should_fail_run(summary: dict[str, Any], records: list[dict[str, Any]], args: argparse.Namespace) -> bool:
    if args.fail_on_critical and summary["issue_counts_by_severity"].get("critical", 0):
        return True
    if args.fail_under_score is not None and any(
        row["mapping_quality_score"] < args.fail_under_score for row in records
    ):
        return True
    return False


def build_detail_report(
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    args: argparse.Namespace,
    generated_at: str,
) -> dict[str, Any]:
    included_records = [
        record
        for record in records
        if should_include_in_json(record, args)
    ]
    return {
        "generated_at": generated_at,
        "db_write_performed": False,
        "filters": {
            "content_ids": args.content_id or [],
            "content_type": args.content_type,
            "limit": args.limit,
            "offset": args.offset,
            "min_score": args.min_score,
            "include_passing": args.include_passing,
        },
        "summary": summary,
        "items": included_records,
    }


def print_summary(summary: dict[str, Any], json_path: Path, csv_path: Path, summary_path: Path) -> None:
    print("Source signal mapping quality audit complete.")
    print("DB writes: none")
    print(f"Titles seen: {summary['titles_seen']}")
    print(f"Mapping ready: {summary['mapping_ready_count']}")
    print(f"Review required: {summary['review_required_count']}")
    print(f"Average score: {summary['average_mapping_quality_score']}")
    print(f"Critical issues: {summary['issue_counts_by_severity'].get('critical', 0)}")
    print(f"JSON report: {relative_path(json_path)}")
    print(f"CSV report: {relative_path(csv_path)}")
    print(f"Summary: {relative_path(summary_path)}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    database_url = get_database_url()
    if not database_url:
        print(
            f"ERROR: Missing {DATABASE_URL_ENV}. Export it before running this audit.",
            file=sys.stderr,
        )
        return 1

    json_path = resolve_path(args.output_json)
    csv_path = resolve_path(args.output_csv)
    summary_path = resolve_path(args.summary_output)
    generated_at = utc_now_iso()
    mapped_keywords = load_mapped_keywords()

    engine = create_engine(database_url)
    with engine.connect() as connection:
        records = audit_catalog(connection, args, mapped_keywords)

    summary = build_summary(records, generated_at)
    detail_report = build_detail_report(records, summary, args, generated_at)

    write_json(json_path, detail_report)
    write_csv(csv_path, records)
    write_json(summary_path, summary)
    print_summary(summary, json_path, csv_path, summary_path)

    return 1 if should_fail_run(summary, records, args) else 0


if __name__ == "__main__":
    raise SystemExit(main())
