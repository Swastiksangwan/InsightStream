# INSIGHTSTREAM — MILESTONE 2B: VERIFIED CATALOG DIAGNOSTICS & REFRESH LIFECYCLE AUDIT

Observation: **November 5, 2026, 19:51:54 Asia/Kolkata / 14:21:54 UTC**.
All before/after selection comparisons use that same frozen instant. Repository
baseline: `1de4232959ec3332698cb8317a818f8832e615d9`. Implementation branch:
`fix/catalog-readiness-diagnostics`.

Evidence labels used throughout: **Fact** = observed database, local artifact or
implemented code; **Inference** = supported explanation; **Heuristic** = existing
quality rule rather than established error; **Unknown** = unavailable evidence.
Completeness, valid identifiers and matching confidence do not prove correctness.

## A. Executive summary

The catalog remains **200 titles: 109 movies and 91 series**, with complete core
text/image/genre coverage under the existing stored-field checks. Development
uses PostgreSQL 18.3, 28 application tables and an already registered version-0
`live` baseline. No managed migration is pending or recorded as applied.

The catalog audit had a real contract defect: it supplied series metadata fields
without `has_series_metadata`, although the planner explicitly requires that
existence flag. It consequently called all 91 series missing/due. The corrected
audit selects **36 ongoing series**, exactly matching the actual runner's ID set;
52 ended and three cancelled series are excluded by the existing policy. The
historical estimate of approximately 18 due series is not a current result.

All **200 video states are due** under existing lifecycle cadences. The previous
refresh-readiness result nevertheless passed because it counted failures alone.
The audit now reports historical operational success separately from source age,
due work, retry eligibility and structural expansion readiness. The current
refresh result is **warning**, with zero failed/incomplete video states, rather
than an invented failure threshold. No cadence or production selection rule was
changed. Evidence: `audit_catalog_expansion_readiness._video_health`, `_readiness`,
`content_refresh_planner.CONTENT_PAGE_QUERY` and the private before/after reports.

The important unresolved problems concern refresh execution and ingestion:

| Priority | Finding | Classification / evidence |
| --- | --- | --- |
| P1 | Due refreshes may reuse indefinitely old compatible cache files unless `--refresh` is supplied | Fact: `fetch_tmdb_sample.fetch_or_reuse_json`; no TTL |
| P1 | An unchanged series import does not advance `last_refreshed_at`; a changed cached import advances it to import time | Fact: metadata importer `ensure_series_metadata` / `update_series_metadata`; this is change time, not reliable collection time |
| P1 | Availability and certifications are insert/skip, with no source snapshot reconciliation | Fact: availability importer `process_availability_rows` / `process_certification_rows` |
| P1 | Metadata/video refresh does not refresh aggregate ratings | Fact: executor invokes metadata and video importers only |
| P1 | IMDb and Letterboxd source-as-of dates and publication rights are not established by local file possession | Unknown source dates; provider restrictions discussed in H |
| P2 | Some diagnostic quality rules are broad heuristics, not proof of bad source mappings | Fact: existing scores/rules; 48 runtime-rejected identity candidates require review, not automatic remapping |

The corrected audit is trustworthy for the measured catalog, existing policy and
explicitly separated states. It is **not a certification of provider freshness,
real-world availability, title identity, video playability or expansion safety**.
Maintain the 200-title catalog while stabilizing the existing refresh loop and
availability lifecycle. No new ingestion architecture is needed to do that.

## B. Actual architecture and source-of-truth boundaries

```text
TMDb title details + external IDs + credits (+ aggregate TV credits)
    -> local raw JSON/cache metadata -> normalized previews
    -> separate metadata / ratings / credits / poster importers
TMDb watch/providers + release_dates/content_ratings
    -> regional availability/certification preview -> insert/skip importer
TMDb keywords -> keyword preview -> provider_keywords/content_keywords
    -> reviewed mapping + title overrides -> signal/guidance preview + QA
    -> atomic source-signal import -> stored signals/guidance + durable run row
Local IMDb TSV -> exact stored IMDb-ID lookup -> separate aggregate-rating importer
Local Letterboxd JSONL -> title/year/director matching -> reviewed preview
    -> separate movie-only aggregate-rating importer

PostgreSQL content + identities + source ratings + credits + availability
    + signals/guidance -> backend content/person services -> FastAPI -> Next.js
Stored signals -> runtime Decision Insight Formatter v2.0.2 -> public display copy

DB series/video state -> shared planner -> plan JSON -> explicit refresh runner
    -> one shared details+videos request/cache per title
    -> independent series-metadata and video import transactions
```

Source code, not old documentation, establishes these paths. Canonical command
inventory: [analytics scripts](../analytics/scripts/README.md). Relevant modules:
[refresh executor](../analytics/scripts/refresh/content_refresh_executor.py),
[planner](../analytics/scripts/refresh/content_refresh_planner.py),
[metadata importer](../analytics/scripts/ingestion/import_content_metadata_from_preview.py),
[video importer](../analytics/scripts/ingestion/import_content_videos_from_preview.py),
[signal importer](../analytics/scripts/source_signals/import_source_signals_from_preview.py),
[content service](../backend/app/services/content_service.py).

The database is the source of truth for stored application state. Reviewed
configuration owns keyword mappings and curated overrides. A preview proves
normalization/matching occurred, not that its contents were imported. Cache
metadata records local collection provenance; a filesystem modification date is
not a provider snapshot date. `content.updated_at` and people/credit timestamps
are write times, not comprehensive refresh state. Runtime formatter output, rather
than stored `watch_feel` or legacy `frontend_ready`, owns public decision copy.

There is no repository scheduler, queue or periodic worker. Execution is manually
invoked; planner eligibility is automated only when a command runs. External
machine-level scheduling is **NOT VERIFIED**. Movie/series/people refresh is not
one universal pipeline. Availability, ratings, people and keyword imports remain
separate workflows.

## C. Corrected diagnostic defects and regression coverage

All executable changes are confined to the catalog audit. The shared production
planner, runner, importers, mappings, APIs, frontend and schema are unchanged.

