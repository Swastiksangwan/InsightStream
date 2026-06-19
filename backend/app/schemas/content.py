from pydantic import BaseModel
from typing import List, Optional
from datetime import date 

# Content
class Content(BaseModel):
    id: int
    title: str
    type: str
    overview: Optional[str]
    poster: Optional[str]
    backdrop: Optional[str]
    release_date: Optional[date]
    year: Optional[int]
    runtime: Optional[int]
    language: Optional[str]
    age_rating: Optional[str]


class PaginatedContentResponse(BaseModel):
    items: List[Content]
    total: int
    limit: int
    offset: int


# Platform
class Platform(BaseModel):
    name: str
    availability_type: str
    platform_type: Optional[str] = None
    region_code: Optional[str] = None
    source_name: Optional[str] = None
    source_provider_id: Optional[str] = None
    display_priority: Optional[int] = None


# Rating
class Rating(BaseModel):
    platform: str
    original_score: float
    original_scale: float
    normalized_score: float
    rating_count: Optional[int]
    reviewer_group: Optional[str]


# Summary
class Summary(BaseModel):
    unified_score: Optional[float]
    critic_score: Optional[float]
    audience_score: Optional[float]
    review_summary: Optional[str]
    pros: Optional[str]
    cons: Optional[str]
    verdict: Optional[str]


class Genre(BaseModel):
    id: int
    name: str


class PlatformMetadata(BaseModel):
    id: int
    name: str
    platform_type: str


class CastCredit(BaseModel):
    person_id: int
    name: str
    character_name: Optional[str] = None
    profile_url: Optional[str] = None
    known_for_department: Optional[str] = None
    display_order: Optional[int] = None


class CrewCredit(BaseModel):
    person_id: int
    name: str
    profile_url: Optional[str] = None
    known_for_department: Optional[str] = None
    job: Optional[str] = None
    department: Optional[str] = None
    display_order: Optional[int] = None


class ContentCreditsResponse(BaseModel):
    content_id: int
    cast: List[CastCredit]
    directors: List[CrewCredit]
    creators: List[CrewCredit]
    crew: List[CrewCredit]

    
# Final Response Model
class ContentDetailsResponse(BaseModel):
    content: Content
    genres: List[str]
    platforms: List[Platform]
    ratings: List[Rating]
    summary: Optional[Summary] = None
