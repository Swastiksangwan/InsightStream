import pytest

from app.services.decision_insight_formatter import (
    InsightComponent,
    InsightPlan,
    audience_modifier,
    build_insight_plan,
    evidence_family_matches,
    genre_identity,
    realize_display_casing,
    render_decision_headline,
    render_insight_plan,
)


def signal(
    dimension,
    label,
    *,
    confidence="medium",
    spoiler_safe=True,
    sources=None,
):
    return {
        "dimension": dimension,
        "value": label.casefold(),
        "label": label,
        "confidence": confidence,
        "spoiler_safe": spoiler_safe,
        "sources": sources or ["tmdb_keywords"],
    }


def profile(identity=None, themes=None, feel=None, pace=None):
    return {
        "identity": identity or [],
        "themes": themes or [],
        "feel": feel or [],
        "pace": pace,
        "best_for": [],
        "consider_first": [],
    }


def context(*, content_type="movie", overview=None, genres=None, inferred=None):
    return {
        "content": {
            "title": "Synthetic future title",
            "type": content_type,
            "overview": overview,
        },
        "genres": genres or [],
        "inferred_identity": inferred,
    }


@pytest.mark.parametrize(
    (
        "title",
        "identities",
        "themes",
        "genres",
        "overview",
        "inferred",
        "expected",
        "forbidden",
    ),
    [
        (
            "Spider-Man: Across the Spider-Verse",
            [("Romantic drama", "medium"), ("Superhero team story", "high")],
            ["Superhero story", "Superhuman powers"],
            ["Action", "Adventure", "Animation", "Sci-Fi"],
            "Spider-People face a difficult choice across the multiverse.",
            "Animated superhero drama",
            "superhero",
            "romantic drama",
        ),
        (
            "Game of Thrones",
            [("Fantasy adventure", "medium"), ("Political power drama", "medium")],
            ["Dark fantasy", "Power struggle"],
            ["Action", "Adventure", "Drama", "Fantasy", "Sci-Fi"],
            "Noble families struggle for power in the mythical land of Westeros.",
            "Cyberpunk action sci-fi",
            "fantasy",
            "cyberpunk",
        ),
        (
            "Amadeus",
            [("Mythic superhero mystery", "medium"), ("Music-driven story", "medium")],
            [],
            ["Drama", "History", "Music"],
            "Two composers are divided by artistic rivalry and jealousy.",
            None,
            "historical music drama",
            "superhero",
        ),
        (
            "The Wild Robot",
            [("Animated adventure", "high")],
            ["Island survival", "Found family"],
            ["Adventure", "Animation", "Family", "Sci-Fi"],
            "A robot adapts to an island and forms an unlikely family bond.",
            "Psychological survival thriller",
            "animated adventure",
            "psychological survival",
        ),
        (
            "The Holdovers",
            [("Bittersweet comedy", "high"), ("War drama", "medium")],
            ["Grief and healing", "Unlikely companionship", "War"],
            ["Comedy", "Drama"],
            "A teacher and student form an unlikely bond after a personal loss linked to Vietnam.",
            None,
            "bittersweet comedy",
            "war drama",
        ),
        (
            "The Crown",
            [("Royal drama", "high"), ("Political thriller", "medium")],
            ["Political pressure", "Political survival"],
            ["Drama"],
            "A monarch and prime ministers navigate public duty and court intrigue.",
            "Psychological survival thriller",
            "royal drama",
            "survival thriller",
        ),
        (
            "Anatomy of a Fall",
            [("Courtroom drama", "high")],
            ["Family relationship", "Moral responsibility"],
            ["Crime", "Mystery", "Thriller"],
            "A writer faces a courtroom inquiry after her husband's suspicious death.",
            "Serial-killer investigation",
            "courtroom drama",
            "serial-killer",
        ),
        (
            "The Sandman",
            [("Superhero story", "medium")],
            ["Dark fantasy", "Comic-book roots"],
            ["Action", "Adventure", "Drama", "Fantasy", "Sci-Fi"],
            "After years of imprisonment, the King of Dreams journeys across worlds.",
            "Prison drama",
            "dark fantasy",
            "prison drama",
        ),
        (
            "The Prestige",
            [("Fantasy adventure", "medium"), ("Rivalry mystery", "high")],
            ["Obsession"],
            ["Drama", "Mystery", "Sci-Fi"],
            "Two magicians pursue an intense rivalry and dangerous secrets.",
            None,
            "rivalry mystery",
            "fantasy adventure",
        ),
        (
            "Her",
            [("Speculative sci-fi", "medium")],
            ["Future society"],
            ["Drama", "Romance", "Sci-Fi"],
            "A romantic relationship develops between a writer and an operating system.",
            "Satirical sci-fi anthology",
            "romantic drama",
            "anthology",
        ),
        (
            "The White Lotus",
            [("Satirical social drama", "high")],
            ["Class tension", "Island survival"],
            ["Comedy", "Drama", "Mystery"],
            "Guests and employees reveal darker tensions at an exclusive resort.",
            "Psychological survival thriller",
            "satirical social drama",
            "survival thriller",
        ),
    ],
)
def test_identity_trust_and_metadata_compatibility_regressions(
    title,
    identities,
    themes,
    genres,
    overview,
    inferred,
    expected,
    forbidden,
):
    del title
    signals = [
        *[
            signal("audience_expectation", label, confidence=confidence)
            for label, confidence in identities
        ],
        *[signal("topic_theme", label) for label in themes],
    ]
    plan, sentence = format_plan(
        profile(identity=[label for label, _confidence in identities] + ([inferred] if inferred else []), themes=themes),
        signals,
        context(overview=overview, genres=genres, inferred=inferred),
    )

    assert expected in sentence.casefold()
    assert forbidden not in sentence.casefold()
    assert plan.primary_identity.trust_tier is not None
    assert plan.primary_identity.selection_rationale


