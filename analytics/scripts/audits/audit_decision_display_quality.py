#!/usr/bin/env python3
"""
Audit product-facing decision display quality for local catalog content.

This script:
- reads local catalog rows through DATABASE_URL
- uses the backend content detail service so it audits real decision_layer.display output
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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, create_engine, text


from analytics.scripts.common.paths import REPO_ROOT, ensure_backend_import_path

ensure_backend_import_path()

from app.services.content_service import get_content_details_service  # noqa: E402
from app.services.decision_insight_formatter import (  # noqa: E402
    INSIGHT_ABOUT_PHRASES,
    INSIGHT_CONCEPT_ALIASES,
    insight_concept_family,
    insight_normalized,
)
from analytics.scripts.audits.decision_insight_report_metadata import (  # noqa: E402
    decision_insight_versions,
)


DATABASE_URL_ENV = "DATABASE_URL"
DEFAULT_JSON_OUTPUT = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "source_signals"
    / "decision_display_quality_report.json"
)
DEFAULT_CSV_OUTPUT = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "source_signals"
    / "decision_display_quality_report.csv"
)
DEFAULT_SUMMARY_OUTPUT = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "source_signals"
    / "run_reports"
    / "decision_display_quality_summary.json"
)

SEVERITY_PENALTIES = {
    "critical": 35,
    "high": 20,
    "medium": 10,
    "low": 4,
}
SEVERITIES = ("critical", "high", "medium", "low")
SOURCE_SIGNAL_REVIEW_ISSUE_CODES = {
    "SOURCE_SIGNAL_IDENTITY_METADATA_CONFLICT",
}

TECHNICAL_LEAK_TERMS = (
    "tmdb_keywords",
    "source_names",
    "mapping_version",
    "provider keyword",
    "source_signal",
    "source signal",
    "confidence",
)
RAW_KEYWORD_LEAK_TERMS = (
    "raw keyword",
    "keyword id",
    "provider keyword",
)
BLOCKED_PHRASES = (
    "tmdb_keywords",
    "source_names",
    "mapping_version",
    "provider keyword",
    "source_signal",
    "source signal",
    "all themes",
    "complex story",
    "bleak mood",
    "built around heist story",
    "built around spy story",
    "built around eerie",
    "warm corruption story",
    "heavier watch assassin story",
    "jiohotstar viewers",
    "netflix viewers",
    "prime video viewers",
    "platform viewers",
    "availability viewers",
    "serialized drama viewers",
)
PLATFORM_IDENTITY_TERMS = (
    "jiohotstar viewers",
    "netflix viewers",
    "prime video viewers",
    "amazon prime video viewers",
    "platform viewers",
    "availability viewers",
    "serialized drama viewers",
    "streaming viewers",
)
PLATFORM_NAMES = (
    "jiohotstar",
    "netflix",
    "prime video",
    "amazon prime video",
)
FEEL_THEME_VALUES = {
    "eerie",
    "tense",
    "bleak",
    "warm",
    "cynical",
    "darkly funny",
    "dark",
    "foreboding",
    "surreal",
    "thoughtful",
    "intense",
}
GENERIC_IDENTITIES = {
    "story",
    "drama",
    "complex story",
    "heavier watch",
    "serious story",
    "content",
}
GENERIC_THEMES = {
    "story",
    "stories",
    "drama",
    "content",
    "all themes",
}
BAD_BUILT_AROUND_TARGETS = (
    "tense",
    "eerie",
    "bleak",
    "darkly funny",
    "warm",
    "heist story",
    "spy story",
    "drama",
    "story",
)
PRIMARY_INSIGHT_SPOILER_TERMS = (
    "death of ",
    "secret identity",
    "surprise ending",
    "plot twist",
    "suicide",
)
PRIMARY_INSIGHT_GENERIC_PATTERNS = (
    r"^an? (?:serious |emotional |light |dark )?(?:drama|story|documentary)\.?$",
    r"^an? music-driven story(?:\s|\.|$)",
)
PRIMARY_INSIGHT_RAW_GRAMMAR_PATTERNS = (
    r"\bbuilt around (?:light|dark|serious|emotional|eerie|foreboding)\b",
    r"\babout (?:light|dark tone|serious tone)\b",
    r"\bbuilt around [^,.]+ story\b",
)
WEAK_CAUTION_PATTERNS = (
    "better suited for viewers comfortable with darker or more intense stories",
    "may feel complex on first watch",
    "expect a more intense watch",
)


@dataclass(frozen=True)
class DisplayIssue:
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


@dataclass
class AuditResult:
    record: dict[str, Any]
    issues: list[DisplayIssue] = field(default_factory=list)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit current decision_layer.display quality for local catalog content."
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
        "--batch-size",
        type=positive_int,
        default=100,
        help="Rows fetched from the catalog cursor at a time. Defaults to 100.",
    )
    parser.add_argument(
        "--min-score",
        type=score_value,
        default=None,
        help="Only include titles with display_quality_score below this score in JSON details.",
    )
    parser.add_argument(
        "--include-passing",
        action="store_true",
        help="Include clean/passing titles in JSON details.",
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


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def lower_text(value: Any) -> str:
    return clean_text(value).lower()


def pipe_join(values: list[Any]) -> str:
    return " | ".join(clean_text(value) for value in values or [] if clean_text(value))


def flatten_public_strings(value: Any) -> list[tuple[str, str]]:
    strings: list[tuple[str, str]] = []

    def walk(current: Any, path: str) -> None:
        if isinstance(current, str):
            if current.strip():
                strings.append((path, current.strip()))
            return
        if isinstance(current, list):
            for index, item in enumerate(current):
                walk(item, f"{path}.{index}" if path else str(index))
            return
        if isinstance(current, dict):
            for key, item in current.items():
                walk(item, f"{path}.{key}" if path else key)

    walk(value, "")
    return strings


def display_text(display: dict[str, Any] | None) -> str:
    return " ".join(
        value
        for field, value in flatten_public_strings(display or {})
        if not field.startswith("_insight_plan")
    ).lower()


def non_access_display_text(display: dict[str, Any] | None) -> str:
    if not display:
        return ""
    values = []
    for field, value in flatten_public_strings(display):
        if field.startswith("supporting_facts") or field.startswith("_insight_plan"):
            continue
        values.append(value)
    return " ".join(values).lower()


def issue(
    code: str,
    severity: str,
    field: str,
    value: Any,
    message: str,
    suggested_action: str,
) -> DisplayIssue:
    return DisplayIssue(
        code=code,
        severity=severity,
        field=field,
        value=clean_text(value),
        message=message,
        suggested_action=suggested_action,
    )


def add_unique_issue(issues: list[DisplayIssue], new_issue: DisplayIssue) -> None:
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


def issue_counts(issues: list[DisplayIssue]) -> dict[str, int]:
    counts = {severity: 0 for severity in SEVERITIES}
    for item in issues:
        counts[item.severity] = counts.get(item.severity, 0) + 1
    return counts


def calculate_score(issues: list[DisplayIssue]) -> int:
    score = 100
    for item in issues:
        score -= SEVERITY_PENALTIES.get(item.severity, 0)
    return max(0, min(100, score))


def grade_for_score(score: int, issues: list[DisplayIssue]) -> str:
    if any(item.severity == "critical" for item in issues) or score < 60:
        return "blocked"
    if score >= 90:
        return "excellent"
    if score >= 80:
        return "good"
    return "needs_review"


def display_ready_for(score: int, issues: list[DisplayIssue]) -> bool:
    return score >= 80 and not any(
        item.severity in {"critical", "high"} for item in issues
    )


def display_issues(issues: list[DisplayIssue]) -> list[DisplayIssue]:
    return [item for item in issues if item.code not in SOURCE_SIGNAL_REVIEW_ISSUE_CODES]


def source_signal_review_issues(issues: list[DisplayIssue]) -> list[DisplayIssue]:
    return [item for item in issues if item.code in SOURCE_SIGNAL_REVIEW_ISSUE_CODES]


def singular_key(label: str) -> str:
    lower_label = lower_text(label)
    if lower_label.endswith("ies"):
        return f"{lower_label[:-3]}y"
    if lower_label.endswith("s"):
        return lower_label[:-1]
    return lower_label


def normalized_case_token(token: str) -> str:
    return token.strip(":-,.()[]{}")


def is_world_war_token(index: int, words: list[str]) -> bool:
    if len(words) < 3:
        return False
    normalized_words = [normalized_case_token(word) for word in words]
    return (
        normalized_words[0] == "World"
        and normalized_words[1] == "War"
        and normalized_words[2] in {"I", "II"}
        and index in {1, 2}
    )


def is_allowed_uppercase_token(token: str, index: int, words: list[str]) -> bool:
    stripped = normalized_case_token(token)
    if not stripped:
        return True
    if is_world_war_token(index, words):
        return True
    if stripped in {"AI", "TV", "U/A", "PG-13", "TV-MA", "IMDb", "TMDb"}:
        return True
    if stripped.startswith("Sci-fi") or stripped.startswith("Post-apocalyptic"):
        return True
    return False


def has_case_inconsistency(label: str) -> bool:
    words = clean_text(label).split()
    if len(words) < 2:
        return False
    for index, word in enumerate(words[1:], start=1):
        stripped = normalized_case_token(word)
        if not stripped or is_allowed_uppercase_token(stripped, index, words):
            continue
        if stripped[:1].isupper():
            return True
    return False


def is_repetitive_primary(primary: str) -> bool:
    lower_primary = lower_text(primary)
    repeated_patterns = (
        r"\b(\w+)\s+\1\b",
        r"\binvestigation\b.*\binvestigation\b",
        r"\bstory\b.*\bstory\b",
    )
    return any(re.search(pattern, lower_primary) for pattern in repeated_patterns)


def bad_built_around_target(primary: str) -> str | None:
    lower_primary = lower_text(primary)
    match = re.search(r"built around ([^,.]+)", lower_primary)
    if not match:
        return None
    target = match.group(1).strip()
    for bad_target in BAD_BUILT_AROUND_TARGETS:
        if target == bad_target or target.startswith(f"{bad_target} "):
            return target
    return None


def primary_template_family(primary: str, display: dict[str, Any] | None = None) -> str:
    plan = (display or {}).get("_insight_plan") or {}
    if plan.get("template_family"):
        return str(plan["template_family"])
    lower_primary = lower_text(primary)
    if " built around " in lower_primary:
        return "built_around"
    if " examining " in lower_primary:
        return "documentary_examination"
    if " exploring " in lower_primary:
        return "character_exploration"
    if " driven by " in lower_primary:
        return "experience_driven"
    if " that blends " in lower_primary:
        return "hybrid_blend"
    if " shaped by " in lower_primary:
        return "layered_exploration"
    if " where " in lower_primary:
        return "identity_conflict"
    if " about " in lower_primary:
        return "identity_about"
    return "identity_only"


def primary_concept_duplicates(
    primary: str,
    identity: list[str],
    themes: list[str],
) -> list[str]:
    normalized_primary = insight_normalized(primary)
    families = defaultdict(list)
    for label in identity + themes:
        normalized_label = insight_normalized(label)
        phrase = insight_normalized(INSIGHT_ABOUT_PHRASES.get(normalized_label, label))
        family = insight_concept_family(label)
        family_aliases = {
            insight_normalized(alias)
            for alias in INSIGHT_CONCEPT_ALIASES.get(family, set())
        }
        if (
            normalized_label not in normalized_primary
            and phrase not in normalized_primary
            and not any(
                alias and alias in normalized_primary
                for alias in family_aliases
            )
        ):
            continue
        families[family].append(label)
    return sorted(
        family
        for family, labels in families.items()
        if family and len({insight_normalized(label) for label in labels}) > 1
    )


def has_primary_punctuation_problem(primary: str) -> bool:
    return bool(
        re.search(r",\s+and\b", primary)
        or re.search(r"\s+[,.!?]", primary)
        or re.search(r"[,.!?]{2,}", primary)
        or primary.count("(") != primary.count(")")
    )


def primary_repeated_word(primary: str) -> str | None:
    ignored = {
        "a",
        "an",
        "and",
        "about",
        "the",
        "that",
        "through",
        "with",
    }
    words = re.findall(r"[a-z][a-z-]+", lower_text(primary))
    for index, word in enumerate(words):
        if word in ignored or len(word) < 4:
            continue
        if word in words[index + 1 : index + 7]:
            return word
    return None


def primary_chip_repetition(primary: str, profile: dict[str, Any]) -> bool:
    normalized_primary = insight_normalized(primary)
    for label in (
        (profile.get("identity") or [])
        + (profile.get("themes") or [])
        + (profile.get("feel") or [])
    ):
        normalized = insight_normalized(label)
        if normalized and normalized_primary.count(normalized) > 1:
            return True
    return False


def has_adjective_stack(primary: str) -> bool:
    return bool(
        re.search(
            r"^an?\s+(?:fast-paced|fast-moving|slow-burn|measured|quiet|tense|bleak|warm|dark|serious|light|gentle)\s+"
            r"(?:tense|bleak|warm|dark|serious|light|gentle|restrained|quiet)\b",
            lower_text(primary),
        )
    )


def has_awkward_pacing(primary: str) -> bool:
    value = lower_text(primary)
    return " momentum" in value or bool(
        re.search(r"\b(?:gentle|slow-burn|fast-paced) pacing (?:rhythm|momentum)\b", value)
    )


def has_conjunction_chain(primary: str) -> bool:
    return len(re.findall(r"\band\b", lower_text(primary))) >= 3


def has_raw_taxonomy_copy(primary: str) -> bool:
    value = lower_text(primary)
    return any(term in value for term in ("animation style", "anime style"))


def detect_display_issues(display: dict[str, Any] | None) -> list[DisplayIssue]:
    issues: list[DisplayIssue] = []

    if not display:
        return [
            issue(
                "MISSING_DISPLAY",
                "critical",
                "decision_layer.display",
                "",
                "Decision display is missing.",
                "source_signal_quality_review",
            )
        ]

    profile = display.get("profile") or {}
    primary = clean_text(display.get("primary_insight"))
    identity = profile.get("identity") or []
    themes = profile.get("themes") or []
    feel = profile.get("feel") or []
    pace = clean_text(profile.get("pace"))
    best_for = profile.get("best_for") or []
    consider_first = profile.get("consider_first") or []
    supporting_facts = display.get("supporting_facts") or []
    all_text = display_text(display)
    non_access_text = non_access_display_text(display)

    if not primary:
        add_unique_issue(
            issues,
            issue(
                "MISSING_PRIMARY_INSIGHT",
                "critical",
                "primary_insight",
                "",
                "Primary insight is missing.",
                "backend_display_rule",
            ),
        )

    for term in TECHNICAL_LEAK_TERMS:
        if term in all_text:
            add_unique_issue(
                issues,
                issue(
                    "TECHNICAL_LEAK",
                    "critical",
                    "decision_layer.display",
                    term,
                    "Technical implementation wording leaked into public display.",
                    "backend_display_rule",
                ),
            )

    for term in RAW_KEYWORD_LEAK_TERMS:
        if term in all_text:
            add_unique_issue(
                issues,
                issue(
                    "RAW_KEYWORD_LEAK",
                    "critical",
                    "decision_layer.display",
                    term,
                    "Raw keyword/provider wording leaked into public display.",
                    "backend_display_rule",
                ),
            )

    for phrase in BLOCKED_PHRASES:
        if phrase in all_text:
            add_unique_issue(
                issues,
                issue(
                    "BLOCKED_PHRASE",
                    "critical",
                    "decision_layer.display",
                    phrase,
                    "Blocked public-display phrase appears in the compact display.",
                    "backend_display_rule",
                ),
            )

    for term in PLATFORM_IDENTITY_TERMS:
        if term in non_access_text:
            add_unique_issue(
                issues,
                issue(
                    "PLATFORM_IDENTITY_LEAK",
                    "critical",
                    "decision_layer.display.profile",
                    term,
                    "Platform/viewer wording appears as watch identity.",
                    "backend_display_rule",
                ),
            )

    for platform in PLATFORM_NAMES:
        if platform in non_access_text:
            add_unique_issue(
                issues,
                issue(
                    "PLATFORM_IDENTITY_LEAK",
                    "critical",
                    "decision_layer.display.profile",
                    platform,
                    "Platform name appears outside explicit Access facts.",
                    "backend_display_rule",
                ),
            )

    if not identity:
        add_unique_issue(
            issues,
            issue(
                "EMPTY_IDENTITY",
                "high",
                "profile.identity",
                "",
                "Compact profile has no identity labels.",
                "source_signal_quality_review",
            ),
        )
    elif lower_text(identity[0]) in GENERIC_IDENTITIES:
        add_unique_issue(
            issues,
            issue(
                "GENERIC_DOMINANT_IDENTITY",
                "high",
                "profile.identity",
                identity[0],
                "Dominant identity is too generic for public display.",
                "mapping_config_review",
            ),
        )

    if not themes and any(term in lower_text(primary) for term in ("story", "drama", "content")):
        add_unique_issue(
            issues,
            issue(
                "EMPTY_THEMES_WITH_GENERIC_PRIMARY",
                "high",
                "profile.themes",
                "",
                "Primary insight is generic and no theme clarifies the watch fit.",
                "source_signal_quality_review",
            ),
        )

    identity_lowers = {lower_text(value) for value in identity}
    for theme in themes:
        lower_theme = lower_text(theme)
        if lower_theme in FEEL_THEME_VALUES:
            add_unique_issue(
                issues,
                issue(
                    "FEEL_USED_AS_THEME",
                    "high",
                    "profile.themes",
                    theme,
                    "Mood/tone label is being used as an aboutness theme.",
                    "backend_display_rule",
                ),
            )
        if lower_theme in identity_lowers or any(
            lower_theme in identity_value or identity_value in lower_theme
            for identity_value in identity_lowers
            if identity_value
        ):
            add_unique_issue(
                issues,
                issue(
                    "IDENTITY_REPEATED_AS_THEME",
                    "high",
                    "profile.themes",
                    theme,
                    "Theme repeats a compact identity label.",
                    "backend_display_rule",
                ),
            )

    if primary:
        plan = display.get("_insight_plan") or {}
        validation_errors = plan.get("validation_errors") or []
        primary_identity_plan = plan.get("primary_identity") or {}
        primary_identity_trust_tier = int(
            primary_identity_plan.get("trust_tier") or 0
        )
        identity_rejections = [
            item
            for item in plan.get("rejected_candidates") or []
            if item.get("role") == "primary_identity"
        ]
        source_conflicts = [
            item
            for item in identity_rejections
            if item.get("reason") == "identity_metadata_conflict"
            and str(item.get("source") or "").startswith("source_signal:")
        ]
        selected_identity_conflicts = [
            item
            for item in identity_rejections
            if item.get("reason") == "identity_metadata_conflict"
            and insight_normalized(item.get("candidate"))
            == insight_normalized(primary_identity_plan.get("text"))
            and item.get("source") == primary_identity_plan.get("source")
        ]
        if selected_identity_conflicts:
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_IDENTITY_METADATA_CONFLICT",
                    "critical",
                    "insight_plan.primary_identity",
                    primary_identity_plan.get("text") or "",
                    "Selected primary identity conflicts with title metadata.",
                    "backend_display_rule",
                ),
            )
        if source_conflicts:
            add_unique_issue(
                issues,
                issue(
                    "SOURCE_SIGNAL_IDENTITY_METADATA_CONFLICT",
                    "high",
                    "insight_plan.rejected_candidates",
                    " | ".join(str(item.get("candidate")) for item in source_conflicts),
                    "One or more source-signal identities conflict with title metadata and were rejected.",
                    "mapping_config_review",
                ),
            )
        if primary_identity_trust_tier >= 6:
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_IDENTITY_WEAK_PROVENANCE",
                    "high",
                    "insight_plan.primary_identity",
                    primary_identity_plan.get("text") or "",
                    "Primary identity comes from a low-trust topic or metadata fallback.",
                    "source_signal_quality_review",
                ),
            )
        if (
            primary_identity_plan.get("source") == "inferred_context"
            and primary_identity_trust_tier >= 5
        ):
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_IDENTITY_INCIDENTAL_CONTEXT",
                    "high",
                    "insight_plan.primary_identity",
                    primary_identity_plan.get("text") or "",
                    "Primary identity relies on inferred context without explicit premise-level support.",
                    "backend_display_rule",
                ),
            )
        if (
            plan.get("curated_override_applied")
            and plan.get("curated_identity_available")
            and "curated_override" not in str(primary_identity_plan.get("source") or "")
        ):
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_IDENTITY_CURATED_OVERRIDE_IGNORED",
                    "high",
                    "insight_plan.primary_identity",
                    primary_identity_plan.get("text") or "",
                    "A compatible curated identity was available but not selected.",
                    "backend_display_rule",
                ),
            )
        if validation_errors:
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_UNSUPPORTED_COMPONENT",
                    "critical",
                    "primary_insight",
                    " | ".join(str(value) for value in validation_errors),
                    "Insight plan contains an unsupported or invalid component.",
                    "backend_display_rule",
                ),
            )
        if any(
            re.search(pattern, lower_text(primary))
            for pattern in PRIMARY_INSIGHT_GENERIC_PATTERNS
        ):
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_GENERIC",
                    "high",
                    "primary_insight",
                    primary,
                    "Primary insight is generic despite the available display context.",
                    "backend_display_rule",
                ),
            )
        duplicate_families = (
            ["insight_plan"]
            if "duplicate_concept_family" in validation_errors
            else (
                []
                if plan
                else primary_concept_duplicates(primary, identity, themes)
            )
        )
        if duplicate_families:
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_DUPLICATE_CONCEPTS",
                    "high",
                    "primary_insight",
                    " | ".join(duplicate_families),
                    "Primary insight repeats equivalent product concepts.",
                    "backend_display_rule",
                ),
            )
        if any(
            re.search(pattern, lower_text(primary))
            for pattern in PRIMARY_INSIGHT_RAW_GRAMMAR_PATTERNS
        ):
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_RAW_LABEL_GRAMMAR",
                    "high",
                    "primary_insight",
                    primary,
                    "Primary insight inserts a canonical label into an unsupported grammatical role.",
                    "backend_display_rule",
                ),
            )
        repeated_word = primary_repeated_word(primary)
        if repeated_word:
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_REPEATED_WORD",
                    "high",
                    "primary_insight",
                    repeated_word,
                    "Primary insight repeats a content word too closely.",
                    "backend_display_rule",
                ),
            )
        if has_primary_punctuation_problem(primary):
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_PUNCTUATION",
                    "high",
                    "primary_insight",
                    primary,
                    "Primary insight contains awkward or invalid punctuation.",
                    "backend_display_rule",
                ),
            )
        if has_adjective_stack(primary):
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_ADJECTIVE_STACK",
                    "high",
                    "primary_insight",
                    primary,
                    "Primary insight stacks pacing and tone adjectives awkwardly.",
                    "backend_display_rule",
                ),
            )
        if has_awkward_pacing(primary):
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_AWKWARD_PACING",
                    "high",
                    "primary_insight",
                    primary,
                    "Primary insight uses an awkward or generic pacing construction.",
                    "backend_display_rule",
                ),
            )
        if has_conjunction_chain(primary):
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_CONJUNCTION_CHAIN",
                    "high",
                    "primary_insight",
                    primary,
                    "Primary insight chains too many conjunctions.",
                    "backend_display_rule",
                ),
            )
        if has_raw_taxonomy_copy(primary):
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_RAW_TAXONOMY",
                    "high",
                    "primary_insight",
                    primary,
                    "Primary insight exposes an internal taxonomy label as product copy.",
                    "backend_display_rule",
                ),
            )
        if any(term in lower_text(primary) for term in PRIMARY_INSIGHT_SPOILER_TERMS):
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_SPOILER_RISK",
                    "critical",
                    "primary_insight",
                    primary,
                    "Primary insight may expose spoiler-sensitive plot information.",
                    "mapping_config_review",
                ),
            )
        if primary_chip_repetition(primary, profile):
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_CHIP_REPETITION",
                    "low",
                    "primary_insight",
                    primary,
                    "Primary insight restates too many compact profile labels.",
                    "backend_display_rule",
                ),
            )
        primary_identity = identity[0] if identity else ""
        if (
            insight_normalized(primary_identity) in GENERIC_IDENTITIES
            or (
                len(insight_normalized(primary_identity).split()) <= 1
                and insight_normalized(primary_identity)
                in {"drama", "story", "documentary", "comedy"}
            )
        ):
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_LOW_SPECIFICITY",
                    "medium",
                    "profile.identity",
                    primary_identity,
                    "Primary insight leads with a low-specificity identity.",
                    "backend_display_rule",
                ),
            )
        if (
            plan
            and (plan.get("primary_identity") or {}).get("source")
            in {"display_profile", "metadata_fallback"}
            and not plan.get("primary_differentiator")
        ):
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_FALLBACK_ONLY",
                    "medium",
                    "primary_insight",
                    primary,
                    "Primary insight relies only on fallback identity without a supported differentiator.",
                    "source_signal_quality_review",
                ),
            )
        if len(primary) > 180:
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_TOO_LONG",
                    "high",
                    "primary_insight",
                    primary,
                    "Primary insight is too long for compact display.",
                    "backend_display_rule",
                ),
            )
        plan_identity = (plan or {}).get("primary_identity") or {}
        normalized_plan_identity = insight_normalized(plan_identity.get("text"))
        has_specific_supported_identity = bool(
            plan_identity.get("supported") is not False
            and len(normalized_plan_identity.split()) >= 2
            and normalized_plan_identity not in GENERIC_IDENTITIES
            and normalized_plan_identity
            not in {"comedy drama", "documentary viewing", "generic drama"}
        )
        if len(primary) < 28 and not has_specific_supported_identity:
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_TOO_SHORT",
                    "high",
                    "primary_insight",
                    primary,
                    "Primary insight is too short to be useful.",
                    "backend_display_rule",
                ),
            )
        if is_repetitive_primary(primary):
            add_unique_issue(
                issues,
                issue(
                    "PRIMARY_INSIGHT_REPETITIVE",
                    "high",
                    "primary_insight",
                    primary,
                    "Primary insight repeats key wording.",
                    "backend_display_rule",
                ),
            )
        bad_target = bad_built_around_target(primary)
        if bad_target:
            add_unique_issue(
                issues,
                issue(
                    "BAD_BUILT_AROUND_TARGET",
                    "high",
                    "primary_insight",
                    bad_target,
                    "Primary insight builds around a mood, setting, or identity-like label.",
                    "backend_display_rule",
                ),
            )

    for theme in themes:
        lower_theme = lower_text(theme)
        if lower_theme in GENERIC_THEMES:
            add_unique_issue(
                issues,
                issue(
                    "GENERIC_THEME",
                    "medium",
                    "profile.themes",
                    theme,
                    "Theme is too generic for public display.",
                    "mapping_config_review",
                ),
            )
    if themes and lower_text(themes[0]).endswith(" setting") and len(themes) > 1:
        add_unique_issue(
            issues,
            issue(
                "SETTING_DOMINATES_THEME",
                "medium",
                "profile.themes",
                themes[0],
                "Setting context is dominating stronger theme labels.",
                "backend_display_rule",
            ),
        )

    seen_best_for: dict[str, str] = {}
    for label in best_for:
        key = singular_key(label)
        if key in seen_best_for:
            add_unique_issue(
                issues,
                issue(
                    "DUPLICATE_BEST_FOR",
                    "medium",
                    "profile.best_for",
                    label,
                    "Best-for labels contain singular/plural duplicates.",
                    "backend_display_rule",
                ),
            )
        seen_best_for[key] = label
        if has_case_inconsistency(label):
            add_unique_issue(
                issues,
                issue(
                    "BEST_FOR_CASE_INCONSISTENCY",
                    "medium",
                    "profile.best_for",
                    label,
                    "Best-for label casing feels inconsistent with product copy.",
                    "backend_display_rule",
                ),
            )

    if len(identity) > 3:
        add_unique_issue(
            issues,
            issue(
                "TOO_MANY_IDENTITY_LABELS",
                "medium",
                "profile.identity",
                pipe_join(identity),
                "Too many identity labels for compact display.",
                "frontend_suppression_only",
            ),
        )
    if len(themes) > 3:
        add_unique_issue(
            issues,
            issue(
                "TOO_MANY_THEME_LABELS",
                "medium",
                "profile.themes",
                pipe_join(themes),
                "Too many theme labels for compact display.",
                "frontend_suppression_only",
            ),
        )
    if len(feel) > 2:
        add_unique_issue(
            issues,
            issue(
                "TOO_MANY_FEEL_LABELS",
                "medium",
                "profile.feel",
                pipe_join(feel),
                "Too many feel labels for compact display.",
                "frontend_suppression_only",
            ),
        )

    lower_feel = {lower_text(value) for value in feel}
    if "warm" in lower_feel and "cynical" in lower_feel and not any(
        term in all_text for term in ("satire", "satirical", "darkly funny", "dark comedy")
    ):
        add_unique_issue(
            issues,
            issue(
                "CONFLICTING_FEEL_LABELS",
                "medium",
                "profile.feel",
                pipe_join(feel),
                "Feel labels conflict without satire/dark-comedy context.",
                "backend_display_rule",
            ),
        )

    for caution in consider_first:
        if any(pattern in lower_text(caution) for pattern in WEAK_CAUTION_PATTERNS):
            add_unique_issue(
                issues,
                issue(
                    "WEAK_CAUTION",
                    "medium",
                    "profile.consider_first",
                    caution,
                    "Consider-first copy is generic and should be more specific.",
                    "backend_display_rule",
                ),
            )

    if not supporting_facts:
        add_unique_issue(
            issues,
            issue(
                "SUPPORTING_FACTS_MISSING",
                "medium",
                "supporting_facts",
                "",
                "No compact supporting facts are available.",
                "metadata_enrichment_needed",
            ),
        )

    if primary and 150 < len(primary) <= 180:
        add_unique_issue(
            issues,
            issue(
                "PRIMARY_INSIGHT_CAN_BE_TIGHTER",
                "low",
                "primary_insight",
                primary,
                "Primary insight is valid but could be tighter.",
                "backend_display_rule",
            ),
        )
    if not pace:
        add_unique_issue(
            issues,
            issue(
                "NO_PACE",
                "low",
                "profile.pace",
                "",
                "No compact pace signal is available.",
                "source_signal_quality_review",
            ),
        )
    if (
        lower_feel & {"intense", "high-stakes", "foreboding", "bleak"}
        and not consider_first
    ):
        add_unique_issue(
            issues,
            issue(
                "NO_CONSIDER_FIRST_FOR_INTENSE_TITLE",
                "low",
                "profile.consider_first",
                "",
                "Intense or darker profile has no mild consider-first note.",
                "mapping_config_review",
            ),
        )
    if len(supporting_facts) > 4:
        add_unique_issue(
            issues,
            issue(
                "SUPPORTING_FACTS_TOO_MANY",
                "low",
                "supporting_facts",
                str(len(supporting_facts)),
                "Too many supporting facts for compact display.",
                "frontend_suppression_only",
            ),
        )

    return issues


def suggested_next_step(issues: list[DisplayIssue]) -> str:
    if not issues:
        return "none"
    codes = {item.code for item in issues}
    actions = [item.suggested_action for item in issues]

    if "MISSING_DISPLAY" in codes or "MISSING_PRIMARY_INSIGHT" in codes:
        return "source_signal_quality_review"
    if codes & {
        "TECHNICAL_LEAK",
        "RAW_KEYWORD_LEAK",
        "PLATFORM_IDENTITY_LEAK",
        "BLOCKED_PHRASE",
        "BAD_BUILT_AROUND_TARGET",
        "PRIMARY_INSIGHT_REPETITIVE",
        "PRIMARY_INSIGHT_DUPLICATE_CONCEPTS",
        "PRIMARY_INSIGHT_FALLBACK_ONLY",
        "PRIMARY_INSIGHT_GENERIC",
        "PRIMARY_INSIGHT_LOW_SPECIFICITY",
        "PRIMARY_INSIGHT_PUNCTUATION",
        "PRIMARY_INSIGHT_RAW_LABEL_GRAMMAR",
        "PRIMARY_INSIGHT_REPEATED_WORD",
        "PRIMARY_INSIGHT_TEMPLATE_OVERUSE",
        "PRIMARY_INSIGHT_UNSUPPORTED_COMPONENT",
    }:
        return "backend_display_rule"
    if codes & {
        "GENERIC_DOMINANT_IDENTITY",
        "GENERIC_THEME",
        "FEEL_USED_AS_THEME",
        "IDENTITY_REPEATED_AS_THEME",
    }:
        return "mapping_config_review"
    if codes & {"SUPPORTING_FACTS_MISSING"}:
        return "metadata_enrichment_needed"
    if all(action == "frontend_suppression_only" for action in actions):
        return "frontend_suppression_only"
    if any(item.severity in {"high", "medium"} for item in issues):
        return "curated_title_override_candidate"
    return actions[0] if actions else "none"


def normalized_profile(display: dict[str, Any] | None) -> dict[str, Any]:
    profile = (display or {}).get("profile") or {}
    return {
        "identity": profile.get("identity") or [],
        "themes": profile.get("themes") or [],
        "feel": profile.get("feel") or [],
        "pace": profile.get("pace"),
        "best_for": profile.get("best_for") or [],
        "consider_first": profile.get("consider_first") or [],
    }


def audit_display_record(content: dict[str, Any], display: dict[str, Any] | None) -> dict[str, Any]:
    issues = detect_display_issues(display)
    public_issues = display_issues(issues)
    source_issues = source_signal_review_issues(issues)
    score = calculate_score(public_issues)
    grade = grade_for_score(score, public_issues)
    counts = issue_counts(issues)
    profile = normalized_profile(display)
    supporting_facts = (display or {}).get("supporting_facts") or []

    return {
        "content_id": content.get("id"),
        "title": content.get("title"),
        "content_type": content.get("type") or content.get("content_type"),
        "year": content.get("year"),
        "display_quality_score": score,
        "grade": grade,
        "display_ready": display_ready_for(score, public_issues),
        "display_review_required": not display_ready_for(score, public_issues),
        "source_signal_review_required": bool(source_issues),
        "review_required": (
            not display_ready_for(score, public_issues) or bool(source_issues)
        ),
        "primary_insight": (display or {}).get("primary_insight"),
        "template_family": primary_template_family(
            (display or {}).get("primary_insight") or "",
            display,
        ),
        "profile": profile,
        "supporting_facts": supporting_facts,
        "issues": [item.as_dict() for item in issues],
        "display_issues": [item.as_dict() for item in public_issues],
        "source_signal_review_issues": [item.as_dict() for item in source_issues],
        "issue_counts": counts,
        "suggested_next_step": suggested_next_step(issues),
    }


def audit_content_detail(detail: dict[str, Any]) -> dict[str, Any]:
    content = detail.get("content") or {}
    decision_layer = detail.get("decision_layer") or {}
    display = decision_layer.get("display") if decision_layer else None
    insight_plan = ((decision_layer.get("debug") or {}).get("insight_plan"))
    if display and insight_plan:
        display = dict(display)
        display["_insight_plan"] = insight_plan
    return audit_display_record(content, display)


def apply_template_overuse_issues(
    records: list[dict[str, Any]],
    threshold: float = 0.50,
    minimum_catalog_size: int = 10,
) -> list[dict[str, Any]]:
    if len(records) < minimum_catalog_size:
        return records
    counts = Counter(record.get("template_family") for record in records)
    dominant, count = counts.most_common(1)[0]
    if not dominant or count / len(records) <= threshold:
        return records

    for record in records:
        if record.get("template_family") != dominant:
            continue
        if any(
            item["code"] == "PRIMARY_INSIGHT_TEMPLATE_OVERUSE"
            for item in record.get("issues") or []
        ):
            continue
        record["issues"].append(
            issue(
                "PRIMARY_INSIGHT_TEMPLATE_OVERUSE",
                "low",
                "primary_insight",
                dominant,
                "One sentence template dominates too much of the catalog.",
                "backend_display_rule",
            ).as_dict()
        )
        severity_counts = Counter(
            item["severity"] for item in record["issues"]
        )
        record["issue_counts"] = {
            severity: severity_counts.get(severity, 0)
            for severity in SEVERITIES
        }
        issue_objects = [
            DisplayIssue(
                code=item["code"],
                severity=item["severity"],
                field=item["field"],
                value=item["value"],
                message=item["message"],
                suggested_action=item["suggested_action"],
            )
            for item in record["issues"]
        ]
        public_issue_objects = display_issues(issue_objects)
        source_issue_objects = source_signal_review_issues(issue_objects)
        score = calculate_score(public_issue_objects)
        record["display_quality_score"] = score
        record["grade"] = grade_for_score(score, public_issue_objects)
        record["display_ready"] = display_ready_for(score, public_issue_objects)
        record["display_review_required"] = not record["display_ready"]
        record["source_signal_review_required"] = bool(source_issue_objects)
        record["review_required"] = (
            record["display_review_required"]
            or record["source_signal_review_required"]
        )
        record["display_issues"] = [item.as_dict() for item in public_issue_objects]
        record["source_signal_review_issues"] = [
            item.as_dict() for item in source_issue_objects
        ]
        record["suggested_next_step"] = suggested_next_step(issue_objects)
    return records


def should_include_in_json(record: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.include_passing:
        return True
    min_score = args.min_score
    if min_score is not None and record["display_quality_score"] < min_score:
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


def primary_issue_codes(record: dict[str, Any], limit: int = 4) -> list[str]:
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    issues = sorted(
        record.get("issues") or [],
        key=lambda item: (severity_order.get(item["severity"], 99), item["code"]),
    )
    return [item["code"] for item in issues[:limit]]


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
                    "score": record["display_quality_score"],
                    "field": item["field"],
                    "value": item["value"],
                    "message": item["message"],
                }
            )
    return dict(sorted(examples.items()))


def content_type_breakdown(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record.get("content_type") or "unknown"].append(record)

    breakdown = {}
    for content_type, rows in sorted(grouped.items()):
        average_score = round(
            sum(row["display_quality_score"] for row in rows) / len(rows),
            1,
        )
        breakdown[content_type] = {
            "titles_seen": len(rows),
            "display_ready_count": sum(1 for row in rows if row["display_ready"]),
            "display_review_required_count": sum(
                1 for row in rows if row["display_review_required"]
            ),
            "source_signal_review_required_count": sum(
                1 for row in rows if row["source_signal_review_required"]
            ),
            "review_required_count": sum(1 for row in rows if row["review_required"]),
            "average_score": average_score,
            "grade_counts": grade_counts(rows),
        }
    return breakdown


def build_summary(records: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    titles_seen = len(records)
    titles_with_display = sum(1 for row in records if row.get("primary_insight"))
    average_score = (
        round(sum(row["display_quality_score"] for row in records) / titles_seen, 1)
        if titles_seen
        else 0
    )
    weakest = sorted(
        records,
        key=lambda row: (row["display_quality_score"], row["title"] or ""),
    )[:10]

    return {
        "titles_seen": titles_seen,
        "titles_with_display": titles_with_display,
        "titles_missing_display": titles_seen - titles_with_display,
        "display_ready_count": sum(1 for row in records if row["display_ready"]),
        "display_review_required_count": sum(
            1 for row in records if row["display_review_required"]
        ),
        "source_signal_review_required_count": sum(
            1 for row in records if row["source_signal_review_required"]
        ),
        "review_required_count": sum(1 for row in records if row["review_required"]),
        "average_score": average_score,
        "grade_counts": grade_counts(records),
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
                "display_quality_score": row["display_quality_score"],
                "grade": row["grade"],
                "primary_issue_codes": primary_issue_codes(row),
                "suggested_next_step": row["suggested_next_step"],
            }
            for row in weakest
        ],
        "top_issue_examples": top_issue_examples(records),
        "content_type_breakdown": content_type_breakdown(records),
        "generated_at": generated_at,
        "versions": decision_insight_versions(),
    }


def csv_row(record: dict[str, Any]) -> dict[str, Any]:
    profile = record.get("profile") or {}
    facts = [
        f"{clean_text(fact.get('label'))}: {clean_text(fact.get('value'))}"
        for fact in record.get("supporting_facts") or []
    ]
    return {
        "content_id": record.get("content_id"),
        "title": record.get("title"),
        "content_type": record.get("content_type"),
        "year": record.get("year"),
        "display_quality_score": record.get("display_quality_score"),
        "grade": record.get("grade"),
        "display_ready": record.get("display_ready"),
        "display_review_required": record.get("display_review_required"),
        "source_signal_review_required": record.get(
            "source_signal_review_required"
        ),
        "review_required": record.get("review_required"),
        "primary_issue_codes": pipe_join(primary_issue_codes(record)),
        "primary_issue_severities": pipe_join(
            sorted(
                {
                    item["severity"]
                    for item in record.get("issues") or []
                },
                key=lambda value: SEVERITIES.index(value)
                if value in SEVERITIES
                else 99,
            )
        ),
        "primary_insight": record.get("primary_insight"),
        "identity": pipe_join(profile.get("identity") or []),
        "themes": pipe_join(profile.get("themes") or []),
        "feel": pipe_join(profile.get("feel") or []),
        "pace": profile.get("pace") or "",
        "best_for": pipe_join(profile.get("best_for") or []),
        "consider_first": pipe_join(profile.get("consider_first") or []),
        "supporting_facts": pipe_join(facts),
        "suggested_next_step": record.get("suggested_next_step"),
    }


CSV_COLUMNS = [
    "content_id",
    "title",
    "content_type",
    "year",
    "display_quality_score",
    "grade",
    "display_ready",
    "display_review_required",
    "source_signal_review_required",
    "review_required",
    "primary_issue_codes",
    "primary_issue_severities",
    "primary_insight",
    "identity",
    "themes",
    "feel",
    "pace",
    "best_for",
    "consider_first",
    "supporting_facts",
    "suggested_next_step",
]


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow(csv_row(record))


def query_catalog_target_batches(connection, args: argparse.Namespace):
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
            c.year
        FROM content c
        {where_sql}
        ORDER BY c.content_type, c.title, c.id
        {query_suffix};
    """)
    if args.content_id:
        query = query.bindparams(bindparam("content_ids", expanding=True))

    result = connection.execute(query, params).mappings()
    batch_size = getattr(args, "batch_size", 100)
    while True:
        rows = result.fetchmany(batch_size)
        if not rows:
            break
        yield [dict(row) for row in rows]


