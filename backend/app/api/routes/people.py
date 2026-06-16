from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.people import PersonCreditsResponse, PersonDetailResponse
from app.services.people_service import (
    get_person_credits_service,
    get_person_detail_service,
)


router = APIRouter()


@router.get("/people/{person_id}", response_model=PersonDetailResponse)
def get_person(person_id: int, db: Session = Depends(get_db)):
    person = get_person_detail_service(person_id, db)

    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")

    return person


@router.get("/people/{person_id}/credits", response_model=PersonCreditsResponse)
def get_person_credits(person_id: int, db: Session = Depends(get_db)):
    credits = get_person_credits_service(person_id, db)

    if credits is None:
        raise HTTPException(status_code=404, detail="Person not found")

    return credits
