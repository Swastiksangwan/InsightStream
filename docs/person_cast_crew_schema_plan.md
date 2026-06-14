# Person, Cast, and Crew Schema Plan

## 1. Purpose

Person, cast, and crew metadata belongs in the metadata foundation phase because it is basic entertainment context that helps users understand what a title is, who made it, and whether it fits their interests.

This data is especially important for the content detail page. Director, creator, cast, character, and crew information can make the detail page more useful without moving into ratings or public social features.

Cast and crew should not be stored as plain text inside the `content` table. A comma-separated field would lose identity, role, order, character names, provider IDs, and future navigation/search value. A normalized person and role model supports:

- detail-page display
- future person search
- future filtering
- future recommendations
- future analytics
- clickable person pages later
- provider replacement

The model should keep TMDb replaceable by storing normalized InsightStream records and provider IDs separately, instead of shaping the app around TMDb response structures.

## 2. Current State

Current content detail pages show:

- basic metadata
- posters and backdrops
- genres
- availability
- ratings and summary fields
- reversible personal Watch Later and Watched actions

The processed TMDb preview contains `top_cast_names` and `director_or_creator_names` for all 15 seeded titles, but those fields are name-only preview data. They are useful for planning, not enough for durable database import.

Current gaps:

- no people table exists
- no person external IDs table exists
- no content-person relationship table exists
- no backend credits response exists
- no frontend cast, crew, director, or creator display exists

The frontend should not fake cast or crew before backend support exists.

## 3. Metadata We Need to Support

People should support:

- name
- profile image URL
- known_for_department
- optional biography later
- provider external IDs
- created_at
- updated_at

Content-person relationships should support:

- content_id
- person_id
- role_type: cast, director, creator, crew
- character_name
- job
- department
- display_order
- source_name
- source_credit_id if available
- created_at
- updated_at

Important modeling rules:

- a person can appear in many content items
- a content item can have many people
- the same person may have multiple roles in the same content
- a person can act in one title and direct or create another
- credits should preserve display order
- person identity should rely on external IDs, not names alone

## 4. Recommended Tables

### people

Recommended fields:

- `id SERIAL PRIMARY KEY`
- `name VARCHAR(255) NOT NULL`
- `profile_url TEXT`
- `known_for_department VARCHAR(100)`
- `biography TEXT`
- `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
- `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`

Notes:

- Do not make `name` globally unique. Multiple people can share the same name.
- Use provider external IDs for identity matching.
- Keep `biography` optional and future-facing so the first implementation can stay small.

### person_external_ids

Recommended fields:

- `id SERIAL PRIMARY KEY`
- `person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE`
- `source_name VARCHAR(50) NOT NULL`
- `external_id VARCHAR(255) NOT NULL`
- `source_url TEXT`
- `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
- `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
- `UNIQUE(person_id, source_name)`
- `UNIQUE(source_name, external_id)`

This mirrors the content `external_ids` model. It can store TMDb person IDs without making application logic TMDb-dependent, and it can later support IMDb person IDs or other provider IDs.

### content_people

Recommended fields:

- `id SERIAL PRIMARY KEY`
- `content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE`
- `person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE`
- `role_type VARCHAR(30) NOT NULL`
- `character_name VARCHAR(255)`
- `job VARCHAR(150)`
- `department VARCHAR(150)`
- `display_order INTEGER`
- `source_name VARCHAR(50)`
- `source_credit_id VARCHAR(255)`
- `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
- `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`

Recommended `role_type` values:

- `cast`
- `director`
- `creator`
- `crew`

Recommended indexes:

- `content_people(content_id)`
- `content_people(person_id)`
- `content_people(role_type)`
- `content_people(content_id, role_type, display_order)`
- `person_external_ids(source_name, external_id)`

Duplicate prevention:

- Avoid duplicate rows for the same content, person, role, character, and job combination.
- A simple SQL `UNIQUE` constraint may be tricky because `character_name` and `job` can be nullable.
- The MVP can start with careful upsert/import logic and review reports.
- Later, add expression indexes or stricter constraints if duplicate behavior becomes clear.

## 5. Movie vs Series Differences

Movies and series should share the same normalized tables, but their source fields differ.

Movies:

- usually use crew job `Director` for directors
- top cast order is usually straightforward
- writers and producers can be stored as `crew` later

Series:

- often use `created_by` for creators
- may also have crew roles in aggregate credits
- can have showrunners, writers, season crew, and episode crew
- may have different casts across seasons

MVP support should focus on:

- top cast
- movie directors
- series creators

Episode-level credits are out of scope for now.

## 6. Import Strategy from TMDb Preview

The current processed preview has `top_cast_names` and `director_or_creator_names`. For actual import, use structured credits with provider person IDs, not only names.

Import rules:

- match people by provider external ID first
- do not match people by name alone unless manually reviewed
- preserve cast order
- limit initial frontend display to top 5 cast
- import directors and creators separately from cast
- preserve provider credit IDs if available
- preserve unknown or incomplete credits in logs or reports instead of silently ignoring them

