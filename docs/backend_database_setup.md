# Backend Database Setup and Recovery

## Existing development data is not the seed

The preserved local development database is **`insightstream_db`**: PostgreSQL
18.3, 28 public application tables, 200 titles (109 movies / 91 series) at the
November 2, 2026 Milestone 1 baseline. It includes imported ratings, credits,
availability, keywords, source signals and videos.

**Never DROP, reset, truncate or reseed this database to run tests or repair setup.**
The three-file seed reconstructs only 15 titles. Keep development enrichment,
disposable test fixtures and private recovery archives separate.

## Connection precedence

`backend/app/core/config.py` uses exported environment variables first. In normal
`development`/`production` mode it loads the explicit `backend/.env` location with
`override=False`, independent of working directory. It then creates the existing
SQLAlchemy engine through `app.db.session`. Existing application API behavior is
unchanged.

In `test` mode it does not load development dotenv data and requires explicit
`TEST_DATABASE_URL`. Test configuration/actual target is validated before pytest
imports application modules. `unit-test` mode forbids application engine creation.
The test runner loads only the private test configuration, never falls back to
the development URL and never changes the parent shell environment.

Do not print URLs, passwords, provider tokens, `.env` content or database rows.

## Start the existing application on macOS

Use the already configured Python environment and PostgreSQL service:

```bash
cd backend
INSIGHTSTREAM_ENV=development python3 -m uvicorn app.main:app --reload
```

In another terminal, from the repository root:

```bash
cd frontend
npm run dev
```

The default API is `http://127.0.0.1:8000`; frontend is `http://localhost:3000`.
Do not export test settings for an ordinary application server.

## Read-only identity and schema status

From the repository root:

```bash
python3 backend/scripts/local_database.py status
```

This uses only read-only queries and reports database/version, catalog counts,
per-table SHA-256 fingerprints, schema/object counts and source-file hashes.
It also validates migration status. An unregistered database is reported as such;
presence of a SQL file is not proof that a migration ran. Unknown schema/history
states fail validation instead of being silently adopted.

## Consistent private backup and verified restore

```bash
python3 backend/scripts/local_database.py backup
```

This command:

1. Requires the explicit local `insightstream_db` target.
2. Opens a repeatable-read, read-only transaction and fingerprints every public
   table, ordered by its primary key, plus schema definitions and sequences.
3. Exports that transaction's PostgreSQL snapshot to `pg_dump --format=custom`.
4. Creates a mode-0600 archive and manifest under a unique mode-0700 directory:
   `~/Library/Application Support/InsightStream/backups/<run>/`.
5. Reads the archive table of contents and calculates SHA-256.
6. Creates a new unique `insightstream_verify_<timestamp>_<suffix>` database.
7. Restores with `--exit-on-error --single-transaction --no-owner --no-privileges`.
8. Requires identical table fingerprints, catalog totals, schema/object counts,
   constraint/index definitions and sequence state before reporting verified.

The tools never pass connection URLs/passwords on command-line arguments. libpq
credentials are scoped to the child environment; errors go to a private log.
The PostgreSQL client must support the server version; a failure stops the
operation. Use a quiet ingestion window: sequence state is not MVCC transactional,
so concurrent writers can cause a conservative verification failure.

The original Milestone 1 backup was restored and verified before test
infrastructure changes. Its private manifest retains the PostgreSQL/client
versions, checksum, complete fingerprints and unique restore target. The dump
contains real development data; do not move it into Git or public artifacts.

To verify that archive again later:

```bash
python3 backend/scripts/local_database.py restore-verify \
  --manifest "$HOME/Library/Application Support/InsightStream/backups/<run>/manifest.json"
```

Replace `<run>` with the recorded directory. This always creates a new database;
there is no replace, clean, drop or arbitrary restore-target option. A checksum
mismatch stops before creating a target. Verification databases are retained;
removing one later requires checking its exact identity and explicit approval.

Compare current development data with a saved baseline without printing rows:

```bash
python3 backend/scripts/local_database.py fingerprint \
  --manifest "$HOME/Library/Application Support/InsightStream/backups/<run>/manifest.json"
```

Every comparison must be true when checking test-induced changes. Intentional
future ingestion changes require a new approved baseline, not editing old hashes.

