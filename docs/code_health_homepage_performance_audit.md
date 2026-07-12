# Code Health and Homepage Performance Audit

Date: 2026-07-12
Branch: `code-health-homepage-performance-audit`

## Summary

The homepage reload issue is not caused by client-side `useEffect` fetching or a duplicate browser call to `/content/home`. The homepage route is a Server Component that fetches `/content/home` on the server and renders behind a `Suspense` boundary.

The visible loading state on hard reload is expected with the current architecture because all API requests use `cache: "no-store"`. Each reload waits for a fresh server-side backend request, so the page can briefly show `Loading InsightStream picks...`.

After clearing `.next`, I did not reproduce `ChunkLoadError` in dev or production mode. The earlier chunk errors are most consistent with stale Next dev chunks, browser cache, or HMR mismatch during active development rather than a production issue.

## Runtime Reproduction

### Dev Mode

Commands used:

```bash
cd frontend
rm -rf .next
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 npm run dev -- -H 127.0.0.1 -p 3001
```

Observed:

- No browser console errors or `ChunkLoadError` after repeated reloads.
- Browser did not call `/content/home` directly.
- Backend received one `/content/home?limit_per_section=8` request per homepage reload.
- At `load`, the page briefly showed `Loading InsightStream picks...`.
- After the server response resolved, the homepage rendered normally.
- Dev server timings observed:
  - First load: `GET / 200 in 1207ms`
  - Repeated reloads: roughly `103ms` to `125ms`

### Production Mode

Commands used:

```bash
cd frontend
rm -rf .next
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 npm run build
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 npm run start -- -H 127.0.0.1 -p 3001
```

Observed:

- Production build succeeded after rerunning outside the sandbox. The first sandboxed build failed with a Turbopack EPERM error while binding a local worker port, which is an environment restriction rather than an app error.
- Route table showed `/` as dynamic server-rendered.
- Production browser reloads did not show console errors or `ChunkLoadError`.
- The loading fallback still appeared briefly at page load, then homepage content rendered normally.
- Direct local HTTP check returned `200` for `/`.

## Root Cause Assessment

| Candidate | Assessment |
| --- | --- |
| Normal `next dev` behavior | Partly. Dev can produce stale chunk/HMR errors during active rebuilds, especially with stale `.next`. |
| Stale `.next` or browser cache | Likely for the reported `ChunkLoadError`, because it did not reproduce after `rm -rf .next`. |
| Client-side homepage fetching | Not the cause. `frontend/app/page.tsx` fetches on the server via `await getHomeContent(...)`. |
| Unnecessary client components | Minor efficiency issue. `HomeContentCard` is a client component only for image fallback state. |
| Inefficient component structure | Not a correctness issue, but the homepage could ship less JS if card rendering becomes server/presentational. |
| Real production chunk issue | Not reproduced. Production build/start did not show chunk errors. |

## Frontend Architecture Findings

| File | Issue | Severity | Suggested action |
| --- | --- | --- | --- |
| `frontend/app/page.tsx` | Homepage is already a Server Component and does not fetch via `useEffect`. | Low | Keep this direction. No immediate refactor needed. |
| `frontend/app/page.tsx` | `Suspense` fallback appears on every hard reload because the homepage fetch is uncached. | Medium | Add route-specific cache/revalidation for homepage data if the loading flash is undesirable. |
| `frontend/lib/api.ts` | `fetchFromApi` applies `cache: "no-store"` to every API call. | Medium | Add an optional cache policy so server-rendered homepage data can use controlled revalidation without changing mutation/detail behavior. |
| `frontend/lib/api.ts` | Server fetches use `NEXT_PUBLIC_API_BASE_URL`; this works locally but mixes browser/public and server concerns. | Low | Consider separate `API_BASE_URL` for server-side calls and `NEXT_PUBLIC_API_BASE_URL` for browser-side calls. |
| `frontend/components/HomeContentCard.tsx` | Whole card is a client component for `useState` image fallback only. | Medium | Later split image fallback into a tiny client component, or accept static fallback behavior to make cards server-renderable. |
| `frontend/components/HomeBucketSection.tsx` | Client component is appropriate for tab state. | Low | Keep as-is. |
| `frontend/types/content.ts` | `HomeContentCard` keeps `decision_reason` and `chips` even though homepage no longer renders them. | Low | Keep for API contract and future use. Do not remove. |
| `frontend/lib/types.ts` | Tracked empty file. | Low | Safe cleanup candidate, but remove only after confirming no tooling expects it. |

