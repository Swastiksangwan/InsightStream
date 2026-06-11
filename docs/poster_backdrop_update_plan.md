# Poster and Backdrop Update Plan

## 1. Purpose

This document plans how to use the processed TMDb preview to replace placeholder poster/backdrop values with real image URLs in a controlled way.

This is not full TMDb ingestion, not a commercial/public data strategy, and not a claim that TMDb data is permanently owned project data. It is a local/prototype metadata improvement for the current InsightStream MVP. TMDb remains a replaceable metadata provider.

## 2. Current State

Current state:

- The frontend already supports poster/backdrop display.
- The frontend already has fallback UI for missing or broken poster/backdrop images.
- Current seed poster/backdrop URLs are placeholder-style values.
- The TMDb sample fetch generated real image URLs.
- The processed preview exists at `analytics/processed/tmdb/sample_mapping_preview.json`.
- A local PostgreSQL update has been applied for the 5 preview titles using the update script.
- `backend/sample_data.sql` still has placeholder-style URLs, so these local updates are not reset-safe yet.
- Raw TMDb output remains gitignored under `analytics/raw/tmdb/`.

## 3. Available Preview Fields

Fields from the processed preview that are useful for this task:

- `source_provider`
- `tmdb_id`
- `media_type`
- `title`
- `poster_url`
- `backdrop_url`
- `poster_path`
- `backdrop_path`
- `mapping_notes`

Other preview fields such as cast, director/creator names, vote data, popularity, and IMDb IDs are useful later, but they should not be part of this poster/backdrop update.

## 4. Update Scope

Recommended first update scope:

- update only the 5 preview titles first
- use only `poster_url` and `backdrop_url`
- do not update overview, genres, runtime, ratings, votes, cast, or director yet
- do not add schema changes
- do not update frontend components unless broken-image handling fails

Current preview titles:

- Interstellar
- Inception
- Breaking Bad
- The Dark Knight
- Dune: Part Two

The Dark Knight is currently included as a temporary known test title. The Mandalorian should be added later after verifying its TMDb TV ID.

## 5. Recommended Update Target

### Option A: Update Local PostgreSQL Only

Pros:

- fastest visual validation
- no seed file change yet
- reversible locally

Cons:

- changes disappear after DB reset
- not reproducible for other developers

### Option B: Update `backend/sample_data.sql`

Pros:

- reproducible
- frontend shows real images after reset
- aligns seed data with current UI testing

Cons:

- embeds TMDb image URLs in seed data
- must remember TMDb attribution/licensing/cache considerations
- not final commercial data strategy

### Option C: Create a Controlled Update Script

Pros:

- repeatable
- can read processed preview
- keeps update logic separate
- can later be provider-neutral

Cons:

- slightly more work
- still needs clear decision on whether to commit output

Recommendation:

For the next coding task, prefer a controlled local update script or SQL preview before changing `backend/sample_data.sql` directly. After visual verification, decide whether to update `backend/sample_data.sql`.

## 6. Data Matching Strategy

Preferred matching:

1. `tmdb_id` + `content_type`/`media_type`
2. fallback title + `media_type` only if `tmdb_id` is missing or suspicious

Rules:

- do not update a movie row using a TV result
- do not update a TV row using a movie result
- do not update if title/media type mismatch is detected
- log skipped rows
- keep mapping visible

The update should treat preview `media_type = tv` as backend `content_type = series`.

## 7. Validation Rules

Before applying poster/backdrop updates:

- `poster_url` must be non-empty
- `backdrop_url` must be non-empty if available
- `source_provider` should be `tmdb`
- `media_type` must match backend `content_type`
- `tmdb_id` should match existing `content.tmdb_id` where possible
- `title` should roughly match current `content.title`
- `mapping_notes` should be reviewed

After applying updates:

- run the backend
- open homepage
- open discovery page
- open detail pages for updated titles
- confirm real posters/backdrops render
- confirm fallback UI still works for titles without real images

## 8. Suggested Next Coding Task

Recommended next coding task:

Create an inspection-first poster/backdrop update script.

Implementation note: this script now exists at `analytics/scripts/update_posters_from_tmdb_preview.py`.

Suggested file:

```text
analytics/scripts/update_posters_from_tmdb_preview.py
```

This script should:

- read `analytics/processed/tmdb/sample_mapping_preview.json`
- connect to local PostgreSQL using `DATABASE_URL`
- print planned updates first
- require a flag such as `--apply` before making changes
- update only `poster_url` and `backdrop_url`
- update only rows with matching `tmdb_id` and `content_type`
- print updated/skipped rows
- never fetch TMDb directly
- never modify ratings/summaries/cast/director
- remain local/prototype-only

## 9. What Not To Do Yet

Do not:

- perform full TMDb ingestion yet
- update ratings from TMDb `vote_average` yet
- update genres/runtime/overview yet
- add cast/crew/director to the frontend yet
- alter schema yet
- remove fallback image UI
- make the frontend call TMDb directly
- commit raw TMDb JSON

## Local Update Result

`analytics/scripts/update_posters_from_tmdb_preview.py` was created to read `analytics/processed/tmdb/sample_mapping_preview.json`. It does not fetch TMDb directly, supports dry-run by default, and requires `--apply` before writing to the database.

The script was run successfully with `--apply`:

- rows updated: 5
- rows skipped: 0
- updated titles: Interstellar, Inception, Breaking Bad, The Dark Knight, Dune: Part Two

Only `poster_url` and `backdrop_url` were updated. No ratings, summaries, genres, runtime, overview, cast, director, or schema fields were changed.

These updates currently exist only in local PostgreSQL. Re-running `backend/sample_data.sql` will restore placeholder URLs unless `sample_data.sql` is updated later.

## 10. Final Decision

The first local poster/backdrop update is complete for 5 matched titles. The next decision is whether to persist verified image URLs into `backend/sample_data.sql` for reset-safe local development, or keep applying them through the local update script while broader ingestion planning continues.
