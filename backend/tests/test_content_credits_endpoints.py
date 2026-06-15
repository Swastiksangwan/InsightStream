from sqlalchemy import text


def test_get_content_credits_returns_provider_neutral_shape(client, content_id_by_title):
    content_id = content_id_by_title("Interstellar")

    response = client.get(f"/content/{content_id}/credits")
    data = response.json()

    assert response.status_code == 200
    assert data["content_id"] == content_id
    assert set(data.keys()) == {
        "content_id",
        "cast",
        "directors",
        "creators",
        "crew",
    }
    assert isinstance(data["cast"], list)
    assert isinstance(data["directors"], list)
    assert isinstance(data["creators"], list)
    assert isinstance(data["crew"], list)


def test_get_content_credits_groups_imported_movie_credits_if_present(
    client,
    content_id_by_title,
    db_session,
):
    content_id = content_id_by_title("Interstellar")
    row = db_session.execute(
        text(
            """
            SELECT COUNT(*) AS total
            FROM content_people
            WHERE content_id = :content_id;
            """
        ),
        {"content_id": content_id},
    ).mappings().first()

    response = client.get(f"/content/{content_id}/credits")
    data = response.json()

    assert response.status_code == 200

    if row["total"] == 0:
        assert data == {
            "content_id": content_id,
            "cast": [],
            "directors": [],
            "creators": [],
            "crew": [],
        }
        return

    assert data["cast"]
    assert data["directors"]
    assert data["creators"] == []

    first_cast = data["cast"][0]
    assert {
        "person_id",
        "name",
        "character_name",
        "profile_url",
        "known_for_department",
        "display_order",
    } <= set(first_cast.keys())

    assert first_cast["name"] == "Matthew McConaughey"
    assert first_cast["character_name"] == "Cooper"
    assert first_cast["display_order"] == 0

    director_names = {director["name"] for director in data["directors"]}
    assert "Christopher Nolan" in director_names

    for private_field in ("source_name", "source_person_id", "source_credit_id"):
        assert private_field not in first_cast
        assert private_field not in data["directors"][0]


def test_get_content_credits_groups_imported_series_credits_if_present(
    client,
    content_id_by_title,
    db_session,
):
    content_id = content_id_by_title("The Mandalorian")
    row = db_session.execute(
        text(
            """
            SELECT COUNT(*) AS total
            FROM content_people
            WHERE content_id = :content_id;
            """
        ),
        {"content_id": content_id},
    ).mappings().first()

    response = client.get(f"/content/{content_id}/credits")
    data = response.json()

    assert response.status_code == 200

    if row["total"] == 0:
        assert data["cast"] == []
        assert data["directors"] == []
        assert data["creators"] == []
        assert data["crew"] == []
        return

    assert data["cast"]
    assert data["directors"] == []
    assert data["creators"]

    creator_names = {creator["name"] for creator in data["creators"]}
    assert "Jon Favreau" in creator_names


def test_get_content_credits_for_missing_content_returns_404(client):
    response = client.get("/content/999999/credits")

    assert response.status_code == 404
    assert response.json()["detail"] == "Content not found"
