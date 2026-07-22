"""Canonical keyword normalization shared by source-signal tooling."""

from __future__ import annotations

import re
from typing import Any


KEYWORD_NORMALIZATION_VERSION = "source-signal-keyword-v1"
KEYWORD_NORMALIZATION_STRATEGY = (
    "lowercase; ampersand-to-and; hyphen/slash/underscore-to-space; "
    "remove remaining punctuation; collapse whitespace"
)


def normalize_keyword_name(value: Any) -> str:
    """Return the canonical source-signal mapping identity for a keyword."""
    if value is None:
        return ""
    text_value = str(value).strip().lower().replace("&", " and ")
    text_value = re.sub(r"[-_/]+", " ", text_value)
    text_value = re.sub(r"[^\w\s]", "", text_value)
    return re.sub(r"\s+", " ", text_value).strip()


def keyword_normalization_metadata() -> dict[str, str]:
    return {
        "version": KEYWORD_NORMALIZATION_VERSION,
        "strategy": KEYWORD_NORMALIZATION_STRATEGY,
    }

