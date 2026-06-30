# TMDb Metadata Gap Analysis

Generated at: `2026-06-13T06:47:24.219304+00:00`

This report compares the current canonical seed data in `backend/sample_data.sql` against the processed TMDb preview in `analytics/processed/tmdb/sample_mapping_preview.json`.

It is analysis-only. It does not update PostgreSQL, does not call TMDb, and does not recommend blindly importing provider data.

## Summary

- Total seeded titles: 15
- Total preview titles: 15
- Matched by `tmdb_id`: 15
- Missing preview count: 0
- Extra preview IDs not in seed: 0
- Total comparison notes/warnings: 43
- Seed content split: {'movie': 8, 'series': 7}
- Preview media split: {'movie': 8, 'tv': 7}

## Important Findings

- Poster and backdrop URLs match the processed preview for all 15 seeded titles.
- IMDb IDs are available in the processed preview for all 15 titles and belong in `external_ids`, not `content`.
- TMDb genres do not map cleanly to the local genre taxonomy without normalization.
- TMDb TV runtime values are missing/null for the current series preview rows, so current seeded runtimes should be kept for now.
- TMDb language values are provider codes such as `en`, `ko`, and `de`; local seed data uses readable names.
- TMDb status values can differ from the current local seed convention, especially for series.
- Cast and director/creator data is available, but the current schema needs person/role tables before importing it.
- TMDb vote average, vote count, and popularity are provider-specific analytics signals and should not be written into `content_summary` directly.

## Field-by-Field Summary

| Field | Current Result | Gap | Recommendation |
| --- | --- | --- | --- |
| title | 15/15 match | No import needed. | Keep current titles unless a manual cleanup task decides otherwise. |
| content_type/media_type | 15/15 match | No schema change needed for movie/series mapping. | Keep broad movie/series values for now. |
| release_date/year | 7/15 release dates match | Some provider dates differ from curated seed dates. | Do not overwrite until release-date policy is decided. |
| runtime | 6/15 match | TV runtimes are mostly null in preview; a few movie runtimes differ. | Keep current seed runtime for now. |
| language | 15/15 normalize cleanly | TMDb returns language codes, seed stores readable names. | Add a normalization map before import. |
| status | 8/15 match | TV status values differ from current seed wording. | Normalize before import. |
| poster_url/backdrop_url | 15/15 posters and 15/15 backdrops match | Already aligned with processed preview. | Safe to keep current seed values. |
| genres | 3/15 raw genre sets match | Provider naming/grouping differs from local taxonomy. | Use a genre normalization map before import. |
| overview | 15/15 available | TMDb overviews often differ from curated seed summaries. | Do not overwrite curated overview yet. |
| imdb_id | 15/15 available | Already suitable for external_ids seed validation. | Safe as external ID data, not content table data. |
| cast/director/creator | 15/15 cast lists; 15/15 director/creator lists | Current schema has no person/role model. | Plan person schema before import. |
| vote/popularity | 15/15 available | Provider-specific signal, not current InsightStream scoring. | Do not write into content_summary directly. |

## Title-by-Title Comparison

