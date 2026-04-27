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
* Flexible content filtering by genre, platform, rating, and release recency

---

## 🛠 Tech Stack

### Backend

* **Framework:** FastAPI
* **Language:** Python
* **Database:** PostgreSQL
* **Queries:** SQLAlchemy using raw SQL via `text()`
* **Validation:** Pydantic schemas

### Frontend (Planned)

* Next.js
* React
* Tailwind CSS

### Analytics (Planned)

* Pandas
* NumPy
* scikit-learn
* NLP using NLTK / spaCy

### External APIs (Planned)

* TMDb

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
├── requirements.txt
└── .env                   # Environment variables
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
    "id": 40,
    "name": "Action"
  },
  {
    "id": 51,
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
    "id": 21,
    "name": "Netflix",
    "platform_type": "ott"
  },
  {
    "id": 28,
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
    "id": 9,
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
      "platform": "Prime Video",
      "original_score": 8.7,
      "original_scale": 10.0,
      "normalized_score": 87.0,
      "rating_count": 2000000,
      "reviewer_group": "general"
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

The database sample data has been expanded and verified.

Current sample data includes:

* Multiple content items
* Movies and series
* Multiple genres
* Multiple platforms
* Platform availability mappings
* Ratings
* Content summaries
* Watch later / watched test data

The sample data supports testing for:

* Top-rated content
* Recent content
* Genre-based discovery
* Platform-based discovery
* Combined discovery filters
* Watch later / watched behavior

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
* Sample data expanded and verified
* Swagger documentation working
* API responses standardized and frontend-friendly

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

* Add indexes for frequently queried fields
* Improve database scalability for discovery queries
* Refactor repeated pagination/query patterns if needed
* Add more sample data for stronger endpoint testing
* Begin frontend integration for content discovery sections

---

### Backend Expansion

Planned future backend work:

* Recommendation system foundation
* Trending / popular content logic
* Analytics-ready data pipelines
* Query optimization
* Migration setup
* Testing setup
* Authentication system

---

### Future Product Work

* Frontend integration with Next.js
* Homepage discovery sections
* Filter-based discovery UI
* User authentication
* Personalized recommendations
* Advanced analytics and insights
* NLP-based review processing
* TMDb ingestion pipeline

---

## ▶️ Running the Project

### 1. Clone the repository

```bash
git clone https://github.com/Swastiksangwan/InsightStream.git
cd InsightStream/backend
```

### 2. Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Setup environment variables

Create a `.env` file:

```env
DATABASE_URL=postgresql://<user>:<password>@localhost:5432/<db_name>
```

### 5. Setup database

Run the schema file in PostgreSQL:

```text
schema.sql
```

Then insert sample data:

```text
sample_data.sql
```

### 6. Run server

```bash
uvicorn app.main:app --reload
```

### 7. Open API docs

```text
http://127.0.0.1:8000/docs
```

---

## 🧩 Vision

InsightStream is not just a content browser.

It aims to become a **decision engine** that helps users confidently choose what to watch using **data, not noise**.

---

