# Source Signal Research Findings

## 1. Purpose

This document preserves practical research findings for InsightStream's future decision-support layer.

It is meant to guide:

- TMDb keyword ingestion
- structured source signals
- mood, tone, pacing, and intensity taxonomy
- future review-derived signals
- future LLM-grounded summaries
- licensing and source-risk decisions

This is not an implementation plan by itself. It is also not legal advice. Before any production or commercial use, official source terms, dataset licenses, API terms, and provider agreements should be rechecked.

The goal is to keep the useful research decisions close to the codebase so future implementation work does not restart from vague source ideas or unsafe assumptions.

## 2. Final Direction From Research

Final direction:

```text
Immediate:
TMDb keywords ingestion preview

Near-term:
Structured source signals from metadata + ratings + availability + certification + TMDb keywords

Research/training:
MovieLens Tag Genome, MPST, sentiment/review corpora

Future licensed production:
IMDb Parents Guide, Rotten Tomatoes licensed data, commercial TMDb/IMDb licensing

Avoid:
Scraped review datasets for product use
```

Hard product rules:

```text
Do not implement review ingestion before review-text policy is finalized.
Do not use raw review text in product UI.
Do not use LLM summaries until approved structured facts/signals exist.
```

Near-term implementation should focus on structured, source-safe enrichment. TMDb keywords are the best next candidate because they connect directly to existing TMDb IDs, support both movies and series, and avoid raw review text.

## 3. Source Ranking

| Rank | Source | Source type | Movie coverage | TV/series coverage | ID quality | Signal value | License/product risk | Recommended use | Implementation timing |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | TMDb Keywords | Structured provider tags | Good | Good | Strong via TMDb IDs | High for genre-adjacent expectations, tone hints, themes | Low to medium; follow TMDb terms | Use next | Immediate preview |
| 2 | IMDb Parents Guide commercial dataset | Structured content advisory | Good | Good | Strong via IMDb IDs | High for intensity, content caution, family suitability | Medium; license required | Future licensed source | Later, after licensing |
| 3 | MovieLens Tag Genome classic/2021 | Tag relevance scores | Movie-only | None | Good via `links.csv` to IMDb/TMDb | Very high for taxonomy design | Non-commercial/research constraints | Research/training only | After TMDb keyword preview |
| 4 | MovieLens Tag Genome Dataverse CC0/property graph variant | Tag/relevance graph variant | Movie-only | None | Must verify | Potentially high | Promising but provenance/schema must be verified | Research/training only until verified | Later dataset inspection |
| 5 | MPST: Movie Plot Synopses with Tags | Plot synopses + narrative tags | Movie-only | None | Good via IMDb IDs | High for narrative/tag taxonomy | CC BY-SA style obligations; spoiler risk | Research/training only | Later research/modeling |
| 6 | TMDb Reviews | User review text/metadata | Good | Good | Strong via TMDb IDs | Medium for review-derived themes | Medium; review-text policy required | Prototype only | Later feasibility check |
| 7 | Letterboxd HF dataset | Film-community data/reviews/ratings | Movie-only | None | Weak to medium; title/year/director matching | Medium for research, rating snapshot | Medium/high; dataset/source policy required | Prototype only | Current use: rating snapshot only |
| 8 | IMDb/HF/Kaggle review datasets | Review text corpora | Varies | Varies | Often weak/source unclear | Medium for sentiment/tone modeling | High if scraped/source unclear | Research/training only | Avoid product use |
| 9 | Amazon Movie/TV reviews | Retail/user reviews | Broad but noisy | Broad but noisy | Weak title/product matching | Medium for generic sentiment training | Medium/high; not title-authoritative | Research/training only | Later generic experiments only |
| 10 | Rotten Tomatoes licensed data | Critic/audience ratings and reviews | Good | Some TV depending product | Strong if licensed | High for critic/audience split | High unless licensed | Future licensed source | Future only |
| 11 | Metacritic scraped datasets | Critic/user score/review data | Good for some titles | Mixed | Varies | High if licensed, risky if scraped | High | Avoid for now | Do not use scraped datasets |

