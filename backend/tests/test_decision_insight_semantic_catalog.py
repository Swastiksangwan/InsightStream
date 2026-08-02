import json
from pathlib import Path

import pytest

from analytics.scripts.audits.audit_decision_display_quality import (
    audit_display_record,
)
from app.services.source_signal_service import build_decision_display


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "decision_insight_semantic_catalog.json"
)


def load_cases():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def signal_from_row(row):
    dimension, label, confidence, *source_names = row
    return {
        "dimension": dimension,
        "value": label.casefold(),
        "label": label,
        "confidence": confidence,
        "spoiler_safe": True,
        "source_names": source_names[0] if source_names else ["tmdb_keywords"],
    }


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case["title"])
def test_semantic_regression_catalog(case):
    signals = [signal_from_row(row) for row in case["signals"]]
    guidance = {
        "watch_feel": "Stored preview prose is non-authoritative.",
        "chips": [signal["label"] for signal in signals],
        "best_for": [],
        "consider_first": [],
        "curated_override_applied": case.get("curated_override_applied", False),
        "metadata_fallback_applied": not bool(signals),
    }
    context = {
        "content": {
            "id": 999,
            "title": case["title"],
            "type": case["content_type"],
            "overview": case["overview"],
        },
        "genres": case["genres"],
        "ratings": {
            "unified_score": 82,
            "scoring_source_count": 2,
            "sources": [
                {
                    "source_name": "fixture_audience_one",
                    "source_category": "audience",
                    "included_in_unified_score": True,
                },
                {
                    "source_name": "fixture_audience_two",
                    "source_category": "audience",
                    "included_in_unified_score": True,
                },
            ],
        },
    }
    display = build_decision_display(
        guidance,
        signals,
        display_context=context,
        include_insight_plan=True,
    )
    plan = display.pop("insight_plan")
    display["_insight_plan"] = plan
    audit = audit_display_record(context["content"], display)
    public_text = str(
        {
            "primary_insight": display.get("primary_insight"),
            "profile": display.get("profile"),
            "supporting_facts": display.get("supporting_facts"),
        }
    ).casefold()

    for required in case["required_public_concepts"]:
        assert required.casefold() in public_text
    for forbidden in case["forbidden_public_concepts"]:
        assert forbidden.casefold() not in public_text
    selected_identity = (plan.get("primary_identity") or {}).get("text") or ""
    differentiators = " ".join(
        str((plan.get(key) or {}).get("text") or "")
        for key in ("primary_differentiator", "secondary_differentiator")
    )
    for required in case.get("required_primary_identity_concepts", []):
        assert required.casefold() in selected_identity.casefold()
    for forbidden in case.get("forbidden_primary_identity_concepts", []):
        assert forbidden.casefold() not in selected_identity.casefold()
    for forbidden in case.get("forbidden_primary_differentiator_concepts", []):
        assert forbidden.casefold() not in differentiators.casefold()
    for required in case.get("required_primary_substrings", []):
        assert required in display["primary_insight"]
    for forbidden in case.get("forbidden_primary_substrings", []):
        assert forbidden not in display["primary_insight"]
    assert audit["display_ready"] is case["expected_display_ready"]
    assert audit["source_signal_review_required"] is case[
        "expected_source_signal_review_required"
    ]
    assert display["primary_insight"] == build_decision_display(
        guidance,
        signals,
        display_context=context,
    )["primary_insight"]
