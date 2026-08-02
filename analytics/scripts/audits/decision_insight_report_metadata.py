"""Shared version provenance for Decision Insight diagnostic reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from analytics.scripts.common.paths import REPO_ROOT, ensure_backend_import_path

ensure_backend_import_path()

from app.services.decision_insight_formatter import (  # noqa: E402
    DECISION_INSIGHT_FORMATTER_VERSION,
)


CONFIG_ROOT = REPO_ROOT / "analytics/config"
MAPPING_CONFIG = CONFIG_ROOT / "source_signal_keyword_mapping.json"
REVIEW_CONFIG = CONFIG_ROOT / "source_signal_keyword_review_decisions.json"
OVERRIDE_CONFIG = CONFIG_ROOT / "source_signal_title_overrides.json"


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return payload


def decision_insight_versions() -> dict[str, str]:
    mapping = load_json_object(MAPPING_CONFIG)
    review = load_json_object(REVIEW_CONFIG)
    overrides = load_json_object(OVERRIDE_CONFIG)
    mapping_version = mapping.get("mapping_version")
    supported_mapping_version = review.get("supports_mapping_version")
    if supported_mapping_version != mapping_version:
        raise ValueError(
            "Source-signal review/config version drift: "
            f"{supported_mapping_version!r} does not support {mapping_version!r}."
        )
    return {
        "formatter_version": DECISION_INSIGHT_FORMATTER_VERSION,
        "keyword_mapping_version": str(mapping_version),
        "review_decision_version": str(review.get("review_version")),
        "review_supports_mapping_version": str(supported_mapping_version),
        "title_override_version": str(overrides.get("override_version")),
    }
