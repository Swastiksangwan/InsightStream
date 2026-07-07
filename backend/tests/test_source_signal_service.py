from app.services.source_signal_service import (
    display_has_blocked_public_phrase,
    get_content_decision_layer,
    sanitize_label,
    sanitize_labels,
)


class FakeResult:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def mappings(self):
        return self

    def first(self):
        return self.row

    def all(self):
        return self.rows


class FakeDecisionDb:
    def __init__(self, guidance=None, signals=None):
        self.guidance = guidance
        self.signals = signals or []

    def execute(self, query, _params):
        query_text = str(query)
        if "FROM content_watch_guidance" in query_text:
            return FakeResult(row=self.guidance)
        if "FROM content_source_signals" in query_text:
            return FakeResult(rows=self.signals)
        return FakeResult()


def guidance_row(**overrides):
    row = {
        "content_id": 1,
        "watch_feel": "A tense character-driven crime drama about pressure and consequence.",
        "chips": [
            "Character-driven crime drama",
            "JioHotstar viewers",
            "Tense",
            "Drama",
            "Fantasy story viewers",
        ],
        "best_for": [
            "Crime drama viewers",
            "Serialized drama viewers",
            "Prime Video viewers",
        ],
        "consider_first": [
            "Better suited for viewers comfortable with darker or more intense stories."
        ],
        "keyword_counts": {"raw_keywords": 10, "mapped_keywords": 5},
        "signal_sources": ["tmdb_keywords", "curated_override"],
        "curated_override_applied": True,
        "metadata_fallback_applied": False,
        "storage_ready": True,
        "frontend_ready": False,
        "quality_summary": {"mapping_version": "2026-07-02-v3.1"},
    }
    row.update(overrides)
    return row


def signal_row(dimension, label, value=None, confidence="medium"):
    return {
        "dimension": dimension,
        "value": value or label.lower(),
        "label": label,
        "confidence": confidence,
    }


def display_context(**overrides):
    context = {
        "content": {
            "type": "movie",
            "age_rating": "UA",
            "runtime": 148,
        },
        "genres": ["Science Fiction", "Thriller"],
        "ratings": {
            "unified_score": 86,
            "scoring_source_count": 2,
        },
        "platforms": [
            {
                "name": "JioHotstar",
                "availability_type": "streaming",
                "region_code": "IN",
            }
        ],
        "credits": {
            "directors": [{"name": "Christopher Nolan"}],
            "creators": [],
        },
        "series_metadata": None,
    }
    context.update(overrides)
    return context


def test_sanitize_label_rewrites_viewer_patterns():
    assert sanitize_label("Fantasy story viewers") == "Fantasy stories"
    assert sanitize_label("AI themes viewers") == "AI-driven sci-fi"
    assert sanitize_label("Character-driven series viewers") == "Character-driven series"


def test_sanitize_labels_removes_platform_and_weak_labels():
    assert sanitize_labels(
        [
            "JioHotstar viewers",
            "Netflix viewers",
            "Drama",
            "Dark fantasy",
            "Tense",
        ],
        limit=5,
    ) == ["Dark fantasy", "Tense"]


def assert_display_has_no_blocked_phrases(display):
    assert not display_has_blocked_public_phrase(display)


def test_decision_layer_returns_sanitized_watch_profile_and_decision_copy():
    db = FakeDecisionDb(
        guidance=guidance_row(),
        signals=[
            signal_row("audience_expectation", "Crime drama"),
            signal_row("tone", "Tense"),
            signal_row("mood", "Foreboding"),
        ],
    )

    decision_layer = get_content_decision_layer(db, 1)

    assert decision_layer["watch_profile"]["watch_feel"].startswith(
        "A tense character-driven crime drama"
    )
    assert "JioHotstar viewers" not in decision_layer["watch_profile"]["chips"]
    assert "Drama" not in decision_layer["watch_profile"]["chips"]
    assert "Fantasy stories" in decision_layer["watch_profile"]["chips"]
    assert "Crime dramas" in decision_layer["watch_profile"]["best_for"]
    assert "Long-form dramas" in decision_layer["watch_profile"]["best_for"]
    assert decision_layer["decision_support"]["headline"] == (
        "Best suited for viewers looking for a tense character-driven crime drama."
    )
    reasons = decision_layer["decision_support"]["reasons"]
    assert reasons
    assert all("Clear " not in reason for reason in reasons)
    assert all("Good fit for" not in reason for reason in reasons)
    assert all("watch profile" not in reason for reason in reasons)
    assert decision_layer["decision_support"]["cautions"]
    assert decision_layer["display"]["primary_insight"]
    assert decision_layer["signal_quality"] == {
        "storage_ready": True,
        "frontend_ready": False,
        "has_watch_guidance": True,
        "has_source_signals": True,
    }


