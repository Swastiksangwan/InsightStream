# Ratings Foundation Plan

## 1. Purpose

Ratings Foundation defines how InsightStream should store, normalize, expose, and display trusted rating signals for movies and series.

The goal is to help users decide what to watch by showing clear, source-aware rating data on content detail pages. The model should preserve raw provider scores, normalize different scales into a comparable 0-100 range, and support a future InsightStream unified score without tying the database to any one provider.

This phase should solve:

- showing trusted rating signals on content detail pages
- normalizing different rating scales
- supporting a future InsightStream unified score
- helping users make a watch decision
- staying provider-neutral and source-aware

Out of scope for this phase:

- user reviews
- review summarization
- AI verdicts
- sentiment analysis
- personalized recommendations
- scraping rating websites
- overloading the UI with too many sources

Ratings should be useful decision support, not a cluttered scoreboard.

## Implementation Status

Ratings Foundation v1 implements TMDb ratings. Ratings v2 adds IMDb ratings
through IMDb's official non-commercial `title.ratings.tsv` dataset.

The implemented path is:

- `rating_sources`
- `content_ratings`
- TMDb `vote_average` / `vote_count` in `sample_mapping_preview.json`
- `analytics/scripts/import_content_ratings_from_preview.py`
- `analytics/scripts/import_imdb_ratings.py`
- content detail API ratings object
- frontend Ratings card with InsightStream Score and source breakdown

Ratings display available source ratings even when vote counts are low,
but the unified InsightStream Score only includes sources with at least 50 votes.
Low-vote or unknown-vote sources remain visible as source ratings without
contributing to the unified score.

IMDb integration uses a local dataset file and matches only through stored IMDb
external IDs. It does not scrape IMDb pages.

Letterboxd is being evaluated through a local dataset preview script only.
It is not imported into `content_ratings` yet and does not contribute to the
InsightStream Score.

Rotten Tomatoes, Letterboxd, Metacritic, CinemaScore, reviews, AI verdicts, and recommendations remain future phases.

## 2. Rating Source Strategy

Not all rating sources are equivalent. InsightStream should separate sources by category and source quality instead of flattening every score into the same meaning.

Audience / community rating signals:

- TMDb
- IMDb
- Letterboxd
- Rotten Tomatoes Audience Score / Popcornmeter, if legally available later

Critic rating signals:

- Rotten Tomatoes Tomatometer, if legally available later
- Metacritic Metascore, if legally available later

Theatrical audience reaction:

- CinemaScore, movie-only and only if data access is appropriate

Phase 1 should implement TMDb ratings first because `vote_average` and `vote_count` are already available in TMDb content metadata fetched by the ingestion pipeline.

Phase 2 adds IMDb ratings because IMDb IDs are already obtained through TMDb external IDs. The prototype path uses IMDb's official non-commercial dataset file.

Rotten Tomatoes, Letterboxd, Metacritic, and CinemaScore should be planned in the schema, but not implemented until source access, legality, terms, and maintenance are clear.

Do not scrape rating websites.

## 3. Phased Source Rollout

| Phase | Source | Why | Implementation Status |
| --- | --- | --- | --- |
| Phase 1 | TMDb | Already available in fetched metadata and safest first implementation. | Implemented |
| Phase 2 | IMDb | Strong user recognition and matchable through existing IMDb external IDs. | Implemented through official non-commercial dataset import |
| Phase 3 | Rotten Tomatoes / Metacritic | Useful critic and audience signals. | Wait for legal/source access |
| Phase 4 | Letterboxd | Strong film-pop-culture signal, mostly film-focused. | Preview-only local dataset matching under evaluation |
| Phase 5 | CinemaScore | Useful movie-only theatrical opening reaction with limited coverage. | Optional later signal |

## 4. Proposed Database Model

Avoid provider-specific columns such as:

- `content.tmdb_rating`
- `content.imdb_rating`
- `content.rotten_tomatoes_rating`

Prefer provider-neutral tables.

### `rating_sources`

Suggested fields:

- `id`
- `source_name`
- `display_name`
- `source_category`
- `raw_score_scale_default`
- `weight`
- `is_active`
- `source_url`
- `notes`
- `created_at`
- `updated_at`

Suggested `source_category` values:

- `audience`
- `critic`
- `theatrical`
- `internal`

### `content_ratings`

Suggested fields:

- `id`
- `content_id`
- `rating_source_id`
- `raw_score`
- `raw_score_scale`
- `normalized_score`
- `vote_count`
- `rating_count_label`
- `rating_url`
- `source_payload`
- `fetched_at`
- `created_at`
- `updated_at`

Suggested constraints:

- foreign key to `content`
- foreign key to `rating_sources`
- `UNIQUE (content_id, rating_source_id)`
- `normalized_score` between 0 and 100 where applicable
- `vote_count` non-negative where available

### Optional Future Table: `content_rating_snapshots`

This is not required in v1. It could later store rating history over time so the app can understand score movement, launch-window reactions, or stale rating data.

## 5. Normalization Rules

Normalize comparable scores into a 0-100 range while preserving the original raw score.

Examples:

- TMDb `8.4/10` -> `84`
- IMDb `8.6/10` -> `86`
- Letterboxd `4.2/5` -> `84`
- Metacritic `84/100` -> `84`
- Rotten Tomatoes `93%` -> `93`

CinemaScore is letter-grade based. It should not be blindly averaged into numeric scores without a documented mapping. For v1, CinemaScore should be stored and displayed separately if added later.

Important rules:

- Always preserve `raw_score`.
- Use `normalized_score` for comparison.
- Preserve `raw_score_scale`.
- Source category matters.
- Critic and audience signals should not be treated as identical.

## 6. Vote Count and Confidence

A score with many votes is more reliable than a score with very few votes.

For v1, keep confidence simple:

- store `vote_count`
- display `vote_count` where available
- require at least 50 votes before including a source in the unified score
- continue displaying low-vote source ratings even when they do not contribute to the unified score

Example:

- TMDb score with 20 votes should have lower confidence than TMDb score with 20,000 votes.

Do not implement complex Bayesian ranking in v1. It can be considered later if rankings become a product focus.

## 7. Unified Score v1

Recommended v1 formula:

```text
InsightStream Score = weighted average of available normalized source scores
```

Rules:

- ignore missing sources
- include only active rating sources
- use `rating_sources.weight`
- TMDb and IMDb audience sources can contribute when they have enough vote confidence
- use TMDb + IMDb weighted average when both are present
- do not include CinemaScore until a clear letter-grade mapping is approved
- do not include critic and audience sources blindly without category awareness

Example:

```text
TMDb: 82
IMDb: 86
Equal weights

InsightStream Score = 84
```

The v1 score should be simple and transparent. Future versions can separate audience score and critic score.

## 8. Ingestion Strategy

### Phase 1: TMDb

`fetch_tmdb_sample.py` already receives `vote_average` and `vote_count` from TMDb details.

Implementation options:

- extend `sample_mapping_preview.json` to include rating fields
- import TMDb ratings through `import_content_metadata_from_preview.py` or a dedicated ratings importer
- seed `rating_sources` with TMDb as an active audience source
- store TMDb rating rows in `content_ratings`

### Phase 2: IMDb

IMDb IDs are already present through `external_ids`.

IMDb ratings are imported from a local copy of IMDb's official non-commercial
`title.ratings.tsv` dataset. The importer matches `tconst` values only against
stored `external_ids.external_id` rows where `source_name = 'imdb'`.

Do not commit the dataset file and do not scrape IMDb pages.

### Letterboxd Preview Evaluation

Letterboxd ratings are being evaluated through a local JSONL dataset preview
before any database import is considered. The preview script matches local
movie catalog rows against Letterboxd rows using normalized title, year, and
director overlap.

Matching is intentionally conservative because Letterboxd rows do not provide a
provider ID that already exists in the local `external_ids` table. Title/year
matching can produce false positives, especially around remakes, alternate
release years, and duplicated film titles.

