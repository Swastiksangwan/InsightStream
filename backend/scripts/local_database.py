#!/usr/bin/env python3
"""Small local PostgreSQL tools. Never resets or migrates development."""

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

from dotenv import dotenv_values
from psycopg2 import sql
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database_safety import (
    DatabaseSafetyError, LOCAL_HOSTS, TEST_DATABASE, TEST_ROLE,
    test_database_url, verify_test_target,
)
from scripts.database_snapshot import PRIVATE_ROOT, backup, connect, snapshot, compare_snapshots, restore_verify
from scripts.test_support import acquire_test_lock, marker, reset_fixture, schema_sources, fixture_sources

TEST_ENV = PRIVATE_ROOT / "test.env"


def development_url():
    raw = os.getenv("DATABASE_URL") or dotenv_values(BACKEND_ROOT / ".env").get("DATABASE_URL")
    try:
        url = make_url(raw or "")
    except Exception:
        raise DatabaseSafetyError("Development DATABASE_URL is missing or invalid.") from None
    if url.drivername not in {"postgresql", "postgresql+psycopg2"} or url.host not in LOCAL_HOSTS or url.query or url.database != "insightstream_db":
        raise DatabaseSafetyError("Only the explicit local insightstream_db development target is supported.")
    return url.render_as_string(hide_password=False)


def test_environment(path=TEST_ENV):
    path = Path(path).expanduser()
    if path.exists() and path.stat().st_mode & 0o077:
        raise DatabaseSafetyError("Private test environment file must have mode 0600.")
    return {**{k: v for k, v in dotenv_values(path).items() if v is not None}, **os.environ}


def assert_no_development_write_access(raw_url):
    # Permission introspection only: never attempt an UPDATE/INSERT against dev.
    connection = connect(raw_url, "insightstream_db")
    try:
        connection.set_session(readonly=True)
        with connection.cursor() as cursor:
            cursor.execute("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relkind IN ('r','p') AND (
                has_table_privilege(current_user,c.oid,'INSERT') OR
                has_table_privilege(current_user,c.oid,'UPDATE') OR
                has_table_privilege(current_user,c.oid,'DELETE') OR
                has_table_privilege(current_user,c.oid,'TRUNCATE') OR
                pg_get_userbyid(c.relowner)=current_user)""")
            writable = cursor.fetchone()[0]
            cursor.execute("SELECT has_database_privilege(current_user,current_database(),'CREATE')")
            can_create = cursor.fetchone()[0]
            cursor.execute("""SELECT count(*) FROM pg_namespace
                WHERE nspname NOT LIKE 'pg_%' AND nspname<>'information_schema'
                AND has_schema_privilege(current_user,oid,'CREATE')""")
            creatable_schemas = cursor.fetchone()[0]
            cursor.execute("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relkind='S' AND (
                has_sequence_privilege(current_user,c.oid,'USAGE') OR
                has_sequence_privilege(current_user,c.oid,'UPDATE'))""")
            writable_sequences = cursor.fetchone()[0]
        if writable or can_create or creatable_schemas or writable_sequences:
            raise DatabaseSafetyError("Test role has development write/DDL privileges; tests refused.")
        return {
            "development_writable_tables": writable,
            "development_writable_sequences": writable_sequences,
            "development_creatable_schemas": creatable_schemas,
            "development_create_privilege": can_create,
        }
    finally:
        connection.rollback()
        connection.close()


