from urllib.parse import quote

import pytest
from sqlalchemy import text

from app.services.content_service import (
    MINIMUM_VOTE_COUNT_FOR_UNIFIED_SCORE,
    get_detail_ratings,
)


MIN_SEED_TOTAL = 15
MIN_SEED_MOVIE_TOTAL = 8
MIN_SEED_SERIES_TOTAL = 7


class FakeRatingsResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeRatingsDb:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _query, _params):
        return FakeRatingsResult(self.rows)


def fake_rating_row(
    normalized_score=84,
    vote_count=MINIMUM_VOTE_COUNT_FOR_UNIFIED_SCORE,
    source_name="tmdb",
    display_name="TMDb",
    weight=1,
    rating_url=None,
    raw_score=None,
    raw_score_scale=10,
):
    if raw_score is None and normalized_score is not None:
        raw_score = normalized_score / 10
    return {
        "source_name": source_name,
        "display_name": display_name,
        "source_category": "audience",
        "weight": weight,
        "raw_score": raw_score,
        "raw_score_scale": raw_score_scale,
        "normalized_score": normalized_score,
        "vote_count": vote_count,
        "rating_count_label": None,
        "rating_url": rating_url,
        "fetched_at": None,
    }


def titles_from_items(response_json):
    return {item["title"] for item in response_json["items"]}


def expected_recent_titles(db_session, limit, content_type=None):
    params = {"limit": limit}
    content_type_filter = ""
    if content_type:
        content_type_filter = "AND content_type = :content_type"
        params["content_type"] = content_type

    rows = db_session.execute(
        text(
            f"""
            SELECT title
            FROM content
            WHERE COALESCE(latest_activity_date, release_date) IS NOT NULL
              {content_type_filter}
            ORDER BY COALESCE(latest_activity_date, release_date) DESC, title ASC
            LIMIT :limit;
            """
        ),
        params,
    ).mappings().all()
    return [row["title"] for row in rows]


def expected_discover_recent_titles(db_session, limit):
    rows = db_session.execute(
        text(
            """
            SELECT title
            FROM content
            ORDER BY COALESCE(latest_activity_date, release_date) DESC, title ASC
            LIMIT :limit;
            """
        ),
        {"limit": limit},
    ).mappings().all()
    return [row["title"] for row in rows]


def recent_content_count(db_session, content_type=None):
    params = {}
    content_type_filter = ""
    if content_type:
        content_type_filter = "AND content_type = :content_type"
        params["content_type"] = content_type

    row = db_session.execute(
        text(
            f"""
            SELECT COUNT(*) AS total
            FROM content
            WHERE COALESCE(latest_activity_date, release_date) IS NOT NULL
              {content_type_filter};
            """
        ),
        params,
    ).mappings().first()
    return row["total"]


def optional_content_id_by_title(db_session, title):
    row = db_session.execute(
        text("SELECT id FROM content WHERE title = :title;"),
        {"title": title},
    ).mappings().first()
    return row["id"] if row else None


def content_ids_for_genre(db_session, genre_name):
    rows = db_session.execute(
        text(
            """
            SELECT c.id
            FROM content c
            JOIN content_genres cg ON cg.content_id = c.id
            JOIN genres g ON g.id = cg.genre_id
            WHERE g.name ILIKE :genre_name;
            """
        ),
        {"genre_name": genre_name},
    ).mappings().all()
    return {row["id"] for row in rows}


def first_region_aware_platform(db_session):
    return db_session.execute(
        text(
            """
            SELECT
                p.name,
                ca.availability_type,
                ca.region_code,
                COUNT(DISTINCT ca.content_id) AS total_content
            FROM content_availability ca
            JOIN platforms p ON p.id = ca.platform_id
            WHERE ca.region_code = 'IN'
            GROUP BY p.name, ca.availability_type, ca.region_code
            ORDER BY
                CASE p.name
                    WHEN 'Apple TV' THEN 1
                    WHEN 'JioHotstar' THEN 2
                    ELSE 3
                END,
                total_content DESC,
                p.name ASC,
                ca.availability_type ASC
            LIMIT 1;
            """
        )
    ).mappings().first()


