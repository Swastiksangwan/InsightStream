# Decision Insight Formatter v2

This document is the canonical operational reference for the sentence shown under
**Why this stands out** on an InsightStream title-detail page. It describes the
implementation on Formatter version `2.0.2`; it does not describe planned behavior.

## 1. Purpose And Product Contract

`decision_layer.display.primary_insight` is a short, deterministic description of
the title's content identity and differentiating viewing experience. It is the prose
rendered below **Why this stands out**. It is not a synopsis, recommendation score,
review, or marketing claim.

The surrounding fields have separate jobs:

| Field | Product role |
| --- | --- |
| Identity | Structured labels for the kind of story or viewing proposition. |
| Themes | Structured subjects the title explores. |
| Feel | Mood and tone descriptors. |
| Pace | Structured viewing-rhythm description. |
| Best for | Audience-fit labels, not a quality claim. |
| Supporting facts | Rating, availability, credits, age, runtime, and series facts. |
| Insight Summary | A separate compatibility summary assembled from the same safe decision layer and metadata. |

Generation is deterministic so the same structured input and formatter version
produce the same plan and sentence. No LLM runs in the details request. Ordinary
copy is derived globally rather than authored per title. The formatter must not
invent plot events, diagnoses, mood, pace, intensity, acclaim, audience response,
or an identity unsupported by active signals and governed metadata/context rules.

## 2. Authoritative Source-Of-Truth Contract

**Structured source signals and metadata are stored. The final primary-insight
sentence is derived at runtime by Formatter v2.**

PostgreSQL stores active normalized signals in `content_source_signals` and
structured/legacy guidance in `content_watch_guidance`. The latter still contains
the preview-era `watch_feel`, chips, `best_for`, and `consider_first`. Stored
`watch_feel` is historical input compatibility data; it is not authoritative prose.

On every details request, `_build_decision_display_and_plan()` copies the structured
watch profile and sets its `watch_feel` to `None` before planning. The formatter
derives `decision_layer.display.primary_insight`, then
`get_content_decision_layer()` assigns that same result to compatibility
`decision_layer.watch_profile.watch_feel`. The runtime value is therefore the one
authoritative sentence exposed by the details API.

The plan-driven decision-support headline and Insight Summary consume the same safe
runtime decision layer. Formatter-only code changes take effect on the next request
and do not require a guidance-table rewrite. A source-signal import changes the
structured inputs and may therefore change the next runtime sentence.

## 3. Complete End-To-End Data Flow

```text
TMDb keyword response
  -> provider keyword preview/import
  -> provider_keywords + content_keywords
  -> keyword mapping + title-override preview
  -> source-signal preview
  -> source-signal dry-run/apply
  -> content_source_signals + content_watch_guidance
  -> GET /content/{id}/details
  -> active-signal and guidance loading
  -> spoiler-safe runtime rows
  -> display profile + identity candidates
  -> InsightPlan -> validation -> rendering
  -> decision_layer + Insight Summary
  -> DecisionDisplayCard
  -> audits, comparisons, conflicts, and explanations
```

1. `build_tmdb_keywords_preview.py` reads TMDb only when explicitly run and writes a
   generated raw-keyword preview; it does not participate in API runtime.
2. `import_tmdb_keywords_from_preview.py` mutates `provider_keywords` and
   `content_keywords` only in its explicit write mode.
3. `source_signal_keyword_normalization.py` applies the
   `source-signal-keyword-v1` canonical keyword normalization contract.
4. `build_keyword_signal_preview.py` reads local catalog/keyword data, mapping
   version `2026-07-29-v2.9`, and override version `2026-07-29-v3.7`. It emits
   mapped signals, provenance, safety flags, structured guidance, and QA metadata.
   It does not write catalog tables.
5. `import_source_signals_from_preview.py` validates the preview and, only with
   `--write`, upserts `content_source_signals` and `content_watch_guidance`. Signal
   `source_payload` stores `spoiler_safe`, mapping/override/generator versions, and
   fallback/override provenance.
6. `content_service.get_content_details_service()` loads content, genres,
   availability, ratings, videos, credits, and series metadata, then calls
   `source_signal_service.get_content_decision_layer()`.
7. The source-signal service loads one title's guidance and active signals. It
   converts stored rows to internal runtime signals that retain `spoiler_safe` and
   to public rows that omit internal provenance.
8. `_build_decision_display_and_plan()` builds a structured display profile and
   passes already-loaded data to the pure formatter. The formatter itself performs
   no query and no write.
9. `build_insight_plan()` filters unsafe rows, constructs and ranks candidates,
   rejects incompatible or overlapping concepts, and records evidence.
10. `validate_insight_plan()` validates the selected structure.
11. `render_insight_plan()` creates the sentence; `render_decision_headline()`
    creates the concise watch-identity headline.
12. The service removes concept families belonging to rejected source identities
    from all public profile and compatibility fields. Debug mode retains the plan
    and conflicts.
13. `build_insight_summary()` consumes the same safe decision layer plus metadata.
14. FastAPI validates the response through `ContentDetailsResponse`; the Next.js
    page passes `decision_layer.display` to `DecisionDisplayCard`.
15. Audit/report CLIs call the production details service in read-only
    transactions, so diagnostics evaluate the same runtime result.

The keyword and source-signal import stages mutate only when their documented write
flags are used. The API, formatter, audits, comparison, stratified review, and
explanation stages are read-only.

## 4. Related-File Inventory

### Production, API, And Frontend