| Fix | Root cause and before behavior | Corrected behavior | Regression evidence |
| --- | --- | --- | --- |
| Series existence contract | `_video_health` omitted `has_series_metadata`; every series took the missing-row branch | Explicit `is not None` existence flag matches the SQL planner contract; present-but-null fields remain distinct from absent rows | Five lifecycle statuses, absent/empty/null records, 7-day boundaries and post-air refresh tests |
| Historical success versus freshness | `_readiness` passed whenever failed/incomplete count was zero, even with overdue work | Independent `fetch_history`, `source_freshness`, `operational_health`; due/unknown work warns | Old success and valid empty, fresh empty, never attempted, invalid timestamps and mixed ages |
| Retry labels | Raw `last_fetch_retryable` counted retry-eligible even at the automatic ceiling; incomplete rows could disappear from manual-review counts | Compatibility counts use actual planner disposition, with due/waiting/manual states separate | Failures 1/2/3, exact 1-/2-day boundaries, nonretryable failure and retryable-marked incomplete state |
| Canonical refresh identity | Audit could count a legacy-only `content.tmdb_id` as runnable although the runner INNER JOIN requires `external_ids.tmdb` | Missing canonical identities are separately ineligible; source-age assessment remains independent | Movie and series fixtures retaining a legacy ID but lacking canonical identity |
| Past next-episode observation | Previously only reversed episode order or future dates on ended series appeared in lifecycle warnings | Past next-episode dates are explicit dated review observations; selection policy remains unchanged | Yesterday/today/tomorrow boundaries |
| Ambiguous expansion label | A structural gate could be read as operational approval | Existing structural threshold retained, with explicit `catalog_structure_only` scope and limitations | Existing readiness assertions retained; scope asserted |

Audit output is version **1.1**; the version assertion was updated accordingly.
There are **45 additional deterministic test cases**. Existing assertions remain,
including planner parity, SQL read-only contracts and strict-mode behavior. No
catalog count is hardcoded into unit tests. Tests live in
[test_catalog_expansion_readiness_audit.py](../backend/tests/test_catalog_expansion_readiness_audit.py).

The existing operational threshold is unchanged: no failed/incomplete states
passes that dimension; a nonzero count below `max(3, catalog_size * 0.1)` warns;
at/above it fails. A freshness backlog alone only warns and does not make strict
mode fail. Existing recommendation/mapping scores and numeric thresholds were
neither invented nor retuned.

## D. Verified catalog health

Counts below come from read-only SQL and the existing audit loaders. The private
`domain_metrics.json` and `diagnostic_queries.json` contain the results and exact
reproduction queries. SQL examples appear in the appendix.

| Domain / field | Present | Eligible | Coverage | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Title, original title, synopsis, release date/year consistency, poster, backdrop, valid-format original language, status | 200 each | 200 | 100% each | Stored-field completeness, not source accuracy or URL availability |
| Positive movie runtime | 109 | 109 movies | 100% | Series runtime is not required; 18 series happen to have a positive value |
| Genres / cast / keywords / active signals / stored guidance | 200 each | 200 | 100% each | A relationship or signal exists; richness varies |
| Canonical TMDb / IMDb identifiers | 200 each | 200 | 100% each | Valid format; all 200 cached TMDb external-ID payloads agree with stored IMDb IDs |
| TMDb ratings and vote counts | 200 | 200 | 100% | Aggregate only; imported June 25–July 29 |
| IMDb ratings and vote counts | 150 | 200 | 75% | 80/109 movies; 70/91 series |
| Letterboxd ratings | 79 | 109 movies | 72.48% | Zero stored vote counts; series unsupported by current importer |
| Any regional availability | 198 | 200 | 99% | Historical offers; current service availability unverified |
| India / US availability | 181 / 198 | 200 each | 90.5% / 99% | Region-specific coverage; no durable successful-empty state |
| Any certification | 197 | 200 | 98.5% | 129 India and 194 US title records; absence may be upstream-unavailable |
| Videos / selected primary video | 199 each | 200 | 99.5% | One valid successful-empty fetch; no live playability check |
| Series lifecycle row / season and episode counters | 91 each | 91 series | 100% | Title-level counters, not season/episode entities |
| Series creators | 80 | 91 series | 87.91% | All 109 movies have directors; missing creator is not proof of importer failure |
| Person profile image | 2,620 | 3,212 people | 81.57% | 592 missing |
| Person biography / birthday / birthplace | 1,860 / 1,798 / 1,838 | 3,212 each | 57.91% / 55.98% / 57.22% | Upstream availability versus uncollected fields cannot be separated from current state |
| Individual provider reviews | NOT IMPLEMENTED | — | — | Ratings, keywords and generated insights are not reviews |

Entity totals: **429 current source-rating records, 2,515 availability offers,
323 certifications, 3,505 videos, 199 primaries, 200 video states, 3,212 people,
4,165 title-person relationships, 19 genres, 582 genre relationships, 1,910
provider keywords, 3,463 title-keyword relationships, 2,023 active signals,
200 guidance rows and nine durable signal-import runs**. Legacy seeded ratings,
summary and platform tables are compatibility data, not additional provider
review or rating coverage. Evidence: snapshot table counts and domain queries.

No normalized external-ID collision, stored/cached IMDb mismatch, legacy/canonical
TMDb disagreement or cross-title primary-video relationship was found. The
schema matches the accepted live signature. These checks do not establish every
real-world title match or semantic claim as correct.

### Actionable title examples

| Internal ID / title | Verified observation | Classification / action |
| --- | --- | --- |
| 3319 — Evil Dead Burn | IMDb ID `tt31170389` absent from current local TSV; no IN/US offers | No invented rating. Cached watch-provider payload has CA data, not IN/US; this is region absence, not universal provider absence |
| 3948 — Main Vaapas Aaunga | No IN/US offers; cached provider `results` is empty | Cached empty evidence, source date unknown; not current-world unavailability |
| 3962 — Paatal Lok | No stored video or primary; fetch state is successful empty | Valid collected empty, not failed ingestion |
| 3316 — Bacurau; 3942 — 13th; 3949 — Central Station | No stored regional certifications | Upstream availability/collection reason unknown; do not fabricate values |
| 3946 — Bāhubali: The Beginning; 3949 — Central Station | Runtime display audit flags weak primary-identity provenance | Heuristic review candidates; do not silently rewrite mappings |
| 193 — Silo; 203 — Ted Lasso; 208 — Slow Horses; 209 — Reacher; 3334 — Lupin | Past next-episode dates can contribute a post-air refresh reason | Existing event rule, plus dated audit observation |

There are six past next-episode dates overall and seven stored next-episode dates;
one is future. Sixteen series have announced-season flags. Eleven series lack
creator relationships: Band of Brothers (109), Cowboy Bebop (157), Death Note
(158), Attack on Titan (159), Planet Earth (163), Our Planet (164), Slow Horses
(208), Obi-Wan Kenobi (213), INVINCIBLE (214), The Vietnam War (3338), The World at
War (3339). Provider credit structures may legitimately differ.

