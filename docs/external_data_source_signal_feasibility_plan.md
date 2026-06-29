# External Data Source & Signal Feasibility Plan

## 1. Purpose

InsightStream needs external/source-enriched data beyond the current local metadata because richer decision support depends on more than titles, genres, cast, ratings, and availability.

The current local metadata is enough for strong baseline detail pages. It can tell users what a title is, who is in it, where it is available, whether it is ongoing, and how it scores across current rating sources.

Ratings are useful but incomplete. A score can say that a title is well-liked, but it usually does not explain:

- tone
- mood
- pacing
- intensity
- review themes
- critic vs audience split
- expectation signals
- whether the experience is light, bleak, tense, slow-burn, action-heavy, dialogue-heavy, or emotionally intense

Better decision support needs source signals that explain what the watch experience may feel like. Every source must be evaluated for:

- access
- legality
- freshness
- reliability
- matching safety
- implementation difficulty
- product value

This plan does not implement ingestion. It defines which source directions are safe to evaluate next.

## 2. Current Source Inventory

### TMDb Metadata

Current use:

- content title
- overview
- release dates
- runtime
- posters/backdrops
- genres
- credits
- people/person details
- series lifecycle fields
- season summary fields
- availability/certification through the current ingestion flow

Strengths:

- already integrated in the metadata pipeline
- broad movie/series coverage
- useful structured fields
- provider IDs are stored through `external_ids`
- supports repeatable preview/import workflow

Limitations:

- not all fields are equally complete
- provider data can change
- provider-specific payloads must remain isolated from frontend/product logic
- TMDb does not fully answer tone, mood, pacing, or review consensus from current fields alone

Freshness strategy:

- periodic metadata refresh
- targeted refresh for active/ongoing series
- run reports and previews before imports

### TMDb Ratings

Current use:

- source rating in Ratings card
- normalized source score
- contributes to InsightStream Score when vote-backed

Strengths:

- already fetched in content details
- vote count available
- easy normalization from 10-point scale

Limitations:

- audience/community rating only
- may be less recognizable than IMDb for some users
- rating alone does not explain viewing experience

Freshness strategy:

- refresh through content metadata preview/import or a dedicated ratings refresh flow

### IMDb Official Non-Commercial Dataset Ratings

Current use:

- imported from official IMDb `title.ratings.tsv`
- matched through stored IMDb external IDs
- displayed in Ratings card
- contributes to InsightStream Score when vote-backed

Strengths:

- strong user recognition
- official dataset access path
- external-ID matching avoids title-only matching
- vote count available

Limitations:

- ratings only, not mood/review themes
- dataset refresh is separate from API ingestion
- non-commercial terms must remain respected

Freshness strategy:

- manual or weekly local dataset refresh for prototype use
- no scraping

### Letterboxd Local Dataset Snapshot Ratings

Current use:

- imported from manually reviewed local dataset preview
- displayed as film-community snapshot
- linked to source page when URL is available
- excluded from InsightStream Score v1

Strengths:

- useful film-community signal
- complements TMDb/IMDb for movie-focused discovery
- dataset preview/review workflow reduces false matches

Limitations:

- no reliable vote count in current dataset
- matching is title/year/director based, not external-ID based
- snapshot may be stale
- review text is not used and should not be displayed

Freshness strategy:

- manual dataset snapshot refresh only
- preview/report/manual review before import
- do not import ambiguous matches without approval

### Availability/Certification From Current Ingestion Flow

Current use:

- region-aware availability
- certification/age rating
- frontend detail display
- Discover platform filtering
- Insight Summary decision signals

Strengths:

- very useful for watch decisions
- region-aware
- already local database-backed

Limitations:

- provider availability may change frequently
- region fallback must be labeled carefully
- does not explain mood/tone/pacing

Freshness strategy:

- periodic availability/certification refresh
- keep region labels explicit

## 3. Candidate Source Categories

### Structured Metadata Enrichment

Examples:

- TMDb keywords
- TMDb genres
- TMDb watch providers
- TMDb reviews metadata if allowed later
- IMDb title datasets
- existing cast/crew/person metadata

Structured metadata should be the first expansion path because it is easier to normalize, easier to test, and less legally risky than review text.

