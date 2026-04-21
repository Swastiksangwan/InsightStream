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

---

## 🛠 Tech Stack

### Backend

* **Framework:** FastAPI
* **Language:** Python
* **Database:** PostgreSQL
* **Queries:** SQLAlchemy (raw SQL via `text()`)

### Frontend (Planned)

* Next.js
* React
* Tailwind CSS

### Analytics (Planned)

* Pandas
* NumPy
* scikit-learn
* NLP (NLTK / spaCy)

### External APIs (Planned)

* TMDb

---

## 📁 Project Structure

```
backend/
│
├── app/
│   ├── api/routes/        # API route definitions
│   ├── services/          # Business logic layer
│   ├── schemas/           # Pydantic response models
│   ├── db/                # Database session management
│   ├── core/              # Configuration (env, settings)
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
* `genres`, `content_genres`
* `platforms`, `content_platforms`
* `ratings` – multi-platform ratings
* `content_summary` – processed insights
* `watch_later` – user watchlist
* `watched` – completed content tracking

---

## ⚙️ Backend Features (Current)

### 🎯 Content APIs

#### 1. `GET /content`

A fully polished listing endpoint supporting:

* Ordering by latest release date
* Filtering by content type (`movie`, `series`)
* Search by title (case-insensitive)
* Combined filtering (search + type)
* Pagination (`limit`, `offset`)
* Total count for frontend pagination

Response format:

```
{
  "items": [...],
  "total": 25,
  "limit": 10,
  "offset": 0
}
```

---

#### 2. `GET /content/{content_id}`

* Returns a clean, structured content object
* Proper 404 handling if content does not exist

---

#### 3. `GET /content/{content_id}/details`

Returns a fully enriched, frontend-ready response:

* Content information
* Genres
* Platform availability (ordered logically)
* Ratings (ordered by reviewer type)
* Summary insights

Key improvements:

* Platform ordering: streaming → rent → buy
* Ratings ordering: critic → audience → general
* Clean field naming
* Stable `summary: null` contract

---

### 👤 User Interaction APIs

#### Add Actions

* `POST /watch-later`
* `POST /watched`

#### Get Actions

* `GET /watch-later/{user_id}`
* `GET /watched/{user_id}`

#### Remove Actions

* `DELETE /watch-later`
* `DELETE /watched`

---

### ✅ Watch System Behavior

* Prevents duplicates (409 Conflict)
* Prevents invalid actions (e.g. already watched)
* Proper validation:

  * User not found → 404
  * Content not found → 404
* Empty lists return `200 OK` (not errors)

---

## 🧠 Backend Design Decisions

### Service Layer Architecture

* Business logic separated from routes
* Cleaner, scalable structure

### Reusable Content Builder

* Consistent response formatting across APIs

### Raw SQL with SQLAlchemy

* Full control over queries
* Optimized and predictable behavior

### Structured Pydantic Schemas

* Strong API contracts
* Automatic validation
* Clean Swagger documentation

### Pagination-first Design

* Designed for real frontend scalability

### Consistent API Contracts

* Stable error messages
* Predictable empty/null behavior

---

## 📊 Example Response (Details API)

```
{
  "content": {
    "id": 1,
    "title": "Interstellar",
    "year": 2014
  },
  "ratings": [],
  "summary": {
    "unified_score": 78.0,
    "verdict": "Highly Recommended"
  }
}
```

---

## 🔄 Current Status

* Backend core architecture complete
* API Polish Phase completed
* Content APIs production-ready
* Advanced filtering + search + pagination implemented
* Watch tracking system fully implemented
* API responses standardized and frontend-friendly
* Swagger documentation fully working

---

## 🚀 Upcoming Work

### Next Phase (Backend Expansion)

* Recommendation system foundation
* Trending / popular content endpoints
* Analytics-ready data pipelines
* Performance optimizations (indexing, query tuning)

---

### Future Work

* Frontend integration (Next.js)
* User authentication system
* Personalized recommendations
* Advanced analytics & insights
* NLP-based review processing

---

## ▶️ Running the Project

### 1. Clone the repository

```
git clone https://github.com/Swastiksangwan/InsightStream.git
cd InsightStream/backend
```

### 2. Create virtual environment

```
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```
pip install -r requirements.txt
```

### 4. Setup environment variables

Create a `.env` file:

```
DATABASE_URL=postgresql://<user>:<password>@localhost:5432/<db_name>
```

### 5. Run server

```
uvicorn app.main:app --reload
```

### 6. Open API docs

```
http://127.0.0.1:8000/docs
```

---

## 🧩 Vision

InsightStream is not just a content browser — it aims to become a **decision engine** that helps users confidently choose what to watch using **data, not noise**.

---

## 👨‍💻 Author

Swastik Sangwan
B.Tech CSE | Backend + Data-driven Systems

---

