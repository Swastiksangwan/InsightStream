# 🎬 InsightStream

InsightStream is a data-driven entertainment decision platform designed to help users decide **what to watch** using structured analytics instead of scattered opinions.

It aggregates and processes information from multiple sources to provide a **clean, unbiased, and intelligent view** of movies and series.

---

## 🚀 Core Idea

Instead of browsing endlessly across platforms, InsightStream provides:

* Unified content details
* Ratings from multiple platforms
* Normalized scoring system
* Simplified review insights
* Personal watch tracking (watch later / watched)
* Structured browsing, filtering, and search
* Discovery-based content exploration
* Flexible filtering by genre, platform, content type, availability type, and release recency/top-rated sorting
* Analytics-backed decision support

---

## Product Direction

InsightStream is an information-first entertainment decision-support platform.

The current MVP focuses on movies and series. It helps users understand what is trending, what is worth watching, where content is available, and how it is rated across sources.

Public user reviews, posts, comments, communities, and social feeds are not part of the MVP. User interaction is limited to personal utility actions like watch later and watched for now.

Public reviews and community features may be reconsidered later only if they clearly fit after the core film/series MVP, analytics foundation, and frontend are stable.

---

## 🛠 Tech Stack

### Backend

* **Framework:** FastAPI
* **Language:** Python
* **Database:** PostgreSQL
* **Queries:** SQLAlchemy using raw SQL via `text()`
* **Validation:** Pydantic schemas

### Frontend

* **Framework:** Next.js
* **UI:** React
* **Language:** TypeScript
* **Styling:** Dark cinematic global CSS currently; Tailwind CSS may be adopted later if the styling system is standardized
* **Current implementation:** homepage, discovery page v1, content detail page v1, reversible watch actions, Watch Later page v1, and Watched page v1

### Analytics

* Analytics planning documented
* Future tools: Pandas, NumPy, scikit-learn, NLTK / spaCy
* Future focus: data collection, rating normalization, unified scoring, review summarization, trending logic, and recommendations

### External APIs (Planned)

* TMDb

---

## Documentation

* `docs/product_direction.md` — MVP boundary and product direction
* `docs/analytics_data_collection_plan.md` — analytics and data collection roadmap
* `docs/backend_database_setup.md` — local database setup/reset/verification guide
* `docs/backend_testing.md` — backend test setup and current test coverage
* `docs/sample_data_gap_analysis.md` — current seed coverage and remaining data gaps
* `docs/sample_data_expansion_plan.md` — completed seed expansion plan
* `docs/frontend_integration_plan.md` — frontend API/page/component integration plan and implementation status

---

## 📁 Project Structure

```text
backend/
│
├── app/
│   ├── api/routes/        # API route definitions
│   ├── services/          # Business logic layer
│   ├── schemas/           # Pydantic response models
│   ├── db/                # Database session management
│   ├── core/              # Configuration and environment settings
│   └── main.py            # FastAPI app entry point
│
├── schema.sql             # Database schema
├── sample_data.sql        # Sample test data
├── indexes.sql            # Database indexes
├── requirements.txt
└── .env                   # Environment variables

frontend/
├── app/                   # Next.js app routes
├── components/            # Reusable UI components
├── lib/                   # Frontend API helpers
└── types/                 # TypeScript response types

docs/                      # Product, backend, data, testing, and frontend planning docs
```

---

## 🗄 Database Overview

Core tables:

* `content` – main movie/series data
* `genres` – genre metadata
* `content_genres` – content-to-genre relationship table
* `platforms` – OTT platforms and rating/review sources
* `content_platforms` – content availability by platform
* `ratings` – multi-platform ratings
* `content_summary` – processed insight and score summaries
* `users` – sample user data
* `watch_later` – user watchlist
* `watched` – completed content tracking

---

## ⚙️ Backend Features (Current)

### 🎯 Content APIs

#### 1. `GET /content`

A polished listing endpoint supporting:

* Ordering by latest release date
* Filtering by content type (`movie`, `series`)
* Search by title using case-insensitive matching
* Combined filtering using search + content type
* Pagination with `limit` and `offset`
* Total count for frontend pagination

Response format:

```json
{
  "items": [],
  "total": 25,
  "limit": 10,
  "offset": 0
}
```

---

#### 2. `GET /content/{content_id}`