## Backend Homepage API Findings

| Area | Finding | Severity | Suggested action |
| --- | --- | --- | --- |
| Candidate pools | Homepage uses bounded pools via `home_candidate_pool_size`, capped at 100. | Low | Keep. This is the right shape for 1,000+ titles. |
| Rotation | No `ORDER BY RANDOM()` found. Rotation happens deterministically after bounded candidate queries. | Low | Keep. |
| Poster safety | Homepage candidates require non-empty `poster_url`. | Low | Keep. |
| Enrichment | Platform and signal enrichment are batched after candidate selection. | Low | Keep. No obvious N+1 issue for cards. |
| Query cost | Each homepage section repeats the rating summary subquery join. | Medium | Fine for current data. Revisit with 1,000+ titles if timings rise. |
| Mood/platform buckets | Multiple section and bucket queries are expected. | Low | Keep bounded pool limits. |
| Indexes | Existing indexes cover content type, dates, platforms, ratings, and source signal dimensions/content IDs. | Low | No schema or index change recommended in this audit. |

Local timing samples against the running FastAPI app:

```text
/content/home?limit_per_section=6   200   0.056230s
/content/home?limit_per_section=10  200   0.063751s
/content/top-rated?limit=10         200   0.007965s
/content/recent?limit=10            200   0.004138s
```

## Bundle and Build Health

Frontend checks:

```text
npm run typecheck  passed
npm run build      passed outside sandbox
npm run lint       not available in package.json
analyze script     not available in package.json
```

Build output:

- Next.js `16.2.7` with Turbopack.
- `/` is dynamic server-rendered.
- No TypeScript errors.
- No Next.js warnings in the successful build output.
- The sandboxed build failed with a Turbopack worker permission error (`Operation not permitted` while binding a port). This did not reproduce outside the sandbox.

Backend checks:

```text
python3 -m pytest tests/test_content_read_endpoints.py
70 passed, 6 skipped

python3 -m pytest
365 passed, 6 skipped, 1 LibreSSL warning
```

## Dead Code and Cleanup Candidates

| Cleanup candidate | Why it may be unused | Risk | Recommended action |
| --- | --- | --- | --- |
| `frontend/lib/types.ts` | File is tracked but empty. | Low | Remove in a small cleanup PR if no tooling references it. |
| `getRecentContent` and `getTopRatedContent` in `frontend/lib/api.ts` | Homepage no longer uses them. | Medium | Keep for now. Existing endpoints remain public and future pages may use them. |
| `HomeContentCard` client boundary | Only needed for image `onError` state. | Medium | Refactor later, not in this audit. |
| `frontend/tsconfig.tsbuildinfo` | Generated locally by typecheck/build and ignored by `.gitignore`. | Low | Do not commit. No action needed. |
| Homepage `decision_reason` and `chips` type fields | Backend returns them but cards do not display them. | Low | Keep for API compatibility and future UI use. |

## Recommended Next Task

Make the homepage server fetch cache policy explicit.

Suggested shape:

1. Keep `frontend/app/page.tsx` as a Server Component.
2. Keep `HomeBucketSection` as the client-only interactive piece.
3. Add an optional fetch policy to `fetchFromApi`, for example `cache?: RequestCache` and `next?: NextFetchRequestConfig`.
4. Use a homepage-specific policy in `getHomeContent`, such as short revalidation or daily-aware revalidation.
5. Keep user-specific and mutation-related requests uncached.
6. Consider a separate server-only `API_BASE_URL` for server fetches.

This should reduce the reload loading flash without changing backend API behavior.

## Remaining Risks

- The in-app browser did not expose reliable `performance.getEntriesByType("resource")` entries during these checks, so backend logs and server/browser console results were used for request-count evidence.
- Production behavior was verified locally, but a real deployment can still differ if frontend and backend base URLs, proxy caching, or CDN settings differ.
- The homepage endpoint is healthy for the current catalog. At 1,000+ titles, watch repeated rating summary join cost and consider materialization or cached summaries only if measured timings justify it.

## Low-Risk Fixes Applied

No runtime code changes were applied. This audit only adds this report.
