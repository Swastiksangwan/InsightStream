# Metadata Ingestion and Rebuild Runbook

## 1. Purpose

This runbook documents how to rebuild the current InsightStream metadata catalog from a clean local PostgreSQL database.

The current catalog is larger than the SQL seed. `backend/sample_data.sql` restores the base 15 canonical development titles, while ingestion scripts restore additional titles, credits, people, biographies, region-aware availability, and certifications.

This document is operational. It explains the current rebuild flow, verification checks, and safe ingestion order. It is not a product planning document.

## 2. Current Catalog State

Current catalog total after the full ingestion rebuild: 21 titles.

Base SQL seed:

- 15 titles from `backend/sample_data.sql`

Additional ingested titles:

- Oppenheimer
- The Matrix
- Fight Club
- Top Gun: Maverick
- House of the Dragon
- Chernobyl

`backend/sample_data.sql` should not be manually expanded for every new provider title. The scalable ingestion target list is:

```text
analytics/config/content_ingestion_targets.json
```

That target file is now the source list for provider-backed catalog expansion.

## 3. Important Files

SQL setup files:

- `backend/schema.sql`: creates tables, constraints, and relationships.
- `backend/sample_data.sql`: creates the canonical 15-title local development seed.
- `backend/indexes.sql`: creates performance indexes.

Ingestion config:

- `analytics/config/content_ingestion_targets.json`: provider-backed target list for scalable ingestion.

Processed preview files:

- `analytics/processed/tmdb/sample_mapping_preview.json`: normalized content metadata preview.
- `analytics/processed/tmdb/credits_preview.json`: provider-neutral cast, director, creator, and crew preview.
- `analytics/processed/tmdb/person_details_preview.json`: person biography/profile preview.
- `analytics/processed/tmdb/availability_certification_preview.json`: region-aware availability and certification preview.

Fetch/build scripts that do not write to PostgreSQL:

- `analytics/scripts/fetch_tmdb_sample.py`: fetches content metadata, external IDs, details, credits, and TV aggregate credits.
- `analytics/scripts/build_tmdb_credits_preview.py`: builds structured credits preview from raw TMDb files.
- `analytics/scripts/fetch_tmdb_person_details.py`: fetches person details and biography preview for imported people.
- `analytics/scripts/fetch_tmdb_availability_certification.py`: fetches watch-provider and certification preview data.

Import scripts that write only with `--apply`:

- `analytics/scripts/import_content_metadata_from_preview.py`: imports content metadata, external IDs, genres, posters/backdrops, and latest activity dates.
- `analytics/scripts/import_people_credits_from_preview.py`: imports `people`, `person_external_ids`, and `content_people`.
- `analytics/scripts/import_person_details_from_preview.py`: imports missing safe person fields such as biography, profile URL, and known-for department.
- `analytics/scripts/import_availability_certification_from_preview.py`: imports region-aware availability, certifications, and safe compact age rating values.

## 4. Environment Variables

Required depending on the stage:

```bash
export DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/insightstream_db
export TMDB_READ_ACCESS_TOKEN=YOUR_TOKEN
```

`DATABASE_URL` is required for backend runtime and all database-aware import scripts.

`TMDB_READ_ACCESS_TOKEN` is required only for scripts that fetch provider data from TMDb:

- `fetch_tmdb_sample.py`
- `fetch_tmdb_person_details.py`
- `fetch_tmdb_availability_certification.py`

Never commit tokens, API keys, local `.env` files, or raw secrets.

## 5. Full Database Reset

For a clean local reset in pgAdmin or `psql`:

```sql
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
```

Then run the base SQL files in this order:

1. `backend/schema.sql`
2. `backend/sample_data.sql`
3. `backend/indexes.sql`

At this point, only the base 15 SQL-seeded titles are restored. Additional ingested titles and metadata are not fully restored until the import scripts run.

## 6. Fast Rebuild From Committed Preview Files

Use this path when processed preview files already exist and do not need refresh.

After running `schema.sql`, `sample_data.sql`, and `indexes.sql`, run from the project root:

```bash
export DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/insightstream_db

python3 analytics/scripts/import_content_metadata_from_preview.py --apply
python3 analytics/scripts/import_people_credits_from_preview.py --apply
python3 analytics/scripts/import_person_details_from_preview.py --apply
python3 analytics/scripts/import_availability_certification_from_preview.py --apply
```

What each import restores:

- Content metadata importer restores additional ingested content, content-level external IDs, genres, poster/backdrop URLs, and latest activity dates.
- People/credits importer restores people, person external IDs, and content-person relationships.
- Person details importer restores biographies, profile URLs, and known-for departments where available.
- Availability/certification importer restores region-aware availability, certifications, and safe compact age rating values.

Expected final result:

- `content` count should be 21.
- Duplicate checks should return no rows.

## 7. Full Rebuild By Refetching Provider Data

Use this path when raw/processed provider files are missing or need refresh.

After the base SQL setup:

```bash
export DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/insightstream_db
export TMDB_READ_ACCESS_TOKEN=YOUR_TOKEN
```

Run in this order:

```bash
python3 analytics/scripts/fetch_tmdb_sample.py
python3 analytics/scripts/import_content_metadata_from_preview.py --apply

python3 analytics/scripts/build_tmdb_credits_preview.py
python3 analytics/scripts/import_people_credits_from_preview.py --apply

python3 analytics/scripts/fetch_tmdb_person_details.py
python3 analytics/scripts/import_person_details_from_preview.py --apply

python3 analytics/scripts/fetch_tmdb_availability_certification.py --all
python3 analytics/scripts/import_availability_certification_from_preview.py --apply
```

