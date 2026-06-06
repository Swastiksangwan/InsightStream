# InsightStream Frontend Integration Plan

## 1. Purpose

This document plans how the Next.js frontend should connect to the existing FastAPI backend.

The goal is to build a clean frontend around the already-working backend APIs instead of randomly creating pages. The backend already provides stable content, discovery, metadata, ratings, summaries, and watch-state read contracts, so the frontend should start by presenting those capabilities clearly.

Current status: partially implemented; frontend MVP loop v1 is connected.

- Homepage v1 completed
- Homepage card polish completed
- Content detail page v1 completed
- Discovery page v1 completed
- Reversible detail-page watch actions completed
- Watch Later page v1 completed
- Watched page v1 completed
- Authentication and deeper polish are still pending

## 2. Current Backend Readiness

The backend already supports:

- content listing
- content details
- top-rated discovery
- recent discovery
- genre discovery
- platform discovery
- combined discovery
- genre metadata
- platform metadata
- watch later
- watched

Current readiness notes:

- canonical sample data contains 15 titles
- backend read endpoint tests have 18 passing pytest tests
- API responses are frontend-friendly
- content list and discovery endpoints use the stable paginated shape with `items`, `total`, `limit`, and `offset`

## 3. Frontend MVP Scope

The frontend MVP should include:

- homepage
- discovery page
- content detail page
- watch later page
- watched page
- reusable cards/components
- loading and error states

The frontend MVP should not include:

- public user reviews
- user posts
- comments
- communities
- social feed
- authentication for now unless added later

## 4. Visual Direction

The desired visual direction is a dark cinematic interface built for entertainment browsing and decision support.

Use:

- dark cinematic interface
- poster-focused entertainment browsing
- clean card grid layout
- horizontal sections for discovery
- large, readable typography
- subtle borders and rounded cards
- dark background with accent highlights
- premium dashboard-like feel
- content detail pages with backdrop image, poster, title, metadata, overview, ratings, and availability

The design can be inspired by modern entertainment discovery platforms, but it should not copy any specific website, logo, brand, images, or exact UI. InsightStream should feel like its own information-first decision platform.

## 5. Recommended First Frontend Pages

### Phase 1: Homepage (Completed)

Purpose: show product value immediately.

Completed status:

- recent content section implemented
- top-rated content section implemented
- polished content cards implemented
- fallback poster UI implemented for placeholder or missing images
- uses the existing `GET /content/recent` and `GET /content/top-rated` backend APIs

Sections:

- recent content
- top-rated content
- maybe platform/genre quick rows later
- optional right-side "Top Picks" or "Highest Rated" panel later

Backend APIs:

- `GET /content/recent`
- `GET /content/top-rated`

UI idea: use poster cards in horizontal or responsive grid sections. Keep it information-first, not social-feed based.

### Phase 2: Discovery Page (v1 Completed)

Purpose: allow search/filter browsing.

Completed v1 status:

- dynamic filters implemented
- uses `GET /content/discover`
- genre filter uses `GET /genres`
- platform filter uses `GET /platforms`
- results render using existing content cards
- cards link to `/content/[id]`
- UI polish can continue later

Features:

- content type filter
- genre filter
- platform filter
- availability type filter
- sort by recent/top-rated
- pagination later if needed

Backend APIs:

- `GET /content/discover`
- `GET /genres`
- `GET /platforms`

UI idea: use filter controls at the top or side and a poster-card grid below.

### Phase 3: Content Detail Page (v1 Completed)

Purpose: show full organized information for one title.

Completed v1 status:

- dynamic `/content/[id]` route implemented
- uses `GET /content/{content_id}/details`
- shows metadata, genres, overview, availability, ratings, unified/critic/audience scores, review summary, pros, cons, and verdict
- supports reversible personal watch actions: add/remove Watch Later and mark/remove Watched
- backend maintains mutual exclusivity between `watch_later` and `watched`
- cast, crew, and person data remain future backend + frontend enhancements

Backend API:

- `GET /content/{content_id}/details`

Sections:

- backdrop hero
- poster
- title and metadata
- overview
- genres
- cast
- crew
- important people connected to the content
- platform availability
- ratings
- unified score
- critic/audience/general scores
- review summary
- pros/cons/verdict
- reversible watch later/watched actions

The desired eventual detail page should include cast, crew, and important person information. The first implementation should only use fields currently available from `GET /content/{content_id}/details`.

Important: do not add public user review sections. If an inspiration design has reviews, replace that area with InsightStream rating summaries and decision-support information.

### Phase 4: Watch Later Page (v1 Completed)

Purpose: show saved watch-later titles for the seeded/demo user.

Completed v1 status:

- uses `GET /watch-later/{user_id}`
- displays saved content cards
- cards link to `/content/[id]`
- uses the temporary demo user until authentication exists

Backend API:

- `GET /watch-later/{user_id}`

Note: use the seeded test user temporarily until authentication exists.

### Phase 5: Watched Page (v1 Completed)

Purpose: show watched titles for the seeded/demo user.

Completed v1 status:

- uses `GET /watched/{user_id}`
- displays watched content cards
- cards link to `/content/[id]`
- uses the temporary demo user until authentication exists

Backend API:

- `GET /watched/{user_id}`

