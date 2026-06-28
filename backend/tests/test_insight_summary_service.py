from app.services.insight_summary_service import (
    UNSUPPORTED_MARKETING_PHRASES,
    build_insight_summary,
)


def base_content(**overrides):
    content = {
        "id": 1,
        "title": "Example",
        "type": "movie",
        "overview": "A focused story built from local metadata.",
        "poster": None,
        "backdrop": None,
        "release_date": None,
        "year": 2023,
        "runtime": 180,
        "language": "en",
        "age_rating": "UA",
    }
    content.update(overrides)
    return content


def ratings(score=84):
    return {
        "unified_score": score,
        "source_count": 1,
        "scoring_source_count": 1,
        "sources": [
            {
                "source_name": "tmdb",
                "display_name": "TMDb",
                "source_category": "audience",
                "normalized_score": score,
                "vote_count": 1000,
            }
        ],
    }


def no_ratings():
    return {
        "unified_score": None,
        "source_count": 0,
        "scoring_source_count": 0,
        "sources": [],
    }


def availability(availability_type="streaming", region_code="IN"):
    return [
        {
            "name": "Example Platform",
            "availability_type": availability_type,
            "region_code": region_code,
        }
    ]


def credits(director=None, creator=None):
    return {
        "content_id": 1,
        "cast": [
            {
                "person_id": 10,
                "name": "Example Actor",
                "character_name": "Lead",
            }
        ],
        "directors": (
            [
                {
                    "person_id": 20,
                    "name": director,
                    "job": "Director",
                    "department": "Directing",
                }
            ]
            if director
            else []
        ),
        "creators": (
            [
                {
                    "person_id": 30,
                    "name": creator,
                    "job": "Creator",
                    "department": "Writing",
                }
            ]
            if creator
            else []
        ),
        "crew": [],
    }


def labels(summary):
    return {signal["label"] for signal in summary["key_signals"]}


def combined_text(summary):
    parts = [
        summary.get("headline") or "",
        summary.get("summary") or "",
        summary.get("watch_note") or "",
    ]
    parts.extend(summary.get("best_for") or [])
    parts.extend(signal["value"] for signal in summary.get("key_signals") or [])
    return " ".join(parts).lower()


def assert_no_unsupported_marketing(summary):
    text = combined_text(summary)
    for phrase in UNSUPPORTED_MARKETING_PHRASES:
        assert phrase not in text


def assert_clean_chips(summary):
    for chip in summary["best_for"]:
        assert " And " not in chip
        assert ", and" not in chip
        assert len(chip) <= 36


def test_movie_with_rich_metadata_gets_non_empty_insight_summary():
    summary = build_insight_summary(
        {
            "content": base_content(title="Oppenheimer"),
            "genres": ["Drama", "History"],
            "platforms": availability("rent"),
            "ratings": ratings(84),
            "series_metadata": None,
            "credits": credits(director="Christopher Nolan"),
        }
    )

    assert summary["headline"]
    assert summary["summary"]
    assert 2 <= len(summary["best_for"]) <= 4
    assert {
        "Audience",
        "Access",
        "Runtime",
        "Creative lead",
    } <= labels(summary)
    assert "focused watch session" in summary["watch_note"]
    assert summary["confidence"] == "high"
    assert_clean_chips(summary)
    assert_no_unsupported_marketing(summary)


def test_ongoing_series_gets_series_aware_signals():
    summary = build_insight_summary(
        {
            "content": base_content(
                title="Example Series",
                type="series",
                runtime=None,
            ),
            "genres": ["Comedy", "Drama"],
            "platforms": availability("streaming"),
            "ratings": ratings(82),
            "series_metadata": {
                "series_status_normalized": "ongoing",
                "released_seasons_count": 4,
                "next_episode_air_date": "2026-07-10",
            },
            "credits": credits(creator="Example Creator"),
        }
    )

    assert summary["headline"]
    assert "ongoing" in combined_text(summary)
    assert {
        "Audience",
        "Access",
        "Watch fit",
        "Series status",
        "Creative lead",
    } <= labels(summary)
    assert "Ongoing release followers" in summary["best_for"]
    assert "Best for viewers" in summary["watch_note"]
    assert "wait if you prefer completed seasons" in summary["watch_note"]
    assert_clean_chips(summary)
    assert_no_unsupported_marketing(summary)


def test_ended_series_avoids_upcoming_signals_when_missing():
    summary = build_insight_summary(
        {
            "content": base_content(type="series", runtime=None),
            "genres": ["Crime", "Drama"],
            "platforms": [],
            "ratings": ratings(88),
            "series_metadata": {
                "series_status_normalized": "ended",
                "released_seasons_count": 5,
                "next_episode_air_date": None,
                "next_season_number": None,
            },
            "credits": credits(creator="Example Creator"),
        }
    )

    assert "completed" in combined_text(summary)
    assert "Series status" in labels(summary)
    assert "upcoming" not in combined_text(summary)
    assert "next episode" not in combined_text(summary)
    assert "next season" not in combined_text(summary)
    assert summary["watch_note"]
    assert any(
        phrase in summary["watch_note"].lower()
        for phrase in ("finished binge", "completed", "binge")
    )


