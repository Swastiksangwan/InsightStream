from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.user_content import UserContentAction
from typing import List
from app.schemas.content import Content
from app.services.user_content_service import (
    add_to_watch_later_service,
    add_to_watched_service,
    get_watch_later_service,
    get_watched_service,
    remove_from_watch_later_service,
    remove_from_watched_service,
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


@router.get("/watch-later/{user_id}", response_model=List[Content])
def get_watch_later(user_id: int, db: Session = Depends(get_db)):
    return get_watch_later_service(user_id, db)


@router.get("/watched/{user_id}", response_model=List[Content])
def get_watched(user_id: int, db: Session = Depends(get_db)):
    return get_watched_service(user_id, db)


@router.delete("/watch-later")
def remove_from_watch_later(data: UserContentAction, db: Session = Depends(get_db)):
    return remove_from_watch_later_service(data.user_id, data.content_id, db)


@router.delete("/watched")
def remove_from_watched(data: UserContentAction, db: Session = Depends(get_db)):
    return remove_from_watched_service(data.user_id, data.content_id, db)