def test_modifier_selection_prefers_confidence_over_profile_order():
    plan, sentence = format_plan(
        profile(identity=["Character drama"], feel=["Bold", "Gentle"]),
        [
            signal("audience_expectation", "Character drama", confidence="high"),
            signal("mood", "Bold", confidence="low"),
            signal("mood", "Gentle", confidence="high"),
        ],
        context(genres=["Drama"]),
    )

    assert plan.tone_modifier.text == "gentle"
    assert plan.tone_modifier.confidence == "high"
    assert sentence.startswith("A gentle character drama")


def test_curated_identity_uses_highest_trust_tier_when_metadata_compatible():
    signals = [
        signal(
            "audience_expectation",
            "Royal drama",
            confidence="high",
            sources=["curated_override"],
        ),
        signal("audience_expectation", "Political thriller", confidence="high"),
    ]
    plan = build_insight_plan(
        profile(identity=["Political thriller", "Royal drama"]),
        {
            "watch_feel": "Legacy prose is not evidence.",
            "curated_override_applied": True,
        },
        signals,
        context(
            overview="A monarch navigates court politics and public duty.",
            genres=["Drama"],
        ),
    )

    assert plan.primary_identity.text == "Royal drama"
    assert plan.primary_identity.trust_tier == 1
    assert plan.primary_identity.source.startswith("curated_override:")
    assert plan.curated_identity_available is True
    assert plan.curated_identity_evaluation == "selected"


def test_aviation_action_is_a_governed_curated_identity_with_supported_modifier():
    signals = [
        signal(
            "audience_expectation",
            "Aviation action",
            confidence="high",
            sources=["curated_override"],
        ),
        signal("tone", "Bold", confidence="low"),
        signal("tone", "Serious tone", confidence="high"),
    ]
    plan = build_insight_plan(
        profile(identity=["Aviation action", "Drama"], feel=["Bold", "Serious"]),
        {"watch_feel": None, "curated_override_applied": True},
        signals,
        context(
            overview="Elite naval aviators train for a dangerous mission.",
            genres=["Action", "Drama"],
        ),
    )
    sentence = render_insight_plan(plan)

    assert plan.primary_identity.text == "Aviation action"
    assert plan.primary_identity.trust_tier == 1
    assert plan.curated_identity_evaluation == "selected"
    assert plan.tone_modifier.text == "serious"
    assert sentence.startswith("A serious aviation action")


