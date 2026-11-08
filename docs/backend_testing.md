# Backend Testing Guide

## Safety boundary

Routine tests use **`insightstream_test`** (or the explicitly authorized new
migration-fixture sandbox described below), with role
`insightstream_test_runner`, on a loopback PostgreSQL server. They never use the
200-title development catalog. Both `INSIGHTSTREAM_ENV=test` and an explicit
`TEST_DATABASE_URL` are required. Missing values do not fall back to `DATABASE_URL`
or `backend/.env`.

Before test modules can import the application's engine, pytest checks the URL,
actual database/user/server, owner, database purpose marker, role privileges,
schema-source hashes and expected tables. The role has no superuser, CREATEDB,
CREATEROLE, replication, bypass-RLS or inherited membership privileges. Permission
inspection must show zero writable development tables and no development CREATE
privilege. No write is attempted against development to test those permissions.

Every SQLAlchemy connection, including independent importer engines, is checked
again. Application configuration rejects a test target outside test mode. Run
pytest in a fresh process: cached application engines imported before the safety
gate are rejected. PostgreSQL URLs are redacted from pytest failure reports.
Managed history and schema signatures are also checked. Pending migrations or
unrecognized drift prevent fixture resets/tests; the runner never auto-migrates
an existing database. Validated managed public tables join fixture resets, while
the separate management history is preserved.

## One-time local preparation

Use the existing macOS PostgreSQL installation and current Python environment.
From the repository root:

```bash
python3 backend/scripts/local_database.py prepare-test
python3 backend/scripts/local_database.py check-test
```

Preparation requires the configured local administrative development connection.
It creates a new role/database only when the names are unused. An existing
unrecognized role/database is a blocker, not permission to overwrite it. An
already prepared environment is inspected without resetting it.

Generated test credentials live in:

```text
~/Library/Application Support/InsightStream/test.env
```

The directory is mode 0700 and the file is 0600. Do not print, commit or send this
file. No real credentials are stored in the repository. The test database owner
is the restricted test role, permitting genuine DDL integration tests in this
disposable database without granting privileges over development.

## Run tests

From the repository root:

```bash
# Full ordinary suite; private test settings are loaded explicitly by this runner.
python3 backend/scripts/run_tests.py -q -rs

# Pure tests without a running PostgreSQL server or any database URL.
python3 backend/scripts/run_tests.py --unit-only -q

# Narrow a run normally.
python3 backend/scripts/run_tests.py backend/tests/test_search_endpoints.py -q
```

The runner removes inherited development/provider credentials from the child
process. Explicit exported test settings override the private file, and unsafe
settings still fail the guard. A bare `python3 -m pytest` without explicit test
configuration intentionally fails before collection. `--unit-only` deselects
cases whose fixture graph requires the database/client and refuses application
engine initialization.

Both repository-root and `cd backend` invocations work. From backend, use
`python3 scripts/run_tests.py -q`.

## Deterministic fixtures and genuine commits

The test schema starts from the pinned `backend/schema.sql` and
`backend/indexes.sql`, with managed versions included when preparing a new test
database. Historical files are not replayed and development is not restored.
The fixture is the canonical 15-title `backend/sample_data.sql` plus
`backend/tests/fixtures/catalog.sql`: 18 titles, synthetic source ratings,
selected people/credits, lifecycle, source signals, regional offers and deliberate
missing-data cases. Registry definitions are explicitly reseeded after data reset.
All fixture timestamps are fixed. Provider-derived seed images are not fetched.
Synthetic ratings are test inputs, never catalog ingestion.

For each database test, the guarded fixture resets only the known test tables
using TRUNCATE/RESTART IDENTITY, then reloads these small deterministic records.
It resets again in `finally`, after sessions/clients close. This is deliberate:
existing integration tests exercise independent connections and real commits, so
an outer rollback cannot isolate all writes. Assertions and importer behavior
are retained; everything is confined to the disposable test database.

A session advisory lock prevents concurrent suites/resets on one local database.
Parallel pytest workers are not supported. A killed process may leave test data;
inspect identity and use the explicit reset below. Unexpected tables/schema-source
drift cause refusal rather than an automatic schema rebuild.

```bash
python3 backend/scripts/local_database.py check-test
python3 backend/scripts/local_database.py reset-test --confirm-reset insightstream_test
```

Reset operates only on marked `insightstream_test`, checks development write
permissions, takes the same lock, and requires the exact target name as explicit
operator confirmation. There is no development-reset command. A regular test run
also resets disposable fixture data; never put personal/development data there.

## Historical migrations and skips

