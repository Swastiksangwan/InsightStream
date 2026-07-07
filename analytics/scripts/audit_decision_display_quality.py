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


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.content_service import get_content_details_service  # noqa: E402


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
    return " ".join(value for _field, value in flatten_public_strings(display or {})).lower()


def non_access_display_text(display: dict[str, Any] | None) -> str:
    if not display:
        return ""
    values = []
    for field, value in flatten_public_strings(display):
        if field.startswith("supporting_facts"):
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
        if len(primary) < 28:
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
    score = calculate_score(issues)
    grade = grade_for_score(score, issues)
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
        "display_ready": display_ready_for(score, issues),
        "review_required": not display_ready_for(score, issues),
        "primary_insight": (display or {}).get("primary_insight"),
        "profile": profile,
        "supporting_facts": supporting_facts,
        "issues": [item.as_dict() for item in issues],
        "issue_counts": counts,
        "suggested_next_step": suggested_next_step(issues),
    }


def audit_content_detail(detail: dict[str, Any]) -> dict[str, Any]:
    content = detail.get("content") or {}
    decision_layer = detail.get("decision_layer") or {}
    display = decision_layer.get("display") if decision_layer else None
    return audit_display_record(content, display)


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
            c.year
        FROM content c
        {where_sql}
        ORDER BY c.content_type, c.title, c.id
        {query_suffix};
    """)
    if args.content_id:
        query = query.bindparams(bindparam("content_ids", expanding=True))

    result = connection.execute(query, params)
    return [dict(row) for row in result.mappings().all()]


def audit_catalog(connection, args: argparse.Namespace) -> list[dict[str, Any]]:
    records = []
    for target in query_catalog_targets(connection, args):
        detail = get_content_details_service(target["id"], connection)
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
    return records


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
    print("Decision display quality audit complete.")
    print("DB writes: none")
    print(f"Titles seen: {summary['titles_seen']}")
    print(f"Display ready: {summary['display_ready_count']}")
    print(f"Review required: {summary['review_required_count']}")
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
        records = audit_catalog(connection, args)

    summary = build_summary(records, generated_at)
    detail_report = build_detail_report(records, summary, args, generated_at)

    write_json(json_path, detail_report)
    write_csv(csv_path, records)
    write_json(summary_path, summary)
    print_summary(summary, json_path, csv_path, summary_path)

    return 1 if should_fail_run(summary, records, args) else 0


if __name__ == "__main__":
    raise SystemExit(main())
