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


STRICT_CONTENT_TMDB_MIN = 910000000
STRICT_CONTENT_TMDB_MAX = 910000099
STRICT_PEOPLE_NAMES = [
    "David House",
    "Strict Search Biography Only",
    "Strict Search Credit Title Person",
    "Strict Search Department Only",
    "Rankperson",
    "Rankperson Alpha",
    "The Rankperson Beta",
    "Prerankperson Gamma",
]
STRICT_GENRE_NAME = "Strict Search House Genre"


def cleanup_strict_search_fixture(db_session):
    params = {
        "tmdb_min": STRICT_CONTENT_TMDB_MIN,
        "tmdb_max": STRICT_CONTENT_TMDB_MAX,
        "people_names": STRICT_PEOPLE_NAMES,
        "genre_name": STRICT_GENRE_NAME,
    }

    db_session.execute(
        text("""
            DELETE FROM content_people
            WHERE content_id IN (
                SELECT id FROM content
                WHERE tmdb_id BETWEEN :tmdb_min AND :tmdb_max
            )
            OR person_id IN (
                SELECT id FROM people
                WHERE name = ANY(:people_names)
            );
        """),
        params,
    )
    db_session.execute(
        text("""
            DELETE FROM content_genres
            WHERE content_id IN (
                SELECT id FROM content
                WHERE tmdb_id BETWEEN :tmdb_min AND :tmdb_max
            )
            OR genre_id IN (
                SELECT id FROM genres
                WHERE name = :genre_name
            );
        """),
        params,
    )
    db_session.execute(
        text("""
            DELETE FROM content
            WHERE tmdb_id BETWEEN :tmdb_min AND :tmdb_max;
        """),
        params,
    )
    db_session.execute(
        text("""
            DELETE FROM people
            WHERE name = ANY(:people_names);
        """),
        params,
    )
    db_session.execute(
        text("""
            DELETE FROM genres
            WHERE name = :genre_name;
        """),
        params,
    )
    db_session.commit()


def insert_content_fixture(
    db_session,
    *,
    tmdb_id,
    title,
    original_title=None,
    overview=None,
):
    return db_session.execute(
        text("""
            INSERT INTO content (
                tmdb_id,
                title,
                original_title,
                content_type,
                overview,
                release_date,
                year,
                age_rating
            )
            VALUES (
                :tmdb_id,
                :title,
                :original_title,
                'movie',
                :overview,
                DATE '2024-01-01',
                2024,
                'UA'
            )
            RETURNING id;
        """),
        {
            "tmdb_id": tmdb_id,
            "title": title,
            "original_title": original_title,
            "overview": overview,
        },
    ).scalar_one()


def insert_person_fixture(
    db_session,
    *,
    name,
    biography=None,
    known_for_department="Acting",
):
    return db_session.execute(
        text("""
            INSERT INTO people (
                name,
                biography,
                known_for_department
            )
            VALUES (
                :name,
                :biography,
                :known_for_department
            )
            RETURNING id;
        """),
        {
            "name": name,
            "biography": biography,
            "known_for_department": known_for_department,
        },
    ).scalar_one()


@pytest.fixture
def strict_search_fixture(db_session):
    cleanup_strict_search_fixture(db_session)

    exact_content_id = insert_content_fixture(
        db_session,
        tmdb_id=910000001,
        title="House",
    )
    title_contains_id = insert_content_fixture(
        db_session,
        tmdb_id=910000002,
        title="House of the Dragon Test",
    )
    original_title_id = insert_content_fixture(
        db_session,
        tmdb_id=910000003,
        title="Strict Search Localized Title",
        original_title="Casa House",
    )
    overview_only_id = insert_content_fixture(
        db_session,
        tmdb_id=910000004,
        title="Strict Search Overview Only",
        overview="A quiet story about a house that should not match title search.",
    )
    genre_only_id = insert_content_fixture(
        db_session,
        tmdb_id=910000005,
        title="Strict Search Genre Only",
    )
    credit_only_id = insert_content_fixture(
        db_session,
        tmdb_id=910000006,
        title="Strict Search Credit Only",
    )

    for tmdb_id, title in (
        (910000020, "Strictneedle"),
        (910000021, "Strictneedle Alpha"),
        (910000022, "Strictneedle Beta"),
        (910000023, "The Strictneedle File"),
        (910000024, "Prestrictneedle"),
    ):
        insert_content_fixture(db_session, tmdb_id=tmdb_id, title=title)

    genre_id = db_session.execute(
        text("""
            INSERT INTO genres (name)
            VALUES (:genre_name)
            ON CONFLICT (name) DO UPDATE
            SET name = EXCLUDED.name
            RETURNING id;
        """),
        {"genre_name": STRICT_GENRE_NAME},
    ).scalar_one()

    db_session.execute(
        text("""
            INSERT INTO content_genres (content_id, genre_id)
            VALUES (:content_id, :genre_id)
            ON CONFLICT (content_id, genre_id) DO NOTHING;
        """),
        {"content_id": genre_only_id, "genre_id": genre_id},
    )

    name_match_id = insert_person_fixture(db_session, name="David House")
    biography_only_id = insert_person_fixture(
        db_session,
        name="Strict Search Biography Only",
        biography="This biography mentions house but should not match person search.",
    )
    credit_title_only_id = insert_person_fixture(
        db_session,
        name="Strict Search Credit Title Person",
    )
    department_only_id = insert_person_fixture(
        db_session,
        name="Strict Search Department Only",
        known_for_department="House Department",
    )

    for name in (
        "Rankperson",
        "Rankperson Alpha",
        "The Rankperson Beta",
        "Prerankperson Gamma",
    ):
        insert_person_fixture(db_session, name=name)

    db_session.execute(
        text("""
            INSERT INTO content_people (
                content_id,
                person_id,
                role_type,
                character_name,
                display_order
            )
            VALUES
                (:credit_only_id, :name_match_id, 'cast', 'Lead', 1),
                (:title_contains_id, :credit_title_only_id, 'cast', 'Guest', 2);
        """),
        {
            "credit_only_id": credit_only_id,
            "title_contains_id": title_contains_id,
            "name_match_id": name_match_id,
            "credit_title_only_id": credit_title_only_id,
        },
    )
    db_session.commit()

    try:
        yield {
            "exact_content_id": exact_content_id,
            "title_contains_id": title_contains_id,
            "original_title_id": original_title_id,
            "overview_only_id": overview_only_id,
            "genre_only_id": genre_only_id,
            "credit_only_id": credit_only_id,
            "name_match_id": name_match_id,
            "biography_only_id": biography_only_id,
            "credit_title_only_id": credit_title_only_id,
            "department_only_id": department_only_id,
        }
    finally:
        cleanup_strict_search_fixture(db_session)


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


