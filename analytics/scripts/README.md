# Analytics Scripts

Run public commands from the repository root with `python3 -m`. Commands resolve
configuration, raw-cache, processed-output, backend and environment paths from
`analytics.scripts.common.paths`; they do not depend on the current working
directory.

## Package Structure

- `audits/`: read-only catalog, ingestion and product-quality reports.
- `refresh/`: database-driven refresh planning and scoped execution.
- `ingestion/`: provider previews, local dataset matching and controlled imports.
- `source_signals/`: keyword-to-signal preview, normalization and import.
- `providers/tmdb/`: reusable TMDb response normalization; not a public CLI.
- `common/`: provider-independent repository path helpers.

Generated files remain under `analytics/raw/` and `analytics/processed/`, which
are local/ignored artifact directories. Import commands are dry-run by default
unless the table below states a different write flag. Provider commands require
locally configured credentials and must never print or persist them.

## Public Command Inventory

For each row below, the former command was
`python3 analytics/scripts/<Original file>`; the canonical replacement is the
listed package-module command. All listed commands were executed with `--help`
from the repository root during this refactor.

| Original file | Canonical command | Purpose | Effect | DB | TMDb/external | Default output |
|---|---|---|---|---|---|---|
| `analyze_tmdb_metadata_gap.py` | `python3 -m analytics.scripts.audits.analyze_tmdb_metadata_gap` | Compare seed metadata with the TMDb preview | Read-only | No | No | `analytics/processed/tmdb/` report |
| `audit_catalog_expansion_readiness.py` | `python3 -m analytics.scripts.audits.audit_catalog_expansion_readiness` | Catalog baseline and expansion-readiness audit | Read-only | Read | No | `analytics/processed/catalog_audits/` |
| `audit_decision_display_quality.py` | `python3 -m analytics.scripts.audits.audit_decision_display_quality` | Product-facing decision-display QA | Read-only | Read | No | `analytics/processed/source_signals/` |
| `audit_source_signal_mapping_quality.py` | `python3 -m analytics.scripts.audits.audit_source_signal_mapping_quality` | Stored source-signal mapping QA | Read-only | Read | No | `analytics/processed/source_signals/` |
| `check_ingestion_health.py` | `python3 -m analytics.scripts.audits.check_ingestion_health` | Catalog ingestion-health checks | Read-only | Read | No | `analytics/processed/tmdb/run_reports/` |
| `reconcile_basic_metadata.py` | `python3 -m analytics.scripts.audits.reconcile_basic_metadata` | Compare seed and processed basic metadata | Read-only | No | No | `analytics/processed/tmdb/` report |
| `build_content_refresh_plan.py` | `python3 -m analytics.scripts.refresh.build_content_refresh_plan` | Build a shared due-work plan | Read-only | Read | No | `analytics/processed/tmdb/content_refresh_plan.json` |
| `plan_series_refresh.py` | `python3 -m analytics.scripts.refresh.plan_series_refresh` | Plan legacy-compatible series refresh targets | Read-only | Read | No | `analytics/config/series_refresh_targets.json`, run report |
| `run_content_refresh.py` | `python3 -m analytics.scripts.refresh.run_content_refresh` | Plan/dry-run/apply scoped metadata and video refreshes | Mutates with `--apply` | Read/write | Yes unless plan-only | Refresh previews and run report under `analytics/processed/tmdb/` |
| `refresh_content_videos.py` | `python3 -m analytics.scripts.refresh.refresh_content_videos` | Videos-only convenience entry point | Mutates with `--apply` | Read/write | Yes | Same as shared refresh runner |
| `build_tmdb_credits_preview.py` | `python3 -m analytics.scripts.ingestion.build_tmdb_credits_preview` | Build credits preview from cached TMDb responses | Artifact write | No | No | `analytics/processed/tmdb/credits_preview.json` |
| `build_tmdb_keywords_preview.py` | `python3 -m analytics.scripts.ingestion.build_tmdb_keywords_preview` | Fetch/preview TMDb keywords | Artifact write | Read | Yes | `analytics/processed/tmdb_keywords/` |
| `fetch_tmdb_availability_certification.py` | `python3 -m analytics.scripts.ingestion.fetch_tmdb_availability_certification` | Fetch availability and certification preview | Artifact write | No | Yes | `analytics/raw/tmdb/`, `analytics/processed/tmdb/` |
| `fetch_tmdb_person_details.py` | `python3 -m analytics.scripts.ingestion.fetch_tmdb_person_details` | Fetch person-detail preview | Artifact write | Read | Yes | `analytics/processed/tmdb/person_details_preview.json` |
| `fetch_tmdb_sample.py` | `python3 -m analytics.scripts.ingestion.fetch_tmdb_sample` | Fetch/reuse TMDb title details and appended videos | Artifact write | No | Yes | `analytics/raw/tmdb/`, `analytics/processed/tmdb/` |
| `import_availability_certification_from_preview.py` | `python3 -m analytics.scripts.ingestion.import_availability_certification_from_preview` | Import reviewed availability/certification preview | Mutates with `--apply` | Read/write | No | Console/run result; reads processed preview |
| `import_content_metadata_from_preview.py` | `python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview` | Import normalized title and series metadata | Mutates with `--apply` | Read/write | No | Console/run result; reads processed preview |
| `import_content_ratings_from_preview.py` | `python3 -m analytics.scripts.ingestion.import_content_ratings_from_preview` | Import TMDb ratings from title preview | Mutates with `--apply` | Read/write | No | Console/run result; reads processed preview |
| `import_content_videos_from_preview.py` | `python3 -m analytics.scripts.ingestion.import_content_videos_from_preview` | Import normalized video snapshots and primary choices | Mutates with `--apply` | Read/write | No | Console/run result; reads processed preview |
| `import_imdb_ratings.py` | `python3 -m analytics.scripts.ingestion.import_imdb_ratings` | Import local IMDb ratings TSV | Mutates with `--apply` | Read/write | No | Console/run result |
| `import_letterboxd_ratings_from_preview.py` | `python3 -m analytics.scripts.ingestion.import_letterboxd_ratings_from_preview` | Import reviewed Letterboxd matches | Mutates with `--apply` | Read/write | No | Console/run result |
| `import_people_credits_from_preview.py` | `python3 -m analytics.scripts.ingestion.import_people_credits_from_preview` | Import people and connected credits | Mutates with `--apply` | Read/write | No | Console/run result |
| `import_person_details_from_preview.py` | `python3 -m analytics.scripts.ingestion.import_person_details_from_preview` | Import optional person profile metadata | Mutates with `--apply` | Read/write | No | Console/run result |
| `import_tmdb_keywords_from_preview.py` | `python3 -m analytics.scripts.ingestion.import_tmdb_keywords_from_preview` | Import normalized provider keywords | Mutates with `--apply` | Read/write | No | `analytics/processed/tmdb_keywords/` import report |
| `merge_ingestion_candidates.py` | `python3 -m analytics.scripts.ingestion.merge_ingestion_candidates` | Merge validated candidates into target config | Mutates file with `--apply` | No | No | `analytics/config/content_ingestion_targets.json` |
| `merge_tmdb_keywords_retry_preview.py` | `python3 -m analytics.scripts.ingestion.merge_tmdb_keywords_retry_preview` | Merge successful keyword retry artifacts | Artifact write | No | No | `analytics/processed/tmdb_keywords/` |
| `preview_letterboxd_ratings_match.py` | `python3 -m analytics.scripts.ingestion.preview_letterboxd_ratings_match` | Match local titles to a local Letterboxd dataset | Artifact write | Read | No | `analytics/processed/letterboxd/` |
| `update_posters_from_tmdb_preview.py` | `python3 -m analytics.scripts.ingestion.update_posters_from_tmdb_preview` | Controlled poster/backdrop backfill | Mutates with `--apply` | Read/write | No | Console/run result |
| `validate_ingestion_candidates.py` | `python3 -m analytics.scripts.ingestion.validate_ingestion_candidates` | Validate proposed TMDb ingestion targets | Artifact write | No | Yes | `analytics/processed/tmdb/` validation report |
| `build_keyword_signal_preview.py` | `python3 -m analytics.scripts.source_signals.build_keyword_signal_preview` | Apply curated keyword-to-signal mappings | Artifact write | Read | No | `analytics/processed/source_signals/` |
| `build_unmapped_keyword_review.py` | `python3 -m analytics.scripts.source_signals.build_unmapped_keyword_review` | Validate curated decisions and build a deterministic review of high-impact keywords; accepts `--baseline-mapping-file` for before/after status | Artifact write | Read-only transaction | No | `analytics/processed/source_signal_reviews/` |
| `import_source_signals_from_preview.py` | `python3 -m analytics.scripts.source_signals.import_source_signals_from_preview` | Import reviewed source signals and guidance | Mutates with `--write` | Read/write | No | `analytics/processed/source_signals/` import report |

