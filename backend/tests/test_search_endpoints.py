import pytest
from sqlalchemy import text


def first_person_for_search(db_session):
    row = db_session.execute(
        text("""
            SELECT id, name
            FROM people
            ORDER BY id ASC
            LIMIT 1;
        """)
    ).mappings().first()

    if row is None:
        pytest.skip("No imported people data present.")

    return row


def first_person_by_name(db_session, name_part):
    row = db_session.execute(
        text("""
            SELECT id, name
            FROM people
            WHERE name ILIKE :name
            ORDER BY name ASC
            LIMIT 1;
        """),
        {"name": f"%{name_part}%"},
    ).mappings().first()

    if row is None:
        pytest.skip(f"No imported person matching {name_part!r} present.")

    return row


def content_ids_linked_to_person_name(db_session, name_part):
    rows = db_session.execute(
        text("""
            SELECT DISTINCT c.id, c.title
            FROM content c
            JOIN content_people cp ON cp.content_id = c.id
            JOIN people p ON p.id = cp.person_id
            WHERE p.name ILIKE :name
            ORDER BY c.title ASC;
        """),
        {"name": f"%{name_part}%"},
    ).mappings().all()

    if not rows:
        pytest.skip(f"No content linked to person matching {name_part!r} present.")

    return rows


def test_search_content_by_exact_title(client):
    response = client.get("/search?q=Interstellar&type=content")
    data = response.json()

    assert response.status_code == 200
    assert data["query"] == "Interstellar"
    assert data["type"] == "content"
    assert data["total_content_results"] >= 1
    assert data["total_person_results"] == 0
    assert data["person_results"] == []
    assert data["content_results"][0]["title"] == "Interstellar"
    assert data["content_results"][0]["result_type"] == "content"


def test_search_content_by_partial_title(client):
    response = client.get("/search?q=dark&type=content")
    data = response.json()
    titles = {item["title"] for item in data["content_results"]}

    assert response.status_code == 200
    assert data["total_content_results"] >= 1
    assert "The Dark Knight" in titles or "Dark" in titles
    assert all(item["result_type"] == "content" for item in data["content_results"])


def test_search_thing_ranks_stranger_things_above_internal_substrings_if_present(client):
    response = client.get("/search?q=thing&type=content&limit=20")
    data = response.json()
    titles = [item["title"] for item in data["content_results"]]

    assert response.status_code == 200

    if "Stranger Things" not in titles:
        pytest.skip("Stranger Things is not present in the current search result window.")

    internal_substring_titles = [
        title
        for title in titles
        if "thing" in title.lower() and title != "Stranger Things"
    ]

    assert not internal_substring_titles or titles.index("Stranger Things") < min(
        titles.index(title) for title in internal_substring_titles
    )


def test_search_person_by_exact_name_if_people_exist(client, db_session):
    person = first_person_for_search(db_session)

    response = client.get("/search", params={"q": person["name"], "type": "person"})
    data = response.json()
    person_ids = {item["id"] for item in data["person_results"]}

    assert response.status_code == 200
    assert data["type"] == "person"
    assert data["content_results"] == []
    assert data["total_content_results"] == 0
    assert person["id"] in person_ids
    assert all(item["result_type"] == "person" for item in data["person_results"])


def test_search_nolan_ranks_name_matches_for_people(client, db_session):
    first_person_by_name(db_session, "Nolan")

    response = client.get("/search?q=Nolan&type=person&limit=10")
    data = response.json()

    assert response.status_code == 200
    assert data["person_results"]
    assert "Nolan" in data["person_results"][0]["name"]
    assert data["person_results"][0]["match_reason"] in {
        "Matched name",
        "Matched exact name",
    }


def test_search_nolan_returns_credit_connected_content_if_present(client, db_session):
    linked_content = content_ids_linked_to_person_name(db_session, "Nolan")
    linked_content_ids = {row["id"] for row in linked_content}

    response = client.get("/search?q=Nolan&type=content&limit=20")
    data = response.json()
    result_ids = {item["id"] for item in data["content_results"]}

    assert response.status_code == 200
    assert result_ids & linked_content_ids
    assert any(
        item.get("match_reason", "").startswith("Matched ")
        for item in data["content_results"]
        if item["id"] in linked_content_ids
    )


def test_search_pedro_returns_credit_connected_content_if_present(client, db_session):
    linked_content = content_ids_linked_to_person_name(db_session, "Pedro")
    linked_content_ids = {row["id"] for row in linked_content}

    response = client.get("/search?q=Pedro&type=content&limit=20")
    data = response.json()
    result_ids = {item["id"] for item in data["content_results"]}

    assert response.status_code == 200
    assert result_ids & linked_content_ids


def test_search_person_by_partial_name_if_people_exist(client, db_session):
    person = first_person_for_search(db_session)
    partial_name = person["name"].split()[0]

    response = client.get("/search", params={"q": partial_name, "type": "person"})
    data = response.json()
    person_ids = {item["id"] for item in data["person_results"]}

    assert response.status_code == 200
    assert person["id"] in person_ids


def test_search_all_returns_grouped_results(client):
    response = client.get("/search?q=dark")
    data = response.json()

    assert response.status_code == 200
    assert data["type"] == "all"
    assert "content_results" in data
    assert "person_results" in data
    assert data["total_content_results"] >= len(data["content_results"])
    assert data["total_person_results"] >= len(data["person_results"])


def test_search_type_content_returns_only_content(client):
    response = client.get("/search?q=dark&type=content")
    data = response.json()

    assert response.status_code == 200
    assert data["content_results"]
    assert data["person_results"] == []
    assert data["total_person_results"] == 0


def test_search_type_person_returns_only_people_if_people_exist(client, db_session):
    person = first_person_for_search(db_session)

    response = client.get("/search", params={"q": person["name"], "type": "person"})
    data = response.json()

    assert response.status_code == 200
    assert data["content_results"] == []
    assert data["total_content_results"] == 0
    assert data["person_results"]


def test_search_empty_query_returns_empty_grouped_response(client):
    response = client.get("/search?q=   ")
    data = response.json()

    assert response.status_code == 200
    assert data == {
        "query": "",
        "type": "all",
        "content_results": [],
        "person_results": [],
        "total_content_results": 0,
        "total_person_results": 0,
    }


def test_search_no_results_returns_clean_empty_response(client):
    response = client.get("/search?q=zzzz-not-a-real-insightstream-title")
    data = response.json()

    assert response.status_code == 200
    assert data["content_results"] == []
    assert data["person_results"] == []
    assert data["total_content_results"] == 0
    assert data["total_person_results"] == 0
