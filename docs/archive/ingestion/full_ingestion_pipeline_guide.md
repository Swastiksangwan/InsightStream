# Full Metadata Ingestion Pipeline Guide

## 1. Purpose

This document explains how to add content to InsightStream using the current metadata ingestion pipeline.

It covers both one-title ingestion and batch ingestion. It explains the role of config files, raw provider files, processed previews, import scripts, run reports, database verification, backend tests, and frontend checks.

This is an operational guide. It is not a product plan and it does not introduce reviews, social features, recommendations, or frontend TMDb calls. Ratings import currently supports TMDb rating signals from the processed metadata preview and IMDb rating signals from a local official non-commercial dataset file.

## Current Catalog Context

`backend/sample_data.sql` restores the canonical 15-title SQL seed.

Scalable ingestion adds provider-backed titles through `analytics/config/content_ingestion_targets.json` and the import scripts in `analytics/scripts/`.

Future catalog growth should use the candidate -> validate -> merge -> ingest flow. Do not treat direct database edits or one-off script runs as a replacement for that pipeline.

## 2. Big-Picture Pipeline

Complete flow:

```text
candidate file
  -> candidate validation
  -> merge into target config
  -> fetch TMDb raw metadata
  -> generate processed previews
  -> dry-run import
  -> apply import
  -> dry-run import again for idempotency
  -> backend tests
  -> frontend build
  -> manual frontend verification
  -> commit
```

What each layer means:

- Config files: declare which titles are allowed to be processed.
- Raw provider files: exact cached TMDb responses under `analytics/raw/tmdb/`.
- Processed preview files: normalized, reviewable JSON under `analytics/processed/tmdb/`.
- Import scripts: read processed previews and write to PostgreSQL only with `--apply`.
- Run reports: summarize what a validation or fetch run selected, reused, fetched, skipped, warned, or failed.
- PostgreSQL data: the app-owned normalized data used by backend APIs and frontend pages.

Important rule: processed previews are latest-run files. They are not guaranteed to be full-catalog snapshots.

## 3. Important Folders and Files

`analytics/config/`

- `content_ingestion_targets.json`: main provider-backed ingestion target list.
- `content_ingestion_candidates_batch_*.json`: candidate batch files that should be validated before merging.

`analytics/raw/tmdb/`

- Exact provider response cache.
- Raw files should not be confused with processed previews.
- Fetch scripts may reuse these files when `--refresh` is not passed.

Common raw file patterns:

- `movie_{id}_details.json`
- `movie_{id}_external_ids.json`
- `movie_{id}_credits.json`
- `movie_{id}_watch_providers.json`
- `movie_{id}_release_dates.json`
- `tv_{id}_details.json`
- `tv_{id}_external_ids.json`
- `tv_{id}_credits.json`
- `tv_{id}_aggregate_credits.json`
- `tv_{id}_watch_providers.json`
- `tv_{id}_content_ratings.json`
- `person_{source_person_id}_details.json`

`analytics/processed/tmdb/`

- `sample_mapping_preview.json`: normalized content metadata preview.
- `credits_preview.json`: provider-neutral cast, director, creator, and crew preview.
- `person_details_preview.json`: person biography/profile preview.
- `availability_certification_preview.json`: region-aware availability and certification preview.

`analytics/processed/tmdb/run_reports/`

- `content_fetch_run_report.json`
- `availability_certification_fetch_run_report.json`
- `person_details_fetch_run_report.json`
- `batch_*_target_validation_report.json`

`analytics/scripts/`

- Validation scripts: check candidates before merge.
- Merge scripts: promote validated candidates to the main target config.
- Fetch/build scripts: create raw files and processed previews; they do not write to PostgreSQL.
- Import scripts: write to PostgreSQL only when `--apply` is passed.

`backend/`

- `schema.sql`: creates tables and constraints.
- `sample_data.sql`: canonical 15-title SQL seed only.
- `indexes.sql`: performance indexes.

## 4. Environment Variables

```bash
export DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/insightstream_db
export TMDB_READ_ACCESS_TOKEN=YOUR_TMDB_READ_ACCESS_TOKEN
```

