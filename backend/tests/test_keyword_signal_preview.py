import importlib.util
import json
import sys
from pathlib import Path


def load_keyword_signal_preview_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "analytics" / "scripts" / "build_keyword_signal_preview.py"
    spec = importlib.util.spec_from_file_location(
        "build_keyword_signal_preview",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_keyword_signal_preview"] = module
    spec.loader.exec_module(module)
    return module


def load_mapping(module):
    repo_root = Path(__file__).resolve().parents[2]
    return module.load_mapping_config(
        repo_root / "analytics" / "config" / "source_signal_keyword_mapping.json"
    )


def load_overrides(module):
    repo_root = Path(__file__).resolve().parents[2]
    return module.load_override_config(
        repo_root / "analytics" / "config" / "source_signal_title_overrides.json"
    )


def content_fixture(module, keywords, title="Example", content_type="movie", genres=None):
    return module.KeywordContent(
        content_id=133,
        title=title,
        content_type=content_type,
        keywords=keywords,
        genres=genres or [],
    )


def test_load_keyword_signal_mapping_config():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    assert mapping["mapping_version"] == "2026-07-09-v2"
    assert "serial killer" in mapping["keyword_mappings"]
    assert "psychological thriller" in mapping["keyword_mappings"]
    assert "dark fantasy" in mapping["keyword_mappings"]
    assert "nuclear catastrophe" in mapping["keyword_mappings"]
    assert "aftercreditsstinger" in mapping["excluded_keywords"]
    assert "plot twist" in mapping["spoiler_unsafe_keywords"]
    assert "violence" in mapping["spoiler_unsafe_keywords"]


def signal_values_for_dimension(item, dimension):
    return {
        signal["value"]
        for signal in item["signals"].get(dimension, [])
    }


def test_mapping_config_dimensions_match_signal_dimensions():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    valid_dimensions = set(mapping["dimensions"])

    for keyword, entry in mapping["keyword_mappings"].items():
        signals = entry.get("signals") or []
        assert signals, f"{keyword} has no mapped signals"
        actual_dimensions = {signal["dimension"] for signal in signals}
        assert set(entry["dimensions"]) == actual_dimensions
        assert actual_dimensions <= valid_dimensions


def test_mapping_config_avoids_public_technical_or_viewer_labels():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    blocked_fragments = {
        "tmdb",
        "keyword",
        "source_names",
        "mapping_version",
        "provider",
        "viewers",
    }

    for entry in mapping["keyword_mappings"].values():
        for signal in entry.get("signals", []):
            label = signal["display_label"].lower()
            assert not any(fragment in label for fragment in blocked_fragments)


def test_title_override_config_loads_safely():
    module = load_keyword_signal_preview_module()
    overrides = load_overrides(module)

    assert overrides["override_version"] == "2026-07-02-v3.1"
    assert any(
        override["title"] == "Breaking Bad"
        for override in overrides["overrides"]
    )


def test_partial_preview_runs_require_explicit_output_paths():
    module = load_keyword_signal_preview_module()

    args = module.parse_args(["--limit", "20"])
    assert module.output_safety_error(args) == module.PARTIAL_OUTPUT_ERROR
    assert module.main(["--limit", "20"]) == 1

    explicit_args = module.parse_args(
        [
            "--limit",
            "20",
            "--output",
            "analytics/processed/source_signals/debug/sample.json",
            "--report-output",
            "analytics/processed/source_signals/debug/sample_report.json",
        ]
    )
    assert module.output_safety_error(explicit_args) is None


def test_default_full_preview_can_use_default_output_paths():
    module = load_keyword_signal_preview_module()

    args = module.parse_args([])

    assert module.output_safety_error(args) is None


def test_keyword_signal_normalization():
    module = load_keyword_signal_preview_module()

    assert module.normalize_keyword_name(" Sci-Fi/Fantasy ") == "sci fi fantasy"
    assert module.normalize_keyword_name("Dark-Comedy") == "dark comedy"
    assert module.normalize_keyword_name("murder   mystery") == "murder mystery"


def test_excluded_keywords_do_not_produce_signals():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["aftercreditsstinger", "sequel"]),
        mapping,
        include_debug=False,
    )

    assert not any(item["signals"].values())
    assert item["keyword_counts"]["excluded_keywords"] == 2
    assert "debug" not in item


