from sqlalchemy import text


def titles_from_content_list(response_json):
    return {item["title"] for item in response_json}


def content_ids_for_titles(content_id_by_title, titles):
    return [content_id_by_title(title) for title in titles]


def reset_user_watch_state(db_session, user_id, watched_ids=None, watch_later_ids=None):
    watched_ids = watched_ids or []
    watch_later_ids = watch_later_ids or []
    content_ids = watched_ids + watch_later_ids

    if content_ids:
        db_session.execute(
            text("""
                DELETE FROM watch_later
                WHERE user_id = :user_id
                  AND content_id = ANY(:content_ids);
            """),
            {"user_id": user_id, "content_ids": content_ids},
        )
        db_session.execute(
            text("""
                DELETE FROM watched
                WHERE user_id = :user_id
                  AND content_id = ANY(:content_ids);
            """),
            {"user_id": user_id, "content_ids": content_ids},
        )

    for content_id in watched_ids:
        db_session.execute(
            text("""
                INSERT INTO watched (user_id, content_id)
                VALUES (:user_id, :content_id)
                ON CONFLICT (user_id, content_id) DO NOTHING;
            """),
            {"user_id": user_id, "content_id": content_id},
        )

    for content_id in watch_later_ids:
        db_session.execute(
            text("""
                INSERT INTO watch_later (user_id, content_id)
                VALUES (:user_id, :content_id)
                ON CONFLICT (user_id, content_id) DO NOTHING;
            """),
            {"user_id": user_id, "content_id": content_id},
        )

    db_session.commit()


def test_get_watched_for_seeded_user(
    client,
    db_session,
    test_user_id,
    content_id_by_title,
):
    watched_titles = ["Interstellar", "Inception"]
    reset_user_watch_state(
        db_session,
        test_user_id,
        watched_ids=content_ids_for_titles(content_id_by_title, watched_titles),
    )

    response = client.get(f"/watched/{test_user_id}")
    data = response.json()

    assert response.status_code == 200
    assert set(watched_titles) <= titles_from_content_list(data)


def test_get_watch_later_for_seeded_user(
    client,
    db_session,
    test_user_id,
    content_id_by_title,
):
    watch_later_titles = ["The Mandalorian", "Dune: Part Two"]
    reset_user_watch_state(
        db_session,
        test_user_id,
        watch_later_ids=content_ids_for_titles(content_id_by_title, watch_later_titles),
    )

    response = client.get(f"/watch-later/{test_user_id}")
    data = response.json()

    assert response.status_code == 200
    assert set(watch_later_titles) <= titles_from_content_list(data)


def test_seeded_watch_states_do_not_overlap(
    client,
    db_session,
    test_user_id,
    content_id_by_title,
):
    reset_user_watch_state(
        db_session,
        test_user_id,
        watched_ids=content_ids_for_titles(
            content_id_by_title,
            ["Interstellar", "Inception"],
        ),
        watch_later_ids=content_ids_for_titles(
            content_id_by_title,
            ["The Mandalorian", "Dune: Part Two"],
        ),
    )

    watched_response = client.get(f"/watched/{test_user_id}")
    watch_later_response = client.get(f"/watch-later/{test_user_id}")

    assert watched_response.status_code == 200
    assert watch_later_response.status_code == 200

    watched_titles = titles_from_content_list(watched_response.json())
    watch_later_titles = titles_from_content_list(watch_later_response.json())

    assert watched_titles.isdisjoint(watch_later_titles)
