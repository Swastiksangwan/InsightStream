import pytest
from sqlalchemy import text


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
    }
    assert data["name"]

    for private_field in ("source_name", "external_id", "source_url"):
        assert private_field not in data


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