def test_search_content_matches_only_title_identity_fields(
    client,
    strict_search_fixture,
):
    response = client.get(
        "/search",
        params={"q": "house", "type": "content", "limit": 30},
    )
    data = response.json()
    titles = [item["title"] for item in data["content_results"]]
    result_ids = {item["id"] for item in data["content_results"]}

    assert response.status_code == 200
    assert titles[0] == "House"
    assert "House of the Dragon Test" in titles
    assert "Strict Search Localized Title" in titles
    assert strict_search_fixture["overview_only_id"] not in result_ids
    assert strict_search_fixture["genre_only_id"] not in result_ids
    assert strict_search_fixture["credit_only_id"] not in result_ids


def test_search_people_matches_only_person_name(
    client,
    strict_search_fixture,
):
    response = client.get(
        "/search",
        params={"q": "house", "type": "person", "limit": 30},
    )
    data = response.json()
    names = [item["name"] for item in data["person_results"]]
    result_ids = {item["id"] for item in data["person_results"]}

    assert response.status_code == 200
    assert "David House" in names
    assert strict_search_fixture["biography_only_id"] not in result_ids
    assert strict_search_fixture["credit_title_only_id"] not in result_ids
    assert strict_search_fixture["department_only_id"] not in result_ids


def test_search_content_ranking_and_tie_order_is_deterministic(
    client,
    strict_search_fixture,
):
    response = client.get(
        "/search",
        params={"q": "strictneedle", "type": "content", "limit": 10},
    )
    data = response.json()
    titles = [item["title"] for item in data["content_results"][:5]]

    assert response.status_code == 200
    assert titles == [
        "Strictneedle",
        "Strictneedle Alpha",
        "Strictneedle Beta",
        "The Strictneedle File",
        "Prestrictneedle",
    ]


def test_search_people_ranking_is_deterministic(client, strict_search_fixture):
    response = client.get(
        "/search",
        params={"q": "rankperson", "type": "person", "limit": 10},
    )
    data = response.json()
    names = [item["name"] for item in data["person_results"][:4]]

    assert response.status_code == 200
    assert names == [
        "Rankperson",
        "Rankperson Alpha",
        "The Rankperson Beta",
        "Prerankperson Gamma",
    ]


def test_search_counts_use_same_strict_filters(client, strict_search_fixture):
    all_response = client.get("/search", params={"q": "house", "limit": 10})
    content_response = client.get(
        "/search",
        params={"q": "house", "type": "content", "limit": 10},
    )
    person_response = client.get(
        "/search",
        params={"q": "house", "type": "person", "limit": 10},
    )
    all_data = all_response.json()
    content_data = content_response.json()
    person_data = person_response.json()

    assert all_response.status_code == 200
    assert content_response.status_code == 200
    assert person_response.status_code == 200
    assert all_data["total_content_results"] == content_data["total_content_results"]
    assert all_data["total_person_results"] == person_data["total_person_results"]


def test_search_pagination_preserves_relevance_order(client, strict_search_fixture):
    first_page = client.get(
        "/search",
        params={"q": "strictneedle", "type": "content", "limit": 2, "offset": 0},
    ).json()
    second_page = client.get(
        "/search",
        params={"q": "strictneedle", "type": "content", "limit": 2, "offset": 2},
    ).json()

    titles = [
        item["title"]
        for item in first_page["content_results"] + second_page["content_results"]
    ]

    assert titles == [
        "Strictneedle",
        "Strictneedle Alpha",
        "Strictneedle Beta",
        "The Strictneedle File",
    ]


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