def test_aviation_action_requires_governed_source_and_action_metadata():
    plan, sentence = format_plan(
        profile(identity=["Aviation action", "Drama"]),
        [signal("audience_expectation", "Aviation action", confidence="high")],
        context(
            overview="A family watches an aircraft cross the sky.",
            genres=["Drama"],
        ),
    )

    assert plan.primary_identity.text == "Drama"
    assert sentence == "A drama."
    assert any(
        item.get("conflict_reason") == "missing_aviation_action_evidence"
        for item in plan.rejected_candidates
    )


@pytest.mark.parametrize(
    ("family", "singular", "plural"),
    [
        ("serial_killer", "a serial killer case", "multiple serial killers"),
        ("cartel", "a drug cartel", "several drug cartels"),
        ("spy", "an undercover spy", "undercover spies"),
    ],
)
def test_evidence_family_matching_supports_governed_lexical_forms(
    family,
    singular,
    plural,
):
    assert evidence_family_matches(singular, family)
    assert evidence_family_matches(plural, family)
    assert not evidence_family_matches("A private family matter.", family)


def test_curated_identity_evaluation_records_copy_role_rejection_as_evaluated():
    rejected = build_insight_plan(
        profile(identity=["Romantic drama", "Crime thriller"]),
        {"watch_feel": None, "curated_override_applied": True},
        [
            signal(
                "audience_expectation",
                "Romantic drama",
                confidence="high",
                sources=["curated_override"],
            ),
            signal("audience_expectation", "Crime thriller", confidence="high"),
        ],
        context(
            overview="Detectives investigate organized crime.",
            genres=["Crime", "Thriller"],
        ),
    )
    not_evaluated = build_insight_plan(
        profile(identity=["Unclassified resonance", "Drama"]),
        {"watch_feel": None, "curated_override_applied": True},
        [
            signal(
                "audience_expectation",
                "Unclassified resonance",
                confidence="high",
                sources=["curated_override"],
            )
        ],
        context(genres=["Drama"]),
    )

    assert rejected.curated_identity_evaluation == "evaluated_rejected"
    assert not_evaluated.curated_identity_evaluation == "evaluated_rejected"


def test_copy_realization_avoids_stacks_momentum_chains_and_raw_taxonomy():
    plan, sentence = format_plan(
        profile(
            identity=["Restrained romance"],
            themes=["Ambition and rivalry", "Technology and society", "Anime style"],
            feel=["Warm"],
            pace="Slow-burn",
        ),
        [
            signal("audience_expectation", "Restrained romance", confidence="high"),
            signal("topic_theme", "Ambition and rivalry", confidence="high"),
            signal("topic_theme", "Technology and society", confidence="high"),
            signal("topic_theme", "Anime style", confidence="high"),
            signal("mood", "Warm", confidence="high"),
            signal("pacing", "Slow-burn", confidence="medium"),
        ],
        context(genres=["Drama", "Romance"]),
    )

    assert sentence.startswith("A warm, restrained romance")
    assert "momentum" not in sentence
    assert sentence.casefold().count(" and ") <= 2
    assert "anime style" not in sentence.casefold()
    assert any(
        item["reason"] == "raw_taxonomy_not_user_facing"
        for item in plan.rejected_candidates
    )


def format_plan(display_profile, signals, display_context):
    plan = build_insight_plan(
        display_profile,
        {"watch_feel": "Legacy prose must not become evidence."},
        signals,
        display_context,
    )
    return plan, render_insight_plan(plan)


def component(text, role="identity"):
    return InsightComponent(
        text=text,
        role=role,
        concept_family=text.casefold(),
        source="test",
        evidence="synthetic fixture",
    )


def test_known_future_identity_and_theme_render_deterministically():
    signals = [
        signal("audience_expectation", "Crime thriller"),
        signal("topic_theme", "Investigation"),
    ]
    args = (
        profile(identity=["Crime thriller"], themes=["Investigation"]),
        signals,
        context(overview="A detective investigates a difficult case.", genres=["Crime"]),
    )

    first_plan, first_sentence = format_plan(*args)
    second_plan, second_sentence = format_plan(*args)

    assert first_plan.as_dict() == second_plan.as_dict()
    assert first_sentence == second_sentence
    assert "crime thriller" in first_sentence.casefold()
    assert "investigation" in first_sentence.casefold()


