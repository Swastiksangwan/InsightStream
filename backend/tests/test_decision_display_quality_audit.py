import argparse
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_audit_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "analytics" / "scripts" / "audits" / "audit_decision_display_quality.py"
    spec = importlib.util.spec_from_file_location(
        "audit_decision_display_quality",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_decision_display_quality"] = module
    spec.loader.exec_module(module)
    return module


def clean_display(**overrides):
    display = {
        "primary_insight": (
            "A surreal sci-fi heist built around memory and identity, "
            "with strong audience backing."
        ),
        "profile": {
            "identity": ["Sci-fi heist"],
            "themes": ["Memory and identity"],
            "feel": ["Surreal", "Thoughtful"],
            "pace": "Plot-driven and puzzle-like",
            "best_for": ["Heist stories", "Stories about memory and identity"],
            "consider_first": ["Dense structure may require attention."],
        },
        "supporting_facts": [
            {"label": "Audience", "value": "86/100 from 2 scoring sources"},
            {"label": "Access", "value": "Streaming in India"},
        ],
    }
    display.update(overrides)
    return display


def audit_record(module, display):
    return module.audit_display_record(
        {"id": 6, "title": "Inception", "type": "movie", "year": 2010},
        display,
    )


def issue_codes(record):
    return {issue["code"] for issue in record["issues"]}


def test_clean_display_scores_high():
    module = load_audit_module()

    record = audit_record(module, clean_display())

    assert record["display_quality_score"] == 100
    assert record["grade"] == "excellent"
    assert record["display_ready"] is True
    assert record["review_required"] is False
    assert record["issues"] == []


def test_missing_display_is_critical():
    module = load_audit_module()

    record = audit_record(module, None)

    assert "MISSING_DISPLAY" in issue_codes(record)
    assert record["issue_counts"]["critical"] == 1
    assert record["grade"] == "blocked"
    assert record["display_ready"] is False


def test_technical_leak_is_critical():
    module = load_audit_module()

    record = audit_record(
        module,
        clean_display(primary_insight="A sci-fi heist from tmdb_keywords."),
    )

    assert "TECHNICAL_LEAK" in issue_codes(record)
    assert record["grade"] == "blocked"


def test_platform_viewer_label_is_critical():
    module = load_audit_module()
    display = clean_display()
    display["profile"]["identity"] = ["JioHotstar viewers"]

    record = audit_record(module, display)

    assert "PLATFORM_IDENTITY_LEAK" in issue_codes(record)
    assert record["grade"] == "blocked"


def test_feel_used_as_theme_is_high():
    module = load_audit_module()
    display = clean_display()
    display["profile"]["themes"] = ["Eerie"]

    record = audit_record(module, display)

    assert "FEEL_USED_AS_THEME" in issue_codes(record)
    assert record["issue_counts"]["high"] == 1
    assert record["display_ready"] is False


def test_generic_identity_is_high():
    module = load_audit_module()
    display = clean_display()
    display["profile"]["identity"] = ["Complex story"]

    record = audit_record(module, display)

    assert "GENERIC_DOMINANT_IDENTITY" in issue_codes(record)
    assert record["display_ready"] is False


def test_duplicate_best_for_is_medium():
    module = load_audit_module()
    display = clean_display()
    display["profile"]["best_for"] = ["Prison drama", "Prison dramas"]

    record = audit_record(module, display)

    assert "DUPLICATE_BEST_FOR" in issue_codes(record)
    assert record["issue_counts"]["medium"] == 1
    assert record["display_quality_score"] == 90


def test_best_for_case_allows_known_proper_phrases():
    module = load_audit_module()

    for label in [
        "World War II dramas",
        "World War I dramas",
        "Sci-fi stories",
        "Post-apocalyptic worlds",
        "AI thrillers",
        "TV dramas",
        "PG-13 action films",
        "TV-MA dramas",
    ]:
        display = clean_display()
        display["profile"]["best_for"] = [label]

        record = audit_record(module, display)

        assert not module.has_case_inconsistency(label)
        assert "BEST_FOR_CASE_INCONSISTENCY" not in issue_codes(record)


def test_best_for_case_still_flags_awkward_title_case_labels():
    module = load_audit_module()

    for label in [
        "Post-apocalyptic World",
        "Historical Crime Drama",
        "Dark Tone Stories",
        "Crime Mystery Stories",
    ]:
        display = clean_display()
        display["profile"]["best_for"] = [label]

        record = audit_record(module, display)

        assert module.has_case_inconsistency(label)
        assert "BEST_FOR_CASE_INCONSISTENCY" in issue_codes(record)


def test_conflicting_feel_labels_are_medium():
    module = load_audit_module()
    display = clean_display()
    display["profile"]["feel"] = ["Warm", "Cynical"]

    record = audit_record(module, display)

    assert "CONFLICTING_FEEL_LABELS" in issue_codes(record)
    assert record["issue_counts"]["medium"] == 1


def test_score_grade_and_readiness_calculation():
    module = load_audit_module()
    issues = [
        module.issue("GENERIC_THEME", "medium", "profile.themes", "Story", "", ""),
        module.issue("NO_PACE", "low", "profile.pace", "", "", ""),
    ]

    score = module.calculate_score(issues)

    assert score == 86
    assert module.grade_for_score(score, issues) == "good"
    assert module.display_ready_for(score, issues) is True


def test_csv_row_uses_pipe_separated_multi_value_cells():
    module = load_audit_module()
    record = audit_record(module, clean_display())

    row = module.csv_row(record)

    assert row["identity"] == "Sci-fi heist"
    assert row["themes"] == "Memory and identity"
    assert row["feel"] == "Surreal | Thoughtful"
    assert row["supporting_facts"] == (
        "Audience: 86/100 from 2 scoring sources | Access: Streaming in India"
    )


def test_summary_aggregation_counts_grades_and_issues():
    module = load_audit_module()
    clean = audit_record(module, clean_display())
    broken = audit_record(module, None)

    summary = module.build_summary([clean, broken], "2026-07-06T00:00:00+00:00")

    assert summary["titles_seen"] == 2
    assert summary["display_ready_count"] == 1
    assert summary["review_required_count"] == 1
    assert summary["grade_counts"]["excellent"] == 1
    assert summary["grade_counts"]["blocked"] == 1
    assert summary["issue_counts_by_code"]["MISSING_DISPLAY"] == 1
    assert summary["top_issue_examples"]["MISSING_DISPLAY"][0]["title"] == "Inception"


def test_fail_on_critical_and_fail_under_score_behavior():
    module = load_audit_module()
    clean = audit_record(module, clean_display())
    broken = audit_record(module, None)
    summary = module.build_summary([clean, broken], "2026-07-06T00:00:00+00:00")

    assert module.should_fail_run(
        summary,
        [clean, broken],
        argparse.Namespace(fail_on_critical=True, fail_under_score=None),
    )
    assert module.should_fail_run(
        summary,
        [clean, broken],
        argparse.Namespace(fail_on_critical=False, fail_under_score=80),
    )
    assert not module.should_fail_run(
        module.build_summary([clean], "2026-07-06T00:00:00+00:00"),
        [clean],
        argparse.Namespace(fail_on_critical=True, fail_under_score=80),
    )


def test_primary_insight_audit_flags_raw_label_grammar():
    module = load_audit_module()
    display = clean_display(
        primary_insight="A workplace comedy built around light."
    )
    display["profile"]["identity"] = ["Workplace comedy"]
    display["profile"]["themes"] = []

    record = audit_record(module, display)

    assert "PRIMARY_INSIGHT_RAW_LABEL_GRAMMAR" in issue_codes(record)


def test_primary_insight_audit_flags_duplicate_concept_family():
    module = load_audit_module()
    display = clean_display(
        primary_insight="A romantic drama built around romance."
    )
    display["profile"]["identity"] = ["Romantic drama"]
    display["profile"]["themes"] = ["Romantic connection"]

    record = audit_record(module, display)

    assert "PRIMARY_INSIGHT_DUPLICATE_CONCEPTS" in issue_codes(record)


def test_primary_insight_audit_flags_repeated_word_and_punctuation():
    module = load_audit_module()
    display = clean_display(
        primary_insight=(
            "A survival drama about survival pressure, and resilience."
        )
    )
    display["profile"]["identity"] = ["Survival drama"]
    display["profile"]["themes"] = ["Human resilience"]

    record = audit_record(module, display)
    codes = issue_codes(record)

    assert "PRIMARY_INSIGHT_REPEATED_WORD" in codes
    assert "PRIMARY_INSIGHT_PUNCTUATION" in codes


def test_primary_insight_audit_flags_unsupported_and_fallback_only_plan():
    module = load_audit_module()
    display = clean_display(primary_insight="A specific historical drama.")
    display["_insight_plan"] = {
        "primary_identity": {
            "text": "Historical drama",
            "source": "display_profile",
        },
        "primary_differentiator": None,
        "validation_errors": ["unsupported_component"],
        "template_family": "identity_about",
    }

    record = audit_record(module, display)
    codes = issue_codes(record)

    assert "PRIMARY_INSIGHT_UNSUPPORTED_COMPONENT" in codes
    assert "PRIMARY_INSIGHT_FALLBACK_ONLY" in codes


def test_short_specific_identity_is_not_padded_or_flagged():
    module = load_audit_module()
    display = clean_display(primary_insight="A workplace comedy.")
    display["profile"]["identity"] = ["Workplace comedy"]
    display["_insight_plan"] = {
        "primary_identity": {
            "text": "Workplace comedy",
            "source": "source_signal:audience_expectation:workplace comedy",
            "supported": True,
        },
        "primary_differentiator": None,
        "validation_errors": [],
        "template_family": "identity_about",
    }

    assert "PRIMARY_INSIGHT_TOO_SHORT" not in issue_codes(
        audit_record(module, display)
    )


def test_short_generic_identity_remains_reviewable():
    module = load_audit_module()
    display = clean_display(primary_insight="A documentary.")
    display["profile"]["identity"] = ["Documentary"]
    display["_insight_plan"] = {
        "primary_identity": {
            "text": "Documentary",
            "source": "genre_context",
            "supported": True,
        },
        "primary_differentiator": None,
        "validation_errors": [],
        "template_family": "identity_about",
    }

    assert "PRIMARY_INSIGHT_TOO_SHORT" in issue_codes(
        audit_record(module, display)
    )


def test_primary_insight_audit_flags_spoiler_risk():
    module = load_audit_module()

    record = audit_record(
        module,
        clean_display(
            primary_insight=(
                "A mystery shaped by the surprise ending and its aftermath."
            )
        ),
    )

    assert "PRIMARY_INSIGHT_SPOILER_RISK" in issue_codes(record)


def test_catalog_audit_flags_dominant_template_family():
    module = load_audit_module()
    records = [
        audit_record(
            module,
            {
                **clean_display(
                    primary_insight=f"A crime thriller about case pressure {index}."
                ),
                "_insight_plan": {
                    "template_family": "identity_about",
                    "primary_identity": {
                        "text": "Crime thriller",
                        "source": "source_signal:audience_expectation",
                    },
                    "primary_differentiator": {
                        "text": "case pressure",
                        "source": "source_signal:topic_theme",
                    },
                    "validation_errors": [],
                },
            },
        )
        for index in range(10)
    ]

    updated = module.apply_template_overuse_issues(records)

    assert all(
        "PRIMARY_INSIGHT_TEMPLATE_OVERUSE" in issue_codes(record)
        for record in updated
    )


def test_small_catalog_does_not_report_template_overuse():
    module = load_audit_module()
    records = [
        audit_record(
            module,
            clean_display(primary_insight="A crime thriller about case pressure."),
        )
    ]

    updated = module.apply_template_overuse_issues(records)

    assert "PRIMARY_INSIGHT_TEMPLATE_OVERUSE" not in issue_codes(updated[0])


def test_semantic_identity_conflicts_require_source_review_without_blocking_safe_display():
    module = load_audit_module()
    display = clean_display(primary_insight="An animated superhero story.")
    display["_insight_plan"] = {
        "primary_identity": {
            "text": "Animated superhero story",
            "source": "source_signal:audience_expectation:superhero story",
            "supported": True,
            "trust_tier": 2,
        },
        "rejected_candidates": [
            {
                "candidate": "Romantic drama",
                "role": "primary_identity",
                "reason": "identity_metadata_conflict",
                "source": "source_signal:audience_expectation:romantic drama",
                "conflict_reason": "missing_central_romance_evidence",
            }
        ],
        "validation_errors": [],
    }

    record = audit_record(module, display)

    assert "SOURCE_SIGNAL_IDENTITY_METADATA_CONFLICT" in issue_codes(record)
    assert record["display_ready"] is True
    assert record["display_review_required"] is False
    assert record["source_signal_review_required"] is True
    assert record["review_required"] is True


def test_copy_semantic_audit_flags_new_grammar_classes():
    module = load_audit_module()
    cases = {
        "PRIMARY_INSIGHT_ADJECTIVE_STACK": "A fast-paced tense thriller.",
        "PRIMARY_INSIGHT_AWKWARD_PACING": "A thriller with gentle pacing momentum.",
        "PRIMARY_INSIGHT_CONJUNCTION_CHAIN": "A drama about ambition and rivalry and technology and society.",
        "PRIMARY_INSIGHT_RAW_TAXONOMY": "An adventure shaped by anime style.",
    }

    for expected_code, primary in cases.items():
        record = audit_record(module, clean_display(primary_insight=primary))
        assert expected_code in issue_codes(record)
        assert record["display_ready"] is False


def test_weak_and_incidental_identity_provenance_requires_review():
    module = load_audit_module()
    display = clean_display(primary_insight="A prison drama.")
    display["_insight_plan"] = {
        "primary_identity": {
            "text": "Prison drama",
            "source": "inferred_context",
            "supported": True,
            "trust_tier": 5,
        },
        "rejected_candidates": [],
        "validation_errors": [],
    }

    record = audit_record(module, display)

    assert "PRIMARY_IDENTITY_INCIDENTAL_CONTEXT" in issue_codes(record)
    assert record["display_ready"] is False


def test_documentary_with_governed_specific_context_is_display_ready_with_source_review():
    module = load_audit_module()
    display = clean_display(
        primary_insight="A tense documentary examining racial inequality."
    )
    display["profile"]["identity"] = ["Documentary"]
    display["profile"]["themes"] = ["Racial inequality"]
    display["_insight_plan"] = {
        "primary_identity": {
            "text": "Documentary",
            "source": "inferred_context",
            "supported": True,
            "trust_tier": 5,
        },
        "primary_differentiator": {
            "text": "racial inequality",
            "source": "overview_rule",
            "concept_family": "racial injustice",
            "supported": True,
        },
        "rejected_candidates": [
            {
                "candidate": label,
                "role": "primary_identity",
                "reason": "identity_metadata_conflict",
                "source": f"source_signal:audience_expectation:{label}",
                "conflict_reason": "documentary_rejects_fictional_identity",
            }
            for label in (
                "Crime drama",
                "Political thriller",
                "Prison drama",
            )
        ],
        "validation_errors": [],
    }

    record = audit_record(module, display)

    assert "PRIMARY_IDENTITY_INCIDENTAL_CONTEXT" not in issue_codes(record)
    assert "PRIMARY_INSIGHT_LOW_SPECIFICITY" not in issue_codes(record)
    assert "SOURCE_SIGNAL_IDENTITY_METADATA_CONFLICT" in issue_codes(record)
    assert record["display_ready"] is True
    assert record["source_signal_review_required"] is True


@pytest.mark.parametrize(
    ("state", "expects_issue"),
    [
        ("not_evaluated", True),
        ("selected", False),
        ("evaluated_rejected", False),
    ],
)
def test_curated_identity_audit_uses_explicit_evaluation_state(
    state,
    expects_issue,
):
    module = load_audit_module()
    display = clean_display(primary_insight="A tense crime thriller.")
    display["profile"]["identity"] = ["Crime thriller"]
    display["_insight_plan"] = {
        "primary_identity": {
            "text": "Crime thriller",
            "source": (
                "curated_override:audience_expectation:crime thriller"
                if state == "selected"
                else "source_signal:audience_expectation:crime thriller"
            ),
            "supported": True,
            "trust_tier": 2,
        },
        "curated_override_applied": True,
        "curated_identity_available": True,
        "curated_identity_evaluation": state,
        "rejected_candidates": [],
        "validation_errors": [],
    }

    record = audit_record(module, display)

    assert (
        "PRIMARY_IDENTITY_CURATED_OVERRIDE_IGNORED" in issue_codes(record)
    ) is expects_issue


def test_catalog_targets_are_consumed_in_bounded_batches():
    module = load_audit_module()

    class Result:
        def __init__(self):
            self.rows = [
                {
                    "id": index,
                    "title": f"Title {index}",
                    "content_type": "movie",
                    "year": 2024,
                }
                for index in range(1, 6)
            ]

        def mappings(self):
            return self

        def fetchmany(self, size):
            batch, self.rows = self.rows[:size], self.rows[size:]
            return batch

    class Connection:
        def execute(self, _query, _params):
            return Result()

    args = SimpleNamespace(
        content_id=None,
        content_type="all",
        limit=None,
        offset=0,
        batch_size=2,
    )

    batches = list(module.query_catalog_target_batches(Connection(), args))

    assert [len(batch) for batch in batches] == [2, 2, 1]
    assert [row["id"] for batch in batches for row in batch] == [1, 2, 3, 4, 5]
