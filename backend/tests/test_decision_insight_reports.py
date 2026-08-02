import json
from datetime import date

from analytics.scripts.audits.build_decision_insight_baseline import (
    build_payload,
    length_bucket,
)
from analytics.scripts.audits.compare_decision_insight_formatter import (
    build_comparison,
    build_identity_conflict_report,
)
from analytics.scripts.audits.build_decision_insight_stratified_review import (
    build_payload as build_stratified_payload,
    stratify_records,
)
from analytics.scripts.audits.decision_insight_report_metadata import (
    decision_insight_versions,
)
from analytics.scripts.audits.explain_decision_insight import (
    build_explanation,
    json_default,
)


def baseline_record():
    return {
        "content_id": 7,
        "title": "Neutral Title",
        "overview": "A detective investigates pressure inside an institution.",
        "genres": ["Crime", "Drama"],
        "current_primary_insight": (
            "A tense crime drama built around investigation, and pressure."
        ),
        "compact_identity": ["Crime drama"],
        "compact_themes": ["Investigation", "Institutional pressure"],
        "compact_feel": ["Tense"],
        "compact_pace": None,
        "source_signals": {
            "audience_expectation": [
                {
                    "value": "crime drama",
                    "label": "Crime drama",
                    "confidence": "medium",
                }
            ]
        },
        "fallback_dependencies": {
            "metadata_fallback_applied": False,
            "signal_sources": ["tmdb_keywords"],
        },
        "title_override_involved": False,
        "selected_sentence_template": "built_around",
        "quality_score": 80,
        "quality_issue_codes": ["PRIMARY_INSIGHT_PUNCTUATION"],
    }


def proposed_detail():
    return {
        "content": {
            "id": 7,
            "title": "Neutral Title",
            "type": "movie",
            "year": 2024,
        },
        "decision_layer": {
            "display": {
                "primary_insight": (
                    "A tense crime drama shaped by institutional pressure."
                ),
                "profile": {
                    "identity": ["Crime drama"],
                    "themes": ["Institutional pressure"],
                    "feel": ["Tense"],
                    "pace": None,
                    "best_for": [],
                    "consider_first": [],
                },
                "supporting_facts": [],
            },
            "debug": {
                "insight_plan": {
                    "primary_identity": {
                        "text": "Crime drama",
                        "role": "identity",
                        "concept_family": "crime",
                        "source": "source_signal:audience_expectation:crime drama",
                        "evidence": "Crime drama",
                        "supported": True,
                    },
                    "tone_modifier": {
                        "text": "tense",
                        "role": "adjective",
                        "concept_family": "tense",
                        "source": "display_profile",
                        "evidence": "profile.feel:Tense",
                        "supported": True,
                    },
                    "mood_modifier": None,
                    "primary_differentiator": {
                        "text": "institutional pressure",
                        "role": "about_phrase",
                        "concept_family": "institutional pressure",
                        "source": "source_signal:topic_theme:institutional pressure",
                        "evidence": "topic_theme:Institutional pressure",
                        "supported": True,
                    },
                    "secondary_differentiator": None,
                    "pacing_modifier": None,
                    "audience_modifier": None,
                    "template_family": "identity_conflict",
                    "rejected_candidates": [],
                    "validation_errors": [],
                    "formatter_version": "2.0.2",
                }
            },
        },
    }


def test_baseline_payload_has_deterministic_catalog_metrics():
    record = baseline_record()

    payload = build_payload([record])

    assert payload["db_write_performed"] is False
    assert payload["catalog_metrics"]["total_titles"] == 1
    assert payload["catalog_metrics"]["grammatical_problems"] == 1
    assert payload["catalog_metrics"]["template_distribution"] == {
        "built_around": 1
    }
    assert payload["records"] == [record]
    assert payload["versions"] == decision_insight_versions()
    assert length_bucket("Short") == "under_40"


def test_comparison_report_preserves_plan_evidence_and_change_state():
    baseline = {
        "report_version": "decision-insight-baseline-v2",
        "records": [baseline_record()],
    }

    payload = build_comparison(baseline, {7: proposed_detail()})
    record = payload["records"][0]

    assert payload["db_write_performed"] is False
    assert payload["versions"] == decision_insight_versions()
    assert payload["catalog_metrics"]["total_titles"] == 1
    assert payload["catalog_metrics"]["sentences_changed"] == 1
    assert record["semantic_change"] is True
    assert record["after_template_family"] == "identity_conflict"
    assert record["insight_plan"]["validation_errors"] == []
    assert any(
        item["source"].startswith("source_signal:")
        for item in record["component_evidence"]
    )


def test_comparison_supports_empty_catalog():
    payload = build_comparison(
        {"report_version": "decision-insight-baseline-v2", "records": []},
        {},
    )

    assert payload["catalog_metrics"]["total_titles"] == 0
    assert payload["records"] == []
    assert payload["manual_review_titles"] == []


