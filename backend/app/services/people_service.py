from sqlalchemy import text
from sqlalchemy.orm import Session


def build_person_detail(row):
    return {
        "person_id": row["person_id"],
        "name": row["name"],
        "profile_url": row["profile_url"],
        "known_for_department": row["known_for_department"],
        "biography": row["biography"],
    }


def build_person_credit_item(row):
    return {
        "content_id": row["content_id"],
        "title": row["title"],
        "content_type": row["content_type"],
        "poster_url": row["poster_url"],
        "year": row["year"],
        "character_name": row["character_name"],
        "display_order": row["display_order"],
        "job": row["job"],
        "department": row["department"],
    }


def get_person_detail_service(person_id: int, db: Session):
    query = text("""
        SELECT
            id AS person_id,
            name,
            profile_url,
            known_for_department,
            biography
        FROM people
        WHERE id = :person_id;
    """)
    result = db.execute(query, {"person_id": person_id})
    row = result.mappings().first()

    if not row:
        return None

    return build_person_detail(row)


def get_person_credits_service(person_id: int, db: Session):
    person = get_person_detail_service(person_id, db)

    if person is None:
        return None

    query = text("""
        SELECT
            cp.role_type,
            cp.character_name,
            cp.job,
            cp.department,
            cp.display_order,
            c.id AS content_id,
            c.title,
            c.content_type,
            c.poster_url,
            c.year
        FROM content_people cp
        JOIN content c ON c.id = cp.content_id
        WHERE cp.person_id = :person_id
        ORDER BY
            CASE cp.role_type
                WHEN 'cast' THEN 1
                WHEN 'director' THEN 2
                WHEN 'creator' THEN 3
                WHEN 'crew' THEN 4
                ELSE 5
            END,
            c.year DESC NULLS LAST,
            c.title ASC,
            cp.display_order ASC NULLS LAST,
            cp.department ASC NULLS LAST,
            cp.job ASC NULLS LAST;
    """)
    result = db.execute(query, {"person_id": person_id})
    rows = result.mappings().all()

    grouped_credits = {
        "person_id": person_id,
        "cast": [],
        "directed": [],
        "created": [],
        "crew": [],
    }

    for row in rows:
        role_type = row["role_type"]
        credit_item = build_person_credit_item(row)

        if role_type == "cast":
            grouped_credits["cast"].append(credit_item)
        elif role_type == "director":
            grouped_credits["directed"].append(credit_item)
        elif role_type == "creator":
            grouped_credits["created"].append(credit_item)
        elif role_type == "crew":
            grouped_credits["crew"].append(credit_item)

    return grouped_credits
