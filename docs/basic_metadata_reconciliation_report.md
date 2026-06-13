# Basic Metadata Reconciliation Report

Generated at: `2026-06-13T14:30:18.843196+00:00`

## 1. Purpose

This report compares current local seed metadata with the processed TMDb preview and classifies what should happen next for each basic metadata field.

It is analysis-only. No database changes were made, no backend or frontend code changed, and no external APIs were called.

Provider metadata is preserved and reviewed, not ignored. Normalization determines what can safely become user-facing local metadata later.

## 2. Data Sources

- Seed data: `backend/sample_data.sql`
- Processed provider preview: `analytics/processed/tmdb/sample_mapping_preview.json`
- Policy reference: `docs/metadata_normalization_plan.md`

## 3. Summary Counts

- Total seeded titles: 15
- Total preview titles: 15
- Matched titles: 15
- Titles with manual review items: 15
- Proposed provider genre additions: 9
- Warnings: 17

Action totals:

- `add_provider_value`: 1
- `keep_local`: 22
- `keep_local_and_preserve_provider`: 24
- `needs_future_schema`: 15
- `needs_manual_review`: 17
- `no_action`: 131
- `provider_signal_only`: 45
- `update_from_provider`: 0

## 4. Normalization Rules Used

Genre mapping:

- `Science Fiction` -> Sci-Fi
- `Sci-Fi & Fantasy` -> Sci-Fi, Fantasy
- `Action & Adventure` -> Action, Adventure
- `Action` -> Action
- `Adventure` -> Adventure
- `Animation` -> Animation
- `Comedy` -> Comedy
- `Crime` -> Crime
- `Drama` -> Drama
- `Fantasy` -> Fantasy
- `Horror` -> Horror
- `Mystery` -> Mystery
- `Romance` -> Romance
- `Thriller` -> Thriller

Language mapping:

- `en` -> `English`
- `ko` -> `Korean`
- `de` -> `German`

Status mapping:

- `Released` -> `Released`
- `Ended` -> `Ended`
- `Returning Series` -> `Ongoing`
- `Canceled` -> `Canceled`
- `In Production` -> `Upcoming`
- `Planned` -> `Upcoming`
- `Post Production` -> `Upcoming`

Unknown provider values are not applied directly to normalized fields. They are captured as warnings and preserved for review.

## 5. Field-Level Recommendation Summary

| Field | Action Counts | Recommendation |
| --- | --- | --- |
| `age_rating` | keep_local: 15 | Keep local value until certification source exists. |
| `backdrop_url` | no_action: 15 | Already aligned; review only if mismatch appears. |
| `cast_crew` | needs_future_schema: 15 | Needs person/role schema. |
| `content_type` | no_action: 15 | Keep local movie/series model; review mismatches. |
| `external_ids` | no_action: 15 | Already safe as identity data. |
| `genres` | add_provider_value: 1, keep_local_and_preserve_provider: 9, no_action: 5 | Use provider genres as normalized enrichment, not destructive replacement. |
| `language` | no_action: 15 | Map known provider codes to readable display values. |
| `overview` | keep_local_and_preserve_provider: 15 | Keep curated local overview and preserve provider overview. |
| `popularity` | provider_signal_only: 15 | Provider signal only. |
| `poster_url` | no_action: 15 | Already aligned; review only if mismatch appears. |
| `release_date` | needs_manual_review: 8, no_action: 7 | Review provider/local date differences before update. |
| `runtime` | keep_local: 7, needs_manual_review: 2, no_action: 6 | Display known runtime; never overwrite with null. |
| `status` | needs_manual_review: 7, no_action: 8 | Normalize provider status, then review current seed differences. |
| `title` | no_action: 15 | No update unless mismatch appears. |
| `vote_average` | provider_signal_only: 15 | Provider signal only. |
| `vote_count` | provider_signal_only: 15 | Provider signal only. |
| `year` | no_action: 15 | Review with release date. |

## 6. Title-by-Title Reconciliation Table