### Ratings and Score Sources

Examples:

- TMDb
- IMDb
- Letterboxd dataset snapshot
- Rotten Tomatoes only if licensed/approved
- Metacritic only if licensed/approved
- CinemaScore only if accessible/appropriate

Ratings can improve decision support, but they should not be treated as review consensus. Scores need source category, vote count, confidence, and freshness context.

### Review and Text Sources

Examples:

- TMDb reviews if terms/product policy allow
- Letterboxd reviews only if dataset/source policy allows
- IMDb reviews only through an approved/source-legal path
- critic sources only through approved/licensed access

Review text is high-risk compared with structured metadata. Review ingestion must wait for explicit source/legal decisions.

### Derived/Internal Signals

Examples:

- long watch
- completed binge
- active series
- rent/buy only
- high audience score
- low confidence score
- streaming available

Internal signals are safe and immediately useful because they can be derived from stored local fields.

## 4. Feasibility Matrix

| Source | Data type | Product value | Access path | Freshness | Legal/source risk | Implementation difficulty | Recommended phase | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TMDb keywords | Structured tags | High for mood/tone/expectation prototypes | TMDb API via existing provider pipeline | Periodic refresh | Low to medium; follow TMDb terms | Medium | Evaluate next | Best near-term source before review text |
| TMDb reviews | Review text/metadata | Medium to high if allowed | TMDb API, subject to terms/product policy | Periodic refresh | Medium; review text handling required | Medium | Prototype only after policy review | Do not display raw text initially |
| IMDb official datasets | Structured title/rating data | High for ratings and identifiers | Official non-commercial files | Manual/weekly prototype refresh | Low if terms respected | Medium | Use now for ratings, evaluate additional datasets carefully | Use external IDs; avoid title-only imports |
| Letterboxd dataset snapshot | Ratings and possible text fields | Medium for film-community signal | Local dataset snapshot with preview/review | Manual snapshot refresh | Medium; dataset/source policy must be respected | Medium | Prototype only / display snapshot rating | Do not use review text; no score contribution v1 |
| Letterboxd official API | Ratings/reviews if available | Potentially high | Official API only if available/approved | Source-specific | Unknown/medium | Unknown | Evaluate later | Do not assume access |
| Rotten Tomatoes licensed data/API | Critic/audience ratings | High for critic/audience split | Licensed/approved access only | Source-specific | High without license | High | Licensed/future only | Avoid scraping |
| Metacritic licensed/approved access | Critic score | High for critic signal | Licensed/approved access only | Source-specific | High without license | High | Licensed/future only | Avoid scraping |
| CinemaScore | Theatrical audience reaction | Medium, movie-only | Approved accessible source only | Low frequency | Medium/high depending access | Medium/high | Licensed/future only | Do not average blindly without mapping |
| Open critic/review datasets | Review text/themes | Potentially useful for experiments | Dataset-specific terms | Dataset-specific | Medium/high; terms vary widely | Medium/high | Prototype only after review | Need strict no-raw-text product policy |
| Internal derived signals | Computed local tags | High immediate value | Existing local DB fields | Regenerate after source refresh | Low | Low/medium | Use now | Safest next layer |

Recommendation labels:

- `Use now`: safe with current architecture/policy
- `Evaluate next`: likely useful and feasible, needs preview
- `Prototype only`: useful for local experiments but not product-ready
- `Licensed/future only`: do not implement until access is approved
- `Avoid scraping`: never scrape as a workaround

## 5. Recommended Near-Term Sources

Safest near-term additions:

1. TMDb keywords/tags ingestion.
2. Structured Source Signals v1 from local metadata plus keywords.
3. Optional TMDb reviews feasibility check, but no review text display yet.
4. Keep Letterboxd as dataset snapshot rating only.
5. Keep Rotten Tomatoes and Metacritic as future licensed-source candidates.

TMDb keywords should likely come before review text because:

- they are structured
- they fit the current TMDb fetch/preview/import pattern
- they can help with tone/mood/pacing prototypes
- they avoid raw review text risks
- they can be reviewed in preview files before DB writes
- they can support deterministic source signals without LLMs

