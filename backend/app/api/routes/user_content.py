from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.user_content import UserContentAction
from app.services.user_content_service import (
    add_to_watch_later_service,
    add_to_watched_service,
)

router = APIRouter()


@router.post("/watch-later")
def add_to_watch_later(data: UserContentAction, db: Session = Depends(get_db)):
    result = add_to_watch_later_service(data.user_id, data.content_id, db)

    if result.get("error") == "Content not found":
        raise HTTPException(status_code=404, detail="Content not found")

    return result


@router.post("/watched")
def add_to_watched(data: UserContentAction, db: Session = Depends(get_db)):
    result = add_to_watched_service(data.user_id, data.content_id, db)

    if result.get("error") == "Content not found":
        raise HTTPException(status_code=404, detail="Content not found")

    return result