| Path | Responsibility and important symbols | DB / reports / public output |
| --- | --- | --- |
| `backend/app/services/decision_insight_formatter.py` | Pure rule engine: `InsightComponent`, `IdentityCandidate`, `InsightPlan`, `build_insight_plan`, `validate_insight_plan`, `render_insight_plan`, `render_decision_headline`, registries and safety helpers. | No DB, no report; directly controls public copy. |
| `backend/app/services/source_signal_service.py` | Queries stored guidance/signals, builds profiles, invokes the formatter, filters rejected concepts, creates decision support and compatibility fields. | Reads DB; controls `decision_layer`. |
| `backend/app/services/content_service.py` | `get_content_details_service`; assembles all detail context and Insight Summary. | Reads DB; owns details response assembly. |
| `backend/app/services/insight_summary_service.py` | `build_insight_summary`; consumes the safe decision layer and metadata. | No DB itself; controls `insight_summary`. |
| `backend/app/api/routes/content.py` | `/content/{id}/details` route. | Public API boundary. |
| `backend/app/schemas/content.py` | `WatchProfileSchema`, `DecisionSupportSchema`, `DecisionDisplaySchema`, `ContentDecisionLayerSchema`, `InsightSummary`, `ContentDetailsResponse`. | Public response contract. |
| `frontend/lib/api.ts` | Fetches the existing content-details response. | One API request; no signal generation. |
| `frontend/types/content.ts` | TypeScript `DecisionDisplay`, `DecisionLayer`, and `InsightSummary` shapes. | Frontend contract. |
| `frontend/lib/publicDisplay.ts` | Final generic public-text sanitization. | No semantic generation. |
| `frontend/components/DecisionDisplayCard.tsx` | Renders `primary_insight`, profile chips, pace, best-for, cautions, and facts. | Displays **Why this stands out**. |
| `frontend/app/content/[id]/page.tsx` | Server detail page; passes `details.decision_layer?.display` to the card. | Consumer only. |

### Ingestion, Mapping, And Storage

| Path | Responsibility | DB behavior |
| --- | --- | --- |
| `analytics/scripts/ingestion/build_tmdb_keywords_preview.py` | Builds provider-keyword previews. | Provider access only when explicitly run; generated output. |
| `analytics/scripts/ingestion/import_tmdb_keywords_from_preview.py` | Imports normalized provider keyword identities and title relationships. | Explicit mutation workflow. |
| `analytics/scripts/source_signals/source_signal_keyword_normalization.py` | Shared canonical keyword normalizer. | None. |
| `analytics/scripts/source_signals/build_keyword_signal_preview.py` | `map_keywords_for_content`, metadata fallback, governed title overrides, `build_watch_guidance`, preview QA. | Reads local DB; generated reports; no writes. |
| `analytics/scripts/source_signals/import_source_signals_from_preview.py` | Preview validation, semantic diff, `SourceSignalRecord`, upserts with `--write`. | Dry run by default; writes only with `--write`. |
| `analytics/config/source_signal_keyword_mapping.json` | Runtime mapping taxonomy, labels, confidence, display/ranking rules. | Configuration. |
| `analytics/config/source_signal_keyword_review_decisions.json` | Human review rationale; must support the mapping version. | Governance only. |
| `analytics/config/source_signal_title_overrides.json` | Exceptional, governed structured signal/guidance overrides. | Applied during preview, not read by API runtime. |
| `backend/migrations/010_add_source_signal_storage.sql` | Creates source-signal and watch-guidance storage. | Schema migration. |
| `backend/schema.sql` | Rebuild definition for the same tables/indexes. | Schema source. |

### Audits And Diagnostics

| Path | Responsibility | Output |
| --- | --- | --- |
| `analytics/scripts/audits/audit_decision_display_quality.py` | Audits production details output and separates display readiness from upstream review. | JSON, CSV, and summary under `analytics/processed/source_signals/`. |
| `analytics/scripts/audits/build_decision_insight_baseline.py` | Captures one deterministic record per current catalog title. | `decision_insight_formatter_v2/baseline_catalog.json`. |
| `analytics/scripts/audits/compare_decision_insight_formatter.py` | Compares a baseline with current runtime output and builds identity conflicts. | Proposed comparison and conflict JSON. |
| `analytics/scripts/audits/build_decision_insight_stratified_review.py` | Deterministic cross-category QA sample and overview provenance. | Stratified review JSON. |
| `analytics/scripts/audits/explain_decision_insight.py` | Explains one production plan by title or content ID. | Console and optional JSON. |
| `analytics/scripts/audits/decision_insight_report_metadata.py` | Validates and emits formatter/mapping/review/override versions. | Shared report metadata. |
| `analytics/scripts/audits/audit_source_signal_mapping_quality.py` | Audits upstream signal quality; separate from prose quality. | Source-signal report. |
| `analytics/scripts/common/paths.py` | Resolves repository/backend paths and makes backend imports stable for module CLIs. | No DB or reports. |

Generated artifacts are ignored operational evidence, not runtime inputs:

- `analytics/processed/source_signals/decision_insight_formatter_v2/baseline_catalog.json`
- `analytics/processed/source_signals/decision_insight_formatter_v2/proposed_comparison_catalog.json`
- `analytics/processed/source_signals/decision_insight_formatter_v2/stratified_catalog_review.json`
- `analytics/processed/source_signals/decision_insight_formatter_v2/source_signal_identity_conflicts.json`
- `analytics/processed/source_signals/decision_display_quality_report.json`
- `analytics/processed/source_signals/decision_display_quality_report.csv`
- `analytics/processed/source_signals/run_reports/decision_display_quality_summary.json`
- any `--json-output` produced by the explanation command.

