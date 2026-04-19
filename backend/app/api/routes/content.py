from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Literal
from app.db.session import get_db
from app.schemas.content import Content, ContentDetailsResponse
from app.services.content_service import (
    get_all_content_service,
    get_content_by_id_service,
    get_content_details_service
)

router = APIRouter()


@router.get("/content", response_model=List[Content])
def get_all_content(
    content_type: Optional[Literal["movie", "series"]] = Query(default=None),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    return get_all_content_service(db, content_type, search)


@router.get("/content/{content_id}", response_model=Content)
def get_content_by_id(content_id: int, db: Session = Depends(get_db)):
    content = get_content_by_id_service(content_id, db)

    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    return content


@router.get("/content/{content_id}/details", response_model=ContentDetailsResponse)
def get_content_details(content_id: int, db: Session = Depends(get_db)):
    content_details = get_content_details_service(content_id, db)

    if not content_details:
        raise HTTPException(status_code=404, detail="Content not found")

    return content_details