def content_ids_for_platform_filter(
    db_session,
    platform_name,
    availability_type=None,
    region="IN",
):
    params = {
        "platform": platform_name,
        "region": region,
    }
    availability_filter = ""
    legacy_availability_filter = ""
    if availability_type:
        availability_filter = "AND ca.availability_type = :availability_type"
        legacy_availability_filter = "AND cp.availability_type = :availability_type"
        params["availability_type"] = availability_type

    rows = db_session.execute(
        text(
            f"""
            SELECT c.id
            FROM content c
            WHERE (
                EXISTS (
                    SELECT 1
                    FROM content_availability ca
                    JOIN platforms p_av ON p_av.id = ca.platform_id
                    WHERE ca.content_id = c.id
                      AND ca.region_code = :region
                      AND p_av.name ILIKE :platform
                      {availability_filter}
                )
                OR (
                    NOT EXISTS (
                        SELECT 1
                        FROM content_availability ca_existing
                        WHERE ca_existing.content_id = c.id
                          AND ca_existing.region_code = :region
                    )
                    AND EXISTS (
                        SELECT 1
                        FROM content_platforms cp
                        JOIN platforms p_legacy ON p_legacy.id = cp.platform_id
                        WHERE cp.content_id = c.id
                          AND p_legacy.name ILIKE :platform
                          {legacy_availability_filter}
                    )
                )
            );
            """
        ),
        params,
    ).mappings().all()
    return {row["id"] for row in rows}


def has_region_aware_availability(db_session, content_id):
    row = db_session.execute(
        text(
            """
            SELECT COUNT(*) AS total
            FROM content_availability
            WHERE content_id = :content_id;
            """
        ),
        {"content_id": content_id},
    ).mappings().first()
    return row["total"] > 0


def first_content_with_imported_rating(db_session):
    return db_session.execute(
        text(
            """
            SELECT
                c.id,
                c.title,
                rs.source_name,
                rs.display_name,
                cr.raw_score,
                cr.raw_score_scale,
                cr.normalized_score,
                cr.vote_count
            FROM content_ratings cr
            JOIN content c ON c.id = cr.content_id
            JOIN rating_sources rs ON rs.id = cr.rating_source_id
            WHERE rs.is_active = TRUE
            ORDER BY c.id ASC, rs.source_name ASC
            LIMIT 1;
            """
        )
    ).mappings().first()


def first_content_without_imported_rating(db_session):
    return db_session.execute(
        text(
            """
            SELECT c.id, c.title
            FROM content c
            WHERE NOT EXISTS (
                SELECT 1
                FROM content_ratings cr
                WHERE cr.content_id = c.id
            )
            ORDER BY c.id ASC
            LIMIT 1;
            """
        )
    ).mappings().first()


def first_in_certification_conflict(db_session):
    return db_session.execute(
        text(
            """
            SELECT
                c.id,
                c.title,
                c.age_rating AS stored_age_rating,
                cc.certification AS certification,
                cc.country_code,
                cc.source_name,
                cc.rating_system
            FROM content c
            JOIN content_certifications cc
                ON cc.content_id = c.id
               AND cc.country_code = 'IN'
            WHERE c.age_rating IS NOT NULL
              AND c.age_rating <> ''
              AND c.age_rating <> cc.certification
            ORDER BY c.title
            LIMIT 1;
            """
        )
    ).mappings().first()


def first_us_only_certification(db_session):
    return db_session.execute(
        text(
            """
            SELECT
                c.id,
                c.title,
                c.age_rating AS stored_age_rating,
                cc.certification AS certification,
                cc.country_code,
                cc.source_name,
                cc.rating_system
            FROM content c
            JOIN content_certifications cc
                ON cc.content_id = c.id
               AND cc.country_code = 'US'
            WHERE NOT EXISTS (
                SELECT 1
                FROM content_certifications cci
                WHERE cci.content_id = c.id
                  AND cci.country_code = 'IN'
            )
            ORDER BY c.title
            LIMIT 1;
            """
        )
    ).mappings().first()


def first_legacy_age_rating_only(db_session):
    return db_session.execute(
        text(
            """
            SELECT id, title, age_rating
            FROM content c
            WHERE c.age_rating IS NOT NULL
              AND c.age_rating <> ''
              AND NOT EXISTS (
                  SELECT 1
                  FROM content_certifications cc
                  WHERE cc.content_id = c.id
              )
            ORDER BY c.title
            LIMIT 1;
            """
        )
    ).mappings().first()


def first_series_with_lifecycle_metadata(db_session):
    return db_session.execute(
        text(
            """
            SELECT
                c.id,
                c.title,
                csm.number_of_seasons,
                csm.series_status_normalized,
                csm.released_seasons_count,
                csm.has_announced_season
            FROM content c
            JOIN content_series_metadata csm ON csm.content_id = c.id
            WHERE c.content_type = 'series'
            ORDER BY c.title
            LIMIT 1;
            """
        )
    ).mappings().first()