def test_comparison_includes_title_added_after_baseline_capture():
    detail = proposed_detail()
    detail["content"] = {
        **detail["content"],
        "id": 8,
        "title": "Future Batch Title",
        "original_language": "ko",
    }
    payload = build_comparison(
        {"report_version": "decision-insight-baseline-v2", "records": []},
        {8: detail},
    )

    record = payload["records"][0]
    assert payload["catalog_metrics"]["total_titles"] == 1
    assert record["baseline_status"] == "new_title"
    assert record["current_sentence"] is None
    assert record["proposed_sentence"]
    assert record["original_language"] == "ko"


def test_stratified_review_is_deterministic_and_never_under_samples():
    records = []
    templates = ["identity_about", "identity_conflict", "thematic_exploration"]
    for index in range(60):
        records.append(
            {
                "content_id": index + 1,
                "title": f"Title {index + 1}",
                "content_type": "movie" if index % 2 == 0 else "series",
                "original_language": ("hi", "ko", "fr", "en")[index % 4],
                "genres": [["Drama"], ["Horror"], ["Documentary"], ["Animation"]][
                    index % 4
                ],
                "signal_count": index % 12,
                "after_template_family": templates[index % len(templates)],
                "after_issue_codes": [],
                "manual_review": index == 0,
                "insight_plan": {
                    "primary_identity": {
                        "text": "Drama",
                        "source": "display_profile",
                    },
                    "primary_differentiator": (
                        {
                            "text": "an investigation",
                            "source": "overview_rule",
                            "evidence": (
                                "rule=investigation;matched=investigates;"
                                "scope=narrower"
                            ),
                        }
                        if index == 1
                        else None
                    ),
                },
            }
        )

    first = stratify_records(records, minimum=40)
    second = stratify_records(list(reversed(records)), minimum=40)
    payload = build_stratified_payload({"records": records}, minimum=40)

    assert len(first) >= 40
    assert [row["content_id"] for row in first] == [
        row["content_id"] for row in second
    ]
    assert payload["catalog_size"] == 60
    assert payload["sample_size"] >= 40
    assert payload["overview_context_provenance"][0]["governing_rule"] == (
        "investigation"
    )
    assert "versions" in payload
    assert all(row["human_review_status"] == "unreviewed" for row in first)
    assert all(row["human_review_notes"] is None for row in first)
    assert all("reviewer_recommendation" not in row for row in first)


def test_identity_conflict_report_is_deterministic_and_explicitly_automated():
    comparison = {
        "generated_at": "2026-07-31T00:00:00+00:00",
        "catalog_metrics": {"total_titles": 1},
        "records": [
            {
                "content_id": 7,
                "title": "Neutral Title",
                "rejected_candidate_components": [
                    {
                        "candidate": "Romantic drama",
                        "reason": "identity_metadata_conflict",
                        "conflict_reason": "missing_central_romance_evidence",
                        "source": "source_signal:audience_expectation:romantic drama",
                        "confidence": "medium",
                        "evidence": "requires Romance genre",
                    }
                ],
            }
        ],
    }

    report = build_identity_conflict_report(comparison)

    assert report["conflict_count"] == 1
    assert report["records"][0]["formatter_rejected"] is True
    assert report["records"][0]["recommended_future_action"] == (
        "review_source_signal_mapping"
    )
    assert report["versions"] == decision_insight_versions()


def test_single_title_explanation_exposes_plan_readiness_and_versions():
    detail = proposed_detail()
    detail["content"]["overview"] = "A detective investigates institutional pressure."
    detail["genres"] = ["Crime", "Drama"]
    detail["decision_layer"]["watch_profile"] = {
        "watch_feel": detail["decision_layer"]["display"]["primary_insight"],
        "chips": ["Crime drama"],
        "best_for": ["Crime dramas"],
        "consider_first": [],
    }
    detail["decision_layer"]["decision_support"] = {
        "headline": "Best suited for viewers looking for a tense crime drama.",
        "reasons": [],
        "cautions": [],
    }
    explanation = build_explanation(
        detail,
        [
            {
                "dimension": "audience_expectation",
                "value": "crime drama",
                "label": "Crime drama",
                "confidence": "medium",
                "spoiler_safe": True,
                "source_names": ["tmdb_keywords"],
            }
        ],
    )

    assert explanation["versions"] == decision_insight_versions()
    assert explanation["db_write_performed"] is False
    assert explanation["identity_candidates"][0]["selection_result"] == "selected"
    assert explanation["display_ready"] is True
    assert explanation["source_signal_review_required"] is False


def test_single_title_explanation_json_serializes_content_dates():
    payload = {"content": {"release_date": date(2026, 8, 1)}}

    encoded = json.dumps(payload, default=json_default)

    assert '"release_date": "2026-08-01"' in encoded