`DATABASE_URL` is required for scripts that read or write PostgreSQL.

`TMDB_READ_ACCESS_TOKEN` is required for scripts that call TMDb. Fetch scripts can reuse raw files if present, but the token is still required when a new provider call is needed or when `--refresh` is used.

Never commit secrets, `.env` files, API keys, database dumps, or local credentials.

## 5. Current Batch-Based Ingestion Strategy

New titles should not be manually inserted into PostgreSQL.

New titles should not be added directly to `backend/sample_data.sql`.

New titles should be proposed as candidates first. Validated candidates are then merged into `analytics/config/content_ingestion_targets.json`.

The `priority` field controls batch selection.

Common priority examples:

- `seed`: original canonical SQL seed titles.
- `pipeline_test`: first one-title scalable ingestion test.
- `batch_test_1`: first five-title batch test.
- `batch_test_2`: validated 30-title batch.
- `batch_test_3`: reasonable next batch name.

Use `--priority` for real batch ingestion. Use `--source-id` or `--title` mainly for debugging one title, checking a cache issue, or rerunning a narrow provider fetch. A one-off debug fetch does not replace candidate validation and target config merge.

## 6. Full Batch Ingestion Flow

### Step 1: Create a candidate batch file

Example:

```text
analytics/config/content_ingestion_candidates_batch_3.json
```

Expected candidate object shape:

```json
{
  "title": "...",
  "content_type": "movie",
  "source_name": "tmdb",
  "source_id": "...",
  "priority": "batch_test_3",
  "ingestion_status": "candidate",
  "notes": "Candidate for scalable ingestion batch."
}
```

Rules:

- `content_type` must be `movie` or `series`.
- `source_name` is currently `tmdb`.
- `source_id` is the TMDb movie or TV ID.
- `priority` groups the batch.
- Candidate files do not affect the database.

### Step 2: Validate candidates

```bash
python3 -m analytics.scripts.ingestion.validate_ingestion_candidates \
  --candidates analytics/config/content_ingestion_candidates_batch_3.json \
  --priority batch_test_3
```

Optional existing-target config argument:

```bash
python3 -m analytics.scripts.ingestion.validate_ingestion_candidates \
  --candidates analytics/config/content_ingestion_candidates_batch_3.json \
  --targets analytics/config/content_ingestion_targets.json
```

If `--priority` is omitted, the validator infers the expected priority when all candidates in the file share one priority. Mixed-priority candidate files fail validation with a clear setup error.

Validation checks:

- JSON structure.
- Required fields.
- `content_type` is `movie` or `series`.
- `source_name` is `tmdb`.
- `source_id` is present and valid.
- Duplicate source IDs inside the candidate file.
- Duplicate `title` plus `content_type` inside the candidate file.
- Duplicates against existing targets.
- TMDb ID and movie/series endpoint correctness when `TMDB_READ_ACCESS_TOKEN` is available.
- Title/name mismatch warnings when remote validation is available.

Validation reports are written under:

```text
analytics/processed/tmdb/run_reports/
```

Check the exact report path in the validator console output. Report filenames may vary by batch or validator implementation.

### Step 3: Merge candidates into target config

Dry-run first:

```bash
python3 -m analytics.scripts.ingestion.merge_ingestion_candidates \
  --candidates analytics/config/content_ingestion_candidates_batch_3.json \
  --targets analytics/config/content_ingestion_targets.json \
  --priority batch_test_3
```

Apply:

```bash
python3 -m analytics.scripts.ingestion.merge_ingestion_candidates \
  --candidates analytics/config/content_ingestion_candidates_batch_3.json \
  --targets analytics/config/content_ingestion_targets.json \
  --priority batch_test_3 \
  --apply
```

The merge helper is dry-run by default. `--apply` writes to `content_ingestion_targets.json`.

The database is still unchanged after this step. Fetch scripts now have a new batch available through `--priority batch_test_3`.