| Title | TMDb ID | Type | Manual Review? | Proposed Genre Additions | Retained Local Genres | Runtime Action | Status Action | Notes |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| The Dark Knight | 155 | movie | yes | - | Drama | no_action | no_action | Release date differs. |
| Breaking Bad | 1396 | series | yes | - | Thriller | keep_local | needs_manual_review | Status differs after normalization. |
| Inception | 27205 | movie | yes | Adventure | Thriller | no_action | no_action | Release date differs. |
| Stranger Things | 66732 | series | yes | Action, Adventure, Mystery | Drama, Horror | keep_local | needs_manual_review | Status differs after normalization. |
| Dark | 70523 | series | yes | Fantasy | Thriller | keep_local | needs_manual_review | Status differs after normalization. |
| The Witcher | 71912 | series | yes | - | Fantasy | keep_local | needs_manual_review | Status differs after normalization. |
| The Boys | 76479 | series | yes | Adventure, Fantasy, Sci-Fi | Comedy, Crime, Drama | keep_local | needs_manual_review | Release date differs.; Status differs after normalization. |
| The Mandalorian | 82856 | series | yes | Fantasy | - | keep_local | needs_manual_review | Status differs after normalization. |
| The Last of Us | 100088 | series | yes | - | Horror, Thriller | keep_local | needs_manual_review | Status differs after normalization. |
| Interstellar | 157336 | movie | yes | - | - | no_action | no_action | Release date differs. |
| Barbie | 346698 | movie | yes | - | - | no_action | no_action | Release date differs. |
| Parasite | 496243 | movie | yes | - | - | needs_manual_review | no_action | Runtime differs. |
| Red Notice | 512195 | movie | yes | - | - | no_action | no_action | Release date differs. |
| Spider-Man: Across the Spider-Verse | 569094 | movie | yes | - | - | no_action | no_action | Release date differs. |
| Dune: Part Two | 693134 | movie | yes | - | Drama | needs_manual_review | no_action | Release date differs.; Runtime differs. |

## 7. Genre Reconciliation Details

| Title | Local Genres To Retain | Normalized Provider Genres | Proposed Additions | Action |
| --- | --- | --- | --- | --- |
| The Dark Knight | Drama | Action, Crime, Thriller | - | `keep_local_and_preserve_provider` |
| Breaking Bad | Thriller | Drama, Crime | - | `keep_local_and_preserve_provider` |
| Inception | Thriller | Action, Sci-Fi, Adventure | Adventure | `keep_local_and_preserve_provider` |
| Stranger Things | Drama, Horror | Action, Adventure, Mystery, Sci-Fi, Fantasy | Action, Adventure, Mystery | `keep_local_and_preserve_provider` |
| Dark | Thriller | Crime, Drama, Sci-Fi, Fantasy, Mystery | Fantasy | `keep_local_and_preserve_provider` |
| The Witcher | Fantasy | Drama, Action, Adventure | - | `keep_local_and_preserve_provider` |
| The Boys | Comedy, Crime, Drama | Sci-Fi, Fantasy, Action, Adventure | Adventure, Fantasy, Sci-Fi | `keep_local_and_preserve_provider` |
| The Mandalorian | - | Sci-Fi, Fantasy, Action, Adventure | Fantasy | `add_provider_value` |
| The Last of Us | Horror, Thriller | Drama | - | `keep_local_and_preserve_provider` |
| Interstellar | - | Adventure, Drama, Sci-Fi | - | `no_action` |
| Barbie | - | Comedy, Adventure, Fantasy | - | `no_action` |
| Parasite | - | Comedy, Thriller, Drama | - | `no_action` |
| Red Notice | - | Action, Comedy, Crime | - | `no_action` |
| Spider-Man: Across the Spider-Verse | - | Animation, Action, Adventure, Sci-Fi | - | `no_action` |
| Dune: Part Two | Drama | Sci-Fi, Adventure | - | `keep_local_and_preserve_provider` |

No local genres should be silently removed. Provider genres can propose additions after normalization, while local decision-support genres should remain until reviewed.

## 8. Runtime Reconciliation Details

