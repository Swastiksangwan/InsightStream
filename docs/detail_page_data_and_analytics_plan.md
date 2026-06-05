# Detail Page Data and Analytics Plan

## 1. Purpose

This document defines the future direction of the InsightStream content detail page and the backend, data, and analytics work needed to support it.

The current detail page v1 is a good foundation. It proves that the frontend can consume the existing `GET /content/{content_id}/details` API and present organized decision-support information. The final product experience should go further by making the detail page the main surface where users understand whether a movie or series is worth watching.

## 2. Current Detail Page State

The current frontend already includes:

- dynamic `/content/[id]` page
- `GET /content/{content_id}/details` integration
- title and metadata display
- genres
- overview
- platform availability
- cross-platform ratings
- unified, critic, and audience scores
- review summary
- pros
- cons
- verdict
- fallback poster and backdrop UI for placeholder or missing images

The current backend detail response includes `content`, `genres`, `platforms`, `ratings`, and `summary`. It does not yet include cast, crew, person data, similar titles, real external media assets, or deeper analytics explanations.

## 3. Desired End-State Detail Page

A mature InsightStream detail page should eventually show:

- title identity and core metadata
- poster and backdrop imagery
- content type and richer labels
- genres and tags
- where to watch
- cross-platform ratings
- unified InsightStream score
- critic, audience, and general score breakdown
- review signal summary
- pros, cons, and verdict
- cast and crew
- important people connected to the content
- similar or recommended titles
- analytics insights
- data source transparency where useful

The detail page should remain information-first and decision-support focused. Public user reviews, posts, comments, communities, and social feeds are still excluded from the MVP.

## 4. Rating Source Strategy

Future rating and review sources to consider include:

- IMDb-style general ratings
- Rotten Tomatoes-style critic and audience signals
- Metacritic-style critic scores
- TMDb vote average and popularity data if useful
- platform-specific metadata where legally and technically allowed

Final source selection should depend on API availability, data quality, rate limits, attribution requirements, terms of use, and whether the data can be stored or displayed in the way InsightStream needs.

The product should avoid pretending all sources are equivalent. Some sources may be better for audience signal, some for critic signal, some for popularity, and some only for metadata enrichment.

## 5. Unified Score Strategy

The current `unified_score` is plausible seeded development data. It is useful for testing UI and sorting, but it should not be treated as the final production scoring model.

A future unified score should consider:

- source reliability
- critic score
- audience score
- general score
- rating count and confidence
- recency if needed
- missing data handling

The formula should not be finalized until real data sources and data quality are clearer. A simple weighted average can be useful for early testing, but the final approach should account for source coverage, sparse ratings, and low-confidence data.

## 6. Review Summary Strategy

Review summaries may be generated or stored through several phases:

- curated/manual summaries for seed data
- external review summaries if API and legal access exists
- NLP or sentiment summarization later if legally usable review text is available
- pros and cons extraction later when data quality supports it

InsightStream should summarize review signals without becoming a public review platform. User-submitted public reviews are not part of the MVP.

Any future summarization should be transparent enough that users understand whether a summary is manually curated, generated from allowed external data, or produced by an internal analytics pipeline.

## 7. Content Type and Labeling Improvements

The current backend schema supports only broad `content_type` values:

- `movie`
- `series`

Future labeling may need to represent:

- movie
- series
- anime
- short film
- documentary
- miniseries
- special
- live event later if the product expands

This should be handled carefully. `content_type` may remain a broad database field, while tags, categories, or labels handle finer distinctions. Any schema changes should be planned before implementation and should avoid breaking existing APIs or frontend assumptions.

## 8. Cast, Crew, and Person Data

Cast, crew, and person information are important for the desired content detail page experience.

Future backend support may need:

- `persons` table
- content-person relationship table
- role fields such as actor, director, writer, creator, and showrunner
- character name for actors
- order or priority for cast display
- person image and profile fields
- extending the details API to return cast and crew

The frontend should not fake cast, crew, or person data before backend support exists. The first implementation should continue using only fields returned by the current detail API.

## 9. Analytics Display on Detail Page

Detail-page analytics should be useful without becoming cluttered.

Possible display elements include:

- score cards
- rating source comparison
- critic vs audience difference
- verdict
- watch-worthiness signal
- popularity or trending signal later
- similar titles later
- confidence or limited-data note if needed

The UI should remain easy to scan. The most important information should answer practical user questions: what is it, where can I watch it, how is it rated, what do people generally think, and is it worth watching?

## 10. Backend/API Improvements Needed Later

Possible future backend work includes:

- richer content labels or tags
- real external IDs
- real poster and backdrop URLs
- person, cast, and crew schema
- rating source configuration
- unified score calculation pipeline
- review summary pipeline
- popularity and trending metrics
- recommendation or similar-content endpoint
- source attribution fields
- better image/media table if needed

These are future improvements, not immediate tasks. The current backend should remain stable while the next frontend and analytics steps are planned and implemented incrementally.

## 11. Data Collection and Analytics Pipeline Needs

Future analytics work should include:

- collecting metadata from TMDb or other allowed APIs
- cleaning incoming data
- normalizing ratings to a consistent scale
- calculating unified scores
- generating summaries and verdicts
- storing raw external payloads if useful later
- validating data before inserting it into production tables

Collection and analytics scripts should stay separate from route logic. Backend APIs should serve clean application data, while ingestion and analytics code should gather, clean, transform, and prepare that data.

## 12. Immediate Next Product Decision

After this planning document, the next coding task should be:

Build the discovery page with filters using:

- `GET /content/discover`
- `GET /genres`
- `GET /platforms`

Reason: the detail page v1 exists, but users need a better way to browse, filter, and intentionally reach detail pages. Discovery is the next practical bridge between the current backend API strength and the frontend product experience.

## 13. Final Summary

The detail page should become the main decision-support surface of InsightStream. The current v1 is a strong start, but the final version depends on better backend data, analytics decisions, rating-source strategy, review summarization, richer labels, and cast/crew/person support.