### Step 4: Fetch basic content metadata

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_sample --priority batch_test_3
```

This script:

- reads `content_ingestion_targets.json`;
- selects targets matching the priority;
- calls TMDb or reuses raw cache;
- creates raw content files;
- creates `sample_mapping_preview.json`;
- creates `content_fetch_run_report.json`;
- does not write to PostgreSQL.

Common raw content files:

- `movie_{id}_details.json`
- `movie_{id}_external_ids.json`
- `movie_{id}_credits.json`
- `tv_{id}_details.json`
- `tv_{id}_external_ids.json`
- `tv_{id}_credits.json`
- `tv_{id}_aggregate_credits.json`

### Step 5: Import content metadata

```bash
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview --apply
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview
```

The first command is dry-run. The second writes to PostgreSQL. The third checks idempotency.

This importer writes or updates:

- `content`
- `external_ids`
- `genres`
- `content_genres`

It preserves existing curated non-empty fields unless the import policy explicitly allows safe update.

### Step 6: Import TMDb ratings

```bash
python3 -m analytics.scripts.ingestion.import_content_ratings_from_preview
python3 -m analytics.scripts.ingestion.import_content_ratings_from_preview --apply
python3 -m analytics.scripts.ingestion.import_content_ratings_from_preview
```

The ratings importer reads TMDb rating rows from `sample_mapping_preview.json` and writes to the provider-neutral ratings tables only when `--apply` is passed.

It writes or updates:

- `rating_sources`
- `content_ratings`

The third command checks idempotency.

### Step 6b: Import IMDb ratings from local dataset

Run this only when a local IMDb dataset file is available.

```bash
python3 -m analytics.scripts.ingestion.import_imdb_ratings \
  --ratings-file analytics/datasets/imdb/title.ratings.tsv
python3 -m analytics.scripts.ingestion.import_imdb_ratings \
  --ratings-file analytics/datasets/imdb/title.ratings.tsv \
  --apply
python3 -m analytics.scripts.ingestion.import_imdb_ratings \
  --ratings-file analytics/datasets/imdb/title.ratings.tsv
```

The IMDb importer reads the official non-commercial `title.ratings.tsv` dataset and matches only through stored IMDb IDs in `external_ids`. It does not scrape IMDb pages and does not import ratings for titles outside the local catalog.

The local dataset directory is ignored by git:

```text
analytics/datasets/imdb/
```

### Step 6c: Import Letterboxd ratings from reviewed preview

Run this only after the Letterboxd match preview has been reviewed.

```bash
python3 -m analytics.scripts.ingestion.import_letterboxd_ratings_from_preview
python3 -m analytics.scripts.ingestion.import_letterboxd_ratings_from_preview --include-ambiguous --apply
python3 -m analytics.scripts.ingestion.import_letterboxd_ratings_from_preview --include-ambiguous
```

The Letterboxd importer reads `analytics/processed/letterboxd/letterboxd_rating_match_preview.json`, imports high-confidence rows by default, and imports ambiguous rows only when `--include-ambiguous` is passed after manual review. Unmatched rows remain skipped.

Letterboxd ratings are displayed as a source rating but are not included in InsightStream Score v1 because the dataset does not provide a reliable vote count. Review text is ignored and never imported.

The local dataset directory is ignored by git:

```text
analytics/datasets/letterboxd/
```

Ratings imports do not include Rotten Tomatoes, Metacritic, CinemaScore, reviews, summaries, or recommendations.

### Step 7: Build credits preview

```bash
python3 -m analytics.scripts.ingestion.build_tmdb_credits_preview
```

This script:

- reads the current `sample_mapping_preview.json`;
- reads raw credits files;
- prefers TV aggregate credits for series cast;
- builds top cast and key crew roles such as creators, directors, writers, and producers;
- creates `credits_preview.json`;
- does not write to PostgreSQL;
- only processes titles currently present in `sample_mapping_preview.json`.

### Step 8: Import people and credits

```bash
python3 -m analytics.scripts.ingestion.import_people_credits_from_preview
python3 -m analytics.scripts.ingestion.import_people_credits_from_preview --apply
python3 -m analytics.scripts.ingestion.import_people_credits_from_preview
```

The importer writes:

- `people`
- `person_external_ids`
- `content_people`

This enables top cast, unified crew display, creators/directors compatibility fields, and person links. Crew is imported from local processed previews and is not fetched by the frontend.

The third command checks idempotency.

### Step 9: Fetch person details

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_person_details
```