### Tests And Fixtures

- `backend/tests/test_decision_insight_formatter.py`: pure planning, rendering,
  unknown-input, templates, rating provenance, documentary, deduplication, and
  deterministic behavior.
- `backend/tests/test_source_signal_service.py`: real service-path safety,
  compatibility, stored-guidance authority, and public leakage tests.
- `backend/tests/test_content_read_endpoints.py`: details endpoint contract.
- `backend/tests/test_insight_summary_service.py`: safe summary/headline behavior.
- `backend/tests/test_decision_display_quality_audit.py`: issue detection and the two
  readiness states.
- `backend/tests/test_decision_insight_reports.py`: baseline, comparison, stratified,
  conflict, explanation, and version metadata.
- `backend/tests/test_decision_insight_semantic_catalog.py` and
  `backend/tests/fixtures/decision_insight_semantic_catalog.json`: 26-title semantic
  property catalog.
- `backend/tests/test_keyword_signal_preview.py` and
  `backend/tests/test_source_signal_importer.py`: upstream preview/import and safety
  provenance.
- `backend/tests/test_source_signal_schema.py` and
  `backend/tests/test_source_signal_mapping_quality_audit.py`: storage and upstream
  quality contracts used to interpret formatter evidence.
- `backend/tests/test_analytics_script_packages.py`: canonical audit CLI imports and
  `--help` smoke tests.

Cross-reference documentation is maintained in `README.md`,
`analytics/scripts/README.md`, `docs/data_ingestion_pipeline.md`,
`docs/backend_testing.md`, and
`docs/tmdb_keyword_import_signal_mapping_plan.md`; this file remains authoritative
when those summaries omit implementation detail.

Files inspected but excluded from the sentence path include
`backend/app/services/content_video_service.py`, user-content/watch-state services,
homepage/discovery ranking services, and frontend trailer components. They share the
details page or content model but do not generate, transform, validate, or render
`primary_insight`.

## 5. Runtime Service Flow

A normal details request follows this concrete call path:

1. `content.get_content_details()` calls
   `content_service.get_content_details_service(content_id, db)`.
2. The content service loads content, certification, optional series metadata,
   genres, platforms, ratings, videos, and credits.
3. It calls `get_content_decision_layer(db, content_id, display_context=...)`.
4. `fetch_watch_guidance()` loads one `content_watch_guidance` row.
5. `fetch_active_source_signals()` loads active rows and derives
   `spoiler_safe` from JSONB `source_payload`; missing legacy safety metadata is
   interpreted as safe.
6. `runtime_signal_rows()` retains internal safety and source names.
   `public_signal_rows()` filters unsafe rows and returns only dimension, value,
   label, and confidence.
7. `build_watch_profile()` sanitizes stored structured guidance.
8. `_build_decision_display_and_plan()` clears stored `watch_feel`, calls
   `build_display_profile()`, computes `infer_context_identity()`, then calls
   formatter `build_insight_plan()` and `render_insight_plan()`.
9. Rejected source-identity concept families are removed by
   `filter_rejected_public_profile()`, `filter_rejected_public_signals()`, and
   `filter_rejected_public_labels()`.
10. The selected identity is placed first in the public profile.
11. The rendered sentence becomes `display.primary_insight` and compatibility
    `watch_profile.watch_feel`.
12. `build_decision_headline()` uses `render_decision_headline(plan)`, falling back
    to safe `best_for` or chips only if no supported identity exists.
13. Reasons and cautions use compatible public signals.
14. With `include_debug=True`, `decision_layer.debug.insight_plan` retains the plan
    and rejected candidates; normal public responses discard it.
15. `build_insight_summary()` receives the completed decision layer. No legacy
    sentence fallback can replace a valid Formatter v2 result.

## 6. Formatter And Configuration Versions

| Version | Current value | Location | Bump when |
| --- | --- | --- | --- |
| Formatter | `2.0.2` | `DECISION_INSIGHT_FORMATTER_VERSION` in `decision_insight_formatter.py` | Planning, validation, rendering, compatibility, or public-safety behavior changes. |
| Keyword mapping | `2026-07-29-v2.9` | `source_signal_keyword_mapping.json` | Runtime keyword-to-signal semantics change. |
| Review decisions | `2026-07-29-v1.7` | `source_signal_keyword_review_decisions.json` | Governed decisions change; it must support the current mapping version. |
| Title overrides | `2026-07-29-v3.7` | `source_signal_title_overrides.json` | Structured title override semantics change. |

All formatter diagnostics emit these four values through
`decision_insight_versions()`. A formatter-only change must not bump mapping or
override versions. Reproduction requires the structured rows/provenance, title
metadata, and all four versions recorded by the report.

## 7. Input Model

The formatter receives no database handle. Its inputs are:

- display profile: identity, themes, feel, pace, best-for, and consider-first;
- compatibility watch profile: structured chips and override/fallback flags, with
  legacy `watch_feel` cleared;
- runtime active signals: dimension, canonical value, display label, confidence,
  source names/provenance, and spoiler safety;
- display context: title, overview, content type, genres, platforms, ratings,
  credits, series metadata, and the governed inferred identity.

