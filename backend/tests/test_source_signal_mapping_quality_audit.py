import argparse
import importlib.util
import sys
from collections import Counter
from pathlib import Path


def load_audit_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = (
        repo_root / "analytics" / "scripts" / "audits" / "audit_source_signal_mapping_quality.py"
    )
    spec = importlib.util.spec_from_file_location(
        "audit_source_signal_mapping_quality",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_source_signal_mapping_quality"] = module
    spec.loader.exec_module(module)
    return module


def signal(dimension, label, value=None, source_names=None, confidence="medium"):
    return {
        "dimension": dimension,
        "value": value or label.lower().replace(" ", "_"),
        "label": label,
        "confidence": confidence,
        "source_names": source_names or ["tmdb_keywords"],
    }


def clean_content():
    return {
        "id": 6,
        "title": "Inception",
        "content_type": "movie",
        "year": 2010,
    }


def clean_signals():
    return [
        signal("audience_expectation", "Sci-fi heist"),
        signal("topic_theme", "Memory and identity"),
        signal("mood", "Surreal"),
        signal("tone", "Thoughtful"),
        signal("pacing", "Plot-driven"),
        signal("content_caution_proxy", "Dense structure"),
    ]


def clean_guidance(**overrides):
    guidance = {
        "signal_sources": ["tmdb_keywords"],
        "curated_override_applied": False,
        "metadata_fallback_applied": False,
    }
    guidance.update(overrides)
    return guidance


def clean_display():
    return {
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
        ],
    }


def audit_clean(module, **overrides):
    kwargs = {
        "genres": ["Action", "Adventure", "Sci-Fi", "Thriller"],
        "raw_keywords": ["heist", "dream", "identity"],
        "signals": clean_signals(),
        "guidance": clean_guidance(),
        "display": clean_display(),
        "mapped_keywords": {"heist", "dream", "identity"},
    }
    kwargs.update(overrides)
    return module.audit_mapping_record(clean_content(), **kwargs)


def issue_codes(record):
    return {issue["code"] for issue in record["issues"]}


def test_clean_rich_signal_record_scores_high():
    module = load_audit_module()

    record = audit_clean(
        module,
        supporting_data={
            "unified_score": 86,
            "source_count": 2,
            "scoring_source_count": 2,
            "availability_count": 3,
        },
    )

    assert record["mapping_quality_score"] == 100
    assert record["grade"] == "excellent"
    assert record["mapping_ready"] is True
    assert record["review_required"] is False
    assert record["signal_dimensions_present"] == [
        "audience_expectation",
        "topic_theme",
        "mood",
        "tone",
        "pacing",
        "content_caution_proxy",
    ]
    assert record["supporting_data"] == {
        "unified_score": 86,
        "source_count": 2,
        "scoring_source_count": 2,
        "availability_count": 3,
    }


def test_missing_source_signals_is_critical():
    module = load_audit_module()

    record = audit_clean(module, signals=[], guidance=None)

    assert "MISSING_SOURCE_SIGNALS" in issue_codes(record)
    assert "MISSING_WATCH_GUIDANCE" in issue_codes(record)
    assert record["issue_counts"]["critical"] == 2
    assert record["grade"] == "blocked"
    assert record["mapping_ready"] is False


def test_missing_pacing_is_not_critical():
    module = load_audit_module()
    signals = [
        item
        for item in clean_signals()
        if item["dimension"] != "pacing"
    ]

    record = audit_clean(module, signals=signals)

    assert "MISSING_PACING_SIGNAL" in issue_codes(record)
    assert record["issue_counts"]["critical"] == 0
    assert record["mapping_quality_score"] >= 80


def test_missing_content_caution_proxy_alone_does_not_block_readiness():
    module = load_audit_module()
    signals = [
        item
        for item in clean_signals()
        if item["dimension"] != "content_caution_proxy"
    ]

    record = audit_clean(module, signals=signals)

    assert "NO_CONTENT_CAUTION_PROXY" not in issue_codes(record)
    assert "CONTENT_CAUTION_MISSING_FOR_INTENSE_TITLE" not in issue_codes(record)
    assert record["future_dimension_gaps"] == ["content_caution_proxy"]
    assert record["mapping_quality_score"] == 100
    assert record["mapping_ready"] is True


def test_intense_horror_title_missing_caution_gets_warning():
    module = load_audit_module()
    signals = [
        signal("audience_expectation", "Psychological horror"),
        signal("topic_theme", "Serial-killer investigation"),
        signal("mood", "Tense"),
        signal("tone", "Bleak"),
        signal("pacing", "Slow-burn"),
    ]

    record = audit_clean(
        module,
        genres=["Horror", "Thriller"],
        raw_keywords=["serial killer", "disturbing", "horror"],
        signals=signals,
        mapped_keywords={"serial killer", "disturbing", "horror"},
    )

    assert "CONTENT_CAUTION_MISSING_FOR_INTENSE_TITLE" in issue_codes(record)
    assert "NO_CONTENT_CAUTION_PROXY" not in issue_codes(record)
    assert record["future_dimension_gaps"] == ["content_caution_proxy"]
    assert record["issue_counts"]["critical"] == 0