def test_spoiler_unsafe_keywords_do_not_produce_user_facing_output():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["plot twist", "secret identity"]),
        mapping,
        include_debug=False,
    )
    rendered = json.dumps(item).lower()

    assert not any(item["signals"].values())
    assert item["keyword_counts"]["spoiler_unsafe_keywords"] == 2
    assert "plot twist" not in rendered
    assert "secret identity" not in rendered


def test_mapped_keywords_produce_expected_dimensions():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["serial killer"]),
        mapping,
        include_debug=False,
    )

    assert item["signals"]["audience_expectation"][0]["value"] == (
        "serial-killer investigation"
    )
    assert item["signals"]["intensity"][0]["value"] == "high"
    assert item["signals"]["tone"][0]["value"] == "dark"


def test_duplicate_mapped_signals_are_deduped():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["murder mystery", "suspenseful"]),
        mapping,
        include_debug=True,
    )

    suspense_signals = [
        signal
        for signal in item["signals"]["mood"]
        if signal["value"] == "suspenseful"
    ]
    assert len(suspense_signals) == 1
    assert suspense_signals[0]["confidence"] in {"medium", "high"}
    assert sorted(suspense_signals[0]["evidence_keywords"]) == [
        "murder mystery",
        "suspenseful",
    ]


def test_top_chips_are_limited():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            [
                "serial killer",
                "suspenseful",
                "detective",
                "murder mystery",
                "revenge",
                "survival",
                "space",
            ],
        ),
        mapping,
        include_debug=False,
    )

    assert 2 <= len(item["watch_guidance"]["chips"]) <= 5


def test_watch_guidance_is_product_friendly():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["survival", "suspenseful"]),
        mapping,
        include_debug=False,
    )
    guidance_text = json.dumps(item["watch_guidance"]).lower()

    assert item["watch_guidance"]["watch_feel"].endswith(".")
    assert "keyword" not in guidance_text
    assert "tmdb" not in guidance_text
    assert "confidence" not in guidance_text
    assert "content_caution_proxy" not in guidance_text
    assert "clear watch feel" not in guidance_text
    assert "clear watch profile" not in guidance_text


def test_psychological_thriller_generates_productized_guidance():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["psychological thriller"]),
        mapping,
        include_debug=False,
    )
    watch_feel = item["watch_guidance"]["watch_feel"].lower()

    assert item["signals"]["audience_expectation"][0]["value"] == (
        "psychological thriller"
    )
    assert item["signals"]["mood"][0]["value"] == "suspenseful"
    assert item["signals"]["tone"][0]["value"] == "tense"
    assert item["signals"]["intensity"][0]["value"] == "high"
    assert "psychological thriller" in watch_feel
    assert "high-stakes" in watch_feel


def test_dark_fantasy_power_struggle_guidance_is_natural():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["dark fantasy", "power struggle"]),
        mapping,
        include_debug=False,
    )
    guidance_text = json.dumps(item["watch_guidance"]).lower()

    assert "political dark fantasy" in guidance_text
    assert "power struggles" in guidance_text
    assert "clear watch feel" not in guidance_text
    assert "clear watch profile" not in guidance_text


def test_nuclear_catastrophe_generates_disaster_guidance():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["nuclear catastrophe"]),
        mapping,
        include_debug=False,
    )
    watch_feel = item["watch_guidance"]["watch_feel"].lower()

    assert item["signals"]["topic_theme"][0]["value"] == "nuclear disaster"
    assert "disaster" in watch_feel
    assert "serious" in watch_feel


def test_organized_crime_generates_gritty_crime_guidance():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["organized crime"]),
        mapping,
        include_debug=False,
    )
    guidance_text = json.dumps(item["watch_guidance"]).lower()

    assert "organized-crime story" in guidance_text
    assert "gritty" in guidance_text


def test_slow_burn_keywords_produce_pacing_signals():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["slow burn", "meditative"]),
        mapping,
        include_debug=False,
    )

    assert "slow-burn" in signal_values_for_dimension(item, "pacing")
    assert {
        "contemplative",
    } & (
        signal_values_for_dimension(item, "tone")
        | signal_values_for_dimension(item, "mood")
    )


