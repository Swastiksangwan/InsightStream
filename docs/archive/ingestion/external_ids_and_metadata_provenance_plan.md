# External IDs and Metadata Provenance Plan

## 1. Purpose

This document plans how InsightStream should track external provider IDs and metadata source information before adding deeper ingestion, ratings integration, or provider replacement support.

The current `content.tmdb_id` field is useful for the prototype, but it is too narrow long term. Future providers may include TMDb, IMDb/OMDb, licensed providers, open datasets, or curated/manual data. External IDs help prevent duplicate content and connect rating/review sources later.

## 2. Current State

Current state:

- The `content` table currently has `tmdb_id`.
- The TMDb sample preview includes both `tmdb_id` and `imdb_id`.
- Poster/backdrop values were tested through the TMDb preview.
- Verified poster/backdrop URLs were persisted into `backend/sample_data.sql` for the tested titles.
- No general `external_ids` table exists yet.
- No metadata source/provenance table exists yet.
- No full ingestion pipeline exists yet.

## 3. Why External IDs Matter

External IDs are needed for:

- provider replacement
- duplicate prevention
- source matching
- IMDb/OMDb/rating-source integration
- future cast/crew/person matching
- debugging mismatched titles
- avoiding a hard dependency on `content.tmdb_id` alone

## 4. Proposed `external_ids` Table

Proposed future table:

```text
external_ids
```

Suggested fields:

- `id`
- `content_id`
- `source_name`
- `external_id`
- `source_url`
- `created_at`
- `updated_at`

Suggested constraints:

- foreign key `content_id` -> `content.id`
- `UNIQUE (content_id, source_name)`
- maybe `UNIQUE (source_name, external_id)`
- `source_name` required
- `external_id` required

`source_name` examples:

- `tmdb`
- `imdb`
- `omdb`
- `manual`
- `other_provider`

Current `content.tmdb_id` can remain during the transition. Later, the project can decide whether to keep it as a convenience field or migrate fully to `external_ids`.

## 5. Mapping From Current TMDb Preview

The processed preview can guide future external ID seeding:

- `tmdb_id` maps to `external_ids.source_name = 'tmdb'`
- `imdb_id` maps to `external_ids.source_name = 'imdb'`
- `source_url` can be generated later if useful
- missing `imdb_id` values should be allowed and skipped

Do not create rows from raw JSON directly yet. Use sanitized processed previews or controlled ingestion outputs.

## 6. Metadata Provenance Need

External IDs track identity. Metadata provenance tracks where a field value came from.

Examples:

- `poster_url` came from `tmdb`
- `backdrop_url` came from `tmdb`
- `overview` may be manual seed data or TMDb later
- ratings may come from separate sources
- summaries may be manually curated or generated later

This distinction matters because identity, content metadata, ratings, summaries, and analytics outputs may come from different sources with different licensing and refresh rules.

## 7. Possible `content_metadata_sources` Table Later

Possible future table:

```text
content_metadata_sources
```

Suggested fields:

- `id`
- `content_id`
- `field_name`
- `source_name`
- `source_record_id`
- `fetched_at`
- `expires_at`
- `confidence`
- `notes`

This is future work, not an immediate schema change. It may be overkill for the current MVP, but it becomes important before public/commercial use because it can support licensing/cache rules, refresh rules, and provider replacement.

## 8. Provider-Neutral Rules

Provider-neutral rules:

- The frontend should consume only InsightStream backend APIs.
- The frontend should not call TMDb directly.
- FastAPI route handlers should not call TMDb directly for normal page loads.
- Provider-specific logic should stay in scripts, services, or adapters.
- The core `content` table should store normalized app fields.
- Provider-specific raw payloads should stay local/ignored unless a storage policy exists.

## 9. Recommended Implementation Sequence

Recommended sequence:

1. Keep current `content.tmdb_id` for now.
2. Plan the `external_ids` schema.
3. Add the `external_ids` table later through `schema.sql` when implementation starts.
4. Seed external IDs for verified titles:
   - `tmdb`
   - `imdb` where available
5. Update the backend details API later only if external ID display/source transparency is needed.
6. Use `external_ids` before rating-source integration.
7. Plan person/cast/crew IDs separately, but follow the same `source_name` + `external_id` pattern.

## 10. What Not To Do Yet

Do not:

- remove `content.tmdb_id` immediately
- migrate all schema blindly
- store every provider field as a new column
- build rating integration before external ID mapping is clear
- store raw provider payloads permanently without a policy
- make the frontend provider-specific
- treat the TMDb free API as long-term commercial infrastructure

## 11. Immediate Next Technical Task

Recommended next technical task:

Create an external IDs schema update plan.

Suggested later file:

```text
docs/external_ids_schema_update_plan.md
```

That future plan should decide:

- exact SQL table definition
- indexes/constraints
- seed data additions
- backend service changes if needed
- tests required

## 12. Final Decision

External IDs should become the provider-neutral identity layer for InsightStream. The current `tmdb_id` field is useful for the prototype, but future metadata, ratings, and provider replacement work should use a generic `source_name` + `external_id` model.
