# TMDb Keyword Import and Signal Mapping Plan

## 1. Purpose

TMDb keywords matter because they can help InsightStream move from:

```text
basic metadata + ratings
```

toward:

```text
source-backed watch profile and decision signals
```

The current product already has metadata, ratings, availability, certification, series lifecycle data, people/cast/crew, and deterministic Insight Summary. Keywords add a structured provider-tag layer that can help describe what a title may feel like to watch without jumping directly into review text, scraping, or LLM-generated claims.

TMDb keywords can support:

- topic and theme identity
- genre refinement
- mood hints
- tone hints
- pacing hints
- intensity hints
- audience expectation
- spoiler-safe watch context

TMDb keywords should not be treated as:

- reviews
- critic consensus
- audience consensus
- definitive labels
- proof of quality
- complete content warnings

Keyword presence is weak evidence, not proof. Missing keyword is not proof of absence. Any product-facing signal derived from keywords must stay conservative, explainable, and source-aware.

## 2. Current Keyword Preview Findings

Current status:

- TMDb keyword preview workflow exists.
- Retry/merge workflow exists.
- Final main preview/report files are the source for analysis:
  - `analytics/processed/tmdb_keywords/tmdb_keywords_preview.json`
  - `analytics/processed/tmdb_keywords/run_reports/tmdb_keywords_report.json`
- Coverage is strong across the current catalog after retry merge.
- The preview workflow remains DB-write-free.
- Normalized keyword storage/import is implemented through `backend/migrations/009_add_tmdb_keyword_storage.sql` and `analytics/scripts/ingestion/import_tmdb_keywords_from_preview.py`.
- Keyword-to-signal mapping preview is implemented through `analytics/config/source_signal_keyword_mapping.json` and `analytics/scripts/source_signals/build_keyword_signal_preview.py`.
- Mapping config `2026-07-02-v3.1` expands high-value crime/thriller, fantasy, period, horror, political, sci-fi, comedy, and disaster mappings, while keeping noisy/spoiler-unsafe keywords out of public guidance.
- Curated title overrides live in `analytics/config/source_signal_title_overrides.json` and correct known weak/misleading keyword-only previews without deleting raw keywords.
- Override config `2026-07-02-v3.1` adds v3.2.1 targeted semantic corrections for high-value titles where keyword-only output was too generic or slightly misleading.
- Metadata fallback uses local genre metadata only when keyword-derived signals are weak; fallback signals are marked `metadata_fallback`.
- Override-added signals are marked `curated_override`.
- The preview report now includes source counts, count-plus-detail fields for fallback/override/keyword-only title groups, low-signal rows, one-signal rows, missing watch-feel rows, bad primary identities, semantic QA rows for generic/conflicting watch guidance, override candidates, and high-value unmapped candidates.
- The preview report includes `preview_generator_version` and `semantic_qa_version`, currently `2026-07-02-v3.2.1`.
- Partial/debug source-signal preview runs must pass explicit `--output` and `--report-output` paths so they do not overwrite the full-catalog preview/report.
- Source-signal DB storage is implemented through `backend/migrations/010_add_source_signal_storage.sql` and `analytics/scripts/source_signals/import_source_signals_from_preview.py`.
- The storage importer is dry-run by default, writes only with `--write`, preserves provenance/version fields, blocks semantic-QA issues unless explicitly allowed, and marks stored guidance as `storage_ready = true` / `frontend_ready = false`.
- The content-detail API now exposes a sanitized `decision_layer` built from stored guidance/signals. Raw keywords, mapping versions, source names, and provider payloads are not exposed by default.
- Decision-layer output prioritizes stronger identity/theme/mood chips, filters mechanical platform/viewer labels, and returns product-friendly reasons rather than keyword-analysis phrasing.
- Frontend Watch Profile UI is still future work.

Useful observed keywords include:

- dystopia
- suspenseful
- murder
- dark comedy
- artificial intelligence
- serial killer
- space
- detective
- survival
- investigation
- revenge
- time travel
- space opera
- murder mystery
- coming of age

Noisy or generic keywords exist:

- based on novel or book
- sequel
- aftercreditsstinger
- duringcreditsstinger
- woman director
- remake
- spin off

Good coverage does not mean all keywords are product-displayable. Import should preserve raw keywords with source provenance, while product mapping should be curated and config-driven.

## 3. Core Design Principle

```text
Store broadly, display selectively, infer conservatively.
```

This means:

- Store provider keywords with provenance.
- Do not show all raw provider keywords.
- Use a curated mapping layer to convert selected keywords into product signals.
- Keep confidence low or medium unless supported by multiple data points.
- Prefer omitting weak signals over making unsupported claims.

Storage and display are different responsibilities. The raw provider layer should preserve what TMDb supplied. The product signal layer should decide what is safe, useful, and user-facing.

## 4. Storage Strategy Options

### Option A: JSON Field on `content`

Pros:

- quick
- simple
- minimal schema surface

Cons:

- hard to query
- hard to dedupe
- poor provenance
- harder to build filters/signals
- harder to refresh individual keyword relationships
- harder to compare provider keyword coverage

This option is not recommended for the main keyword layer.

### Option B: Normalized Provider Keyword Tables

Preferred.

Possible tables:

```text
keyword_sources
provider_keywords
content_keywords
```

Example shape:

```sql
keyword_sources
- id
- source_name
- display_name
- is_active
- created_at
- updated_at

provider_keywords
- id
- source_id
- external_keyword_id
- keyword_name
- normalized_keyword_name
- created_at
- updated_at

content_keywords
- id
- content_id
- keyword_id
- source_id
- confidence
- raw_payload
- first_seen_at
- last_seen_at
- fetched_at
- source_preview_generated_at
- import_run_id
- import_report_path
- created_at
- updated_at
```

Recommended details:

- `external_keyword_id` should preserve the TMDb keyword ID on `provider_keywords`.
- `content_keywords.keyword_id` should reference the internal `provider_keywords.id` row.
- `keyword_name` should preserve provider text.
- `normalized_keyword_name` should support matching, mapping, and dedupe.
- `raw_payload` should stay compact, such as TMDb external keyword ID/name and fetch metadata.
- `confidence` for TMDb keyword presence can default to `low` or `medium`.
- `first_seen_at` and `last_seen_at` should track when the app first and most recently saw the content-keyword relationship.
- `fetched_at` should preserve when the keyword data was fetched from TMDb.
- `source_preview_generated_at` should preserve the preview file generation time that produced the import row.
- Optional `import_run_id` or `import_report_path` should connect rows back to the import run/report that created or refreshed them.
- Unique constraints should prevent duplicate keyword rows and duplicate content-keyword relationships.

Suggested uniqueness rules:

- `keyword_sources(source_name)`
- `provider_keywords(source_id, external_keyword_id)`
- `content_keywords(content_id, keyword_id, source_id)`

Recommended indexes:

- `provider_keywords(source_id, external_keyword_id)`
- `provider_keywords(normalized_keyword_name)`
- `content_keywords(content_id)`
- `content_keywords(keyword_id)`
- `content_keywords(source_id)`
- `content_keywords(content_id, source_id)`

These indexes support detail page joins, source signal generation, keyword coverage reports, and future keyword/search/discovery work.

This design keeps the raw provider keyword layer available for future remapping, health checks, search/discovery experiments, and source-signal derivation.

Batch/import-run tracking matters for scale:

- new title batches can be imported without affecting older titles
- keyword freshness can be audited later
- source signal regeneration can know which titles or keyword relationships changed
- partial retry/import workflows can remain traceable

### Option C: Generic Source Signal Table Only

This is not enough by itself.

Why:

- loses the raw provider keyword layer
- makes it harder to remap later
- hides which TMDb keyword produced which signal
- makes keyword coverage and provider debugging harder