Returns a clean, structured content object.

Features:

* Controlled response fields
* Consistent naming for frontend usage
* Proper `404` handling if content does not exist

---

#### 3. `GET /content/{content_id}/details`

Returns a fully enriched, frontend-ready response containing:

* Content information
* Genres
* Platform availability
* Ratings
* Summary insights

Key improvements:

* Platform ordering: `streaming` → `rent` → `buy`
* Ratings ordering: `critic` → `audience` → `general`
* Clean field naming
* Stable `summary: null` contract when summary data is missing

---

## 🔎 Discovery APIs

InsightStream now includes a discovery API layer for browsing and filtering content in a product-friendly way.

### 1. `GET /content/top-rated`

Returns content ordered by highest `unified_score`.

Supports:

* Optional `content_type`
* Pagination with `limit` and `offset`
* Stable ordering using score, release date, and title

Example:

```text
/content/top-rated
/content/top-rated?content_type=movie
```

---

### 2. `GET /content/recent`

Returns recently released content.

Supports:

* Optional `content_type`
* Pagination with `limit` and `offset`
* Ordering by `release_date DESC`

Example:

```text
/content/recent
/content/recent?content_type=series
```

---

### 3. `GET /content/by-genre/{genre_name}`

Returns content belonging to a specific genre.

Supports:

* Case-insensitive genre matching
* Optional `content_type`
* Pagination
* Empty result response for unknown or unmatched genres

Example:

```text
/content/by-genre/Sci-Fi
/content/by-genre/Sci-Fi?content_type=movie
```

---

### 4. `GET /content/by-platform/{platform_name}`

Returns content available on a specific platform.

Supports:

* Case-insensitive platform matching
* Optional `content_type`
* Optional `availability_type`
* Pagination
* Empty result response for unknown or unmatched platforms

Example:

```text
/content/by-platform/Netflix
/content/by-platform/Prime Video?availability_type=streaming
```

---

### 5. `GET /content/discover`

A combined discovery endpoint for flexible filtering.

This endpoint supports multiple filters in one request and is intended for a full discovery/search page.

Supported filters:

* `content_type`
* `genre`
* `platform`
* `availability_type`
* `sort_by`
* `limit`
* `offset`

Supported `sort_by` values:

* `recent`
* `top_rated`

Examples:

```text
/content/discover
/content/discover?content_type=movie
/content/discover?genre=Sci-Fi
/content/discover?platform=Prime Video
/content/discover?genre=Sci-Fi&platform=Prime Video
/content/discover?genre=Sci-Fi&platform=Prime Video&sort_by=top_rated
```

Response format remains consistent with the other paginated content endpoints:

```json
{
  "items": [],
  "total": 0,
  "limit": 10,
  "offset": 0
}
```

---

## 🧾 Metadata APIs

Metadata endpoints were added to support frontend filter menus and dynamic discovery UI.

### 1. `GET /genres`

Returns all available genres.

Example response:

```json
[
  {
    "id": 1,
    "name": "Action"
  },
  {
    "id": 12,
    "name": "Sci-Fi"
  }
]
```

---

### 2. `GET /platforms`

Returns all available platforms.

Supports optional filtering by platform type.

Example:

```text
/platforms
/platforms?platform_type=ott
/platforms?platform_type=rating_source
```

Example response:

```json
[
  {
    "id": 1,
    "name": "Netflix",
    "platform_type": "ott"
  },
  {
    "id": 8,
    "name": "IMDb",
    "platform_type": "rating_source"
  }
]
```

---

## 👤 User Interaction APIs

### Add Actions

* `POST /watch-later`
* `POST /watched`

### Get Actions

* `GET /watch-later/{user_id}`
* `GET /watched/{user_id}`

### Remove Actions

* `DELETE /watch-later`
* `DELETE /watched`

---

## ✅ Watch System Behavior

The watch system now includes proper business rules and validation.

Current behavior:

* Prevents duplicate watch later entries
* Prevents duplicate watched entries
* Prevents invalid user/content actions
* Removes content from `watch_later` when it is added to `watched`
* Keeps `watch_later` and `watched` mutually exclusive for the same user/content pair
* Returns empty lists with `200 OK`
* Uses proper error responses:
  * User not found → `404`
  * Content not found → `404`
  * Duplicate or invalid action → `409`