Identity may use safe audience-expectation/topic signals, governed genre composites,
curated provenance, or explicit context inference. Modifiers use safe mood/tone.
Differentiators use safe topic themes and governed overview rules. Pace uses pacing
only. The headline uses the validated identity/modifier plan. Ratings may create
supporting facts and an internal `audience_modifier` evidence component, but they are
not rendered into the primary sentence. Platforms, credits, age, runtime, ratings,
and series status cannot alter the main sentence.

## 8. Signal Dimensions

| Dimension | Meaning and Formatter v2 use |
| --- | --- |
| `audience_expectation` | Stable viewing identity. Can be an identity, public chip, and best-for input; highest signal identity priority. |
| `topic_theme` | Subject or identity-like governed concept. Can be a differentiator; only labels with an identity copy role can become identity. |
| `mood` | Emotional atmosphere. Can become a governed adjective and public feel label; never fabricates pace or identity. |
| `tone` | Narrative stance. Ranked with mood for one modifier and public feel; no raw label is forced into prose. |
| `pacing` | Viewing rhythm. Can become a governed pace phrase or suffix; omitted when overlapping or unsupported. |
| `intensity` | Viewing pressure. Used in profile/caution logic; it is not independently treated as pace. |
| `content_caution_proxy` | Non-spoiler viewing consideration. Used for public cautions/consider-first, not identity or differentiators. |

Absent dimensions remain absent. Metadata fallback can supply a safe identity, but
does not fabricate missing feel, pace, or themes.

## 9. Spoiler-Safety Contract

Spoiler-unsafe decisions originate in the governed mapping/review workflow. Preview
generation retains their analysis status but does not let unsafe keywords produce
normal public signal effects. For imported active rows, the importer writes
`source_payload.spoiler_safe`. Runtime SQL reads that field; legacy rows without it
default to safe for backward compatibility.

`safe_signals()` excludes `spoiler_safe=False` before public conversion and before
candidate construction. The plan may record a rejected `spoiler_unsafe` candidate
for diagnostics. Unsafe or rejected concepts cannot influence primary insight,
identity, themes, best-for, compatibility watch-feel, decision headline, reasons,
cautions, or Insight Summary. They may appear only in debug plans, conflict reports,
and explanation output.

## 10. Identity Candidate Construction

Candidate sources and implemented trust are:

1. Curated override signal with an identity copy role (`tier 1`).
2. High-confidence `audience_expectation` (`tier 2`).
3. Governed genre composite or strictly evidenced inferred identity (`tier 3`).
4. Medium-confidence audience identity or high/medium identity-bearing topic
   (`tier 4`).
5. Explicit governed inferred identity (`tier 5` when not promoted to tier 3).
6. Low-confidence audience or other identity-like topic (`tier 6`).
7. Display-profile or generic metadata fallback (`tier 7`).

Every candidate needs `identity_has_copy_role()`, then must pass
`identity_compatibility()`. Longer labels do not automatically win. Ranking is
trust tier, confidence, specificity score, original deterministic position, then
normalized label. Unknown labels without a governed identity noun/copy role are
rejected as `missing_identity_copy_role`; low-confidence identities cannot outrank
higher-trust evidence.

`GOVERNED_IDENTITY_COPY_ROLES` admits specific identities whose final token is not
a general identity noun. Formatter 2.0.2 includes `Aviation action` and
`Martial-arts action`. Both require a governed source identity and compatible
Action metadata; an aircraft, fight, or weapon mention alone cannot create them.
Curated provenance retains tier 1.

## 11. Identity Trust Tiers

`IDENTITY_TRUST_TIER_LABELS` is the executable registry. Within a tier,
`identity_score()` favors reliable governed identities, specificity markers,
audience-expectation evidence, and confidence while penalizing generic/weak labels.
Candidates not selected are retained with `lower_trust_or_specificity` or the
explicit centrality displacement reason. Stable normalized ordering makes ties
deterministic.

## 12. Compatibility Rules

`identity_compatibility()` currently enforces:

- Documentary metadata rejects fictional identities; `Documentary` and `Concert
  film` are allowed.
- Romantic identities require Romance genre or explicit romance premise.
- Superhero identities require independent superhero/comic-book evidence and reject
  incompatible History/Music-only metadata.
- Cyberpunk and anthology identities require explicit lexical evidence.
- Cartel identity requires a cartel, organized-crime, trafficking, or drug-trade
  premise.
- Dark fantasy requires Fantasy metadata and explicit dark-fantasy provenance.
- War identities require War metadata or high-confidence central military evidence.
- Prison drama requires an explicit governed identity and central prison premise.
- Serial-killer investigation requires explicit serial-killer evidence.
- Psychological survival thriller requires physical survival evidence and
  Thriller/Horror compatibility; family/animation/adventure alone is insufficient.
- Fantasy adventure requires Fantasy; sci-fi requires Sci-Fi/Science Fiction.
- Crime and fantasy identities require compatible genre or explicit premise.
- Generic marker-based inferred identities at weaker tiers must match Comedy,
  Documentary, Horror, Mystery, Romance, Thriller, or Western metadata.

Lexical premise evidence is centralized in `EVIDENCE_FAMILIES` and matched with
`evidence_family_matches()`. Governed singular/plural forms include serial
killer/serial killers, cartel/cartels, and spy/spies plus explicit secret-agent,
intelligence-service/officer/operative, Soviet-agent, sleeper-agent, posing-as,
living-undercover, KGB, MI5, and MI6 phrases. The verb construction `spies on` is
excluded. A spy
identity also requires explicit premise evidence and compatible Drama, Thriller,
Crime, Action, War, or War & Politics metadata.