def test_unknown_identity_falls_back_to_supported_genre_copy():
    plan, sentence = format_plan(
        profile(identity=["Unclassified resonance"]),
        [signal("audience_expectation", "Unclassified resonance")],
        context(genres=["Drama"]),
    )

    assert sentence == "A drama."
    assert plan.primary_identity.source == "genre_context"
    assert any(
        item["reason"] == "missing_identity_copy_role"
        for item in plan.rejected_candidates
    )


def test_unknown_theme_is_rejected_instead_of_inserted_into_prose():
    plan, sentence = format_plan(
        profile(identity=["Crime thriller"], themes=["Aurora resonance"]),
        [
            signal("audience_expectation", "Crime thriller"),
            signal("topic_theme", "Aurora resonance"),
        ],
        context(genres=["Crime"]),
    )

    assert "aurora resonance" not in sentence.casefold()
    assert any(
        item["reason"] == "missing_about_copy_role"
        for item in plan.rejected_candidates
    )


def test_identity_only_without_tone_mood_theme_or_pace_is_truthful():
    plan, sentence = format_plan(
        profile(identity=["Documentary"]),
        [signal("audience_expectation", "Documentary")],
        context(genres=["Documentary"]),
    )

    assert sentence == "A documentary."
    assert plan.primary_differentiator is None
    assert plan.tone_modifier is None
    assert plan.pacing_modifier is None


def test_metadata_fallback_only_is_rendered_and_marked_as_profile_evidence():
    plan, sentence = format_plan(
        profile(identity=["Drama"]),
        [],
        context(content_type="series", genres=["Drama"]),
    )

    assert sentence == "A drama."
    assert plan.primary_identity.source in {"display_profile", "genre_context"}


def test_many_overlapping_signals_are_deduplicated_by_concept_family():
    plan, sentence = format_plan(
        profile(
            identity=["Romantic drama", "Relationship story"],
            themes=["Romance", "Romantic connection", "Class divide"],
        ),
        [
            signal("audience_expectation", "Romantic drama"),
            signal("audience_expectation", "Relationship story"),
            signal("topic_theme", "Romance"),
            signal("topic_theme", "Romantic connection"),
            signal("topic_theme", "Class divide"),
        ],
        context(genres=["Drama", "Romance"]),
    )

    assert sentence.casefold().count("romantic") == 1
    assert "differences in class and status" in sentence.casefold()
    assert not plan.validation_errors


def test_unseen_future_canonical_identity_with_safe_noun_role_is_supported():
    plan, sentence = format_plan(
        profile(identity=["Solarpunk mystery"]),
        [signal("audience_expectation", "Solarpunk mystery")],
        context(genres=["Mystery"]),
    )

    assert sentence == "A solarpunk mystery."
    assert plan.primary_identity.source.startswith("source_signal:")


def test_spoiler_unsafe_candidate_is_never_rendered():
    plan, sentence = format_plan(
        profile(identity=["Crime thriller"], themes=["Secret identity"]),
        [
            signal("audience_expectation", "Crime thriller"),
            signal("topic_theme", "Secret identity", spoiler_safe=False),
        ],
        context(genres=["Crime"]),
    )

    assert "secret identity" not in sentence.casefold()
    assert any(
        item["reason"] == "spoiler_unsafe" for item in plan.rejected_candidates
    )


def test_missing_overview_and_empty_genres_do_not_throw():
    plan, sentence = format_plan(profile(), [], context(overview=None, genres=[]))

    assert sentence is None
    assert plan.validation_errors == ["missing_supported_identity"]


def test_unicode_title_and_labels_fail_closed_without_losing_known_identity():
    plan, sentence = format_plan(
        profile(identity=["Fantasia épica", "Animated adventure"]),
        [
            signal("audience_expectation", "Fantasia épica"),
            signal("audience_expectation", "Animated adventure"),
            signal("topic_theme", "Memória cósmica"),
        ],
        context(
            content_type="series",
            overview="Uma jornada através de mundos.",
            genres=["Animation", "Adventure"],
        ),
    )

    assert sentence == "An animated adventure."
    assert "memória cósmica" not in sentence.casefold()
    assert not plan.validation_errors


