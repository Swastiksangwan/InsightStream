from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db

router = APIRouter()

@router.get("/content")
def get_all_content(db: Session = Depends(get_db)):
    query = text("SELECT * FROM content ORDER BY id;")
    result = db.execute(query)
    rows = result.mappings().all()
    return rows

@router.get("/content/{content_id}")
def get_content_by_id(content_id: int, db: Session = Depends(get_db)):
    query = text("SELECT * FROM content WHERE id = :content_id;")
    result = db.execute(query, {"content_id": content_id})
    row = result.mappings().first()

    if not row:
        return {"message": "Content not found"}

    return row