Rejected candidates receive `identity_metadata_conflict`, a specific conflict reason,
and evidence. Selection falls through to the strongest compatible candidate.

## 13. Centrality And Corroboration

Centrality is not inferred from one incidental token. Each compatible candidate
records independent corroboration families: curated identity,
`audience_expectation`, `topic_theme`, content genre, explicit overview premise,
and governed inferred context. Repeated labels within one family count once.

Trust tiers remain authoritative. Tier-1 curated identities are never displaced by
the centrality guard. After compatibility, the guard may resolve only a same-tier
contest, or a contest between a governed tier-3 genre composite and an adjacent
tier-4 candidate. The alternative must have explicit premise evidence and a
materially larger independent corroboration set. This prevents a longer incidental
label such as creature, investigation, space, organized-crime, or background-war
context from winning on specificity alone. Every selected and rejected candidate
records `corroboration_sources`, `corroboration_count`, `centrality_class`,
`explicit_premise_evidence`, `incidental_context`, and ranking rationale.

Some identities, such as cartel, prison, war, serial-killer, and survival thriller,
also retain dedicated compatibility requirements. Missing overview wording is not
itself evidence that a concept is incidental. A rejected upstream identity can
remain in internal conflict evidence while a compatible fallback makes the public
display usable.

## 14. Modifier Selection

`select_modifier()` considers profile feel labels backed by mood/tone signals. It
ranks confidence first, uses a small comedy-specific order, then stable source order
and label. `INSIGHT_ADJECTIVES` is the allowlist. Unsupported labels are rejected as
`no_adjective_copy_role`. At most one modifier is selected, and a modifier already
present in the identity is omitted. Pacing is selected separately by
`select_pacing()` and converted to dialogue-driven, measured, fast-moving,
character-driven, or a conservative supported fallback. Overlapping pacing is
removed. Ratings never render into `primary_insight`.

## 15. Differentiator Selection

Differentiators come from priority overview rules, safe `topic_theme` signals with
an `INSIGHT_ABOUT_PHRASES` copy role, then non-priority overview rules. At most two
are retained. Identity-family overlap, duplicate families, duplicate phrases,
unsupported raw taxonomy, missing copy roles, and low-confidence secondary items are
rejected with reasons. The explicit racial-inequality context is exclusive; lower
priority candidates are recorded but not selected. Atomic phrases containing
`and` use `alongside` when another phrase is joined.

`differentiator_is_incidental()` applies an additional conservative centrality
check. War is suppressed when neither War metadata nor an explicit central war
premise supports it. Creature context is suppressed only when a central mythic/space
sci-fi identity wins and the overview has no explicit creature premise. Governed
overview-rule phrases remain eligible, and absent wording alone does not suppress
investigation, prison, or organized-crime signals. Suppressed concepts remain in
the debug plan as `incidental_context_suppressed`.

## 16. Concept Families And Semantic Deduplication

`INSIGHT_CONCEPT_ALIASES` in `decision_insight_formatter.py` governs the families:
Romance, Family, Class, Coming-of-age, Workplace, Emotion, Live music,
Investigation, Survival, War identity, History identity, Human cost, Military
mission, War setting, Crime, Supernatural, Afterlife, Revenge, Power, Legal,
Technology/society, Future context, Post-apocalyptic, Music, Nature, Body,
Creature, Conspiracy, and Superhero.

Aliases in one family overlap for sentence selection; related but distinct families
remain available (for example War documentary plus Human cost, or Music documentary
plus Artistic ambition). Identity-to-differentiator and differentiator-to-
differentiator checks use families, not substring matching alone. Public chip
compaction in `source_signal_service.py` is a separate, more presentation-oriented
process. Rejected identity families are removed from every public field after the
plan is built.

## 17. Copy-Role Registry

The formatter uses controlled roles rather than inserting taxonomy labels blindly:

- `INSIGHT_ADJECTIVES`: `light -> light`, `melancholy -> melancholic`,
  `high stakes -> high-stakes`.
- `INSIGHT_ABOUT_PHRASES`: `class divide -> differences in class and status`,
  `creature threat -> an escalating creature threat`, `medical workplace ->
  workplace pressure in a hospital`, `live music performance -> live performance`.
- pacing conversion in `select_pacing()` and `pacing_suffix()`.
- identity noun allowlists and governed genre/inferred identity registries.

Canonical labels with no required copy role are rejected rather than placed into an
invalid grammatical slot. Unknown values may still be a valid identity only when
their normalized final noun is a governed identity noun; raw taxonomy-only labels
such as Animation style/Anime style are suppressed as differentiators.

## 18. Governed Overview Context

`INSIGHT_CONTEXT_RULES` performs bounded lexical matching; it never summarizes an
overview freely. Implemented rules are:

| Rule | Evidence | Phrase | Scope / safeguard |
| --- | --- | --- | --- |
| `explicit_racial_inequality` | exact racial-inequality phrase | racial inequality | equivalent; exclusive priority |
| `studio_workplace` | studio plus film/movie/creative/executive | pressure inside a film studio | narrower |
| `matchmaking` | matchmaker/matchmaking | modern matchmaking | equivalent |
| `family_estrangement` | estranged/family rift/fractured family | strained family bonds | narrower |
| `live_performance` | concert/on-stage/live-performance language | live performance | equivalent |
| `concert_staging` | concert film plus choreography/cinematic performance | cinematic staging and choreography | narrower |
| `artistic_ambition` | explicit aspiring-artist/creative-ambition phrase | artistic ambition | equivalent |
| `investigation` | investigates/investigator/detective/FBI/police language | an investigation | narrower |
| `military_mission` | task/mission language and War genre | a military mission | narrower, genre-gated |
| `war_experience` | war/battle/occupation/soldier/troops and War genre | the human experience of conflict | narrower, genre-gated |
| `survival` | stranded/fight or try to survive/survivors | survival under pressure | narrower |
| `outbreak` | explicit plague/outbreak phrase | a spreading outbreak | narrower |
| `rescue_mission` | explicit rescue/tasked-with-bringing phrase | a rescue mission | equivalent |
| `multigenerational_migration` | family plus immigrant/homeland/generations | migration across generations | narrower |