Note: use the seeded test user temporarily until authentication exists.

## 6. API Usage Map

| Frontend Need | Backend Endpoint | Notes |
| --- | --- | --- |
| homepage recent section | `GET /content/recent` | Use a small `limit`, such as 8 or 10. |
| homepage top-rated section | `GET /content/top-rated` | Use for highest-score rows or top-pick panels. |
| browse all content | `GET /content` | Supports `content_type`, `search`, `limit`, and `offset`. |
| discovery filters | `GET /content/discover` | Supports content type, genre, platform, availability type, sort, limit, and offset. |
| genre dropdown | `GET /genres` | Use for dynamic filter options. |
| platform dropdown | `GET /platforms` | Use for platform filter options; can filter by `platform_type`. |
| detail page | `GET /content/{content_id}/details` | Primary source for detail page UI. |
| detail watch actions | `POST /watch-later`, `DELETE /watch-later`, `POST /watched`, `DELETE /watched` | Temporary demo user until authentication exists; backend keeps states mutually exclusive. |
| watch later list | `GET /watch-later/{user_id}` | Use seeded user until authentication exists. |
| watched list | `GET /watched/{user_id}` | Use seeded user until authentication exists. |

## 7. Suggested Frontend Folder Structure

The existing `frontend/` folder already contains `app/`, `components/`, and `lib/` placeholders. A practical Next.js structure could be:

```text
frontend/
  app/
    page.tsx
    discover/page.tsx
    content/[id]/page.tsx
    watch-later/page.tsx
    watched/page.tsx
  components/
    Navbar.tsx
    ContentCard.tsx
    ContentSection.tsx
    DetailHero.tsx
    ScoreBadge.tsx
    SummaryPanel.tsx
    PlatformList.tsx
    RatingList.tsx
    LoadingState.tsx
    ErrorState.tsx
  lib/
    api.ts
    constants.ts
    helpers.ts
  types/
    content.ts
```

Do not create all planned files at once unless the implementation task needs them. Add files gradually as pages are built.

## 8. Frontend API Client Plan

The frontend should use a small API helper file:

```text
frontend/lib/api.ts
```

This helper currently supports homepage, discovery, content detail, watch actions, and saved-list reads. It should continue to:

- use `NEXT_PUBLIC_API_BASE_URL`
- centralize fetch calls
- keep endpoint URLs in one place
- handle common errors
- return typed data

Example environment variable:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Extend this helper gradually as new frontend pages are implemented.

## 9. TypeScript Type Plan

The frontend should define types matching backend responses:

- `Content`
- `PaginatedContentResponse`
- `ContentDetailsResponse`
- `Genre`
- `PlatformMetadata`
- `Rating`
- `Summary`

The current content and details types are implemented and should continue to mirror the backend Pydantic schemas in `backend/app/schemas/content.py` and `backend/app/schemas/user_content.py`.

## 10. UI/UX Direction

Keep the UI:

- clean
- minimal
- information-first
- card-based
- easy to scan
- focused on decision support
- visually cinematic but not cluttered

Avoid:

- noisy social-feed layout
- public post UI
- review forms
- community UI
- user-profile-driven content

## 11. Detail Page MVP Boundary

Cast, crew, and person information are important for the desired content detail page experience. They are not part of the first frontend implementation only because the current backend schema/API does not support them yet. They should be planned as a future backend + frontend enhancement.

Future backend support may require:

- `persons` table
- content-person relationship table
- role fields such as actor, director, writer, creator, and showrunner
- person profile/image fields
- extending the content details API to return cast and crew

For the first InsightStream frontend implementation:

- current detail pages should focus on content metadata, genres, availability, ratings, summary, pros, cons, and verdict
- production house data is future work because the current backend schema/API does not support it yet
- public user reviews are excluded from the MVP
- posts are excluded from the MVP
- comments are excluded from the MVP
- communities are excluded from the MVP
- social feeds are excluded from the MVP

## 12. Demo User Handling

Watch later and watched pages can temporarily use the seeded test user.

Notes:

- this is temporary
- authentication is future work
- frontend should not pretend full auth exists
- demo user handling should be isolated in a constant, not scattered through page code

## 13. Next Recommended Frontend Task

The next recommended coding task is:

Frontend MVP polish pass across:

- homepage
- discovery
- content detail
- Watch Later
- Watched

After visual and interaction polish, future work can move toward frontend integration testing, authentication planning, real image/data ingestion planning, and backend/data/analytics improvements. Public reviews, posts, comments, communities, and social feed features remain outside the MVP.

## 14. Risks / Notes

- Frontend should not depend on hardcoded content IDs where avoidable.
- Backend must be running locally during frontend integration.
- CORS may need to be handled if frontend and backend run on different ports.
- API response shapes should remain stable.
- Frontend should be built incrementally.
- Visual inspiration should guide theme and layout, not product scope.
- Watch later/watched pages use the seeded user only as a temporary demo bridge.

## 15. Final Summary

The frontend should stay built around the current stable backend API contract. Homepage v1, content detail page v1, discovery page v1, reversible detail-page watch actions, Watch Later page v1, and Watched page v1 are now implemented, so the basic frontend MVP loop is connected. Public reviews, posts, and communities remain outside the MVP.