def test_overview_rules_are_phrase_aware_and_do_not_match_generic_case():
    plan, sentence = format_plan(
        profile(identity=["Historical drama"]),
        [signal("audience_expectation", "Historical drama")],
        context(
            overview="In each case, the family exceeds every expectation.",
            genres=["Drama"],
        ),
    )

    assert "investigation" not in sentence.casefold()
    assert not any(
        component.source == "overview_rule"
        for component in (
            plan.primary_differentiator,
            plan.secondary_differentiator,
        )
        if component
    )


def test_non_artistic_aspiration_does_not_create_artistic_ambition():
    _plan, sentence = format_plan(
        profile(identity=["Superhero story"]),
        [signal("audience_expectation", "Superhero story")],
        context(
            overview="A young archer dreams of becoming a superhero.",
            genres=["Action"],
        ),
    )

    assert "artistic ambition" not in sentence.casefold()


def rating_source(category, name, included=True):
    return {
        "source_name": name,
        "source_category": category,
        "included_in_unified_score": included,
    }


@pytest.mark.parametrize(
    ("score", "sources", "count", "expected"),
    [
        (
            84,
            [rating_source("audience", "tmdb"), rating_source("audience", "imdb")],
            2,
            "strong audience backing",
        ),
        (
            84,
            [rating_source("audience", "tmdb"), rating_source("critic", "metacritic")],
            2,
            "strong cross-source ratings",
        ),
        (
            92,
            [rating_source("critic", "one"), rating_source("internal", "two")],
            2,
            "exceptional cross-source ratings",
        ),
        (84, [rating_source("audience", "tmdb")], 1, None),
        (
            69,
            [rating_source("audience", "tmdb"), rating_source("audience", "imdb")],
            2,
            None,
        ),
        (None, [], 0, None),
    ],
)
def test_rating_modifier_uses_source_accurate_language(score, sources, count, expected):
    modifier = audience_modifier(
        {
            "ratings": {
                "unified_score": score,
                "scoring_source_count": count,
                "sources": sources,
            }
        }
    )

    assert (modifier.text if modifier else None) == expected
    if modifier:
        assert "categories:" in modifier.evidence
        assert "sources:" in modifier.evidence


def test_primary_insight_is_stable_when_only_ratings_change():
    display_profile = profile(
        identity=["Crime thriller"],
        themes=["Investigation"],
        feel=["Tense"],
    )
    signals = [
        signal("audience_expectation", "Crime thriller"),
        signal("topic_theme", "Investigation"),
        signal("mood", "Tense"),
    ]
    contexts = [
        context(genres=["Crime", "Thriller"]),
        {
            **context(genres=["Crime", "Thriller"]),
            "ratings": {
                "unified_score": 95,
                "scoring_source_count": 2,
                "sources": [
                    rating_source("audience", "tmdb"),
                    rating_source("audience", "imdb"),
                ],
            },
        },
        {
            **context(genres=["Crime", "Thriller"]),
            "ratings": {
                "unified_score": 72,
                "scoring_source_count": 2,
                "sources": [
                    rating_source("audience", "tmdb"),
                    rating_source("critic", "metacritic"),
                ],
            },
        },
    ]

    plans_and_sentences = [
        format_plan(display_profile, signals, display_context)
        for display_context in contexts
    ]

    assert len({sentence for _plan, sentence in plans_and_sentences}) == 1
    assert all(
        "audience backing" not in sentence.casefold()
        and "ratings" not in sentence.casefold()
        for _plan, sentence in plans_and_sentences
    )
    assert plans_and_sentences[0][0].audience_modifier is None
    assert plans_and_sentences[1][0].audience_modifier.text == (
        "exceptional audience backing"
    )
    assert plans_and_sentences[2][0].audience_modifier.text == (
        "positive cross-source ratings"
    )


@pytest.mark.parametrize(
    "template_family",
    [
        "identity_about",
        "identity_conflict",
        "hybrid_blend",
        "experience_driven",
        "character_exploration",
        "documentary_examination",
        "layered_exploration",
    ],
)
def test_decision_headline_is_identity_driven_for_every_template(template_family):
    plan = InsightPlan(
        primary_identity=component("Workplace comedy"),
        tone_modifier=component("light", role="adjective"),
        primary_differentiator=component("studio pressure", role="about_phrase"),
        template_family=template_family,
    )

    headline = render_decision_headline(plan)

    assert headline == "Best suited for viewers looking for a light workplace comedy."
    assert "studio pressure" not in headline