def first_content_with_watch_guidance(db_session):
    return db_session.execute(
        text(
            """
            SELECT c.id, c.title
            FROM content c
            JOIN content_watch_guidance cwg ON cwg.content_id = c.id
            ORDER BY c.id ASC
            LIMIT 1;
            """
        )
    ).mappings().first()


def first_content_without_watch_guidance(db_session):
    return db_session.execute(
        text(
            """
            SELECT c.id, c.title
            FROM content c
            WHERE NOT EXISTS (
                SELECT 1
                FROM content_watch_guidance cwg
                WHERE cwg.content_id = c.id
            )
            ORDER BY c.id ASC
            LIMIT 1;
            """
        )
    ).mappings().first()


def test_get_content_returns_seed_or_larger_catalog(client):
    response = client.get("/content?limit=20")
    data = response.json()

    assert response.status_code == 200
    assert data["total"] >= MIN_SEED_TOTAL
    assert len(data["items"]) == min(data["total"], data["limit"])
    assert data["limit"] == 20
    assert data["offset"] == 0

    if data["total"] <= data["limit"]:
        assert {
            "Interstellar",
            "Inception",
            "The Dark Knight",
            "The Last of Us",
        } <= titles_from_items(data)


def test_get_content_filters_movies(client):
    response = client.get("/content?content_type=movie&limit=20")
    data = response.json()

    assert response.status_code == 200
    assert data["total"] >= MIN_SEED_MOVIE_TOTAL
    assert len(data["items"]) == min(data["total"], data["limit"])
    assert all(item["type"] == "movie" for item in data["items"])

    if data["total"] <= data["limit"]:
        assert {
            "Dune: Part Two",
            "Barbie",
            "Inception",
        } <= titles_from_items(data)


def test_get_content_filters_series(client):
    response = client.get("/content?content_type=series&limit=20")
    data = response.json()

    assert response.status_code == 200
    assert data["total"] >= MIN_SEED_SERIES_TOTAL
    assert len(data["items"]) == min(data["total"], data["limit"])
    assert all(item["type"] == "series" for item in data["items"])


def test_get_recent_content(client, db_session):
    response = client.get("/content/recent?limit=5")
    data = response.json()
    titles = [item["title"] for item in data["items"]]

    assert response.status_code == 200
    assert data["total"] == recent_content_count(db_session)
    assert data["total"] >= MIN_SEED_TOTAL
    assert len(data["items"]) <= 5
    assert titles == expected_recent_titles(db_session, limit=5)


def test_recent_sorting_preserves_series_original_release_date(client):
    response = client.get("/content/recent?limit=5")
    data = response.json()

    the_boys = next(item for item in data["items"] if item["title"] == "The Boys")

    assert response.status_code == 200
    assert the_boys["release_date"] == "2019-07-26"
    assert the_boys["year"] == 2019


def test_recent_movie_filter_still_sorts_by_movie_release_date(client, db_session):
    response = client.get("/content/recent?content_type=movie&limit=3")
    data = response.json()

    assert response.status_code == 200
    assert [item["title"] for item in data["items"]] == expected_recent_titles(
        db_session,
        limit=3,
        content_type="movie",
    )


def test_discover_recent_uses_latest_activity_date(client, db_session):
    limit = 3
    response = client.get(f"/content/discover?sort_by=recent&limit={limit}")
    data = response.json()
    titles = [item["title"] for item in data["items"]]

    assert response.status_code == 200
    assert data["limit"] == limit
    assert len(data["items"]) <= limit
    assert titles == expected_discover_recent_titles(
        db_session,
        limit=limit,
    )


def test_get_top_rated_content(client):
    response = client.get("/content/top-rated?limit=5")
    data = response.json()

    assert response.status_code == 200
    assert data["total"] >= MIN_SEED_TOTAL
    assert len(data["items"]) == 5

    expected_high_score_titles = {
        "Breaking Bad",
        "Parasite",
        "The Dark Knight",
        "Spider-Man: Across the Spider-Verse",
        "The Last of Us",
    }
    assert len(titles_from_items(data) & expected_high_score_titles) >= 3


