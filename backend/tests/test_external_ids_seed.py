from sqlalchemy import text


def test_external_ids_table_has_seeded_rows(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT source_name, COUNT(*) AS total
            FROM external_ids
            GROUP BY source_name;
            """
        )
    ).mappings().all()

    counts = {row["source_name"]: row["total"] for row in rows}

    assert counts.get("tmdb") == 15
    assert counts.get("imdb") == 5


def test_every_seeded_tmdb_content_has_tmdb_external_id(db_session):
    row = db_session.execute(
        text(
            """
            SELECT COUNT(*) AS total
            FROM content c
            LEFT JOIN external_ids ei
              ON ei.content_id = c.id
             AND ei.source_name = 'tmdb'
             AND ei.external_id = c.tmdb_id::TEXT
            WHERE c.tmdb_id IS NOT NULL
              AND ei.id IS NULL;
            """
        )
    ).mappings().first()

    assert row["total"] == 0


def test_verified_imdb_ids_exist_for_tested_titles(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT c.title, ei.external_id
            FROM content c
            JOIN external_ids ei ON ei.content_id = c.id
            WHERE ei.source_name = 'imdb'
              AND c.title IN (
                  'Interstellar',
                  'Inception',
                  'Breaking Bad',
                  'The Dark Knight',
                  'Dune: Part Two'
              );
            """
        )
    ).mappings().all()

    imdb_ids = {row["title"]: row["external_id"] for row in rows}

    assert imdb_ids == {
        "Interstellar": "tt0816692",
        "Inception": "tt1375666",
        "Breaking Bad": "tt0903747",
        "The Dark Knight": "tt0468569",
        "Dune: Part Two": "tt15239678",
    }


def test_external_ids_have_no_duplicate_source_external_id_pairs(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT source_name, external_id, COUNT(*) AS total
            FROM external_ids
            GROUP BY source_name, external_id
            HAVING COUNT(*) > 1;
            """
        )
    ).mappings().all()

    assert rows == []