def test_tense_and_suspense_keywords_produce_mood_signals():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["tense", "suspense"]),
        mapping,
        include_debug=False,
    )

    assert "tense" in signal_values_for_dimension(item, "mood")
    assert "suspenseful" in signal_values_for_dimension(item, "mood")
    assert "tense" in signal_values_for_dimension(item, "tone")


def test_survival_keywords_add_theme_and_expectation():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["stranded", "survival", "escape"]),
        mapping,
        include_debug=False,
    )

    assert {
        "survival",
        "survival story",
        "escape",
    } & signal_values_for_dimension(item, "topic_theme")
    assert "survival drama" in signal_values_for_dimension(item, "audience_expectation")
    assert "plot-driven" in signal_values_for_dimension(item, "pacing")


def test_absurd_and_dark_comedy_keywords_produce_tone_signals():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["absurd", "dark comedy"]),
        mapping,
        include_debug=False,
    )

    assert "absurdist" in signal_values_for_dimension(item, "tone")
    assert "darkly funny" in signal_values_for_dimension(item, "tone")
    assert "offbeat comedy" in signal_values_for_dimension(item, "audience_expectation")


def test_war_keywords_add_human_cost_and_duty_themes():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["war", "soldier", "battle"]),
        mapping,
        include_debug=False,
    )

    themes = signal_values_for_dimension(item, "topic_theme")
    assert {"war", "human cost", "duty"} & themes
    assert "war drama" in signal_values_for_dimension(item, "audience_expectation")
    assert "serious" in signal_values_for_dimension(item, "tone")


def test_post_apocalyptic_survival_keywords_add_subgenre_signal():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["post-apocalyptic", "survival"]),
        mapping,
        include_debug=False,
    )

    assert "post-apocalyptic world" in signal_values_for_dimension(item, "topic_theme")
    assert "post-apocalyptic survival drama" in signal_values_for_dimension(
        item,
        "audience_expectation",
    )
    assert "survival drama" in signal_values_for_dimension(item, "audience_expectation")


def test_space_survival_keywords_add_space_survival_signals():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["space", "stranded", "spacecraft"]),
        mapping,
        include_debug=False,
    )

    assert "space sci-fi" in signal_values_for_dimension(item, "topic_theme")
    assert {
        "space sci-fi",
        "space survival sci-fi",
        "survival drama",
    } & signal_values_for_dimension(item, "audience_expectation")
    assert "tense" in signal_values_for_dimension(item, "mood")


def test_family_emotional_keywords_produce_character_drama_identity():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["family vacation", "father daughter relationship", "bittersweet"],
        ),
        mapping,
        include_debug=False,
    )

    assert "emotional character drama" in signal_values_for_dimension(
        item,
        "audience_expectation",
    )
    assert "family relationship" in signal_values_for_dimension(item, "topic_theme")
    assert "bittersweet" in signal_values_for_dimension(item, "mood")


def test_workplace_keywords_produce_workplace_comedy_and_drama_context():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["office", "work", "boss"]),
        mapping,
        include_debug=False,
    )

    assert "workplace story" in signal_values_for_dimension(item, "topic_theme")
    assert "workplace comedy" in signal_values_for_dimension(item, "audience_expectation")
    assert "character-focused" in signal_values_for_dimension(item, "mood")


def test_supernatural_keywords_produce_mystery_identity():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["witch", "gothic", "macabre"]),
        mapping,
        include_debug=False,
    )

    assert "supernatural mystery" in signal_values_for_dimension(
        item,
        "audience_expectation",
    )
    assert "supernatural story" in signal_values_for_dimension(item, "topic_theme")
    assert "eerie" in signal_values_for_dimension(item, "mood")


def test_political_crime_and_survival_drama_mappings_are_specific():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    political_item, _analysis = module.build_preview_item(
        content_fixture(module, ["political thriller", "political crisis"]),
        mapping,
        include_debug=False,
    )
    crime_item, _analysis = module.build_preview_item(
        content_fixture(module, ["cartel", "drug lord"]),
        mapping,
        include_debug=False,
    )
    survival_item, _analysis = module.build_preview_item(
        content_fixture(module, ["airplane crash", "island"]),
        mapping,
        include_debug=False,
    )

    assert "political thriller" in signal_values_for_dimension(
        political_item,
        "audience_expectation",
    )
    assert "political survival" in signal_values_for_dimension(
        political_item,
        "topic_theme",
    )
    assert "cartel crime drama" in signal_values_for_dimension(
        crime_item,
        "audience_expectation",
    )
    assert "cartel crime story" in signal_values_for_dimension(crime_item, "topic_theme")
    assert "survival mystery" in signal_values_for_dimension(
        survival_item,
        "audience_expectation",
    )
    assert "survival" in signal_values_for_dimension(survival_item, "topic_theme")


