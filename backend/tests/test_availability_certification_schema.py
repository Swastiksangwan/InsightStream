from sqlalchemy import text


def test_availability_and_certification_tables_exist(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN (
                  'content_availability',
                  'content_certifications',
                  'content_platforms'
              )
            ORDER BY table_name;
            """
        )
    ).mappings().all()

    table_names = {row["table_name"] for row in rows}

    assert table_names == {
        "content_availability",
        "content_certifications",
        "content_platforms",
    }


def test_availability_and_certification_tables_have_expected_columns(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name IN (
                  'content',
                  'content_availability',
                  'content_certifications'
              );
            """
        )
    ).mappings().all()

    columns_by_table = {}
    for row in rows:
        columns_by_table.setdefault(row["table_name"], set()).add(row["column_name"])

    assert "age_rating" in columns_by_table["content"]

    assert {
        "id",
        "content_id",
        "platform_id",
        "availability_type",
        "region_code",
        "source_name",
        "source_provider_id",
        "display_priority",
        "fetched_at",
        "updated_at",
    } <= columns_by_table["content_availability"]

    assert {
        "id",
        "content_id",
        "certification",
        "country_code",
        "rating_system",
        "source_name",
        "source_priority",
        "notes",
        "fetched_at",
        "updated_at",
    } <= columns_by_table["content_certifications"]


def test_availability_and_certification_unique_constraints_exist(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT table_name, constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'public'
              AND table_name IN ('content_availability', 'content_certifications')
              AND constraint_type = 'UNIQUE';
            """
        )
    ).mappings().all()

    constraints_by_table = {}
    for row in rows:
        constraints_by_table.setdefault(row["table_name"], set()).add(
            row["constraint_name"]
        )

    assert (
        "uq_content_availability_content_platform_type_region_source"
        in constraints_by_table["content_availability"]
    )
    assert (
        "uq_content_certifications_content_country_system_source"
        in constraints_by_table["content_certifications"]
    )
