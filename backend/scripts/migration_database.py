"""Explicit local migration targets and disposable test provisioning."""

import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
from datetime import datetime, timezone

from psycopg2 import sql
from sqlalchemy.engine import make_url

from app.core.database_safety import (
    DatabaseSafetyError, LOCAL_HOSTS, TEST_ROLE, test_database_url,
    verify_test_connection,
)
from scripts.database_snapshot import PRIVATE_ROOT, connect, pg_command


SANDBOX_NAME = re.compile(r"insightstream_migrate_[0-9a-f]{12}\Z")
SANDBOX_MARKER = "insightstream-migration-sandbox-v1"


def target_url(target):
    # Local imports avoid loading development configuration during pytest imports.
    from scripts.local_database import development_url, test_environment

    if target == "insightstream_db":
        if os.getenv("INSIGHTSTREAM_ENV") in {"test", "unit-test"}:
            raise DatabaseSafetyError("Migration tests cannot select the development database.")
        return development_url()
    if target == "insightstream_test" or SANDBOX_NAME.fullmatch(target):
        raw = test_database_url(test_environment())
        return make_url(raw).set(database=target).render_as_string(hide_password=False)
    raise DatabaseSafetyError("Unknown migration target; only explicit known local targets are supported.")


def verify_target(connection, target, write=False):
    """Check actual identity before DDL. Never trust a URL/name alone."""
    if target not in {"insightstream_db", "insightstream_test"} and not SANDBOX_NAME.fullmatch(target):
        raise DatabaseSafetyError("Unknown migration target.")
    if write and os.getenv("INSIGHTSTREAM_ENV", "development") not in {"development", "test"}:
        raise DatabaseSafetyError("Migration writes require an explicit local development/test context.")
    with connection.cursor() as cursor:
        cursor.execute("""SELECT current_database(),current_user,inet_server_addr()::text,
            current_setting('server_version_num')::integer,pg_get_userbyid(d.datdba),
            shobj_description(d.oid,'pg_database'),r.rolsuper,r.rolcreatedb,
            r.rolcreaterole,r.rolreplication,r.rolbypassrls,
            EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid)
            FROM pg_database d JOIN pg_roles r ON r.rolname=current_user
            WHERE d.datname=current_database()""")
        row = cursor.fetchone()
    if not row or row[0] != target or not row[2] or not ipaddress.ip_address(row[2].split("/")[0]).is_loopback:
        raise DatabaseSafetyError("Actual migration database/server does not match the explicit local target.")
    if row[3] // 10000 != 18:
        raise DatabaseSafetyError("Migration baselines support PostgreSQL major 18 only.")
    if target == "insightstream_db":
        if os.getenv("INSIGHTSTREAM_ENV") in {"test", "unit-test"}:
            raise DatabaseSafetyError("Development is forbidden in a migration-test process.")
    elif target == "insightstream_test":
        verify_test_connection(connection)
    else:
        try:
            marker = json.loads(row[5] or "{}")
        except (TypeError, ValueError):
            raise DatabaseSafetyError("Migration sandbox marker is invalid.") from None
        if (row[1] != TEST_ROLE or row[4] != TEST_ROLE or any(row[6:])
                or not isinstance(marker, dict) or marker.get("purpose") != SANDBOX_MARKER):
            raise DatabaseSafetyError("Migration sandbox must be marked, owned by the restricted test role, and unprivileged.")
    return {"database": row[0], "role": row[1], "postgresql_major": 18}


def verify_url(raw_url, target):
    try:
        url = make_url(raw_url)
        valid = (url.drivername in {"postgresql", "postgresql+psycopg2"}
                 and url.host in LOCAL_HOSTS and not url.query and url.database == target)
        if target != "insightstream_db":
            valid = valid and url.username == TEST_ROLE and bool(url.password)
        if not valid:
            raise ValueError()
    except Exception:
        raise DatabaseSafetyError("Migration URL must match the explicit supported local target.") from None