Recommended labels:

- `Use next`: safe and aligned with current architecture
- `Near-term after preview`: useful after preview proves value
- `Research/training only`: useful for taxonomy/modeling, not direct product signals
- `Future licensed source`: wait for approved source/legal path
- `Avoid for now`: do not use in product

## 4. TMDb Keywords — Immediate Source

TMDb keywords are the immediate source to evaluate.

Research findings:

- TMDb keywords support movies and TV/series.
- Movie endpoint returns per-title keywords tied to TMDb movie ID.
- TV endpoint returns per-series keywords tied to TMDb series ID.
- Keyword shape is effectively:
  - `id`
  - `name`
- There is no explicit relevance or confidence score.
- Keyword presence should be treated as a weak structured signal, not proof.
- Existing `external_ids` already provide TMDb IDs for local content matching.
- Preview should come before any database import.

Implementation notes:

- Build preview script first.
- Output keyword coverage report.
- Do not write to DB in the first task.
- Do not map every keyword blindly.
- Keep raw provider payload in processed preview files only.
- Later import into a provider-neutral keyword/source table or JSON structure after schema decision.

Useful signal mappings to evaluate:

Crime/thriller expectation:

- murder
- detective
- serial killer
- investigation

Sci-fi identity:

- space
- time travel
- alien
- artificial intelligence

Tone/mood:

- bleak
- feel-good
- haunting
- dark comedy

Pacing/intensity:

- slow burn
- action
- survival
- suspense

Audience expectation:

- coming of age
- revenge
- political drama
- family comedy

Warnings:

- TMDb keywords can be noisy.
- Missing keywords should not mean absence of a trait.
- Keywords should not create strong claims without confidence.
- No raw reviews are involved.

## 5. MovieLens Tag Genome — Research/Taxonomy Source

MovieLens Tag Genome is useful for research and taxonomy design, not direct product use yet.

Research findings:

- Movies only.
- Contains tag relevance scores per movie/tag.
- Strong for tone, mood, pacing, intensity, and style taxonomy.
- Modern MovieLens datasets include mapping through `links.csv` to IMDb/TMDb.
- Classic/2021 datasets are research/non-commercial or non-commercial.

Use for:

- taxonomy design
- mapping TMDb keywords to internal dimensions
- evaluating which tags are useful
- future recommender/model training

Do not directly ship derived Tag Genome product signals commercially unless licensing/permission is clear.

Important implementation insight:

- Tag Genome can teach what signal tags should exist.
- TMDb keywords can provide production/prototype per-title tags.
- The mapping layer should be internal and conservative.

Examples:

- Tag Genome tag `slow` can inform `pacing = slow-burn`.
- Tag Genome tag `dark` can inform `tone = dark`.
- Tag Genome tag `visually appealing` can inform `style = visually strong`, but only if future UI supports style signals.

## 6. MPST — Narrative Tag Training Source

MPST is a narrative tag research source, not an immediate production signal source.

Research findings:

- Movie-only dataset.
- Has IMDb IDs.
- Has plot synopses and multi-label narrative tags.
- Around 14k movies and roughly 70 tags.
- Useful for mood, tone, pacing, and narrative expectation taxonomy.

Use for:

- mood/tone/pacing taxonomy
- narrative expectation tags
- supervised tag-classification experiments

License note:

- Research indicated CC BY-SA style licensing.
- Direct product use may create share-alike or attribution obligations.
- Treat as training/research unless licensing is reviewed.

Warnings:

- Plot synopses can contain spoilers.
- Do not display plot-derived tags if they reveal spoiler-level story events.
- Prefer spoiler-safe high-level tags only.

## 7. IMDb Parents Guide — Best Future Licensed Source

IMDb Parents Guide is the best future licensed source for structured intensity and content caution, but it is not a current prototype source unless licensed.

Research findings:

- Tied to IMDb IDs.
- Supports movies and TV/series.
- Provides content advisory categories and severity levels.
- Better than raw review text for production because it is structured and commercially licensed.

Strong for:

- intensity
- content caution
- family suitability
- audience expectation
- spoiler-safe watch fit