The two existing video migration idempotency/preservation tests retain every
assertion and the `migration` marker. Their original shared-database cases remain
skipped. Historical migrations were **not replayed during Milestone 1**.

Milestone 2A executes both original functions, with their original assertions,
through `test_original_historical_assertions_execute_only_on_new_disposable_database`
on a newly initialized sandbox. This reveals that 015 adds a second equivalent
retry-count CHECK to the consolidated fresh schema. The migration ledger correctly
reports that replay as drift rather than marking it as managed execution. Routine
test/development schemas are not changed. The old `--run-migration-tests` flag now
fails before database access; use the controlled lifecycle checks below.

The five November 1 development-data-dependent skips are now covered by fixture
cases: mixed scoring-source tie, missing guidance, missing imported rating,
legacy-only age rating and legacy-only availability. Fixtures also provide
Oppenheimer regional certification, a US-only offer and no-availability records.

Existing pure formatter/mapping/provider helper tests remain database-independent.
Real database tests retain schema, SQL/read API, importer-commit, idempotency,
failure-state and people/search behavior coverage. Database cases are tagged
`database` automatically from their fixture graph.

## Migration management checks

Create fresh targets, then use the exact private JSON path printed by preparation:

```bash
python3 backend/scripts/local_database.py migrations prepare-tests
MIGRATION_CHECKS="$HOME/Library/Application Support/InsightStream/migration-checks/<run>.json"

# Full backend suite on NEW sandbox schema + deterministic fixtures, including 016:
python3 backend/scripts/run_tests.py --migration-env "$MIGRATION_CHECKS" --migration-fixtures -q -rs
```

`--migration-fixtures` initializes only the new empty `fresh` target through the
managed runner, marks it for deterministic fixtures, then authorizes that exact
verified sandbox in this pytest process. No environment variable alone widens the
test allowlist. Actual identity/owner/purpose/privileges, schema and development
write-denial checks still apply; the ordinary test DB is not migrated or reset.
Initialization rejects a nonempty/reused target. Fixture data resets and the test
advisory lock apply to the sandbox; migration DDL also respects that lock.