Current optimized behavior:

- default mode is missing-only;
- reads `people` and `person_external_ids` from PostgreSQL;
- skips people that already have non-empty `biography`, `profile_url`, and `known_for_department`;
- fetches or reuses raw person cache for incomplete people;
- creates `person_details_preview.json`;
- creates `person_details_fetch_run_report.json`;
- does not write to PostgreSQL.

Raw person cache path:

```text
analytics/raw/tmdb/person_{source_person_id}_details.json
```

Useful examples:

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_person_details --missing-only --limit 20
python3 -m analytics.scripts.ingestion.fetch_tmdb_person_details --all --limit 10
python3 -m analytics.scripts.ingestion.fetch_tmdb_person_details --source-person-id 525 --refresh
python3 -m analytics.scripts.ingestion.fetch_tmdb_person_details --name "Christopher Nolan" --refresh
```

Important: this script reads DB people, not content targets. It does not support `--priority`.

### Step 10: Import person details

```bash
python3 -m analytics.scripts.ingestion.import_person_details_from_preview
python3 -m analytics.scripts.ingestion.import_person_details_from_preview --apply
python3 -m analytics.scripts.ingestion.import_person_details_from_preview
```

This importer writes safe missing fields to `people`:

- `biography`
- `profile_url`
- `known_for_department`

It preserves existing non-empty local values. The third command checks idempotency.

### Step 11: Fetch availability and certification

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_availability_certification --priority batch_test_3
```

This script:

- reads `content_ingestion_targets.json`;
- selects target batch by priority;
- fetches or reuses availability and certification raw files;
- creates `availability_certification_preview.json`;
- creates `availability_certification_fetch_run_report.json`;
- does not write to PostgreSQL.

Common raw files:

- `movie_{id}_watch_providers.json`
- `movie_{id}_release_dates.json`
- `tv_{id}_watch_providers.json`
- `tv_{id}_content_ratings.json`

### Step 12: Import availability and certification

```bash
python3 -m analytics.scripts.ingestion.import_availability_certification_from_preview
python3 -m analytics.scripts.ingestion.import_availability_certification_from_preview --apply
python3 -m analytics.scripts.ingestion.import_availability_certification_from_preview
```

The importer writes:

- `platforms`
- `content_availability`
- `content_certifications`

It safely updates compact `content.age_rating` only when appropriate. The region-aware truth lives in `content_availability` and `content_certifications`.

The third command checks idempotency.

### Step 13: Verification

Backend tests:

```bash
cd backend
python3 -m pytest
cd ..
```

Frontend build:

```bash
cd frontend
npm run build
cd ..
```

Manual frontend checks:

- catalog count updated;
- new title detail pages open;
- poster/backdrop visible;
- overview visible;
- genres visible;
- cast/crew visible;
- person links work;
- biography/profile visible where available;
- age rating chip visible where available;
- Availability in India visible where available;
- Discovery/search/filtering still works;
- Recent sorting still works.

### Step 14: SQL Verification

Content count:

```sql
SELECT COUNT(*) AS total_content FROM content;
```

Duplicate content:

```sql
SELECT title, content_type, COUNT(*)
FROM content
GROUP BY title, content_type
HAVING COUNT(*) > 1;
```

Duplicate external IDs:

```sql
SELECT source_name, external_id, COUNT(*)
FROM external_ids
GROUP BY source_name, external_id
HAVING COUNT(*) > 1;
```

Duplicate people external IDs:

```sql
SELECT source_name, external_id, COUNT(*)
FROM person_external_ids
GROUP BY source_name, external_id
HAVING COUNT(*) > 1;
```

Duplicate content people:

```sql
SELECT
    content_id,
    person_id,
    role_type,
    COALESCE(character_name, '') AS character_name,
    COALESCE(job, '') AS job,
    COALESCE(source_credit_id, '') AS source_credit_id,
    COUNT(*)
FROM content_people
GROUP BY
    content_id,
    person_id,
    role_type,
    COALESCE(character_name, ''),
    COALESCE(job, ''),
    COALESCE(source_credit_id, '')
HAVING COUNT(*) > 1;
```

Duplicate availability:

```sql
SELECT content_id, platform_id, availability_type, region_code, source_name, COUNT(*)
FROM content_availability
GROUP BY content_id, platform_id, availability_type, region_code, source_name
HAVING COUNT(*) > 1;
```

Duplicate certifications:

```sql
SELECT content_id, country_code, rating_system, source_name, COUNT(*)
FROM content_certifications
GROUP BY content_id, country_code, rating_system, source_name
HAVING COUNT(*) > 1;
```

Expected result: duplicate checks should return no rows.

Note: current schema stores provider IDs in `external_id`, not `source_id`, for both `external_ids` and `person_external_ids`.

## Automated Ingestion Health Check

Run the read-only health check before and after large batch ingestion:

```bash
python3 -m analytics.scripts.audits.check_ingestion_health
```

Batch-specific check:

```bash
python3 -m analytics.scripts.audits.check_ingestion_health --priority batch_test_2
```

Strict mode:

```bash
python3 -m analytics.scripts.audits.check_ingestion_health --strict
```

IMDb coverage expectation:

```bash
python3 -m analytics.scripts.audits.check_ingestion_health --expect-imdb
```

Letterboxd coverage expectation:

```bash
python3 -m analytics.scripts.audits.check_ingestion_health --expect-letterboxd
```

This script does not write to PostgreSQL. It checks target config shape, target-to-database coverage, duplicate rows, metadata completeness, people summary metrics, availability/certification coverage, IMDb rating gaps, and optional Letterboxd movie coverage when requested.

It writes:

```text
analytics/processed/tmdb/run_reports/ingestion_health_report.json
```

Use `--fail-on-warning` in CI or review workflows when warnings should block the run.

## Series Lifecycle Metadata Refresh

Series lifecycle metadata comes from TMDb TV details payloads already fetched as:

```text
analytics/raw/tmdb/tv_{id}_details.json
```

The metadata is series-level only. It records season count, episode count, provider status, normalized app status, first/last aired dates, last episode air date, next episode air date, series type, and a season summary that distinguishes released seasons from announced/upcoming seasons. It does not create episode pages or season pages.

The season summary is provider-derived and stored locally. The frontend should not infer future seasons from total season count alone; it displays stored fields such as `released_seasons_count`, `next_season_number`, `next_season_air_date`, and `season_summary_note`.

For a targeted ongoing-series refresh:

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_sample --source-id TMDB_SERIES_ID --refresh

python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview --apply
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview
```

The targeted fetch rebuilds `sample_mapping_preview.json` for the selected title. The importer safely refreshes dynamic series lifecycle and season summary fields in `content_series_metadata` and updates `content.latest_activity_date` from the latest valid aired date. It does not use future `next_episode_air_date` or `next_season_air_date` values for recency.

For a full backfill, regenerate a full content preview before importing so every series target is present in `sample_mapping_preview.json`.

## Series Refresh Workflow

Use the series refresh planner for existing series that may have changed since the last metadata refresh. This does not add new titles. It only creates a temporary target file for series already in the catalog with TMDb external IDs.

Plan due series:

```bash
python3 -m analytics.scripts.refresh.plan_series_refresh
```

The planner writes:

```text
analytics/config/series_refresh_targets.json
analytics/processed/tmdb/run_reports/series_refresh_plan_report.json
```

Then use the generated target file with the normal content fetch/import flow:

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_sample \
  --targets analytics/config/series_refresh_targets.json \
  --refresh

python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview --apply
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview
```

Useful planner modes:

```bash
# Select all existing series, regardless of freshness.
python3 -m analytics.scripts.refresh.plan_series_refresh --all

# Plan only ongoing series.
python3 -m analytics.scripts.refresh.plan_series_refresh --status ongoing

# Include ended/cancelled series in freshness checks.
python3 -m analytics.scripts.refresh.plan_series_refresh --include-ended
```

