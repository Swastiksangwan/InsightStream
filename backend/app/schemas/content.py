from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime

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
    age_rating_region: Optional[str] = None
    age_rating_source: Optional[str] = None
    age_rating_system: Optional[str] = None


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
class RatingSourceItem(BaseModel):
    source_name: str
    display_name: str
    source_category: str
    raw_score: Optional[float] = None
    raw_score_scale: Optional[float] = None
    normalized_score: Optional[float] = None
    vote_count: Optional[int] = None
    rating_count_label: Optional[str] = None
    rating_url: Optional[str] = None
    fetched_at: Optional[datetime] = None
    included_in_unified_score: bool = False


class RatingsResponse(BaseModel):
    unified_score: Optional[int] = None
    source_count: int
    scoring_source_count: int = 0
    sources: List[RatingSourceItem]


# Summary
class Summary(BaseModel):
    unified_score: Optional[float]
    critic_score: Optional[float]
    audience_score: Optional[float]
    review_summary: Optional[str]
    pros: Optional[str]
    cons: Optional[str]
    verdict: Optional[str]


class InsightSummarySignal(BaseModel):
    label: str
    value: str


class InsightSummary(BaseModel):
    headline: Optional[str] = None
    summary: Optional[str] = None
    best_for: List[str]
    key_signals: List[InsightSummarySignal]
    watch_note: Optional[str] = None
    generated_from: List[str]
    confidence: str


class WatchProfileSchema(BaseModel):
    watch_feel: Optional[str] = None
    chips: List[str]
    best_for: List[str]
    consider_first: List[str]


class DecisionSupportSchema(BaseModel):
    headline: Optional[str] = None
    reasons: List[str]
    cautions: List[str]


class DecisionDisplayProfileSchema(BaseModel):
    identity: List[str]
    themes: List[str]
    feel: List[str]
    pace: Optional[str] = None
    best_for: List[str]
    consider_first: List[str]


class DecisionDisplayFactSchema(BaseModel):
    label: str
    value: str


class DecisionDisplaySchema(BaseModel):
    primary_insight: Optional[str] = None
    profile: DecisionDisplayProfileSchema
    supporting_facts: List[DecisionDisplayFactSchema]


class SourceSignalQualitySchema(BaseModel):
    storage_ready: bool
    frontend_ready: bool
    has_watch_guidance: bool
    has_source_signals: bool


class ContentDecisionLayerSchema(BaseModel):
    watch_profile: WatchProfileSchema
    decision_support: DecisionSupportSchema
    display: Optional[DecisionDisplaySchema] = None
    signal_quality: SourceSignalQualitySchema


class SeriesMetadata(BaseModel):
    number_of_seasons: Optional[int] = None
    number_of_episodes: Optional[int] = None
    series_status: Optional[str] = None
    series_status_normalized: Optional[str] = None
    in_production: Optional[bool] = None
    first_air_date: Optional[date] = None
    last_air_date: Optional[date] = None
    last_episode_air_date: Optional[date] = None
    next_episode_air_date: Optional[date] = None
    series_type: Optional[str] = None
    released_seasons_count: Optional[int] = None
    announced_seasons_count: Optional[int] = None
    next_season_number: Optional[int] = None
    next_season_air_date: Optional[date] = None
    next_season_year: Optional[int] = None
    has_announced_season: Optional[bool] = None
    season_summary_note: Optional[str] = None


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
    role_type: Optional[str] = None
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
    ratings: RatingsResponse
    series_metadata: Optional[SeriesMetadata] = None
    insight_summary: InsightSummary
    decision_layer: Optional[ContentDecisionLayerSchema] = None
    summary: Optional[Summary] = None
