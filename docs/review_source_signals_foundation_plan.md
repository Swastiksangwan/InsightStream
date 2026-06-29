# Review & Source Signals Foundation Plan

## 1. Purpose

Review & Source Signals Foundation defines how InsightStream can move beyond basic metadata and ratings into richer, source-aware decision-support signals.

This layer should help users understand what a title may feel like to watch, not only what it is or how it scores. It should support signals such as:

- tone
- mood
- pacing
- intensity
- content expectations
- review consensus
- critic vs audience distinction
- source-backed strengths and weaknesses
- better Insight Summary v2 inputs

This layer is not:

- user reviews on InsightStream
- social posting
- generic AI summaries
- scraping review websites
- copying review text
- ungrounded recommendations

The goal is to create a safe path toward richer decision support while keeping every product claim grounded in stored, approved source data.

## 2. Current Foundation

InsightStream already has a strong local metadata and ratings foundation:

- content metadata
- posters and backdrops
- genres
- cast and crew
- people and biographies
- availability
- certification and age rating
- series lifecycle metadata
- season summary metadata
- TMDb ratings
- IMDb ratings from the official non-commercial dataset
- Letterboxd ratings from a local dataset preview/import
- InsightStream Score based on vote-backed scoring sources
- Letterboxd displayed as a film-community snapshot, not part of InsightStream Score v1
- deterministic Insight Summary
- local database-driven content detail pages

Current limitation:

- metadata explains "what it is"
- ratings explain "how it scores"
- availability explains "where/how to watch"
- series lifecycle explains "whether it is ongoing or complete"
- but these signals do not fully explain "what it feels like to watch"

For example, two titles may both be high-rated dramas, but one may be slow-burn, bleak, and intense, while another may be warm, fast-moving, and easy to binge. Ratings and genres alone do not always expose that difference.

## 3. Source Categories

InsightStream should separate source categories clearly so that the product does not treat every signal as equally reliable or equally expressive.

### Structured Metadata Sources

Structured metadata sources are safer and already part of the local system. They can support deterministic signals without review text.

Examples:

- TMDb keywords if added later
- genres
- runtime
- certification
- series lifecycle
- season summary
- cast and crew
- availability
- content type
- release year

### Rating Sources

Rating sources provide audience or film-community score signals. They are easier to store and normalize than full review text, but still need confidence handling.

Current examples:

- TMDb
- IMDb
- Letterboxd dataset snapshot

Current product policy:

- TMDb and IMDb can contribute to InsightStream Score when vote-backed and active.
- Letterboxd can display as an additional film-community snapshot.
- Letterboxd should not affect InsightStream Score v1 because it has no reliable vote count in the current dataset workflow.

### Review Sources

Review sources may become useful later, but they require stronger legal, source, storage, and product policies.

Potential future sources:

- TMDb user reviews if API terms allow the intended use
- IMDb review data only if approved and source-legal
- Letterboxd reviews only if dataset, legal, and product policy allow
- Rotten Tomatoes or Metacritic only through approved or licensed access

Review sources should not be used casually. Review text is expressive user-generated or editorial content and needs careful handling.

### Internal Derived Signals

Internal derived signals are deterministic labels created from existing structured data.

Examples:

- `long_watch`
- `completed_series`
- `active_release`
- `high_rating`
- `streaming_available`
- `rent_buy_only`
- `limited_rating_confidence`

These can be useful before any review-text ingestion exists.

## 4. Legal and Product Guardrails

Strict rules:

- do not scrape review websites
- do not copy full review text into product UI without approved rights
- do not summarize copyrighted review text without a source/legal plan
- do not claim "critically acclaimed" unless critic data supports it
- do not claim "audiences love it" unless audience data supports it
- do not use review text in LLM summaries until storage, source, and legal policy is clear
- do not expose usernames or review text from datasets in product UI yet

Ratings are generally safer than review text because ratings are structured numeric or categorical signals. Review text is different: it is expressive content, often user-generated or editorial, and may carry copyright, attribution, privacy, and terms-of-service constraints.

Any future LLM-assisted summary must be grounded in stored, approved source facts or derived signals. It should not invent consensus, quality claims, critic claims, or audience sentiment.

