from fastapi import FastAPI
from app.api.routes.content import router as content_router
from app.api.routes.people import router as people_router
from app.api.routes.search import router as search_router
from app.api.routes.user_content import router as user_content_router

app = FastAPI(title="InsightStream API")

app.include_router(content_router)
app.include_router(people_router)
app.include_router(search_router)
app.include_router(user_content_router)

@app.get("/")
def root():
    return {"message": "InsightStream backend is running"}