def test_all_generic_labels_are_high_issue():
    module = load_audit_module()
    generic_signals = [
        signal("audience_expectation", "Story"),
        signal("topic_theme", "Drama"),
    ]

    record = audit_clean(module, signals=generic_signals)

    assert "ALL_SIGNALS_GENERIC" in issue_codes(record)
    assert record["issue_counts"]["high"] >= 1
    assert record["mapping_ready"] is False


def test_missing_audience_expectation_remains_high_severity():
    module = load_audit_module()
    signals = [
        item
        for item in clean_signals()
        if item["dimension"] != "audience_expectation"
    ]

    record = audit_clean(module, signals=signals)

    assert "EMPTY_AUDIENCE_EXPECTATION" in issue_codes(record)
    assert record["issue_counts"]["high"] >= 1
    assert record["mapping_ready"] is False


def test_missing_topic_theme_remains_high_severity():
    module = load_audit_module()
    signals = [
        item
        for item in clean_signals()
        if item["dimension"] != "topic_theme"
    ]

    record = audit_clean(module, signals=signals)

    assert "EMPTY_TOPIC_THEME" in issue_codes(record)
    assert record["issue_counts"]["high"] >= 1
    assert record["mapping_ready"] is False


def test_generic_genre_only_title_is_diagnostic_not_blocking_issue():
    module = load_audit_module()
    signals = [
        signal("audience_expectation", "Mission thriller"),
        signal("topic_theme", "Rescue mission"),
        signal("mood", "Tense"),
        signal("tone", "Serious"),
        signal("pacing", "Fast-paced"),
        signal("content_caution_proxy", "High intensity"),
    ]

    record = audit_clean(
        module,
        genres=["Action", "Drama", "Thriller"],
        raw_keywords=["mission", "chase", "fight"],
        signals=signals,
        mapped_keywords={"mission", "chase", "fight"},
    )

    assert record["genre_quality"]["is_too_generic"] is True
    assert "GENERIC_GENRE_ONLY" not in issue_codes(record)
    assert record["mapping_ready"] is True
    assert record["suggested_next_step"] == "ready_for_catalog_expansion"


def test_missing_signal_dimensions_prefer_mapping_config_review():
    module = load_audit_module()
    signals = [
        signal("audience_expectation", "Mission thriller"),
        signal("topic_theme", "Rescue mission"),
        signal("mood", "Tense"),
    ]

    record = audit_clean(
        module,
        genres=["Action", "Drama", "Thriller"],
        raw_keywords=["mission", "chase", "fight"],
        signals=signals,
        mapped_keywords={"mission", "chase", "fight"},
    )

    assert "MISSING_PACING_SIGNAL" in issue_codes(record)
    assert record["suggested_next_step"] == "mapping_config_review"


def test_no_subgenre_candidate_is_genre_diagnostic_not_issue():
    module = load_audit_module()

    record = audit_clean(
        module,
        genres=["Mystery"],
        raw_keywords=["dream", "identity"],
        mapped_keywords={"dream", "identity"},
    )

    assert "NO_SUBGENRE_CANDIDATE" not in issue_codes(record)
    assert record["genre_quality"]["no_subgenre_candidate"] is True
    assert record["mapping_ready"] is True


def test_subgenre_opportunity_detection():
    module = load_audit_module()

    assert "Sci-fi heist" in module.detect_subgenre_candidates(
        ["Sci-Fi"],
        ["heist"],
        [],
    )
    assert "World War II drama" in module.detect_subgenre_candidates(
        ["History", "War"],
        ["World War II"],
        [],
    )
    assert "Post-apocalyptic survival drama" in module.detect_subgenre_candidates(
        ["Drama"],
        ["post-apocalyptic", "survival"],
        [],
    )


def test_concrete_subgenre_candidate_still_creates_actionable_issue():
    module = load_audit_module()
    signals = [
        signal("audience_expectation", "Heist story"),
        signal("topic_theme", "Dream theft"),
        signal("mood", "Surreal"),
        signal("tone", "Thoughtful"),
        signal("pacing", "Plot-driven"),
        signal("content_caution_proxy", "Dense structure"),
    ]
    display = clean_display()
    display["profile"]["identity"] = ["Heist story"]
    display["primary_insight"] = "A surreal heist story built around dream theft."

    record = audit_clean(
        module,
        genres=["Sci-Fi"],
        raw_keywords=["heist", "dream"],
        signals=signals,
        display=display,
        mapped_keywords={"heist", "dream"},
    )

    assert "Sci-fi heist" in record["genre_quality"]["subgenre_candidates"]
    assert "SUBGENRE_MISSING" in issue_codes(record)