def test_decision_layer_keeps_useful_chips():
    db = FakeDecisionDb(
        guidance=guidance_row(
            chips=[
                "Dark fantasy",
                "Political power drama",
                "Power struggle",
                "JioHotstar viewers",
            ],
            best_for=["Political power dramas", "Fantasy adventures"],
        ),
        signals=[signal_row("topic_theme", "Political power drama")],
    )

    decision_layer = get_content_decision_layer(db, 1)

    assert "Political power drama" in decision_layer["watch_profile"]["chips"]
    assert "Dark fantasy" in decision_layer["watch_profile"]["chips"]
    assert "Power struggle" in decision_layer["watch_profile"]["chips"]
    assert "JioHotstar viewers" not in decision_layer["watch_profile"]["chips"]


def test_decision_layer_prioritizes_strong_chips_over_weak_secondary_chips():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel=(
                "A surreal heist story about memory and identity with a layered sci-fi setup."
            ),
            chips=[
                "Spy story",
                "Heist story",
                "Memory and identity",
                "Surreal",
                "Thoughtful",
                "Plot-driven",
            ],
            best_for=["Heist stories", "Puzzle-like stories"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Heist story"),
            signal_row("audience_expectation", "Spy story"),
            signal_row("topic_theme", "Memory and identity"),
            signal_row("topic_theme", "Spy story"),
            signal_row("mood", "Surreal"),
            signal_row("tone", "Thoughtful"),
            signal_row("pacing", "Plot-driven"),
        ],
    )

    decision_layer = get_content_decision_layer(db, 1)
    chips = decision_layer["watch_profile"]["chips"]
    reasons = decision_layer["decision_support"]["reasons"]

    assert chips[:5] == [
        "Heist story",
        "Memory and identity",
        "Thoughtful",
        "Surreal",
        "Plot-driven",
    ]
    assert "Spy story" not in chips
    assert any("heist story" in reason.lower() for reason in reasons)
    assert any("memory-and-identity" in reason.lower() for reason in reasons)
    assert any("puzzle-like stories" in reason.lower() for reason in reasons)
    assert all("Clear " not in reason for reason in reasons)
    assert all("Good fit for" not in reason for reason in reasons)
    assert all("is part of the watch profile" not in reason for reason in reasons)