---

## 🧠 Backend Design Decisions

### Service Layer Architecture

Business logic is separated from route files.

This keeps routes thin and makes the backend easier to expand.

---

### Reusable Content Builder

A shared `build_content_object()` helper is used to keep content response formatting consistent across endpoints.

---

### Shared Content Select Fields

Common content fields are reused across service queries to reduce duplication and keep response structures aligned.

---

### Raw SQL with SQLAlchemy

The backend currently uses SQLAlchemy `text()` queries.

Reason:

* Full control over SQL
* Easier learning and debugging
* Predictable joins and ordering
* Clear visibility into database behavior

---

### Structured Pydantic Schemas

Pydantic schemas are used for:

* Content responses
* Paginated content responses
* Details responses
* Platform availability
* Ratings
* Summary data
* User content actions
* Genre metadata
* Platform metadata

This improves:

* Swagger documentation
* Response validation
* Frontend clarity
* API consistency

---

### Pagination-first Design

List and discovery endpoints are designed with pagination from the start.

This prepares the backend for larger datasets and frontend usage.

---

### Consistent API Contracts

The backend follows stable response behavior:

* Missing single resources return `404`
* Empty lists return `200 OK`
* Discovery filters return empty paginated responses when no match exists
* Paginated endpoints use a shared response shape

---

## 📊 Example Response: Details API

```json
{
  "content": {
    "id": 1,
    "title": "Interstellar",
    "type": "movie",
    "overview": "A team of explorers travel through a wormhole in space in an attempt to ensure humanity's survival.",
    "poster": "https://image.tmdb.org/t/p/w500/sampleposter.jpg",
    "backdrop": "https://image.tmdb.org/t/p/original/samplebackdrop.jpg",
    "release_date": "2014-11-07",
    "year": 2014,
    "runtime": 169,
    "language": "English",
    "age_rating": "PG-13"
  },
  "genres": [
    "Adventure",
    "Drama",
    "Sci-Fi"
  ],
  "platforms": [
    {
      "name": "Prime Video",
      "availability_type": "streaming"
    }
  ],
  "ratings": [
    {
      "platform": "Metacritic",
      "original_score": 74.0,
      "original_scale": 100.0,
      "normalized_score": 74.0,
      "rating_count": 60,
      "reviewer_group": "critic"
    }
  ],
  "summary": {
    "unified_score": 78.0,
    "critic_score": 73.5,
    "audience_score": 87.0,
    "review_summary": "A visually ambitious and emotionally powerful science-fiction film that is widely appreciated for its scale, performances, and music.",
    "pros": "Strong visuals, emotional depth, memorable soundtrack",
    "cons": "Complex pacing and scientific heaviness may not appeal to all viewers",
    "verdict": "Highly Recommended"
  }
}
```

---

## 🧪 Sample Data Status

`backend/sample_data.sql` is the single canonical reset-safe seed source for local development.

Current sample data includes 15 seeded titles:

* 8 movies
* 7 series
* Multiple genres
* Multiple platforms
* Streaming, rent, and buy availability examples
* Cross-source ratings, including `audience` reviewer-group rows
* Content summaries
* Watch later / watched test data

The sample data supports testing for:

* Top-rated content
* Recent content
* Genre-based discovery
* Platform-based discovery
* Combined discovery filters
* Watch later / watched behavior
* Pagination, analytics planning, and future frontend card/detail testing

Legacy/manual seed files have been removed and should not be used. The expanded seed supports stronger discovery, analytics, pagination, and frontend testing.

---

## Backend Testing

A pytest testing foundation has been added for the current read-only backend endpoints.

Current result: 18 passing tests.

Tests assume the local database is prepared with:

1. `backend/schema.sql`
2. `backend/sample_data.sql`
3. `backend/indexes.sql`

The full testing guide is in `docs/backend_testing.md`.

---

## Frontend Features (Current)

The frontend foundation is now functionally connected as a v1 MVP loop:

* Next.js setup completed
* Homepage implemented with Recent Releases using `GET /content/recent` and Top Rated Picks using `GET /content/top-rated`
* Discovery page v1 uses `GET /content/discover`, `GET /genres`, and `GET /platforms`
* Discovery filters include content type, genre, platform, availability type, and recent/top-rated sorting
* Content cards are polished, include fallback poster states, and route to `/content/[id]`
* Dynamic content detail page v1 uses `GET /content/{content_id}/details`
* Detail page shows metadata, genres, overview, availability, ratings, unified score, critic/audience scores, review summary, pros, cons, and verdict
* Detail page has reversible personal watch actions using `POST /watch-later`, `DELETE /watch-later`, `POST /watched`, and `DELETE /watched`
* Watch Later page v1 uses `GET /watch-later/{user_id}`
* Watched page v1 uses `GET /watched/{user_id}`
* Frontend production build passes

Current seed poster/backdrop URLs are placeholders, so real media data remains future work through TMDb or another ingestion source.

---

## 🔄 Current Status

Current backend status:

* Backend core architecture completed
* API polish phase completed
* Content listing API completed
* Details API completed
* Watch later / watched APIs completed
* Discovery endpoint family completed
* Combined discovery endpoint completed
* Metadata endpoints completed
* Genre and platform metadata schemas added
* Database indexes completed through `backend/indexes.sql`
* Canonical sample data completed through `backend/sample_data.sql`
* Expanded canonical sample seed data completed and tested
* Backend read endpoint testing foundation added with 18 passing pytest tests
* Product direction documented
* Analytics/data collection plan documented
* Swagger verification passed for expanded sample data
* Swagger documentation working
* API responses standardized and frontend-friendly
* Frontend foundation implemented with homepage, discovery page, content detail page, reversible watch actions, Watch Later page, and Watched page
* Basic frontend MVP loop is now connected: browse, view details, save/mark watched, view saved lists, and return to detail pages
* Frontend still uses a temporary demo user until authentication exists
* Frontend production build passes
* Frontend UI polish will continue over time
* Real poster/backdrop data is still future work through TMDb/data ingestion
* Cast/crew/person support remains future backend + frontend work
* Analytics scripts and API-based data collection still planned / not implemented

Current discovery endpoints:

```text
GET /content/top-rated
GET /content/recent
GET /content/by-genre/{genre_name}
GET /content/by-platform/{platform_name}
GET /content/discover
GET /genres
GET /platforms
```

---

## 🚀 Upcoming Work

### Immediate Next Phase

Possible next steps:

* Frontend MVP polish pass across homepage, discovery, detail, Watch Later, and Watched pages
* Polish the detail page over time as data quality improves
* Polish discovery page UI over time
* Plan frontend integration testing
* Expand backend tests to mutation endpoints and edge cases
* Continue analytics script planning
* Plan future TMDb ingestion before implementing it
* Use the expanded seed to identify remaining data edge cases

---

### Backend Expansion

Planned future backend work:

* Recommendation system foundation
* True trending / popularity logic
* Analytics-ready data pipelines
* Query optimization
* TMDb ingestion
* Migration setup
* Additional mutation and edge-case testing
* Authentication system

---

### Future Product Work

* Content detail page refinements
* Discovery page UI refinements
* Real poster/backdrop data through future TMDb ingestion
* Cast, crew, and person support after backend schema/API expansion
* Frontend integration testing later
* User authentication
* Backend/data/analytics improvements for scoring, labels, summaries, and ingestion
* Personalized recommendations
* Advanced analytics and insights
* NLP-based review processing
* TMDb ingestion pipeline

---

## ▶️ Running the Project

### 1. Clone the repository

    git clone https://github.com/Swastiksangwan/InsightStream.git
    cd InsightStream

### 2. Move into backend and create virtual environment

    cd backend
    python3 -m venv .venv
    source .venv/bin/activate

### 3. Install dependencies

    pip install -r requirements.txt

### 4. Setup environment variables

Create a `.env` file inside `backend/`:

    DATABASE_URL=postgresql://<user>:<password>@localhost:5432/<db_name>

### 5. Setup database

From the repository root, run the database files in this order:

    backend/schema.sql
    backend/sample_data.sql
    backend/indexes.sql

For detailed setup, reset, and verification steps, see:

    docs/backend_database_setup.md

### 6. Run server

From inside `backend/`:

    uvicorn app.main:app --reload

### 7. Open API docs

    http://127.0.0.1:8000/docs

---

## 🧩 Vision

InsightStream is not just a content browser.

It aims to become a **decision engine** that helps users confidently choose what to watch using **data, not noise**.

---
