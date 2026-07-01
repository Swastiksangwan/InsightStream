from sqlalchemy import text


def test_tmdb_keyword_tables_exist(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('keyword_sources', 'provider_keywords', 'content_keywords')
            ORDER BY table_name;
            """
        )
    ).mappings().all()

    assert {row["table_name"] for row in rows} == {
        "content_keywords",
        "keyword_sources",
        "provider_keywords",
    }


def test_tmdb_keyword_tables_have_expected_columns(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name IN ('keyword_sources', 'provider_keywords', 'content_keywords');
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
        "is_active",
        "created_at",
        "updated_at",
    } <= columns_by_table["keyword_sources"]

    assert {
        "id",
        "source_id",
        "external_keyword_id",
        "keyword_name",
        "normalized_keyword_name",
        "created_at",
        "updated_at",
    } <= columns_by_table["provider_keywords"]
    assert "provider_keyword_id" not in columns_by_table["provider_keywords"]

    assert {
        "id",
        "content_id",
        "keyword_id",
        "source_id",
        "confidence",
        "raw_payload",
        "first_seen_at",
        "last_seen_at",
        "fetched_at",
        "source_preview_generated_at",
        "import_run_id",
        "import_report_path",
        "created_at",
        "updated_at",
    } <= columns_by_table["content_keywords"]
    assert "provider_keyword_id" not in columns_by_table["content_keywords"]


def test_tmdb_keyword_constraints_exist(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT table_name, constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'public'
              AND table_name IN ('keyword_sources', 'provider_keywords', 'content_keywords');
            """
        )
    ).mappings().all()

    constraints_by_table = {}
    for row in rows:
        constraints_by_table.setdefault(row["table_name"], set()).add(
            row["constraint_name"]
        )

    assert "keyword_sources_source_name_key" in constraints_by_table["keyword_sources"]
    assert (
        "uq_provider_keywords_source_external_keyword"
        in constraints_by_table["provider_keywords"]
    )
    assert (
        "uq_content_keywords_content_keyword_source"
        in constraints_by_table["content_keywords"]
    )


def test_tmdb_keyword_indexes_exist(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT tablename, indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename IN ('keyword_sources', 'provider_keywords', 'content_keywords');
            """
        )
    ).mappings().all()
    indexes = {row["indexname"] for row in rows}

    assert "idx_keyword_sources_source_name" in indexes
    assert "idx_provider_keywords_source_external_keyword" in indexes
    assert "idx_provider_keywords_normalized_keyword_name" in indexes
    assert "idx_content_keywords_content_id" in indexes
    assert "idx_content_keywords_keyword_id" in indexes
    assert "idx_content_keywords_source_id" in indexes
    assert "idx_content_keywords_content_source" in indexes


def test_tmdb_keyword_source_is_seeded(db_session):
    row = db_session.execute(
        text(
            """
            SELECT source_name, display_name, is_active
            FROM keyword_sources
            WHERE source_name = 'tmdb';
            """
        )
    ).mappings().first()

    assert row is not None
    assert row["display_name"] == "TMDb"
    assert row["is_active"] is True
