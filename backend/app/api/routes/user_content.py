from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.user_content import UserContentAction, ActionResponse
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


@router.post("/watch-later", response_model=ActionResponse)
def add_to_watch_later(data: UserContentAction, db: Session = Depends(get_db)):
    result = add_to_watch_later_service(data.user_id, data.content_id, db)

    if result.get("error") == "User not found":
        raise HTTPException(status_code=404, detail="User not found")

    if result.get("error") == "Content not found":
        raise HTTPException(status_code=404, detail="Content not found")

    if result.get("error") == "Content is already in watched":
        raise HTTPException(status_code=400, detail="Content is already in watched")

    if result.get("error") == "Content is already in watch later":
        raise HTTPException(status_code=409, detail="Content is already in watch later")

    return result


@router.post("/watched", response_model=ActionResponse)
def add_to_watched(data: UserContentAction, db: Session = Depends(get_db)):
    result = add_to_watched_service(data.user_id, data.content_id, db)

    if result.get("error") == "User not found":
        raise HTTPException(status_code=404, detail="User not found")

    if result.get("error") == "Content not found":
        raise HTTPException(status_code=404, detail="Content not found")

    if result.get("error") == "Content is already in watched":
        raise HTTPException(status_code=409, detail="Content is already in watched")

    return result


@router.get("/watch-later/{user_id}", response_model=List[Content])
def get_watch_later(user_id: int, db: Session = Depends(get_db)):
    result = get_watch_later_service(user_id, db)

    if isinstance(result, dict) and result.get("error") == "User not found":
        raise HTTPException(status_code=404, detail="User not found")

    return result


@router.get("/watched/{user_id}", response_model=List[Content])
def get_watched(user_id: int, db: Session = Depends(get_db)):
    result = get_watched_service(user_id, db)

    if isinstance(result, dict) and result.get("error") == "User not found":
        raise HTTPException(status_code=404, detail="User not found")

    return result


@router.delete("/watch-later", response_model=ActionResponse)
def remove_from_watch_later(data: UserContentAction, db: Session = Depends(get_db)):
    result = remove_from_watch_later_service(data.user_id, data.content_id, db)

    if result.get("error") == "User not found":
        raise HTTPException(status_code=404, detail="User not found")

    if result.get("error") == "Content is not in watch later":
        raise HTTPException(status_code=404, detail="Content is not in watch later")

    return result


@router.delete("/watched", response_model=ActionResponse)
def remove_from_watched(data: UserContentAction, db: Session = Depends(get_db)):
    result = remove_from_watched_service(data.user_id, data.content_id, db)

    if result.get("error") == "User not found":
        raise HTTPException(status_code=404, detail="User not found")

    if result.get("error") == "Content is not in watched":
        raise HTTPException(status_code=404, detail="Content is not in watched")

    return result