from sqlalchemy import text
import pytest

from app.core import database_safety as safety
from scripts.database_snapshot import connect
from scripts.local_database import assert_no_development_write_access
from scripts.test_support import acquire_test_lock, reset_fixture


def test_application_and_fixture_use_only_the_test_target(db_session):
    from app.db.session import engine

    row = db_session.execute(text("SELECT current_database(),current_user")).one()
    assert tuple(row) == (safety.TEST_DATABASE, safety.TEST_ROLE)
    assert engine.url.database == safety.TEST_DATABASE
    assert engine.url.username == safety.TEST_ROLE
    assert db_session.execute(text("SELECT count(*) FROM content")).scalar_one() == 18


def test_test_role_has_no_development_write_privileges(db_session):
    url = db_session.get_bind().url.render_as_string(hide_password=False)
    result = assert_no_development_write_access(url)
    assert result == {
        "development_writable_tables": 0,
        "development_writable_sequences": 0,
        "development_creatable_schemas": 0,
        "development_create_privilege": False,
    }


def test_fixture_reset_cleans_real_commits_from_independent_connections(db_session):
    url = db_session.get_bind().url.render_as_string(hide_password=False)
    connection = connect(url)
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO content(title,content_type) VALUES ('Committed isolation sentinel','movie')")
        reset_fixture(connection)
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM content WHERE title='Committed isolation sentinel'")
            assert cursor.fetchone()[0] == 0
            cursor.execute("SELECT count(*) FROM content")
            assert cursor.fetchone()[0] == 18
    finally:
        connection.close()


def test_parallel_test_reset_is_refused_while_suite_holds_lock(db_session):
    connection = connect(db_session.get_bind().url)
    try:
        with pytest.raises(safety.DatabaseSafetyError, match="holds the disposable database lock"):
            acquire_test_lock(connection)
    finally:
        connection.close()
