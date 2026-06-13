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
- Unknown or unmapped values should not be applied directly to normalized fields, but they should be preserved and logged for review.
- Metadata imports should not change ratings, summaries, or decision-support fields.

## 4. Metadata Preservation Rule

Normalization does not mean ignoring provider data.

Provider metadata should not blindly overwrite local fields, but it should also not be silently discarded. Unknown values, unmapped values, and conflicting values should be preserved in processed previews, import logs, or future provenance tables so they can be reviewed later.

Users should see the best available normalized metadata. If a provider gives a useful value that can be mapped safely, InsightStream should display the readable normalized value rather than a provider-specific code or a missing field. If a provider value conflicts with a curated local value, the conflict should be reviewed instead of ignored.

Local curated values and provider values should remain traceable. A future metadata provenance layer should make it clear which fields came from manual seed data, TMDb, another metadata provider, or a later internal import process.

## 5. Basic Metadata Display Policy

| Field | Display Priority | Import/Update Policy | Needs Normalization | Future Schema/Provenance Need |
| --- | --- | --- | --- | --- |
| `title` | Show local title unless a verified provider title is intentionally adopted. | Do not overwrite automatically; review title conflicts. | Low | Provenance useful for alternate titles later. |
| `content_type` | Show local broad type: `movie` or `series`. | Keep broad local model; map provider `movie`/`tv` into local values. | Yes | Future labels/tags may handle anime, documentary, miniseries, specials. |
| `overview` | Show curated local overview for now. | Preserve provider overview for review; do not overwrite blindly. | Low | Provenance useful to track manual vs provider text. |
| `release_date` | Show best verified release or first-air date. | Review provider/local differences before updating. | Medium | Provenance useful because dates can differ by region/source. |
| `year` | Derive from displayed release date. | Recalculate only if release date changes intentionally. | Medium | Usually derived; source follows release date. |
| `runtime` | Show known runtime when available. | Never replace a known runtime with null; review differences. | Medium | Runtime source should eventually be traceable. |
| `language` | Show readable local value such as `English`. | Map known provider codes; preserve unknown codes for review. | Yes | Provenance useful if multiple language/origin fields are added later. |
| `status` | Show normalized lifecycle value. | Map known provider statuses; preserve unknown statuses for review. | Yes | Provenance useful because status changes over time. |
| `age_rating` | Show local age rating when available. | Do not update until certification/source strategy exists. | Yes | May need release/certification schema later. |
| `genres` | Show curated local genres plus reviewed normalized enrichments. | Do not destructively replace; propose additions/removals for review. | Yes | Provenance useful for manual vs provider genre assignments. |
| `poster_url` | Show verified local media URL, with fallback UI. | Already safe to keep/update from processed preview. | Low | Media/source provenance may be useful later. |
| `backdrop_url` | Show verified local media URL, with fallback UI. | Already safe to keep/update from processed preview. | Low | Media/source provenance may be useful later. |
| `external_ids` | Not primary user-facing metadata, but used for matching/source transparency. | Store verified provider IDs in `external_ids`. | Low | Already has provider-neutral schema; source URLs/provenance can be expanded later. |

## 6. Genre Normalization

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

TMDb genres should not automatically replace local genres. The current local taxonomy includes some curated decision-support choices that TMDb does not always include. Provider genres should be normalized and used as enrichment or reconciliation input.

Examples from the metadata gap analysis:

- The Dark Knight has local `Drama`, but TMDb does not include `Drama`.
- Breaking Bad has local `Thriller`, but TMDb does not include `Thriller`.
- The Last of Us has local `Horror` and `Thriller`, but TMDb only returns `Drama`.
- Stranger Things has local `Drama`, `Fantasy`, `Horror`, and `Sci-Fi`, while TMDb returns grouped values such as `Action & Adventure` and `Sci-Fi & Fantasy`.

Recommendation:

- Keep curated local genres for now.
- Normalize provider genres before comparing them with local genres.
- If TMDb has useful genres that are not currently local, propose them for addition.
- If local genres contain useful decision-support labels that TMDb does not include, retain them unless reviewed.
- Use TMDb genre mapping later as enrichment or reconciliation, not destructive replacement.
- When importing provider genres, create a review mode that shows proposed additions/removals before applying changes.

## 7. Language Normalization

TMDb returns language codes. InsightStream currently stores readable display values.

| Provider Code | Local Display Value | Action |
| --- | --- | --- |
| en | English | map |
| ko | Korean | map |
| de | German | map |

Rules:

- For known codes, map to the local display value.
- For unknown codes, do not guess silently.
- Do not leave users with raw codes like `en` when a readable mapping exists.
- Unknown codes should not be applied directly to normalized display fields, but they should be preserved and flagged for review.
- Unknown codes may be displayed as a fallback only if no readable mapping exists yet.
- If language coverage grows, use a fuller ISO language mapping instead of hand-maintaining a tiny list.
- Do not change current seed language values unless a later import task explicitly applies this normalization.

## 8. Status Normalization

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
- Known provider statuses should be mapped and displayed as readable local values.
- If a provider returns an unknown status, map the display value to `Unknown`, preserve the original provider value, and flag it for review.
- Status imports should be idempotent and should not alter content type, release dates, ratings, or summaries.

## 9. Runtime Policy

Runtime is basic metadata and should be displayed when available.

Rules:

- Movie runtime can use a verified provider value after review.
- TV runtime may be null or inconsistent from TMDb, so keep curated representative runtime instead of overwriting it with null.
- Never replace a known runtime with null.
- Small differences, such as `166` vs `167` minutes, should be manually reviewed before changing local data.
- Runtime source should eventually be traceable through metadata provenance.
- If multiple providers disagree, preserve each provider value in preview/import logs and decide the displayed runtime through an explicit rule.

## 10. Fields That Should Stay Curated For Now

These fields should not be overwritten by TMDb metadata in the current phase:

- `overview`
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
- Provider overviews may be useful references later, but they should not replace curated summaries without a product decision.
- Ratings and summary fields belong to the future ratings/scoring phase, not this metadata normalization plan.

Runtime is handled separately as basic metadata: it should be shown when available, preserved when known, and reviewed before provider replacement.

## 11. Fields Requiring New Schema

These fields are useful but should wait for schema support:

- cast
- directors
- creators
- crew jobs
- character names

Cast and crew are still part of the metadata foundation phase. They should be shown to users after person/role schema is implemented.

The next metadata foundation task after normalization may be a person/cast/crew schema plan. Do not store cast or crew as comma-separated text in the `content` table. Future support should use stable person identity, role relationships, display order, and provider external IDs.

## 12. Future Import Rules

A future normalized metadata import should:

- read from a processed preview or controlled ingestion result, not raw provider JSON directly.
- validate that `tmdb_id` and `external_ids` match the intended content row.
- map provider values through these normalization rules.
- avoid applying unknown or unmapped values directly to normalized fields.
- preserve unknown, unmapped, and conflicting values in import logs or future provenance tables.
- log warnings for title, media type, genre, language, and status mismatches.
- avoid destructive replacement unless explicitly intended.
- keep imports idempotent with safe upsert behavior.
- keep TMDb-specific logic isolated from backend route handlers and frontend code.
- avoid changing curated overview, runtime, ratings, summaries, or scoring fields.

## 13. Recommended Next Tasks

1. Review and commit this normalization plan.
2. Create a person/cast/crew schema plan.
3. Implement normalized metadata import only after schema decisions are clear.
4. Later move into ratings source and rating normalization planning.