def test_unrelated_future_or_fantasy_terms_do_not_gain_war_or_post_apocalyptic_signals():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["future", "fantasy world", "superhero"]),
        mapping,
        include_debug=False,
    )
    rendered_signals = json.dumps(item["signals"]).lower()

    assert "war drama" not in rendered_signals
    assert "world war" not in rendered_signals
    assert "post-apocalyptic" not in rendered_signals


def test_mapping_config_does_not_reintroduce_generic_weak_labels():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    labels = {
        signal["display_label"]
        for entry in mapping["keyword_mappings"].values()
        for signal in entry.get("signals", [])
    }

    assert "Heavier watch" not in labels
    assert "Bleak mood" not in labels
    assert "Complex story" not in labels


def test_best_for_labels_are_user_friendly():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["based on comic", "memory", "world war ii", "martial arts"],
        ),
        mapping,
        include_debug=False,
    )
    best_for_text = json.dumps(item["watch_guidance"]["best_for"]).lower()

    assert "comic-book roots viewers" not in best_for_text
    assert "memory and identity viewers" not in best_for_text
    assert "world war ii setting viewers" not in best_for_text
    assert any(
        phrase in best_for_text
        for phrase in (
            "comic-book-based stories",
            "stories about memory and identity",
            "world war ii dramas",
            "martial-arts stories",
        )
    )


def test_public_chips_do_not_include_unsafe_violence_keyword():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["violence", "psychological thriller"]),
        mapping,
        include_debug=False,
    )
    rendered = json.dumps(item).lower()

    assert "violence" not in rendered
    assert item["keyword_counts"]["spoiler_unsafe_keywords"] == 1


def test_curated_override_adds_signals_and_sources():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["dark comedy", "crime"],
            title="Breaking Bad",
            content_type="series",
        ),
        mapping,
        override_config=overrides,
        include_debug=True,
    )
    rendered = json.dumps(item).lower()

    assert item["curated_override_applied"] is True
    assert "character-driven crime drama" in rendered
    assert "curated_override" in rendered


def test_breaking_bad_override_suppresses_misleading_primary_comedy():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["dark comedy", "crime"],
            title="Breaking Bad",
            content_type="series",
        ),
        mapping,
        override_config=overrides,
        include_debug=False,
    )
    watch_feel = item["watch_guidance"]["watch_feel"].lower()

    assert "character-driven crime drama" in watch_feel
    assert "offbeat comedy" not in watch_feel


def test_jurassic_park_override_adds_adventure_guidance():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["monster"],
            title="Jurassic Park",
            content_type="movie",
        ),
        mapping,
        override_config=overrides,
        include_debug=False,
    )
    guidance_text = json.dumps(item["watch_guidance"]).lower()

    assert "sci-fi adventure" in guidance_text
    assert "creature" in guidance_text


def test_documentary_metadata_fallback_marks_source():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["unmapped nature term"],
            title="Documentary Example",
            content_type="series",
            genres=["Documentary", "Nature"],
        ),
        mapping,
        include_debug=False,
    )
    rendered = json.dumps(item).lower()

    assert item["metadata_fallback_applied"] is True
    assert "metadata_fallback" in rendered
    assert "nature documentary" in rendered


def test_planet_earth_override_can_produce_documentary_guidance():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["unmapped nature term"],
            title="Planet Earth",
            content_type="series",
            genres=["Documentary"],
        ),
        mapping,
        override_config=overrides,
        include_debug=False,
    )
    guidance_text = json.dumps(item["watch_guidance"]).lower()

    assert item["curated_override_applied"] is True
    assert "nature documentary" in guidance_text
    assert "educational" in guidance_text