Fetch scripts do not write to PostgreSQL. Import scripts write only with `--apply`.

When changing the target list or reviewing a fresh batch, run each import script once without `--apply` before applying:

```bash
python3 analytics/scripts/import_content_metadata_from_preview.py
python3 analytics/scripts/import_people_credits_from_preview.py
python3 analytics/scripts/import_person_details_from_preview.py
python3 analytics/scripts/import_availability_certification_from_preview.py
```

The target config controls which titles are fetched.

## 8. Normal Daily Ingestion Flow For New Titles

Standard flow for adding new provider-backed titles:

1. Add the title to `analytics/config/content_ingestion_targets.json`.
2. Run `python3 analytics/scripts/fetch_tmdb_sample.py`.
3. Review `analytics/processed/tmdb/sample_mapping_preview.json`.
4. Run `python3 analytics/scripts/import_content_metadata_from_preview.py`.
5. Run `python3 analytics/scripts/import_content_metadata_from_preview.py --apply`.
6. Run `python3 analytics/scripts/build_tmdb_credits_preview.py`.
7. Run `python3 analytics/scripts/import_people_credits_from_preview.py`.
8. Run `python3 analytics/scripts/import_people_credits_from_preview.py --apply`.
9. Run `python3 analytics/scripts/fetch_tmdb_person_details.py`.
10. Run `python3 analytics/scripts/import_person_details_from_preview.py`.
11. Run `python3 analytics/scripts/import_person_details_from_preview.py --apply`.
12. Run `python3 analytics/scripts/fetch_tmdb_availability_certification.py --all` or a targeted source ID.
13. Run `python3 analytics/scripts/import_availability_certification_from_preview.py`.
14. Run `python3 analytics/scripts/import_availability_certification_from_preview.py --apply`.
15. Run backend tests.
16. Run the frontend build.
17. Manually verify frontend detail pages.

## 9. Verification SQL

These queries use the current schema column names. Provider IDs are stored in `external_ids.external_id` and `person_external_ids.external_id`.

Content count:

```sql
SELECT COUNT(*) AS total_content FROM content;
```

Expected current result after full rebuild: 21.

External IDs:

```sql
SELECT source_name, COUNT(*)
FROM external_ids
GROUP BY source_name
ORDER BY source_name;
```

Content duplicates:

```sql
SELECT title, content_type, COUNT(*)
FROM content
GROUP BY title, content_type
HAVING COUNT(*) > 1;
```

External ID duplicates:

```sql
SELECT source_name, external_id, COUNT(*)
FROM external_ids
GROUP BY source_name, external_id
HAVING COUNT(*) > 1;
```

Genre duplicates:

```sql
SELECT LOWER(name), COUNT(*)
FROM genres
GROUP BY LOWER(name)
HAVING COUNT(*) > 1;
```

Content-genre duplicates:

```sql
SELECT content_id, genre_id, COUNT(*)
FROM content_genres
GROUP BY content_id, genre_id
HAVING COUNT(*) > 1;
```

People external ID duplicates:

```sql
SELECT source_name, external_id, COUNT(*)
FROM person_external_ids
GROUP BY source_name, external_id
HAVING COUNT(*) > 1;
```

Content people duplicates:

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

Availability duplicates:

```sql
SELECT
    content_id,
    platform_id,
    availability_type,
    region_code,
    source_name,
    COUNT(*)
FROM content_availability
GROUP BY content_id, platform_id, availability_type, region_code, source_name
HAVING COUNT(*) > 1;
```

Certification duplicates:

```sql
SELECT
    content_id,
    country_code,
    rating_system,
    source_name,
    COUNT(*)
FROM content_certifications
GROUP BY content_id, country_code, rating_system, source_name
HAVING COUNT(*) > 1;
```

Platform duplicates:

```sql
SELECT LOWER(name), COUNT(*)
FROM platforms
GROUP BY LOWER(name)
HAVING COUNT(*) > 1;
```

Expected duplicate check result: no rows.

## 10. Test Commands

Backend:

```bash
cd backend
python3 -m pytest
```

Frontend:

```bash
cd frontend
npm run build
```

Backend tests should pass, and the frontend build should pass, when the local database has been prepared through the setup/rebuild flow above.

## 11. Reset/Rebuild Warnings

- Do not rerun `backend/schema.sql` on an existing populated database unless you are intentionally resetting or manually applying a new `CREATE TABLE IF NOT EXISTS` block.
- Do not manually insert provider data into PostgreSQL.
- Do not expand `backend/sample_data.sql` for every new title.
- Do not call TMDb from the frontend.
- Do not overwrite curated local data blindly.
- Always dry-run import scripts before `--apply` when importing new or refreshed provider data.
- Keep TMDb raw/provider data replaceable.
- Availability and certifications are region-aware; do not mix `IN` and `US` silently.
- Do not commit API tokens or local environment files.

## 12. Current Limitations

- Ratings and review intelligence are not implemented yet.
- Advanced admin ingestion UI is not implemented yet.
- Episode-level metadata is not implemented.
- Broad 1000-title ingestion needs batching, retry, and report hardening.
- `backend/sample_data.sql` still represents only the base seed, not the full current catalog.

## 13. Next Recommended Step

After this runbook is committed, either:

- test a larger 30-50 title batch, or
- harden batch ingestion with better logging, retry behavior, and failed-title reporting before larger expansion.