@pytest.mark.parametrize(
    ("genres", "expected"),
    [
        (["Documentary", "War"], "War documentary"),
        (["Documentary", "History"], "History documentary"),
        (["Documentary", "Music"], "Music documentary"),
        (["Documentary", "Nature"], "Nature documentary"),
        (["Documentary"], "Documentary"),
        (["War", "Drama"], "War drama"),
        (["History", "Drama"], "Historical drama"),
    ],
)
def test_genre_identity_keeps_documentaries_out_of_drama_fallbacks(genres, expected):
    assert genre_identity([], {"genres": genres}) == expected


def test_documentary_converts_supported_war_identity_without_losing_specificity():
    assert genre_identity(
        ["War drama"],
        {"genres": ["Documentary"]},
    ) == "War documentary"


@pytest.mark.parametrize(
    ("identity", "theme", "genres"),
    [
        ("War documentary", "War", ["Documentary", "War"]),
        ("History documentary", "Period setting", ["Documentary", "History"]),
        ("Music documentary", "Music", ["Documentary", "Music"]),
        ("Nature documentary", "Nature", ["Documentary", "Nature"]),
    ],
)
def test_documentary_identity_rejects_repeated_theme_concept(identity, theme, genres):
    plan, sentence = format_plan(
        profile(identity=[identity], themes=[theme]),
        [
            signal("audience_expectation", identity),
            signal("topic_theme", theme),
        ],
        context(genres=genres),
    )

    assert theme.casefold() not in sentence.casefold().removeprefix(
        f"a {identity.casefold()}"
    ).removeprefix(f"an {identity.casefold()}")
    assert any(
        item.get("concept_family") == plan.primary_identity.concept_family
        and item["reason"] == "duplicate_concept_family"
        for item in plan.rejected_candidates
    )


@pytest.mark.parametrize(
    ("identity", "theme", "genres", "expected_phrase"),
    [
        ("War documentary", "Human cost", ["Documentary", "War"], "human cost"),
        (
            "Music documentary",
            "Artistic ambition",
            ["Documentary", "Music"],
            "artistic ambition",
        ),
        (
            "Nature documentary",
            "Conservation",
            ["Documentary", "Nature"],
            "conservation",
        ),
        (
            "History documentary",
            "Historical power struggle",
            ["Documentary", "History"],
            "political power",
        ),
    ],
)
def test_documentary_identity_keeps_distinct_theme(identity, theme, genres, expected_phrase):
    _plan, sentence = format_plan(
        profile(identity=[identity], themes=[theme]),
        [
            signal("audience_expectation", identity),
            signal("topic_theme", theme),
        ],
        context(genres=genres),
    )

    assert expected_phrase in sentence.casefold()


def test_explicit_racial_inequality_context_outranks_generic_conspiracy():
    plan, sentence = format_plan(
        profile(
            identity=["Documentary"],
            themes=["Conspiracy"],
            feel=["Tense"],
        ),
        [
            signal("audience_expectation", "Documentary"),
            signal("topic_theme", "Conspiracy"),
            signal("mood", "Tense"),
        ],
        context(
            overview=(
                "An examination of the prison system and the nation's history "
                "of racial inequality."
            ),
            genres=["Documentary"],
        ),
    )

    assert sentence == "A tense documentary examining racial inequality."
    assert plan.primary_differentiator.source == "overview_rule"
    assert plan.primary_differentiator.evidence == (
        "rule=explicit_racial_inequality;matched=racial inequality;scope=equivalent"
    )
    assert any(
        item["candidate"] == "conspiracy"
        and item["reason"] == "lower_priority_than_explicit_context"
        and item["evidence"] == "topic_theme:Conspiracy"
        for item in plan.rejected_candidates
    )


def test_social_critique_copy_does_not_broaden_to_inequality():
    _plan, sentence = format_plan(
        profile(identity=["Music-driven horror"], themes=["Social critique"]),
        [
            signal("audience_expectation", "Music-driven horror"),
            signal("topic_theme", "Social critique"),
        ],
        context(genres=["Horror"]),
    )

    assert "social critique" in sentence.casefold()
    assert "inequality" not in sentence.casefold()