By default, ended and cancelled series are skipped unless their `last_refreshed_at` is missing. Ongoing, upcoming, and unknown-status series are selected when their refresh timestamp is stale, they have a near-future next episode date, or recent activity suggests the provider details should be refreshed.

## Full Batch Command Sequence

Use this compact sequence after a candidate batch has passed validation and has been merged into `content_ingestion_targets.json`.

```bash
export DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/insightstream_db
export TMDB_READ_ACCESS_TOKEN=YOUR_TMDB_READ_ACCESS_TOKEN
BATCH=batch_test_3

python3 -m analytics.scripts.ingestion.fetch_tmdb_sample --priority "$BATCH"

python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview --apply
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview

python3 -m analytics.scripts.ingestion.import_content_ratings_from_preview
python3 -m analytics.scripts.ingestion.import_content_ratings_from_preview --apply
python3 -m analytics.scripts.ingestion.import_content_ratings_from_preview

python3 -m analytics.scripts.ingestion.import_imdb_ratings --ratings-file analytics/datasets/imdb/title.ratings.tsv
python3 -m analytics.scripts.ingestion.import_imdb_ratings --ratings-file analytics/datasets/imdb/title.ratings.tsv --apply
python3 -m analytics.scripts.ingestion.import_imdb_ratings --ratings-file analytics/datasets/imdb/title.ratings.tsv

python3 -m analytics.scripts.ingestion.import_letterboxd_ratings_from_preview
python3 -m analytics.scripts.ingestion.import_letterboxd_ratings_from_preview --include-ambiguous --apply
python3 -m analytics.scripts.ingestion.import_letterboxd_ratings_from_preview --include-ambiguous

python3 -m analytics.scripts.ingestion.build_tmdb_credits_preview

python3 -m analytics.scripts.ingestion.import_people_credits_from_preview
python3 -m analytics.scripts.ingestion.import_people_credits_from_preview --apply
python3 -m analytics.scripts.ingestion.import_people_credits_from_preview

python3 -m analytics.scripts.ingestion.fetch_tmdb_person_details

python3 -m analytics.scripts.ingestion.import_person_details_from_preview
python3 -m analytics.scripts.ingestion.import_person_details_from_preview --apply
python3 -m analytics.scripts.ingestion.import_person_details_from_preview

python3 -m analytics.scripts.ingestion.fetch_tmdb_availability_certification --priority "$BATCH"

python3 -m analytics.scripts.ingestion.import_availability_certification_from_preview
python3 -m analytics.scripts.ingestion.import_availability_certification_from_preview --apply
python3 -m analytics.scripts.ingestion.import_availability_certification_from_preview

cd backend
python3 -m pytest
cd ..

cd frontend
npm run build
cd ..
```

The content and availability fetches use `--priority` because they operate on target batches. The person details fetcher reads existing DB people and defaults to missing-only behavior.

## 7. Single-Title Ingestion Flow

Recommended safe approach:

1. Create a small candidate file with one item.
2. Validate it.
3. Merge it with a priority such as `single_title_test` or `batch_test_3`.
4. Run the same full pipeline using `--priority`.