def test_war_drama_not_suggested_for_unrelated_contexts():
    module = load_audit_module()

    unrelated_contexts = [
        (["Comedy", "Fantasy"], ["award show", "plastic world"]),
        (["Animation", "Family"], ["music", "memory", "family"]),
        (["Action", "Adventure"], ["superhero", "irreverent", "multiverse"]),
    ]

    for genres, keywords in unrelated_contexts:
        candidates = module.detect_subgenre_candidates(genres, keywords, [])
        assert "War drama" not in candidates
        assert "World War II drama" not in candidates


def test_war_drama_suggested_for_explicit_war_context():
    module = load_audit_module()

    assert "War drama" in module.detect_subgenre_candidates(
        ["Drama", "War"],
        ["duty"],
        [],
    )
    assert "War drama" in module.detect_subgenre_candidates(
        ["Drama"],
        ["battlefield", "soldier"],
        [],
    )


def test_kitchen_workplace_requires_culinary_workplace_evidence():
    module = load_audit_module()

    office_ai_signals = [
        signal("topic_theme", "Workplace setting"),
        signal("audience_expectation", "AI thriller"),
    ]
    kitchen_signals = [
        signal("topic_theme", "Kitchen workplace"),
        signal("audience_expectation", "Kitchen workplace drama"),
    ]

    assert "Kitchen workplace drama" not in module.detect_subgenre_candidates(
        ["Drama", "Sci-Fi"],
        ["office", "artificial intelligence"],
        office_ai_signals,
    )
    assert "Kitchen workplace drama" in module.detect_subgenre_candidates(
        ["Drama"],
        ["restaurant", "chef"],
        kitchen_signals,
    )


def test_space_survival_requires_space_and_survival_or_mission_evidence():
    module = load_audit_module()

    assert "Space survival sci-fi" not in module.detect_subgenre_candidates(
        ["Drama", "Fantasy", "Sci-Fi"],
        ["time travel", "antihero"],
        [signal("audience_expectation", "Reality-bending sci-fi")],
    )
    assert "Space survival sci-fi" not in module.detect_subgenre_candidates(
        ["Drama", "Sci-Fi"],
        ["survival"],
        [signal("topic_theme", "Survival")],
    )
    assert "Space survival sci-fi" in module.detect_subgenre_candidates(
        ["Drama", "Sci-Fi"],
        ["space", "survival mission"],
        [signal("topic_theme", "Space sci-fi")],
    )


def test_serial_killer_investigation_not_suggested_for_light_murder_comedy():
    module = load_audit_module()

    assert "Serial-killer investigation" not in module.detect_subgenre_candidates(
        ["Comedy", "Crime", "Mystery"],
        ["murder", "podcast", "evidence"],
        [signal("audience_expectation", "Murder mystery")],
    )
    assert "Serial-killer investigation" in module.detect_subgenre_candidates(
        ["Crime", "Mystery", "Thriller"],
        ["serial killer", "detective"],
        [signal("topic_theme", "Investigation")],
    )


def test_unmapped_keyword_opportunity_aggregation():
    module = load_audit_module()
    records = [
        {
            "title": "A",
            "unmapped_keywords": ["slow burn", "survival"],
        },
        {
            "title": "B",
            "unmapped_keywords": ["slow burn", "satire"],
        },
    ]

    opportunities = module.top_unmapped_keyword_opportunities(records)

    slow_burn = next(item for item in opportunities if item["keyword"] == "slow burn")
    assert slow_burn["count"] == 2
    assert slow_burn["suggested_dimension"] == "pacing"
    assert slow_burn["suggested_label"] == "Slow-burn"


def test_summary_aggregation_counts_dimensions_and_issues():
    module = load_audit_module()
    clean = audit_clean(module)
    missing = audit_clean(module, signals=[], guidance=None)

    summary = module.build_summary([clean, missing], "2026-07-08T00:00:00+00:00")

    assert summary["titles_seen"] == 2
    assert summary["titles_with_source_signals"] == 1
    assert summary["mapping_ready_count"] == 1
    assert summary["review_required_count"] == 1
    assert summary["grade_counts"]["excellent"] == 1
    assert summary["grade_counts"]["blocked"] == 1
    assert summary["signals_by_dimension"]["audience_expectation"] == 1
    assert summary["issue_counts_by_code"]["MISSING_SOURCE_SIGNALS"] == 1