def test_low_confidence_theme_does_not_fill_secondary_slot():
    plan, sentence = format_plan(
        profile(
            identity=["Creature thriller"],
            themes=["Supernatural story", "Family relationship"],
        ),
        [
            signal("audience_expectation", "Creature thriller"),
            signal("topic_theme", "Supernatural story", confidence="medium"),
            signal("topic_theme", "Family relationship", confidence="low"),
        ],
        context(genres=["Horror"]),
    )

    assert "supernatural forces" in sentence.casefold()
    assert "family relationships" not in sentence.casefold()
    assert any(
        item["reason"] == "low_confidence_secondary"
        for item in plan.rejected_candidates
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ai thriller", "AI thriller"),
        ("a tense ai thriller", "a tense AI thriller"),
        ("an ai thriller", "an AI thriller"),
        ("AI thriller", "AI thriller"),
        ("(fbi), cia; mi5/mi6 and kgb", "(FBI), CIA; MI5/MI6 and KGB"),
        ("world war ii drama", "World War II drama"),
        ("a wwii story", "a WWII story"),
        ("a paid role", "a paid role"),
    ],
)
def test_token_aware_display_casing(raw, expected):
    assert realize_display_casing(raw) == expected


def test_centrality_guard_prefers_explicit_fantasy_over_background_war_genre():
    plan, sentence = format_plan(
        profile(identity=["War drama", "Dark fantasy"], themes=["Dark fantasy", "War"]),
        [
            signal("audience_expectation", "Dark fantasy"),
            signal("topic_theme", "Dark fantasy"),
            signal("topic_theme", "War"),
        ],
        context(
            genres=["Drama", "Fantasy", "War"],
            overview=(
                "In post-civil-war Spain, a child enters a labyrinth where a "
                "faun reveals an underground kingdom and a lost princess."
            ),
        ),
    )

    assert plan.primary_identity.text == "Dark fantasy"
    assert plan.primary_identity.explicit_premise_evidence is True
    assert "fantasy" in sentence.casefold()
    assert any(
        item.get("candidate") == "War drama"
        and item.get("reason") == "stronger_corroborated_candidate_selected"
        for item in plan.rejected_candidates
    )


def test_centrality_guard_preserves_curated_tier_one_authority():
    display_profile = profile(identity=["AI thriller", "Tech-driven sci-fi"])
    signals = [
        signal(
            "audience_expectation",
            "AI thriller",
            confidence="high",
            sources=["curated_override"],
        ),
        signal("audience_expectation", "Tech-driven sci-fi"),
        signal("topic_theme", "Technology and society"),
    ]
    plan = build_insight_plan(
        display_profile,
        {"curated_override_applied": True},
        signals,
        context(
            genres=["Drama", "Sci-Fi"],
            overview="A programmer tests the first true artificial intelligence.",
        ),
    )

    assert plan.primary_identity.text == "AI thriller"
    assert plan.primary_identity.trust_tier == 1


def test_incidental_war_theme_is_suppressed_but_retained_in_debug_provenance():
    plan, sentence = format_plan(
        profile(
            identity=["Reality-bending sci-fi"],
            themes=["Alien encounter", "War"],
        ),
        [
            signal("audience_expectation", "Reality-bending sci-fi"),
            signal("topic_theme", "Alien encounter"),
            signal("topic_theme", "War"),
        ],
        context(
            genres=["Drama", "Mystery", "Sci-Fi"],
            overview=(
                "An expert linguist is recruited after alien crafts arrive to "
                "determine whether they come in peace."
            ),
        ),
    )

    assert "alien encounter" in sentence.casefold()
    assert "war" not in sentence.casefold()
    assert any(
        item.get("candidate") == "war"
        and item.get("reason") == "incidental_context_suppressed"
        for item in plan.rejected_candidates
    )


def test_governed_spy_evidence_recognizes_agents_and_undercover_premise():
    assert evidence_family_matches(
        "Two Soviet KGB officers pose as a married couple while living undercover.",
        "spy",
    )
    assert not evidence_family_matches("A secret government mission begins.", "spy")