Debug commands for one title:

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_sample --source-id 603
python3 -m analytics.scripts.ingestion.fetch_tmdb_availability_certification --source-id 603
python3 -m analytics.scripts.ingestion.fetch_tmdb_person_details --source-person-id 525 --refresh
```

Debugging one title with `--source-id` does not replace the normal candidate -> validate -> merge flow. For production-like ingestion, use the candidate/target config path.

## 8. Full CLI Reference

| Script | Purpose | Supported options |
| --- | --- | --- |
| `validate_ingestion_candidates.py` | Validate candidate target file before merge. | `--candidates`, `--targets`, `--priority` |
| `merge_ingestion_candidates.py` | Merge validated candidates into target config. | `--candidates`, `--targets`, `--priority`, `--apply` |
| `fetch_tmdb_sample.py` | Fetch or reuse content metadata raw files and build content preview. | `--targets`, `--priority`, `--source-id`, `--title`, `--limit`, `--refresh` |
| `import_content_metadata_from_preview.py` | Dry-run/apply normalized content metadata import. | `--preview`, `--apply` |
| `import_content_ratings_from_preview.py` | Dry-run/apply TMDb ratings import from the content preview. | `--preview`, `--apply` |
| `import_imdb_ratings.py` | Dry-run/apply IMDb ratings import from a local official `title.ratings.tsv` dataset. | `--ratings-file`, `--apply` |
| `import_letterboxd_ratings_from_preview.py` | Dry-run/apply Letterboxd ratings import from the reviewed local match preview. | `--preview-file`, `--include-ambiguous`, `--apply` |
| `build_tmdb_credits_preview.py` | Build credits preview from current content preview and raw files. | No major CLI options. |
| `import_people_credits_from_preview.py` | Dry-run/apply people and credits import. | `--apply` |
| `fetch_tmdb_person_details.py` | Fetch or reuse person details for local TMDb people. | `--missing-only`, `--all`, `--source-person-id`, `--person-id`, `--name`, `--limit`, `--refresh` |
| `import_person_details_from_preview.py` | Dry-run/apply missing person detail fields. | `--apply` |
| `fetch_tmdb_availability_certification.py` | Fetch or reuse availability/certification raw files and build preview. | `--targets`, `--priority`, `--source-id`, `--title`, `--all`, `--limit`, `--refresh` |
| `import_availability_certification_from_preview.py` | Dry-run/apply region-aware availability/certification import. | `--preview`, `--apply` |
| `check_ingestion_health.py` | Read-only target config, DB coverage, duplicate, metadata completeness, ratings coverage, and people summary check. | `--targets`, `--priority`, `--output`, `--strict`, `--fail-on-warning`, `--expect-imdb`, `--expect-letterboxd` |

This table is based on the current scripts. Do not assume an option exists unless it is listed here or shown by the script's `--help`.

## 9. Preview File Warning

Processed preview files are latest-run previews. They are not always full-catalog snapshots.

Example:

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_sample --priority batch_test_3
```

After that command, `sample_mapping_preview.json` contains `batch_test_3` only. Then:

```bash
python3 -m analytics.scripts.ingestion.build_tmdb_credits_preview
```

builds credits only for that current preview.

This is expected. Use run reports to confirm what the last fetch/build command selected.

## 10. Dry-Run / Apply Rule

Fetch/build scripts do not write to PostgreSQL.

Import scripts write only with `--apply`.

Normal pattern:

```bash
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview --apply
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview
```

The first command previews planned changes. The second writes changes. The third checks idempotency.

Use this pattern for all import scripts.

## 11. Commit Guidance

Usually commit:

- config changes;
- processed previews if repo policy is to track them;
- run reports if useful for audit/review;
- documentation;
- script changes.

Do not commit:

- secrets;
- `.env`;
- database dumps;
- accidental raw cache files unless intentionally tracked;
- `sample_data.sql` for every new provider-backed title.

## 12. Common Mistakes

- Adding titles directly to PostgreSQL.
- Adding every new title manually to `sample_data.sql`.
- Running an import script without checking dry-run output.
- Forgetting `--priority` and accidentally rebuilding a broad preview.
- Confusing raw files with processed previews.
- Assuming preview files always contain the full catalog.
- Forgetting `TMDB_READ_ACCESS_TOKEN`.
- Forgetting `DATABASE_URL`.
- Expecting `fetch_tmdb_person_details.py` to use `--priority`; it reads DB people, not content targets.
- Committing secrets.
- Calling TMDb from the frontend.

## 13. Final Checklist Before New Batch

- Candidate file created.
- Validation passed.
- No duplicates.
- Candidates merged into target config.
- Fetch reports inspected.
- Previews generated.
- Dry-run imports inspected.
- Imports applied.
- Idempotency checks passed.
- Backend tests passed.
- Frontend build passed.
- Manual detail pages checked.
- Duplicate SQL checks clean.
- Changes committed.