`source_signals` should be derived from stored keywords, not replace keywords.

### Recommendation

Use normalized keyword tables first. Later derive `source_signals` from stored keywords plus metadata, ratings, availability, certification, and series lifecycle data.

## 5. Import Behavior

Implemented script:

```text
analytics/scripts/ingestion/import_tmdb_keywords_from_preview.py
```

Input:

```text
analytics/processed/tmdb_keywords/tmdb_keywords_preview.json
```

Current expected behavior:

- dry-run by default
- `--apply` required for database writes
- idempotent after apply
- keep provider keyword import separate from source-signal generation
- upsert keyword source `tmdb`
- upsert provider keywords by TMDb `external_keyword_id`
- upsert content-keyword relationships by `content_id` + internal `keyword_id` + source
- preserve existing keywords
- remove stale relationships only if explicitly supported later
- report inserted, updated, and unchanged counts
- do not create `source_signals` yet
- do not update frontend
- do not fetch live TMDb
- do not import failed preview rows

Suggested CLI options:

- `--preview-file`
- `--apply`
- `--limit`
- `--content-type`
- `--content-id`
- `--only-content-ids-file`

Batch-safe options such as `--content-id` and `--only-content-ids-file` are useful when importing a new 100-title batch, retrying a subset, or regenerating keywords for selected titles. They must be scoped carefully: a partial preview/import must not delete or stale-mark keywords outside the selected preview scope.

Avoid in v1:

- `--delete-missing`

Deleting missing relationships needs a careful freshness and target-scope design. A subset preview should not accidentally delete keywords from titles outside that subset.

Output report includes:

- source inserted/updated
- provider keywords inserted/updated/unchanged
- content keyword relationships inserted/updated/unchanged
- skipped rows
- failed preview rows
- duplicate keywords deduped
- `db_write_performed`
- preview `generated_at`
- import `generated_at`

The report should also include `source_preview_generated_at`, optional `import_run_id`, and optional `import_report_path` so later health checks and source-signal regeneration can audit which preview/import run produced the current keyword state.

### Batch Scalability

Adding a new 100-title target batch should work if those titles have TMDb IDs.

Recommended flow:

1. Run keyword preview for the batch.
2. Retry and merge failed rows.
3. Import from the merged preview.
4. Upsert provider keywords and content-keyword relationships.
5. Leave existing titles untouched unless they are in the selected preview/import scope.

No `--delete-missing` behavior in v1 prevents accidental deletion when importing partial batches or retry subsets.

## 6. Keyword Refresh Strategy

Keyword refresh is about updating the raw provider keyword layer from new TMDb keyword previews. It is separate from internal keyword-to-signal mapping changes.

### When a Keyword Is Present in a New Preview

If the content-keyword relationship already exists:

- update `last_seen_at`
- update `fetched_at`
- update `source_preview_generated_at`
- update `import_report_path` if present
- keep `first_seen_at` unchanged

If the relationship does not exist:

- insert it
- set `first_seen_at`
- set `last_seen_at`
- set `fetched_at`
- set `source_preview_generated_at`
- set `import_report_path` if present

This allows new title batches, partial refreshes, and retry imports to update keyword freshness without rewriting older rows unnecessarily.

### When an Old Keyword Is Missing From a Later Preview

For v1:

- do not delete it
- do not remove the relationship automatically
- do not mark it stale unless stale tracking is explicitly implemented
- do not add `--delete-missing`

Reason:

- partial previews and batch imports should not accidentally remove valid older data
- TMDb keywords may change or be incomplete
- deletion requires target-scope awareness
- retry-only previews should not be interpreted as full truth for a title unless explicitly marked that way

Future optional behavior:

- add `is_active`
- add `removed_seen_at`
- add `last_confirmed_missing_at`
- add `stale_reason`
- support a carefully scoped `--mark-missing-stale` flag
- never stale-mark titles outside the selected preview/import scope