| Title | TMDb ID | Type | Media OK | Dates | Runtime | Language | Status | Poster | Backdrop | IMDb | Credits | Notes |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| The Dark Knight | 155 | movie | yes | 2008-07-18 -> 2008-07-16 | 152 -> 152 | English -> en | Released -> Released | yes | yes | tt0468569 | cast 5, people 1 | Release date differs.; Genre mapping differs: Local only: Drama. |
| Breaking Bad | 1396 | series | yes | 2008-01-20 -> 2008-01-20 | 60 -> None | English -> en | Released -> Ended | yes | yes | tt0903747 | cast 5, people 1 | Missing or empty episode_run_time; runtime is approximate/null.; Runtime differs or is unavailable in TMDb preview.; Status differs and needs normalization before import.; Genre mapping differs: Local only: Thriller. |
| Inception | 27205 | movie | yes | 2010-07-16 -> 2010-07-15 | 148 -> 148 | English -> en | Released -> Released | yes | yes | tt1375666 | cast 5, people 1 | Release date differs.; Genre mapping differs: Local only: Thriller; TMDb only: Adventure. |
| Stranger Things | 66732 | series | yes | 2016-07-15 -> 2016-07-15 | 50 -> None | English -> en | Released -> Ended | yes | yes | tt4574334 | cast 5, people 2 | Missing or empty episode_run_time; runtime is approximate/null.; Runtime differs or is unavailable in TMDb preview.; Status differs and needs normalization before import.; Genre mapping differs: Local only: Drama, Horror; TMDb only: Action, Adventure, Mystery. |
| Dark | 70523 | series | yes | 2017-12-01 -> 2017-12-01 | 53 -> None | German -> de | Released -> Ended | yes | yes | tt5753856 | cast 1, people 2 | Missing or empty episode_run_time; runtime is approximate/null.; Runtime differs or is unavailable in TMDb preview.; Status differs and needs normalization before import.; Genre mapping differs: Local only: Thriller; TMDb only: Fantasy. |
| The Witcher | 71912 | series | yes | 2019-12-20 -> 2019-12-20 | 60 -> None | English -> en | Released -> Returning Series | yes | yes | tt5180504 | cast 5, people 1 | Missing or empty episode_run_time; runtime is approximate/null.; Runtime differs or is unavailable in TMDb preview.; Status differs and needs normalization before import.; Genre mapping differs: Local only: Fantasy. |
| The Boys | 76479 | series | yes | 2019-07-26 -> 2019-07-25 | 60 -> None | English -> en | Released -> Ended | yes | yes | tt1190634 | cast 5, people 1 | Missing or empty episode_run_time; runtime is approximate/null.; Release date differs.; Runtime differs or is unavailable in TMDb preview.; Status differs and needs normalization before import.; Genre mapping differs: Local only: Comedy, Crime, Drama; TMDb only: Adventure, Fantasy, Sci-Fi. |
| The Mandalorian | 82856 | series | yes | 2019-11-12 -> 2019-11-12 | 50 -> None | English -> en | Released -> Ended | yes | yes | tt8111088 | cast 2, people 1 | Missing or empty episode_run_time; runtime is approximate/null.; Runtime differs or is unavailable in TMDb preview.; Status differs and needs normalization before import.; Genre mapping differs: TMDb only: Fantasy. |
| The Last of Us | 100088 | series | yes | 2023-01-15 -> 2023-01-15 | 55 -> None | English -> en | Released -> Returning Series | yes | yes | tt3581920 | cast 4, people 2 | Missing or empty episode_run_time; runtime is approximate/null.; Runtime differs or is unavailable in TMDb preview.; Status differs and needs normalization before import.; Genre mapping differs: Local only: Horror, Thriller. |
| Interstellar | 157336 | movie | yes | 2014-11-07 -> 2014-11-05 | 169 -> 169 | English -> en | Released -> Released | yes | yes | tt0816692 | cast 5, people 1 | Release date differs.; Genre mapping differs: Naming/grouping difference only. |
| Barbie | 346698 | movie | yes | 2023-07-21 -> 2023-07-19 | 114 -> 114 | English -> en | Released -> Released | yes | yes | tt1517268 | cast 5, people 1 | Release date differs. |
| Parasite | 496243 | movie | yes | 2019-05-30 -> 2019-05-30 | 132 -> 133 | Korean -> ko | Released -> Released | yes | yes | tt6751668 | cast 5, people 1 | Runtime differs or is unavailable in TMDb preview. |
| Red Notice | 512195 | movie | yes | 2021-11-12 -> 2021-11-04 | 118 -> 118 | English -> en | Released -> Released | yes | yes | tt7991608 | cast 5, people 1 | Release date differs. |
| Spider-Man: Across the Spider-Verse | 569094 | movie | yes | 2023-06-02 -> 2023-05-31 | 140 -> 140 | English -> en | Released -> Released | yes | yes | tt9362722 | cast 5, people 3 | Release date differs.; Genre mapping differs: Naming/grouping difference only. |
| Dune: Part Two | 693134 | movie | yes | 2024-03-01 -> 2024-02-27 | 166 -> 167 | English -> en | Released -> Released | yes | yes | tt15239678 | cast 5, people 1 | Release date differs.; Runtime differs or is unavailable in TMDb preview.; Genre mapping differs: Local only: Drama. |

## Genre Analysis

Local genres and TMDb genres should not be merged directly. TMDb uses broader or differently named categories in several places.

