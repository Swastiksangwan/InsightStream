# InsightStream

InsightStream is a data-driven entertainment decision-support platform that helps users decide what to watch using structured content data, cross-platform ratings, availability, summaries, and personal watch tracking.

## Product Direction

InsightStream is an information-first platform for a movie/series MVP. It is focused on helping users browse content, compare ratings, understand availability, read concise decision-support summaries, and track what they want to watch or have already watched.

Public user reviews, posts, comments, communities, and social feeds are not part of the current MVP. User interaction is personal and utility-focused: Watch Later and Watched.

## Features

### Backend

- Content listing and detail APIs
- Discovery APIs for recent, top-rated, genre, platform, and combined filtering
- Genre and platform metadata APIs
- Watch Later and Watched APIs
- Pydantic response schemas
- PostgreSQL schema, canonical seed data, and indexes
- Pytest read-endpoint test foundation

### Frontend

- Homepage with recent and top-rated sections
- Discovery page with filters
- Content detail page with ratings, availability, summary, pros, cons, and verdict
- Reversible Watch Later and Watched actions
- Watch Later page
- Watched page
- Fallback poster UI for placeholder or missing images
- Dark cinematic UI foundation

### Data and Analytics

- Rating normalization planning
- Unified score planning
- Review summary and verdict planning
- Future real data ingestion planning
- Future poster/backdrop improvement planning

## Tech Stack

### Backend

- FastAPI
- Python
- PostgreSQL
- SQLAlchemy using raw SQL via `text()`
- Pydantic

### Frontend

- Next.js
- React
- TypeScript
- CSS-based dark cinematic UI foundation

### Analytics / Future

- Pandas
- NumPy
- scikit-learn
- NLP tools later
- TMDb or other allowed external APIs later

## Project Structure

```text
backend/   FastAPI app, SQL schema, seed data, indexes, tests
frontend/  Next.js app, UI components, API helpers, TypeScript types
docs/      Active product, frontend, backend, and analytics documentation
analytics/ Future data collection, cleaning, scoring, and analysis work
```

## Current Status

- Backend is stable.
- Canonical seed data contains 15 titles.
- Backend tests currently pass: `18 passed`.
- Frontend MVP loop v1 is connected:
  - homepage
  - discovery
  - content detail
  - reversible watch actions
  - Watch Later
  - Watched
- Frontend MVP polish pass 1 is complete.
- Frontend uses temporary `DEMO_USER_ID` until authentication exists.
- Real poster/backdrop data is future work through data ingestion.
- Cast, crew, director, and person support are future backend + frontend work.

## Running Locally

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
DATABASE_URL=postgresql://<user>:<password>@localhost:5432/<db_name>
```

From the repository root, run the SQL files in this order:

1. `backend/schema.sql`
2. `backend/sample_data.sql`
3. `backend/indexes.sql`

Start the backend:

```bash
cd backend
uvicorn app.main:app --reload
```

Backend API docs:

```text
http://127.0.0.1:8000/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend app:

```text
http://localhost:3000
```

## Testing

Backend tests use pytest and assume the local database was prepared with:

1. `backend/schema.sql`
2. `backend/sample_data.sql`
3. `backend/indexes.sql`

Run from the backend folder:

```bash
python3 -m pytest
```

Expected current result:

```text
18 passed
```

## Documentation

Active docs:

- `docs/product_direction.md` — MVP boundary and product direction
- `docs/frontend_integration_plan.md` — frontend status, API usage, and next direction
- `docs/detail_page_data_and_analytics_plan.md` — detail-page data and analytics roadmap
- `docs/analytics_data_collection_plan.md` — analytics and data collection roadmap
- `docs/backend_database_setup.md` — local database setup/reset/verification guide
- `docs/backend_testing.md` — backend test setup and current test coverage

Older completed planning docs are available in `docs/archive/`.

## Roadmap

- Real poster/backdrop ingestion
- Data source selection
- Rating-source strategy
- Unified score calculation
- Review summary pipeline
- Richer labels beyond movie/series, such as anime, short film, documentary, miniseries, and special
- Cast, crew, director, and person schema/API support
- Detail page support for director, cast, crew, and important people
- Clickable genres leading to filtered discovery/listing
- Clickable director/cast/crew/person entries and person pages later
- Frontend integration tests
- Authentication later
- Recommendation and true trending logic later

## MVP Boundary

InsightStream is not a public social or community platform in the current MVP. Public reviews, posts, comments, communities, followers, likes, and social feeds are intentionally excluded so the product can stay focused on structured information, analytics, availability, ratings, summaries, and personal watch actions.