def test_anatomy_of_a_fall_override_gets_productized_watch_feel():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["unmapped courtroom tag"],
            title="Anatomy of a Fall",
            content_type="movie",
        ),
        mapping,
        override_config=overrides,
        include_debug=False,
    )

    assert item["watch_guidance"]["watch_feel"].startswith("A tense courtroom drama")
    assert item["watch_guidance"]["chips"]


def test_there_will_be_blood_override_gets_productized_watch_feel():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["unmapped oil tag"],
            title="There Will Be Blood",
            content_type="movie",
        ),
        mapping,
        override_config=overrides,
        include_debug=False,
    )

    assert item["watch_guidance"]["watch_feel"].startswith(
        "A severe character drama"
    )
    assert item["watch_guidance"]["chips"]


def test_poor_things_curated_watch_feel_is_not_bad_primary_identity():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["bold"],
            title="Poor Things",
            content_type="movie",
        ),
        mapping,
        override_config=overrides,
        include_debug=False,
    )

    assert item["curated_override_applied"] is True
    assert module.primary_identity_issue(item) is None


def test_low_confidence_only_signals_do_not_create_strong_watch_feel():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["bold"]),
        mapping,
        include_debug=False,
    )

    assert item["watch_guidance"]["watch_feel"] == module.LIMITED_GUIDANCE_TEXT


def test_report_includes_quality_diagnostics():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)
    content_items = [
        content_fixture(module, ["psychological thriller"]),
        module.KeywordContent(
            content_id=134,
            title="Sparse",
            content_type="movie",
            keywords=["very specific unmapped tag"],
        ),
    ]
    preview, analyses = module.build_preview_payload(
        generated_at="2026-07-01T00:00:00+00:00",
        mapping_file=Path("analytics/config/source_signal_keyword_mapping.json"),
        mapping_config=mapping,
        override_file=Path("analytics/config/source_signal_title_overrides.json"),
        override_config=overrides,
        content_items=content_items,
        include_debug=False,
    )

    report = module.build_report(
        generated_at="2026-07-01T00:00:00+00:00",
        mapping_file=Path("analytics/config/source_signal_keyword_mapping.json"),
        output_path=Path("analytics/processed/source_signals/source_signal_preview.json"),
        report_path=Path(
            "analytics/processed/source_signals/run_reports/source_signal_preview_report.json"
        ),
        mapping_config=mapping,
        override_file=Path("analytics/config/source_signal_title_overrides.json"),
        override_config=overrides,
        content_items=content_items,
        preview_items=preview["items"],
        analyses=analyses,
    )

    assert preview["db_write_performed"] is False
    assert report["db_write_performed"] is False
    assert report["preview_generator_version"] == "2026-07-02-v3.2.1"
    assert report["semantic_qa_version"] == "2026-07-02-v3.2.1"
    assert report["override_version"] == overrides["override_version"]
    assert "newly_mapped_from_previous_version" in report
    assert "signals_by_source" in report
    assert "titles_using_metadata_fallback_count" in report
    assert "titles_using_metadata_fallback" in report
    assert isinstance(report["titles_using_metadata_fallback"], list)
    assert "titles_using_curated_override_count" in report
    assert "titles_using_curated_override" in report
    assert isinstance(report["titles_using_curated_override"], list)
    assert "titles_keyword_only_count" in report
    assert "titles_keyword_only" in report
    assert isinstance(report["titles_keyword_only"], list)
    assert "titles_with_low_signal_quality" in report
    assert "titles_with_only_one_signal" in report
    assert "titles_with_no_watch_feel" in report
    assert "titles_with_bad_primary_identity" in report
    assert "titles_with_generic_watch_feel" in report
    assert "titles_with_semantic_conflicts" in report
    assert "titles_needing_curated_review" in report
    assert "semantic_quality_summary" in report
    assert "top_unmapped_high_value_candidates" in report
    assert "top_override_candidates" in report


