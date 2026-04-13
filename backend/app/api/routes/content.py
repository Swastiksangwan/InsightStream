from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db
from app.schemas.content import ContentDetailsResponse
from app.services.content_service import get_content_details_service

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
        raise HTTPException(status_code=404, detail="Content not found")

    return row


@router.get("/content/{content_id}/details", response_model=ContentDetailsResponse)
def get_content_details(content_id: int, db: Session = Depends(get_db)):
    content_details = get_content_details_service(content_id, db)

    if not content_details:
        raise HTTPException(status_code=404, detail="Content not found")

    return content_details