Each component records `rule`, matched text, and scope in its evidence field.

## 19. InsightPlan Model

`InsightPlan` contains:

- `primary_identity`, `tone_modifier`, `mood_modifier`;
- `primary_differentiator`, `secondary_differentiator`, `pacing_modifier`;
- `audience_modifier` (rating evidence retained outside primary copy);
- `template_family`;
- `rejected_candidates` with source/evidence/reason;
- `validation_errors`;
- `curated_override_applied`, `curated_identity_available`, and
  `curated_identity_evaluation`;
- `formatter_version`.

Each selected `InsightComponent` carries text, grammatical role, concept family,
source, evidence, support flag, confidence, trust tier, and selection rationale.

Representative abbreviated serialization:

```json
{
  "primary_identity": {
    "text": "Workplace comedy",
    "role": "identity",
    "source": "source_signal:audience_expectation:workplace comedy",
    "confidence": "high",
    "trust_tier": 2
  },
  "tone_modifier": {"text": "light", "role": "adjective"},
  "primary_differentiator": {
    "text": "pressure inside a film studio",
    "role": "about_phrase",
    "source": "overview_rule"
  },
  "template_family": "identity_conflict",
  "rejected_candidates": [],
  "validation_errors": [],
  "formatter_version": "2.0.2"
}
```

`curated_identity_evaluation` is `not_applicable` when no curated identity exists,
`not_evaluated` before the selection pipeline processes one, `selected` when it
wins, or `evaluated_rejected` when copy-role, compatibility, or ranking checks
reject it. Only `not_evaluated` produces
`PRIMARY_IDENTITY_CURATED_OVERRIDE_IGNORED`; an evaluated rejection can require
source review without invalidating safe display.

## 20. Plan Validation

`validate_insight_plan()` currently emits structural errors for a missing supported
identity, any unsupported selected component, duplicate selected concept families,
and invalid differentiator roles. These errors prevent rendering. Candidate-level
checks reject spoiler-unsafe, incompatible, overlapping, low-confidence secondary,
raw-taxonomy, and missing-copy-role inputs before validation.

The display audit adds independent output checks for missing/generic/low-specificity
insights, duplicate concepts, raw-label grammar/taxonomy, repeated words, template
overuse, fallback-only output, chip repetition, unsupported components, spoiler
risk, punctuation, adjective stacks, awkward pacing, conjunction chains, excessive
length, missing facts, and existing profile correctness rules. Critical display
issues make `display_ready=false`. A successfully rejected identity conflict creates
source-signal review, not a display failure.

`PRIMARY_IDENTITY_STRONGER_CORROBORATED_CANDIDATE_AVAILABLE` independently audits
serialized candidate provenance. It reports the selected/candidate tiers,
corroboration sources, and ranking rationale when an explicit, materially better
supported compatible identity loses without a higher-trust justification. The
audit evaluates plan data independently rather than calling the selection guard.

## 21. Template Families

Templates are selected semantically by `select_template()`, never randomly:

| Family | Structure / condition |
| --- | --- |
| `documentary_examination` | `A {subject} examining {primary} [through/alongside {secondary}].` Documentary identity plus differentiator. |
| `character_exploration` | `A {subject} exploring {differentiators}.` Character drama plus differentiator. |
| `thematic_exploration` | Same exploration form for governed thematic families such as family, class, identity, mental health, romance, or human cost. |
| `experience_driven` | `A {pace} {subject} about {differentiator}.` Pace exists, tone does not, and evidence supports the structure. |
| `identity_conflict` | `A {subject} shaped by {differentiators}.` Conflict, investigation, mission, pressure, struggle, or threat. |
| `hybrid_blend` | `A {subject} that blends {one} with {two}.` Two differentiators and horror-comedy/satire identity. |
| `layered_exploration` | `A {subject} shaped by {one} and {two}.` Two reliable non-hybrid differentiators. |
| `identity_about` | `A {subject} [about {primary}] [and/alongside {secondary}] [pace suffix].` Safe default. |

## 22. Rendering Rules

`article_for()` selects `a/an` from the normalized subject. The centralized
`realize_display_casing()` registry restores only governed token/phrase forms:
`AI`, `FBI`, `CIA`, `MI5`, `MI6`, `KGB`, `WWII`, and `World War II`. It applies at
the display-realization boundary, including after lowercasing an identity for an
article, so `AI thriller` cannot become `aI thriller`. It does not title-case a
sentence or uppercase ordinary substrings. The
renderer normalizes whitespace, removes comma-before-and, uses safe conjunctions for
atomic phrases, avoids duplicate families/phrases before rendering, and caps output
at 180 characters on a word boundary. Modifier ordering is deterministic. No rating
modifier is appended. The same plan always renders the same result.

## 23. Public Output Contract

