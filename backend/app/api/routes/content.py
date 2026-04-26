from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, Literal
from app.db.session import get_db
from app.schemas.content import Content, ContentDetailsResponse, PaginatedContentResponse
from app.services.content_service import (
    get_all_content_service,
    get_all_genres_service,
    get_all_platforms_service,
    get_top_rated_content_service,
    get_recent_content_service,
    get_content_by_genre_service,
    get_content_by_platform_service,
    get_content_by_id_service,
    get_content_details_service
)

router = APIRouter()


@router.get("/content", response_model=PaginatedContentResponse)
def get_all_content(
    content_type: Optional[Literal["movie", "series"]] = Query(
        default=None,
        description="Filter content by type. Allowed values: movie, series."
    ),
    search: Optional[str] = Query(
        default=None,
        description="Case-insensitive search by title."
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of items to return."
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of items to skip before returning results."
    ),
    db: Session = Depends(get_db)
):
    return get_all_content_service(db, content_type, search, limit, offset)


@router.get("/genres")
def get_all_genres(db: Session = Depends(get_db)):
    return get_all_genres_service(db)


@router.get("/platforms")
def get_all_platforms(
    platform_type: Optional[Literal["ott", "rating_source", "review_source"]] = Query(
        default=None,
        description="Filter platforms by type. Allowed values: ott, rating_source, review_source."
    ),
    db: Session = Depends(get_db)
):
    return get_all_platforms_service(db, platform_type)


@router.get("/content/top-rated", response_model=PaginatedContentResponse)
def get_top_rated_content(
    content_type: Optional[Literal["movie", "series"]] = Query(
        default=None,
        description="Filter top-rated content by type. Allowed values: movie, series."
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of items to return."
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of items to skip before returning results."
    ),
    db: Session = Depends(get_db)
):
    return get_top_rated_content_service(db, content_type, limit, offset)


@router.get("/content/recent", response_model=PaginatedContentResponse)
def get_recent_content(
    content_type: Optional[Literal["movie", "series"]] = Query(
        default=None,
        description="Filter recent content by type. Allowed values: movie, series."
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of items to return."
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of items to skip before returning results."
    ),
    db: Session = Depends(get_db)
):
    return get_recent_content_service(db, content_type, limit, offset)


@router.get("/content/by-genre/{genre_name}", response_model=PaginatedContentResponse)
def get_content_by_genre(
    genre_name: str,
    content_type: Optional[Literal["movie", "series"]] = Query(
        default=None,
        description="Filter genre results by type. Allowed values: movie, series."
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of items to return."
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of items to skip before returning results."
    ),
    db: Session = Depends(get_db)
):
    return get_content_by_genre_service(db, genre_name, content_type, limit, offset)


@router.get("/content/by-platform/{platform_name}", response_model=PaginatedContentResponse)
def get_content_by_platform(
    platform_name: str,
    content_type: Optional[Literal["movie", "series"]] = Query(
        default=None,
        description="Filter platform results by type. Allowed values: movie, series."
    ),
    availability_type: Optional[Literal["streaming", "rent", "buy"]] = Query(
        default=None,
        description="Filter by availability type. Allowed values: streaming, rent, buy."
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of items to return."
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of items to skip before returning results."
    ),
    db: Session = Depends(get_db)
):
    return get_content_by_platform_service(
        db,
        platform_name,
        content_type,
        availability_type,
        limit,
        offset
    )


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