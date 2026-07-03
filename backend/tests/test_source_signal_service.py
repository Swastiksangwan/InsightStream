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
    assert decision_layer["decision_support"]["reasons"]
    assert decision_layer["decision_support"]["cautions"]
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

    assert decision_layer["watch_profile"]["chips"] == [
        "Dark fantasy",
        "Political power drama",
        "Power struggle",
    ]


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
