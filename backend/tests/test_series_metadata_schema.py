from sqlalchemy import text


def test_content_series_metadata_table_exists(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'content_series_metadata';
            """
        )
    ).mappings().all()

    assert [row["table_name"] for row in rows] == ["content_series_metadata"]


def test_content_series_metadata_has_expected_columns(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'content_series_metadata';
            """
        )
    ).mappings().all()
    columns = {row["column_name"] for row in rows}

    assert {
        "content_id",
        "number_of_seasons",
        "number_of_episodes",
        "series_status",
        "series_status_normalized",
        "in_production",
        "first_air_date",
        "last_air_date",
        "last_episode_air_date",
        "next_episode_air_date",
        "series_type",
        "released_seasons_count",
        "announced_seasons_count",
        "next_season_number",
        "next_season_air_date",
        "next_season_year",
        "has_announced_season",
        "season_summary_note",
        "source_name",
        "last_refreshed_at",
    } <= columns


def test_content_series_metadata_indexes_exist(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'content_series_metadata';
            """
        )
    ).mappings().all()
    indexes = {row["indexname"] for row in rows}

    assert "idx_content_series_metadata_status_normalized" in indexes
    assert "idx_content_series_metadata_last_air_date" in indexes
    assert "idx_content_series_metadata_next_episode_air_date" in indexes
    assert "idx_content_series_metadata_has_announced_season" in indexes
    assert "idx_content_series_metadata_next_season_air_date" in indexes
