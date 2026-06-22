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