def prepare_test(raw_url):
    if TEST_ENV.exists():
        environment = test_environment()
        target = test_database_url(environment)
        identity = verify_test_target(target)
        return {"status": "already prepared; no database was overwritten", "database": identity["database"], **assert_no_development_write_access(target)}
    admin = connect(raw_url, "postgres")
    try:
        admin.autocommit = True
        with admin.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname=%s", (TEST_DATABASE,))
            database_exists = cursor.fetchone() is not None
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (TEST_ROLE,))
            role_exists = cursor.fetchone() is not None
            if database_exists or role_exists:
                raise DatabaseSafetyError("Test database or role already exists without this private configuration; inspect it, never overwrite it.")
            password = secrets.token_urlsafe(32)
            cursor.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS").format(sql.Identifier(TEST_ROLE)), (password,))
            cursor.execute(sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(sql.Identifier(TEST_DATABASE), sql.Identifier(TEST_ROLE)))
            cursor.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(TEST_DATABASE)))
            cursor.execute(sql.SQL("COMMENT ON DATABASE {} IS %s").format(sql.Identifier(TEST_DATABASE)), (marker(),))
        target = make_url(raw_url).set(username=TEST_ROLE, password=password, database=TEST_DATABASE).render_as_string(hide_password=False)
        PRIVATE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
        PRIVATE_ROOT.chmod(0o700)
        # Never overwrite an existing credential file, even after partial setup.
        fd = os.open(TEST_ENV, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write("INSIGHTSTREAM_ENV=test\nTEST_DATABASE_URL='" + target + "'\n")
    finally:
        admin.close()
    verify_test_target(target)
    assert_no_development_write_access(target)
    connection = connect(target)
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute((BACKEND_ROOT / "schema.sql").read_text())
                cursor.execute((BACKEND_ROOT / "indexes.sql").read_text())
        reset_fixture(connection)
    finally:
        connection.close()
    return {"status": "created from declarative schema and deterministic fixtures", "database": TEST_DATABASE, "role": TEST_ROLE, "private_environment_file": str(TEST_ENV), **assert_no_development_write_access(target)}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    command = commands.add_parser("backup", help="Consistent dev backup AND restore into a new unique verification database")
    command.add_argument("--backup-dir", type=Path)
    command = commands.add_parser("restore-verify", help="Verify checksum and restore ONLY into a new unique database")
    command.add_argument("--manifest", required=True, type=Path)
    command = commands.add_parser("fingerprint", help="Read-only development fingerprint and optional baseline comparison")
    command.add_argument("--manifest", type=Path)
    commands.add_parser("prepare-test", help="Create a new dedicated test role/database; never overwrite existing targets")
    commands.add_parser("check-test", help="Verify actual test identity and absence of development write permissions")
    command = commands.add_parser("reset-test", help="Reset deterministic DATA in the verified disposable test database only")
    command.add_argument("--confirm-reset", required=True, choices=[TEST_DATABASE])
    commands.add_parser("status", help="Read-only development schema fingerprint; no migration history is inferred")
    return result


def main(argv=None):
    os.umask(0o077)
    args = parser().parse_args(argv)
    if args.command in {"check-test", "reset-test"}:
        target = test_database_url(test_environment())
        identity = verify_test_target(target)
        permissions = assert_no_development_write_access(target)
        if args.command == "reset-test":
            connection = connect(target)
            try:
                acquire_test_lock(connection)
                reset_fixture(connection)
            finally:
                connection.close()
        print(json.dumps({"database": identity["database"], "role": identity["role"], **permissions, "status": "verified" if args.command == "check-test" else "fixture data reset"}, indent=2))
        return 0
    raw_url = development_url()
    if args.command == "backup":
        result = backup(raw_url, args.backup_dir)
    elif args.command == "restore-verify":
        result = restore_verify(raw_url, args.manifest)
    elif args.command == "prepare-test":
        result = prepare_test(raw_url)
    else:
        connection = connect(raw_url)
        try:
            state = snapshot(connection)
        finally:
            connection.rollback()
            connection.close()
        if state["database"] != "insightstream_db":
            raise DatabaseSafetyError("Connected development identity mismatch.")
        result = {"database": state["database"], "server_version": state["version"], "catalog": state["catalog"], "tables": state["tables"], "schema_sha256": state["schema_sha256"], "schema_object_counts": state["schema_object_counts"], "schema_sources": schema_sources(), "fixture_sources": fixture_sources(), "migration_history": "UNTRACKED: no migrations applied by this tool"}
        if getattr(args, "manifest", None):
            expected = json.loads(args.manifest.read_text())["source_snapshot"]
            result["baseline_comparisons"] = compare_snapshots(expected, state)
            if not all(result["baseline_comparisons"].values()):
                print(json.dumps(result, indent=2))
                return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DatabaseSafetyError, RuntimeError) as exc:
        print("STOPPED: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
    except Exception:
        print("STOPPED: local PostgreSQL operation failed; credentials and row values withheld.", file=sys.stderr)
        raise SystemExit(2)