def test_get_content_by_animation_genre(client, db_session):
    response = client.get("/content/by-genre/Animation")
    data = response.json()
    animation_ids = content_ids_for_genre(db_session, "Animation")

    assert response.status_code == 200
    assert data["total"] >= 1
    assert data["items"]
    assert len(data["items"]) == min(data["total"], data["limit"])
    assert all(item["id"] in animation_ids for item in data["items"])

    spider_verse_id = optional_content_id_by_title(
        db_session,
        "Spider-Man: Across the Spider-Verse",
    )
    if spider_verse_id is not None:
        assert spider_verse_id in animation_ids


def test_get_content_by_mystery_genre(client, db_session):
    response = client.get("/content/by-genre/Mystery")
    data = response.json()
    mystery_ids = content_ids_for_genre(db_session, "Mystery")

    assert response.status_code == 200
    assert data["total"] >= 1
    assert data["items"]
    assert len(data["items"]) == min(data["total"], data["limit"])
    assert all(item["id"] in mystery_ids for item in data["items"])

    dark_id = optional_content_id_by_title(db_session, "Dark")
    if dark_id is not None:
        assert dark_id in mystery_ids


def test_get_content_by_netflix_streaming_platform(client, db_session):
    expected_ids = content_ids_for_platform_filter(
        db_session,
        "Netflix",
        availability_type="streaming",
    )
    if not expected_ids:
        pytest.skip("No Netflix streaming availability exists in this database.")

    response = client.get("/content/by-platform/Netflix?availability_type=streaming&limit=20")
    data = response.json()

    assert response.status_code == 200
    assert data["total"] == len(expected_ids)
    assert data["items"]
    assert len({item["id"] for item in data["items"]}) == len(data["items"])
    assert all(item["id"] in expected_ids for item in data["items"])


def test_discover_scifi_netflix_top_rated(client, db_session):
    scifi_ids = content_ids_for_genre(db_session, "Sci-Fi")
    platform_ids = content_ids_for_platform_filter(db_session, "Netflix")
    expected_ids = scifi_ids & platform_ids
    if not expected_ids:
        pytest.skip("No Sci-Fi Netflix availability exists in this database.")

    response = client.get(
        "/content/discover?genre=Sci-Fi&platform=Netflix&sort_by=top_rated&limit=20"
    )
    data = response.json()

    assert response.status_code == 200
    assert data["total"] == len(expected_ids)
    assert data["items"]
    assert len({item["id"] for item in data["items"]}) == len(data["items"])
    assert all(item["id"] in expected_ids for item in data["items"])


def test_discover_platform_filter_uses_region_aware_availability(
    client,
    db_session,
):
    platform = first_region_aware_platform(db_session)
    if platform is None:
        pytest.skip("No IN region-aware availability exists in this database.")

    expected_ids = content_ids_for_platform_filter(db_session, platform["name"])
    response = client.get(
        f"/content/discover?platform={quote(platform['name'])}&limit=20"
    )
    data = response.json()

    assert response.status_code == 200
    assert data["total"] == len(expected_ids)
    assert data["items"]
    assert len({item["id"] for item in data["items"]}) == len(data["items"])
    assert all(item["id"] in expected_ids for item in data["items"])


def test_discover_platform_and_availability_type_use_region_aware_availability(
    client,
    db_session,
):
    platform = first_region_aware_platform(db_session)
    if platform is None:
        pytest.skip("No IN region-aware availability exists in this database.")

    expected_ids = content_ids_for_platform_filter(
        db_session,
        platform["name"],
        availability_type=platform["availability_type"],
    )
    response = client.get(
        f"/content/discover?platform={quote(platform['name'])}"
        f"&availability_type={platform['availability_type']}&limit=20"
    )
    data = response.json()

    assert response.status_code == 200
    assert data["total"] == len(expected_ids)
    assert data["items"]
    assert len({item["id"] for item in data["items"]}) == len(data["items"])
    assert all(item["id"] in expected_ids for item in data["items"])


def test_get_content_by_platform_uses_region_aware_availability(
    client,
    db_session,
):
    platform = first_region_aware_platform(db_session)
    if platform is None:
        pytest.skip("No IN region-aware availability exists in this database.")

    expected_ids = content_ids_for_platform_filter(db_session, platform["name"])
    response = client.get(f"/content/by-platform/{quote(platform['name'])}?limit=20")
    data = response.json()

    assert response.status_code == 200
    assert data["total"] == len(expected_ids)
    assert data["items"]
    assert len({item["id"] for item in data["items"]}) == len(data["items"])
    assert all(item["id"] in expected_ids for item in data["items"])