def test_breaking_bad_override_is_not_candidate_after_curated_fix():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)
    content = content_fixture(
        module,
        ["dark comedy", "crime"],
        title="Breaking Bad",
        content_type="series",
    )
    preview, analyses = module.build_preview_payload(
        generated_at="2026-07-01T00:00:00+00:00",
        mapping_file=Path("analytics/config/source_signal_keyword_mapping.json"),
        mapping_config=mapping,
        override_file=Path("analytics/config/source_signal_title_overrides.json"),
        override_config=overrides,
        content_items=[content],
        include_debug=False,
    )
    report = module.build_report(
        generated_at="2026-07-01T00:00:00+00:00",
        mapping_file=Path("analytics/config/source_signal_keyword_mapping.json"),
        output_path=Path("analytics/processed/source_signals/source_signal_preview.json"),
        report_path=Path(
            "analytics/processed/source_signals/run_reports/source_signal_preview_report.json"
        ),
        mapping_config=mapping,
        override_file=Path("analytics/config/source_signal_title_overrides.json"),
        override_config=overrides,
        content_items=[content],
        preview_items=preview["items"],
        analyses=analyses,
    )

    assert not any(
        candidate["title"] == "Breaking Bad"
        for candidate in report["top_override_candidates"]
    )


def test_bad_primary_identity_still_catches_weak_abstract_watch_feel():
    module = load_keyword_signal_preview_module()
    item = {
        "watch_guidance": {"watch_feel": "A complex story."},
        "signals": {
            "audience_expectation": [
                {
                    "value": "complex story",
                    "label": "Complex story",
                    "confidence": "low",
                    "sources": ["tmdb_keywords"],
                }
            ]
        },
    }

    assert module.primary_identity_issue(item) == (
        "primary phrase uses only low-confidence signals"
    )


def test_generic_watch_feel_detection_catches_high_raw_low_mapped_output():
    module = load_keyword_signal_preview_module()
    item = {
        "curated_override_applied": False,
        "keyword_counts": {"raw_keywords": 18, "mapped_keywords": 2},
        "watch_guidance": {"watch_feel": "A fantasy adventure."},
    }

    assert module.generic_watch_feel_issue(item) == (
        "watch feel is too generic for a high-keyword title"
    )


def test_semantic_conflict_detection_catches_warm_revenge_story():
    module = load_keyword_signal_preview_module()
    item = {
        "watch_guidance": {
            "watch_feel": "A tense, warm revenge story.",
            "chips": ["Warm", "Revenge story"],
            "best_for": [],
        },
        "signals": {},
    }

    assert module.semantic_conflict_issue(item) == (
        "watch feel combines conflicting tone and identity signals"
    )


def test_semantic_conflict_detection_catches_warm_tech_sci_fi():
    module = load_keyword_signal_preview_module()
    item = {
        "watch_guidance": {
            "watch_feel": "A warm tech-driven sci-fi with a high-stakes edge.",
            "chips": ["Warm", "AI themes"],
            "best_for": [],
        },
        "signals": {},
    }

    assert module.semantic_conflict_issue(item) == (
        "watch feel combines conflicting tone and identity signals"
    )


def test_ex_machina_override_prevents_warm_tech_sci_fi_identity():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["artificial intelligence ai", "hope"],
            title="Ex Machina",
            content_type="movie",
        ),
        mapping,
        override_config=overrides,
        include_debug=False,
    )
    watch_feel = item["watch_guidance"]["watch_feel"].lower()

    assert "ai chamber thriller" in watch_feel
    assert "warm tech-driven sci-fi" not in watch_feel
    assert "friendship" not in watch_feel


def test_django_override_prevents_warm_revenge_identity():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["revenge", "hope"],
            title="Django Unchained",
            content_type="movie",
        ),
        mapping,
        override_config=overrides,
        include_debug=False,
    )
    watch_feel = item["watch_guidance"]["watch_feel"].lower()

    assert "revenge western" in watch_feel
    assert "warm revenge" not in watch_feel
    assert item["watch_guidance"]["consider_first"] == [
        "Better suited for viewers comfortable with darker or more intense stories."
    ]


def test_stranger_things_override_prevents_superhero_primary_identity():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["super power", "superhero team", "supernatural"],
            title="Stranger Things",
            content_type="series",
        ),
        mapping,
        override_config=overrides,
        include_debug=False,
    )
    watch_feel = item["watch_guidance"]["watch_feel"].lower()

    assert "supernatural adventure" in watch_feel
    assert "superhero" not in watch_feel


def test_the_bear_override_has_kitchen_workplace_guidance():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["workplace comedy"],
            title="The Bear",
            content_type="series",
        ),
        mapping,
        override_config=overrides,
        include_debug=False,
    )
    guidance_text = json.dumps(item["watch_guidance"]).lower()

    assert "kitchen workplace drama" in guidance_text
    assert "pressure" in guidance_text