def test_decision_display_groups_compact_profile_and_facts():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel=(
                "A surreal heist story about memory and identity with a layered sci-fi setup."
            ),
            chips=[
                "Spy story",
                "Heist story",
                "Memory and identity",
                "Surreal",
                "Thoughtful",
                "Plot-driven",
            ],
            best_for=[
                "Heist stories",
                "Stories about memory and identity",
                "Prime Video viewers",
            ],
            consider_first=["May feel complex on first watch."],
        ),
        signals=[
            signal_row("audience_expectation", "Heist story"),
            signal_row("audience_expectation", "Spy story"),
            signal_row("topic_theme", "Memory and identity"),
            signal_row("topic_theme", "Spy story"),
            signal_row("mood", "Surreal"),
            signal_row("tone", "Thoughtful"),
            signal_row("pacing", "Plot-driven"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(genres=["Fantasy", "Adventure"]),
    )

    display = decision_layer["display"]
    assert_display_has_no_blocked_phrases(display)
    assert display["primary_insight"].startswith("A surreal sci-fi heist")
    assert "memory and identity" in display["primary_insight"].lower()
    assert "strong audience backing" in display["primary_insight"].lower()
    assert "Best suited" not in display["primary_insight"]
    assert len(display["primary_insight"]) <= 180
    assert display["profile"]["identity"] == ["Sci-fi heist"]
    assert "Spy story" not in display["profile"]["identity"]
    assert "Spy story" not in display["profile"]["themes"]
    assert display["profile"]["themes"] == ["Memory and identity"]
    assert display["profile"]["feel"][:2] == ["Surreal", "Thoughtful"]
    assert display["profile"]["pace"] == "Plot-driven and puzzle-like"
    assert display["profile"]["best_for"] == [
        "Heist stories",
        "Stories about memory and identity",
    ]

    facts = display["supporting_facts"]
    assert len(facts) <= 4
    assert {"label": "Audience", "value": "86/100 from 2 scoring sources"} in facts
    assert {"label": "Access", "value": "Streaming in India"} in facts
    assert {
        "label": "Creative lead",
        "value": "Directed by Christopher Nolan",
    } in facts
    assert {"label": "Age rating", "value": "UA"} in facts


def test_decision_display_deduplicates_overlapping_feel_labels():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel=(
                "A political dark fantasy built around power struggles and "
                "foreboding tension."
            ),
            chips=[
                "Fantasy adventure",
                "Dark fantasy",
                "Political power drama",
                "Power struggle",
                "High-stakes",
                "Intense",
                "Tense",
                "Foreboding",
            ],
            best_for=["Political power dramas", "Fantasy adventures"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Dark fantasy"),
            signal_row("topic_theme", "Political power drama"),
            signal_row("topic_theme", "Power struggle"),
            signal_row("mood", "Foreboding"),
            signal_row("tone", "Dark tone"),
            signal_row("intensity", "High-stakes"),
            signal_row("intensity", "Intense"),
            signal_row("pacing", "Slow-burn"),
        ],
    )

    decision_layer = get_content_decision_layer(db, 1)
    profile = decision_layer["display"]["profile"]
    assert_display_has_no_blocked_phrases(decision_layer["display"])

    assert "Political dark fantasy" in profile["identity"]
    assert "Fantasy adventure" not in profile["identity"]
    assert "Power struggle" in profile["themes"]
    assert len(profile["feel"]) <= 2
    assert not {"High-stakes", "Intense"} <= set(profile["feel"])


