def test_get_genres(client):
    response = client.get("/genres")
    data = response.json()
    genre_names = {genre["name"] for genre in data}

    assert response.status_code == 200
    assert isinstance(data, list)
    assert {"Action", "Drama", "Sci-Fi"} <= genre_names


def test_get_platforms(client):
    response = client.get("/platforms")
    data = response.json()
    platform_names = {platform["name"] for platform in data}

    assert response.status_code == 200
    assert isinstance(data, list)
    assert {"Netflix", "Prime Video", "IMDb"} <= platform_names


def test_get_ott_platforms(client):
    response = client.get("/platforms?platform_type=ott")
    data = response.json()

    assert response.status_code == 200
    assert data
    assert all(platform["platform_type"] == "ott" for platform in data)


def test_get_rating_source_platforms(client):
    response = client.get("/platforms?platform_type=rating_source")
    data = response.json()

    assert response.status_code == 200
    assert data
    assert all(platform["platform_type"] == "rating_source" for platform in data)