Do not mix provider keyword import with source-signal generation in one irreversible step.

Reason:

- provider data should remain raw and auditable
- product mappings will evolve
- source signals should be regeneratable

## 7. Filtering Strategy

Filtering should separate storage from display.

### Store All Usable Provider Keywords

Store a provider keyword if:

- the preview row has valid `content_id`
- the preview row succeeded
- the keyword has a usable ID and name
- the content match is valid

Storage is not the same as display.

### Exclude From Display/Mapping By Default

Examples:

- `aftercreditsstinger`
- `duringcreditsstinger`
- overly technical provider artifacts
- extremely generic production terms
- potentially spoiler-heavy keywords
- low-value franchise/metadata tags unless useful

### Keep But Treat As Metadata/Context

Examples:

- `based on novel or book`
- `sequel`
- `remake`
- `spin off`
- `based on true story`

These may be useful context, filters, or internal metadata, but they should not become strong mood/tone/watch-fit claims by themselves.

### Use For Product Signals

Examples:

- `dystopia`
- `suspenseful`
- `dark comedy`
- `serial killer`
- `space`
- `detective`
- `survival`
- `investigation`
- `revenge`
- `time travel`
- `coming of age`

Only mapped, spoiler-safe, product-useful keywords should become public-facing signals.

## 8. Keyword-to-Signal Mapping Design

Recommend a config-driven mapping file:

```text
analytics/config/source_signal_keyword_mapping.json
```

Reason:

- keyword import and early source-signal derivation are analytics/offline concerns
- existing ingestion target/config files already live under `analytics/config/`
- the mapping can later be promoted or mirrored into `backend/app/config/` if runtime API generation needs direct backend access

Example mapping shape:

```json
{
  "mapping_version": "2026-06-30-v1",
  "tmdb_keywords": {
    "dystopia": {
      "dimensions": ["mood", "audience_expectation"],
      "signals": ["bleak", "dystopian future"],
      "confidence": "medium",
      "spoiler_safe": true
    },
    "slow burn": {
      "dimensions": ["pacing"],
      "signals": ["slow-burn"],
      "confidence": "medium",
      "spoiler_safe": true
    },
    "serial killer": {
      "dimensions": ["audience_expectation", "intensity"],
      "signals": ["serial-killer story", "high intensity"],
      "confidence": "medium",
      "spoiler_safe": true
    }
  },
  "excluded_keywords": [
    "aftercreditsstinger",
    "duringcreditsstinger"
  ]
}
```

Mapping rules:

- mapping should be manually curated
- mapping should be versioned
- mapping should be easy to test
- not every keyword needs mapping
- unmapped keywords remain stored but not displayed as signals
- mapping should preserve source provenance for explainability
- source signals generated later should store or report the mapping version
- mapping changes should allow deterministic signal regeneration

### Mapping Versioning Lifecycle

The mapping config should include a top-level `mapping_version`:

```json
{
  "mapping_version": "2026-07-01-v1"
}
```

Every generated source-signal batch should store or report the mapping version used to create it. When mapping logic changes, increment the version.

Versioning matters because:

- old source signals can be regenerated from stored raw keywords
- product copy and signal behavior can be corrected without refetching TMDb
- mapping changes can be reviewed, tested, and rolled forward deterministically
- future reports can explain which mapping rules produced a given signal

## 9. Mapping Update Strategy

Keyword-to-signal mapping is separate from raw keyword import.

When product logic improves later:

- edit the mapping config, such as `analytics/config/source_signal_keyword_mapping.json`
- do not refetch TMDb keywords just to apply new mapping rules
- run a future source-signal regeneration step
- record the mapping version on generated signals or reports
- keep mapping changes deterministic and testable

Example:

