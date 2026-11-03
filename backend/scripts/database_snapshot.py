"""Private pg_dump archives and read-only, deterministic recovery verification."""

import hashlib
import json
import os
import re
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import make_url


PRIVATE_ROOT = Path.home() / "Library" / "Application Support" / "InsightStream"


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def canonical_constraint(definition):
    # pg_restore can push varchar[] -> text[] casts into literal array elements.
    # Normalize only this lossless representation change, not arbitrary SQL.
    pattern = r"\(\(ARRAY\[((?:'[^']*'::character varying)(?:, '[^']*'::character varying)*)\]\)::text\[\]\)"
    return re.sub(
        pattern,
        lambda match: "(ARRAY[" + ", ".join(
            "(" + value + ")::text" for value in match.group(1).split(", ")
        ) + "])",
        definition,
    )


def snapshot(connection):
    """Hash every row ordered by PK; emit counts/hashes, never row values."""
    connection.set_session(isolation_level="REPEATABLE READ", readonly=True)
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL statement_timeout='20s'")
        cursor.execute("SET LOCAL lock_timeout='1s'")
        cursor.execute("SET LOCAL timezone='UTC'")
        cursor.execute("SELECT current_database(),current_setting('server_version')")
        database, version = cursor.fetchone()
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        tables = {}
        for (table,) in cursor.fetchall():
            cursor.execute(
                """SELECT a.attname FROM pg_index i JOIN pg_attribute a
                ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey)
                WHERE i.indrelid=%s::regclass AND i.indisprimary
                ORDER BY array_position(i.indkey::smallint[],a.attnum)""",
                ("public." + table,),
            )
            keys = [row[0] for row in cursor.fetchall()]
            if not keys:
                raise RuntimeError("Fingerprint ordering requires a primary key: " + table)
            cursor.execute(sql.SQL("SELECT to_jsonb(t)::text FROM public.{} t ORDER BY {}").format(
                sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, keys))
            ))
            hasher, count = hashlib.sha256(), 0
            for (value,) in cursor:
                encoded = value.encode()
                hasher.update(len(encoded).to_bytes(8, "big"))
                hasher.update(encoded)
                count += 1
            tables[table] = {"rows": count, "sha256": hasher.hexdigest()}
        queries = {
            "columns": "SELECT table_name,column_name,ordinal_position,data_type,udt_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' ORDER BY 1,3",
            "constraints": "SELECT r.relname,c.conname,c.contype,pg_get_constraintdef(c.oid),c.convalidated FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname='public' ORDER BY 1,2",
            "indexes": "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY 1,2",
            "objects": "SELECT c.relkind,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY 1,2",
            "routines": "SELECT p.proname,pg_get_function_identity_arguments(p.oid),pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' ORDER BY 1,2",
            "triggers": "SELECT event_object_table,trigger_name,event_manipulation,action_statement FROM information_schema.triggers WHERE trigger_schema='public' ORDER BY 1,2,3",
        }
        schema = {}
        for name, query in queries.items():
            cursor.execute(query)
            schema[name] = cursor.fetchall()
        raw_schema_hash = digest(schema)
        schema["constraints"] = [
            (table, name, kind, canonical_constraint(definition), validated)
            for table, name, kind, definition, validated in schema["constraints"]
        ]
        cursor.execute("SELECT content_type,count(*) FROM content GROUP BY 1 ORDER BY 1")
        catalog = dict(cursor.fetchall())
        cursor.execute("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='S' ORDER BY c.relname")
        sequences = {}
        for (name,) in cursor.fetchall():
            cursor.execute(sql.SQL("SELECT last_value,is_called FROM public.{}").format(sql.Identifier(name)))
            sequences[name] = cursor.fetchone()
    return {
        "database": database, "version": version, "tables": tables, "catalog": catalog,
        "schema_raw_sha256": raw_schema_hash, "schema_sha256": digest(schema),
        "schema_object_counts": {key: len(value) for key, value in schema.items()},
        "sequences": sequences, "sequences_sha256": digest(sequences),
    }


def connect(raw_url, database=None):
    url = make_url(raw_url)
    return psycopg2.connect(
        host=url.host, port=url.port or 5432, user=url.username,
        password=url.password, dbname=database or url.database, connect_timeout=8,
    )


