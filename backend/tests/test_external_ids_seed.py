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
    assert counts.get("imdb") == 15


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


def test_verified_imdb_ids_exist_for_seeded_titles(db_session):
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
                  'The Dark Knight',
                  'Parasite',
                  'Dune: Part Two',
                  'Barbie',
                  'Spider-Man: Across the Spider-Verse',
                  'Red Notice',
                  'Breaking Bad',
                  'The Mandalorian',
                  'The Last of Us',
                  'Stranger Things',
                  'The Boys',
                  'Dark',
                  'The Witcher'
              );
            """
        )
    ).mappings().all()

    imdb_ids = {row["title"]: row["external_id"] for row in rows}

    assert imdb_ids == {
        "Interstellar": "tt0816692",
        "Inception": "tt1375666",
        "The Dark Knight": "tt0468569",
        "Parasite": "tt6751668",
        "Dune: Part Two": "tt15239678",
        "Barbie": "tt1517268",
        "Spider-Man: Across the Spider-Verse": "tt9362722",
        "Red Notice": "tt7991608",
        "Breaking Bad": "tt0903747",
        "The Mandalorian": "tt8111088",
        "The Last of Us": "tt3581920",
        "Stranger Things": "tt4574334",
        "The Boys": "tt1190634",
        "Dark": "tt5753856",
        "The Witcher": "tt5180504",
    }


def test_mandalorian_has_verified_tmdb_and_imdb_external_ids(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT c.title, c.tmdb_id, ei.source_name, ei.external_id
            FROM content c
            JOIN external_ids ei ON ei.content_id = c.id
            WHERE c.title = 'The Mandalorian'
            ORDER BY ei.source_name;
            """
        )
    ).mappings().all()

    ids = {row["source_name"]: row["external_id"] for row in rows}

    assert rows
    assert rows[0]["title"] == "The Mandalorian"
    assert rows[0]["tmdb_id"] == 82856
    assert ids == {
        "imdb": "tt8111088",
        "tmdb": "82856",
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
