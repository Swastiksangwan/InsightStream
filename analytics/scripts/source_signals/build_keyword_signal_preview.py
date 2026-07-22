#!/usr/bin/env python3
"""
Preview source-signal guidance from imported TMDb keywords.

This script:
- reads imported TMDb keywords from PostgreSQL using DATABASE_URL
- applies analytics/config/source_signal_keyword_mapping.json
- writes local preview/report JSON under analytics/processed/source_signals/
- does not write to the database
- does not call TMDb or any external API
- does not expose raw keyword evidence unless --include-debug is used
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


from analytics.scripts.common.paths import REPO_ROOT
from analytics.scripts.source_signals.source_signal_keyword_normalization import (
    normalize_keyword_name,
)

DATABASE_URL_ENV = "DATABASE_URL"
DEFAULT_MAPPING_PATH = (
    REPO_ROOT / "analytics" / "config" / "source_signal_keyword_mapping.json"
)
DEFAULT_OVERRIDES_PATH = (
    REPO_ROOT / "analytics" / "config" / "source_signal_title_overrides.json"
)
DEFAULT_OUTPUT_PATH = (
    REPO_ROOT / "analytics" / "processed" / "source_signals" / "source_signal_preview.json"
)
DEFAULT_REPORT_PATH = (
    REPO_ROOT
    / "analytics"
    / "processed"
    / "source_signals"
    / "run_reports"
    / "source_signal_preview_report.json"
)
PREVIEW_GENERATOR_VERSION = "2026-07-02-v3.2.1"
SEMANTIC_QA_VERSION = "2026-07-02-v3.2.1"
REQUIRED_DIMENSIONS = [
    "topic_theme",
    "tone",
    "mood",
    "pacing",
    "intensity",
    "audience_expectation",
    "content_caution_proxy",
]
CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}
RANK_CONFIDENCE = {1: "low", 2: "medium", 3: "high"}
USER_FACING_BANNED_TERMS = {
    "confidence",
    "tmdb",
    "content_caution_proxy",
}
LIMITED_GUIDANCE_TEXT = (
    "More watch-profile detail will be available after additional source signals are added."
)
SOURCE_PRIORITY = {"curated_override": 0, "tmdb_keywords": 1, "metadata_fallback": 2}
LOCATION_NOISE_HINTS = {
    "africa",
    "america",
    "american",
    "asia",
    "australia",
    "berlin",
    "california",
    "canada",
    "chicago",
    "china",
    "england",
    "europe",
    "france",
    "india",
    "italy",
    "japan",
    "london",
    "los angeles",
    "mexico",
    "new york",
    "paris",
    "russia",
    "spain",
    "texas",
    "united kingdom",
    "usa",
}
UNMAPPED_NOISE_HINTS = {
    "adaptation",
    "actor",
    "actress",
    "based on",
    "behind the scenes",
    "cameo",
    "director",
    "duringcreditsstinger",
    "franchise",
    "novel",
    "producer",
    "remake",
    "sequel",
    "spin off",
    "stinger",
}
STRONG_PRIMARY_IDENTITIES = {
    "character-driven crime drama",
    "corporate family drama",
    "courtroom drama",
    "crime drama",
    "fantasy-drama",
    "historical drama",
    "music drama",
    "nature documentary",
    "romantic drama",
    "space sci-fi drama",
    "tech-driven sci-fi",
}
WEAK_PRIMARY_PHRASES = {
    "bold story",
    "complex story",
    "dialogue-heavy story",
    "generic drama",
    "limited signal",
}
GENERIC_WATCH_FEEL_PHRASES = {
    "a fantasy adventure.",
    "a space opera.",
    "a tech-driven sci-fi.",
    "a serious war story.",
    "a warm friendship story.",
    "a plot-driven spy story.",
    "a serious historical drama.",
    "a period drama with a high-stakes edge.",
}
PARTIAL_OUTPUT_ERROR = (
    "Partial/debug preview runs require explicit --output and --report-output so the "
    "full catalog preview is not overwritten."
)


@dataclass(frozen=True)
class KeywordContent:
    content_id: int
    title: str
    content_type: str
    keywords: list[str]
    tmdb_id: str | None = None
    genres: list[str] = field(default_factory=list)


class KeywordSignalPreviewError(RuntimeError):
    pass


def argv_has_option(argv: list[str], option: str) -> bool:
    return option in argv or any(value.startswith(f"{option}=") for value in argv)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        description="Build a local preview of keyword-derived source signals."
    )
    parser.add_argument(
        "--mapping-file",
        default=str(DEFAULT_MAPPING_PATH.relative_to(REPO_ROOT)),
        help=(
            "Keyword mapping config path. Defaults to "
            f"{DEFAULT_MAPPING_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--override-file",
        default=str(DEFAULT_OVERRIDES_PATH.relative_to(REPO_ROOT)),
        help=(
            "Curated title override config path. Defaults to "
            f"{DEFAULT_OVERRIDES_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH.relative_to(REPO_ROOT)),
        help=(
            "Preview output path. Defaults to "
            f"{DEFAULT_OUTPUT_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--report-output",
        default=str(DEFAULT_REPORT_PATH.relative_to(REPO_ROOT)),
        help=(
            "Report output path. Defaults to "
            f"{DEFAULT_REPORT_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument("--limit", type=int, help="Limit selected titles after filters.")
    parser.add_argument(
        "--content-type",
        choices=["movie", "series", "all"],
        default="all",
        help="Filter titles by content type. Defaults to all.",
    )
    parser.add_argument(
        "--content-id",
        type=int,
        action="append",
        help="Preview only this content ID. Can be passed more than once.",
    )
    parser.add_argument(
        "--only-content-ids-file",
        help="JSON file containing either a list of content IDs or {\"content_ids\": [...]}.",
    )
    parser.add_argument(
        "--include-debug",
        action="store_true",
        help="Include raw keyword/evidence debug details in preview output.",
    )
    args = parser.parse_args(raw_argv)
    args.output_explicit = argv_has_option(raw_argv, "--output")
    args.report_output_explicit = argv_has_option(raw_argv, "--report-output")
    return args


def partial_or_debug_run(args: argparse.Namespace) -> bool:
    return bool(
        args.limit is not None
        or args.content_type != "all"
        or args.content_id
        or args.only_content_ids_file
        or args.include_debug
    )


def output_safety_error(args: argparse.Namespace) -> str | None:
    if partial_or_debug_run(args) and not (
        getattr(args, "output_explicit", False)
        and getattr(args, "report_output_explicit", False)
    ):
        return PARTIAL_OUTPUT_ERROR
    return None


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


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_safe(data), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise KeywordSignalPreviewError(f"Missing file: {relative_path(path)}") from exc
    except json.JSONDecodeError as exc:
        raise KeywordSignalPreviewError(
            f"Malformed JSON in {relative_path(path)}: {exc}"
        ) from exc


def normalize_mapping_config(raw_config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw_config, dict):
        raise KeywordSignalPreviewError("Mapping config must be a JSON object.")

    keyword_mappings = raw_config.get("keyword_mappings")
    if not isinstance(keyword_mappings, dict):
        raise KeywordSignalPreviewError("Mapping config must include keyword_mappings.")

    dimensions = raw_config.get("dimensions") or REQUIRED_DIMENSIONS
    if not isinstance(dimensions, list):
        raise KeywordSignalPreviewError("Mapping config dimensions must be a list.")
    dimension_set = {str(dimension) for dimension in dimensions}
    missing_dimensions = sorted(set(REQUIRED_DIMENSIONS) - dimension_set)
    if missing_dimensions:
        raise KeywordSignalPreviewError(
            "Mapping config missing required dimensions: "
            + ", ".join(missing_dimensions)
        )

    normalized_mappings: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for keyword, entry in keyword_mappings.items():
        normalized_keyword = normalize_keyword_name(keyword)
        if not normalized_keyword or not isinstance(entry, dict):
            warnings.append(f"Invalid mapping entry for {keyword!r}; ignored.")
            continue
        signals = entry.get("signals")
        if not isinstance(signals, list):
            warnings.append(f"{keyword}: signals must be a list; ignored.")
            continue
        valid_signals = []
        for signal in signals:
            if not isinstance(signal, dict):
                continue
            dimension = clean_text(signal.get("dimension"))
            value = clean_text(signal.get("value"))
            label = clean_text(signal.get("display_label"))
            if dimension not in dimension_set or not value or not label:
                warnings.append(f"{keyword}: invalid signal skipped.")
                continue
            valid_signals.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "display_label": label,
                    "weight": int(signal.get("weight") or 1),
                    "confidence": clean_text(signal.get("confidence")) or "low",
                    "spoiler_safe": bool(signal.get("spoiler_safe", True)),
                }
            )
        normalized_mappings[normalized_keyword] = {
            **entry,
            "signals": valid_signals,
        }

    config = {
        **raw_config,
        "dimensions": list(dimensions),
        "keyword_mappings": normalized_mappings,
        "excluded_keywords": {
            normalize_keyword_name(keyword)
            for keyword in raw_config.get("excluded_keywords", [])
            if normalize_keyword_name(keyword)
        },
        "spoiler_unsafe_keywords": {
            normalize_keyword_name(keyword)
            for keyword in raw_config.get("spoiler_unsafe_keywords", [])
            if normalize_keyword_name(keyword)
        },
        "warnings": warnings,
    }
    return config


def load_mapping_config(path: Path) -> dict[str, Any]:
    return normalize_mapping_config(load_json_file(path))


def normalize_title_key(value: Any) -> str:
    text_value = clean_text(value)
    if not text_value:
        return ""
    text_value = text_value.lower().replace("&", " and ")
    text_value = re.sub(r"[^\w\s]", "", text_value)
    return re.sub(r"\s+", " ", text_value).strip()


def normalize_override_signal(raw_signal: dict[str, Any]) -> dict[str, Any] | None:
    dimension = clean_text(raw_signal.get("dimension"))
    value = clean_text(raw_signal.get("value"))
    label = clean_text(raw_signal.get("label") or raw_signal.get("display_label"))
    if dimension not in REQUIRED_DIMENSIONS or not value or not label:
        return None
    return {
        "dimension": dimension,
        "value": value,
        "label": label,
        "confidence": clean_text(raw_signal.get("confidence")) or "high",
        "sources": ["curated_override"],
    }


def normalize_override_rules(raw_rules: Any) -> list[dict[str, str]]:
    if not isinstance(raw_rules, list):
        return []
    rules: list[dict[str, str]] = []
    for raw_rule in raw_rules:
        if isinstance(raw_rule, str):
            normalized_value = clean_text(raw_rule)
            if normalized_value:
                rules.append({"value": normalized_value})
            continue
        if not isinstance(raw_rule, dict):
            continue
        rule: dict[str, str] = {}
        for key in ("dimension", "value", "label"):
            normalized = clean_text(raw_rule.get(key))
            if normalized:
                rule[key] = normalized
        if rule:
            rules.append(rule)
    return rules


def normalize_title_override(raw_override: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(raw_override, dict):
        return None
    content_id = raw_override.get("content_id")
    normalized_content_id: int | None = None
    if content_id is not None and not isinstance(content_id, bool):
        try:
            normalized_content_id = int(content_id)
        except (TypeError, ValueError):
            normalized_content_id = None

    title = clean_text(raw_override.get("title"))
    content_type = clean_text(raw_override.get("content_type"))
    tmdb_id = clean_text(raw_override.get("tmdb_id"))
    if normalized_content_id is None and not (title and content_type) and not tmdb_id:
        return None

    signals_to_add = [
        signal
        for signal in (
            normalize_override_signal(raw_signal)
            for raw_signal in raw_override.get("signals_to_add", [])
            if isinstance(raw_signal, dict)
        )
        if signal
    ]
    preferred_consider_first = None
    if "preferred_consider_first" in raw_override:
        preferred_consider_first = [
            value
            for value in (
                clean_text(item)
                for item in raw_override.get("preferred_consider_first", [])
            )
            if value
        ]
    return {
        "content_id": normalized_content_id,
        "title": title,
        "title_key": normalize_title_key(title),
        "content_type": content_type,
        "tmdb_id": tmdb_id,
        "signals_to_add": signals_to_add,
        "signals_to_demote": normalize_override_rules(raw_override.get("signals_to_demote")),
        "signals_to_suppress": normalize_override_rules(
            raw_override.get("signals_to_suppress")
        ),
        "preferred_watch_feel": clean_text(raw_override.get("preferred_watch_feel")),
        "preferred_chips": [
            value
            for value in (clean_text(item) for item in raw_override.get("preferred_chips", []))
            if value
        ],
        "preferred_best_for": [
            value
            for value in (clean_text(item) for item in raw_override.get("preferred_best_for", []))
            if value
        ],
        "preferred_consider_first": preferred_consider_first,
        "notes": clean_text(raw_override.get("notes")),
    }


def normalize_override_config(raw_config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw_config, dict):
        raise KeywordSignalPreviewError("Override config must be a JSON object.")
    overrides = [
        override
        for override in (
            normalize_title_override(raw_override)
            for raw_override in raw_config.get("overrides", [])
        )
        if override
    ]
    return {
        **raw_config,
        "overrides": overrides,
    }


def load_override_config(path: Path) -> dict[str, Any]:
    return normalize_override_config(load_json_file(path))


def override_matches_content(override: dict[str, Any], content: KeywordContent) -> bool:
    if override.get("content_id") is not None and override["content_id"] == content.content_id:
        return True
    if override.get("tmdb_id") and content.tmdb_id and override["tmdb_id"] == content.tmdb_id:
        return True
    return bool(
        override.get("title_key")
        and override.get("content_type") == content.content_type
        and override["title_key"] == normalize_title_key(content.title)
    )


def find_title_override(
    content: KeywordContent,
    override_config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not override_config:
        return None
    for override in override_config.get("overrides", []):
        if override_matches_content(override, content):
            return override
    return None


def load_content_ids_file(path: Path) -> set[int]:
    data = load_json_file(path)
    raw_ids = data.get("content_ids") if isinstance(data, dict) else data
    if not isinstance(raw_ids, list):
        raise KeywordSignalPreviewError(
            "Content IDs file must be a JSON list or an object with content_ids."
        )
    content_ids: set[int] = set()
    for raw_id in raw_ids:
        if isinstance(raw_id, bool):
            continue
        try:
            content_ids.add(int(raw_id))
        except (TypeError, ValueError):
            continue
    return content_ids


def selected_content_ids(args: argparse.Namespace) -> set[int] | None:
    content_ids: set[int] = set(args.content_id or [])
    if args.only_content_ids_file:
        content_ids.update(load_content_ids_file(resolve_path(args.only_content_ids_file)))
    return content_ids or None


def fetch_imported_tmdb_keywords(connection: Any) -> list[dict[str, Any]]:
    rows = connection.execute(
        text(
            """
            SELECT
                c.id AS content_id,
                c.tmdb_id,
                c.title,
                c.content_type,
                pk.keyword_name,
                pk.normalized_keyword_name,
                genre_data.genre_names
            FROM content c
            JOIN content_keywords ck ON ck.content_id = c.id
            JOIN keyword_sources ks
              ON ks.id = ck.source_id
             AND ks.source_name = 'tmdb'
            JOIN provider_keywords pk ON pk.id = ck.keyword_id
            LEFT JOIN LATERAL (
                SELECT STRING_AGG(DISTINCT g.name, '||' ORDER BY g.name) AS genre_names
                FROM content_genres cg
                JOIN genres g ON g.id = cg.genre_id
                WHERE cg.content_id = c.id
            ) genre_data ON true
            ORDER BY c.title ASC, pk.normalized_keyword_name ASC;
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def group_keyword_rows(
    rows: list[dict[str, Any]],
    content_type_filter: str = "all",
    content_id_filter: set[int] | None = None,
    limit: int | None = None,
) -> list[KeywordContent]:
    grouped: dict[int, dict[str, Any]] = {}
    for row in rows:
        content_id = int(row["content_id"])
        content_type = clean_text(row.get("content_type")) or ""
        if content_type_filter != "all" and content_type != content_type_filter:
            continue
        if content_id_filter is not None and content_id not in content_id_filter:
            continue
        keyword_name = clean_text(row.get("keyword_name"))
        normalized_keyword = normalize_keyword_name(
            row.get("normalized_keyword_name") or keyword_name
        )
        if not keyword_name or not normalized_keyword:
            continue
        grouped.setdefault(
            content_id,
            {
                "content_id": content_id,
                "title": clean_text(row.get("title")) or f"content_id={content_id}",
                "content_type": content_type,
                "tmdb_id": clean_text(row.get("tmdb_id")),
                "genres": [
                    genre
                    for genre in str(row.get("genre_names") or "").split("||")
                    if clean_text(genre)
                ],
                "keywords_by_normalized": {},
            },
        )["keywords_by_normalized"].setdefault(normalized_keyword, keyword_name)

    items = []
    for item in sorted(grouped.values(), key=lambda value: (value["title"], value["content_id"])):
        if limit is not None and len(items) >= limit:
            break
        items.append(
            KeywordContent(
                content_id=item["content_id"],
                title=item["title"],
                content_type=item["content_type"],
                keywords=list(item["keywords_by_normalized"].values()),
                tmdb_id=item["tmdb_id"],
                genres=item["genres"],
            )
        )
    return items