| Title | Local Runtime | Provider Runtime | Action | Note |
| --- | ---: | ---: | --- | --- |
| The Dark Knight | 152 | 152 | `no_action` |  |
| Breaking Bad | 60 |  | `keep_local` | Never replace known representative series runtime with null. |
| Inception | 148 | 148 | `no_action` |  |
| Stranger Things | 50 |  | `keep_local` | Never replace known representative series runtime with null. |
| Dark | 53 |  | `keep_local` | Never replace known representative series runtime with null. |
| The Witcher | 60 |  | `keep_local` | Never replace known representative series runtime with null. |
| The Boys | 60 |  | `keep_local` | Never replace known representative series runtime with null. |
| The Mandalorian | 50 |  | `keep_local` | Never replace known representative series runtime with null. |
| The Last of Us | 55 |  | `keep_local` | Never replace known representative series runtime with null. |
| Interstellar | 169 | 169 | `no_action` |  |
| Barbie | 114 | 114 | `no_action` |  |
| Parasite | 132 | 133 | `needs_manual_review` | Movie runtime differs by 1 minute(s); preserve provider value for review. |
| Red Notice | 118 | 118 | `no_action` |  |
| Spider-Man: Across the Spider-Verse | 140 | 140 | `no_action` |  |
| Dune: Part Two | 166 | 167 | `needs_manual_review` | Movie runtime differs by 1 minute(s); preserve provider value for review. |

## 9. Language and Status Reconciliation Details

| Title | Local Language | Normalized Language | Language Action | Local Status | Normalized Status | Status Action |
| --- | --- | --- | --- | --- | --- | --- |
| The Dark Knight | English | English | `no_action` | Released | Released | `no_action` |
| Breaking Bad | English | English | `no_action` | Released | Ended | `needs_manual_review` |
| Inception | English | English | `no_action` | Released | Released | `no_action` |
| Stranger Things | English | English | `no_action` | Released | Ended | `needs_manual_review` |
| Dark | German | German | `no_action` | Released | Ended | `needs_manual_review` |
| The Witcher | English | English | `no_action` | Released | Ongoing | `needs_manual_review` |
| The Boys | English | English | `no_action` | Released | Ended | `needs_manual_review` |
| The Mandalorian | English | English | `no_action` | Released | Ended | `needs_manual_review` |
| The Last of Us | English | English | `no_action` | Released | Ongoing | `needs_manual_review` |
| Interstellar | English | English | `no_action` | Released | Released | `no_action` |
| Barbie | English | English | `no_action` | Released | Released | `no_action` |
| Parasite | Korean | Korean | `no_action` | Released | Released | `no_action` |
| Red Notice | English | English | `no_action` | Released | Released | `no_action` |
| Spider-Man: Across the Spider-Verse | English | English | `no_action` | Released | Released | `no_action` |
| Dune: Part Two | English | English | `no_action` | Released | Released | `no_action` |

## 10. Metadata Preservation Notes

- Provider metadata should not blindly overwrite local fields.
- Provider metadata should also not be silently discarded.
- Unknown/unmapped values should be preserved in reports, JSON artifacts, import logs, or future provenance tables.
- Conflicting values should be reviewed, not ignored.
- Local curated values and provider values should remain traceable.

## 11. Safe Future Update Candidates

- Missing normalized provider genres can be proposed for addition after review.
- Series statuses such as `Ended` and `Ongoing` are likely useful but should be reviewed before changing seed data.
- Missing local language values, if any appear later, can be filled from normalized provider codes.
- Missing local movie runtime can be filled from a verified provider value.

## 12. Fields Not To Update Yet

- Curated overview text should not be overwritten.
- Existing runtime should not be replaced by null.
- Local genres should not be destructively removed.
- `age_rating` needs a certification/source strategy before provider updates.
- Cast/crew needs person/role schema before import or display.
- TMDb vote average, vote count, and popularity are provider-specific signals only.
- Ratings, summaries, verdicts, and InsightStream scores are out of scope for this metadata phase.

## 13. Recommended Next Task

Create a person/cast/crew schema plan, then return to a normalized metadata import plan that can apply safe updates with review/provenance support.