def test_decision_display_blocks_bad_public_phrases_globally():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A bleak mood complex story built around all themes.",
            chips=[
                "All themes",
                "Complex story",
                "Bleak mood",
                "Heist story",
                "Spy story",
                "Prime Video viewers",
                "JioHotstar viewers",
            ],
            best_for=["Serialized drama viewers", "Availability viewers"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Heist story"),
            signal_row("topic_theme", "Heist story"),
            signal_row("topic_theme", "Spy story"),
            signal_row("topic_theme", "All themes"),
            signal_row("mood", "Bleak mood"),
            signal_row("pacing", "Plot-driven"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(genres=["Science Fiction", "Thriller"]),
    )

    display = decision_layer["display"]
    display_text = str(display).lower()
    assert_display_has_no_blocked_phrases(display)
    for blocked in (
        "all themes",
        "complex story",
        "bleak mood",
        "built around heist story",
        "built around spy story",
        "built around eerie",
        "warm corruption story",
        "heavier watch assassin story",
        "prime video viewers",
        "jiohotstar viewers",
    ):
        assert blocked not in display_text
    assert display["profile"]["identity"][0] == "Sci-fi heist"


def test_decision_display_builds_space_scifi_from_context_without_bad_fallbacks():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A complex story with space, family, and time pressure.",
            chips=[
                "Space sci-fi",
                "Survival",
                "Family",
                "Time",
                "Humanity's future",
                "Emotional",
                "Atmospheric",
                "Complex story",
                "Dystopian future",
            ],
            best_for=["Space sci-fi viewers"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Space sci-fi"),
            signal_row("topic_theme", "Survival"),
            signal_row("topic_theme", "Family"),
            signal_row("topic_theme", "Time"),
            signal_row("topic_theme", "Humanity's future"),
            signal_row("mood", "Emotional"),
            signal_row("tone", "Atmospheric"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(genres=["Science Fiction", "Adventure", "Drama"]),
    )

    display = decision_layer["display"]
    insight = display["primary_insight"].lower()
    assert_display_has_no_blocked_phrases(display)
    assert "space sci-fi" in insight
    assert any(
        theme.lower() in insight
        for theme in ("survival", "family", "time", "humanity's future")
    )
    assert "bleak mood complex story" not in insight
    assert "all themes" not in insight
    assert "complex story built around" not in insight


def test_decision_display_prefers_prison_drama_over_corruption_setting_context():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A warm corruption story built around 1940s setting and hope.",
            chips=[
                "Corruption story",
                "Freedom story",
                "1940s setting",
                "Hope",
                "Friendship",
                "Warm",
                "Cynical",
            ],
            best_for=["Prison drama", "Corruption story"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Corruption story"),
            signal_row("topic_theme", "1940s setting"),
            signal_row("topic_theme", "Hope"),
            signal_row("topic_theme", "Endurance"),
            signal_row("topic_theme", "Friendship"),
            signal_row("tone", "Warm"),
            signal_row("tone", "Cynical"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(
            content={
                "type": "movie",
                "overview": (
                    "A prison inmate endures a long sentence, builds friendship, "
                    "and holds onto hope under a corrupt warden."
                ),
            },
            genres=["Drama"],
            ratings={"unified_score": 94, "scoring_source_count": 2},
        ),
    )

    display = decision_layer["display"]
    insight = display["primary_insight"].lower()
    themes = {theme.lower() for theme in display["profile"]["themes"]}

    assert display["profile"]["identity"][0] == "Prison drama"
    assert insight.startswith("a serious prison drama")
    assert "warm corruption story" not in insight
    assert "1940s setting" not in themes
    assert themes & {"hope", "endurance", "friendship", "institutional corruption"}
    assert "exceptional audience backing" in insight


def test_decision_display_prefers_satirical_scifi_anthology_over_crime_story():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A bleak crime story built around dystopian future.",
            chips=[
                "Crime story",
                "Dystopian future",
                "Bleak",
                "Darkly funny",
            ],
            best_for=["Crime drama viewers", "Dystopian future viewers"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Crime story"),
            signal_row("topic_theme", "Dystopian future"),
            signal_row("mood", "Bleak"),
            signal_row("tone", "Darkly funny"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(
            content={
                "type": "series",
                "overview": (
                    "A satirical anthology about technology, future society, "
                    "surveillance, and moral consequences."
                ),
            },
            genres=["Science Fiction", "Drama"],
        ),
    )

    display = decision_layer["display"]
    insight = display["primary_insight"].lower()
    themes = {theme.lower() for theme in display["profile"]["themes"]}

    assert "sci-fi anthology" in " ".join(display["profile"]["identity"]).lower()
    assert "crime story" not in insight
    assert "technology and society" in themes
    assert "moral consequences" in themes


def test_decision_display_prefers_serial_killer_crime_thriller_without_repetition():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel=(
                "A tense investigation-led mystery built around detective investigation."
            ),
            chips=[
                "Investigation-led mystery",
                "Detective investigation",
                "Serial-killer investigation",
                "Tense",
                "Dark",
            ],
            best_for=["Investigation-led mystery viewers"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Investigation-led mystery"),
            signal_row("topic_theme", "Detective investigation"),
            signal_row("topic_theme", "Serial-killer investigation"),
            signal_row("mood", "Tense"),
            signal_row("tone", "Dark"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(
            content={
                "type": "movie",
                "overview": (
                    "Two detectives hunt a serial killer whose murders follow "
                    "the seven deadly sins."
                ),
            },
            genres=["Crime", "Mystery", "Thriller"],
        ),
    )

    display = decision_layer["display"]
    insight = display["primary_insight"].lower()

    assert any(
        identity in " ".join(display["profile"]["identity"]).lower()
        for identity in ("neo-noir crime thriller", "serial-killer investigation")
    )
    assert "built around detective investigation" not in insight
    assert "serial-killer investigation" in insight


def test_decision_display_prefers_action_crime_investigation_over_assassin_story():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel=(
                "A heavier watch assassin story built around police investigation."
            ),
            chips=[
                "Assassin story",
                "Police investigation",
                "Heavier watch",
                "Action-heavy",
            ],
            best_for=["Assassin Story", "Police Investigation"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Assassin story"),
            signal_row("topic_theme", "Police investigation"),
            signal_row("topic_theme", "Corruption"),
            signal_row("pacing", "Action-heavy"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(
            content={
                "type": "series",
                "overview": (
                    "A drifter and former military police investigator uncovers "
                    "a local conspiracy and corruption."
                ),
            },
            genres=["Action", "Crime", "Drama"],
        ),
    )

    display = decision_layer["display"]
    display_text = str(display).lower()

    assert "action-crime investigation" in " ".join(
        display["profile"]["identity"]
    ).lower()
    assert "assassin story" not in display_text
    assert "heavier watch assassin story" not in display_text
    assert "heavier watch" not in display["primary_insight"].lower()


def test_decision_display_avoids_repeated_investigation_phrasing():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A tense investigation-led mystery built around federal investigation.",
            chips=["Investigation-led mystery", "Federal investigation", "Tense"],
            best_for=["Investigation-led mystery viewers"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Investigation-led mystery"),
            signal_row("topic_theme", "Federal investigation"),
            signal_row("topic_theme", "Conspiracy"),
            signal_row("mood", "Tense"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(
            content={
                "type": "series",
                "overview": (
                    "A federal agent uncovers conspiracy, surveillance, "
                    "and government secrecy under political pressure."
                ),
            },
            genres=["Action", "Thriller", "Mystery"],
        ),
    )

    display = decision_layer["display"]
    insight = display["primary_insight"].lower()
    themes = {theme.lower() for theme in display["profile"]["themes"]}

    assert "investigation built around federal investigation" not in insight
    assert "investigation-led mystery built around federal investigation" not in insight
    assert "federal investigation" not in themes
    assert themes & {"conspiracy", "federal pressure", "government secrecy"}
    assert display["profile"]["themes"]


def test_decision_display_keeps_action_crime_themes_without_police_repetition():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A heavier watch assassin story built around police investigation.",
            chips=["Assassin story", "Police investigation", "Military background"],
            best_for=["Police Investigation"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Assassin story"),
            signal_row("topic_theme", "Police investigation"),
            signal_row("topic_theme", "Lone investigator"),
            signal_row("topic_theme", "Military background"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(
            content={
                "type": "series",
                "overview": (
                    "An ex-military drifter investigates local corruption and conspiracy "
                    "with a military police background."
                ),
            },
            genres=["Action", "Crime", "Thriller"],
        ),
    )

    display = decision_layer["display"]
    insight = display["primary_insight"].lower()
    themes = {theme.lower() for theme in display["profile"]["themes"]}

    assert "investigation series built around police investigation" not in insight
    assert "police investigation" not in themes
    assert themes & {"lone investigator", "military background", "conspiracy"}


def test_decision_display_keeps_eerie_as_feel_for_survival_thriller():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A tense psychological thriller built around eerie.",
            chips=[
                "Psychological thriller",
                "Survival",
                "Trauma",
                "Group collapse",
                "Past consequences",
                "Eerie",
                "Tense",
            ],
            best_for=["Psychological thriller", "Survival mystery"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Psychological thriller"),
            signal_row("topic_theme", "Eerie"),
            signal_row("topic_theme", "Survival"),
            signal_row("topic_theme", "Trauma"),
            signal_row("mood", "Eerie"),
            signal_row("tone", "Tense"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(
            content={
                "type": "series",
                "overview": (
                    "After a plane crash in the wilderness, the group faces "
                    "survival, trauma, group collapse, and past consequences."
                ),
            },
            genres=["Drama", "Mystery", "Horror"],
        ),
    )

    display = decision_layer["display"]
    insight = display["primary_insight"].lower()
    themes = {theme.lower() for theme in display["profile"]["themes"]}

    assert display["profile"]["identity"][0] == "Psychological survival thriller"
    assert "built around eerie" not in insight
    assert "eerie" in {feel.lower() for feel in display["profile"]["feel"]}
    assert "eerie" not in themes
    assert themes & {"survival", "trauma", "group collapse", "past consequences"}


def test_decision_display_can_infer_mythic_superhero_mystery():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A superhero story built around comic-book roots.",
            chips=[
                "Superhero story",
                "Mystery",
                "Identity conflict",
                "Mythology",
                "Action-heavy",
            ],
            best_for=["Superhero story viewers"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Superhero story"),
            signal_row("topic_theme", "Identity conflict"),
            signal_row("topic_theme", "Mythology"),
            signal_row("pacing", "Action-heavy"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(
            content={
                "type": "series",
                "overview": (
                    "A hero with blackouts and fractured identities is drawn "
                    "into Egyptian gods and mythology."
                ),
            },
            genres=["Fantasy", "Mystery", "Action"],
        ),
    )

    display = decision_layer["display"]

    assert display["profile"]["identity"][0] == "Mythic superhero mystery"
    assert "identity conflict" in {
        theme.lower() for theme in display["profile"]["themes"]
    }
    assert "mythology" in {theme.lower() for theme in display["profile"]["themes"]}


def test_decision_display_normalizes_repeated_tone_phrasing_for_historical_drama():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A serious tone historical drama with a serious tone tone.",
            chips=["Historical drama", "Serious tone"],
            best_for=["Historical dramas"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Historical drama"),
            signal_row("tone", "Serious tone"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(
            content={
                "type": "movie",
                "overview": (
                    "A scientist leads the Manhattan Project and confronts "
                    "nuclear war, political consequence, and moral responsibility."
                ),
            },
            genres=["Drama", "History"],
        ),
    )

    display = decision_layer["display"]
    insight = display["primary_insight"].lower()
    themes = {theme.lower() for theme in display["profile"]["themes"]}

    for blocked in (
        "tone tone",
        "mood mood",
        "serious tone historical drama with a serious tone tone",
    ):
        assert blocked not in insight
    assert insight.startswith("a serious historical drama")
    assert themes & {
        "scientific ambition",
        "moral responsibility",
        "political consequence",
        "war",
    }


def test_decision_display_adds_war_drama_theme_fallbacks():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A serious tone war story.",
            chips=["War story", "World War II dramas", "Serious tone"],
            best_for=["World War II dramas"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "War story"),
            signal_row("tone", "Serious tone"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(
            content={
                "type": "movie",
                "overview": (
                    "World War II soldiers face occupation, survival, duty, "
                    "and the human cost of war."
                ),
            },
            genres=["Drama", "History", "War"],
        ),
    )

    display = decision_layer["display"]
    insight = display["primary_insight"].lower()
    themes = {theme.lower() for theme in display["profile"]["themes"]}

    assert "tone tone" not in insight
    assert themes & {"war", "human cost", "survival", "institutional cruelty", "duty"}
    assert "world war ii dramas" in {
        label.lower() for label in display["profile"]["best_for"]
    }


def test_decision_display_adds_historical_war_themes_when_theme_signals_are_empty():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A serious historical drama.",
            chips=["Historical drama", "Serious tone"],
            best_for=["Historical dramas"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Historical drama"),
            signal_row("tone", "Serious tone"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(
            content={
                "type": "movie",
                "overview": (
                    "World War II occupation, Nazi cruelty, soldiers, survival, "
                    "and the human cost of war shape the story."
                ),
            },
            genres=["Drama", "History", "War"],
        ),
    )

    display = decision_layer["display"]
    insight = display["primary_insight"].lower()
    themes = {theme.lower() for theme in display["profile"]["themes"]}

    assert "serious historical drama, with" not in insight
    assert "tone tone" not in insight
    assert themes & {
        "war",
        "human cost",
        "survival",
        "duty",
        "institutional cruelty",
    }


def test_decision_display_adds_gangster_crime_theme_fallbacks():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A dark tone gangster crime story with a dark tone tone.",
            chips=["Gangster crime story", "Offbeat comedy", "Dark tone"],
            best_for=["Offbeat comedy viewers", "Gangster crime story"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Gangster crime story"),
            signal_row("tone", "Dark tone"),
            signal_row("tone", "Darkly funny"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(
            content={
                "type": "movie",
                "overview": (
                    "Gangsters, a hitman, loyalty, violence, and moral chaos "
                    "collide inside organized crime."
                ),
            },
            genres=["Crime", "Thriller"],
        ),
    )

    display = decision_layer["display"]
    insight = display["primary_insight"].lower()
    themes = {theme.lower() for theme in display["profile"]["themes"]}

    assert "dark tone tone" not in insight
    assert "gangster crime story" in insight
    assert "darkly funny" in insight or "dark" in insight
    assert themes & {"crime", "loyalty", "moral chaos", "violence"}
    assert "offbeat comedies" in {
        label.lower() for label in display["profile"]["best_for"]
    }


def test_decision_display_adds_space_survival_themes_and_specific_caution():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A space survival drama.",
            chips=["Space sci-fi", "Survival", "Resourcefulness"],
            best_for=["Space sci-fi viewers", "Survival stories"],
            consider_first=[
                "Better suited for viewers comfortable with darker or more intense stories."
            ],
        ),
        signals=[
            signal_row("audience_expectation", "Space survival drama"),
            signal_row("intensity", "High-stakes"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(
            content={
                "type": "movie",
                "overview": (
                    "An astronaut stranded on Mars uses resourcefulness, isolation, "
                    "and survival instincts while humanity plans a rescue."
                ),
            },
            genres=["Science Fiction", "Adventure", "Drama"],
        ),
    )

    display = decision_layer["display"]
    themes = {theme.lower() for theme in display["profile"]["themes"]}
    caution = " ".join(display["profile"]["consider_first"]).lower()

    assert themes & {"survival", "resourcefulness", "isolation", "humanity's future"}
    assert "better suited for viewers comfortable" not in caution
    assert caution
    assert "a space survival drama, with positive audience backing" not in display[
        "primary_insight"
    ].lower()


def test_decision_display_adds_heist_and_spy_theme_fallbacks():
    heist_db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A heist story.",
            chips=["Heist story", "Plot-driven"],
            best_for=["Heist stories"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Heist story"),
            signal_row("pacing", "Plot-driven"),
        ],
    )

    heist_layer = get_content_decision_layer(heist_db, 1)
    heist_themes = {
        theme.lower() for theme in heist_layer["display"]["profile"]["themes"]
    }

    assert heist_themes & {"planning", "deception", "pressure"}
    assert "built around heist story" not in heist_layer["display"][
        "primary_insight"
    ].lower()

    spy_db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A spy story.",
            chips=["Spy story", "Plot-driven"],
            best_for=["Spy thrillers"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Spy story"),
            signal_row("pacing", "Plot-driven"),
        ],
    )

    spy_layer = get_content_decision_layer(
        spy_db,
        1,
        display_context=display_context(
            content={"type": "movie", "overview": "MI5 espionage and intelligence work."},
            genres=["Thriller"],
        ),
    )
    spy_themes = {theme.lower() for theme in spy_layer["display"]["profile"]["themes"]}

    assert spy_themes & {"espionage", "betrayal", "intelligence work"}
    assert "built around spy story" not in spy_layer["display"][
        "primary_insight"
    ].lower()


def test_decision_display_normalizes_post_apocalyptic_best_for_label():
    db = FakeDecisionDb(
        guidance=guidance_row(
            watch_feel="A high-adrenaline post-apocalyptic survival story.",
            chips=["Survival story", "High-adrenaline"],
            best_for=["Post-apocalyptic World", "Survival stories"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Survival story"),
            signal_row("topic_theme", "Survival"),
            signal_row("mood", "High-adrenaline"),
        ],
    )

    decision_layer = get_content_decision_layer(db, 1)
    best_for = decision_layer["display"]["profile"]["best_for"]

    assert "Post-apocalyptic World" not in best_for
    assert "Post-apocalyptic worlds" in best_for


def test_decision_display_does_not_repeat_feel_as_tone_clause():
    for identity, feel, bad_phrase in [
        ("Disaster story", "Emotional", "emotional disaster story with a emotional tone"),
        ("Supernatural story", "Eerie", "eerie supernatural story with a eerie tone"),
    ]:
        db = FakeDecisionDb(
            guidance=guidance_row(
                watch_feel=f"An {feel.lower()} {identity.lower()} with a {feel.lower()} tone.",
                chips=[identity, feel],
                best_for=[],
                consider_first=[],
            ),
            signals=[
                signal_row("audience_expectation", identity),
                signal_row("mood", feel),
            ],
        )

        decision_layer = get_content_decision_layer(db, 1)
        insight = decision_layer["display"]["primary_insight"].lower()

        assert bad_phrase not in insight
        assert "tone tone" not in insight
        assert "mood mood" not in insight


def test_decision_display_uses_specific_cautions_for_complex_and_dark_profiles():
    complex_db = FakeDecisionDb(
        guidance=guidance_row(
            chips=["Heist story", "Memory and identity", "Plot-driven"],
            consider_first=[
                "Better suited for viewers comfortable with darker or more intense stories."
            ],
        ),
        signals=[
            signal_row("audience_expectation", "Heist story"),
            signal_row("topic_theme", "Memory and identity"),
            signal_row("pacing", "Plot-driven"),
        ],
    )
    complex_layer = get_content_decision_layer(complex_db, 1)
    assert complex_layer["display"]["profile"]["consider_first"] == [
        "Dense or unusual structure may require attention."
    ]

    dark_db = FakeDecisionDb(
        guidance=guidance_row(
            chips=["Dark fantasy", "Power struggle", "Foreboding"],
            consider_first=[
                "Better suited for viewers comfortable with darker or more intense stories."
            ],
        ),
        signals=[
            signal_row("audience_expectation", "Dark fantasy"),
            signal_row("topic_theme", "Power struggle"),
            signal_row("mood", "Foreboding"),
            signal_row("intensity", "High-stakes"),
        ],
    )
    dark_layer = get_content_decision_layer(dark_db, 1)
    cautions = dark_layer["display"]["profile"]["consider_first"]
    assert cautions == ["Sustained tension may feel heavy for casual viewing."]
    assert len(cautions) <= 2


def test_decision_display_removes_platform_identity_but_keeps_access_fact():
    db = FakeDecisionDb(
        guidance=guidance_row(
            chips=["JioHotstar viewers", "Fantasy story viewers", "Warm"],
            best_for=["Netflix viewers", "Fantasy adventure viewers"],
            consider_first=[],
        ),
        signals=[
            signal_row("audience_expectation", "Fantasy story"),
            signal_row("mood", "Warm"),
        ],
    )

    decision_layer = get_content_decision_layer(
        db,
        1,
        display_context=display_context(),
    )

    display_text = str(decision_layer["display"]).lower()
    assert "jiohotstar viewers" not in display_text
    assert "netflix viewers" not in display_text
    assert "prime video viewers" not in display_text
    assert "fantasy" in " ".join(
        decision_layer["display"]["profile"]["identity"]
    ).lower()
    assert {"label": "Access", "value": "Streaming in India"} in decision_layer[
        "display"
    ]["supporting_facts"]


def test_decision_display_does_not_expose_internal_terms():
    db = FakeDecisionDb(
        guidance=guidance_row(),
        signals=[
            signal_row("tone", "Tense"),
            signal_row("topic_theme", "source_signal debug"),
            signal_row("mood", "mapping_version"),
        ],
    )

    decision_layer = get_content_decision_layer(db, 1)
    display_text = str(decision_layer["display"]).lower()

    for blocked in (
        "keyword",
        "tmdb_keywords",
        "source_names",
        "mapping_version",
        "provider",
        "confidence",
        "source_signal",
    ):
        assert blocked not in display_text


def test_decision_layer_returns_none_without_guidance_or_signals():
    assert get_content_decision_layer(FakeDecisionDb(), 1) is None


def test_decision_layer_does_not_expose_technical_fields_by_default():
    db = FakeDecisionDb(
        guidance=guidance_row(),
        signals=[signal_row("tone", "Tense")],
    )

    decision_layer = get_content_decision_layer(db, 1)
    public_text = str(decision_layer).lower()

    assert "keyword_counts" not in decision_layer
    assert "debug" not in decision_layer
    assert "mapping_version" not in public_text
    assert "source_names" not in public_text
    assert "tmdb_keywords" not in public_text
    assert "confidence" not in public_text
    assert "provider" not in public_text