Example keyword-driven signal possibilities:

- "serial killer", "murder", "detective" -> crime/thriller expectation
- "post-apocalyptic", "survival" -> bleak/intense expectation
- "time travel", "space" -> sci-fi identity
- "coming of age" -> audience expectation tag

These mappings must stay conservative and source-aware.

## 6. Review Text Policy

Rules:

- do not scrape reviews
- do not display raw review text without approved rights
- do not expose usernames from datasets in product UI
- do not summarize review text with an LLM until source/legal policy is clear
- do not quote reviews except under a defined citation/permission policy
- store derived signals first, not raw reviews

Review text should be treated as a later phase. Even if a dataset includes reviews, InsightStream should not automatically import, display, or summarize them.

Preferred early approach:

1. Evaluate whether review data can legally be used.
2. If allowed, derive compact non-quoting signals.
3. Store signals/themes, not raw review text.
4. Keep UI spoiler-safe and source-aware.

## 7. LLM Usage Policy

Future LLM rules:

- LLMs should not browse randomly for conclusions.
- LLM summaries should use stored approved facts/signals only.
- LLM output should include source provenance internally.
- LLM output must avoid unsupported claims.
- No critic/audience consensus should appear unless data supports it.
- Generated summaries may need DB storage/versioning later.

LLMs should not become a substitute for source evaluation. They can help phrase approved facts, but they should not invent tone, mood, consensus, review themes, or recommendations.

## 8. Freshness Strategy

Recommended refresh cadence:

- TMDb metadata/keywords: periodic refresh, plus targeted refresh for active titles.
- IMDb dataset: weekly or manual refresh for prototype use.
- Letterboxd dataset snapshot: manual snapshot refresh only.
- Licensed sources: source-specific refresh rules.
- Generated signals: regenerate after source refresh.

Freshness should be visible internally in run reports and health checks where practical.

Signal freshness rule:

If source data changes, regenerate derived signals and update Insight Summary from the latest local data. Do not store stale generated summaries unless there is a versioning/review reason.

## 9. Matching Strategy

Matching rules:

- prefer external IDs where available
- avoid title-only matching for imports
- match by provider IDs whenever possible
- use `external_ids` as the trusted matching backbone
- for Letterboxd-like datasets, use title + year + director and require preview/manual review
- track ambiguous and unmatched cases
- never import ambiguous matches without explicit approval

Recommended confidence tiers:

- high confidence: external ID match, or title/year/director match with no ambiguity
- review required: title/year match with multiple candidates or missing director
- reject/skip: title-only match, conflicting director/year, or no confidence

This protects the product from importing signals onto the wrong title.

## 10. Recommended Implementation Roadmap

Recommended next tasks:

1. Implement TMDb keywords ingestion preview.
2. Import TMDb keywords into a local metadata table or JSON field after schema decision.
3. Implement structured Source Signals v1 using metadata, ratings, availability, and keywords.
4. Improve Insight Summary using `source_signals`.
5. Research source-safe review ingestion.
6. Later add review-derived signals.
7. Later add LLM-assisted source-grounded summaries.

The first step should be preview-only. It should answer whether TMDb keywords are useful enough before committing to schema changes.

## 11. Risks and Guardrails

Risks:

- data source terms changing
- stale datasets
- bad matching
- copyrighted review text
- overclaiming mood/tone
- LLM hallucination
- too many UI badges
- confusing users with unsupported certainty
- creating signals that feel more precise than the source data supports

Guardrails:

- do not scrape
- prefer structured data first
- keep source provenance
- use previews before imports
- require manual review for ambiguous matches
- omit weak signals rather than overclaim
- do not use review text without policy approval
- keep frontend labels compact and conservative

## 12. Recommended Next Implementation Task

Recommended next implementation task:

```text
Implement TMDb keywords ingestion preview
```

Suggested scope:

- backend/analytics only
- no frontend
- no DB writes initially
- fetch or map TMDb keywords for local catalog
- create preview/report
- evaluate how useful keywords are for source signals
- no review text
- no scraping

This gives InsightStream a safe bridge from metadata/ratings into richer source signals without jumping directly into review ingestion or AI summarization.
