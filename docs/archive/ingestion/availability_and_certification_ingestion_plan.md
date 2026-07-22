# Availability and Certification Ingestion Plan

## 1. Purpose

Core metadata ingestion now works for scalable catalog growth. New titles such as Oppenheimer can be added through the ingestion target file, fetched from the current prototype provider, imported into PostgreSQL, and displayed with posters, backdrops, overview, genres, credits, and person links.

Availability and age rating/certification are still missing from the scalable ingestion pipeline. They need separate planning because both are region-dependent. A platform that is available in the United States may not be available in India, and an age rating without a country or rating system can mislead users.

This plan defines how InsightStream should fetch, preview, normalize, import, and display availability and certification metadata while keeping TMDb replaceable and keeping the frontend dependent only on InsightStream backend APIs.

## 2. Current State

Existing seed titles may have platform availability from `backend/sample_data.sql`.

Newly ingested titles do not automatically get platform availability. Oppenheimer was successfully imported through the scalable metadata pipeline, but availability remains empty because no region-aware provider availability stage exists yet.

The content metadata import script does not import availability. It imports normalized content metadata, external IDs, and genres from `analytics/processed/tmdb/sample_mapping_preview.json`.

The content metadata import script does not fully handle certification or age rating. `content.age_rating` exists, but the current preview does not provide a region/source-aware certification value.

The frontend currently behaves correctly when no availability rows exist. `PlatformList` shows a clean empty state, and age rating is displayed only as a metadata chip when `content.age_rating` has a value.

## 3. Availability Requirements

Availability should be modeled as a region-aware content-platform relationship.

Required concepts:

- `content_id`
- platform/provider display name
- provider/platform external ID when available
- `availability_type`: `stream`, `rent`, `buy`, `ads`, or `free`
- `region_code`: `IN`, `US`, or another ISO-style country code
- `source_name`
- `source_provider_id`
- `display_priority` if useful for UI ordering
- `fetched_at` and `updated_at` if useful for refresh behavior

Policy:

- The primary MVP region should be `IN`.
- `US` can be used as fallback only if clearly labelled as `US`.
- Never display `US` fallback data as India availability.
- Missing availability is acceptable and should remain an empty state rather than fake data.
- Provider-specific availability types should be normalized before display.

## 4. Certification / Age Rating Requirements

Certification should also be region-aware.

Required concepts:

- `content_id`
- certification or rating value, such as `U/A 13+`, `PG-13`, `R`, or `TV-MA`
- `country_code`
- `rating_system`
- `source_name`
- `source_priority`
- `notes` or warnings for fallback/missing/conflicting values

Policy:

- Prefer `IN` certification if available.
- Fallback to `US` certification only if `IN` is missing.
- Store or document which country/source the displayed rating came from.
- Do not display a rating without knowing its region/source.
- Do not overwrite an existing curated age rating blindly.
- Preserve missing, conflicting, or unmapped provider values in preview/import logs.

## 5. Current Schema Assessment

Availability:

- `platforms` exists with:
  - `id`
  - `name`
  - `platform_type`
- `content_platforms` exists with:
  - `content_id`
  - `platform_id`
  - `availability_type`
- `content_platforms.availability_type` currently supports only `streaming`, `rent`, and `buy`.
- `content_platforms` does not support `region_code`.
- `content_platforms` does not support provider platform IDs.
- `content_platforms` does not support `source_name`, `source_provider_id`, `display_priority`, or `fetched_at`.
- The current unique constraint is `(content_id, platform_id, availability_type)`, so the same title/platform/type cannot be represented separately for multiple regions.

Certification:

- `content.age_rating` exists.
- There is no `age_rating_region`.
- There is no `age_rating_source`.
- There is no `rating_system`.
- There is no certification history or per-country certification table.

Conclusion:

- Current schema is enough for simple manually seeded local development availability.
- Current schema is not enough for accurate scalable region-aware availability ingestion.
- `content.age_rating` is not enough for trustworthy scalable certification ingestion unless region/source fields are added or certification rows are modeled separately.

No schema changes are made by this document.

## 6. Recommended MVP Data Model

Availability recommendation:

Use a normalized region-aware availability model rather than extending the current `content_platforms` table too far.

Recommended future table:

```sql
content_availability
```

Suggested fields:

- `id`
- `content_id`
- `platform_id`
- `availability_type`
- `region_code`
- `source_name`
- `source_provider_id`
- `display_priority`
- `fetched_at`
- `updated_at`

Recommended uniqueness:

- `UNIQUE (content_id, platform_id, availability_type, region_code, source_name)`

Tradeoff:

- MVP-simple option: add `region_code`, `source_name`, and provider ID fields to `content_platforms`.
- More scalable option: keep `content_platforms` as the current simple seed relationship and add `content_availability` for region-aware provider ingestion.

Recommendation:

- Add a new `content_availability` table for provider-ingested availability.
- Later, either migrate frontend detail responses to read from `content_availability`, or merge simple seed availability and region-aware rows in the service layer.

Certification recommendation:

Use a region-aware certification table instead of relying only on `content.age_rating`.

Recommended future table:

```sql
content_certifications
```

Suggested fields:

- `id`
- `content_id`
- `certification`
- `country_code`
- `rating_system`
- `source_name`
- `source_priority`
- `notes`
- `fetched_at`
- `updated_at`

Recommended uniqueness:

- `UNIQUE (content_id, country_code, rating_system, source_name)`

Tradeoff:

- MVP-simple option: keep `content.age_rating` and add `age_rating_region` plus `age_rating_source`.
- More scalable option: store all known region/source certifications in `content_certifications`, then choose one display value for `content.age_rating` or API display.

Recommendation:

- Add `content_certifications`.
- Keep `content.age_rating` as a compact display/convenience field only after a chosen certification has a known region/source.
- Do not import unknown-region ratings into `content.age_rating`.

## 7. Provider Mapping Notes

TMDb can be the current adapter, but the app model should remain provider-neutral.

Availability mapping:

- Fetch movie provider availability from the provider's movie watch-provider data.
- Fetch TV provider availability from the provider's TV watch-provider data.
- Read the primary region first, currently `IN`.
- Optionally read fallback region `US`.
- Map provider platform names to local `platforms` rows.
- Store provider platform IDs separately from local platform IDs.
- Normalize provider availability types into local values:
  - `flatrate` -> `streaming`
  - `rent` -> `rent`
  - `buy` -> `buy`
  - `ads` -> `ads`
  - `free` -> `free`
- Log unmapped providers instead of dropping them silently.
- Preserve the source region on every row.

Certification mapping:

- For movies, inspect provider release/certification data.
- For TV, inspect provider content-rating data.
- Choose certification by region priority:
  1. `IN`
  2. `US`
  3. no display value until manually reviewed
- Preserve all available country certifications in the preview if possible.
- Log missing, conflicting, or unmapped values.
- Do not infer India ratings from US ratings.

## 8. Processed Preview Design

Recommended preview file:

```text
analytics/processed/tmdb/availability_certification_preview.json
```

Alternative split files:

```text
analytics/processed/tmdb/availability_preview.json
analytics/processed/tmdb/certification_preview.json
```

Combined preview is acceptable for the first implementation because both are region-aware metadata stages.

Preview should include:

- `generated_at`
- `inspection_only`
- `source_provider`
- `primary_region`
- `fallback_regions`
- `items`

Each item should include:

- `title`
- `content_type`
- `source_name`
- `source_id`
- `region`
- provider/platform name
- local platform match if known
- provider platform ID
- `availability_type`
- certification value
- certification country
- certification rating system
- warnings
- skipped or unmapped fields

The preview should preserve missing or unmapped provider values for review. It should not imply DB writes.

## 9. Import Strategy

Availability and certification import scripts should follow the established ingestion pattern:

- dry-run by default
- require `--apply` for DB writes
- use one transaction in apply mode
- use idempotent inserts
- avoid duplicate platforms
- avoid duplicate availability relationships
- preserve existing manually curated availability unless missing or explicitly superseded
- do not overwrite `content.age_rating` blindly
- report conflicts
- report region fallbacks clearly
- avoid manual DB inserts
- do not call provider APIs during import

Recommended scripts:

```text
analytics/scripts/ingestion/fetch_tmdb_availability_certification.py
analytics/scripts/ingestion/import_availability_certification_from_preview.py
```

Import should match content through `external_ids`, not title alone.

## 10. Frontend Display Strategy

Availability:

- Continue showing platform names grouped by availability type.
- Keep the empty state when no rows exist.
- Add region label later when backend can return it, for example `Availability in IN`.
- If fallback data is shown, label it clearly, for example `US availability`.
- Do not hardcode platform names in the frontend.

Age rating:

- Show rating only if known.
- Prefer showing compact rating in the hero metadata.
- Later, consider tooltip/detail text for region/source, such as `IN certification` or `US rating`.
- Avoid misleading mixed-region display.
- Do not show fake ratings.

## 11. Testing Strategy

Backend tests should cover:

- imported availability appears in content detail response
- missing availability remains safe and returns an empty list
- duplicate availability rows are not created
- certification import sets the expected value and region/source
- fallback data is not mislabeled as the primary region
- existing seed availability is not destroyed
- platform name matching is case-safe and does not create duplicates
- imported availability remains idempotent after repeated dry-run/apply cycles

Frontend/build checks should cover:

- content detail page still renders when availability is empty
- content detail page shows grouped availability when rows exist
- age rating chip hides or stays absent when no trusted rating exists

## 12. Implementation Roadmap

1. Finalize schema decision for region-aware availability and certification.
2. Add schema support:
   - recommended: `content_availability`
   - recommended: `content_certifications`
3. Update backend detail response only after schema exists and a provider-neutral response shape is chosen.
4. Create a dedicated fetch script for availability/certification raw data.
5. Build `availability_certification_preview.json`.
6. Create import script with dry-run/apply behavior.
7. Test with Oppenheimer first.
8. Verify frontend Availability and age rating display.
9. Apply to all current 16 titles.
10. Test with 5 more titles before broad catalog expansion.

## 13. What Not To Do

Do not:

- call TMDb from the frontend
- hardcode availability in frontend components
- fake platform data
- fake age ratings
- pretend fallback region data belongs to another region
- overwrite curated local availability blindly
- overwrite `content.age_rating` without region/source confidence
- mix this with ratings/reviews implementation
- build admin ingestion UI before backend ingestion is stable
- treat TMDb availability as permanent commercial infrastructure

## 14. Immediate Next Task After This Plan

Recommended next task:

Add region-aware availability and certification schema support.

Reason:

The current schema cannot safely distinguish India availability from US fallback data, and `content.age_rating` cannot identify which country/source a rating came from. Fetching provider availability/certification previews before schema planning is possible, but import/display decisions would remain blocked by missing region/source fields.

After schema support exists, create a fetch/preview script for Oppenheimer only, then add the dry-run/apply importer.
