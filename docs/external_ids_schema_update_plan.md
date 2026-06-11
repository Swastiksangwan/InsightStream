# External IDs Schema Update Plan

## 1. Purpose

This document plans the concrete schema, seed-data, backend, and testing steps needed to add a provider-neutral `external_ids` table.

The current `content.tmdb_id` field is useful but narrow. `external_ids` will support TMDb, IMDb, OMDb, licensed providers, manual IDs, and future provider replacement. This is a plan only, not the schema implementation.

## 2. Current State

Current state:

- The `content` table currently has `tmdb_id`.
- `backend/sample_data.sql` includes TMDb IDs for content rows.
- The processed TMDb preview includes `tmdb_id` and `imdb_id` for tested titles.
- No `external_ids` table exists.
- No API currently exposes external IDs separately.
- The frontend does not need external IDs immediately.

## 3. Proposed Table

Proposed table:

```text
external_ids
```

Recommended SQL shape:

```sql
CREATE TABLE external_ids (
    id SERIAL PRIMARY KEY,
    content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    source_name VARCHAR(50) NOT NULL,
    external_id VARCHAR(255) NOT NULL,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (content_id, source_name),
    UNIQUE (source_name, external_id)
);
```

Notes:

- `source_name` should use lowercase normalized values such as `tmdb`, `imdb`, `omdb`, and `manual`.
- `external_id` should be a string because provider IDs can be numeric or alphanumeric.
- `source_url` is optional.

## 4. Constraints and Indexes

Recommended constraints:

- `UNIQUE (content_id, source_name)`
- `UNIQUE (source_name, external_id)`

Recommended indexes:

- index on `content_id`
- index on `source_name`
- index on `external_id`
- optional composite index on `(source_name, external_id)`

PostgreSQL creates indexes for unique constraints, so implementation should check whether separate explicit indexes are redundant before adding them to `backend/indexes.sql`.

## 5. Relationship With Existing `content.tmdb_id`

Transition strategy:

- keep `content.tmdb_id` for now
- do not remove it immediately
- seed `external_ids` from existing `content.tmdb_id`
- later decide whether `content.tmdb_id` remains a convenience field or is deprecated
- avoid breaking existing services/tests that may rely on `content.tmdb_id`

Recommendation:

The first implementation should add `external_ids` alongside `content.tmdb_id`, not replace it.

## 6. Seed Data Plan

For every content row with `tmdb_id`:

- insert an `external_ids` row with `source_name = 'tmdb'`
- set `external_id = content.tmdb_id` converted to text

For tested titles with `imdb_id` from the processed preview:

- insert an `external_ids` row with `source_name = 'imdb'`
- set `external_id = preview imdb_id`
- insert only if verified and non-empty

Seed rules:

- use stable natural-key lookups by title/content type or `tmdb_id`
- keep `backend/sample_data.sql` reset-safe
- use `ON CONFLICT` or an equivalent safe pattern
- do not add external IDs from raw JSON directly
- do not seed unverified IDs

Current verified preview titles:

- Interstellar
- Inception
- Breaking Bad
- The Dark Knight
- Dune: Part Two

The Mandalorian:

- TMDb TV ID still needs manual verification before adding IMDb/external IDs from TMDb preview.

## 7. Backend Service/API Impact

No frontend change is required immediately.

Existing content listing/detail APIs can continue working unchanged. The details API may later expose `external_ids` if source transparency is useful, but the first schema implementation should not change public API responses.

Possible later service helpers:

- `get_external_ids_for_content`
- `get_content_by_external_id`

Ingestion scripts should eventually use `external_ids` for matching instead of relying only on `content.tmdb_id`.

## 8. Testing Plan

Recommended backend tests after implementation:

- table exists after schema setup
- sample seed creates TMDb external IDs
- verified IMDb IDs exist for tested titles
- unique constraints prevent duplicate source IDs
- deleting content cascades external IDs if tested safely
- existing 18 backend tests still pass
- no existing API response shape breaks

If tests are added, prefer read-only tests first unless a safer mutation/isolation strategy exists.

## 9. Migration / Local Setup Considerations

Current project setup uses SQL files in this order:

1. `backend/schema.sql`
2. `backend/sample_data.sql`
3. `backend/indexes.sql`

Implementation should update:

- `backend/schema.sql` for the new table
- `backend/sample_data.sql` for seed data
- `backend/indexes.sql` for indexes if not covered by constraints
- `docs/backend_database_setup.md` if setup/verification queries need updating
- `docs/backend_testing.md` if tests are added

After a schema change, the local DB must be reset or the table must be manually created before sample external IDs can be inserted.

## 10. Verification Queries

Count external IDs by source:

```sql
SELECT source_name, COUNT(*) AS total
FROM external_ids
GROUP BY source_name
ORDER BY source_name;
```

List external IDs for tested titles:

```sql
SELECT
    c.title,
    c.content_type,
    ei.source_name,
    ei.external_id
FROM content c
JOIN external_ids ei ON ei.content_id = c.id
WHERE c.title IN (
    'Interstellar',
    'Inception',
    'Breaking Bad',
    'The Dark Knight',
    'Dune: Part Two'
)
ORDER BY c.title, ei.source_name;
```

Detect duplicate source/external ID pairs:

```sql
SELECT source_name, external_id, COUNT(*) AS duplicate_count
FROM external_ids
GROUP BY source_name, external_id
HAVING COUNT(*) > 1;
```

Join content to external IDs:

```sql
SELECT
    c.id,
    c.title,
    c.tmdb_id,
    ei.source_name,
    ei.external_id
FROM content c
LEFT JOIN external_ids ei ON ei.content_id = c.id
ORDER BY c.title, ei.source_name;
```

## 11. What Not To Do In First Implementation

Do not:

- remove `content.tmdb_id` yet
- expose external IDs in the frontend yet
- change detail page UI yet
- build ratings integration yet
- add person external IDs yet
- store raw provider payloads
- add a broad metadata provenance table yet
- rewrite ingestion scripts fully yet

## 12. Recommended Implementation Task After This Plan

Recommended next coding task:

Add `external_ids` table and seed verified IDs.

That task should:

- update `backend/schema.sql`
- update `backend/sample_data.sql`
- update `backend/indexes.sql` if needed
- add verification queries to `docs/backend_database_setup.md` if useful
- optionally add backend tests
- keep existing API response shapes unchanged

## 13. Final Decision

The first external IDs implementation should add a generic `external_ids` table alongside `content.tmdb_id`, seed TMDb IDs for existing content, seed verified IMDb IDs for tested titles, and keep backend/frontend API behavior unchanged until a later source-transparency feature requires exposing external IDs.