def test_detail_ratings_high_vote_source_returns_unified_score():
    ratings = get_detail_ratings(
        FakeRatingsDb([
            fake_rating_row(
                normalized_score=86,
                vote_count=MINIMUM_VOTE_COUNT_FOR_UNIFIED_SCORE,
            )
        ]),
        content_id=1,
    )

    assert ratings["unified_score"] == 86
    assert ratings["source_count"] == 1
    assert ratings["scoring_source_count"] == 1
    assert ratings["sources"][0]["source_name"] == "tmdb"
    assert ratings["sources"][0]["included_in_unified_score"] is True
    assert (
        ratings["sources"][0]["vote_count"]
        == MINIMUM_VOTE_COUNT_FOR_UNIFIED_SCORE
    )


def test_detail_ratings_low_vote_source_keeps_source_without_unified_score():
    ratings = get_detail_ratings(
        FakeRatingsDb([
            fake_rating_row(
                normalized_score=91,
                vote_count=MINIMUM_VOTE_COUNT_FOR_UNIFIED_SCORE - 1,
            )
        ]),
        content_id=1,
    )

    assert ratings["unified_score"] is None
    assert ratings["source_count"] == 1
    assert ratings["scoring_source_count"] == 0
    assert ratings["sources"][0]["normalized_score"] == 91
    assert ratings["sources"][0]["included_in_unified_score"] is False
    assert (
        ratings["sources"][0]["vote_count"]
        == MINIMUM_VOTE_COUNT_FOR_UNIFIED_SCORE - 1
    )


def test_detail_ratings_null_vote_count_source_keeps_source_without_unified_score():
    ratings = get_detail_ratings(
        FakeRatingsDb([fake_rating_row(normalized_score=78, vote_count=None)]),
        content_id=1,
    )

    assert ratings["unified_score"] is None
    assert ratings["source_count"] == 1
    assert ratings["scoring_source_count"] == 0
    assert ratings["sources"][0]["normalized_score"] == 78
    assert ratings["sources"][0]["vote_count"] is None
    assert ratings["sources"][0]["included_in_unified_score"] is False


def test_detail_ratings_combines_tmdb_and_imdb_sources():
    ratings = get_detail_ratings(
        FakeRatingsDb(
            [
                fake_rating_row(
                    normalized_score=83,
                    vote_count=6000,
                    source_name="tmdb",
                    display_name="TMDb",
                ),
                fake_rating_row(
                    normalized_score=87,
                    vote_count=250000,
                    source_name="imdb",
                    display_name="IMDb",
                ),
            ]
        ),
        content_id=1,
    )

    assert ratings["unified_score"] == 85
    assert ratings["source_count"] == 2
    assert ratings["scoring_source_count"] == 2
    assert {source["source_name"] for source in ratings["sources"]} == {
        "tmdb",
        "imdb",
    }


def test_detail_ratings_rounds_unified_score_normally():
    ratings = get_detail_ratings(
        FakeRatingsDb(
            [
                fake_rating_row(
                    normalized_score=85,
                    vote_count=6000,
                    source_name="tmdb",
                    display_name="TMDb",
                ),
                fake_rating_row(
                    normalized_score=82,
                    vote_count=250000,
                    source_name="imdb",
                    display_name="IMDb",
                ),
            ]
        ),
        content_id=1,
    )

    assert ratings["unified_score"] == 84


def test_detail_ratings_returns_rating_url_when_available():
    ratings = get_detail_ratings(
        FakeRatingsDb(
            [
                fake_rating_row(
                    normalized_score=87,
                    vote_count=250000,
                    source_name="imdb",
                    display_name="IMDb",
                    rating_url="https://www.imdb.com/title/tt0133093/",
                )
            ]
        ),
        content_id=1,
    )

    assert ratings["sources"][0]["source_name"] == "imdb"
    assert ratings["sources"][0]["rating_url"] == "https://www.imdb.com/title/tt0133093/"


def test_detail_ratings_includes_letterboxd_without_changing_unified_score():
    ratings = get_detail_ratings(
        FakeRatingsDb(
            [
                fake_rating_row(
                    normalized_score=80,
                    vote_count=2000,
                    source_name="tmdb",
                    display_name="TMDb",
                ),
                fake_rating_row(
                    normalized_score=84,
                    vote_count=250000,
                    source_name="imdb",
                    display_name="IMDb",
                ),
                fake_rating_row(
                    normalized_score=100,
                    vote_count=None,
                    source_name="letterboxd",
                    display_name="Letterboxd",
                    weight=0,
                    rating_url="https://letterboxd.com/film/example/",
                    raw_score=5,
                    raw_score_scale=5,
                ),
            ]
        ),
        content_id=1,
    )

    assert ratings["unified_score"] == 82
    assert ratings["source_count"] == 3
    assert ratings["scoring_source_count"] == 2
    letterboxd = next(
        source for source in ratings["sources"] if source["source_name"] == "letterboxd"
    )
    assert letterboxd["raw_score"] == 5
    assert letterboxd["raw_score_scale"] == 5
    assert letterboxd["vote_count"] is None
    assert letterboxd["rating_url"] == "https://letterboxd.com/film/example/"
    assert letterboxd["included_in_unified_score"] is False