All 200 titles produce backend decision-display objects. The existing display
audit calls 198 display-ready and two review-required; it separately flags 48
titles with rejected source-identity candidates, producing 50 combined review
candidates. These are not 50 broken detail pages. Existing mapping QA calls 184
mapping-ready and 16 review-required. Its 101 missing display-pace observations
differ from 92 missing stored pacing signals because display selection is a
different contract. No new quality score was introduced here.

The expansion audit still flags 106 titles under its existing low-keyword-mapping
heuristic. That does not prove 106 ingestion failures. For example, the mapping
audit's proposed space-survival label for Das Boot is a broad context heuristic,
not authoritative taxonomy. Review such suggestions manually. All stored
`content_watch_guidance.frontend_ready` flags are false, yet runtime display exists
for 200 titles; that legacy flag is not the current public formatter contract.

## E. Exact refresh-selection rules and observed results

### Series metadata

Authoritative rules: [plan_series_refresh.evaluate_refresh_status](../analytics/scripts/refresh/plan_series_refresh.py),
wrapped by `content_refresh_planner.evaluate_series_refresh`.

1. Explicit all/forced selection overrides normal eligibility.
2. Missing metadata row or null last-refresh timestamp selects the title before
   inactive-status exclusions.
3. Ended/cancelled titles with a timestamp are skipped by default. Legacy
   `--include-ended` permits their stale checks. Shared explicit targeting or
   `--include-not-due` can override normal series exclusion.
4. Ongoing/upcoming/unknown titles are stale when the timestamp is **strictly
   older than seven days**; exactly seven days does not satisfy that test.
5. A stored next-episode date within today through 14 days ahead selects even
   when otherwise fresh. A passed next-episode date selects when the last refresh
   date is before that episode date. A same-day/post-air refresh suppresses that
   reason; weekly staleness can still select the title.
6. Stale titles with last-episode or latest-activity dates within 60 days also
   select. Season/episode counts, announced-season counts and `in_production`
   do not independently trigger series selection. There is no persisted series
   attempt/failure/backoff state.

TMDb Returning Series/In Production normalize to ongoing; Planned/Pilot to
upcoming; Ended to ended; Canceled/Cancelled to cancelled; unrecognized provider
statuses to unknown. Actual current state is 36 ongoing, 52 ended, three cancelled.
**36 selected / 55 intentionally skipped / zero genuinely missing metadata**.
Ended/cancelled titles cannot discover a return or correction without an explicit
check: an intentional current policy with a maintenance gap, not a new bug fix.

Repeated next-episode-window selection can make successive invocations refetch
unchanged titles. Unknown raw status strings bypassing normalization may lack an
age-only rule. Neither policy was silently changed. `due_at` is a planning hint;
it does not override an inactive exclusion or prove source collection occurred.

### Videos

Authoritative rules: `content_refresh_planner.evaluate_video_refresh` and
`_video_lifecycle`. Defaults are movie/series independent unless stated below.

| Disposition | Current rule |
| --- | --- |
| No fetch status | Immediately selected, high priority |
| Incomplete normalization | Manual normalization review; not automatically selected |
| Failed, nonretryable or at least three consecutive failed runs | Manual review |
| Retryable failure 1 / 2 | Retry due at last attempt + one / two days; equality is due; high priority |
| Release within next 90 days | One-day cadence; high priority |
| Released within last 30 days | Two-day cadence; high priority |
| Series with active/unknown status and next episode within 21 days, or ongoing recent activity within 45 days | Two-day cadence; high priority |
| Announced future season | Seven-day cadence; normal priority |
| Other older title | Thirty-day cadence; low priority |
| Successful empty | Uses the same lifecycle cadence, not a permanent skip or a failure |
| Explicit forced target | Can override review/exclusion; requires operator judgment |

`last_fetched_at` is the successful source timestamp; `last_attempted_at` anchors
failure backoff. No `next_retry_at` column exists: it is calculated. Last-success
source age is assessed independently of the latest failed attempt. The automatic
ceiling is three failed **runs**, separate from retries within each HTTP request.

Current results: **199 latest nonempty successes + one valid empty; 200 recorded
successful fetches; zero never-attempted, failed, incomplete, retry-waiting,
retry-due or manual-review states; zero within cadence; 200 due**. Source-fetch
timestamps range July 17–August 2. Video reasons are 184 older-title, 15 announced
season and one currently-airing. A combined plan has 200 unique titles, not 236
requests: the 36 series/video overlaps share details requests. Combined priorities
are 36 high and 164 low; videos-only priorities are one high, 15 normal and 184 low.

## F. Per-domain ingestion and refresh coverage matrix

Paths abbreviated below are actual files under `analytics/scripts/ingestion/`
unless prefixed `refresh/` or `source_signals/`. All import operations discussed
are implemented capabilities, **not commands executed by this milestone**.
Counts reference D and the private SQL results. No cadence is inferred where no
selector exists; age without an established policy is not automatically failure.