def confidence_rank(confidence: str | None) -> int:
    return CONFIDENCE_RANK.get((confidence or "low").lower(), 1)


def aggregate_confidence(
    max_rank: int,
    support_count: int,
    max_weight: int,
    dimension: str,
) -> str:
    rank = max_rank
    if support_count >= 2:
        rank = max(rank, 2)
    if support_count >= 3 and max_weight >= 3 and dimension != "content_caution_proxy":
        rank = max(rank, 3)
    if dimension == "content_caution_proxy":
        rank = min(rank, 2)
    return RANK_CONFIDENCE.get(rank, "low")


def empty_signal_bucket(dimensions: list[str]) -> dict[str, list[dict[str, Any]]]:
    return {dimension: [] for dimension in dimensions}


def signal_sort_key(signal: dict[str, Any]) -> tuple[int, int, str]:
    source_priority = min(
        (SOURCE_PRIORITY.get(source, 9) for source in signal.get("sources", [])),
        default=9,
    )
    return (
        source_priority,
        -confidence_rank(signal.get("confidence")),
        -int(signal.get("_weight", 0)),
        -int(signal.get("_support_count", 0)),
        signal.get("label", ""),
    )


def merge_confidence(existing: str | None, incoming: str | None) -> str:
    return RANK_CONFIDENCE.get(
        max(confidence_rank(existing), confidence_rank(incoming)),
        "low",
    )