def test_detail_ratings_low_vote_imdb_does_not_override_confident_tmdb_score():
    ratings = get_detail_ratings(
        FakeRatingsDb(
            [
                fake_rating_row(
                    normalized_score=80,
                    vote_count=2000,
                    source_name="tmdb",
                    display_name="TMDb",
                ),
                fake_rating_row(
                    normalized_score=100,
                    vote_count=MINIMUM_VOTE_COUNT_FOR_UNIFIED_SCORE - 1,
                    source_name="imdb",
                    display_name="IMDb",
                ),
            ]
        ),
        content_id=1,
    )

    assert ratings["unified_score"] == 80
    assert ratings["source_count"] == 2
    assert ratings["scoring_source_count"] == 1
    assert any(
        source["source_name"] == "imdb"
        and source["normalized_score"] == 100
        and source["vote_count"] == MINIMUM_VOTE_COUNT_FOR_UNIFIED_SCORE - 1
        for source in ratings["sources"]
    )


def test_detail_ratings_empty_rows_return_stable_empty_shape():
    assert get_detail_ratings(FakeRatingsDb([]), content_id=1) == {
        "unified_score": None,
        "source_count": 0,
        "scoring_source_count": 0,
        "sources": [],
    }


def test_get_content_details_for_seeded_title(client, content_id_by_title):
    content_id = content_id_by_title("Interstellar")

    response = client.get(f"/content/{content_id}/details")
    data = response.json()

    assert response.status_code == 200
    assert data["content"]["title"] == "Interstellar"
    assert data["genres"]
    assert data["platforms"]
    assert data["ratings"]["source_count"] == len(data["ratings"]["sources"])
    assert data["ratings"]["scoring_source_count"] <= data["ratings"]["source_count"]
    assert "unified_score" in data["ratings"]
    assert data["insight_summary"]["confidence"] in {"low", "medium", "high"}
    assert isinstance(data["insight_summary"]["best_for"], list)
    assert isinstance(data["insight_summary"]["key_signals"], list)
    assert isinstance(data["insight_summary"]["generated_from"], list)
    assert "decision_layer" in data
    assert data["summary"] is not None
    assert data["series_metadata"] is None


def test_content_details_include_decision_layer_when_source_signals_exist(
    client,
    db_session,
):
    row = first_content_with_watch_guidance(db_session)
    if row is None:
        pytest.skip("No imported source-signal watch guidance exists in this database.")

    response = client.get(f"/content/{row['id']}/details")
    data = response.json()

    assert response.status_code == 200
    decision_layer = data["decision_layer"]
    assert decision_layer is not None
    assert decision_layer["watch_profile"]["watch_feel"]
    assert isinstance(decision_layer["watch_profile"]["chips"], list)
    assert isinstance(decision_layer["decision_support"]["reasons"], list)
    assert decision_layer["signal_quality"]["has_watch_guidance"] is True
    public_text = str(decision_layer).lower()
    assert "tmdb_keywords" not in public_text
    assert "mapping_version" not in public_text
    assert "source_names" not in public_text
    assert "confidence" not in public_text
    assert "provider" not in public_text
    assert "raw keyword" not in public_text
    labels = (
        decision_layer["watch_profile"]["chips"]
        + decision_layer["watch_profile"]["best_for"]
    )
    blocked_identity_phrases = (
        "jiohotstar viewers",
        "netflix viewers",
        "prime video viewers",
        "serialized drama viewers",
        "platform viewers",
        "availability viewers",
    )
    assert all(
        blocked not in label.lower()
        for label in labels
        for blocked in blocked_identity_phrases
    )


def test_content_details_handle_missing_decision_layer_safely(client, db_session):
    row = first_content_without_watch_guidance(db_session)
    if row is None:
        pytest.skip("All content has imported source-signal watch guidance.")

    response = client.get(f"/content/{row['id']}/details")
    data = response.json()

    assert response.status_code == 200
    assert data["decision_layer"] is None