| Domain / eligible types | Fetch / normalize / import entry points | Existing selection and cadence | Current evidence and gaps | Update / reconciliation semantics | Risk and recommended change |
| --- | --- | --- | --- | --- | --- |
| 1. Core movies | `fetch_tmdb_sample` -> mapping preview -> `import_content_metadata_from_preview` | Config/manual; no periodic movie metadata scope | 109 core-complete; write dates through July 29; source age not durably tracked | Existing core fields mainly fill-only; latest activity updateable; genre links additive | P1: define explicit safe refresh fields for upcoming/recent movies; release/runtime/image corrections are not comprehensive today |
| 2. Core series | Same fetcher/importer; shared executor builds a limited series preview | Weekly/event selector for lifecycle, not full core refresh | 91 core-complete; core writes through August 2 | Series status is refreshable; title/overview/language generally preserved; shared preview has no full genre set | P1: distinguish lifecycle refresh from complete metadata refresh |
| 3. Series counters/lifecycle | `refresh/build_content_refresh_plan` -> `run_content_refresh` -> metadata importer | Seven-day/event rules in E | 91 rows; 36 due; 55 excluded; six past next dates; last change June 23–August 2 | Replace changed lifecycle fields; stamp only when values change; no success-attempt ledger | P1: fix no-change/source-time semantics and record failure outcomes |
| 4. Videos/primary | Appended details -> `tmdb_video_metadata.normalize_video_snapshot` -> `import_content_videos_from_preview` | Actual 1/2/7/30-day selector, with bounded failure retries | 3,505 rows; 199 primary; 200 due; July 17–August 2 source timestamps | Complete authoritative snapshots reconcile source-scoped obsolete videos and primary; failed/incomplete input preserves prior valid state | P1: require fresh-enough source evidence for due work; retain current safe reconciliation |
| 5. TMDb ratings | Details `vote_average/vote_count` -> `import_content_ratings_from_preview` | Separate manual import, no rating eligibility selector | 200/200; June 25–July 29 preview timestamps; no recent rating attempts | Upsert source row when values/payload differ; unchanged values do not advance fetched timestamp; no source-removal lifecycle | P1: explicit ratings refresh action and collection time distinct from change time |
| 6. IMDb ratings | Local TSV -> `import_imdb_ratings` exact ID scan | Dataset-triggered/manual, no automatic cadence | 150/200 stored; 49 recoverable; one absent; June 27 import timestamp | Upsert changed rows; identical repeated data unchanged; duplicate TSV IDs overwrite in the scan dictionary rather than reporting conflict | P1: approve source manifest/rights, review proposed backfill; preserve source-as-of and hash |
| 7. Letterboxd movie ratings | `preview_letterboxd_ratings_match` -> reviewed preview -> `import_letterboxd_ratings_from_preview` | Manual, movies only | 79/109 stored; 95 high-confidence current matches, 92 rating-bearing; no supported vote count/review storage | Changed source row upsert; default skips ambiguous/unmatched; optional explicit ambiguous import; URL/payload identity rather than external_ids row | P1: permission and durable identity decisions before additional imports |
| 8. Availability, movies/series | `fetch_tmdb_availability_certification` -> same-domain preview -> availability importer | Manual targets, IN/US; no planner | 2,515 offers/198 titles; June 19–July 29 database insertion timestamps; zero durable failure/empty state | Insert new keys, skip existing; do not refresh existing priority/timestamps or remove disappeared offers | P1: reviewed per-source/per-region authoritative reconciliation design in G |
| 9. Certifications, movies/series | Same fetcher uses release_dates/content_ratings | Manual; no planner | 323 rows/197 titles, IN 129/US 194; same insertion-time range | Insert/skip; conflicting certificate preserved with warning; legacy age rating fill-only | P2: preserve provenance and approved correction/reconciliation policy; null rating_system weakens SQL unique semantics |
| 10. People/cast/crew | Title credits/aggregate credits -> `build_tmdb_credits_preview` -> `import_people_credits_from_preview` | Config/manual; no periodic selector | 3,212 people, 4,165 relationships; 200 cast-bearing titles; 11 series without creators | Source-person ID matching; new relationships append; profiles/departments fill missing only; no deletion/update of existing credit snapshot | P2: source-scoped credit refresh and concurrency-safe identity constraints after review |
| 11. Person enrichment | `fetch_tmdb_person_details` -> person preview -> `import_person_details_from_preview` | Missing-only/targeted/all; not time-based | Biography 1,860, profile 2,620; current writes through July 29; latest retained fetch report July 15 | Fill empty biography/profile/birthday/birthplace; conflicting existing data preserved | P2: track successful-unavailable versus never collected; avoid endless retries of intentionally absent biographies/dates |
| 12. Posters/backdrops | Details -> metadata fill or `update_posters_from_tmdb_preview` | Manual; no planner | 200 each; no URL/playability check | Generic importer fills; dedicated updater can replace reviewed image URLs by TMDb/type/title match | P2: event-driven correction using existing dedicated updater, not blind full overwrites |
| 13. Genres | Details -> metadata normalizer / genre map -> metadata importer | Manual metadata workflow | 19 genres / 582 links / 200 titles; no domain fetch time | Add normalized genres and links; no removal | P2: explicit replacement policy before presenting genre membership as a current full snapshot |
| 14. Keywords | `build_tmdb_keywords_preview` -> `import_tmdb_keywords_from_preview` | Manual selected catalog; retry artifacts; no age planner | 1,910 terms / 3,463 links / 200 titles; fetched June 30–July 29 | Upsert labels/provenance/last-seen; no removal of provider-deleted keywords; successful empty preview does not clear existing links | P1: add authoritative snapshot semantics before relying on recomputation to remove upstream-deleted concepts |
| 15. Source signals | `build_keyword_signal_preview` + mapping/override QA -> `import_source_signals_from_preview` | Manual recomputation on input/config changes | 2,023 active/200 titles; all tied to durable run 9, July 29; mapping v2.9 | Planned upsert/removal of obsolete selected-title signals; partial/unsafe plans gated; one transaction with run provenance | P2: preserve this system; recompute only after approved upstream/mapping changes; source freshness remains inherited |
| 16. Guidance/runtime insights | Same preview/import; backend runtime formatter | Guidance recomputation manual; display computed on read | 200 guidance; 200 runtime display; 198 display-ready by existing heuristic | Guidance upsert with last run; public sentence planned at runtime; no review-derived inference or provider fetch | P2: validate display after upstream changes; do not use legacy frontend_ready as a runtime availability test |

Common importers are dry-run by default; source-signal writes use `--write` rather
than `--apply`. Dry-run fetch commands can still make provider requests and change
raw caches; **only plan-only mode is request-free**. They were not run here.

## G. Streaming availability investigation and later design

The collector requests one watch-provider payload and one certification payload
per title, then filters regions IN and US. `flatrate` becomes streaming; buy,
rent, ads and free remain distinct stored types. Platform identity is primarily
normalized provider **name**, not a durable provider-ID identity. The current
offer key is `(content_id, platform_id, availability_type, region_code, source_name)`.
Name changes can therefore split provider identity. Source provider IDs and
priorities are stored but existing keys are skipped without refreshing them.

IN has 714 offers and US 1,801. Their types are respectively streaming 284/501,
rent 249/591, buy 169/631, ads 7/35 and free 5/43. Stored rows do not expire.
Disappeared offers can remain visible indefinitely. An empty preview adds nothing
and clears nothing. Fetch failures and malformed regional payloads have no durable
state; normalizer warnings/empty lists do not establish an authoritative complete
snapshot. A future deletion loop cannot safely be bolted onto today's row list.
Evidence: availability collector `normalize_availability` and importer
`process_availability_rows`, which has `ON CONFLICT ... DO NOTHING` and no DELETE.

