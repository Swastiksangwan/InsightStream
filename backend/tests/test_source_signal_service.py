from app.services.source_signal_service import (
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
                "A surreal heist story about memory and identity with a layered setup."
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
                "A surreal heist story about memory and identity with a layered setup."
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
        display_context=display_context(),
    )

    display = decision_layer["display"]
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

    assert "Political dark fantasy" in profile["identity"]
    assert "Fantasy adventure" not in profile["identity"]
    assert "Power struggle" in profile["themes"]
    assert len(profile["feel"]) <= 2
    assert not {"High-stakes", "Intense"} <= set(profile["feel"])


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
    assert "fantasy story" in " ".join(
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