Schema verification retains raw hashes and narrowly canonicalizes PostgreSQL's
lossless `varchar[] -> text[]` literal-array cast deparser rewrite on restore.
Literal values, constraint names, validation and all other definitions must match.
The November 2 restore had nine such equivalent CHECK representations.

Limitations: `pg_dump` does not include cluster-wide roles/tablespaces. Recovery
verification uses existing local admin credentials and does not reproduce original
ownership/ACLs; it proves application data/schema/sequence restoration, not a
complete server disaster-recovery drill. Private archives require an independent
backup destination/retention policy before treating the laptop as recoverable.

## Disposable test environment

```bash
python3 backend/scripts/local_database.py prepare-test
python3 backend/scripts/local_database.py check-test
python3 backend/scripts/run_tests.py -q -rs
```

Preparation creates only a previously absent `insightstream_test` and dedicated
unprivileged `insightstream_test_runner` role, using the current declarative
schema and indexes. No historical migrations run. Role credentials are generated
locally in private `test.env` (0600), outside Git. The test role can own/modify only
its disposable database; permission checks require no development-table write
or development CREATE privileges. PUBLIC access to the new test database is
revoked. Development privileges/configuration are not modified.

An existing unknown test database/role is inspected and refused, never overwritten.
Do not put development/user data into the marked test target. Test runs reset only
its deterministic 18-title fixture data, including after committed test failures.
See [Backend Testing](backend_testing.md) for isolation, locks, unit-only runs,
explicit test-data reset, and the two gated historical migration tests.

## Migration management: baseline and history

Milestone 2A adds a small Python/psycopg2 runner, using the existing installation.
No framework, scheduler, provider request or startup migration is introduced.
**No baseline or migration was applied to `insightstream_db` during this milestone.**

`backend/migrations/baseline.json` pins the schema/index declarations at
`349c179`, management DDL, historical file checksums, and two separately verified
PostgreSQL 18 schema profiles:

| Profile | Tables / indexes | Meaning |
| --- | --- | --- |
| `live` | 28 / 118 | Observed 200-title development schema, November 4, 2026 |
| `declarative` | 28 / 122 | Fresh `schema.sql` + `indexes.sql` initialization |

Known differences are recorded, not repaired:

- Live lacks `idx_content_content_type_lower`, `idx_content_original_title_lower`,
  `idx_people_known_for_department_lower`, and `idx_people_name_lower`.
- Column order differs in `content`, `content_series_metadata`,
  `content_video_fetch_state`, and `people`.
- Equivalent retry-count CHECKs have different names:
  `chk_content_video_fetch_state_failure_count` (live) and
  `content_video_fetch_state_consecutive_failure_count_check` (declarative).

Signatures retain column order, types/lengths, nullability, defaults, constraint
names/definitions, index definitions/validity, relation properties, sequence
definitions/ownership links, routines, triggers, views, types, policies, rules and
collations. Unexpected non-system schemas/extensions fail validation. Object
owners, ACLs, comments, table contents and sequence *values* are not schema-version
identity; target privileges are checked separately, and recovery fingerprints
cover data and sequence values. Equivalent literal varchar-array CHECK casts use
the same narrow normalization as backup verification. Other PostgreSQL major
versions are deliberately unsupported until their signatures are reviewed.
The accepted database locale is UTF8 / C / C with the libc provider; a different
locale requires a separately reviewed profile rather than automatic adoption.

`insightstream_migrations.history` lives outside public fixture tables. It records
version, kind, filename, SHA-256, application time, baseline profile/provenance and
the resulting application-schema signature. Version **0** is a baseline adoption
record, not execution of an old migration. Historical files **004–015** are pinned
archival evidence and never become pending migrations. New versions start at **016**.
The ledger's structure, manifest checksum, contiguous applied prefix, file
checksums and schema-signature chain are checked before subsequent work.

### Read-only status, validation and preview

All commands below run from the repository root, in the current Python environment:

```bash
python3 backend/scripts/local_database.py migrations status --target insightstream_db
python3 backend/scripts/local_database.py migrations validate --target insightstream_db
python3 backend/scripts/local_database.py migrations preview --target insightstream_db
```

