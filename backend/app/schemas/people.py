from pydantic import BaseModel
from typing import List, Optional


class PersonDetailResponse(BaseModel):
    person_id: int
    name: str
    profile_url: Optional[str] = None
    known_for_department: Optional[str] = None
    biography: Optional[str] = None


class PersonCreditContentItem(BaseModel):
    content_id: int
    title: str
    content_type: str
    poster_url: Optional[str] = None
    year: Optional[int] = None
    character_name: Optional[str] = None
    display_order: Optional[int] = None
    job: Optional[str] = None
    department: Optional[str] = None


class PersonCreditsResponse(BaseModel):
    person_id: int
    cast: List[PersonCreditContentItem]
    directed: List[PersonCreditContentItem]
    created: List[PersonCreditContentItem]
    crew: List[PersonCreditContentItem]
