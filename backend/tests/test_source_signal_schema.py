from sqlalchemy import text


SOURCE_SIGNAL_TABLES = {
    "source_signal_import_runs",
    "content_source_signals",
    "content_watch_guidance",
}


def test_source_signal_tables_exist(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN (
                  'source_signal_import_runs',
                  'content_source_signals',
                  'content_watch_guidance'
              )
            ORDER BY table_name;
            """
        )
    ).mappings().all()

    assert {row["table_name"] for row in rows} == SOURCE_SIGNAL_TABLES


def test_source_signal_tables_have_expected_columns(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name IN (
                  'source_signal_import_runs',
                  'content_source_signals',
                  'content_watch_guidance'
              );
            """
        )
    ).mappings().all()

    columns_by_table = {}
    for row in rows:
        columns_by_table.setdefault(row["table_name"], set()).add(row["column_name"])

    assert {
        "id",
        "run_key",
        "mapping_version",
        "override_version",
        "preview_generator_version",
        "semantic_qa_version",
        "semantic_quality_summary",
        "signals_by_source",
        "db_write_performed",
        "dry_run",
    } <= columns_by_table["source_signal_import_runs"]

    assert {
        "id",
        "content_id",
        "last_signal_run_id",
        "dimension",
        "value",
        "label",
        "confidence",
        "source_names",
        "source_payload",
        "is_active",
    } <= columns_by_table["content_source_signals"]

    assert {
        "content_id",
        "last_signal_run_id",
        "watch_feel",
        "chips",
        "best_for",
        "consider_first",
        "keyword_counts",
        "signal_sources",
        "curated_override_applied",
        "metadata_fallback_applied",
        "storage_ready",
        "frontend_ready",
        "quality_summary",
    } <= columns_by_table["content_watch_guidance"]


def test_source_signal_constraints_and_indexes_exist(db_session):
    constraints = db_session.execute(
        text(
            """
            SELECT table_name, constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'public'
              AND table_name IN (
                  'source_signal_import_runs',
                  'content_source_signals',
                  'content_watch_guidance'
              );
            """
        )
    ).mappings().all()
    constraints_by_table = {}
    for row in constraints:
        constraints_by_table.setdefault(row["table_name"], set()).add(
            row["constraint_name"]
        )

    assert "source_signal_import_runs_run_key_key" in constraints_by_table[
        "source_signal_import_runs"
    ]
    assert (
        "uq_content_source_signals_content_dimension_value"
        in constraints_by_table["content_source_signals"]
    )
    assert "content_watch_guidance_pkey" in constraints_by_table[
        "content_watch_guidance"
    ]

    indexes = db_session.execute(
        text(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename IN (
                  'source_signal_import_runs',
                  'content_source_signals',
                  'content_watch_guidance'
              );
            """
        )
    ).mappings().all()
    index_names = {row["indexname"] for row in indexes}

    assert "idx_source_signal_import_runs_run_key" in index_names
    assert "idx_content_source_signals_content_id" in index_names
    assert "idx_content_source_signals_content_dimension" in index_names
    assert "idx_content_watch_guidance_content_id" in index_names
