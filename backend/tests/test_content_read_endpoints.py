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
    response = client.get("/content/discover?sort_by=recent&limit=3")
    data = response.json()

    assert response.status_code == 200
    assert [item["title"] for item in data["items"]] == expected_recent_titles(
        db_session,
        limit=3,
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


def test_get_content_by_animation_genre(client):
    response = client.get("/content/by-genre/Animation")
    data = response.json()

    assert response.status_code == 200
    assert data["total"] >= 1
    assert "Spider-Man: Across the Spider-Verse" in titles_from_items(data)


def test_get_content_by_mystery_genre(client):
    response = client.get("/content/by-genre/Mystery")
    data = response.json()

    assert response.status_code == 200
    assert data["total"] >= 1
    assert "Dark" in titles_from_items(data)


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
