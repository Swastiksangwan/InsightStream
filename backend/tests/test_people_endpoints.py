import pytest
from sqlalchemy import text


def insert_test_person(
    db_session,
    *,
    name="Test Person",
    birthday=None,
    place_of_birth=None,
    biography=None,
    known_for_department="Acting",
):
    row = db_session.execute(
        text(
            """
            INSERT INTO people (
                name,
                profile_url,
                known_for_department,
                biography,
                birthday,
                place_of_birth
            )
            VALUES (
                :name,
                NULL,
                :known_for_department,
                :biography,
                :birthday,
                :place_of_birth
            )
            RETURNING id;
            """
        ),
        {
            "name": name,
            "known_for_department": known_for_department,
            "biography": biography,
            "birthday": birthday,
            "place_of_birth": place_of_birth,
        },
    ).mappings().first()
    db_session.commit()
    return row["id"]


def delete_test_person(db_session, person_id):
    db_session.execute(text("DELETE FROM people WHERE id = :person_id;"), {"person_id": person_id})
    db_session.commit()


def get_existing_person_id(db_session):
    row = db_session.execute(
        text("""
            SELECT id
            FROM people
            ORDER BY id ASC
            LIMIT 1;
        """)
    ).mappings().first()

    if row is None:
        pytest.skip("No imported people data present.")

    return row["id"]


def test_get_missing_person_returns_404(client):
    response = client.get("/people/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Person not found"


def test_get_missing_person_credits_returns_404(client):
    response = client.get("/people/999999/credits")

    assert response.status_code == 404
    assert response.json()["detail"] == "Person not found"


def test_get_person_returns_provider_neutral_profile_if_present(client, db_session):
    person_id = get_existing_person_id(db_session)

    response = client.get(f"/people/{person_id}")
    data = response.json()

    assert response.status_code == 200
    assert data["person_id"] == person_id
    assert set(data.keys()) == {
        "person_id",
        "name",
        "profile_url",
        "known_for_department",
        "biography",
        "birthday",
        "place_of_birth",
    }
    assert data["name"]

    for private_field in ("source_name", "external_id", "source_url"):
        assert private_field not in data


def test_get_person_returns_birthday_and_birthplace_for_controlled_person(
    client,
    db_session,
):
    person_id = insert_test_person(
        db_session,
        name="Metadata Test Person",
        birthday="1995-12-27",
        place_of_birth="New York City, New York, USA",
        biography="A controlled test biography.",
    )

    try:
        response = client.get(f"/people/{person_id}")
        data = response.json()

        assert response.status_code == 200
        assert data["birthday"] == "1995-12-27"
        assert data["place_of_birth"] == "New York City, New York, USA"
        assert data["biography"] == "A controlled test biography."
    finally:
        delete_test_person(db_session, person_id)


def test_get_person_handles_missing_birthday_and_birthplace(client, db_session):
    person_id = insert_test_person(
        db_session,
        name="Sparse Metadata Test Person",
        birthday=None,
        place_of_birth=None,
    )

    try:
        response = client.get(f"/people/{person_id}")
        data = response.json()

        assert response.status_code == 200
        assert data["birthday"] is None
        assert data["place_of_birth"] is None
    finally:
        delete_test_person(db_session, person_id)


def test_get_person_credits_returns_grouped_content_if_present(client, db_session):
    person_id = get_existing_person_id(db_session)

    response = client.get(f"/people/{person_id}/credits")
    data = response.json()

    assert response.status_code == 200
    assert data["person_id"] == person_id
    assert set(data.keys()) == {
        "person_id",
        "cast",
        "directed",
        "created",
        "crew",
    }
    assert isinstance(data["cast"], list)
    assert isinstance(data["directed"], list)
    assert isinstance(data["created"], list)
    assert isinstance(data["crew"], list)

    all_credits = (
        data["cast"] +
        data["directed"] +
        data["created"] +
        data["crew"]
    )

    if not all_credits:
        return

    first_credit = all_credits[0]
    assert {
        "content_id",
        "title",
        "content_type",
        "poster_url",
        "year",
        "character_name",
        "display_order",
        "job",
        "department",
    } <= set(first_credit.keys())

    for private_field in ("source_name", "source_credit_id", "source_person_id"):
        assert private_field not in first_credit
