import argparse
import importlib.util
import sys
from pathlib import Path


def load_audit_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "analytics" / "scripts" / "audit_decision_display_quality.py"
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