def test_content_details_include_imported_ratings_when_available(client, db_session):
    row = first_content_with_imported_rating(db_session)
    if row is None:
        pytest.skip("No imported content ratings exist in this database.")

    response = client.get(f"/content/{row['id']}/details")
    data = response.json()

    assert response.status_code == 200
    assert data["content"]["title"] == row["title"]
    assert data["ratings"]["source_count"] >= 1
    assert data["ratings"]["scoring_source_count"] <= data["ratings"]["source_count"]
    assert data["ratings"]["sources"]

    source = data["ratings"]["sources"][0]
    assert source["source_name"] == row["source_name"]
    assert source["display_name"] == row["display_name"]
    assert source["normalized_score"] is not None
    if (
        row["vote_count"] is not None
        and row["vote_count"] >= MINIMUM_VOTE_COUNT_FOR_UNIFIED_SCORE
    ):
        assert data["ratings"]["unified_score"] is not None
    else:
        assert data["ratings"]["unified_score"] is None


def test_content_details_return_empty_ratings_shape_when_missing(client, db_session):
    row = first_content_without_imported_rating(db_session)
    if row is None:
        pytest.skip("All content has imported ratings in this database.")

    response = client.get(f"/content/{row['id']}/details")
    data = response.json()

    assert response.status_code == 200
    assert data["ratings"] == {
        "unified_score": None,
        "source_count": 0,
        "scoring_source_count": 0,
        "sources": [],
    }


def test_content_details_include_series_metadata_when_imported(client, db_session):
    row = first_series_with_lifecycle_metadata(db_session)
    if row is None:
        pytest.skip("No imported series lifecycle metadata exists in this database.")

    response = client.get(f"/content/{row['id']}/details")
    data = response.json()

    assert response.status_code == 200
    assert data["content"]["title"] == row["title"]
    assert data["content"]["type"] == "series"
    assert data["series_metadata"] is not None
    assert data["series_metadata"]["number_of_seasons"] == row["number_of_seasons"]
    assert (
        data["series_metadata"]["series_status_normalized"]
        == row["series_status_normalized"]
    )
    assert "released_seasons_count" in data["series_metadata"]
    assert "announced_seasons_count" in data["series_metadata"]
    assert "next_season_number" in data["series_metadata"]
    assert "next_season_air_date" in data["series_metadata"]
    assert "next_season_year" in data["series_metadata"]
    assert "has_announced_season" in data["series_metadata"]
    assert "season_summary_note" in data["series_metadata"]
    assert (
        data["series_metadata"]["released_seasons_count"]
        == row["released_seasons_count"]
    )
    assert (
        data["series_metadata"]["has_announced_season"]
        == row["has_announced_season"]
    )


def test_content_details_return_null_series_metadata_for_movie(
    client,
    content_id_by_title,
):
    content_id = content_id_by_title("Interstellar")

    response = client.get(f"/content/{content_id}/details")
    data = response.json()

    assert response.status_code == 200
    assert data["content"]["type"] == "movie"
    assert data["series_metadata"] is None


def test_content_details_include_imported_region_aware_availability(client, db_session):
    content_id = optional_content_id_by_title(db_session, "Oppenheimer")
    if content_id is None:
        pytest.skip("Oppenheimer has not been imported into this local database.")
    if not has_region_aware_availability(db_session, content_id):
        pytest.skip("Oppenheimer region-aware availability has not been imported.")

    response = client.get(f"/content/{content_id}/details")
    data = response.json()
    platforms = data["platforms"]

    assert response.status_code == 200
    assert data["content"]["title"] == "Oppenheimer"
    assert data["content"]["age_rating"] == "UA"
    assert platforms
    assert {platform["region_code"] for platform in platforms} == {"IN"}
    assert all(platform["source_name"] == "tmdb" for platform in platforms)
    assert any(
        platform["name"] == "JioHotstar"
        and platform["availability_type"] == "streaming"
        for platform in platforms
    )


def test_content_details_prefer_in_certification_over_stored_age_rating(
    client,
    db_session,
):
    row = first_in_certification_conflict(db_session)
    if row is None:
        pytest.skip("No content has an IN certification conflict in this database.")

    response = client.get(f"/content/{row['id']}/details")
    content = response.json()["content"]

    assert response.status_code == 200
    assert content["title"] == row["title"]
    assert content["age_rating"] == row["certification"]
    assert content["age_rating"] != row["stored_age_rating"]
    assert content["age_rating_region"] == "IN"
    assert content["age_rating_source"] == row["source_name"]
    assert content["age_rating_system"] == row["rating_system"]


