import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
for import_root in (REPO_ROOT, BACKEND_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from app.core.database_safety import (
    DatabaseSafetyError, redact_database_urls, test_database_url, verify_test_connection, verify_test_target,
)
from scripts.database_snapshot import connect
from scripts.local_database import assert_no_development_write_access
from scripts.test_support import acquire_test_lock, reset_fixture, verify_fixture_schema


def pytest_addoption(parser):
    parser.addoption("--unit-only", action="store_true", help="Run tests with no database/client fixtures; no PostgreSQL required")
    parser.addoption("--run-migration-tests", action="store_true", help="Explicitly allow historical migration SQL in the disposable test database")


def pytest_configure(config):
    config._test_lock = None
    config._test_connection_guard = None
    if config.getoption("--unit-only"):
        os.environ["INSIGHTSTREAM_ENV"] = "unit-test"
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("TEST_DATABASE_URL", None)
        return
    if "app.db.session" in sys.modules or "app.core.config" in sys.modules:
        raise pytest.UsageError("Application database configuration was imported before the test safety gate.")
    try:
        raw_url = test_database_url(os.environ)
        verify_test_target(raw_url)
        assert_no_development_write_access(raw_url)
        lock = connect(raw_url)
        try:
            verify_fixture_schema(lock)
            acquire_test_lock(lock)
        except Exception:
            lock.close()
            raise
        config._test_lock = lock
    except DatabaseSafetyError as exc:
        raise pytest.UsageError(str(exc)) from None
    except Exception:
        raise pytest.UsageError("Test database safety verification failed; no test modules were imported.") from None
    os.environ["DATABASE_URL"] = raw_url
    os.environ.pop("TMDB_READ_ACCESS_TOKEN", None)
    config._test_database_url = raw_url

    def guard_connection(dbapi_connection, _record):
        try:
            verify_test_connection(dbapi_connection)
        finally:
            dbapi_connection.rollback()

    event.listen(Engine, "connect", guard_connection)
    config._test_connection_guard = guard_connection


def pytest_unconfigure(config):
    guard = getattr(config, "_test_connection_guard", None)
    if guard is not None:
        event.remove(Engine, "connect", guard)
    lock = getattr(config, "_test_lock", None)
    if lock is not None:
        lock.close()


def pytest_collection_modifyitems(config, items):
    selected, deselected = [], []
    for item in items:
        database = bool({"db_session", "client", "database_state"} & set(item.fixturenames))
        if database:
            item.add_marker(pytest.mark.database)
        if database and config.getoption("--unit-only"):
            deselected.append(item)
            continue
        if item.get_closest_marker("migration") and not config.getoption("--run-migration-tests"):
            item.add_marker(pytest.mark.skip(reason="Historical migration execution requires --run-migration-tests; not replayed during Milestone 1."))
        selected.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.failed:
        rendered = str(report.longrepr)
        redacted = redact_database_urls(rendered)
        if redacted != rendered:
            report.longrepr = redacted
    report.sections = [(name, redact_database_urls(value)) for name, value in report.sections]


@pytest.fixture
def database_state(request):
    if request.config.getoption("--unit-only"):
        raise pytest.UsageError("A unit-only test requested a database fixture.")
    connection = connect(request.config._test_database_url)
    try:
        reset_fixture(connection)
        yield
    finally:
        try:
            connection.rollback()
            reset_fixture(connection)
        finally:
            connection.close()


@pytest.fixture
def client(database_state):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as instance:
        yield instance


@pytest.fixture
def db_session(database_state):
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        yield session


@pytest.fixture
def test_user_id(db_session):
    row = db_session.execute(
        text("SELECT id FROM users WHERE email=:email"), {"email": "test@example.com"}
    ).mappings().first()
    assert row is not None, "Expected deterministic test user."
    return row["id"]


@pytest.fixture
def content_id_by_title(db_session):
    def find(title):
        row = db_session.execute(text("SELECT id FROM content WHERE title=:title"), {"title": title}).mappings().first()
        assert row is not None, f"Expected fixture title {title!r}."
        return row["id"]
    return find
