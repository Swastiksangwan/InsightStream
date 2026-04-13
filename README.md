# InsightStream

InsightStream is a data-driven entertainment decision platform for movies and series.

It helps users decide what to watch by combining:
- Content details
- Ratings from multiple sources
- Normalized scores
- Simplified review insights
- Watch tracking
- Recommendations

## Tech Stack
- **Frontend:** Next.js, React, Tailwind CSS
- **Backend:** Python, FastAPI
- **Database:** PostgreSQL
- **Analytics:** Pandas, NumPy, scikit-learn, NLTK/spaCy
- **External API:** TMDb

## Current Progress
- PostgreSQL database schema designed and tested
- Sample data created and validated
- FastAPI backend structure implemented
- Database connection configured using environment variables
- `/content` endpoint created
- `/content/{content_id}` endpoint created
- `/content/{content_id}/details` endpoint implemented
- Response schemas added using Pydantic
- Details logic moved to a service layer
- Proper 404 handling added for content endpoints
- Nested, cleaner, frontend-ready details response prepared

## Current Backend Features
- FastAPI setup with PostgreSQL connection
- Content listing endpoint
- Single content fetch endpoint
- Detailed content endpoint with:
  - Content info
  - Platform availability
  - Ratings
  - Summary insights

## Next Steps
- Expand service layer for more backend logic
- Add more structured API endpoints
- Integrate frontend with backend
- Build recommendation features
- Improve analytics and insight generation