## Implementation Modules

| Original file | New module | Responsibility | Decision |
|---|---|---|---|
| `content_refresh_planner.py` | `analytics.scripts.refresh.content_refresh_planner` | Shared database-driven refresh cadence and selection | Moved; imported by refresh CLIs and catalog audit |
| `content_refresh_executor.py` | `analytics.scripts.refresh.content_refresh_executor` | Per-title scoped refresh execution | Moved; imported by refresh runner |
| `source_signal_keyword_normalization.py` | `analytics.scripts.source_signals.source_signal_keyword_normalization` | Canonical mapping-key normalization | Moved; shared by preview and audits |
| `tmdb_video_metadata.py` | `analytics.scripts.providers.tmdb.tmdb_video_metadata` | Normalize TMDb videos and rank primary media | Moved; imported by fetcher/importer/refresh executor |

## Removed Placeholders

| Removed file | Evidence | Replacement |
|---|---|---|
| `data_cleaning.py` | Zero bytes; no imports, tests, docs, CLI, shell or CI references | None; no behavior existed |
| `normalization.py` | Zero bytes; no imports, tests, CLI, shell or CI references | Purpose-specific normalization lives in `source_signals/source_signal_keyword_normalization.py` |

Git history preserves both placeholders. No non-empty or uncertain legacy script
was removed.

## Source-Signal Mapping Ownership

- `analytics/config/source_signal_keyword_mapping.json` is the runtime source of truth used by preview and import code.
- `analytics/config/source_signal_keyword_review_decisions.json` is the tracked human-curation record. It stores rationale, confidence, intended action, exact proposed mappings, and the supported runtime mapping version. The review CLI fails when these decisions drift from runtime configuration.
- `analytics/processed/source_signal_reviews/source_signal_unmapped_keyword_review.json` is a generated, ignored report combining database frequency/title samples with runtime status and curated decisions. It is not a configuration input.

The review command opens PostgreSQL in an explicit read-only transaction. To compare a candidate with a retained baseline configuration, run:

```bash
python3 -m analytics.scripts.source_signals.build_unmapped_keyword_review \
  --baseline-mapping-file /path/to/baseline-source-signal-mapping.json
```

Without a baseline file, before-state fields are reported as not evaluated rather than inferred. Semantic decisions remain human-authored; the script only validates and renders them.