def query_catalog_targets(connection, args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        row
        for batch in query_catalog_target_batches(connection, args)
        for row in batch
    ]


def audit_catalog(connection, args: argparse.Namespace) -> list[dict[str, Any]]:
    records = []
    for targets in query_catalog_target_batches(connection, args):
        for target in targets:
            detail = get_content_details_service(
                target["id"],
                connection,
                include_decision_debug=True,
            )
            if not detail:
                record = audit_display_record(
                    {
                        "id": target["id"],
                        "title": target["title"],
                        "type": target["content_type"],
                        "year": target["year"],
                    },
                    None,
                )
            else:
                record = audit_content_detail(detail)
            records.append(record)
    return apply_template_overuse_issues(records)


def should_fail_run(summary: dict[str, Any], records: list[dict[str, Any]], args: argparse.Namespace) -> bool:
    if args.fail_on_critical and summary["issue_counts_by_severity"].get("critical", 0):
        return True
    if args.fail_under_score is not None and any(
        row["display_quality_score"] < args.fail_under_score for row in records
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
        "versions": decision_insight_versions(),
        "filters": {
            "content_ids": args.content_id or [],
            "content_type": args.content_type,
            "limit": args.limit,
            "offset": args.offset,
            "batch_size": getattr(args, "batch_size", 100),
            "min_score": args.min_score,
            "include_passing": args.include_passing,
        },
        "summary": summary,
        "items": included_records,
    }