These use read-only transactions. Preview reports pending filenames, checksums,
statement counts and any management-schema/baseline registration changes. Review
the exact matching SQL files under `backend/migrations/managed/` before approval;
SQL literals, connection URLs and private rows are not logged. There is no default
target and no production/remote/unknown-target fallback. The supported targets are
the exact local development/test names or newly marked `insightstream_migrate_*`
sandboxes. A name alone is insufficient: actual server, database, role, ownership,
purpose marker and PostgreSQL major version are checked where applicable.

### Creating and testing a new migration

Keep `schema.sql`, `indexes.sql`, `ledger.sql`, the adopted baseline manifest and
historical files immutable. New work goes in a new file, for example:

```sql
-- insightstream-migration: transactional
ALTER TABLE public.content ADD COLUMN example_note text;
```

Use `backend/migrations/managed/016_description.sql`, then 017, with three-digit,
contiguous unique versions and lowercase descriptions. The example is only
illustrative; no business migration is shipped by Milestone 2A. Include tests and
deterministic fixture changes for the behavior being introduced. Do not edit an
applied file to fix it: add a later reviewed migration.

The supported SQL subset is ordinary transactional `CREATE TABLE`, `ALTER TABLE`,
`CREATE [UNIQUE] INDEX`, and `DROP INDEX`. Standard quotes, comments and semicolons
are handled conservatively. Data updates, procedural bodies, psql commands, custom
transaction/session control, CREATE TABLE AS, temporary/unlogged objects and
CONCURRENTLY operations are rejected. Other operations require a separately
reviewed procedure/tool extension; they are not silently run outside a transaction.
The filter is a compatibility boundary, not a sandbox for untrusted SQL authors.
Review ALTER TABLE carefully: a transaction does not make a destructive change safe.

Table targets, foreign-key `REFERENCES` targets and `DROP INDEX` targets must use
explicit `public.<name>` qualification, including known application objects. This
prevents unqualified names from resolving through `search_path` or temporary
schemas. Approved existing names come from the pinned `schema.sql`/`indexes.sql`;
reviewed `CREATE TABLE public.<name>` and `CREATE INDEX <name> ON public.<table>`
declarations extend that allowlist in migration order. PostgreSQL creates a new
index in its target table's schema, so its declaration uses an unqualified index
name. Ordinary double-quoted identifiers preserve case and escaped double quotes.
Unknown existing objects, system/management schemas, internal/reserved object
names and identifiers exceeding PostgreSQL's 63-byte limit are rejected. Schema
moves, renames, inheritance/partition operations, indirect `USING INDEX` targets,
cascading/multiple drops and other unsupported forms require separate review.

Prepare a **new** migration test configuration for each lifecycle test invocation:

```bash
python3 backend/scripts/local_database.py migrations prepare-tests
# Use the private configuration path printed by that command:
MIGRATION_CHECKS="$HOME/Library/Application Support/InsightStream/migration-checks/<run>.json"
python3 backend/scripts/run_tests.py --migration-env "$MIGRATION_CHECKS" -q -rs
```

This creates three unique databases owned by the existing restricted test role:
empty fresh/historical targets and a schema-only clone of development (plus its
verified management-history metadata, if already registered). Admin
credentials are used only to create new databases on maintenance database
`postgres`; pytest receives only restricted target credentials. Configuration and
schema archives stay private outside Git. All three databases are retained; a
failed preparation also retains any targets already created. Their removal needs
a separate identity check and approval. The configuration reader revalidates
identity but does **not** consume the file or enforce single-use access. A repeated
lifecycle run fails initialization once a target is nonempty; preparation of fresh
targets is the supported rerun procedure. Do not reset or replace retained
databases to get a green result.

For manual fresh initialization of the newly created empty sandbox only:

```bash
python3 backend/scripts/local_database.py migrations initialize \
  --target insightstream_migrate_<suffix> --confirm-target insightstream_migrate_<suffix>
```

Initialization requires an empty public schema, executes the pinned schema/index
files, registers the declarative baseline, then applies pending managed migrations
in one transaction. It never loads catalog seeds or reconstructs development.
The automated lifecycle tests perform this operation themselves.

### Later approved baseline registration and application

The following development-writing commands are prepared for **later approval**.
They were not executed during Milestone 2A. Stop application/ingestion writes for
the maintenance window, inspect status/preview, and take a new verified backup:

```bash
python3 backend/scripts/local_database.py backup
# Set the exact private manifest path printed by the successful backup command:
MIGRATION_BACKUP="$HOME/Library/Application Support/InsightStream/backups/<run>/manifest.json"
python3 backend/scripts/local_database.py migrations validate --target insightstream_db
python3 backend/scripts/local_database.py migrations preview --target insightstream_db
```

After explicit approval, register **only** the matched baseline:

```bash
python3 backend/scripts/local_database.py migrations baseline \
  --target insightstream_db --confirm-target insightstream_db --profile live \
  --approve-development --backup-manifest "$MIGRATION_BACKUP"
python3 backend/scripts/local_database.py migrations validate --target insightstream_db
python3 backend/scripts/local_database.py migrations status --target insightstream_db
```

Registration adds the management schema/table and one provenance row. It does not
change catalog data, repair indexes, or invent migration execution history.
Repeated registration with the same profile is idempotent. New managed SQL still
requires a separate preview/review. Take another verified backup after registration
before a subsequent application, because management history has now changed:

```bash
python3 backend/scripts/local_database.py migrations apply \
  --target insightstream_db --confirm-target insightstream_db \
  --approve-development --backup-manifest "$MIGRATION_BACKUP"
python3 backend/scripts/local_database.py migrations validate --target insightstream_db
```

Update `MIGRATION_BACKUP` to that new manifest. Development writes require a backup
created and restore-verified within 24 hours, a matching archive checksum and saved
restore verification, and unchanged current data/schema/sequences/history. Missing,
stale or mismatched evidence fails closed. These checks do not replace human
approval or prevent another operator writing after the check; use a quiet window.

All pending files and their ledger rows form **one transaction** under a
database-scoped advisory lock, with two-second lock and 30-second statement
timeouts. A failure rolls back the entire batch. Re-running with no pending files
does nothing. There are no automatic down migrations, force/repair switches or
nontransactional fallback. After an error, inspect the SQLSTATE and unchanged
status; correct an uncommitted pending file or prepare a reviewed forward fix.
Recover data from the verified archive if necessary, never by blind rollback SQL.

For an independently prepared test database, inspect/preview and explicitly
register profile `declarative` (or the actual matched profile), then apply using
`--target insightstream_test --confirm-target insightstream_test`. Development
approval/backup flags are not required for this disposable target. A shared pytest
advisory lock prevents schema changes while a suite/reset is running. The runner
never auto-migrates an existing test database. Pending managed versions cause an
early test safety failure; apply them explicitly before testing. New test database
preparation includes managed versions before loading deterministic fixtures.

### Second developer, catalog growth and recovery

A developer with an existing supported schema follows status → backup → matched
baseline registration → preview/review → apply → validate. A fresh sandbox follows
initialize → validate; routine test setup uses `prepare-test`. A brand-new local
development database still requires separately approved provisioning of the pinned
schema/index files into a verified **empty** database, or approved restoration of a
private backup into a new target, before matched baseline registration. There is
deliberately no development-rebuild command or automatic adoption of a different
schema. A fresh declarative database uses profile `declarative`, not `live`.

Catalog imports change records, not schema versions. Back up before approved
imports and capture new data fingerprints afterward; do not manufacture migrations
for title batches or copy development records into tests. Commit migration SQL,
code and small deterministic fixtures together. Apply the same versioned SQL to
each developer's own databases rather than manually synchronizing catalogs.

History proves what this runner executed, not that data is recoverable. Backups
remain essential and now fingerprint management history/structure as well as
public data/schema/sequences. Older Milestone 1 manifests without a management
schema remain comparable. Existing backup limitations about roles/ACLs and
off-machine retention still apply.

## Two-developer data workflow

- Each developer has an independently enriched development database and a small
  reproducible test database. Provider tokens remain private.
- Commit schema, fixture and code changes; never commit dumps, private environments
  or generated provider datasets.
- Catalog batches affect development only. Ordinary tests do not synchronize with
  the number of ingested titles or private processed previews.
- Add deterministic fixture records for new behavior and keep genuine independent
  importer/commit coverage. Do not mock database behavior solely to obtain green.
- Back up before approved imports/schema changes; record new baselines afterward.
- Full-catalog restoration is explicit recovery verification, not routine testing.
