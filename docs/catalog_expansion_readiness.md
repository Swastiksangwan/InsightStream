# Catalog Expansion Readiness Audit

## Purpose

The catalog expansion audit creates a deterministic baseline before a reviewed
import wave. It measures the current PostgreSQL catalog; it does not select exact
provider titles, call external services, or modify catalog data.

Run it from the repository root:

```bash
python3 -m analytics.scripts.audits.audit_catalog_expansion_readiness
```

Useful scoped runs:

```bash
python3 -m analytics.scripts.audits.audit_catalog_expansion_readiness --content-type movie
python3 -m analytics.scripts.audits.audit_catalog_expansion_readiness --content-type series
python3 -m analytics.scripts.audits.audit_catalog_expansion_readiness --reference-date 2026-07-21
python3 -m analytics.scripts.audits.audit_catalog_expansion_readiness --performance-check --explain
python3 -m analytics.scripts.audits.audit_catalog_expansion_readiness --strict
```

`DATABASE_URL` is read from `backend/.env`/the environment, or can be supplied
with `--database-url`. The database work runs in an explicit read-only
transaction and uses a bounded number of set-based reads. `--strict` still
writes reports, then returns non-zero when a readiness area is `fail`.

## Generated Reports

The defaults are ignored by Git:

- `analytics/processed/catalog_audits/catalog_baseline.json`
- `analytics/processed/catalog_audits/catalog_baseline.md`
- `analytics/processed/catalog_audits/catalog_expansion_gap_plan.json`

JSON contains every per-title audit record. Markdown intentionally keeps only
aggregate tables and a focused high-priority review sample. The gap plan defines
category targets, never invented TMDb IDs or automatic title choices.

## Definitions

Readiness areas are reported independently as `pass`, `warning`, `fail`, or
`not_evaluated`; there is no composite score. Thresholds are written into the
JSON report so a result remains explainable.

Audit format **1.1** also separates video data presence, historical collection,
source freshness and operational retry disposition. `fetch_history` reports the
latest successful/nonempty or valid-empty status and recorded prior successes.
`source_freshness` compares the last successful source timestamp with the existing
video lifecycle cadence; it is independent of failure retry/backoff. Missing or
malformed success timestamps have unknown freshness, never inferred freshness.
`operational_health` uses the planner's retry ceiling and manual-review rules.
The compatibility `retryable_failures` count means automatic-retry eligibility,
not just the raw retryable flag; waiting and due retries are reported separately.

`per_title_refresh` includes both selected and skipped dispositions, metadata-row
existence and the reason for each scope. Movies have no series disposition.
Series-row presence is passed explicitly to the shared planner, even if fields
inside an existing row are null. Runnable targets require the canonical
`external_ids` TMDb row used by the runner, not merely legacy `content.tmdb_id`.
Past next-episode dates are dated review observations; this does not change any
production selection rule or establish that the provider is wrong.

The previous failed/incomplete operational thresholds remain unchanged: zero
failures passes that dimension; fewer than `max(3, titles * 0.1)` warns; at or
above that threshold fails. Due work, unknown freshness or missing canonical
refresh identities adds an overall refresh **warning**, never a new failure
threshold. Historical success alone cannot produce a fresh/readiness pass.
The expansion-area result is explicitly a **catalog-structure gate**. It does not
approve source freshness, reconciliation, permissions or operational expansion.
See the [November 5 lifecycle audit](catalog_diagnostics_refresh_audit_2026_11_05.md)
for measured results and the separate prerequisites for expansion.

Keyword mapping coverage is:

```text
mapped unique keywords / (mapped unique keywords + unmapped unique keywords)
```

Configured ignored/spoiler-unsafe keywords are excluded from that denominator.
Technical duplicate normalization is reported separately and is not counted as
additional mapping success.

Keyword identities use the shared `source-signal-keyword-v1` normalization
contract from `analytics/scripts/source_signals/source_signal_keyword_normalization.py`:
lowercase, replace `&` with `and`, convert hyphen/slash/underscore runs to
spaces, remove remaining punctuation, and collapse whitespace. The JSON report
records both the normalization version and strategy so baselines created under
different contracts are not compared silently.

More Like This readiness is an audit of candidate density, not a recommendation
algorithm. The implementation forms candidate sets in memory after bounded
set-based reads. `ready` currently requires at least eight plausible and four
strong candidates; `limited` requires four plausible candidates. A source title
without genres or at least three useful signals is `insufficient_data`.

The database has no canonical subgenre or production-country field. Subgenre
coverage is therefore labelled as a conservative proxy from active mapped
`audience_expectation`/`topic_theme` signals. Country/region coverage is
`not_evaluated`; original language is never used to infer geography.

## Performance Interpretation

`--performance-check` runs selected bounded reads; `--explain` adds PostgreSQL
plan output. These results are a baseline for the real catalog, not a production
load test. Sequential scans can be reasonable at 150 rows. Repeat the review at
300–400 titles and use separate synthetic-scale testing for larger candidate
sets and user-list growth.

## Safety Boundary

The audit:

- sends no TMDb or other provider requests;
- performs no database writes;
- does not refresh metadata or videos;
- does not import synthetic or real titles;
- writes only ignored local report files.
