# Metadata Navigation Plan

## 1. Purpose

Metadata should become navigable after the core metadata display is stable. Genres, cast, directors, and creators are not just labels on a detail page; they are useful discovery paths that help users move from one title to related titles with similar context.

Clickable genres can turn the detail page into a direct path back into filtered discovery. Clickable people can later support person-centered browsing, such as finding other titles featuring an actor or directed by the same filmmaker.

This belongs after metadata display because navigation should use reliable local IDs, normalized genre values, and provider-neutral person records. It should not be mixed with the ratings/reviews phase, which has separate scoring, source, and summarization concerns.

## 2. Current State

The content detail page currently shows:

- basic content metadata
- genre chips
- cast
- directors or creators
- availability
- ratings and summary fields
- personal Watch Later and Watched actions

Discovery already supports filters through URL query parameters, including genre. The frontend discovery page reads the `genre` search parameter and calls `GET /content/discover`.

The backend currently has:

- `GET /genres`
- `GET /content/discover`
- `GET /content/by-genre/{genre_name}`
- `GET /content/{content_id}/credits`

The database already has normalized genre tables and people/credits tables. The credits API exposes provider-neutral cast/director/creator data for content details.

Current gaps:

- no dedicated genre detail page exists yet
- no person detail page exists yet
- no `GET /people/{person_id}` endpoint exists yet
- no `GET /people/{person_id}/credits` endpoint exists yet
- genre chips and person cards are not clickable yet

## 3. Genre Navigation Plan

User behavior:

- Clicking a genre chip opens related content for that genre.
- The destination should show a filtered content grid.
- The user should be able to continue refining results through the discovery filters.

Possible route options:

- `/genres/[name]`
- `/discover?genre=Sci-Fi`

Recommended MVP:

- Use `/discover?genre=GenreName` first because the discovery page and backend discovery endpoint already support genre filtering.
- Later add a dedicated `/genres/[name]` page only if the product needs richer genre-specific editorial layout, descriptions, or analytics.

Initial display for genre-filtered discovery:

- page context should make the selected genre obvious
- title can remain discovery-oriented, or later become `Genre: Sci-Fi`
- related content should use the existing content card grid
- sort options can remain the current discovery sort controls
- do not add fake analytics, explanations, or recommendations

Backend approach:

- Reuse `GET /content/discover?genre=...` first.
- `GET /content/by-genre/{genre_name}` already exists and can remain useful for direct API reads.
- Add `GET /genres/{name}/content` later only if a clearer public contract is needed.

## 4. Person Navigation Plan

User behavior:

- Clicking a cast, director, or creator person opens that person's page.
- Route:
  - `/people/[id]`

Person page should show:

- name
- profile image
- known_for_department
- biography later if available
- credits grouped by role:
  - Cast appearances
  - Directed titles
  - Created titles
  - Crew titles
- related content cards for those credits

Backend future endpoints:

- `GET /people/{person_id}`
- `GET /people/{person_id}/credits`

The response should remain provider-neutral. It should not expose raw TMDb payloads, raw provider credit shapes, API tokens, or frontend-only provider logic.

Person pages should rely on local `people.id` and normalized relationships in `content_people`. Provider IDs should remain internal identity/provenance data through `person_external_ids`.

## 5. API Plan

### Genre

First pass:

- Reuse `GET /content/discover` with the existing `genre` query parameter.
- Continue using `GET /genres` for filter options and valid local genre names.

Optional later endpoint:

```http
GET /genres/{name}/content
```

This endpoint would be useful only if the frontend needs a dedicated genre page contract separate from general discovery.

### People

Future endpoints:

```http
GET /people/{person_id}
GET /people/{person_id}/credits
```

Suggested `GET /people/{person_id}` response:

```json
{
  "person_id": 1,
  "name": "Christopher Nolan",
  "profile_url": "https://example.com/profile.jpg",
  "known_for_department": "Directing",
  "biography": null
}
```

Suggested `GET /people/{person_id}/credits` response:

```json
{
  "person_id": 1,
  "cast": [],
  "directed": [],
  "created": [],
  "crew": []
}
```

Credit items should use existing content card-compatible fields where possible: `id`, `title`, `type`, `poster`, `year`, and optional role details such as `character_name`, `job`, or `department`.

## 6. Frontend Plan

### Genre

- Keep genre chips visually the same initially.
- Later wrap each chip with `Link` to `/discover?genre=GenreName`.
- Use `URLSearchParams` or equivalent encoding for genre names such as `Sci-Fi`.
- Preserve non-clickable styling until the target route behavior is implemented and verified.
- Keep discovery filters in sync with the URL-selected genre.

### People

- Keep person cards non-clickable for now.
- Later wrap the image/name area with `Link` to `/people/[id]`.
- Add hover and focus states only when the links actually work.
- Keep the same circular profile image and fallback initials behavior.
- Do not overload homepage, discovery cards, or saved pages with person navigation in the first pass.

## 7. Implementation Phases

### Phase A: Genre Chip Links

- Link detail-page genre chips to `/discover?genre=...`.
- Verify URL encoding for names such as `Sci-Fi`.
- Confirm the discovery page preselects the genre and returns filtered content.
- Keep chips non-clickable until this is implemented end to end.

### Phase B: Person Detail Backend Endpoints

- Add `GET /people/{person_id}`.
- Add `GET /people/{person_id}/credits`.
- Query local `people`, `content_people`, and `content` tables.
- Keep responses provider-neutral.

### Phase C: Person Detail Frontend Page

- Add `/people/[id]`.
- Show profile image, name, known department, optional biography, and grouped credits.
- Use existing content cards for related titles.

### Phase D: Clickable Person Cards

- Wrap person cards on the content detail page with links to `/people/[id]`.
- Add clear hover/focus states.
- Keep names non-clickable until the person page and backend endpoints are live.

### Phase E: Dedicated Genre Pages

- Add `/genres/[name]` only if `/discover?genre=...` is not enough.
- Keep the first version simple: title, content grid, and existing sort/filter behavior.

## 8. What Not To Do

- Do not create fake person biographies.
- Do not call TMDb from the frontend.
- Do not expose provider raw payloads.
- Do not expose provider-only IDs as the primary frontend contract.
- Do not mix this with the ratings/scoring phase.
- Do not add public reviews, comments, user profiles, communities, or social feeds.
- Do not make links clickable before the target route and data contract work.
- Do not make genres or people look clickable while they still behave as static metadata.

## 9. Recommended Next Task

Implement genre chip navigation first because the current frontend discovery page and backend discovery endpoint already support genre filtering.

After genre navigation is working, implement the person API and person page flow:

1. Add `GET /people/{person_id}`.
2. Add `GET /people/{person_id}/credits`.
3. Add `/people/[id]` frontend page.
4. Make detail-page person cards clickable.

This keeps metadata navigation incremental: genre navigation can ship with existing infrastructure, while person navigation waits for a proper provider-neutral person API and page.
