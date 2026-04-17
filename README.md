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

### Content APIs

* `GET /content`
  → Returns list of content (clean, structured)

* `GET /content/{content_id}`
  → Returns single content object

* `GET /content/{content_id}/details`
  → Returns full details including:

  * Content info
  * Genres
  * Platforms
  * Ratings (normalized)
  * Summary insights (pros, cons, verdict)

---

### User Interaction APIs

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

## 🧠 Backend Design Decisions

* **Service Layer Architecture**

  * Business logic separated from routes
  * Improves scalability and maintainability

* **Reusable Content Formatter**

  * Consistent response structure across APIs

* **Raw SQL with SQLAlchemy**

  * Full control over queries
  * Better understanding of database behavior

* **Structured Pydantic Schemas**

  * Clean API contracts
  * Automatic validation and Swagger documentation

* **Proper Error Handling**

  * 404 responses for missing content
  * Safe handling of empty lists

---

## 📊 Example Response (Simplified)

```json
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
* Content APIs stable and structured
* User watch tracking system implemented (CRUD)
* Swagger documentation fully working

---

## ⏳ Upcoming Work

### Immediate Next Steps

* Add business rules:

  * Prevent duplicate entries
  * Prevent adding to watch_later if already watched

### Near Future

* Improve API formatting (polish phase)

  * Better ordering (ratings/platforms)
  * Cleaner summary handling

### Mid-Term

* Frontend integration (Next.js)
* User authentication system

### Long-Term

* Recommendation engine
* Advanced analytics
* NLP-based review insights

---

## ▶️ Running the Project

### 1. Clone the repository

```bash
git clone <your-repo-url>
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

```
DATABASE_URL=postgresql://<user>:<password>@localhost:5432/<db_name>
```

### 5. Run server

```bash
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