def test_no_rating_content_does_not_claim_rating_strength():
    summary = build_insight_summary(
        {
            "content": base_content(),
            "genres": ["Drama"],
            "platforms": availability("streaming"),
            "ratings": no_ratings(),
            "series_metadata": None,
            "credits": credits(director="Example Director"),
        }
    )

    assert "Audience" not in labels(summary)
    text = combined_text(summary)
    assert "high-rated" not in text
    assert "strong audience" not in text
    assert "mixed-to-positive" not in text


def test_no_availability_content_does_not_claim_availability():
    summary = build_insight_summary(
        {
            "content": base_content(),
            "genres": ["Drama"],
            "platforms": [],
            "ratings": ratings(78),
            "series_metadata": None,
            "credits": credits(director="Example Director"),
        }
    )

    assert "Access" not in labels(summary)
    assert "availability" not in combined_text(summary)


def test_rent_buy_movie_mentions_rent_buy_watch_guidance():
    summary = build_insight_summary(
        {
            "content": base_content(runtime=110),
            "genres": ["Drama"],
            "platforms": availability("rent"),
            "ratings": ratings(76),
            "series_metadata": None,
            "credits": credits(director="Example Director"),
        }
    )

    assert "Access" in labels(summary)
    assert any(
        signal["label"] == "Access" and "Rent/buy" in signal["value"]
        for signal in summary["key_signals"]
    )
    assert summary["watch_note"]
    assert "renting or buying" in summary["watch_note"]


def test_summary_access_text_avoids_duplicate_platform_variants():
    summary = build_insight_summary(
        {
            "content": base_content(runtime=110),
            "genres": ["Action", "Adventure"],
            "platforms": [
                {
                    "name": "Amazon Prime Video",
                    "availability_type": "streaming",
                    "region_code": "IN",
                },
                {
                    "name": "Amazon Prime Video with Ads",
                    "availability_type": "streaming",
                    "region_code": "IN",
                },
                {
                    "name": "Apple TV Amazon Channel",
                    "availability_type": "streaming",
                    "region_code": "IN",
                },
                {
                    "name": "Netflix",
                    "availability_type": "streaming",
                    "region_code": "IN",
                },
            ],
            "ratings": ratings(82),
            "series_metadata": None,
            "credits": credits(director="Example Director"),
        }
    )

    access_value = next(
        signal["value"]
        for signal in summary["key_signals"]
        if signal["label"] == "Access"
    )

    assert access_value == "Streaming in India on Amazon Prime Video, Apple TV + more"
    assert "Amazon Prime Video with Ads" not in combined_text(summary)
    assert "Apple TV Amazon Channel" not in combined_text(summary)


def test_summary_rating_signal_uses_scoring_source_count_not_displayed_sources():
    summary = build_insight_summary(
        {
            "content": base_content(runtime=110),
            "genres": ["Drama"],
            "platforms": availability("streaming"),
            "ratings": {
                "unified_score": 79,
                "source_count": 3,
                "scoring_source_count": 2,
                "sources": [
                    {
                        "source_name": "tmdb",
                        "display_name": "TMDb",
                        "source_category": "audience",
                        "normalized_score": 78,
                        "vote_count": 5000,
                    },
                    {
                        "source_name": "imdb",
                        "display_name": "IMDb",
                        "source_category": "audience",
                        "normalized_score": 80,
                        "vote_count": 250000,
                    },
                    {
                        "source_name": "letterboxd",
                        "display_name": "Letterboxd",
                        "source_category": "audience",
                        "normalized_score": 96,
                        "vote_count": None,
                    },
                ],
            },
            "series_metadata": None,
            "credits": credits(director="Example Director"),
        }
    )

    audience_signal = next(
        signal["value"]
        for signal in summary["key_signals"]
        if signal["label"] == "Audience"
    )

    assert "2 scoring sources" in audience_signal
    assert "3 rating sources" not in audience_signal
    assert "Letterboxd" not in audience_signal


def test_no_crew_content_does_not_claim_director_or_creator():
    summary = build_insight_summary(
        {
            "content": base_content(),
            "genres": ["Drama"],
            "platforms": availability("streaming"),
            "ratings": ratings(78),
            "series_metadata": None,
            "credits": {"cast": [], "directors": [], "creators": [], "crew": []},
        }
    )

    assert "Creative lead" not in labels(summary)
    assert "fans" not in combined_text(summary)


def test_sparse_content_returns_stable_low_confidence_shape():
    summary = build_insight_summary(
        {
            "content": base_content(
                overview=None,
                runtime=None,
                age_rating=None,
            ),
            "genres": [],
            "platforms": [],
            "ratings": no_ratings(),
            "series_metadata": None,
            "credits": {"cast": [], "directors": [], "creators": [], "crew": []},
        }
    )

    assert summary == {
        "headline": None,
        "summary": None,
        "best_for": [],
        "key_signals": [],
        "watch_note": None,
        "generated_from": [],
        "confidence": "low",
    }