## 5. Signal Types to Build

This section defines target signal types for future decision support.

### Tone

Examples:

- dark
- light
- emotional
- tense
- humorous
- serious

Tone should describe the viewing character of the title. In v1, tone should only be inferred when structured metadata makes it reasonably safe, or when approved source signals exist later.

### Mood

Examples:

- feel-good
- bleak
- suspenseful
- intense
- contemplative

Mood should be treated carefully because it is more interpretive than genre.

### Pacing

Examples:

- slow-burn
- fast-paced
- action-heavy
- dialogue-heavy

Pacing is especially valuable for watch decisions, but it is hard to infer safely without review or keyword support. V1 should derive it only from conservative structured rules.

### Intensity

Examples:

- low
- medium
- high

Intensity can come from genre, certification, runtime, and later review-derived signals.

### Watch Commitment

Examples:

- long movie
- completed binge
- ongoing release
- weekly-follow friendly
- short casual watch

This is the safest and most immediately useful category because InsightStream already stores runtime, series lifecycle, season summary, and availability.

### Audience Confidence

Examples:

- strong vote-backed audience signal
- mixed audience signal
- limited rating confidence

This can be derived from InsightStream Score, scoring source count, and vote-count thresholds.

### Access Friction

Examples:

- streaming
- rent/buy only
- no stored availability

This can be derived from the existing region-aware availability data.

### Critic/Audience Split

Future only.

This should wait until source-approved critic data exists. It should not be inferred from audience sources alone.

## 6. Source-Safe V1 Plan

Source Signals v1 should not require review text. It should derive from structured local data already stored in InsightStream.

Inputs:

- genre combinations
- runtime
- certification
- ratings
- scoring source count
- vote counts
- availability
- content type
- series status
- released seasons
- upcoming season/episode data
- cast/crew presence

Example derived signals:

- `long_watch`
- `completed_binge`
- `active_series`
- `weekly_follow`
- `high_audience_score`
- `limited_rating_confidence`
- `rent_buy_only`
- `streaming_available`
- `adult_certification`
- `family_certification`
- `genre_identity`

These signals can improve Insight Summary without touching reviews.

Example v1 derivations:

- runtime over 150 minutes -> `long_watch`
- series status `ended` with released seasons -> `completed_binge`
- series status `ongoing` with next episode date -> `weekly_follow`
- unified score 80+ with scoring sources -> `high_audience_score`
- no unified score but source ratings exist -> `limited_rating_confidence`
- streaming availability in India -> `streaming_available`
- rent/buy availability only -> `rent_buy_only`

V1 should stay conservative. If a signal cannot be justified from stored fields, omit it.

## 7. Review-Based Future Plan

Review-based signals should come later, only after source/legal policy is clear.

### Review Signals v2

If approved/source-safe review data becomes available, derive structured signals rather than displaying raw review blocks.

Possible outputs:

- common positive themes
- common negative themes
- tone and mood terms
- pacing complaints or praise
- spoiler-safe expectation tags
- critic/audience disagreement flags

Example derived signals:

- "praised for performances"
- "common pacing concern"
- "strong atmosphere signal"
- "split audience response"

These should be stored as compact signals, not full copied review text.

### LLM-Assisted Summary v3

Only after approved source data exists:

- use stored facts and approved review snippets/signals
- summarize into short source-grounded insights
- avoid long direct quotes
- do not invent claims
- keep prompts controlled and deterministic where possible
- store generated output only if needed for review, versioning, or performance

LLM output should be treated as a presentation layer over approved source facts, not as a new source of truth.

## 8. Proposed Data Model Options

Planning only. Do not implement these tables yet.

### `content_source_signals`

Possible fields:

- `id`
- `content_id`
- `signal_type`
- `signal_value`
- `confidence`
- `source_name`
- `source_category`
- `generated_from`
- `created_at`
- `updated_at`

Use case:

- store deterministic structured signals such as `long_watch`, `completed_binge`, or `streaming_available`
- support filtering or display without recomputing everything
- make signal provenance explicit

### `content_review_signals`

Possible fields:

