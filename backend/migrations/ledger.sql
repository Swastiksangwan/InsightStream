-- Management metadata only. Never added to/replayed as an application migration.
CREATE SCHEMA insightstream_migrations;
CREATE TABLE insightstream_migrations.history (
    version INTEGER PRIMARY KEY CHECK (version = 0 OR version >= 16),
    kind TEXT NOT NULL CHECK (kind IN ('baseline', 'migration')),
    filename TEXT UNIQUE NOT NULL,
    checksum TEXT NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    baseline_id TEXT NOT NULL,
    provenance JSONB NOT NULL,
    schema_sha256 TEXT NOT NULL CHECK (schema_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK ((version = 0 AND kind = 'baseline') OR (version >= 16 AND kind = 'migration'))
);
