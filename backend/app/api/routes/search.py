from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.search import SearchResponse
from app.services.search_service import search_catalog_service


router = APIRouter()


@router.get("/search", response_model=SearchResponse)
def search_catalog(
    q: str = Query(
        ...,
        description="Search text for local content and people catalog results.",
    ),
    search_type: Literal["all", "content", "person"] = Query(
        default="all",
        alias="type",
        description="Result type to search. Allowed values: all, content, person.",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum results to return per selected result group.",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of results to skip per selected result group.",
    ),
    db: Session = Depends(get_db),
):
    return search_catalog_service(db, q, search_type, limit, offset)
