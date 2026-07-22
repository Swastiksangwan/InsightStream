# Scalable Metadata Ingestion Plan

## 1. Purpose

Current title addition is too manual. Adding one title is manageable, but adding 10, 100, or 1000 titles by hand would be slow, inconsistent, and easy to break.

The goal is to make catalog expansion repeatable and safe before moving deeper into ratings and reviews. InsightStream should be able to fetch provider metadata, normalize it, review it, import it, and verify it without manually editing every row or trusting unreviewed provider values.

This plan focuses on the metadata foundation: content metadata, posters/backdrops, external IDs, normalized genres/status/language, latest activity dates, credits, people, and biographies.

## 2. Current Manual Flow

The current flow is controlled but still manual:

1. Manually decide which titles belong in the catalog.
2. Hardcode or update the seeded title list.
3. Run `analytics/scripts/ingestion/fetch_tmdb_sample.py` to fetch TMDb metadata for known titles.
4. Generate `analytics/processed/tmdb/sample_mapping_preview.json`.
5. Update or persist poster/backdrop data.
6. Run `analytics/scripts/ingestion/build_tmdb_credits_preview.py`.
7. Run `analytics/scripts/ingestion/import_people_credits_from_preview.py`.
8. Run `analytics/scripts/ingestion/fetch_tmdb_person_details.py`.
9. Run `analytics/scripts/ingestion/import_person_details_from_preview.py`.
10. Verify backend APIs and frontend pages.

This works for the current 15-title foundation because every title can be inspected manually. It does not scale because target selection, provider matching, validation, import decisions, warning review, and recovery from partial failures are not yet organized around batches.

## 3. Target Scalable Flow

Future scalable flow:

```text
ingestion target list
-> provider fetch
-> raw provider cache
-> processed normalized preview
-> validation/reconciliation report
-> dry-run import
-> apply import
-> backend/frontend verification
```

The pipeline should keep each stage visible. Fetching should not imply importing. Importing should not imply overwriting. Warnings should be reviewable before writes happen.

## 4. Ingestion Target File

Add a target file later, for example:

```text
analytics/config/content_ingestion_targets.json
```

Suggested item fields:

- `title`
- `content_type`
- `source_name`
- `source_id`
- `priority`
- `ingestion_status`
- `notes`

Example shape:

```json
{
  "targets": [
    {
      "title": "Interstellar",
      "content_type": "movie",
      "source_name": "tmdb",
      "source_id": "157336",
      "priority": "seed",
      "ingestion_status": "verified",
      "notes": "Current canonical seed title."
    }
  ]
}
```

Provider ID is preferred when available because title search can mismatch, especially for remakes, translated titles, TV specials, similarly named titles, and series with regional variants. Title search can remain a fallback, but search-derived matches should be flagged for review before import.

## 5. Provider-Neutral Architecture

TMDb is the current prototype provider, not a permanent application dependency.

Preferred architecture:

```text
provider target
-> provider fetcher
-> provider raw cache
-> normalized preview
-> InsightStream database
-> FastAPI API
-> frontend
```

Rules:

- Internal database tables should store provider-neutral fields.
- `external_ids` should anchor content identity across TMDb, IMDb, OMDb, licensed providers, open datasets, and manual sources.
- `person_external_ids` should anchor person identity.
- Raw files or a future `raw_external_payloads` storage policy should preserve provider data for review/debugging without shaping the app around raw provider responses.
- Frontend should consume only InsightStream backend APIs.
- Frontend should never call TMDb directly.

## 6. Raw and Processed Data Layers

Raw provider files:

- exact provider responses saved under ignored local paths such as `analytics/raw/tmdb/`
- useful for debugging, refetch avoidance, provider comparison, and rebuilding processed previews
- should not be imported directly without normalization

Processed normalized preview:

- provider-specific payloads mapped into app-owned field names
- should include normalized values and original provider values where useful
- should preserve warnings, conflicts, unknown values, and skipped fields

Import reports:

- dry-run output describing inserts, updates, skips, conflicts, and warnings
- should be deterministic and reviewable

Warning files:

- batch-level failed titles
- title mismatches
- missing provider IDs
- missing posters/backdrops
- missing credits/person IDs
- unknown genres/languages/status values
- potentially conflicting local/provider values

Raw data should not be directly imported because raw provider values can be incomplete, provider-specific, differently named, region-dependent, or incompatible with the current normalized schema.

## 7. Normalization Rules

Future batch ingestion should normalize these fields before import:

- `content_type`: map provider values such as `movie` and `tv` to local `movie` and `series`.
- `title` / original title: preserve provider title, but do not overwrite local title automatically when conflicts exist.
- `release_date`: keep original movie release or series first air date; review regional/source differences.
- `latest_activity_date`: for series, use latest aired activity according to the documented hierarchy; do not overwrite `release_date`.
- `runtime`: preserve known runtime; never replace a known runtime with null.
- `language`: map provider language codes to readable local values.
- `status`: map provider lifecycle values into local statuses such as `Released`, `Ended`, `Ongoing`, `Canceled`, `Upcoming`, and `Unknown`.
- `genres`: normalize provider taxonomy into local genres; use provider genres as enrichment, not destructive replacement.
- `poster_url` / `backdrop_url`: resolve provider image paths into the chosen local URL/path policy.
- `external_ids`: store verified provider IDs in `external_ids`.
- `age_rating`: defer until certification/source policy exists.
- cast/crew/people: import only structured person IDs, roles, character names, jobs, departments, and display order.
- person biographies: import safe missing fields only; preserve other person-detail fields in previews until schema supports them.

Unknown or unmapped values should be logged, not silently dropped. Provider values should not blindly overwrite existing local values. Conflicts should be reported and reviewed.

## 8. Import Strategy

Import scripts should follow these rules:

- dry-run by default
- require `--apply` for database writes
- use transactions for apply mode
- make imports idempotent and safe to rerun
- use upserts where constraints exist
- prevent duplicates through `external_ids`, `person_external_ids`, and cautious relationship checks
- report conflicts instead of hiding them
- skip unsafe rows with clear reasons
- produce summaries for inserted, updated, skipped, unchanged, and warning rows
- avoid manual direct database inserts for provider data

Partial failure handling should be explicit. A batch should either fail safely before commit or record enough skipped/failed state that the next run can resume without duplicating successful work.

## 9. Scaling to 1000 Titles

Scaling requires pipeline behavior that is boring, resumable, and inspectable.

Needed capabilities:

- batching by target count or priority
- retry logic for transient fetch failures
- skip already-fetched raw files unless refresh is requested
- skip already-imported external IDs unless update mode is requested
- rate-limit awareness and clear pauses/retry reporting
- resumable runs from target status and existing raw/processed files
- progress summary during fetch/import
- warning summary after each batch
- failed title report with reasons
- deterministic output files for review and diffing
- consistent naming for raw and processed files
- no frontend dependency on provider availability

The first scalable milestone should not jump directly to 1000 titles. Test the pipeline with 5 new titles, then 30-50 titles, then larger batches.

## 10. Database Reset/Rebuild Compatibility

Scalable ingestion should support local rebuilds without hand repair.

Current reset foundation:

1. `backend/schema.sql`
2. `backend/sample_data.sql`
3. `backend/indexes.sql`

After base reset:

1. import people/credits from processed credits preview
2. import person biographies from processed person details preview
3. run future batch content metadata imports
4. run verification queries and backend tests

Posters/backdrops for the current 15-title seed are persisted in `backend/sample_data.sql`. Future catalog expansion should rely on generated previews and import scripts rather than manually editing seed rows for every new provider-derived title.

The seed file can stay small and canonical for development. Larger catalog data should come from repeatable ingestion outputs.

## 11. Relationship to Ratings/Reviews

Ratings should come after stable metadata ingestion.

Reasons:

- ratings require correct content identity
- rating sources need external IDs and source matching
- review intelligence needs reliable title, release, type, and provider identity
- scoring should not be mixed with metadata cleanup or provider matching

This plan prepares for ratings by making content identity, metadata normalization, provider isolation, and batch safety stronger. It does not implement ratings, review summaries, pros/cons, verdict generation, or unified score calculation.

## 12. What Not To Do

Do not:

- call TMDb from the frontend
- hardcode provider data in UI components
- manually insert titles into PostgreSQL for scalable provider ingestion
- overwrite local values blindly
- silently drop unknown provider values
- mix ratings/reviews implementation into the metadata ingestion task
- build an admin ingestion UI before backend ingestion scripts are stable
- build broad episode-level schema unless a later requirement proves it is needed
- treat TMDb as permanent commercial infrastructure
- expose raw provider payloads through frontend-facing APIs

## 13. Recommended Implementation Roadmap

1. Create ingestion target file format.
2. Refactor `analytics/scripts/ingestion/fetch_tmdb_sample.py` to read targets instead of a hardcoded list.
3. Create reusable provider fetch helpers.
4. Create normalized processed preview for content metadata.
5. Create content metadata import script with dry-run/apply.
6. Integrate poster/backdrop and external ID import into the content metadata import flow.
7. Keep credits/person imports as separate but connected stages.
8. Add validation and reconciliation reports for every batch.
9. Test with 5 new titles.
10. Expand to 30-50 titles.
11. Then plan ratings architecture.

## 14. Immediate Next Task After This Plan

Create ingestion target config and refactor the TMDb fetch script.

Suggested next task:

```text
Create analytics/config/content_ingestion_targets.json and update fetch_tmdb_sample.py to read targets from that file while preserving the current 15-title behavior.
```

The first implementation should still be inspection-first: fetch raw files, generate a processed preview, print warnings, and make no database writes.