```text
Before:
"political intrigue" is stored as a raw keyword but unmapped.

Later:
Add mapping:
political intrigue -> audience_expectation: political drama, tone: tense

Then:
Run source signal regeneration.
Existing stored keywords produce new source_signals.
No TMDb refetch required.
```

### Planned Future Source Signal Regeneration Workflow

This workflow is planned, not currently implemented:

1. Import raw TMDb keywords.
2. Build or update mapping config.
3. Run source signal generation.
4. Review generated signals.
5. Adjust mapping if needed.
6. Regenerate signals without refetching TMDb.

This is why raw keyword storage should remain independent from mapped product signals.

## 10. Signal Dimensions

### Topic/Theme

Examples:

- space
- crime
- investigation
- revenge
- political drama
- survival
- coming of age

### Tone

Examples:

- dark
- humorous
- serious
- tense
- satirical

### Mood

Examples:

- suspenseful
- bleak
- feel-good
- contemplative
- emotional

### Pacing

Examples:

- slow-burn
- fast-paced
- action-heavy
- dialogue-heavy

### Intensity

Examples:

- low
- medium
- high

### Audience Expectation

Examples:

- murder mystery
- serial-killer story
- time-travel story
- dystopian future
- space opera
- family comedy

### Content Caution Proxy

Keywords and certification may provide weak caution hints, but they are not a replacement for a proper source such as Parents Guide or licensed advisory data.

Rules:

- avoid strong warnings unless a proper content advisory source exists
- do not infer detailed content warnings from genres alone
- treat keyword-derived caution as low/medium confidence
- keep caution language neutral and non-alarmist

## 11. Confidence Rules

Confidence should stay conservative.

Examples:

- Keyword only: low or medium confidence.
- Keyword + genre support: medium confidence.
- Keyword + genre + certification/runtime support: medium or high confidence depending on signal.
- Rating score should not increase tone/mood confidence.
- Availability should not affect tone/mood confidence.
- Multiple related keywords can increase confidence.
- Contradictory keywords should reduce confidence or hide the signal.

Examples:

```text
serial killer + murder + crime genre => audience expectation: serial-killer crime story, medium/high confidence
space + spacecraft + sci-fi genre => topic: space sci-fi, medium/high confidence
suspenseful only => mood: suspenseful, low/medium confidence
```

Confidence should describe evidence strength, not quality. A high-confidence signal does not mean the title is good; it means the system has stronger evidence for that signal.

## 12. Spoiler Safety Rules

Rules:

- avoid exposing story-ending keywords
- avoid twist/reveal keywords
- avoid character-death-specific terms
- avoid late-plot event terms
- prefer high-level expectation tags
- keep raw keywords backend/internal
- display only approved mapped signals

Examples:

- safe: `space opera`, `coming of age`, `murder mystery`
- risky: very specific plot event keywords, death/reveal/twist-specific tags

When unsure, hide the signal from public UI and keep the raw keyword in the provider keyword layer only.

## 13. Backend/API Direction

Future content detail API should eventually expose a `source_signals` object, not a raw keyword dump.

Example:

```json
{
  "source_signals": {
    "watch_profile": {
      "tone": [
        {
          "value": "tense",
          "confidence": "medium",
          "sources": ["tmdb_keywords"]
        }
      ],
      "pacing": [
        {
          "value": "slow-burn",
          "confidence": "medium",
          "sources": ["tmdb_keywords"]
        }
      ],
      "intensity": {
        "value": "high",
        "confidence": "medium",
        "sources": ["tmdb_keywords", "certification"]
      }
    },
    "decision_signals": {
      "audience_expectation": [
        {
          "value": "space opera",
          "confidence": "medium",
          "sources": ["tmdb_keywords", "genres"]
        }
      ]
    },
    "generated_from": ["metadata", "ratings", "availability", "certification", "tmdb_keywords"]
  }
}
```

Guidance:

- raw keywords can be available internally or in admin/debug tooling later
- public UI should show selected mapped signals, not raw provider tags
- raw provider payloads should not be exposed publicly
- source provenance should be kept
- API response should remain stable when no signals exist
- source signals should not claim review or critic consensus

