from fastapi import FastAPI
from app.api.routes.content import router as content_router

app = FastAPI(title="InsightStream API")

app.include_router(content_router)

@app.get("/")
def root():
    return {"message": "InsightStream backend is running"}