Milestone 2C leaves the existing test DB at its original schema. The ordinary
runner therefore intentionally fails closed on pending 016 until an operator
separately approves its test-only upgrade. Use the new sandbox mode above in the
meantime; unit-only testing remains independent of PostgreSQL.
The later, separately approved procedure to restore the ordinary runner is in
[Upgrading insightstream_test to 016](backend_database_setup.md#later-approved-upgrade-of-insightstream_test-to-016).
It validates the existing declarative baseline, registers it if needed, applies
only 016 with exact-target confirmation and validates again. No test reset,
development migration or catalog-data copy is part of that upgrade.
The suite-lock test verifies unchanged history whether the ledger is absent or
already registered, so it remains valid after that approved upgrade.

Run lifecycle checks **separately**, with a new configuration (do not use
`--migration-fixtures`). `--migration-only` selects only lifecycle cases using
the explicit sandbox configuration and never resets/migrates the routine test DB,
which can remain at baseline 0:

```bash
python3 backend/scripts/local_database.py migrations prepare-tests
MIGRATION_CHECKS="$HOME/Library/Application Support/InsightStream/migration-checks/<new-run>.json"
python3 backend/scripts/run_tests.py --migration-env "$MIGRATION_CHECKS" --migration-only -q -rs
```

Reading a
configuration revalidates identity but does not consume it or prevent rereading.
Fresh targets are required for each lifecycle run because initialization refuses
nonempty schema state. No migration database is reset or deleted automatically.
Without `--migration-env`, lifecycle cases explicitly skip. Pure
migration safety tests and the shared-test-lock check still run normally.
`--unit-only` deselects every database case, including migration sandboxes.
In full sandbox-fixture mode the four lifecycle wrappers skip (three original
runner lifecycles and the real-016 additive/rollback case); run them via
`--migration-only`. The two archived test entry points still skip while their
unaltered assertions execute inside the historical lifecycle wrapper.

The fresh lifecycle covers initialization/baseline provenance, successful schema
changes, idempotency, modified/missing files, whole-batch rollback, advisory-lock
contention, data preservation, corrupt history and unrecorded schema drift. The
existing-schema case uses a schema-only clone with the exact live profile and
proves no automatic index repair. Historical checks call the original test
functions on a third new database. Pure cases cover unsupported/nontransactional
SQL, explicit public-schema object allowlists (including quoted identifiers),
configuration rereading, duplicate/gapped versions, immutable source checksums, unknown/forged targets,
backup evidence and protection from development credentials. The shared fixture
check proves the suite lock blocks test-schema migrations before DDL.

See [Database Setup and Recovery](backend_database_setup.md#migration-management-baseline-and-history)
for the canonical migration commands, SQL subset, two baseline profiles and later
approval procedure. Sandbox credentials/archives stay outside Git; created
databases are retained pending separately approved cleanup.

## Existing regression history and references

An early combined-discovery regression used `SELECT DISTINCT` with
`ORDER BY cs.unified_score` without selecting that sort expression. PostgreSQL
rejected filtered `sort_by=top_rated` queries. The existing fix selects an internal
`sort_unified_score` value while `build_content_object()` preserves the public
response shape. This history remains a reason to retain genuine PostgreSQL
endpoint coverage alongside pure tests.

Formatter test ownership, public-field consistency rules, and diagnostic commands
remain documented in [Decision Insight Formatter v2](decision_insight_formatter_v2.md).
The read-only catalog expansion audit is documented in
[Catalog Expansion Readiness](catalog_expansion_readiness.md); generated audit
reports are evidence, not ordinary test fixtures.

## Validation and two-developer workflow

Before changing fixtures or schema, run the safety unit tests and `check-test`.
Developers each prepare their own local test database once; no manual
synchronization with development ingestion is needed. Catalog expansion must not
change ordinary test counts or expectations. Add a small explicit fixture for a
new behavior, not a production dump.

Full-catalog recovery is a separate `backup`/`restore-verify` workflow in
[Backend Database Setup](backend_database_setup.md); it is never an implicit
pytest fixture. Future snapshot-based integration tests must have their own
explicit isolated targets and authorization.

November 2, 2026 validation: **876 passed, two skipped** (the explicitly gated
migration cases), versus the original 829 passed / five skipped baseline.
The unit-only run passed **747 tests**, deselecting 131 database cases, without
PostgreSQL access. Forty-four safety/isolation cases were added; all five former
fixture-dependent skips now execute. An intentional committed-test failure also
verified cleanup. Development counts, row fingerprints, schema and sequences
matched the pre-change snapshot. The two gated migration cases were not executed.

November 4, 2026 Milestone 2A validation: **928 passed / two intentionally skipped**
with a fresh migration configuration, including **52 migration-management cases**.
The original historical assertions passed inside the sandbox lifecycle; their
two shared-schema entries remain skipped. Unit-only validation passed **795 tests**
with 135 database cases deselected. The frontend production build passed. The
existing urllib3/LibreSSL warning remains; no dependencies were installed/changed.

November 7, 2026 Milestone 2C validation: **1,075 passed / six intentional skips**
using a newly initialized migration-fixture sandbox. The four lifecycle wrappers
passed separately (three original runner lifecycles, then the real-016
rollback/idempotency/data-preservation case); the two historical entry points
retain their assertions inside the historical wrapper. The previous Milestone 2B
configuration reported 1,030 passed / five skips. Forty-six cases were added,
including deterministic refresh regressions and two fail-closed target cases.
The frontend production build passed. All 28 development table counts/row hashes,
schema, sequences and migration history matched the before snapshot: 200 titles
(109 movies / 91 series), baseline 0 with 016 pending. Neither existing database
was migrated; no live provider request or real catalog refresh was run. The
existing urllib3/LibreSSL warning remains.

November 8, 2026 final-review corrections: **1,102 passed / six intentional skips**
in a new protected fixture sandbox; **245 focused tests passed** (one migration
wrapper reserved for the separate run), and **all four migration lifecycle
wrappers passed separately**. Twenty-seven persisted-state regressions were added
for local cache/credential blocks, stale replay no-ops, historical-but-newer cache
application, online recovery and real HTTP failure classification using mocked
responses. Assertions cover complete metadata/video/state preservation and shared
planner/audit eligibility, including unchanged genuine failure counters/backoff.
The suite-lock check also supports a registered ordinary test ledger.

The unchanged 016 SQL passed separate rollback/idempotency/ledger/preservation
trials against both a fresh declarative baseline and a restricted sandbox restored
from a newly verified full development backup (200 titles, all 28 original table
hashes and sequences preserved, no state backfill). Both existing databases'
before/after data, schema, sequence and history fingerprints matched; development
stays baseline 0 with 016 pending and the 18-title routine test DB stays
unregistered with 016 pending. No live TMDb requests, existing-database migrations,
fixture resets on insightstream_test, or database deletion occurred. The frontend
production build, Python syntax and whitespace checks passed. The existing
urllib3/LibreSSL warning remains.