def print_summary(summary: dict[str, Any], json_path: Path, csv_path: Path, summary_path: Path) -> None:
    print("Decision display quality audit complete.")
    print("DB writes: none")
    print(f"Titles seen: {summary['titles_seen']}")
    print(f"Display ready: {summary['display_ready_count']}")
    print(f"Display review required: {summary['display_review_required_count']}")
    print(
        "Source-signal review required: "
        f"{summary['source_signal_review_required_count']}"
    )
    print(f"Any operational review required: {summary['review_required_count']}")
    print(f"Average score: {summary['average_score']}")
    print(f"Critical issues: {summary['issue_counts_by_severity'].get('critical', 0)}")
    print(f"JSON report: {relative_path(json_path)}")
    print(f"CSV report: {relative_path(csv_path)}")
    print(f"Summary: {relative_path(summary_path)}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    database_url = os.getenv(DATABASE_URL_ENV)
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

    engine = create_engine(database_url)
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        records = audit_catalog(connection, args)
        connection.rollback()

    summary = build_summary(records, generated_at)
    detail_report = build_detail_report(records, summary, args, generated_at)

    write_json(json_path, detail_report)
    write_csv(csv_path, records)
    write_json(summary_path, summary)
    print_summary(summary, json_path, csv_path, summary_path)

    return 1 if should_fail_run(summary, records, args) else 0


if __name__ == "__main__":
    raise SystemExit(main())
