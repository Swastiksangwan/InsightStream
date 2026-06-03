def titles_from_content_list(response_json):
    return {item["title"] for item in response_json}


def test_get_watched_for_seeded_user(client, test_user_id):
    response = client.get(f"/watched/{test_user_id}")
    data = response.json()

    assert response.status_code == 200
    assert {"Interstellar", "Inception"} <= titles_from_content_list(data)


def test_get_watch_later_for_seeded_user(client, test_user_id):
    response = client.get(f"/watch-later/{test_user_id}")
    data = response.json()

    assert response.status_code == 200
    assert {"The Mandalorian", "Dune: Part Two"} <= titles_from_content_list(data)


def test_seeded_watch_states_do_not_overlap(client, test_user_id):
    watched_response = client.get(f"/watched/{test_user_id}")
    watch_later_response = client.get(f"/watch-later/{test_user_id}")

    assert watched_response.status_code == 200
    assert watch_later_response.status_code == 200

    watched_titles = titles_from_content_list(watched_response.json())
    watch_later_titles = titles_from_content_list(watch_later_response.json())

    assert watched_titles.isdisjoint(watch_later_titles)
