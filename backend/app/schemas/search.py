from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ContentSearchResult(BaseModel):
    id: int
    title: str
    content_type: str
    overview_snippet: Optional[str] = None
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None
    release_date: Optional[date] = None
    latest_activity_date: Optional[date] = None
    age_rating: Optional[str] = None
    genres: List[str] = Field(default_factory=list)
    matched_people: List[str] = Field(default_factory=list)
    match_reason: Optional[str] = None
    result_type: Literal["content"] = "content"


class PersonSearchResult(BaseModel):
    id: int
    name: str
    profile_url: Optional[str] = None
    known_for_department: Optional[str] = None
    biography_snippet: Optional[str] = None
    match_reason: Optional[str] = None
    result_type: Literal["person"] = "person"


class SearchResponse(BaseModel):
    query: str
    type: Literal["all", "content", "person"]
    content_results: List[ContentSearchResult]
    person_results: List[PersonSearchResult]
    total_content_results: int
    total_person_results: int