def pg_environment(raw_url, database=None):
    url = make_url(raw_url)
    # Do not inherit service/options variables that could redirect a libpq command.
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("PG") and key not in {"DATABASE_URL", "TEST_DATABASE_URL", "TMDB_READ_ACCESS_TOKEN"}
    }
    for key, value in {
        "PGHOST": url.host, "PGPORT": str(url.port or 5432),
        "PGUSER": url.username, "PGPASSWORD": url.password,
        "PGDATABASE": database or url.database, "PGCONNECT_TIMEOUT": "8",
    }.items():
        if value is not None:
            environment[key] = value
    return environment


def pg_command(arguments, raw_url, directory, database=None):
    process = subprocess.run(arguments, env=pg_environment(raw_url, database), capture_output=True)
    if process.returncode:
        error_path = directory / "postgresql-error.log"
        error_path.write_bytes(process.stderr)
        error_path.chmod(0o600)
        raise RuntimeError(f"{arguments[0]} failed; inspect the private postgresql-error.log.")
    return process.stdout


def compare_snapshots(expected, actual):
    return {key: expected[key] == actual[key] for key in (
        "tables", "catalog", "schema_sha256", "schema_object_counts", "sequences_sha256"
    )}


def restore_verify(raw_url, manifest_path):
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    archive = Path(manifest["backup_path"])
    if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest["sha256"]:
        raise RuntimeError("Backup checksum mismatch; restore refused.")
    pg_command(["pg_restore", "--list", str(archive)], raw_url, manifest_path.parent)
    target = "insightstream_verify_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(3)
    admin = connect(raw_url, "postgres")
    try:
        admin.autocommit = True
        with admin.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname=%s", (target,))
            if cursor.fetchone():
                raise RuntimeError("Verification target already exists; restore refused.")
            cursor.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(target)))
    finally:
        admin.close()
    pg_command([
        "pg_restore", "--exit-on-error", "--single-transaction", "--no-owner",
        "--no-privileges", "--no-password", "--dbname=" + target, str(archive),
    ], raw_url, manifest_path.parent, target)
    restored = connect(raw_url, target)
    try:
        actual = snapshot(restored)
    finally:
        restored.rollback()
        restored.close()
    comparison = compare_snapshots(manifest["source_snapshot"], actual)
    result = {"verification_database": target, "comparisons": comparison, "verified": all(comparison.values())}
    record = {**result, "restored_snapshot": actual}
    verification_path = manifest_path.parent / (target + ".json")
    verification_path.write_text(json.dumps(record, indent=2, default=str) + "\n")
    verification_path.chmod(0o600)
    if not result["verified"]:
        raise RuntimeError("Restored data/schema fingerprint mismatch; verification stopped.")
    return result


def backup(raw_url, directory=None):
    os.umask(0o077)
    directory = Path(directory or PRIVATE_ROOT / "backups").expanduser().resolve()
    repository = Path(__file__).resolve().parents[2]
    if directory == repository or repository in directory.parents:
        raise RuntimeError("Backups must be outside the Git repository.")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    directory = directory / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secrets.token_hex(3))
    directory.mkdir(mode=0o700)
    archive = directory / "insightstream_db.dump"
    source = connect(raw_url)
    try:
        before = snapshot(source)
        if before["database"] != "insightstream_db":
            raise RuntimeError("Development database identity mismatch; backup stopped.")
        with source.cursor() as cursor:
            cursor.execute("SELECT pg_export_snapshot()")
            exported = cursor.fetchone()[0]
        pg_command(["pg_dump", "--format=custom", "--file=" + str(archive), "--snapshot=" + exported, "--no-password"], raw_url, directory)
    finally:
        source.rollback()
        source.close()
    archive.chmod(0o600)
    pg_command(["pg_restore", "--list", str(archive)], raw_url, directory)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_database": before["database"], "server_version": before["version"],
        "pg_dump_version": pg_command(["pg_dump", "--version"], raw_url, directory).decode().strip(),
        "pg_restore_version": pg_command(["pg_restore", "--version"], raw_url, directory).decode().strip(),
        "backup_path": str(archive), "backup_bytes": archive.stat().st_size,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "archive_readable": True, "source_snapshot": before,
        "schema_verification_note": "Only equivalent literal varchar[] -> text[] constraint casts are canonicalized. Raw schema hash retained.",
        "limitations": ["Cluster roles/tablespaces are not included; verification restores use the existing local admin role without restoring ownership/ACLs."],
    }
    path = directory / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    path.chmod(0o600)
    verification = restore_verify(raw_url, path)
    manifest.update(verification)
    path.write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    return {key: manifest[key] for key in (
        "backup_path", "backup_bytes", "sha256", "verification_database", "comparisons", "verified"
    )} | {"manifest_path": str(path)}
