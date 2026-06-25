# Insight Summary Foundation Plan

## 1. Purpose

Insight Summary Foundation defines a deterministic summary layer for content detail pages. Its job is to help users quickly understand what a title is, why it may be worth considering, and what structured decision signals matter.

The summary should help users understand:

- what the title is
- why it may be worth watching
- who it is best suited for
- what decision signals matter
- whether movie or series status affects the watch decision
- where ratings and availability fit into the decision

This is not a replacement for:

- reviews
- AI verdicts
- critic summaries
- user opinions
- personalized recommendations

The v1 goal is decision support using structured data already stored in InsightStream.

## 2. Product Positioning

The Insight Summary should be:

- factual
- source-aware
- compact
- explainable
- generated from stored metadata
- careful with unsupported claims

For v1, language should stay neutral. The summary should not say phrases such as "critically acclaimed", "audiences love it", "masterpiece", or "must-watch" unless those claims are explicitly supported by available ratings, review data, and product rules.

Good v1 tone:

- "A high-rated historical drama available to rent or buy, led by Christopher Nolan and a major ensemble cast."
- "An ongoing workplace drama-comedy with a strong TMDb audience rating and multiple released seasons."

Avoid exaggerated marketing language. The summary should explain signals, not sell the title.

## 3. V1 Data Inputs

V1 can use structured fields already available through the local backend:

- content title
- content type
- release year
- original language
- runtime
- genres
- overview
- cast
- crew
- director or creator
- availability
- age rating or certification
- ratings
- InsightStream Score
- rating source count
- vote count and rating confidence
- movie or series type
- series status
- released seasons count
- announced or upcoming season information
- next episode date
- last aired date

V1 should not rely on external live calls or frontend provider APIs. All inputs should come from local database-backed backend responses.

## 4. V1 Summary Output Contract

Recommended response shape:

```json
{
  "insight_summary": {
    "headline": "High-rated historical drama with a major ensemble cast.",
    "summary": "A 2023 historical drama from Christopher Nolan, supported by a strong TMDb audience rating and availability across rent/buy platforms.",
    "best_for": [
      "Historical drama viewers",
      "Christopher Nolan fans",
      "Long-form biographical films"
    ],
    "key_signals": [
      {
        "label": "Rating",
        "value": "80/100 InsightStream Score from TMDb audience rating"
      },
      {
        "label": "Availability",
        "value": "Available to rent or buy in India"
      },
      {
        "label": "Runtime",
        "value": "Long movie"
      }
    ],
    "watch_note": "Best suited for viewers comfortable with a long, dialogue-heavy historical drama.",
    "generated_from": [
      "metadata",
      "ratings",
      "availability",
      "credits"
    ],
    "confidence": "medium"
  }
}
```

Recommended empty-state shape:

```json
{
  "insight_summary": {
    "headline": null,
    "summary": null,
    "best_for": [],
    "key_signals": [],
    "watch_note": null,
    "generated_from": [],
    "confidence": "low"
  }
}
```

Recommended v1 approach:

- compute the summary dynamically in the backend at API time
- do not create a new database table yet
- add storage later only if AI-generated, editorial, or manually curated summaries are introduced

Dynamic generation keeps v1 simple, testable, and aligned with the current metadata foundation.

## 5. Rule-Based Generation Strategy

V1 should be deterministic and rule-based.

### Rating Rule

If `unified_score` exists:

- `80+` -> "high-rated"
- `70-79` -> "well-rated"
- `60-69` -> "mixed-to-positive rating signal"
- below `60` -> avoid promotional wording and say "moderate rating signal"

If no unified score exists, do not mention rating strength. Source ratings may still appear in the Ratings card, but the Insight Summary should not overstate confidence.

### Availability Rule

If streaming availability exists, mention streaming availability.

If only rent or buy availability exists, mention rent/buy availability.

If no availability exists, do not imply where it can be watched.

Availability wording must preserve region context. US availability should not be described as India availability.

### Series Rule

For ongoing series:

- mention ongoing status
- mention released seasons if available
- mention announced or upcoming season only if available

For ended series:

- mention completed status
- mention released seasons if available

For upcoming series:

- mention upcoming status carefully
- avoid implying released episodes or seasons

### Crew Rule

For movies, prefer director if available.

For series, prefer creator or key showrunner-like creator data if available.

If crew data is missing, avoid crew claims.

### Genre Rule

Use the top 1-3 genres to describe the title. Avoid long genre dumps.

Examples:

- "historical drama"
- "sci-fi thriller"
- "animated superhero series"

### Runtime Rule

For movies, if runtime is greater than 150 minutes, mention "long movie" only as a watch consideration, not as criticism.

For series, do not use runtime unless reliable episode runtime is available.

## 6. Suggested Summary Blocks

Recommended v1 frontend blocks:

1. Headline
2. Short summary paragraph
3. Best for chips
4. Key signals list
5. Watch note

Example visual structure:

```text
Insight Summary

High-rated historical drama with a major ensemble cast.

A 2023 historical drama from Christopher Nolan, supported by a strong TMDb audience rating and rent/buy availability in India.

Best for:
Historical drama viewers · Christopher Nolan fans · Long-form biographical films

Key signals:
Rating: 80/100 InsightStream Score
Availability: Rent/buy in India
Runtime: Long movie

Watch note:
Best suited for viewers comfortable with a long, dialogue-heavy historical drama.
```

Keep this card compact. It should not become visually heavier than Cast & Crew, Ratings, or Availability.

## 7. Movie Examples

### Oppenheimer

