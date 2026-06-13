# Metadata Normalization Plan

## 1. Purpose

Provider metadata needs normalization before it is imported into InsightStream because external APIs use their own naming, grouping, codes, and lifecycle values. TMDb is useful for prototype metadata, but its values should not be copied directly into local tables without mapping rules.

This plan defines how TMDb genres, language codes, and status values should map into InsightStream's local metadata model. It supports the metadata foundation phase by making metadata fetching, cleaning, storing, and display more reliable before the project moves deeper into ratings and scoring.

The plan also keeps TMDb replaceable. InsightStream should depend on its own normalized schema and API, while provider-specific values pass through a mapping layer before they affect local data.

## 2. Current Local Metadata Model

Relevant current tables and fields:

- `content.content_type`: broad type, currently `movie` or `series`.
- `content.language`: readable display value, such as `English`, `Korean`, or `German`.
- `content.status`: readable lifecycle value, currently mostly `Released`.
- `genres`: local genre taxonomy.
- `content_genres`: relationship between content and local genres.
- `external_ids`: provider-neutral identity layer for values such as TMDb and IMDb IDs.

Already handled:

- `poster_url` and `backdrop_url` are aligned with the processed TMDb preview for all 15 seeded titles.
- TMDb and IMDb IDs are stored in `external_ids` for all 15 seeded titles.

Out of scope for this plan:

- cast, crew, directors, creators, and people, which need future person/role schema.
- ratings, review summaries, pros, cons, verdicts, and scoring.
- TMDb vote average, vote count, and popularity.

## 3. Normalization Principles

- Local values should be stable, readable, and product-friendly.
- Provider values should be mapped, not blindly inserted.
- Curated fields should be preserved when they are intentionally different.
- Avoid duplicate taxonomy values such as `Sci-Fi` and `Science Fiction`.
- Provider-specific raw values should remain traceable later through provenance or import logs.
- Imports should be idempotent and safe to rerun.
- Unknown or unmapped values should be skipped or logged for review instead of silently guessed.
- Metadata imports should not change ratings, summaries, or decision-support fields.

## 4. Genre Normalization

TMDb genre values should map into InsightStream's local genre taxonomy before any import changes are made.

| TMDb Genre | Local Genre(s) | Action |
| --- | --- | --- |
| Science Fiction | Sci-Fi | map |
| Sci-Fi & Fantasy | Sci-Fi, Fantasy | split |
| Action & Adventure | Action, Adventure | split |
| Action | Action | keep |
| Adventure | Adventure | keep |
| Animation | Animation | keep |
| Comedy | Comedy | keep |
| Crime | Crime | keep |
| Drama | Drama | keep |
| Fantasy | Fantasy | keep |
| Horror | Horror | keep |
| Mystery | Mystery | keep |
| Romance | Romance | keep |
| Thriller | Thriller | keep |

TMDb genres should not automatically replace local genres. The current local taxonomy includes some curated decision-support choices that TMDb does not always include.

Examples from the metadata gap analysis:

- The Dark Knight has local `Drama`, but TMDb does not include `Drama`.
- Breaking Bad has local `Thriller`, but TMDb does not include `Thriller`.
- The Last of Us has local `Horror` and `Thriller`, but TMDb only returns `Drama`.
- Stranger Things has local `Drama`, `Fantasy`, `Horror`, and `Sci-Fi`, while TMDb returns grouped values such as `Action & Adventure` and `Sci-Fi & Fantasy`.

Recommendation:

- Keep curated local genres for now.
- Use TMDb genre mapping later as enrichment or reconciliation, not destructive replacement.
- When importing provider genres, create a review mode that shows proposed additions/removals before applying changes.

## 5. Language Normalization

TMDb returns language codes. InsightStream currently stores readable display values.

| Provider Code | Local Display Value | Action |
| --- | --- | --- |
| en | English | map |
| ko | Korean | map |
| de | German | map |

Rules:

- For known codes, map to the local display value.
- For unknown codes, do not guess silently.
- Unknown codes may be stored or displayed as the code only if no mapping exists, and the import should log a warning.
- If language coverage grows, use a fuller ISO language mapping instead of hand-maintaining a tiny list.
- Do not change current seed language values unless a later import task explicitly applies this normalization.

## 6. Status Normalization

Current local seed status mostly uses:

- `Released`

TMDb may return different movie and TV lifecycle values. These should map to a smaller local display set before import.

Recommended local display values:

- `Released`
- `Ended`
- `Ongoing`
- `Canceled`
- `Upcoming`
- `Unknown`

| TMDb Status | Local Status | Notes |
| --- | --- | --- |
| Released | Released | Movie/released content. |
| Ended | Ended | Completed series. |
| Returning Series | Ongoing | Active series. |
| Canceled | Canceled | Canceled series. |
| In Production | Upcoming | Not released yet. |
| Planned | Upcoming | Not released yet. |
| Post Production | Upcoming | Not released yet. |

Rules:

- Do not change current seed status immediately.
- Apply this only when intentionally importing or updating status later.
- If a provider returns an unknown status, map to `Unknown` and log the original provider value for review.
- Status imports should be idempotent and should not alter content type, release dates, ratings, or summaries.

## 7. Fields That Should Stay Curated For Now

These fields should not be overwritten by TMDb metadata in the current phase:

- `overview`
- `runtime`
- `content_summary`
- `ratings`
- `pros`
- `cons`
- `verdict`
- `unified_score`
- `critic_score`
- `audience_score`

Why:

- These fields support InsightStream's decision-support product voice.
- The current seed data is curated for local API and frontend testing.
- TMDb runtime can be missing or inconsistent for series.
- Provider overviews may be useful references later, but they should not replace curated summaries without a product decision.
- Ratings and summary fields belong to the future ratings/scoring phase, not this metadata normalization plan.

## 8. Fields Requiring New Schema

These fields are useful but should wait for schema support:

- cast
- directors
- creators
- crew jobs
- character names

The next metadata foundation task after normalization may be a person/cast/crew schema plan. Do not store cast or crew as comma-separated text in the `content` table. Future support should use stable person identity, role relationships, display order, and provider external IDs.

## 9. Future Import Rules

A future normalized metadata import should:

- read from a processed preview or controlled ingestion result, not raw provider JSON directly.
- validate that `tmdb_id` and `external_ids` match the intended content row.
- map provider values through these normalization rules.
- skip unknown or unmapped values unless manually approved.
- log warnings for title, media type, genre, language, and status mismatches.
- avoid destructive replacement unless explicitly intended.
- keep imports idempotent with safe upsert behavior.
- keep TMDb-specific logic isolated from backend route handlers and frontend code.
- avoid changing curated overview, runtime, ratings, summaries, or scoring fields.

## 10. Recommended Next Tasks

1. Review and commit this normalization plan.
2. Create a person/cast/crew schema plan.
3. Implement normalized metadata import only after schema decisions are clear.
4. Later move into ratings source and rating normalization planning.