| Title | Local Genres | TMDb Genres | Normalized Difference |
| --- | --- | --- | --- |
| The Dark Knight | Action, Crime, Drama, Thriller | Action, Crime, Thriller | Local only: Drama |
| Breaking Bad | Crime, Drama, Thriller | Drama, Crime | Local only: Thriller |
| Inception | Action, Sci-Fi, Thriller | Action, Science Fiction, Adventure | Local only: Thriller; TMDb only: Adventure |
| Stranger Things | Drama, Fantasy, Horror, Sci-Fi | Action & Adventure, Mystery, Sci-Fi & Fantasy | Local only: Drama, Horror; TMDb only: Action, Adventure, Mystery |
| Dark | Crime, Drama, Mystery, Sci-Fi, Thriller | Crime, Drama, Sci-Fi & Fantasy, Mystery | Local only: Thriller; TMDb only: Fantasy |
| The Witcher | Action, Adventure, Drama, Fantasy | Drama, Action & Adventure | Local only: Fantasy |
| The Boys | Action, Comedy, Crime, Drama | Sci-Fi & Fantasy, Action & Adventure | Local only: Comedy, Crime, Drama; TMDb only: Adventure, Fantasy, Sci-Fi |
| The Mandalorian | Action, Adventure, Sci-Fi | Sci-Fi & Fantasy, Action & Adventure | TMDb only: Fantasy |
| The Last of Us | Drama, Horror, Thriller | Drama | Local only: Horror, Thriller |
| Interstellar | Adventure, Drama, Sci-Fi | Adventure, Drama, Science Fiction | Naming/grouping difference only |
| Barbie | Adventure, Comedy, Fantasy | Comedy, Adventure, Fantasy | Match |
| Parasite | Comedy, Drama, Thriller | Comedy, Thriller, Drama | Match |
| Red Notice | Action, Comedy, Crime | Action, Comedy, Crime | Match |
| Spider-Man: Across the Spider-Verse | Action, Adventure, Animation, Sci-Fi | Animation, Action, Adventure, Science Fiction | Naming/grouping difference only |
| Dune: Part Two | Adventure, Drama, Sci-Fi | Science Fiction, Adventure | Local only: Drama |

Observed normalization needs:

- `Sci-Fi` vs `Science Fiction`
- `Sci-Fi`/`Fantasy` vs `Sci-Fi & Fantasy`
- `Action`/`Adventure` vs `Action & Adventure`
- Some local genres intentionally add decision-support nuance that TMDb does not provide for the same title.

Recommendation: create a future genre normalization map before importing provider genres. Do not direct-import TMDb genres into the local taxonomy yet.

Local genre frequency:

- Action: 7
- Adventure: 6
- Animation: 1
- Comedy: 4
- Crime: 5
- Drama: 10
- Fantasy: 3
- Horror: 2
- Mystery: 1
- Sci-Fi: 7
- Thriller: 6

TMDb genre frequency:

- Action: 4
- Action & Adventure: 4
- Adventure: 5
- Animation: 1
- Comedy: 3
- Crime: 4
- Drama: 6
- Fantasy: 1
- Mystery: 2
- Sci-Fi & Fantasy: 4
- Science Fiction: 4
- Thriller: 2

## Runtime Analysis

| Title | Type | Seed Runtime | TMDb Runtime | Recommendation |
| --- | --- | ---: | ---: | --- |
| The Dark Knight | movie | 152 | 152 | No change needed. |
| Breaking Bad | series | 60 |  | Keep seed runtime; TMDb preview has null TV runtime. |
| Inception | movie | 148 | 148 | No change needed. |
| Stranger Things | series | 50 |  | Keep seed runtime; TMDb preview has null TV runtime. |
| Dark | series | 53 |  | Keep seed runtime; TMDb preview has null TV runtime. |
| The Witcher | series | 60 |  | Keep seed runtime; TMDb preview has null TV runtime. |
| The Boys | series | 60 |  | Keep seed runtime; TMDb preview has null TV runtime. |
| The Mandalorian | series | 50 |  | Keep seed runtime; TMDb preview has null TV runtime. |
| The Last of Us | series | 55 |  | Keep seed runtime; TMDb preview has null TV runtime. |
| Interstellar | movie | 169 | 169 | No change needed. |
| Barbie | movie | 114 | 114 | No change needed. |
| Parasite | movie | 132 | 133 | Review manually before changing seed runtime. |
| Red Notice | movie | 118 | 118 | No change needed. |
| Spider-Man: Across the Spider-Verse | movie | 140 | 140 | No change needed. |
| Dune: Part Two | movie | 166 | 167 | Review manually before changing seed runtime. |

## Credits Analysis

Credits are useful for the future detail page, but they require person and role schema before import.