Rules for this evaluation:

- output a preview/report for manual review
- do not write to `content_ratings`
- do not use or store review text
- do not scrape Letterboxd
- keep Letterboxd out of the InsightStream Score until match confidence,
  vote-count handling, and source policy are decided

### Future Sources

Rotten Tomatoes, Letterboxd, Metacritic, and CinemaScore should only be implemented when legal/source-approved access is available.

### Refresh

Ratings change over time. Ratings should refresh during content metadata refresh or through a dedicated ratings refresh flow. Store `fetched_at` so stale data can be identified.

## 9. Backend API Contract

Recommended content detail response shape:

```json
{
  "ratings": {
    "unified_score": 84,
    "source_count": 2,
    "sources": [
      {
        "source_name": "tmdb",
        "display_name": "TMDb",
        "source_category": "audience",
        "raw_score": 8.2,
        "raw_score_scale": 10,
        "normalized_score": 82,
        "vote_count": 24000,
        "fetched_at": "2026-06-24T00:00:00Z"
      }
    ]
  }
}
```

For no ratings, recommended response:

```json
{
  "ratings": {
    "unified_score": null,
    "source_count": 0,
    "sources": []
  }
}
```

This is preferable to `ratings: null` because it keeps the frontend shape stable and lets the Ratings card render a clean empty state without defensive branching.

## 10. Frontend Display Plan

The existing Ratings card should evolve into a compact decision-support panel.

Recommended v1 display:

- InsightStream Score
- source breakdown
- vote count
- missing state

Example:

```text
InsightStream Score: 82

Source ratings:
TMDb: 8.2/10 · 24K votes
IMDb: 8.6/10 · 1.2M votes
```

Future category display:

- Audience signals
- Critic signals
- Theatrical reaction

Frontend rules:

- only show sources that exist
- do not show empty placeholders
- keep the UI compact
- avoid too many badges and clutter
- show "Not enough rating data yet" when no ratings exist

## 11. Health Checks

Recommended health checks:

- `rating_sources` has TMDb seeded
- no duplicate `content_ratings` rows for the same content/source
- `normalized_score` is between 0 and 100
- `raw_score_scale` is positive
- `vote_count` is non-negative
- rating coverage percentage across the catalog
- content detail pages handle missing ratings cleanly

These checks should be added to the ingestion health check once ratings tables exist.

## 12. Tests

Recommended tests:

- TMDb rating is imported from preview
- duplicate rating rows are not created
- normalized score is calculated correctly
- content detail API returns ratings
- content detail API handles no-ratings content
- frontend Ratings card renders rating data
- frontend Ratings card renders empty state

Avoid brittle catalog-count tests.

## 13. Implementation Phases

1. Add ratings schema and TMDb source seed.
2. Add TMDb rating fields to metadata preview.
3. Import TMDb ratings into `content_ratings`.
4. Add ratings to content detail API.
5. Update frontend Ratings card.
6. Add health checks and tests.
7. Add IMDb ratings through the official non-commercial dataset importer.
8. Later evaluate Rotten Tomatoes, Letterboxd, Metacritic, and CinemaScore.

## 14. Risks and Decisions

Open decisions:

- exact unified score formula
- whether to separate audience score and critic score later
- legal/source access for non-TMDb sources
- whether IMDb dataset refresh should be manual or scheduled during prototype use
- whether rating history snapshots are needed
- whether low vote counts should suppress source display or only suppress unified score inclusion

## 15. Recommended Next Task

Recommended next implementation task:

```text
Harden ratings refresh and source health checks
```

Suggested scope:

- keep TMDb ratings refreshed through the metadata preview importer
- refresh IMDb ratings from the local official dataset when a new dataset is downloaded
- monitor missing IMDb coverage in the ingestion health check
- keep non-TMDb/non-IMDb sources out until source/legal access is clear

This keeps Ratings Foundation source-aware, local-dataset driven, and aligned with the ingestion pipeline.
