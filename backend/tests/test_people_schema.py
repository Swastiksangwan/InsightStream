from sqlalchemy import text


def test_people_credit_tables_exist(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('people', 'person_external_ids', 'content_people')
            ORDER BY table_name;
            """
        )
    ).mappings().all()

    table_names = {row["table_name"] for row in rows}

    assert table_names == {
        "content_people",
        "people",
        "person_external_ids",
    }


def test_people_credit_tables_have_expected_columns(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name IN ('people', 'person_external_ids', 'content_people');
            """
        )
    ).mappings().all()

    columns_by_table = {}
    for row in rows:
        columns_by_table.setdefault(row["table_name"], set()).add(row["column_name"])

    assert {
        "id",
        "name",
        "profile_url",
        "known_for_department",
        "biography",
        "created_at",
        "updated_at",
    } <= columns_by_table["people"]

    assert {
        "id",
        "person_id",
        "source_name",
        "external_id",
        "source_url",
        "created_at",
        "updated_at",
    } <= columns_by_table["person_external_ids"]

    assert {
        "id",
        "content_id",
        "person_id",
        "role_type",
        "character_name",
        "job",
        "department",
        "display_order",
        "source_name",
        "source_credit_id",
        "created_at",
        "updated_at",
    } <= columns_by_table["content_people"]


def test_person_external_ids_unique_constraints_exist(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'public'
              AND table_name = 'person_external_ids'
              AND constraint_type = 'UNIQUE';
            """
        )
    ).mappings().all()

    constraint_names = {row["constraint_name"] for row in rows}

    assert {
        "uq_person_external_ids_person_source",
        "uq_person_external_ids_source_external_id",
    } <= constraint_names


def test_content_people_role_type_check_constraint_exists(db_session):
    row = db_session.execute(
        text(
            """
            SELECT pg_get_constraintdef(c.oid) AS constraint_definition
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
              AND t.relname = 'content_people'
              AND c.contype = 'c'
              AND pg_get_constraintdef(c.oid) ILIKE '%role_type%';
            """
        )
    ).mappings().first()

    assert row is not None
    constraint_definition = row["constraint_definition"]

    for role_type in ("cast", "director", "creator", "crew"):
        assert role_type in constraint_definition