def create_sandbox(profile="empty"):
    """Create a new database only; no drop/replace/reset path exists.

    Admin credentials are used only on the maintenance database 'postgres'.
    SQL/schema execution in the new target uses the existing restricted test role.
    """
    from scripts.local_database import (
        development_url, test_environment, assert_no_development_write_access,
    )

    if profile not in {"empty", "live-schema"}:
        raise DatabaseSafetyError("Unknown sandbox profile.")
    admin_url = development_url()
    test_url = test_database_url(test_environment())
    assert_no_development_write_access(test_url)
    target = "insightstream_migrate_" + secrets.token_hex(6)
    administrator = connect(admin_url, "postgres")
    try:
        administrator.autocommit = True
        with administrator.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname=%s", (target,))
            if cursor.fetchone():
                raise DatabaseSafetyError("Sandbox name exists; refusing to replace it.")
            cursor.execute(sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                sql.Identifier(target), sql.Identifier(TEST_ROLE)))
            cursor.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(target)))
            cursor.execute(sql.SQL("COMMENT ON DATABASE {} IS %s").format(sql.Identifier(target)),
                (json.dumps({"purpose": SANDBOX_MARKER, "profile": profile,
                             "created_at": datetime.now(timezone.utc).isoformat()}),))
    finally:
        administrator.close()
    raw = make_url(test_url).set(database=target).render_as_string(hide_password=False)
    if profile == "live-schema":
        # Copy no catalog/users/watch-state data. If the source has already
        # adopted managed versions, include its verified ledger metadata so the
        # clone remains recognizable after future schema changes.
        from scripts.migration_management import inspect

        directory = PRIVATE_ROOT / "migration-checks" / target
        directory.mkdir(parents=True, mode=0o700)
        directory.chmod(0o700)
        archive = directory / "schema.dump"
        source = connect(admin_url)
        try:
            source.set_session(readonly=True, isolation_level="REPEATABLE READ")
            state = inspect(source, "insightstream_db")
            history = []
            schemas = ["--schema=public"]
            with source.cursor() as cursor:
                if state["baseline_registered"]:
                    schemas.append("--schema=insightstream_migrations")
                    cursor.execute("""SELECT version,kind,filename,checksum,applied_at,
                        baseline_id,provenance,schema_sha256
                        FROM insightstream_migrations.history ORDER BY version""")
                    history = cursor.fetchall()
                cursor.execute("SELECT pg_export_snapshot()")
                exported = cursor.fetchone()[0]
            pg_command(["pg_dump", "--schema-only", *schemas, "--format=custom",
                        "--snapshot=" + exported, "--no-password", "--file=" + str(archive)],
                       admin_url, directory)
        finally:
            source.rollback()
            source.close()
        archive.chmod(0o600)
        # template0 already supplies public, owned by pg_database_owner. Do not
        # drop it or replay the archive's CREATE SCHEMA entry into that namespace.
        listing = pg_command(["pg_restore", "--list", str(archive)], raw, directory).decode()
        toc = directory / "restore.list"
        toc.write_text("\n".join(line for line in listing.splitlines()
                                if not re.search(r"\bSCHEMA - public\b", line)) + "\n")
        toc.chmod(0o600)
        pg_command(["pg_restore", "--no-owner", "--no-privileges", "--single-transaction",
                    "--exit-on-error", "--no-password", "--use-list=" + str(toc),
                    "--dbname=" + target, str(archive)],
                   raw, directory, target)
        cloned = connect(raw)
        try:
            verify_target(cloned, target, write=True)
            with cloned:
                with cloned.cursor() as cursor:
                    for row in history:
                        cursor.execute("""INSERT INTO insightstream_migrations.history
                            (version,kind,filename,checksum,applied_at,baseline_id,provenance,schema_sha256)
                            VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
                            (*row[:6], json.dumps(row[6]), row[7]))
                clone_state = inspect(cloned, target)
                if clone_state["schema_sha256"] != state["schema_sha256"]:
                    raise DatabaseSafetyError("Cloned migration-test schema does not match the verified source.")
        finally:
            cloned.rollback()
            cloned.close()
    return {"database": target, "url": raw}


def prepare_checks():
    """An explicit run gets three new databases; no older database is reused."""
    os.umask(0o077)
    targets = {"fresh": create_sandbox(), "existing": create_sandbox("live-schema"),
               "historical": create_sandbox()}
    path = PRIVATE_ROOT / "migration-checks" / (secrets.token_hex(6) + ".json")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("x") as handle:
        json.dump(targets, handle)
    path.chmod(0o600)
    return {"migration_test_config": str(path), "databases": [v["database"] for v in targets.values()],
            "cleanup": "New databases are retained; removal requires a separate identity check and approval."}


def read_check_targets(path):
    """Revalidate private target identities on every read; do not consume/reset them.

    A fresh configuration is needed for each lifecycle run because initialization
    refuses nonempty databases, not because this reader enforces one-time use.
    """
    path = Path(path).expanduser()
    if path.stat().st_mode & 0o077:
        raise DatabaseSafetyError("Migration test configuration must be private (0600).")
    try:
        values = json.loads(path.read_text())
        if set(values) != {"fresh", "existing", "historical"}:
            raise ValueError()
        names = set()
        for item in values.values():
            target = item["database"]
            if not SANDBOX_NAME.fullmatch(target) or target in names:
                raise ValueError()
            names.add(target)
            verify_url(item["url"], target)
            connection = connect(item["url"])
            try:
                connection.set_session(readonly=True)
                verify_target(connection, target)
            finally:
                connection.rollback()
                connection.close()
        return values
    except DatabaseSafetyError:
        raise
    except Exception:
        raise DatabaseSafetyError("Cannot validate disposable migration test targets; no tests started.") from None