| Field | Source and consistency rule |
| --- | --- |
| `decision_layer.display.primary_insight` | Formatter-rendered authoritative prose. |
| `display.profile.identity` | Safe structured profile with selected identity first; weaker same-family fragments are removed. |
| `display.profile.themes/feel/pace/best_for/consider_first` | Safe structured fields, filtered for rejected concepts and weaker fragments that merely repeat the selected identity. |
| `display.supporting_facts` | Metadata/rating/access/credits facts; not primary copy. |
| `decision_layer.watch_profile.watch_feel` | Compatibility alias of the exact primary insight. |
| `watch_profile.chips/best_for/consider_first` | Sanitized stored guidance, filtered for rejected concepts. |
| `decision_support.headline` | Plan-driven concise identity; safe best-for/chip fallback. |
| `decision_support.reasons/cautions` | Compatible public signals only. |
| `insight_summary` | Built from the completed safe decision layer and metadata. |
| `DecisionDisplayCard` | Renders only `decision_layer.display`; never reconstructs prose. |

Rejected and unsafe concepts may not appear in any of these public fields.
For example, `Investigation-led mystery` suppresses the weaker public theme
`Investigation-led`, while `Conspiracy` and `Government secrecy` remain eligible.
If this deduplication empties themes, a selected safe topic differentiator is
restored so the structured profile remains consistent with the sentence.

## 24. Readiness States

`display_ready` evaluates final public output using display issues, score, and
critical safety/coherence checks. `source_signal_review_required` means at least one
upstream source identity was rejected as incompatible (`SOURCE_SIGNAL_IDENTITY_METADATA_CONFLICT`).
The compatibility aggregate `review_required` is true when either state needs review.

A safe fallback can therefore yield:

```text
Selected identity: Superhero team story
Rejected source identity: Romantic drama
display_ready: true
source_signal_review_required: true
```

The rejected concept remains diagnostic evidence and is removed from every public
field. Display review issues affect display readiness; source conflicts alone do
not. Critical issues remain reserved for unsafe or incoherent public output.

A safe Documentary metadata identity with a specific governed overview
differentiator is not classified as incidental or low-specificity merely because
incompatible fictional identities were rejected. Those rejections still set
`source_signal_review_required=true`.

## 25. Audit And Diagnostic Pipeline

All commands below are deterministic and read-only. DB-backed commands use
`DATABASE_URL`; their code opens read-only transactions and rolls back.

```bash
python3 -m analytics.scripts.audits.build_decision_insight_baseline \
  --batch-size 100
```

Captures the actual catalog size in batches. Default output:
`analytics/processed/source_signals/decision_insight_formatter_v2/baseline_catalog.json`.

```bash
python3 -m analytics.scripts.audits.compare_decision_insight_formatter \
  --batch-size 100
```

Compares the baseline with current runtime output. Outputs the proposed comparison
and source-signal identity conflict reports in the same ignored directory.

```bash
python3 -m analytics.scripts.audits.build_decision_insight_stratified_review \
  --minimum 40
```

Reads the comparison report and writes the deterministic stratified review.

```bash
python3 -m analytics.scripts.audits.audit_decision_display_quality \
  --include-passing \
  --batch-size 100
```

Audits production details output. It supports content IDs, content type, limit,
offset, minimum score, and fail gates. Outputs JSON, CSV, and summary reports.

```bash
python3 -m analytics.scripts.audits.explain_decision_insight \
  --title "The Crown" \
  --json-output analytics/processed/source_signals/decision_insight_formatter_v2/the_crown_explanation.json
```

Explains one production result. Every report records actual catalog scope where
applicable and all four version contracts.

## 26. Single-Title Explanation Command

Use either stable local identity:

```bash
python3 -m analytics.scripts.audits.explain_decision_insight --title "The Crown"
python3 -m analytics.scripts.audits.explain_decision_insight --content-id 152
```

Title matching is exact and case-insensitive; ambiguous titles require content ID.
The output shows metadata, genres, overview, safety-aware signals grouped by
dimension, all identity candidates, source, trust tier, confidence, compatibility,
centrality/corroboration evidence, selection/rejection reason, modifier,
differentiators, full serialized plan, template, public fields, source conflicts,
the two readiness states, and versions. `--json-output` writes the same deterministic
payload; place it under `analytics/processed` so it remains ignored.

## 27. Formatter Problem Versus Mapping Problem

| Symptom | Owner |
| --- | --- |
| Correct signals, awkward wording | Formatter copy roles/templates. |
| Wrong canonical identity produced from a keyword | Mapping plus review decision. |
| Globally correct mapping, exceptional title | Governed title override. |
| Valid alternate identity rejected | Formatter compatibility/centrality rule. |
| Sentence is safe but conflict report exposes a bad stored signal | Source-signal cleanup workflow. |
| Spoiler-unsafe concept reaches public output | Safety/integration defect. |
| Missing useful source evidence | Ingestion/mapping quality, not prose. |
| Correct API output rendered incorrectly | Frontend consumer. |

## 28. Safe Change Procedure

Formatter behavior changes require a formatter-version bump, focused formatter and
service integration tests, semantic fixture tests, regenerated ignored diagnostics,
one-title explanations for affected concepts, the full backend suite, and this
document update.

Mapping changes require mapping/review semantic parity and version bumps, a full
preview rebuild, importer dry run, mapping/display audits, and no formatter-version
bump unless formatting behavior also changes. Title override changes bump only the
override version. Never use generated reports as configuration.

## 29. Future Batch 8+ Workflow