def add_signal_to_bucket(
    signals_by_dimension: dict[str, list[dict[str, Any]]],
    *,
    dimension: str,
    value: str,
    label: str,
    confidence: str,
    source: str,
    prepend: bool = False,
) -> bool:
    signal_list = signals_by_dimension.setdefault(dimension, [])
    for existing in signal_list:
        if existing.get("value") == value:
            existing["confidence"] = merge_confidence(existing.get("confidence"), confidence)
            sources = existing.setdefault("sources", [])
            if source not in sources:
                sources.append(source)
            return False
    signal = {
        "value": value,
        "label": label,
        "confidence": confidence,
        "sources": [source],
    }
    if prepend:
        signal_list.insert(0, signal)
    else:
        signal_list.append(signal)
    return True


def sort_public_signal_buckets(signals_by_dimension: dict[str, list[dict[str, Any]]]) -> None:
    for signal_list in signals_by_dimension.values():
        signal_list.sort(key=signal_sort_key)


def map_keywords_for_content(
    keywords: list[str],
    mapping_config: dict[str, Any],
    include_debug: bool = False,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    dimensions = list(mapping_config["dimensions"])
    mappings = mapping_config["keyword_mappings"]
    excluded = mapping_config["excluded_keywords"]
    spoiler_unsafe = mapping_config["spoiler_unsafe_keywords"]
    display_config = mapping_config.get("signal_display") or {}
    max_per_dimension = int(display_config.get("max_signals_per_dimension") or 3)

    aggregated: dict[tuple[str, str], dict[str, Any]] = {}
    mapped_keywords: list[str] = []
    excluded_keywords: list[str] = []
    spoiler_unsafe_keywords: list[str] = []
    unmapped_keywords: list[str] = []

    for keyword in keywords:
        normalized_keyword = normalize_keyword_name(keyword)
        if not normalized_keyword:
            continue
        if normalized_keyword in excluded:
            excluded_keywords.append(normalized_keyword)
            continue
        if normalized_keyword in spoiler_unsafe:
            spoiler_unsafe_keywords.append(normalized_keyword)
            continue

        entry = mappings.get(normalized_keyword)
        if not entry:
            unmapped_keywords.append(normalized_keyword)
            continue

        usable_signal_count = 0
        for signal in entry.get("signals", []):
            if signal.get("spoiler_safe") is False:
                spoiler_unsafe_keywords.append(normalized_keyword)
                continue
            dimension = signal["dimension"]
            value = signal["value"]
            key = (dimension, value)
            existing = aggregated.setdefault(
                key,
                {
                    "dimension": dimension,
                    "value": value,
                    "label": signal["display_label"],
                    "_weight": 0,
                    "_confidence_rank": 1,
                    "_support_count": 0,
                    "_evidence_keywords": [],
                },
            )
            existing["_weight"] = max(existing["_weight"], int(signal.get("weight") or 1))
            existing["_confidence_rank"] = max(
                existing["_confidence_rank"],
                confidence_rank(signal.get("confidence")),
            )
            existing["_support_count"] += 1
            if normalized_keyword not in existing["_evidence_keywords"]:
                existing["_evidence_keywords"].append(normalized_keyword)
            usable_signal_count += 1

        if usable_signal_count:
            mapped_keywords.append(normalized_keyword)

    signals_by_dimension = empty_signal_bucket(dimensions)
    for signal in aggregated.values():
        dimension = signal["dimension"]
        public_signal = {
            "value": signal["value"],
            "label": signal["label"],
            "confidence": aggregate_confidence(
                signal["_confidence_rank"],
                signal["_support_count"],
                signal["_weight"],
                dimension,
            ),
            "sources": ["tmdb_keywords"],
            "_weight": signal["_weight"],
            "_support_count": signal["_support_count"],
        }
        if include_debug:
            public_signal["evidence_keywords"] = sorted(signal["_evidence_keywords"])
        signals_by_dimension.setdefault(dimension, []).append(public_signal)

    for dimension, signal_list in signals_by_dimension.items():
        signal_list.sort(key=signal_sort_key)
        trimmed = signal_list[:max_per_dimension]
        for signal in trimmed:
            signal.pop("_weight", None)
            signal.pop("_support_count", None)
        signals_by_dimension[dimension] = trimmed

    analysis = {
        "mapped_keywords": sorted(set(mapped_keywords)),
        "excluded_keywords": sorted(set(excluded_keywords)),
        "spoiler_unsafe_keywords": sorted(set(spoiler_unsafe_keywords)),
        "unmapped_keywords": sorted(set(unmapped_keywords)),
        "mapped_keyword_hits": mapped_keywords,
        "excluded_keyword_hits": excluded_keywords,
        "spoiler_unsafe_keyword_hits": spoiler_unsafe_keywords,
        "unmapped_keyword_hits": unmapped_keywords,
        "signals_by_dimension": signals_by_dimension,
    }
    return signals_by_dimension, analysis


def top_signals(
    signals: dict[str, list[dict[str, Any]]],
    dimensions: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for dimension in dimensions:
        for signal in signals.get(dimension, []):
            key = (dimension, signal["value"])
            if key in seen:
                continue
            selected.append({**signal, "dimension": dimension})
            seen.add(key)
            if len(selected) >= limit:
                return selected
    return selected


def lower_label(label: str) -> str:
    if not label:
        return label
    return label[0].lower() + label[1:]


def article_for_phrase(phrase: str) -> str:
    return "an" if phrase[:1].lower() in {"a", "e", "i", "o", "u"} else "a"


def signal_values(signals: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {
        str(signal.get("value"))
        for signal_list in signals.values()
        for signal in signal_list
        if signal.get("value")
    }


def has_signal_value(signals: dict[str, list[dict[str, Any]]], *values: str) -> bool:
    value_set = signal_values(signals)
    return any(value in value_set for value in values)


def count_signals(signals: dict[str, list[dict[str, Any]]]) -> int:
    return sum(len(signal_list) for signal_list in signals.values())


def all_signals_low_confidence(signals: dict[str, list[dict[str, Any]]]) -> bool:
    signal_list = [
        signal
        for signals_for_dimension in signals.values()
        for signal in signals_for_dimension
    ]
    return bool(signal_list) and all(
        confidence_rank(signal.get("confidence")) <= 1 for signal in signal_list
    )


def needs_metadata_fallback(signals: dict[str, list[dict[str, Any]]]) -> bool:
    signal_count = count_signals(signals)
    return signal_count == 0 or signal_count == 1 or all_signals_low_confidence(signals)


def normalized_genres(content: KeywordContent) -> set[str]:
    return {normalize_keyword_name(genre) for genre in content.genres if normalize_keyword_name(genre)}


def genre_has(genres: set[str], *names: str) -> bool:
    return any(normalize_keyword_name(name) in genres for name in names)


def metadata_fallback_signals(
    content: KeywordContent,
    existing_signals: dict[str, list[dict[str, Any]]],
) -> list[dict[str, str]]:
    genres = normalized_genres(content)
    fallback: list[dict[str, str]] = []

    def add(dimension: str, value: str, label: str, confidence: str = "medium") -> None:
        fallback.append(
            {
                "dimension": dimension,
                "value": value,
                "label": label,
                "confidence": confidence,
            }
        )

    if genre_has(genres, "documentary"):
        add("topic_theme", "documentary", "Documentary")
        add("audience_expectation", "documentary viewing", "Documentary viewing")
    if genre_has(genres, "nature", "wildlife"):
        add("topic_theme", "nature documentary", "Nature documentary")
        add("mood", "expansive", "Expansive")
    if genre_has(genres, "comedy"):
        add("audience_expectation", "comedy", "Comedy")
        add("tone", "playful", "Playful", "low")
    if genre_has(genres, "drama"):
        add("audience_expectation", "drama", "Drama")
        if count_signals(existing_signals) > 0:
            add("tone", "serious", "Serious tone", "low")
    if genre_has(genres, "romance"):
        add("topic_theme", "romantic drama", "Romantic drama")
        add("mood", "emotional", "Emotional", "low")
    if genre_has(genres, "science fiction", "sci fi", "sci fi and fantasy"):
        add("audience_expectation", "sci-fi story", "Sci-fi story")
    if genre_has(genres, "adventure"):
        add("pacing", "adventure-driven", "Adventure-driven")
    if genre_has(genres, "thriller"):
        add("mood", "suspenseful", "Suspenseful")
        add("tone", "tense", "Tense")
    if genre_has(genres, "crime"):
        add("topic_theme", "crime story", "Crime story")
        if has_signal_value(existing_signals, "organized crime story", "crime mystery"):
            add("tone", "gritty", "Gritty tone", "low")
    if genre_has(genres, "fantasy"):
        add("audience_expectation", "fantasy story", "Fantasy story")
    if genre_has(genres, "animation"):
        add("topic_theme", "animated story", "Animated story")
    if genre_has(genres, "music"):
        add("topic_theme", "music-driven story", "Music-driven story")
    if genre_has(genres, "history"):
        add("topic_theme", "historical drama", "Historical drama")
        add("tone", "serious", "Serious tone")
    if genre_has(genres, "war"):
        add("topic_theme", "war story", "War story")
        add("tone", "serious", "Serious tone")

    return fallback


def apply_metadata_fallback(
    signals: dict[str, list[dict[str, Any]]],
    content: KeywordContent,
) -> dict[str, Any]:
    if not needs_metadata_fallback(signals):
        return {"applied": False, "signals_added": 0}
    added = 0
    for fallback_signal in metadata_fallback_signals(content, signals):
        if add_signal_to_bucket(
            signals,
            dimension=fallback_signal["dimension"],
            value=fallback_signal["value"],
            label=fallback_signal["label"],
            confidence=fallback_signal["confidence"],
            source="metadata_fallback",
        ):
            added += 1
    if added:
        sort_public_signal_buckets(signals)
    return {"applied": bool(added), "signals_added": added}


def product_primary_phrase(
    signals: dict[str, list[dict[str, Any]]],
    main_candidates: list[dict[str, Any]],
) -> str | None:
    if has_signal_value(signals, "dark fantasy") and has_signal_value(
        signals,
        "power struggle",
        "political power drama",
        "court politics",
        "royal power drama",
    ):
        return "political dark fantasy"
    if has_signal_value(signals, "psychological thriller"):
        return "psychological thriller"
    if has_signal_value(signals, "organized crime story"):
        return "organized-crime story"
    if has_signal_value(signals, "horror story") and has_signal_value(
        signals,
        "supernatural story",
        "ghost story",
        "haunted-house story",
    ):
        return "supernatural horror"
    if has_signal_value(signals, "nuclear disaster"):
        return "historical disaster drama"
    if has_signal_value(signals, "neo-noir crime"):
        return "neo-noir crime story"
    if has_signal_value(signals, "workplace comedy"):
        return "workplace comedy"
    if has_signal_value(signals, "mockumentary comedy"):
        return "mockumentary comedy"
    if has_signal_value(signals, "sitcom comedy"):
        return "sitcom comedy"
    if has_signal_value(signals, "martial arts action"):
        return "martial-arts adventure"
    if has_signal_value(signals, "memory and identity"):
        return "story about memory and identity"
    if has_signal_value(signals, "mythic superhero mystery") and has_signal_value(
        signals,
        "identity conflict",
        "mythology",
    ):
        return "mythic superhero mystery"
    if has_signal_value(signals, "superhero team story"):
        return "superhero team story"
    if has_signal_value(signals, "superhuman powers"):
        return "superhero story"
    if has_signal_value(signals, "comic-book adaptation") and has_signal_value(
        signals,
        "superhero story",
        "superhero team story",
        "superhuman powers",
    ):
        return "comic-book-based superhero story"
    if has_signal_value(signals, "comic-book adaptation"):
        return "comic-book-based story"
    if has_signal_value(signals, "World War II setting"):
        return "World War II drama"
    if has_signal_value(signals, "period setting"):
        return "period drama"
    if has_signal_value(signals, "fantasy world"):
        return "fantasy adventure"
    if has_signal_value(signals, "federal investigation"):
        return "federal investigation story"
    if has_signal_value(signals, "corruption story"):
        return "corruption drama"
    if has_signal_value(signals, "offbeat comedy") and has_signal_value(
        signals,
        "crime story",
        "crime mystery",
        "organized crime story",
        "psychological thriller",
    ):
        return "crime drama"

    if not main_candidates:
        return None
    signal = main_candidates[0]
    value = signal.get("value")
    label = signal.get("label", "")
    if value in {"complex story"}:
        return None
    if value == "political power drama":
        return "political drama"
    if value == "court politics":
        return "court-intrigue drama"
    if value == "royal power drama":
        return "royal power drama"
    if value == "animation style":
        return "animated story"
    if value == "period setting":
        return "period drama"
    if value == "memory and identity":
        return "story about memory and identity"
    return lower_label(label)


def guidance_descriptor(signal: dict[str, Any]) -> str | None:
    dimension = signal.get("dimension")
    value = signal.get("value")
    label = signal.get("label")
    if value in {"dark fantasy", "neo-noir crime", "psychological thriller"}:
        return None
    if dimension in {"tone", "mood", "pacing"}:
        descriptor = lower_label(label)
        for suffix in (" tone", " mood", " pacing"):
            if descriptor.endswith(suffix):
                return descriptor[: -len(suffix)]
        return descriptor
    if dimension == "intensity" and value == "high":
        return "high-stakes"
    return None


def secondary_phrase(signals: dict[str, list[dict[str, Any]]], primary_phrase: str) -> str | None:
    if "nuclear disaster" in signal_values(signals):
        return "serious, grounded tension"
    if "organized-crime story" in primary_phrase and has_signal_value(signals, "gritty"):
        return "tense, character-driven stakes"
    if "political dark fantasy" in primary_phrase and has_signal_value(
        signals,
        "power struggle",
        "political power drama",
        "court politics",
    ):
        return "power struggles and foreboding tension"
    if "psychological thriller" in primary_phrase and has_signal_value(signals, "high"):
        return "a high-stakes edge"
    if "workplace comedy" in primary_phrase:
        return "an easygoing, character-focused feel"
    if "mockumentary comedy" in primary_phrase:
        return "playful workplace-style humor"
    if "supernatural horror" in primary_phrase:
        return "an eerie, heavier watch feel"
    if "martial-arts adventure" in primary_phrase:
        return "action-heavy pacing"
    if "animated" in primary_phrase and has_signal_value(signals, "hopeful", "warm"):
        return "family-friendly emotional warmth"
    if has_signal_value(signals, "high"):
        return "a high-stakes edge"
    if has_signal_value(signals, "action-heavy"):
        return "action-heavy pacing"
    return None


def product_chip_label(signal: dict[str, Any]) -> str:
    label = signal.get("label", "")
    value = signal.get("value")
    overrides = {
        "comic-book adaptation": "Comic-book-based",
        "memory and identity": "Memory and identity",
        "period setting": "Period setting",
        "World War II setting": "World War II setting",
        "organized crime story": "Organized crime",
        "political power drama": "Political power drama",
        "court politics": "Court intrigue",
        "royal power drama": "Royal power drama",
        "animation style": "Animated",
        "superhuman powers": "Superhero story",
    }
    return overrides.get(value, label)


def normalize_chip_list(chips: list[str], limit: int) -> list[str]:
    normalized = dedupe_preserve_order(chips)

    def remove_if_present(value: str) -> None:
        try:
            normalized.remove(value)
        except ValueError:
            return

    if "Superhero team story" in normalized and "Superhero story" in normalized:
        remove_if_present("Superhero story")
    if "Fantasy adventure" in normalized and "Fantasy world" in normalized:
        remove_if_present("Fantasy world")
    if "Magical world" in normalized and "Fantasy world" in normalized:
        remove_if_present("Fantasy world")
    return normalized[:limit]


def best_for_label(signal: dict[str, Any]) -> str:
    label = signal.get("label", "")
    dimension = signal.get("dimension")
    value = signal.get("value")
    value_overrides = {
        "World War II setting": "World War II dramas",
        "World War II drama": "World War II dramas",
        "period setting": "Period dramas",
        "fantasy adventure": "Fantasy adventures",
        "magical world": "Magical fantasy stories",
        "space sci-fi": "Space sci-fi",
        "investigation-led mystery": "Investigation-led mysteries",
        "murder mystery": "Murder mysteries",
        "serial-killer investigation": "Crime investigations",
        "spy story": "Spy thrillers",
        "heist story": "Heist stories",
        "creature threat": "Creature thrillers",
        "war story": "War dramas",
        "coming-of-age": "Coming-of-age stories",
        "coming-of-age story": "Coming-of-age stories",
        "space opera": "Space-opera stories",
        "dystopian future": "Dystopian sci-fi",
        "animation style": "Animated stories",
        "gangster crime story": "Gangster crime dramas",
        "friendship story": "Friendship-led stories",
        "artificial intelligence": "AI-driven sci-fi",
        "tech-driven sci-fi": "AI-driven sci-fi",
        "memory and identity": "Stories about memory and identity",
        "comic-book adaptation": "Comic-book-based stories",
        "martial arts action": "Martial-arts stories",
        "martial-arts action": "Martial-arts stories",
        "emotional character drama": "Emotional character dramas",
        "family drama": "Family dramas",
        "historical drama": "Historical dramas",
        "political drama": "Political dramas",
        "crime drama": "Crime dramas",
        "survival drama": "Survival dramas",
        "workplace drama": "Workplace dramas",
        "psychological drama": "Psychological dramas",
        "romantic drama": "Romantic dramas",
        "disaster drama": "Disaster dramas",
        "war drama": "War dramas",
        "post-apocalyptic survival drama": "Post-apocalyptic survival stories",
        "space survival sci-fi": "Space survival sci-fi",
        "animated family story": "Animated family stories",
        "supernatural mystery": "Supernatural mysteries",
        "mythic superhero mystery": "Superhero mysteries",
        "political thriller": "Political thrillers",
        "cartel crime drama": "Cartel crime dramas",
        "organized-crime drama": "Organized-crime dramas",
        "kitchen workplace drama": "Kitchen workplace dramas",
        "neo-noir crime": "Crime thrillers",
        "psychological thriller": "Psychological thrillers",
        "organized crime story": "Organized-crime dramas",
        "federal investigation": "Investigation-led mysteries",
        "corruption story": "Political dramas",
        "dark fantasy": "Political fantasy",
        "fantasy world": "Fantasy adventures",
        "political power drama": "Political power dramas",
        "workplace comedy": "Workplace comedies",
        "mockumentary comedy": "Mockumentary comedies",
        "sitcom comedy": "Sitcom comedies",
        "supernatural story": "Supernatural mysteries",
        "horror story": "Horror stories",
        "nuclear disaster": "Historical disaster dramas",
        "disaster story": "Disaster stories",
        "superhero team story": "Superhero stories",
        "superhero story": "Superhero stories",
        "superhuman powers": "Superhero stories",
        "antihero story": "Antihero stories",
        "time-travel story": "Time-travel stories",
        "reality-bending sci-fi": "Reality-bending sci-fi",
        "survival mystery": "Survival mysteries",
        "survival story": "Survival stories",
        "island survival": "Survival stories",
        "creature thriller": "Creature thrillers",
        "period comedy-drama": "Period comedy-dramas",
        "heist caper": "Heist capers",
        "caper": "Caper stories",
        "hotel setting": "Stylized hotel stories",
        "mentorship": "Mentor-protege stories",
        "wartime backdrop": "Period dramas",
        "class tension": "Social satires",
        "amateur investigation": "Amateur investigations",
        "international investigation": "International investigations",
        "heroic teamwork": "Team-led adventures",
        "mythology": "Mythic stories",
        "theme-park danger": "Creature thrillers",
        "adventure-driven": "Adventure stories",
        "mission-driven": "Mission-driven thrillers",
        "survival-driven": "Survival stories",
        "mind-bending": "Mind-bending stories",
        "high-concept": "High-concept sci-fi",
        "energetic": "High-energy stories",
        "heroic": "Heroic stories",
        "morally gray": "Morally gray stories",
        "hard-edged": "Hard-edged action stories",
        "playful": "Playful stories",
        "imaginative": "Imaginative fantasy",
        "mythic": "Mythic stories",
        "mysterious": "Mysteries",
        "revenge story": "Revenge stories",
    }
    if value in value_overrides:
        return value_overrides[value]
    if dimension in {"tone", "mood", "pacing", "intensity"}:
        descriptor = guidance_descriptor(signal) or lower_label(label)
        return clean_product_copy(f"{descriptor} stories")
    if label.lower().endswith(("story", "mystery", "investigation", "sci-fi", "action")):
        return f"{label} viewers"
    return f"{label} viewers"


def signal_matches_rule(signal: dict[str, Any], rule: dict[str, str]) -> bool:
    dimension = rule.get("dimension")
    if dimension and signal.get("dimension") != dimension:
        return False
    value = rule.get("value")
    if value and normalize_keyword_name(signal.get("value")) != normalize_keyword_name(value):
        return False
    label = rule.get("label")
    if label and normalize_keyword_name(signal.get("label")) != normalize_keyword_name(label):
        return False
    return bool(value or label or dimension)


def suppress_signals(
    signals: dict[str, list[dict[str, Any]]],
    rules: list[dict[str, str]],
) -> int:
    if not rules:
        return 0
    removed = 0
    for dimension, signal_list in signals.items():
        kept = []
        for signal in signal_list:
            signal_with_dimension = {**signal, "dimension": dimension}
            if any(signal_matches_rule(signal_with_dimension, rule) for rule in rules):
                removed += 1
            else:
                kept.append(signal)
        signals[dimension] = kept
    return removed


def demote_signals(
    signals: dict[str, list[dict[str, Any]]],
    rules: list[dict[str, str]],
) -> int:
    demoted = 0
    for dimension, signal_list in signals.items():
        for signal in signal_list:
            signal_with_dimension = {**signal, "dimension": dimension}
            if any(signal_matches_rule(signal_with_dimension, rule) for rule in rules):
                signal["confidence"] = "low"
                sources = signal.setdefault("sources", [])
                if "curated_override" not in sources:
                    sources.append("curated_override")
                demoted += 1
    if demoted:
        sort_public_signal_buckets(signals)
    return demoted


def apply_title_override(
    signals: dict[str, list[dict[str, Any]]],
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    if not override:
        return {"applied": False}
    suppressed = suppress_signals(signals, override.get("signals_to_suppress", []))
    demoted = demote_signals(signals, override.get("signals_to_demote", []))
    added = 0
    for signal in override.get("signals_to_add", []):
        if add_signal_to_bucket(
            signals,
            dimension=signal["dimension"],
            value=signal["value"],
            label=signal["label"],
            confidence=signal["confidence"],
            source="curated_override",
            prepend=True,
        ):
            added += 1
    if added or suppressed or demoted:
        sort_public_signal_buckets(signals)
    return {
        "applied": True,
        "signals_added": added,
        "signals_suppressed": suppressed,
        "signals_demoted": demoted,
        "notes": override.get("notes"),
    }


def apply_preferred_guidance(
    guidance: dict[str, Any],
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    if not override:
        return guidance
    updated = dict(guidance)
    if override.get("preferred_watch_feel"):
        updated["watch_feel"] = override["preferred_watch_feel"]
    if override.get("preferred_chips"):
        updated["chips"] = override["preferred_chips"]
    if override.get("preferred_best_for"):
        updated["best_for"] = override["preferred_best_for"]
    if override.get("preferred_consider_first") is not None:
        updated["consider_first"] = override.get("preferred_consider_first") or []
    return updated


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        clean_value = clean_text(value)
        if not clean_value:
            continue
        key = clean_value.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(clean_value)
    return deduped


def clean_product_copy(value: str) -> str:
    text_value = re.sub(r"\s+", " ", value).strip()
    if not text_value:
        return text_value
    return text_value[0].upper() + text_value[1:]


def contains_banned_user_facing_terms(value: str) -> bool:
    normalized = value.lower()
    return any(term in normalized for term in USER_FACING_BANNED_TERMS)


def build_watch_guidance(
    signals: dict[str, list[dict[str, Any]]],
    mapping_config: dict[str, Any],
) -> dict[str, Any]:
    display_config = mapping_config.get("signal_display") or {}
    dimension_order = display_config.get("dimension_order") or REQUIRED_DIMENSIONS
    chip_limit = int(display_config.get("chip_limit") or 5)
    best_for_limit = int(display_config.get("best_for_limit") or 4)
    consider_first_limit = int(display_config.get("consider_first_limit") or 2)

    main_candidates = top_signals(
        signals,
        ["audience_expectation", "topic_theme"],
        2,
    )
    descriptor_candidates = top_signals(
        signals,
        ["tone", "mood", "pacing", "intensity"],
        3,
    )
    primary_phrase = None if all_signals_low_confidence(signals) else product_primary_phrase(
        signals,
        main_candidates,
    )
    descriptors = dedupe_preserve_order(
        [
            descriptor
            for descriptor in (guidance_descriptor(signal) for signal in descriptor_candidates)
            if descriptor
        ]
    )[:2]

    if primary_phrase:
        support_phrase = secondary_phrase(signals, primary_phrase)
        descriptor_text = ", ".join(
            descriptor
            for descriptor in descriptors
            if descriptor not in primary_phrase
            and (not support_phrase or descriptor not in support_phrase)
        )
        lead_phrase = (
            f"{descriptor_text} {primary_phrase}".strip()
            if descriptor_text
            else primary_phrase
        )
        watch_feel = f"{article_for_phrase(lead_phrase)} {lead_phrase}"
        if support_phrase:
            watch_feel = f"{watch_feel} with {support_phrase}"
        watch_feel = f"{watch_feel}."
    else:
        watch_feel = LIMITED_GUIDANCE_TEXT
    watch_feel = clean_product_copy(watch_feel)

    chip_signals = top_signals(signals, dimension_order, chip_limit)
    chips = normalize_chip_list(
        [product_chip_label(signal) for signal in chip_signals],
        chip_limit,
    )

    best_for = dedupe_preserve_order(
        [best_for_label(signal) for signal in main_candidates + descriptor_candidates]
    )[:best_for_limit]

    consider_first: list[str] = []
    high_intensity = any(signal.get("value") == "high" for signal in signals.get("intensity", []))
    darker = any(
        signal.get("value") in {"dark", "bleak", "gritty", "haunting"}
        for dimension in ("tone", "mood")
        for signal in signals.get(dimension, [])
    )
    emotional_heavy = any(
        signal.get("value") in {"emotionally heavy", "emotional"}
        for dimension in ("content_caution_proxy", "mood")
        for signal in signals.get(dimension, [])
    )
    if high_intensity or darker:
        consider_first.append(
            "Better suited for viewers comfortable with darker or more intense stories."
        )
    if emotional_heavy:
        consider_first.append("Expect a more emotional watch.")
    consider_first = dedupe_preserve_order(consider_first)[:consider_first_limit]

    for field_name, values in {
        "watch_feel": [watch_feel],
        "chips": chips,
        "best_for": best_for,
        "consider_first": consider_first,
    }.items():
        for value in values:
            if contains_banned_user_facing_terms(value):
                raise KeywordSignalPreviewError(
                    f"Generated user-facing {field_name} contains internal wording: {value!r}"
                )

    return {
        "watch_feel": watch_feel,
        "best_for": best_for,
        "consider_first": consider_first,
        "chips": chips,
    }


def build_preview_item(
    content: KeywordContent,
    mapping_config: dict[str, Any],
    override_config: dict[str, Any] | None = None,
    include_debug: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    signals, analysis = map_keywords_for_content(
        content.keywords,
        mapping_config,
        include_debug=include_debug,
    )
    metadata_fallback = apply_metadata_fallback(signals, content)
    title_override = find_title_override(content, override_config)
    override_result = apply_title_override(signals, title_override)
    watch_guidance = build_watch_guidance(signals, mapping_config)
    watch_guidance = apply_preferred_guidance(watch_guidance, title_override)
    keyword_counts = {
        "raw_keywords": len({normalize_keyword_name(keyword) for keyword in content.keywords}),
        "mapped_keywords": len(analysis["mapped_keywords"]),
        "excluded_keywords": len(analysis["excluded_keywords"]),
        "spoiler_unsafe_keywords": len(analysis["spoiler_unsafe_keywords"]),
        "unmapped_keywords": len(analysis["unmapped_keywords"]),
    }
    item = {
        "content_id": content.content_id,
        "title": content.title,
        "content_type": content.content_type,
        "mapping_version": mapping_config.get("mapping_version"),
        "keyword_counts": keyword_counts,
        "signals": signals,
        "watch_guidance": watch_guidance,
        "metadata_fallback_applied": metadata_fallback["applied"],
        "curated_override_applied": override_result["applied"],
    }
    if override_result["applied"]:
        item["curated_override"] = {
            "title": title_override.get("title") if title_override else None,
            "signals_added": override_result.get("signals_added", 0),
            "signals_suppressed": override_result.get("signals_suppressed", 0),
            "signals_demoted": override_result.get("signals_demoted", 0),
        }
    if include_debug:
        item["debug"] = {
            "raw_keywords": sorted({normalize_keyword_name(keyword) for keyword in content.keywords}),
            "genres": content.genres,
            "mapped_keywords": analysis["mapped_keywords"],
            "excluded_keywords": analysis["excluded_keywords"],
            "spoiler_unsafe_keywords": analysis["spoiler_unsafe_keywords"],
            "unmapped_keywords": analysis["unmapped_keywords"],
            "metadata_fallback": metadata_fallback,
            "curated_override": override_result,
        }
    analysis["metadata_fallback"] = metadata_fallback
    analysis["curated_override"] = override_result
    return item, analysis


def counter_to_top_list(counter: Counter[str], limit: int = 25) -> list[dict[str, Any]]:
    return [
        {"keyword": keyword, "count": count}
        for keyword, count in counter.most_common(limit)
    ]


def signal_count_for_item(item: dict[str, Any]) -> int:
    return sum(len(signals) for signals in (item.get("signals") or {}).values())


def is_low_signal_quality(item: dict[str, Any]) -> bool:
    signal_count = signal_count_for_item(item)
    if signal_count == 0:
        return True
    if signal_count == 1:
        return True
    signals = [
        signal
        for signal_list in (item.get("signals") or {}).values()
        for signal in signal_list
    ]
    return bool(signals) and all(signal.get("confidence") == "low" for signal in signals)


def quality_item(item: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "content_id": item.get("content_id"),
        "title": item.get("title"),
        "content_type": item.get("content_type"),
        "signal_count": signal_count_for_item(item),
        "reason": reason,
    }


def primary_identity_issue(item: dict[str, Any]) -> str | None:
    watch_feel = ((item.get("watch_guidance") or {}).get("watch_feel") or "").lower()
    signals = item.get("signals") or {}
    all_public_signals = [
        signal
        for signal_list in signals.values()
        for signal in signal_list
    ]
    if watch_feel == LIMITED_GUIDANCE_TEXT.lower():
        return None
    if item.get("curated_override_applied") and watch_feel:
        if any(identity in watch_feel for identity in STRONG_PRIMARY_IDENTITIES):
            return None
        if not any(phrase in watch_feel for phrase in WEAK_PRIMARY_PHRASES):
            return None
    if any(identity in watch_feel for identity in STRONG_PRIMARY_IDENTITIES):
        return None
    if all_public_signals and all(
        confidence_rank(signal.get("confidence")) <= 1 for signal in all_public_signals
    ):
        return "primary phrase uses only low-confidence signals"
    if any(phrase in watch_feel for phrase in WEAK_PRIMARY_PHRASES):
        return "primary phrase uses weak abstract signal"
    if "offbeat comedy" in watch_feel and any(
        signal.get("value") in {
            "crime story",
            "crime mystery",
            "organized crime story",
            "psychological thriller",
            "drama",
        }
        for signal_list in signals.values()
        for signal in signal_list
    ):
        return "offbeat comedy used despite stronger drama/crime signal"
    has_topic_or_expectation = bool(signals.get("topic_theme") or signals.get("audience_expectation"))
    if watch_feel and not has_topic_or_expectation:
        return "watch feel exists without topic or audience signal"
    if watch_feel.strip() in {"a drama.", "a generic drama."}:
        return "generic drama with no stronger topic or audience identity"
    return None


def override_candidate_item(item: dict[str, Any], issue: str, action: str) -> dict[str, Any]:
    counts = item.get("keyword_counts") or {}
    return {
        "content_id": item.get("content_id"),
        "title": item.get("title"),
        "content_type": item.get("content_type"),
        "raw_keywords": counts.get("raw_keywords", 0),
        "mapped_keywords": counts.get("mapped_keywords", 0),
        "issue": issue,
        "suggested_action": action,
    }


def sources_for_item(item: dict[str, Any]) -> list[str]:
    sources = {
        source
        for signal_list in (item.get("signals") or {}).values()
        for signal in signal_list
        for source in signal.get("sources", [])
    }
    return sorted(sources, key=lambda source: SOURCE_PRIORITY.get(source, 9))


def report_title_row(item: dict[str, Any]) -> dict[str, Any]:
    counts = item.get("keyword_counts") or {}
    return {
        "content_id": item.get("content_id"),
        "title": item.get("title"),
        "content_type": item.get("content_type"),
        "raw_keywords": counts.get("raw_keywords", 0),
        "mapped_keywords": counts.get("mapped_keywords", 0),
        "signal_count": signal_count_for_item(item),
        "watch_feel": (item.get("watch_guidance") or {}).get("watch_feel"),
        "sources": sources_for_item(item),
    }


def semantic_issue_row(item: dict[str, Any], issue: str, action: str) -> dict[str, Any]:
    row = report_title_row(item)
    row["issue"] = issue
    row["suggested_action"] = action
    return row


def normalized_sentence(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.lower()).strip()
    if normalized and not normalized.endswith("."):
        normalized = f"{normalized}."
    return normalized


def generic_watch_feel_issue(item: dict[str, Any]) -> str | None:
    if item.get("curated_override_applied"):
        return None
    watch_feel = ((item.get("watch_guidance") or {}).get("watch_feel") or "").strip()
    if not watch_feel or watch_feel == LIMITED_GUIDANCE_TEXT:
        return None
    counts = item.get("keyword_counts") or {}
    raw_keywords = int(counts.get("raw_keywords") or 0)
    mapped_keywords = int(counts.get("mapped_keywords") or 0)
    if raw_keywords < 15:
        return None
    normalized = normalized_sentence(watch_feel)
    if mapped_keywords <= 2 and normalized in GENERIC_WATCH_FEEL_PHRASES:
        return "watch feel is too generic for a high-keyword title"
    if mapped_keywords <= 2 and len(re.findall(r"\w+", watch_feel)) <= 5:
        return "watch feel is too short for a high-keyword title"
    return None


def public_guidance_text(item: dict[str, Any]) -> str:
    guidance = item.get("watch_guidance") or {}
    return json.dumps(guidance, ensure_ascii=False).lower()


def semantic_conflict_issue(item: dict[str, Any]) -> str | None:
    watch_feel = ((item.get("watch_guidance") or {}).get("watch_feel") or "").lower()
    if not watch_feel or watch_feel == LIMITED_GUIDANCE_TEXT.lower():
        return None
    text_value = public_guidance_text(item)

    obvious_conflicts = (
        ("warm" in watch_feel and "revenge story" in watch_feel),
        ("warm" in watch_feel and "tech-driven sci-fi" in watch_feel),
        ("warm" in watch_feel and "high-stakes edge" in watch_feel),
        (
            "warm" in watch_feel
            and any(term in watch_feel for term in ("dark", "bleak", "gritty"))
        ),
    )
    if any(obvious_conflicts):
        return "watch feel combines conflicting tone and identity signals"

    if item.get("curated_override_applied") and primary_identity_issue(item) is None:
        return None

    if "superhero story" in watch_feel and not has_signal_value(
        item.get("signals") or {},
        "superhero team story",
        "comic-book adaptation",
    ):
        return "superhero identity may be too prominent"
    if "fantasy adventure" in watch_feel and any(
        term in text_value for term in ("mystery", "illusion", "psychological")
    ):
        return "fantasy adventure may hide the stronger mystery identity"
    if "serious war story" in watch_feel and any(
        term in text_value for term in ("aviation", "action")
    ):
        return "war story may overstate the primary identity"
    if "offbeat comedy" in watch_feel and any(
        term in text_value for term in ("crime", "drama", "thriller")
    ):
        return "offbeat comedy may dominate a stronger crime/drama identity"
    if "period drama" in watch_feel and any(
        term in text_value for term in ("creature", "disaster", "action")
    ):
        return "period drama may hide the stronger genre identity"
    return None


def has_productized_watch_feel(item: dict[str, Any]) -> bool:
    watch_feel = ((item.get("watch_guidance") or {}).get("watch_feel") or "").strip()
    return bool(watch_feel and watch_feel != LIMITED_GUIDANCE_TEXT)


def has_useful_chips(item: dict[str, Any]) -> bool:
    return bool((item.get("watch_guidance") or {}).get("chips"))


def has_topic_or_audience_signal(item: dict[str, Any]) -> bool:
    signals = item.get("signals") or {}
    return bool(signals.get("topic_theme") or signals.get("audience_expectation"))


def source_counts_for_items(preview_items: list[dict[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for item in preview_items:
        for signal_list in (item.get("signals") or {}).values():
            for signal in signal_list:
                for source in signal.get("sources", []):
                    counter[source] += 1
    return counter


def looks_like_high_value_unmapped_keyword(keyword: str, count: int) -> bool:
    if count < 3:
        return False
    normalized = normalize_keyword_name(keyword)
    if not normalized or len(normalized) < 4:
        return False
    if normalized in LOCATION_NOISE_HINTS:
        return False
    if any(noise in normalized for noise in UNMAPPED_NOISE_HINTS):
        return False
    if re.search(r"\b(19|20)\d{2}s?\b", normalized):
        return True
    return any(
        hint in normalized
        for hint in (
            "comedy",
            "crime",
            "dark",
            "detective",
            "disaster",
            "fantasy",
            "horror",
            "magic",
            "mystery",
            "noir",
            "political",
            "prison",
            "psychological",
            "supernatural",
            "thriller",
            "war",
        )
    )


def high_value_unmapped_candidates(counter: Counter[str], limit: int = 25) -> list[dict[str, Any]]:
    return [
        {"keyword": keyword, "count": count}
        for keyword, count in counter.most_common()
        if looks_like_high_value_unmapped_keyword(keyword, count)
    ][:limit]


def build_report(
    *,
    generated_at: str,
    mapping_file: Path,
    output_path: Path,
    report_path: Path,
    mapping_config: dict[str, Any],
    override_file: Path | None = None,
    override_config: dict[str, Any] | None = None,
    content_items: list[KeywordContent],
    preview_items: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
) -> dict[str, Any]:
    raw_keyword_counter: Counter[str] = Counter()
    mapped_counter: Counter[str] = Counter()
    unmapped_counter: Counter[str] = Counter()
    excluded_counter: Counter[str] = Counter()
    spoiler_counter: Counter[str] = Counter()
    dimension_titles: dict[str, set[int]] = defaultdict(set)
    dimension_signal_counts: Counter[str] = Counter()
    coverage_by_type: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "titles_seen": 0,
            "titles_with_mapped_signals": 0,
            "titles_without_mapped_signals": 0,
        }
    )

    analyses_by_content = {
        item["content_id"]: analysis
        for item, analysis in zip(preview_items, analyses)
    }
    preview_item_map = preview_items_by_id(preview_items)
    for content in content_items:
        coverage = coverage_by_type[content.content_type]
        coverage["titles_seen"] += 1
        raw_keyword_counter.update(
            normalize_keyword_name(keyword)
            for keyword in content.keywords
            if normalize_keyword_name(keyword)
        )
        analysis = analyses_by_content.get(content.content_id, {})
        has_signals = any(
            preview_signal
            for signals in (
                preview_item_map.get(content.content_id, {}).get("signals") or {}
            ).values()
            for preview_signal in signals
        )
        if has_signals:
            coverage["titles_with_mapped_signals"] += 1
        else:
            coverage["titles_without_mapped_signals"] += 1
        mapped_counter.update(analysis.get("mapped_keyword_hits", []))
        unmapped_counter.update(analysis.get("unmapped_keyword_hits", []))
        excluded_counter.update(analysis.get("excluded_keyword_hits", []))
        spoiler_counter.update(analysis.get("spoiler_unsafe_keyword_hits", []))

    for item in preview_items:
        for dimension, signals in item.get("signals", {}).items():
            if signals:
                dimension_titles[dimension].add(item["content_id"])
                dimension_signal_counts[dimension] += len(signals)

    titles_with_mapped = sum(
        1
        for item in preview_items
        if any(signals for signals in item.get("signals", {}).values())
    )
    sample_watch_guidance = [
        {
            "content_id": item["content_id"],
            "title": item["title"],
            "content_type": item["content_type"],
            "watch_guidance": item["watch_guidance"],
        }
        for item in preview_items[:10]
    ]
    titles_with_only_one_signal = [
        quality_item(item, "only one mapped signal")
        for item in preview_items
        if signal_count_for_item(item) == 1
    ]
    titles_with_no_watch_feel = [
        quality_item(item, "no productized watch feel")
        for item in preview_items
        if (item.get("watch_guidance") or {}).get("watch_feel") == LIMITED_GUIDANCE_TEXT
    ]
    titles_with_low_signal_quality = [
        quality_item(item, "no, single, or only low-confidence mapped signals")
        for item in preview_items
        if is_low_signal_quality(item)
    ]
    titles_with_bad_primary_identity = [
        quality_item(item, primary_identity_issue(item) or "bad primary identity")
        for item in preview_items
        if primary_identity_issue(item)
    ]
    titles_with_generic_watch_feel = [
        semantic_issue_row(
            item,
            generic_watch_feel_issue(item) or "generic watch feel",
            "improve_phrase_rule",
        )
        for item in preview_items
        if generic_watch_feel_issue(item)
    ]
    titles_with_semantic_conflicts = [
        semantic_issue_row(
            item,
            semantic_conflict_issue(item) or "semantic conflict",
            "add_curated_override",
        )
        for item in preview_items
        if semantic_conflict_issue(item)
    ]
    override_candidates_by_content: dict[int, dict[str, Any]] = {}
    for item in titles_with_no_watch_feel:
        candidate_item = preview_item_map[item["content_id"]]
        override_candidates_by_content[item["content_id"]] = override_candidate_item(
            candidate_item,
            "no productized watch feel",
            "add_metadata_fallback",
        )
    for item in titles_with_low_signal_quality:
        candidate_item = preview_item_map[item["content_id"]]
        if candidate_item.get("curated_override_applied") and has_productized_watch_feel(candidate_item):
            continue
        override_candidates_by_content.setdefault(
            item["content_id"],
            override_candidate_item(candidate_item, "low signal quality", "add_mapping"),
        )
    for item in titles_with_bad_primary_identity:
        candidate_item = preview_item_map[item["content_id"]]
        override_candidates_by_content[item["content_id"]] = override_candidate_item(
            candidate_item,
            item["reason"],
            "add_curated_override",
        )
    for item in titles_with_generic_watch_feel:
        candidate_item = preview_item_map[item["content_id"]]
        override_candidates_by_content.setdefault(
            item["content_id"],
            override_candidate_item(
                candidate_item,
                item["issue"],
                item["suggested_action"],
            ),
        )
    for item in titles_with_semantic_conflicts:
        candidate_item = preview_item_map[item["content_id"]]
        override_candidates_by_content[item["content_id"]] = override_candidate_item(
            candidate_item,
            item["issue"],
            item["suggested_action"],
        )
    for item in preview_items:
        counts = item.get("keyword_counts") or {}
        if item.get("curated_override_applied") and has_productized_watch_feel(item):
            continue
        if (
            counts.get("raw_keywords", 0) >= 12
            and counts.get("mapped_keywords", 0) <= 2
            and not has_productized_watch_feel(item)
        ):
            override_candidates_by_content.setdefault(
                item["content_id"],
                override_candidate_item(
                    item,
                    "many raw keywords but empty guidance",
                    "add_mapping",
                ),
            )
        if not has_useful_chips(item):
            override_candidates_by_content.setdefault(
                item["content_id"],
                override_candidate_item(item, "no useful chips", "add_curated_override"),
            )
        if not has_topic_or_audience_signal(item):
            override_candidates_by_content.setdefault(
                item["content_id"],
                override_candidate_item(
                    item,
                    "no topic or audience signal after fallback",
                    "add_metadata_fallback",
                ),
            )
    newly_mapped_keywords = mapping_config.get("newly_mapped_from_previous_version") or []
    newly_mapped_hits = [
        {"keyword": keyword, "count": mapped_counter.get(keyword, 0)}
        for keyword in newly_mapped_keywords
        if mapped_counter.get(keyword, 0)
    ]
    source_counter = source_counts_for_items(preview_items)
    titles_using_metadata_fallback = [
        report_title_row(item)
        for item in preview_items
        if item.get("metadata_fallback_applied")
    ]
    titles_using_curated_override = [
        report_title_row(item)
        for item in preview_items
        if item.get("curated_override_applied")
    ]
    titles_keyword_only = [
        report_title_row(item)
        for item in preview_items
        if any(signals for signals in (item.get("signals") or {}).values())
        and not item.get("metadata_fallback_applied")
        and not item.get("curated_override_applied")
    ]
    curated_review_candidates_by_content: dict[int, dict[str, Any]] = {}
    for item in titles_with_generic_watch_feel + titles_with_semantic_conflicts:
        curated_review_candidates_by_content[item["content_id"]] = item
    for item in titles_with_no_watch_feel:
        candidate_item = preview_item_map[item["content_id"]]
        curated_review_candidates_by_content.setdefault(
            item["content_id"],
            semantic_issue_row(
                candidate_item,
                "no productized watch feel",
                "add_metadata_fallback",
            ),
        )
    for item in titles_with_bad_primary_identity:
        candidate_item = preview_item_map[item["content_id"]]
        curated_review_candidates_by_content[item["content_id"]] = semantic_issue_row(
            candidate_item,
            item["reason"],
            "add_curated_override",
        )
    titles_needing_curated_review = list(curated_review_candidates_by_content.values())

    return {
        "generated_at": generated_at,
        "db_write_performed": False,
        "preview_generator_version": PREVIEW_GENERATOR_VERSION,
        "semantic_qa_version": SEMANTIC_QA_VERSION,
        "mapping_file": relative_path(mapping_file),
        "mapping_version": mapping_config.get("mapping_version"),
        "override_file": relative_path(override_file) if override_file else None,
        "override_version": (override_config or {}).get("override_version"),
        "output_path": relative_path(output_path),
        "report_path": relative_path(report_path),
        "titles_seen": len(content_items),
        "titles_with_keywords": len(content_items),
        "titles_with_mapped_signals": titles_with_mapped,
        "titles_without_mapped_signals": len(content_items) - titles_with_mapped,
        "total_raw_keyword_relationships_seen": sum(len(content.keywords) for content in content_items),
        "unique_raw_keywords_seen": len(raw_keyword_counter),
        "unique_keywords_mapped": len(mapped_counter),
        "unique_keywords_unmapped": len(unmapped_counter),
        "excluded_keyword_hits": sum(excluded_counter.values()),
        "spoiler_unsafe_keyword_hits": sum(spoiler_counter.values()),
        "top_mapped_keywords": counter_to_top_list(mapped_counter),
        "top_unmapped_keywords": counter_to_top_list(unmapped_counter),
        "top_unmapped_high_value_candidates": high_value_unmapped_candidates(
            unmapped_counter
        ),
        "top_excluded_keywords": counter_to_top_list(excluded_counter),
        "top_spoiler_unsafe_keywords": counter_to_top_list(spoiler_counter),
        "signals_by_source": dict(sorted(source_counter.items())),
        "titles_using_metadata_fallback_count": len(titles_using_metadata_fallback),
        "titles_using_metadata_fallback": titles_using_metadata_fallback,
        "titles_using_curated_override_count": len(titles_using_curated_override),
        "titles_using_curated_override": titles_using_curated_override,
        "titles_keyword_only_count": len(titles_keyword_only),
        "titles_keyword_only": titles_keyword_only,
        "newly_mapped_from_previous_version": {
            "keywords": newly_mapped_keywords,
            "hits": newly_mapped_hits,
        },
        "titles_with_low_signal_quality": titles_with_low_signal_quality,
        "titles_with_only_one_signal": titles_with_only_one_signal,
        "titles_with_no_watch_feel": titles_with_no_watch_feel,
        "titles_with_bad_primary_identity": titles_with_bad_primary_identity,
        "titles_with_generic_watch_feel": titles_with_generic_watch_feel,
        "titles_with_semantic_conflicts": titles_with_semantic_conflicts,
        "titles_needing_curated_review": titles_needing_curated_review,
        "semantic_quality_summary": {
            "generic_watch_feel_count": len(titles_with_generic_watch_feel),
            "semantic_conflict_count": len(titles_with_semantic_conflicts),
            "curated_review_candidate_count": len(titles_needing_curated_review),
        },
        "top_override_candidates": list(override_candidates_by_content.values())[:25],
        "coverage_by_content_type": dict(sorted(coverage_by_type.items())),
        "dimension_coverage": {
            dimension: {
                "titles_with_signal": len(dimension_titles.get(dimension, set())),
                "signal_count": dimension_signal_counts.get(dimension, 0),
            }
            for dimension in mapping_config["dimensions"]
        },
        "sample_watch_guidance": sample_watch_guidance,
        "warnings": mapping_config.get("warnings", []),
        "errors": [],
    }


def preview_items_by_id(preview_items: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {item["content_id"]: item for item in preview_items}


def build_preview_payload(
    *,
    generated_at: str,
    mapping_file: Path,
    mapping_config: dict[str, Any],
    override_file: Path,
    override_config: dict[str, Any],
    content_items: list[KeywordContent],
    include_debug: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    preview_items: list[dict[str, Any]] = []
    analyses: list[dict[str, Any]] = []
    for content in content_items:
        item, analysis = build_preview_item(
            content,
            mapping_config,
            override_config=override_config,
            include_debug=include_debug,
        )
        preview_items.append(item)
        analyses.append(analysis)

    return {
        "generated_at": generated_at,
        "source": "tmdb_keyword_signal_preview",
        "db_write_performed": False,
        "mapping_file": relative_path(mapping_file),
        "mapping_version": mapping_config.get("mapping_version"),
        "override_file": relative_path(override_file),
        "override_version": override_config.get("override_version"),
        "include_debug": include_debug,
        "items": preview_items,
    }, analyses


def print_summary(report: dict[str, Any]) -> None:
    print("Keyword signal preview complete.")
    print("DB writes: none")
    print(f"Titles seen: {report.get('titles_seen', 0)}")
    print(f"Titles with mapped signals: {report.get('titles_with_mapped_signals', 0)}")
    print(f"Unique raw keywords seen: {report.get('unique_raw_keywords_seen', 0)}")
    print(f"Unique mapped keywords: {report.get('unique_keywords_mapped', 0)}")
    print(f"Excluded keyword hits: {report.get('excluded_keyword_hits', 0)}")
    print(f"Spoiler-unsafe keyword hits: {report.get('spoiler_unsafe_keyword_hits', 0)}")
    print(f"Preview: {report.get('output_path')}")
    print(f"Report: {report.get('report_path')}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    safety_error = output_safety_error(args)
    if safety_error:
        print(f"ERROR: {safety_error}", file=sys.stderr)
        return 1

    mapping_file = resolve_path(args.mapping_file)
    override_file = resolve_path(args.override_file)
    output_path = resolve_path(args.output)
    report_path = resolve_path(args.report_output)

    try:
        mapping_config = load_mapping_config(mapping_file)
        override_config = load_override_config(override_file)
        content_id_filter = selected_content_ids(args)
    except KeywordSignalPreviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    database_url = os.getenv(DATABASE_URL_ENV)
    if not database_url:
        print(
            f"ERROR: Missing {DATABASE_URL_ENV}. Export it before running this preview.",
            file=sys.stderr,
        )
        return 1

    try:
        engine = create_engine(database_url)
        with engine.connect() as connection:
            rows = fetch_imported_tmdb_keywords(connection)
    except SQLAlchemyError as exc:
        print(f"ERROR: Keyword signal preview failed: {exc}", file=sys.stderr)
        return 1

    content_items = group_keyword_rows(
        rows,
        content_type_filter=args.content_type,
        content_id_filter=content_id_filter,
        limit=args.limit,
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    preview_payload, analyses = build_preview_payload(
        generated_at=generated_at,
        mapping_file=mapping_file,
        mapping_config=mapping_config,
        override_file=override_file,
        override_config=override_config,
        content_items=content_items,
        include_debug=args.include_debug,
    )
    report = build_report(
        generated_at=generated_at,
        mapping_file=mapping_file,
        output_path=output_path,
        report_path=report_path,
        mapping_config=mapping_config,
        override_file=override_file,
        override_config=override_config,
        content_items=content_items,
        preview_items=preview_payload["items"],
        analyses=analyses,
    )

    write_json(output_path, preview_payload)
    write_json(report_path, report)
    print_summary(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
