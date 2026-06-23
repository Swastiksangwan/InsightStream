import pytest
from sqlalchemy import text


MIN_SEED_TOTAL = 15
MIN_SEED_MOVIE_TOTAL = 8
MIN_SEED_SERIES_TOTAL = 7


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
            SELECT c.id, c.title, csm.number_of_seasons, csm.series_status_normalized
            FROM content c
            JOIN content_series_metadata csm ON csm.content_id = c.id
            WHERE c.content_type = 'series'
            ORDER BY c.title
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


def test_get_content_by_netflix_streaming_platform(client):
    response = client.get("/content/by-platform/Netflix?availability_type=streaming&limit=20")
    data = response.json()
    titles = titles_from_items(data)

    assert response.status_code == 200
    assert data["total"] >= 1
    assert {"Inception", "Breaking Bad", "Stranger Things"} <= titles


def test_discover_scifi_netflix_top_rated(client):
    response = client.get(
        "/content/discover?genre=Sci-Fi&platform=Netflix&sort_by=top_rated&limit=20"
    )
    data = response.json()
    titles = titles_from_items(data)

    assert response.status_code == 200
    assert data["total"] >= 1
    assert {
        "Inception",
        "Spider-Man: Across the Spider-Verse",
        "Stranger Things",
        "Dark",
    } <= titles


def test_get_content_details_for_seeded_title(client, content_id_by_title):
    content_id = content_id_by_title("Interstellar")

    response = client.get(f"/content/{content_id}/details")
    data = response.json()

    assert response.status_code == 200
    assert data["content"]["title"] == "Interstellar"
    assert data["genres"]
    assert data["platforms"]
    assert data["ratings"]
    assert data["summary"] is not None
    assert data["series_metadata"] is None


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