def test_content_details_falls_back_to_us_certification_when_in_missing(
    client,
    db_session,
):
    row = first_us_only_certification(db_session)
    if row is None:
        pytest.skip("No content has a US-only certification in this database.")

    response = client.get(f"/content/{row['id']}/details")
    content = response.json()["content"]

    assert response.status_code == 200
    assert content["title"] == row["title"]
    assert content["age_rating"] == row["certification"]
    assert content["age_rating_region"] == "US"
    assert content["age_rating_source"] == row["source_name"]
    assert content["age_rating_system"] == row["rating_system"]


def test_content_details_falls_back_to_legacy_age_rating_without_certifications(
    client,
    db_session,
):
    row = first_legacy_age_rating_only(db_session)
    if row is None:
        pytest.skip("No content has legacy-only age_rating in this database.")

    response = client.get(f"/content/{row['id']}/details")
    content = response.json()["content"]

    assert response.status_code == 200
    assert content["title"] == row["title"]
    assert content["age_rating"] == row["age_rating"]
    assert content["age_rating_region"] is None
    assert content["age_rating_source"] is None
    assert content["age_rating_system"] is None


def test_content_details_region_aware_availability_has_no_duplicate_rows(
    client,
    db_session,
):
    content_id = optional_content_id_by_title(db_session, "Oppenheimer")
    if content_id is None:
        pytest.skip("Oppenheimer has not been imported into this local database.")
    if not has_region_aware_availability(db_session, content_id):
        pytest.skip("Oppenheimer region-aware availability has not been imported.")

    response = client.get(f"/content/{content_id}/details")
    platforms = response.json()["platforms"]
    platform_keys = {
        (
            platform["name"],
            platform["availability_type"],
            platform.get("region_code"),
            platform.get("source_name"),
        )
        for platform in platforms
    }

    assert response.status_code == 200
    assert len(platform_keys) == len(platforms)


def test_content_details_preserve_legacy_availability_fallback(client, db_session):
    row = db_session.execute(
        text(
            """
            SELECT c.id, c.title
            FROM content c
            WHERE EXISTS (
                SELECT 1
                FROM content_platforms cp
                WHERE cp.content_id = c.id
            )
              AND NOT EXISTS (
                SELECT 1
                FROM content_availability ca
                WHERE ca.content_id = c.id
            )
            ORDER BY c.title
            LIMIT 1;
            """
        )
    ).mappings().first()
    if row is None:
        pytest.skip("No legacy-only availability content exists in this database.")

    response = client.get(f"/content/{row['id']}/details")
    platforms = response.json()["platforms"]

    assert response.status_code == 200
    assert platforms
    assert all(platform.get("region_code") is None for platform in platforms)
    assert all(platform.get("source_name") is None for platform in platforms)


def test_content_details_us_availability_fallback_is_not_labeled_as_in(
    client,
    db_session,
):
    row = db_session.execute(
        text(
            """
            SELECT c.id, c.title
            FROM content c
            WHERE EXISTS (
                SELECT 1
                FROM content_availability ca
                WHERE ca.content_id = c.id
                  AND ca.region_code = 'US'
            )
              AND NOT EXISTS (
                SELECT 1
                FROM content_availability ca
                WHERE ca.content_id = c.id
                  AND ca.region_code = 'IN'
            )
            ORDER BY c.title
            LIMIT 1;
            """
        )
    ).mappings().first()
    if row is None:
        pytest.skip("No content has US-only availability in this database.")

    response = client.get(f"/content/{row['id']}/details")
    platforms = response.json()["platforms"]

    assert response.status_code == 200
    assert platforms
    assert {platform["region_code"] for platform in platforms} == {"US"}


def test_content_details_empty_availability_is_safe(client, db_session):
    row = db_session.execute(
        text(
            """
            SELECT c.id
            FROM content c
            WHERE NOT EXISTS (
                SELECT 1
                FROM content_platforms cp
                WHERE cp.content_id = c.id
            )
              AND NOT EXISTS (
                SELECT 1
                FROM content_availability ca
                WHERE ca.content_id = c.id
            )
            ORDER BY c.title
            LIMIT 1;
            """
        )
    ).mappings().first()
    if row is None:
        pytest.skip("No content without availability exists in this database.")

    response = client.get(f"/content/{row['id']}/details")
    data = response.json()

    assert response.status_code == 200
    assert data["platforms"] == []
