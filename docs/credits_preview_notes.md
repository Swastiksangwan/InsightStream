# Credits Preview Notes

## Purpose

`analytics/processed/tmdb/credits_preview.json` is an inspection-only structured preview of cast, director, and creator metadata for the 15 seeded titles.

It is built from existing local TMDb raw files and the processed title preview. It does not call TMDb, update PostgreSQL, change backend APIs, change frontend code, or modify seed data.

## What It Contains

The preview uses provider-neutral fields where possible:

- `source_name`
- `source_person_id`
- `source_credit_id`
- `role_type`
- `character_name`
- `job`
- `department`
- `display_order`
- `profile_url`

The first preview focuses on:

- top 5 cast members per title
- movie directors
- series creators

Generic crew remains empty for now so the first import can stay focused and reviewable.

For TV series, the preview should prefer TMDb aggregate credits for show-level cast. Regular TV credits can be incomplete or biased toward a current/recent season, so `tv_{tmdb_id}_aggregate_credits.json` is used for cast extraction when available. The regular `tv_{tmdb_id}_credits.json` file remains a fallback and should produce a warning when used.

## Why It Is Preview-Only

People and credits should be imported only after reviewing structured person IDs, role data, display order, and missing-field warnings. The import should create `people`, `person_external_ids`, and `content_people` rows through a safe, idempotent script.

Do not use name-only matching for durable person identity. Provider person IDs should drive identity matching.

## Not Yet Included

This preview does not:

- import rows into PostgreSQL
- expose credits through the backend API
- display cast or crew in the frontend
- import every crew member
- add episode-level credits
- change ratings, summaries, or scoring

## Recommended Next Task

Create a safe people/credits import script that reads `analytics/processed/tmdb/credits_preview.json`, prints planned inserts/updates first, requires an explicit apply flag for database writes, and preserves skipped or ambiguous records in an import report.