## 14. Frontend Direction

Future UI should not display a giant keyword list.

Preferred display:

```text
Watch Profile
Tone: Tense
Pacing: Slow-burn
Intensity: High
Expectation: Space opera
```

or compact chips:

```text
Tense
Slow-burn
Space opera
High intensity
```

Rules:

- keep compact
- avoid too many chips
- avoid weird provider keywords
- show only mapped/spoiler-safe signals
- no raw review-like claims
- no critic/audience consensus language
- no quality claims from keywords

## 15. Insight Summary Integration

Keywords can improve Insight Summary by making the quick take more specific and useful.

Possible improvements:

- `A slow-burn dystopian sci-fi story with strong audience backing.`
- `A tense crime investigation with high audience confidence.`

Better `best_for` chips:

- `Space sci-fi`
- `Murder mystery`
- `Slow-burn viewers`
- `Dark comedy`

Better consider-first notes:

- `Better for viewers comfortable with darker, intense stories.`

Only use notes like this when supported by mapped signals and confidence rules.

Warnings:

- do not use hype
- do not invent review consensus
- do not overfit one keyword
- do not turn one noisy tag into a strong product claim
- keep generation deterministic and explainable

## 16. Admin and Manual Correction Strategy

A future admin/manual override layer may be needed for:

- fixing bad mappings
- hiding a misleading signal
- promoting a useful signal
- marking a keyword as spoiler unsafe
- manually blocking a noisy keyword

V1 should avoid manual per-title overrides unless necessary. A curated mapping config is easier to test, review, and regenerate than scattered one-off overrides.

Recommended future fields if manual review becomes necessary:

- `is_blocked`
- `blocked_reason`
- `manual_signal_override`
- `reviewed_by`
- `reviewed_at`

Manual overrides should not replace the raw provider keyword layer. They should sit above it as product curation metadata.

## 17. Testing Strategy

Implementation should test:

- keyword import idempotency
- duplicate prevention
- keyword normalization
- missing/failed preview rows skipped
- provider keyword upsert
- content-keyword relationship upsert
- mapping excludes noisy keywords
- mapping produces expected source signals
- unmapped keywords do not display
- spoiler-unsafe keywords do not display
- confidence calculation is conservative
- API does not return raw provider payloads publicly unless intentional

Tests should use small fixtures and should not require live TMDb calls.

Expected keyword health checks:

- total local content with TMDb IDs
- content with imported TMDb keywords
- movie keyword coverage
- series keyword coverage
- provider keyword row count
- content-keyword relationship count
- titles with zero keywords
- failed preview rows
- latest keyword import timestamp

## 18. Recommended Implementation Roadmap

Recommended order:

1. Create this plan. Done.
2. Create DB schema/migration for normalized keyword storage. Done.
3. Implement `import_tmdb_keywords_from_preview.py`. Done.
4. Import keywords from final preview. Manual apply step.
5. Add keyword ingestion health checks. Done.
6. Build keyword filtering/mapping config and preview script. Done.
7. Review v3 preview quality and continue refining mapping, fallback rules, and title overrides. Done for v3.2.1.
8. Implement Source Signals v1 storage/importer. Done.
9. Product-copy polish pass before public display.
10. Expose a sanitized source-signal decision layer in content detail API. Done.
11. Polish backend decision-layer copy before frontend display. Done.
12. Add compact Watch Profile UI.
13. Improve frontend Insight Summary presentation using source-signal guidance.
14. Later evaluate MovieLens/MPST for taxonomy/modeling.
15. Later evaluate review-derived signals.

## 19. Recommended Next Coding Task

```text
Plan Watch Profile frontend display
```

Suggested scope:

- keep raw keywords internal/admin only
- design compact Watch Profile UI
- keep `frontend_ready = false` until copy/design review is complete