Proposed independently reviewed design, **not implemented**:

1. Emit a validated envelope per title/source/region: provider/type identity,
   source fetch time, attempt time, complete/partial/failed status, explicit empty
   status, source response identity/hash and normalization diagnostics. Missing
   region in an otherwise validated complete provider response must have defined
   empty semantics; failed/malformed input must never be treated as empty.
2. Persist one fetch-state row per title/source/region, separate from offer rows.
   This needs an additive managed migration, separately reviewed with M2A backup,
   preview and approval gates. Preserve attempt/success/change times separately.
3. Under a per-target lock, validate the whole snapshot before mutation. In one
   transaction upsert desired keys/priority/provider ID, remove only disappeared
   keys for that exact title/source/region, and record successful state. Never
   delete another region, legacy row, source or title.
4. A complete valid empty snapshot removes only that region/source's old offers
   and records successful empty. Failure/partial input preserves prior offers and
   last-success time while recording retry/review state. Certification lifecycle
   is a separate decision, not implicitly deleted with offers.
5. Report insert/update/remove/unchanged/state-only changes before apply. Repeated
   identical input must converge without duplicate rows or false source freshness.
   Source time remains unchanged when an old cache is reused.
6. Commit each title/source/region atomically; retain run identity and completion
   checkpoint so interrupted batches resume only incomplete work. Retain prior
   valid data after item failure. No global queue is necessary for this catalog.
7. Integration tests: disappeared/unchanged/new offers, validated empty, missing
   results, malformed rows, provider rename, partial region success, cross-region
   and source isolation, repeated input, rollback and interrupted-batch recovery.

Backend details choose IN offers, then US only if IN has none, then legacy
platforms (`content_service.get_detail_platforms`). Thus **17 titles use US
fallback**; two have no modern offers. `PlatformList` renders region labels but
`buildDiscoverHref` omits region, while discovery defaults to IN. US-only links
can consequently lead to an India-based filter. This is confirmed from source,
not a browser session. No frontend change was made.

TMDb's [watch-provider documentation](https://developer.themoviedb.org/reference/movie-watch-providers)
requires JustWatch attribution and describes regional availability rather than
direct provider deep links. Attribution and deployment permissions need separate
review; no claim of commercial readiness is made.

## H. Ratings and dataset investigation

### IMDb

The existing local 29,464,121-byte TSV was scanned without download or modification:
**1,687,805 rows, 199 matching catalog IDs**. All 200 stored IDs have valid format
and agree with cached TMDb external-ID responses. Of 50 missing source ratings,
**28 movies and 21 series are recoverable**. Evil Dead Burn (`3319`, `tt31170389`)
is absent. Proposed candidates are supplied in `imdb_backfill_candidates.csv`
(all 50 IDs, including the nonrecoverable title); no rating was imported.
Dataset SHA-256: `fddb0dced4cf8961e46e3e5d5fde0295e642466e277445dadddd626724ded999`.

Matching is exact `tconst`, not fuzzy title matching. Normalization multiplies the
0–10 aggregate by ten and stores votes. The parser clamps scores rather than
rejecting every out-of-range input; duplicate TSV IDs overwrite earlier dictionary
entries. Those validation limitations deserve later tests before new snapshots.
`fetched_at` is importer execution time, not dataset publication time, and advances
only when the stored payload/value changes. Neither file mtime nor June 27's import
time proves source freshness. Official TSV fields contain no snapshot date.

**Inference:** the 150 June 27 rating rows and later 200-title catalog are
consistent with ratings not being re-imported for later batches, rather than 50
bad IDs. The local scan directly demonstrates 49 obtainable rows; historical job
execution for every batch is not recorded.