- `id`
- `content_id`
- `source_name`
- `positive_themes`
- `negative_themes`
- `tone_tags`
- `pacing_tags`
- `intensity_tags`
- `source_payload_summary`
- `generated_at`

Use case:

- store review-derived themes without storing raw review text
- separate review-derived data from metadata-derived data
- enable review consensus without exposing user review content

### `content_review_sources`

Possible fields:

- `id`
- `source_name`
- `display_name`
- `access_type`
- `is_active`
- `terms_notes`

Use case:

- document where review-derived signals are allowed to come from
- keep source activation explicit
- store source/legal notes

Important:

- do not store raw review text in v1
- store derived signals first
- raw review storage requires a separate legal/product decision

## 9. Backend API Direction

Future content detail response could include a `source_signals` object:

```json
{
  "source_signals": {
    "tone": ["tense", "serious"],
    "pacing": ["slow-burn"],
    "intensity": "high",
    "watch_commitment": ["long movie"],
    "audience_confidence": "strong",
    "access_friction": "streaming available",
    "generated_from": ["metadata", "ratings", "availability"]
  }
}
```

Recommended approach for the next implementation:

- compute Source Signals v1 dynamically from the same local detail data used by Insight Summary
- return a stable empty shape when sparse
- keep provenance in `generated_from`
- do not add a database table until stored signals are needed

Insight Summary v2 can consume `source_signals` instead of duplicating every rule internally.

## 10. Frontend Direction

The frontend should display signals without creating clutter.

Possible UI:

- a compact "Watch Profile" card
- tone/pacing chips
- decision signals inside Insight Summary
- short, source-aware labels
- no raw review text in early versions

Example:

```text
Watch profile
Tone: Tense · Serious
Pacing: Slow-burn
Commitment: Long movie
Access: Streaming
Audience signal: Strong
```

Guidelines:

- keep the card compact
- show only signals that exist
- avoid empty placeholders
- avoid review-like claims without review data
- avoid making the detail page feel like a dashboard of badges
- keep richer review consensus for later phases

## 11. Testing Strategy

Recommended tests:

- structured signals derive correctly from metadata
- no fake tone if no source supports it
- no review claims without review data
- no unsupported phrases appear
- no raw review text is returned
- Insight Summary consumes only available signals
- sparse content returns minimal signals
- Letterboxd remains a displayed source signal but not a scoring source
- critic/audience split is absent when critic sources are absent

Avoid brittle full-text tests. Prefer asserting:

- field presence
- expected signal keys
- expected omissions
- source provenance
- absence of unsupported claims

## 12. Risks

Risks:

- review data legality
- overclaiming audience or critic consensus
- LLM hallucination
- storing copyrighted review text
- exposing usernames or personal review content
- noisy datasets
- matching errors between platforms
- stale external datasets
- confusing users with too many chips
- implying certainty when signals are weak

Mitigations:

- use structured metadata first
- keep source provenance visible internally
- avoid unsupported critic/review language
- do not expose raw review text in early versions
- require explicit approval before using review datasets
- keep LLM work out until approved facts/signals exist

## 13. Recommended Implementation Roadmap

Recommended phased order:

1. Build Source Signals v1 from structured metadata only.
2. Add `source_signals` field to content detail API.
3. Update Insight Summary to use `source_signals`.
4. Optionally add a compact Watch Profile UI.
5. Later evaluate approved review datasets or APIs.
6. Later add review-derived signals, not raw reviews.
7. Later add LLM-assisted summaries only from approved stored facts/signals.
8. Later consider critic/audience comparison if legal critic sources exist.

This roadmap keeps the next step useful while avoiding legal and product risk.

## 14. Recommended Next Implementation Task

Recommended next coding task:

```text
Implement structured source signals v1
```

Suggested scope:

- no new external data
- no reviews
- no AI
- derive signal tags from existing metadata, ratings, availability, certification, and series lifecycle fields
- expose `source_signals` in the content detail API
- use `source_signals` to improve Insight Summary
- optionally add a small Watch Profile UI

This is the safest next step because it improves decision support using local data that InsightStream already owns or has already normalized.
