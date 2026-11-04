"""Deterministic fixture reset, exclusively for the marked disposable test DB."""

import hashlib
import json
import re
from pathlib import Path

from psycopg2 import sql

from app.core.database_safety import DatabaseSafetyError, verify_test_connection


BACKEND_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_VERSION = "deterministic-catalog-v1"
TEST_LOCK_KEY = 182736451


def acquire_test_lock(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (TEST_LOCK_KEY,))
        if not cursor.fetchone()[0]:
            raise DatabaseSafetyError("Another test/reset process holds the disposable database lock.")
    connection.rollback()


def schema_sources():
    return {
        name: hashlib.sha256((BACKEND_ROOT / name).read_bytes()).hexdigest()
        for name in ("schema.sql", "indexes.sql")
    }


def fixture_sources():
    return {
        name: hashlib.sha256((BACKEND_ROOT / name).read_bytes()).hexdigest()
        for name in ("sample_data.sql", "tests/fixtures/catalog.sql")
    }


def expected_tables():
    return sorted(re.findall(
        r"CREATE TABLE(?: IF NOT EXISTS)? (\w+)",
        (BACKEND_ROOT / "schema.sql").read_text(),
    ))


def verify_fixture_schema(connection):
    identity = verify_test_connection(connection)
    marker = identity["marker"]
    if marker.get("fixture") != FIXTURE_VERSION or marker.get("schema_sources") != schema_sources():
        raise DatabaseSafetyError("Test schema baseline differs; inspect it before an explicit test-only reset.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        tables = [row[0] for row in cursor.fetchall()]
    from scripts.migration_management import inspect

    state = inspect(connection, identity["database"])
    if state["pending"]:
        raise DatabaseSafetyError("Pending managed test migrations; inspect/preview and explicitly apply them before pytest.")
    if not state["baseline_registered"] and tables != expected_tables():
        raise DatabaseSafetyError("Unexpected or missing test tables; automatic fixture reset refused.")
    return {**identity, "fixture_tables": tables}


def reset_fixture(connection):
    """Reset only this fixture's known tables, including after committed tests.

    Tests exercise independent importer connections and real commits, so an outer
    rollback alone would not isolate them. Rebuild small test DATA per case; never
    rebuild a schema or restore the development snapshot here.
    """
    verified = verify_fixture_schema(connection)
    connection.rollback()
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(
                sql.SQL(",").join(sql.Identifier("public", name) for name in verified["fixture_tables"])
            ))
            for path in (BACKEND_ROOT / "sample_data.sql", BACKEND_ROOT / "tests/fixtures/catalog.sql"):
                script = re.sub(r"^\s*(BEGIN|COMMIT);\s*$", "", path.read_text(), flags=re.MULTILINE)
                cursor.execute(script)
            # Stable timestamps make fixtures independent of run date and local data.
            cursor.execute("""SELECT table_name,column_name FROM information_schema.columns
                WHERE table_schema='public' AND data_type LIKE 'timestamp%'
                ORDER BY table_name,column_name""")
            for table, column in cursor.fetchall():
                cursor.execute(sql.SQL("UPDATE public.{} SET {}=%s WHERE {} IS NOT NULL").format(
                    sql.Identifier(table), sql.Identifier(column), sql.Identifier(column)
                ), ("2026-07-10T00:00:00Z",))


def marker():
    return json.dumps({
        "purpose": "insightstream-disposable-test-v1",
        "fixture": FIXTURE_VERSION,
        "schema_sources": schema_sources(),
    }, sort_keys=True)