Possible future dimensions:

- `content_caution.violence`
- `content_caution.profanity`
- `content_caution.substance_use`
- `content_caution.frightening_intense_scenes`
- `content_caution.sex_nudity`
- `overall_intensity`

Warnings:

- Use only after licensing.
- Free-text descriptions should still be handled carefully.
- Do not invent content warnings from genres alone.

## 8. Dataverse CC0 Tag Genome Variant

Research found a Dataverse property-graph Tag Genome variant with a CC0 license.

Potential value:

- CC0 may allow broader use than the classic/non-commercial Tag Genome datasets.
- A graph structure may be useful for tag relationships or taxonomy exploration.

Current decision:

- Promising, but not approved.
- Schema, provenance, completeness, and relationship to original MovieLens terms must be verified before implementation.

Implementation note:

- A future task can inspect this dataset separately.
- Do not build a production dependency on it until verified.

## 9. Review Text Sources

### TMDb Reviews

Research decision:

- Potentially useful later.
- Official API path exists.
- Review text is still expressive user-generated content.
- Do not ingest before product/legal policy.
- If used later, derive compact signals instead of displaying raw text.

### Letterboxd HF Dataset

Research decision:

- Rich research corpus.
- Useful for mood/tone experiments.
- Movie-only.
- Do not use review text in product.
- Current Letterboxd product usage should remain rating snapshot only.

### IMDb/HF/Kaggle Review Datasets

Research decision:

- Useful for training sentiment/tone models.
- Often scraped or source-unclear.
- Not suitable for production per-title signals.

### Amazon Movie/TV Reviews

Research decision:

- Useful for generic sentiment/helpfulness training.
- Weak title matching.
- Not suitable for per-title product signals.

### Rotten Tomatoes / Metacritic

Research decision:

- Use only licensed/approved sources.
- Do not scrape.
- Future critic/audience split depends on licensed critic/audience data.

## 10. Signal Taxonomy To Build

Initial internal dimensions:

- `tone`
- `mood`
- `pacing`
- `intensity`
- `watch_commitment`
- `content_caution`
- `audience_expectation`
- `audience_confidence`
- `access_friction`
- `series_status`

### Tone

Examples:

- dark
- light
- humorous
- serious
- tense

### Mood

Examples:

- bleak
- feel-good
- suspenseful
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

### Watch Commitment

Examples:

- long movie
- short casual watch
- completed binge
- active weekly follow
- complex watch

### Content Caution

Examples:

- violence
- frightening/intense scenes
- profanity
- adult themes
- family suitability

### Audience Expectation

Examples:

- revenge story
- coming-of-age
- political drama
- survival story
- mystery investigation
- philosophical sci-fi

### Audience Confidence

Examples:

- strong vote-backed signal
- limited rating confidence
- mixed source signal

### Access Friction

Examples:

- streaming available
- rent/buy only
- no stored availability

### Series Status

Examples:

- completed
- ongoing
- upcoming season
- active release

## 11. Mapping Principles

Rules:

- A keyword can support a signal, but should not become a strong claim alone.
- Missing keyword does not mean the trait is absent.
- Prefer conservative labels.
- Avoid hype:
  - masterpiece
  - must-watch
  - critically acclaimed
  - audiences love it
- Avoid critic claims unless critic source exists.
- Avoid review-consensus claims unless review-derived source signals exist.
- Keep provenance:
  - `source_name`
  - `source_version`
  - `generated_from`
  - `confidence`
  - `last_updated_at`
- Prefer `omit weak signal` over `overclaim`.
- Keep spoiler safety.
- Do not expose raw provider payloads in frontend.

Implementation guidance:

- Use source tags as evidence, not final product copy.
- Map source tags into internal dimensions through a conservative rules/config layer.
- Keep weak or noisy source tags out of frontend display.
- Let Insight Summary consume curated source signals, not raw provider tags.

## 12. Proposed Source Signal API Shape

