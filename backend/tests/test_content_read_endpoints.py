def titles_from_items(response_json):
    return {item["title"] for item in response_json["items"]}


def test_get_content_returns_expanded_seed(client):
    response = client.get("/content?limit=20")
    data = response.json()

    assert response.status_code == 200
    assert data["total"] == 15
    assert len(data["items"]) == 15
    assert data["limit"] == 20
    assert data["offset"] == 0


def test_get_content_filters_movies(client):
    response = client.get("/content?content_type=movie&limit=20")
    data = response.json()

    assert response.status_code == 200
    assert data["total"] == 8
    assert all(item["type"] == "movie" for item in data["items"])


def test_get_content_filters_series(client):
    response = client.get("/content?content_type=series&limit=20")
    data = response.json()

    assert response.status_code == 200
    assert data["total"] == 7
    assert all(item["type"] == "series" for item in data["items"])


def test_get_recent_content(client):
    response = client.get("/content/recent?limit=5")
    data = response.json()
    titles = [item["title"] for item in data["items"]]

    assert response.status_code == 200
    assert data["total"] == 15
    assert len(data["items"]) == 5
    assert titles == [
        "The Boys",
        "Stranger Things",
        "The Witcher",
        "The Last of Us",
        "Dune: Part Two",
    ]


def test_recent_sorting_preserves_series_original_release_date(client):
    response = client.get("/content/recent?limit=5")
    data = response.json()

    the_boys = next(item for item in data["items"] if item["title"] == "The Boys")

    assert response.status_code == 200
    assert the_boys["release_date"] == "2019-07-26"
    assert the_boys["year"] == 2019


def test_recent_movie_filter_still_sorts_by_movie_release_date(client):
    response = client.get("/content/recent?content_type=movie&limit=3")
    data = response.json()

    assert response.status_code == 200
    assert [item["title"] for item in data["items"]] == [
        "Dune: Part Two",
        "Barbie",
        "Spider-Man: Across the Spider-Verse",
    ]


def test_discover_recent_uses_latest_activity_date(client):
    response = client.get("/content/discover?sort_by=recent&limit=3")
    data = response.json()

    assert response.status_code == 200
    assert [item["title"] for item in data["items"]] == [
        "The Boys",
        "Stranger Things",
        "The Witcher",
    ]


def test_get_top_rated_content(client):
    response = client.get("/content/top-rated?limit=5")
    data = response.json()

    assert response.status_code == 200
    assert data["total"] == 15
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