def test_fight_club_override_prevents_dystopian_future_primary_identity():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["dystopia"],
            title="Fight Club",
            content_type="movie",
        ),
        mapping,
        override_config=overrides,
        include_debug=False,
    )
    watch_feel = item["watch_guidance"]["watch_feel"].lower()

    assert "psychological drama" in watch_feel
    assert "dystopian future" not in watch_feel


def test_godzilla_minus_one_override_has_creature_disaster_identity():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["disaster"],
            title="Godzilla Minus One",
            content_type="movie",
        ),
        mapping,
        override_config=overrides,
        include_debug=False,
    )
    guidance_text = json.dumps(item["watch_guidance"]).lower()

    assert "creature-disaster drama" in guidance_text
    assert "large-scale devastation" in guidance_text


def test_wolf_of_wall_street_override_has_finance_satire_identity():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["dark comedy"],
            title="The Wolf of Wall Street",
            content_type="movie",
        ),
        mapping,
        override_config=overrides,
        include_debug=False,
    )
    guidance_text = json.dumps(item["watch_guidance"]).lower()

    assert "finance satire" in guidance_text
    assert "fast" in guidance_text


def test_matrix_override_has_cyberpunk_action_sci_fi_identity():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["dystopia", "martial arts"],
            title="The Matrix",
            content_type="movie",
        ),
        mapping,
        override_config=overrides,
        include_debug=False,
    )
    guidance_text = json.dumps(item["watch_guidance"]).lower()

    assert "cyberpunk action sci-fi" in guidance_text
    assert "martial-arts spectacle" in guidance_text


def test_shawshank_override_has_prison_hope_identity():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    overrides = load_overrides(module)

    item, _analysis = module.build_preview_item(
        content_fixture(
            module,
            ["prison"],
            title="The Shawshank Redemption",
            content_type="movie",
        ),
        mapping,
        override_config=overrides,
        include_debug=False,
    )
    guidance_text = json.dumps(item["watch_guidance"]).lower()

    assert "prison drama" in guidance_text
    assert "hope" in guidance_text


def test_best_for_formatter_avoids_ai_themes_viewers():
    module = load_keyword_signal_preview_module()

    label = module.best_for_label(
        {
            "dimension": "topic_theme",
            "value": "artificial intelligence",
            "label": "AI themes",
        }
    )

    assert label == "AI-driven sci-fi"
    assert "viewers" not in label.lower()


def test_best_for_formatter_replaces_common_viewers_patterns():
    module = load_keyword_signal_preview_module()

    cases = {
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
    }

    for value, expected in cases.items():
        assert module.best_for_label(
            {
                "dimension": "audience_expectation",
                "value": value,
                "label": expected.removesuffix("s"),
            }
        ) == expected


def test_chip_formatter_avoids_duplicate_superhero_chips():
    module = load_keyword_signal_preview_module()

    chips = module.normalize_chip_list(
        ["Superhero team story", "Superhero story", "Tense"],
        5,
    )

    assert "Superhero team story" in chips
    assert "Superhero story" not in chips


def test_debug_controls_raw_keyword_visibility():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)
    content = content_fixture(module, ["serial killer", "aftercreditsstinger"])

    item_without_debug, _analysis = module.build_preview_item(
        content,
        mapping,
        include_debug=False,
    )
    item_with_debug, _analysis = module.build_preview_item(
        content,
        mapping,
        include_debug=True,
    )

    assert "debug" not in item_without_debug
    assert "debug" in item_with_debug
    assert item_with_debug["debug"]["raw_keywords"] == [
        "aftercreditsstinger",
        "serial killer",
    ]


def test_unmapped_keywords_are_counted_not_displayed():
    module = load_keyword_signal_preview_module()
    mapping = load_mapping(module)

    item, _analysis = module.build_preview_item(
        content_fixture(module, ["very specific unmapped tag"]),
        mapping,
        include_debug=False,
    )
    rendered = json.dumps(item).lower()

    assert item["keyword_counts"]["unmapped_keywords"] == 1
    assert "very specific unmapped tag" not in rendered
    assert not any(item["signals"].values())