IMDb's [dataset documentation](https://data.imdb.com/non-commercial-datasets/)
describes daily upstream updates, not the age of this local copy. Its
[software-use conditions](https://help.imdb.com/article/imdb/general-information/can-i-use-imdb-data-in-my-software/G5JTRESSHJBBHTGX)
restrict noncommercial data usage and republication. Public/commercial distribution
requires an appropriate permission/licensing decision. The rating TSV supplies
aggregates and votes, not individual reviews.

### Letterboxd

A full offline scan of the existing 847,209-row JSONL found no malformed JSON rows.
It matched current movie title/year/director context, without retaining/exporting
review text or user records. The previous preview covers only 80 movies, generated
June 28: 75 high-confidence, four ambiguous and one unmatched. Stored coverage is
79 movies, including **four recorded ambiguous matches**. No durable separate
approval log proves who approved those four; an explicit ambiguous import option
exists, but historical use of that option is an inference.

| Current 109-movie classification | Matches | Rating-bearing | Missing stored ratings |
| --- | ---: | ---: | ---: |
| High confidence | 95 | 92 | 20: 17 with rating, three without |
| Ambiguous | 10 | 7 | 6: three with rating, three without |
| Unmatched | 4 | 0 | 4 |

High confidence here means unique normalized title/year with director overlap,
not independent confirmed identity. Missing directors permit a lower confidence
path in code, though none occurred in this scan. Nearby-year, director mismatch
and multiple-candidate cases remain ambiguous. The importer has no meaningful
Letterboxd vote-count or individual-review support; it stores URL/match provenance
in rating fields/JSON rather than separate Letterboxd external-ID rows. Series
are outside this importer, not 91 failed movie matches.

The local dataset card labels itself MIT and cites 2025, but neither establishes
the source snapshot date or rights in all underlying content. Letterboxd's
[terms](https://letterboxd.com/legal/terms-of-use/) restrict unauthorized automated
extraction and content export. Its current [API access page](https://letterboxd.com/api-beta/access/)
also excludes several project categories, including recommendation projects,
from new access grants. Do not assume an API approval or the dataset uploader's
license authorizes InsightStream publication. Resolve source permission before
importing additional matches or planning a refresh capability around this source.

### TMDb ratings

All 200 have aggregate ratings/votes, but no rating selection/refresh stage exists
in the shared series/video executor. The separate ratings importer uses preview
generation time rather than per-response source age. All stored rating timestamps
predate this observation; with no current rating cadence or provider calls, the
precise number whose rating values have changed is **NOT VERIFIED**. A proposed
weekly/monthly age policy must not be misrepresented as an existing failed job.
Reuse fresh details to build an explicit ratings preview, then apply a reviewed
rating importer update with source/change timestamps separated.

## I. Reliability, efficiency and scale

| Stage | Current implementation / outcome | Main limitation |
| --- | --- | --- |
| Eligibility/plan | Canonical TMDb join, paged reads (100), pure per-scope decisions, priority then ID order | No scheduler; no plan expiration or revalidation against current due state when reusing a saved plan |
| Fetch/cache | Shared details+videos request; default batch 25/concurrency 3; request signature and source-time sidecar | Compatible caches have no age limit; `--dry-run` may fetch while `--apply` later reuses that cache |
| HTTP retry | Default 15-second connect/read timeout, three retries; 429/500/502/503/504 and network errors; exponential delay plus jitter | Numeric Retry-After only, capped at 30 seconds; long server delays can be truncated; no coordinated global rate limiter |
| Normalize/preview | Domain-specific validation; videos explicitly classify complete, incomplete, failed and empty | Other domains lack equally strong complete-snapshot envelopes; generated files are not durable applied-state proof |
| Validate/apply | Metadata and most rating/credit imports use a whole-preview transaction; shared executor passes one title per domain; videos commit per title | Series and video domains commit independently, permitting partial success; file/run outcomes must be read per domain |
| Reconcile | Videos remove obsolete source-scoped rows only after authoritative successful snapshots; signals plan selected-title replacements | Availability, genres, credits and keywords do not reconcile provider removals |
| Record/retry | Video state preserves success age and failure class/count; signals have nine durable applied run rows | Other domains mostly rely on mutable latest reports; series failures do not have persisted attempts/backoff |
| Next refresh | Video source timestamp; series last changed/imported timestamp | Series unchanged collection remains due; changed cached data may appear recently refreshed without network evidence |

The normal video path handles primary-language preference, original language and
neutral fallback; YouTube is the playable primary site. Valid full snapshots may
change the primary or clear it after disappearance. Partial/malformed snapshots
disable stale deletion and preserve valid prior primary state. Tests cover
reconciliation, empty versus failed input, source timestamp and retry behavior.
Provider removal is different from a video URL becoming unavailable on YouTube;
the latter is **NOT VERIFIED** without a separate capability.

An actual retained August 2 dry-run report records 30 network fetches, followed by
an apply report for the same 30 titles using cached responses. Current video
source timestamps and series update times corroborate that limited execution;
this is not a recent refresh of all 200. The default latest refresh report is a
July 20 **dry run**, not evidence of application. The latest signal report is also
a dry run, whereas database run 9 explicitly records July 29 applied writes.
Latest keyword import report files say `db_write_performed=false` even though
stored keyword provenance reaches July 29. Do not infer the exact apply job from
those overwritten reports. Evidence: `pipeline_evidence.json` and SQL run rows.

For full initial collection the main title fetcher uses approximately three
logical endpoints per movie and four per series (details, external IDs, credits,
plus aggregate TV credits); availability/certifications add two per title and
keywords another one. Person enrichment adds requests per selected person.
Shared series/video refresh alone uses one logical details request per selected
title, with both scopes sharing it. Retries and incompatible cache signatures can
increase actual attempts. Request counts in plans are budgets, not execution logs.

| Catalog size | One details refresh per due title | Worst-case attempts with three HTTP retries | Existing working-memory concern |
| --- | ---: | ---: | --- |
| 200 | 200 if all due; current plan is exactly 200 | Up to 800 for that scope | Catalog audit evaluated in about 0.08 seconds locally, excluding DB load |
| 500 | 500 if all due | Up to 2,000 | Pairwise recommendation-density audit considers up to 249,500 directed pairs |
| 1,000 | 1,000 if all due | Up to 4,000 | Up to 999,000 directed pairs; measure before optimization |

Those are code-derived budgets, not provider throughput measurements or load-test
results. Existing batch/concurrency controls are adequate for deliberate small
runs. Fix cache freshness, reconciliation, provenance and resumability before
raising concurrency. There is no evidence requiring a queue or a rewrite.
The audit's legacy `content_summary` top-rated performance probe is not the live
aggregate-rating API; do not use it as an API performance claim. No production
load test or provider throughput benchmark was run.

## J. Proposed future refresh policy — recommendations, not current behavior

| Data class/domain | Proposed trigger/cadence and priority | Eligibility/retry/cost | Required change |
| --- | --- | --- | --- |
| Series lifecycle | Keep weekly ongoing checks; coalesce next-air-window work to at most one successful fresh collection/day; P1 | Force low-frequency correction checks for ended/cancelled, e.g. quarterly, instead of permanent exclusion | Source-success state plus reviewed policy extension; no silent rule change |
| Movie metadata | Upcoming/recent: weekly or release-date events; old titles: correction/missing-field events, with occasional quarterly audit; P1 | Refresh only approved mutable fields; preserve manual corrections | New movie selector and explicit importer update policy |
| Videos | Keep existing lifecycle cadence initially; P1 | Due work must require fresh-enough cache or a network result; preserve bounded retry/manual review | Fetch-cache policy fix, not a new scheduler |
| TMDb aggregates | Weekly for current/active titles, monthly for older titles; P1 | Reuse an already fresh details response; unchanged ratings still record collection evidence | Explicit rating action/preview and source-success timestamps |
| IMDb | Approved dataset snapshot acquisition, approximately monthly for this local product; P1 | Compare by exact IDs and dataset hash; missing snapshot row is not a failed HTTP retry | Source manifest/rights decision; existing importer reusable after validation improvements |
| Letterboxd | No automatic cadence until permission and data access are resolved; P1 | Human review for uncertain identity; no review or vote-count invention | Provider-permission decision and supported source capability |
| Availability | Daily/weekly depending recent activity and expected usage; monthly for rarely viewed historical titles; P1 | Per source/region validated snapshot; bounded transient retries; preserve previous success after failure | Reconciliation importer plus additive per-region state migration |
| Certifications | On metadata correction/release events, then infrequent audit; P2 | Country/source isolated; no blanket replacement of curated values | Explicit update policy and source evidence |
| Cast/crew | Release/season-change event; old titles on correction or infrequent review; P2 | Deduplicate by stable credit identity; avoid re-fetching all people per title | Source-scoped reconcile and reviewed uniqueness/state |
| Person biography/images | Missing/explicit correction; quarterly retry for uncollected fields, longer or manual retry for successful-unavailable; P2 | Avoid treating permanently absent birth data as a perpetual fetch failure | Successful-empty/unavailable state, not forced fill-only overwrites |
| Posters/backdrops | Missing/correction or release-event review; P2 | Reuse details; preserve reviewed image choices | Existing dedicated updater, no immediate framework change |
| Genres/keywords | With approved metadata/source collection; P1/P2 | Reconcile authoritative provider removals before derived recomputation | Domain importer corrections; do not erase on malformed/empty-unknown input |
| Signals/guidance | Event-driven on mapping, override or upstream keyword/metadata changes; P2 | Offline recomputation, QA and explicit import; validate runtime display afterward | Existing machinery reusable; no periodic provider request needed |
| User watch state | User action only | Never synchronize development users into fixtures or overwrite during catalog imports | No refresh feature needed |

A lightweight consolidated plan may later list independent domain actions and
provenance. It is useful only after those actions have truthful success state and
reconciliation contracts. Do not introduce a universal refresh framework now.

## K. Prioritized, independently testable implementation sequence

| Milestone | Problem / affected code | Dependencies / complexity / schema | Acceptance criteria |
| --- | --- | --- | --- |
| **Next: P1, make the existing refresh loop source-freshness aware** | Cache has no TTL; series no-change does not record success; changed cached input stamps import time. `fetch_tmdb_sample`, `content_refresh_executor`, metadata importer, planner | Small-to-medium, roughly 2–4 engineering days plus review; separate additive source-success/attempt state if required; M2A backup/preview gates | Fresh unchanged collection advances success time without claiming a data change; old cache never advances source freshness; repeated planning suppresses redundant work; failures preserve last success; tests for cache hit/miss, interruption and mixed domain outcomes |
| P1, authoritative availability reconciliation | Append/skip offers can remain indefinitely; collector lacks complete region envelope | Medium, roughly 3–5 days; per-title/source/region state migration; provider attribution and identity review | All G scenarios pass; validated empty only clears its region/source; failed/partial input preserves data; repeated input converges; preview matches apply counts |
| P1, reviewed ratings backfill and refresh provenance | 49 recoverable IMDb gaps; 17 additional rating-bearing high-confidence LB candidates, with rights unresolved; TMDb refresh absent | Small importer/manifest work, 1–3 days excluding permission lead time; permission is an explicit dependency | ID-level approval, known snapshot/hash/as-of, no ambiguous automatic imports; validate votes/scales/duplicates; source/change time separate; no unsupported reviews |
| P1, keyword snapshot lifecycle | Old provider-deleted keywords survive and can regenerate signals | Medium, 2–3 days; compatible source-state design before schema decision | Complete/empty/failure/partial tests, scoped removal, idempotency; recompute selected-title signals only after valid keyword state |
| P2, metadata/credits/person correction policies | Fill-only or append-only imports cannot converge to corrected full snapshots | Medium, staged per domain, 3–5 days total initial work; evaluate constraints/migration independently | Preserve curated values; handle removed credits/genres, successful unavailable person fields and duplicate/concurrent imports; no blanket overwrite |
| P2, focused display/mapping review | Two weak display identities, 48 rejected identity candidates, broad heuristic suggestions | Small curated batches; no schema change assumed | Human rationale recorded; existing mapping/formatter tests preserved; no inferred taxonomy accepted solely from audit score |
| P2, controlled next catalog batch | Expansion amplifies freshness, identity and state gaps | After above P1 acceptance; source rights and request budget reviewed | Current catalog has an owner/runbook for each mutable domain; refresh/reconcile failures are recoverable; deterministic tests independent of live size; inspect IDs before import |

Effort estimates are planning ranges, not commitments. The first task should
precede bulk refreshes/backfills because today an apparently successful rerun can
either stay permanently due or falsely look fresh from reused data. Availability
is the next user-facing correctness priority. Neither low mapping percentages
nor a structural expansion pass justifies increasing the catalog now.

Before expansion, check a further schema limitation: `content.tmdb_id` and
`external_ids(source_name, external_id)` are globally unique across movies and
series, while provider fetch paths distinguish movie/TV ID namespaces. There is
no current collision among these 200 titles. A valid future cross-type collision
needs explicit identity-model/migration review, not a skipped or mismerged title.

## L. Validation, reproducibility and data preservation

| Check | Result |
| --- | --- |
| Main before branching | Clean; fetched origin; main and origin/main both `1de4232` |
| Existing protected baseline | 985 passed / five skipped / one existing warning |
| Focused audit/series/orchestration tests after final fixes | 111 passed / two DB cases deselected in unit-only mode |
| Full protected backend suite after final fixes | **1,030 passed / five skipped**, 27.36 seconds |
| Added deterministic cases | 45 |
| Current diagnostic versus actual runner | Same complete series/video ID sets: 36 and 200 |
| Historical versus current series diagnosis | 91 falsely missing/due -> zero missing, 36 due, 55 policy exclusions |
| Historical versus current refresh readiness | Pass -> warning; underlying success/failure counts unchanged |
| Read-only display/source-signal audits | 200 titles processed by each, no provider requests or writes |
| Python syntax / whitespace / sensitive artifacts | Checked before delivery; no new dependency installed |
| Frontend | No frontend changes; backend API regression suite passed; no browser session or new build required for these audit-only changes |

The two original historical migration cases remain skipped, as before. Three
additional M2A lifecycle cases were deliberately not enabled: this milestone
prohibits migration execution and did not prepare or mutate migration sandboxes.
The previously reported 988/two baseline included those three disposable lifecycle
cases. This run collects 1,035 cases versus the earlier 990, with 45 added tests;
the different skip count is configuration, not lost behavioral assertions.

The existing urllib3/LibreSSL compatibility warning persists. Ruff/Flake8/Pyflakes
are not installed; packages were not added. Syntax parsing and the isolated suite
are the available executable checks. No real provider data requests, downloads,
refresh/import jobs, migration execution or catalog expansion occurred. Only
official provider documentation/terms pages were consulted online.

Development preservation uses the existing `database_snapshot.snapshot` and
`compare_snapshots` in read-only repeatable-read transactions. It compares all
28 application-table counts and deterministic row hashes, canonical schema,
schema-object counts, sequence state, and migration ledger structure/history.
Baseline schema hash: `97d531728d29821a531195da8e89364cc12889d8c65b27cdfbe99d9d0cfa65d1`.
Sequence-state hash: `946295d68229348fd14e8ec1ed9b8526fa04db630495fc4041ccb12ffbbe8895`.
The migration tool's separate public-schema signature remains
`a5aa572999c95e87f4b4f239324c5acf13f29012d01d6d77e55afc78cba729d5` for `public`.
**All six before/after comparison dimensions passed.** The management history
remains one baseline row, with history hash
`40fd7a22cc0be23d0ddeec7bfa2b9d622f3012665e9c4e2729fdc4f1c220e157`
and unchanged management-schema hash
`e9209b54a6394a9df8b735e317c383b90db55f48b06e2516369b7c1c1bd4c069`.
Before/after evidence is supplied privately as `development_integrity.json`.
No user rows or provider review records are included in the report.

Reproduce a dated read-only report from the repository root, choosing a private
output directory outside Git:

```bash
AUDIT_OUTPUT="$HOME/Library/Application Support/InsightStream/catalog-audits/<run>"
mkdir -p "$AUDIT_OUTPUT"
chmod 700 "$AUDIT_OUTPUT"
PGOPTIONS='-c default_transaction_read_only=on' python3 -m analytics.scripts.audits.audit_catalog_expansion_readiness \
  --reference-date '2026-11-05T14:21:54.019420+00:00' \
  --output-json "$AUDIT_OUTPUT/catalog.json" \
  --output-markdown "$AUDIT_OUTPUT/catalog.md" \
  --output-gap-plan "$AUDIT_OUTPUT/gaps.json"
python3 backend/scripts/run_tests.py --unit-only \
  backend/tests/test_catalog_expansion_readiness_audit.py \
  backend/tests/test_series_refresh_planner.py \
  backend/tests/test_content_refresh_orchestration.py -q
python3 backend/scripts/run_tests.py -q -rs
git diff --check
```

The report command loads development settings privately; do not put connection
URLs on the command line. Run diagnostics in a quiet window and compare integrity
before/after if another process could change the catalog concurrently.

## M. Git summary and review deliverables

All work remains uncommitted and unstaged on `fix/catalog-readiness-diagnostics`.
Main remains at `1de4232`; nothing was pushed, merged or rebased.

| File | Change |
| --- | --- |
| `analytics/scripts/audits/audit_catalog_expansion_readiness.py` | Correct planner input/identity eligibility, independent freshness/retry reporting, dated episode warning and scoped readiness; format 1.1 |
| `backend/tests/test_catalog_expansion_readiness_audit.py` | 45 deterministic regressions and retained assertions |
| `docs/catalog_expansion_readiness.md` | Document actual 1.1 fields, unchanged operational thresholds and limits |
| `README.md` | Record subsequently observed version-0 registration and link this current assessment |
| This report | Evidence, full domain assessment, deferred defects and independently testable recovery plan |

Suggested later commit message:
`fix: correct catalog readiness diagnostics and document refresh lifecycle gaps`.

Private review artifacts outside Git: original/corrected catalog JSON and Markdown,
frozen plan, domain metrics and exact query definitions, display/mapping summaries,
pipeline evidence, ratings investigation, complete 200-title `title_diagnostics.csv`,
50-row `imdb_backfill_candidates.csv`, 109-movie Letterboxd match classifications,
integrity comparison and review diff. Raw datasets, credentials, backups and these
generated artifacts are not staged or committed.

## Appendix — important reproducible diagnostic methods

Use a read-only connection with a statement timeout. Do not send database URLs to
stdout. The complete executed query dictionary is supplied privately as
`diagnostic_queries.json`; it includes per-title regional, credit, signal and
rating presence without personal watch-state records.

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '20s';

-- Catalog and actual metadata-row existence, not inferred status.
SELECT c.content_type, count(*) AS titles,
       count(m.content_id) AS metadata_rows
FROM public.content c
LEFT JOIN public.content_series_metadata m ON m.content_id = c.id
GROUP BY c.content_type;

-- Rating rows, usable aggregate value and supported vote counts are distinct.
SELECT s.source_name, c.content_type, count(*) AS rows,
       count(*) FILTER (WHERE r.normalized_score BETWEEN 0 AND 100) AS ratings,
       count(r.vote_count) AS vote_counts,
       min(r.fetched_at), max(r.fetched_at)
FROM public.content_ratings r
JOIN public.rating_sources s ON s.id = r.rating_source_id
JOIN public.content c ON c.id = r.content_id
GROUP BY s.source_name, c.content_type;

-- Video collection state. Source freshness is subsequently evaluated by the
-- actual Python planner at the frozen observation instant, not COUNT(success).
SELECT last_fetch_status, count(*), min(last_fetched_at), max(last_fetched_at),
       count(*) FILTER (WHERE last_fetch_retryable) AS retryable_flag,
       max(consecutive_failure_count),
       count(*) FILTER (WHERE source_snapshot_empty) AS successful_empty
FROM public.content_video_fetch_state GROUP BY last_fetch_status;

-- Availability coverage cannot establish a successful empty result.
SELECT region_code, availability_type, count(*) AS offers,
       count(DISTINCT content_id) AS titles, min(fetched_at), max(fetched_at)
FROM public.content_availability GROUP BY region_code, availability_type;

-- Exact-ID backfill selection; compare these IDs offline with the local TSV.
SELECT c.id, c.title, c.content_type, e.external_id AS imdb_id
FROM public.content c
JOIN public.external_ids e ON e.content_id = c.id AND lower(e.source_name) = 'imdb'
WHERE NOT EXISTS (
  SELECT 1 FROM public.content_ratings r
  JOIN public.rating_sources s ON s.id = r.rating_source_id
  WHERE r.content_id = c.id AND s.source_name = 'imdb'
    AND r.normalized_score IS NOT NULL
)
ORDER BY c.id;

-- Durable applied signal provenance versus a generated/latest dry-run report.
SELECT id, mapping_version, imported_at, preview_generated_at,
       db_write_performed, dry_run, titles_seen, titles_imported
FROM public.source_signal_import_runs ORDER BY id;

-- Actual management state is independently included in integrity fingerprints.
SELECT version, kind, filename, checksum, baseline_id, schema_sha256
FROM insightstream_migrations.history ORDER BY version;
ROLLBACK;
```

For planner parity, execute `content_refresh_planner.CONTENT_PAGE_QUERY` read-only
and call `build_refresh_plan(rows, frozen_time)`. Compare complete ID sets for each
scope with the corrected audit, not just counts. The local IMDb scan reused
`scan_imdb_ratings_file` with the 200 stored IDs; Letterboxd classification reused
`read_letterboxd_dataset` and `match_local_movie` against current local movies.
Neither invoked an importer, provider request or apply path.
