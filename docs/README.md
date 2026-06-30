# InsightStream Docs Index

This folder contains current product, backend, ingestion, and future-planning documentation for InsightStream / CineLens.

For ingestion work, use `docs/data_ingestion_pipeline.md` as the single source of truth. Older ingestion plans are archived after useful details are merged.

## Active Docs

### Product

- `product_direction.md` - product boundary, audience, and decision-support direction.

### Setup and Testing

- `backend_database_setup.md` - local PostgreSQL setup and schema/sample/index order.
- `backend_testing.md` - backend test scope, database expectations, and test file overview.

### Ingestion

- `data_ingestion_pipeline.md` - canonical guide for metadata, ratings, availability, people, series refresh, health checks, and TMDb keyword preview workflow.

### Ratings and Decision Support

- `ratings_foundation_plan.md` - provider-neutral ratings model and source strategy.
- `insight_summary_foundation_plan.md` - deterministic Insight Summary design and guardrails.

### Source Signals / Future Analysis Layer

- `review_source_signals_foundation_plan.md` - review/source-signal foundation and guardrails.
- `external_data_source_signal_feasibility_plan.md` - source feasibility matrix and recommended source strategy.
- `source_signal_research_findings.md` - implementation-facing source-signal research findings.

### Frontend / Navigation

- `frontend_integration_plan.md` - frontend integration notes and feature direction.
- `metadata_navigation_plan.md` - navigation plan for metadata-driven surfaces.
- `content_recency_sorting_plan.md` - recency sorting behavior and active-series considerations.

### Provider and Metadata Strategy

- `metadata_provider_strategy.md` - provider-neutral metadata strategy.
- `metadata_normalization_plan.md` - normalization rules and metadata consistency notes.
- `analytics_data_collection_plan.md` - analytics/data collection planning.
- `detail_page_data_and_analytics_plan.md` - detail-page analytics/data planning.
- `person_cast_crew_schema_plan.md` - person/cast/crew schema design history that still explains current data model.

## Archived Docs

Archived docs are historical or superseded planning/runbook artifacts kept for traceability. They should not be treated as current implementation guidance.

- `archive/` - older project and database notes.
- `archive/ingestion/` - superseded ingestion plans, runbooks, gap analyses, and import notes.

When an archived doc conflicts with an active doc, follow the active doc.