Recommended frontend-friendly but source-aware shape:

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
          "confidence": "low",
          "sources": ["tmdb_keywords"]
        }
      ],
      "intensity": {
        "value": "high",
        "confidence": "medium",
        "sources": ["certification", "genres", "tmdb_keywords"]
      }
    },
    "decision_signals": {
      "watch_commitment": {
        "value": "long movie",
        "confidence": "high",
        "sources": ["runtime"]
      },
      "audience_confidence": {
        "value": "strong vote-backed signal",
        "confidence": "high",
        "sources": ["tmdb_rating", "imdb_rating"]
      },
      "access_friction": {
        "value": "streaming available",
        "confidence": "high",
        "sources": ["availability"]
      }
    },
    "generated_from": ["metadata", "ratings", "availability", "tmdb_keywords"]
  }
}
```

How this should be used:

- frontend can show compact Watch Profile chips
- Insight Summary can consume the same `source_signals`
- raw source tags should remain backend/internal unless selected for display
- source provenance should remain available for debugging and future explainability

## 13. TMDb Keywords Preview — Next Implementation Requirements

Next script:

```text
analytics/scripts/build_tmdb_keywords_preview.py
```

Input:

- local catalog content IDs
- stored TMDb external IDs
- content type movie/series
- optional target file support

Behavior:

- fetch movie keywords for movie content
- fetch TV keywords for series content
- dry-run/preview only
- no DB writes
- no frontend changes
- no schema changes
- save preview JSON
- save run report

Preview output:

```text
analytics/processed/tmdb_keywords/tmdb_keywords_preview.json
```

Run report:

```text
analytics/processed/tmdb_keywords/run_reports/tmdb_keywords_report.json
```

Report should include:

- total local titles checked
- titles with TMDb IDs
- titles without TMDb IDs
- successful fetches
- failed fetches
- titles with zero keywords
- total keywords fetched
- unique keywords
- top repeated keywords
- movie coverage
- series coverage
- sample keyword rows
- possible useful keywords
- noisy/common keywords
- errors by status code
- no DB changes confirmation

Data shape:

```json
{
  "content_id": 1,
  "title": "Dune",
  "content_type": "movie",
  "tmdb_id": "438631",
  "keywords": [
    {
      "keyword_id": 4565,
      "keyword_name": "dystopia"
    }
  ],
  "fetched_at": "..."
}
```

## 14. Future Implementation Sequence

Recommended order:

1. Create this research findings doc.
2. Implement TMDb keywords preview.
3. Assess keyword coverage/usefulness.
4. Decide schema for imported keywords/source tags.
5. Import TMDb keywords.
6. Implement structured Source Signals v1 from:
   - metadata
   - ratings
   - availability
   - certification
   - series lifecycle
   - TMDb keywords
7. Add Watch Profile UI.
8. Improve Insight Summary from `source_signals`.
9. Later inspect MovieLens/MPST for taxonomy/modeling.
10. Later create review-text policy.
11. Later explore TMDb review-derived signals.
12. Later LLM-assisted summaries only from approved stored signals.

## 15. Implementation Guardrails

Guardrails:

- no scraping
- no raw review text
- no user names from review datasets
- no unsupported claims
- no critic/audience split without critic source
- no LLM-generated conclusions before `source_signals` exist
- no ambiguous source matching without review
- no direct product use of non-commercial datasets unless terms allow
- every generated signal should be explainable from stored source data

Product language guardrails:

- do not say `masterpiece`
- do not say `must-watch`
- do not say `critically acclaimed`
- do not say `audiences love it`
- do not imply review consensus without review-derived signals
- do not imply critic consensus without critic sources

## 16. Open Questions

Open questions:

- Should TMDb keywords be stored in a normalized table or provider payload JSON?
- Should keyword-to-signal mapping be config-driven?
- Should keywords display directly or only through derived signals?
- How should confidence be calculated when TMDb provides no relevance score?
- Should we track keyword freshness per content?
- Can Dataverse CC0 Tag Genome variant be safely used directly?
- Should MovieLens/MPST only inform taxonomy, or can they seed initial mappings?
- What is the minimum coverage threshold to justify building Watch Profile UI?
- What is the final commercial licensing path for TMDb/IMDb?