For TMDb specifically, the next credits preview should inspect structured fields such as person ID, name, profile path, cast order, character, crew job, department, and credit ID. The normalized import output should still use provider-neutral names like `source_name`, `external_id`, `role_type`, and `display_order`.

## 7. Scalable Ingestion Considerations

The design should scale beyond the current 15 titles to 100+ titles.

Scalable import rules:

- person import must be idempotent
- repeated people across many titles should resolve to the same `people` row
- provider IDs should prevent duplicate people
- import scripts should generate review reports before database writes
- failed or missing person matches should be logged
- provider-specific logic should stay in scripts or adapters
- frontend should consume backend-normalized data, not raw TMDb data

The import pipeline should be able to rerun without duplicating people or content-person relationships.

## 8. API Design Plan

Recommended first endpoint:

```http
GET /content/{content_id}/credits
```

Suggested response shape:

```json
{
  "cast": [
    {
      "person_id": 1,
      "name": "Matthew McConaughey",
      "character_name": "Cooper",
      "profile_url": "https://example.com/profile.jpg",
      "display_order": 0
    }
  ],
  "directors": [
    {
      "person_id": 2,
      "name": "Christopher Nolan",
      "profile_url": "https://example.com/profile.jpg"
    }
  ],
  "creators": [],
  "crew": []
}
```

Optional later endpoints:

```http
GET /people/{person_id}
GET /people/{person_id}/credits
```

Recommended MVP:

- start with `GET /content/{content_id}/credits`
- keep credits out of existing detail response until the schema and response shape are stable
- later decide whether compact credits should be embedded into `GET /content/{content_id}/details`

## 9. Frontend Display Plan

The content detail page should eventually show:

- Director for movies near the main metadata area
- Creator for series near the main metadata area
- Top Cast section below the hero or near the decision-support panels
- initially the top 5 cast members
- character names where available
- profile image if available
- initials/fallback avatar when profile image is missing

Person names can be non-clickable in the first UI pass. Later, once person detail APIs exist, names and avatars should link to person pages.

Do not overload homepage or discovery cards with cast/crew in the first implementation. Keep this detail-page focused.

## 10. Data Preservation and Provenance Rules

Person and credit imports should preserve useful provider data without blindly overwriting normalized app data.

Rules:

- do not lose provider credit data
- do not rely on name-only matching long term
- store person provider IDs in `person_external_ids`
- preserve `display_order`
- preserve `source_name` and `source_credit_id` where useful
- do not overwrite person fields blindly if providers disagree
- keep imports idempotent and reviewable
- keep TMDb-specific logic outside FastAPI route handlers and frontend components
- preserve skipped or ambiguous credits in import reports

If two providers disagree about a person's name, profile image, or role, the import should preserve the alternate value in a review artifact or future provenance table instead of silently discarding it.

## 11. What Not To Do

Do not:

- store cast as comma-separated text in `content`
- make `person.name` globally unique
- add public user profiles, reviews, posts, comments, communities, or social features
- add episode-level credits yet
- mix person metadata with the ratings phase
- call TMDb directly from the frontend
- expose raw provider payloads to the frontend
- implement schema in this planning task
- fake director, cast, or crew data in the frontend

## 12. Implementation Phases

### Phase A: Schema Foundation

- add `people`, `person_external_ids`, and `content_people` tables in `backend/schema.sql`
- add indexes
- update `docs/backend_database_setup.md`
- keep existing content APIs unchanged

### Phase B: Structured Credits Preview

- create a structured credits preview from TMDb data
- include provider person IDs, names, profile paths, character names, jobs, departments, display order, and credit IDs
- do not write to PostgreSQL initially

### Phase C: Safe Import Script

- create an inspection-first import/upsert script for `people`, `person_external_ids`, and `content_people`
- print planned inserts/updates before applying
- require an explicit apply flag for database writes
- log skipped or ambiguous credits

### Phase D: Backend Read API

- add `GET /content/{content_id}/credits`
- keep response provider-neutral
- add read-only backend tests

### Phase E: Frontend Detail Display

- show Director or Creator near detail metadata
- show Top Cast on content detail pages
- use profile image and fallback avatar states
- keep person links disabled until person pages exist

### Phase F: Metadata Navigation Pages Later

- add clickable genre pages from content detail genre chips
- add `GET /people/{person_id}`
- add `GET /people/{person_id}/credits`
- make person names and avatars clickable
- show related content for a person
- align person-page behavior with genre-page behavior
- consider person-based and genre-based discovery/recommendations later

## 13. Recommended Next Task

After this plan:

1. Review and commit this plan.
2. Implement `people`, `person_external_ids`, and `content_people` schema in SQL only.
3. Create a normalized structured credits preview script.
4. Create a safe import/upsert script after preview review.
5. Add backend credits API.
6. Add frontend detail-page credits display.

The first implementation should stay metadata-focused and should not move into ratings, reviews, episode-level credits, or social features.