1. Ingest title metadata and raw provider keywords.
2. Build and review the full current-catalog source-signal preview.
3. Dry-run and manually apply structured signals/guidance when safe.
4. Request `/content/{id}/details`; Formatter v2 automatically receives the new
   title's loaded metadata/signals and derives its sentence.
5. Run display audit, conflict report, and one-title explanation for review cases.

No sentence migration, manual primary-insight write, formatter code change, or title
override is required for an ordinary new title. Change mappings only for a genuine
reusable taxonomy gap; change formatter rules only for a demonstrated global rule
gap.

## 30. Performance And Scaling

The formatter executes no query. For one title, normalization, candidate sorting,
registry checks, and deduplication are bounded by that title's loaded signals and the
fixed rule registries: approximately `O(S log S + S*R)`, where `S` is active signals
and `R` is the small fixed rule set. Memory is `O(S)`.

Audit CLIs discover the current catalog size and fetch IDs with configurable batches
(default 100), deterministic ID ordering, and zero/one/many-title support. Each title
currently calls the details service, which issues a bounded bundle of per-title
queries; this is the known audit N-query limitation. It does not create an N+1 inside
the formatter. At the current hundreds-of-titles scale this is acceptable. Runtime
caching is unnecessary because the work is small and formatter changes should become
visible without rewriting stored guidance.

## 31. Known Limitations

- Overview rules are lexical, governed, and test-driven; they are not semantic
  summarization.
- An unseen canonical label may fall back or be rejected when no copy role exists.
- Upstream mapping conflicts can still occur and remain a separate cleanup workflow.
- Automated audits cannot replace human semantic approval.
- Full-catalog audits use per-title service query bundles even though ID loading is
  batched.
- Legacy rows without explicit `spoiler_safe` provenance default to safe.
- Concept-family registries require maintenance when genuinely new taxonomy concepts
  are introduced.

## 32. Worked End-To-End Examples

### Clean, well-supported title

Input: Comedy/Drama series, high-confidence `Workplace comedy`, tone `Light`, and an
overview explicitly describing a film studio. Candidates rank the source audience
identity at tier 2 above metadata Drama. The `studio_workplace` rule adds `pressure
inside a film studio`; Light becomes a governed adjective. Plan: identity Workplace
comedy, modifier light, differentiator studio pressure, `identity_conflict` template.
Output: `A light workplace comedy shaped by pressure inside a film studio.` Public
identity starts with Workplace comedy; display is ready; no source review is needed.

### Incompatible identity rejected, display still ready

Input: Animation/Action/Fantasy with explicit superhero evidence plus an incompatible
source Romantic drama and Romance theme. Romantic drama fails central romance
compatibility. Its Romance family is removed from public identity, themes, chips,
best-for, headline, compatibility watch-feel, and Insight Summary. The governed
superhero identity is selected. The debug plan/conflict report retains the rejection.
`display_ready=true`; `source_signal_review_required=true`.

### Sparse safe fallback

Input: a series with Drama genre, no overview, and no safe identity/theme/mood/pace
signals. `genre_identity()` supplies tier-7 Drama. No modifier or differentiator is
fabricated. Plan uses `identity_about`; output is `A drama.` The sentence is truthful,
but audit rules may mark it low-specificity/fallback-only for display review. The
formatter does not throw.

The tracked semantic regression catalog also covers acronym realization, spy lexical
variants, fantasy-versus-background-war centrality, mythic/space/creature contests,
heist-versus-investigation, superhero-versus-space, action-versus-organized-crime,
and incidental differentiator suppression without production title allowlists.

Automated centrality remains deliberately bounded. It recognizes only governed
families and lexical evidence; it does not summarize overviews, infer unregistered
identities, or demote a signal merely because a short overview omits it. Genuine
source-evidence gaps remain mapping or human-review work.

All examples use formatter `2.0.2`, mapping `2026-07-29-v2.9`, review
`2026-07-29-v1.7`, and overrides `2026-07-29-v3.7`.

## 33. Related Commands Quick Reference

```bash
# Full source-signal preview
python3 -m analytics.scripts.source_signals.build_keyword_signal_preview

# Source-signal import dry run (no --write)
python3 -m analytics.scripts.source_signals.import_source_signals_from_preview

# Display audit
python3 -m analytics.scripts.audits.audit_decision_display_quality --include-passing

# Formatter comparison and conflict report
python3 -m analytics.scripts.audits.compare_decision_insight_formatter

# Stratified QA
python3 -m analytics.scripts.audits.build_decision_insight_stratified_review --minimum 40

# One-title explanation
python3 -m analytics.scripts.audits.explain_decision_insight --title "The Crown"

# Semantic regression catalog
cd backend
python3 -m pytest tests/test_decision_insight_semantic_catalog.py

# Full backend suite
python3 -m pytest
```

## 34. Maintenance Checklist

- [ ] Did formatter behavior change, and therefore require a formatter version bump?
- [ ] Are mapping/review/override versions unchanged unless their semantics changed?
- [ ] Are unsafe and rejected signals excluded from every public field?
- [ ] Did pure formatter and service-path safety tests pass?
- [ ] Did the semantic fixture catalog pass?
- [ ] Were baseline/comparison/audit/stratified/explanation reports regenerated?
- [ ] Was at least one relevant one-title explanation reviewed?
- [ ] Was this document updated to match actual functions and registries?
- [ ] Were generated reports kept out of Git?
- [ ] Was PostgreSQL left unchanged during formatter-only work?
- [ ] Did the full backend suite, compileall, and `git diff --check` pass?