def test_summary_separates_future_diagnostics_from_normal_issues():
    module = load_audit_module()
    signals = [
        item
        for item in clean_signals()
        if item["dimension"] != "content_caution_proxy"
    ]
    record = audit_clean(module, signals=signals)

    summary = module.build_summary([record], "2026-07-08T00:00:00+00:00")

    assert "NO_CONTENT_CAUTION_PROXY" not in summary["issue_counts_by_code"]
    assert summary["future_dimension_gap_counts"] == {"content_caution_proxy": 1}


def test_csv_row_uses_pipe_separated_values():
    module = load_audit_module()
    record = audit_clean(module)

    row = module.csv_row(record)

    assert row["genres"] == "Action | Adventure | Sci-Fi | Thriller"
    assert row["audience_expectation"] == "Sci-fi heist"
    assert row["topic_theme"] == "Memory and identity"
    assert row["uses_curated_override"] is False


def test_backend_display_fallback_alone_does_not_lower_readiness():
    module = load_audit_module()
    display = clean_display()
    display["profile"]["themes"] = ["Memory and identity", "Dream logic"]

    record = audit_clean(module, display=display)

    assert record["fallback_dependency"]["uses_backend_display_fallback"] is True
    assert "BACKEND_DISPLAY_FALLBACK_COMPENSATING" not in issue_codes(record)
    assert record["mapping_ready"] is True


def test_backend_display_fallback_with_sparse_mapping_is_flagged():
    module = load_audit_module()
    sparse_signals = [
        signal("audience_expectation", "Heist story"),
        signal("mood", "Surreal"),
    ]

    record = audit_clean(module, signals=sparse_signals)

    assert record["fallback_dependency"]["uses_backend_display_fallback"] is True
    assert "BACKEND_DISPLAY_FALLBACK_COMPENSATING" in issue_codes(record)
    assert record["mapping_ready"] is False


def test_low_mapping_density_reduces_quality():
    module = load_audit_module()
    signals = [
        signal("audience_expectation", "Crime thriller"),
        signal("topic_theme", "Investigation"),
        signal("mood", "Tense"),
        signal("tone", "Suspenseful"),
        signal("pacing", "Slow-burn"),
    ]

    record = audit_clean(
        module,
        raw_keywords=[
            "investigation",
            "detective",
            "procedural",
            "murder",
            "city",
            "evidence",
            "case",
            "secret",
            "police",
            "night",
            "crime",
            "clue",
            "witness",
            "suspect",
            "cover up",
            "trial",
            "law",
            "pressure",
            "family",
            "past",
            "truth",
        ],
        signals=signals,
        mapped_keywords={"investigation"},
    )

    assert "LOW_MAPPING_DENSITY" in issue_codes(record)
    assert record["mapping_quality_score"] < 100


def test_common_quality_labels_are_not_weak():
    module = load_audit_module()

    for label in ["Tense", "Suspenseful", "Action-heavy", "Emotional", "Darkly funny", "Fast-paced", "Slow-burn"]:
        assert module.is_weak_label(label) is False


def test_weak_labels_are_still_flagged():
    module = load_audit_module()

    for label in ["Heavier watch", "Complex story", "Drama"]:
        assert module.is_weak_label(label) is True


def test_fail_on_critical_and_fail_under_score_behavior():
    module = load_audit_module()
    clean = audit_clean(module)
    broken = audit_clean(module, signals=[], guidance=None)
    summary = module.build_summary([clean, broken], "2026-07-08T00:00:00+00:00")

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
        module.build_summary([clean], "2026-07-08T00:00:00+00:00"),
        [clean],
        argparse.Namespace(fail_on_critical=True, fail_under_score=80),
    )


def test_overused_weak_labels_are_flagged_with_global_counts():
    module = load_audit_module()
    signals = [
        signal("audience_expectation", "Drama"),
        signal("topic_theme", "Story"),
        signal("mood", "Tense"),
        signal("tone", "Serious"),
        signal("pacing", "Fast-paced"),
        signal("content_caution_proxy", "High intensity"),
    ]

    record = audit_clean(
        module,
        signals=signals,
        global_label_counts=Counter({"Drama": 35, "Story": 35}),
    )

    assert "OVERUSED_LABEL" in issue_codes(record)
    assert "Drama" in record["overused_labels"]


def test_common_overused_quality_labels_are_not_flagged():
    module = load_audit_module()
    signals = [
        signal("audience_expectation", "Crime thriller"),
        signal("topic_theme", "Investigation"),
        signal("mood", "Tense"),
        signal("tone", "Suspenseful"),
        signal("pacing", "Action-heavy"),
        signal("content_caution_proxy", "High intensity"),
    ]

    record = audit_clean(
        module,
        signals=signals,
        global_label_counts=Counter({"Tense": 80, "Suspenseful": 60, "Action-heavy": 40}),
    )

    assert "OVERUSED_LABEL" not in issue_codes(record)
    assert record["overused_labels"] == []
