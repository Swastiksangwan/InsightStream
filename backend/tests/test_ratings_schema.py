from sqlalchemy import text


def test_ratings_foundation_tables_exist(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('rating_sources', 'content_ratings')
            ORDER BY table_name;
            """
        )
    ).mappings().all()

    assert {row["table_name"] for row in rows} == {
        "content_ratings",
        "rating_sources",
    }


def test_ratings_foundation_tables_have_expected_columns(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name IN ('rating_sources', 'content_ratings');
            """
        )
    ).mappings().all()

    columns_by_table = {}
    for row in rows:
        columns_by_table.setdefault(row["table_name"], set()).add(row["column_name"])

    assert {
        "id",
        "source_name",
        "display_name",
        "source_category",
        "raw_score_scale_default",
        "weight",
        "is_active",
        "source_url",
        "notes",
        "created_at",
        "updated_at",
    } <= columns_by_table["rating_sources"]

    assert {
        "id",
        "content_id",
        "rating_source_id",
        "raw_score",
        "raw_score_scale",
        "normalized_score",
        "vote_count",
        "rating_count_label",
        "rating_url",
        "source_payload",
        "fetched_at",
        "created_at",
        "updated_at",
    } <= columns_by_table["content_ratings"]


def test_ratings_foundation_constraints_exist(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT table_name, constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'public'
              AND table_name IN ('rating_sources', 'content_ratings');
            """
        )
    ).mappings().all()

    constraints_by_table = {}
    for row in rows:
        constraints_by_table.setdefault(row["table_name"], set()).add(
            row["constraint_name"]
        )

    assert "rating_sources_source_name_key" in constraints_by_table["rating_sources"]
    assert (
        "uq_content_ratings_content_source"
        in constraints_by_table["content_ratings"]
    )
    assert (
        "chk_content_ratings_normalized_score"
        in constraints_by_table["content_ratings"]
    )
    assert (
        "chk_content_ratings_raw_score_scale"
        in constraints_by_table["content_ratings"]
    )
    assert (
        "chk_content_ratings_vote_count"
        in constraints_by_table["content_ratings"]
    )


def test_ratings_foundation_indexes_exist(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT tablename, indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename IN ('rating_sources', 'content_ratings');
            """
        )
    ).mappings().all()
    indexes = {row["indexname"] for row in rows}

    assert "idx_content_ratings_content_id" in indexes
    assert "idx_content_ratings_rating_source_id" in indexes
    assert "idx_content_ratings_source_normalized_score" in indexes
    assert "idx_rating_sources_source_name" in indexes


def test_tmdb_rating_source_is_seeded(db_session):
    row = db_session.execute(
        text(
            """
            SELECT
                source_name,
                display_name,
                source_category,
                raw_score_scale_default,
                weight,
                is_active
            FROM rating_sources
            WHERE source_name = 'tmdb';
            """
        )
    ).mappings().first()

    assert row is not None
    assert row["display_name"] == "TMDb"
    assert row["source_category"] == "audience"
    assert float(row["raw_score_scale_default"]) == 10
    assert float(row["weight"]) == 1
    assert row["is_active"] is True