Headline:

```text
High-rated historical drama with a major ensemble cast.
```

Summary:

```text
A 2023 historical drama from Christopher Nolan, supported by a strong TMDb audience rating and rent/buy availability where available in the selected region.
```

Best for:

- Historical drama viewers
- Christopher Nolan fans
- Viewers comfortable with long, dialogue-heavy films

Key signals:

- Rating: InsightStream Score when vote confidence is sufficient
- Availability: streaming, rent, or buy only if rows exist
- Runtime: long movie if runtime is above 150 minutes

### The Dark Knight

Headline:

```text
High-rated superhero crime drama from Christopher Nolan.
```

Summary:

```text
A superhero crime drama with a strong audience rating signal, major cast visibility, and availability shown only from local platform data.
```

Best for:

- Superhero films
- Crime drama viewers
- Christopher Nolan fans

### Lower-Data Movie Example

Headline:

```text
Movie metadata available, but decision signals are limited.
```

Summary:

```text
This title has basic metadata available. Ratings, availability, or key crew data may be missing, so the summary remains minimal.
```

This prevents v1 from inventing confidence when only sparse metadata exists.

## 8. Series Examples

### The Bear

Headline:

```text
Ongoing workplace drama-comedy with released seasons available.
```

Summary:

```text
An ongoing workplace drama-comedy with season information, cast data, and rating signals shown when enough vote confidence exists.
```

Series signals:

- status: ongoing if stored
- released seasons: show count if available
- next season or episode: mention only if stored

### INVINCIBLE

Headline:

```text
Ongoing animated superhero series with released seasons.
```

Summary:

```text
An animated superhero series with local cast, availability, and series lifecycle metadata. Upcoming season details should appear only when stored in series metadata.
```

### Slow Horses

Headline:

```text
Ongoing spy drama with multiple released seasons.
```

Summary:

```text
A spy drama series with released-season metadata and platform availability shown from local region-aware availability rows.
```

### FROM

Headline:

```text
Ongoing mystery-horror series with recent activity signals.
```

Summary:

```text
A mystery-horror series where lifecycle and latest activity dates help users understand whether the show is still active.
```

### Ended Series Example

Headline:

```text
Completed series with available season metadata.
```

Summary:

```text
A completed series where released seasons and last aired date help users understand that the story is no longer actively airing.
```

Ended series wording should avoid upcoming-season language unless stored metadata contradicts the status and a warning has been reviewed.

## 9. Confidence Model

Recommended internal confidence levels:

High confidence:

- overview exists
- genres exist
- rating exists with enough votes
- availability exists
- cast or crew exists

Medium confidence:

- most metadata exists, but ratings or availability are missing

Low confidence:

- only basic metadata exists

Confidence should not be shown prominently to users in v1 unless there is a design reason. It is useful for backend tests, debugging, and deciding how minimal the summary should be.

Low-confidence summaries should be shorter and avoid evaluative language.

## 10. Backend API Plan

Recommended implementation:

- create a backend function such as `build_insight_summary(content_detail)`
- call it inside the content detail endpoint after metadata, ratings, availability, credits, and series metadata are loaded
- return `insight_summary` in the content detail response
- keep the logic deterministic and testable

No database storage is recommended in v1. The summary can be computed from existing response data.

Storage can be added later if the product introduces:

- AI-generated summaries
- editorial summaries
- manual overrides
- cached expensive summaries

## 11. Frontend Plan

Update the existing Insight Summary card.

If summary exists, show:

- headline
- short paragraph
- best-for chips
- key signals
- watch note if available

If summary does not exist, keep a clean empty state:

```text
Not enough structured data to generate a summary yet.
```

The design should stay aligned with:

- dark layout
- Ratings card
- Availability card
- Cast & Crew section

## 12. Tests

Suggested backend tests:

- summary generated for a movie with rich metadata
- summary generated for an ongoing series
- summary generated for an ended series
- summary handles no rating
- summary handles no availability
- summary handles no crew
- summary does not invent unsupported claims
- summary returns stable empty or low-confidence shape for sparse content

Suggested frontend tests or build checks:

- summary card renders headline and paragraph
- best-for chips render when present
- key signals render when present
- empty state renders when no summary exists

Avoid brittle exact-text tests where possible. Prefer asserting:

- fields exist
- unsupported phrases do not appear
- `best_for` length is reasonable
- `key_signals` contain expected labels when source data exists

## 13. Risks and Guardrails

Risks:

- summaries may sound like opinions if wording is too strong
- sparse metadata can produce weak summaries
- ratings alone can create overconfident claims
- review or critic claims could appear before review data exists
- LLM-style wording could imply unsupported judgment

Guardrails:

- only use stored data
- use neutral language
- include only signals that exist
- do not infer unavailable facts
- do not call providers from the frontend
- do not introduce LLM generation in v1
- keep review-summary work as a separate future layer

## 14. Future Enhancements

Possible future phases:

- v2: add IMDb and stronger rating confidence
- v3: review-summary layer after legal/source-approved reviews exist
- v4: AI-assisted summaries using controlled prompts and stored source facts
- v5: personalized summaries based on user preferences or watch history
- v6: critic vs audience comparison

These are not part of v1.

## 15. Recommended Next Implementation Task

Recommended next task:

```text
Implement deterministic Insight Summary v1
```

Suggested scope:

- add backend summary builder
- add `insight_summary` field to the content detail API
- generate summary dynamically from existing metadata
- update frontend Insight Summary card
- add backend tests
- run frontend build
- do not add a database schema change in v1