| Title | Top Cast Available | Director/Creator Available | Top Cast Preview | Director/Creator Preview |
| --- | ---: | ---: | --- | --- |
| The Dark Knight | 5 | 1 | Christian Bale, Heath Ledger, Aaron Eckhart... | Christopher Nolan |
| Breaking Bad | 5 | 1 | Bryan Cranston, Aaron Paul, Anna Gunn... | Vince Gilligan |
| Inception | 5 | 1 | Leonardo DiCaprio, Joseph Gordon-Levitt, Ken Watanabe... | Christopher Nolan |
| Stranger Things | 5 | 2 | Winona Ryder, David Harbour, Millie Bobby Brown... | Ross Duffer, Matt Duffer |
| Dark | 1 | 2 | Louis Hofmann | Baran bo Odar, Jantje Friese |
| The Witcher | 5 | 1 | Liam Hemsworth, Anya Chalotra, Freya Allan... | Lauren Schmidt Hissrich |
| The Boys | 5 | 1 | Karl Urban, Jack Quaid, Antony Starr... | Eric Kripke |
| The Mandalorian | 2 | 1 | Pedro Pascal, Katee Sackhoff | Jon Favreau |
| The Last of Us | 4 | 2 | Bella Ramsey, Gabriel Luna, Isabela Merced... | Neil Druckmann, Craig Mazin |
| Interstellar | 5 | 1 | Matthew McConaughey, Anne Hathaway, Michael Caine... | Christopher Nolan |
| Barbie | 5 | 1 | Margot Robbie, Ryan Gosling, America Ferrera... | Greta Gerwig |
| Parasite | 5 | 1 | Song Kang-ho, Lee Sun-kyun, Cho Yeo-jeong... | Bong Joon Ho |
| Red Notice | 5 | 1 | Dwayne Johnson, Ryan Reynolds, Gal Gadot... | Rawson Marshall Thurber |
| Spider-Man: Across the Spider-Verse | 5 | 3 | Shameik Moore, Hailee Steinfeld, Brian Tyree Henry... | Justin K. Thompson, Kemp Powers, Joaquim Dos Santos |
| Dune: Part Two | 5 | 1 | Timothée Chalamet, Zendaya, Rebecca Ferguson... | Denis Villeneuve |

## Provider-Specific Analytics Signals

| Title | Vote Average | Vote Count | Popularity | Recommendation |
| --- | ---: | ---: | ---: | --- |
| The Dark Knight | 8.5 | 35875 | 41.699 | Keep as provider-specific input; do not write into `content_summary` directly. |
| Breaking Bad | 8.946 | 17901 | 158.4361 | Keep as provider-specific input; do not write into `content_summary` directly. |
| Inception | 8.372 | 39341 | 32.9299 | Keep as provider-specific input; do not write into `content_summary` directly. |
| Stranger Things | 8.564 | 21278 | 132.5819 | Keep as provider-specific input; do not write into `content_summary` directly. |
| Dark | 8.424 | 7588 | 41.9549 | Keep as provider-specific input; do not write into `content_summary` directly. |
| The Witcher | 7.915 | 6703 | 47.1923 | Keep as provider-specific input; do not write into `content_summary` directly. |
| The Boys | 8.453 | 12894 | 342.517 | Keep as provider-specific input; do not write into `content_summary` directly. |
| The Mandalorian | 8.41 | 10968 | 71.3149 | Keep as provider-specific input; do not write into `content_summary` directly. |
| The Last of Us | 8.428 | 7045 | 43.4921 | Keep as provider-specific input; do not write into `content_summary` directly. |
| Interstellar | 8.478 | 39976 | 67.4273 | Keep as provider-specific input; do not write into `content_summary` directly. |
| Barbie | 6.922 | 11136 | 20.6207 | Keep as provider-specific input; do not write into `content_summary` directly. |
| Parasite | 8.494 | 20706 | 36.4975 | Keep as provider-specific input; do not write into `content_summary` directly. |
| Red Notice | 6.731 | 6453 | 7.4526 | Keep as provider-specific input; do not write into `content_summary` directly. |
| Spider-Man: Across the Spider-Verse | 8.337 | 8654 | 30.1341 | Keep as provider-specific input; do not write into `content_summary` directly. |
| Dune: Part Two | 8.128 | 8019 | 23.0595 | Keep as provider-specific input; do not write into `content_summary` directly. |

## Recommendations

### A. Safe to Keep/Update Now

- `poster_url`
- `backdrop_url`
- `external_ids` for `tmdb` and `imdb`

These fields already have a clear storage location and have been verified through the processed preview.

### B. Needs Normalization Before Import

- `genres`
- `language`
- `status`

These fields are useful, but provider values should pass through normalization rules before changing local seed data or production tables.

### C. Needs New Schema Before Import

- cast
- directors
- creators

Credits should wait for `persons` and content-person role tables. Do not squeeze this data into text fields.

### D. Should Not Overwrite Yet

- curated `overview`
- manually chosen `runtime`
- existing ratings
- existing summaries, pros, cons, verdicts, and unified scores

Current seed values support the product narrative and tests. Provider values may be useful later, but they should not overwrite curated fields without a separate product decision.

### E. Provider-Specific Analytics Signals

- `vote_average`
- `vote_count`
- `popularity`

These should remain provider-specific inputs for future analytics/scoring work. They should not become the InsightStream unified score by direct assignment.

## Suggested Next Task

Create a genre/language/status normalization plan before importing additional TMDb metadata. That plan should define allowed local values, provider mappings, and fields that should stay curated.

## Final Summary

The processed TMDb preview confirms that the current seed already safely uses real media URLs and external IDs for all 15 titles. The remaining useful TMDb metadata should be imported only after normalization rules, provenance decisions, and person/credits schema are planned.
