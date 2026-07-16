import re

from sqlalchemy import text
from sqlalchemy.orm import Session


def normalize_search_query(query: str) -> str:
    return query.strip()


def regex_pattern_for_query(query: str) -> str:
    return re.sub(r"([\\.^$*+?{}\[\]|()])", r"\\\1", query)


def word_pattern_for_query(query: str) -> str:
    escaped_query = regex_pattern_for_query(query)
    return f"(^|[^[:alnum:]]){escaped_query}([^[:alnum:]]|$)"


def word_start_pattern_for_query(query: str) -> str:
    escaped_query = regex_pattern_for_query(query)
    return f"(^|[^[:alnum:]]){escaped_query}"


def build_snippet(value, max_length: int = 220):
    if not value:
        return None

    normalized = " ".join(str(value).split())

    if len(normalized) <= max_length:
        return normalized

    return f"{normalized[: max_length - 3].rstrip()}..."


def build_content_search_result(row):
    genres = row["genres"] or []
    matched_people = list(dict.fromkeys(row["matched_people"] or []))

    return {
        "id": row["id"],
        "title": row["title"],
        "content_type": row["content_type"],
        "overview_snippet": build_snippet(row["overview"]),
        "poster_url": row["poster_url"],
        "backdrop_url": row["backdrop_url"],
        "release_date": row["release_date"],
        "latest_activity_date": row["latest_activity_date"],
        "age_rating": row["age_rating"],
        "genres": list(genres),
        "matched_people": list(matched_people),
        "match_reason": row["match_reason"],
        "result_type": "content",
    }


def build_person_search_result(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "profile_url": row["profile_url"],
        "known_for_department": row["known_for_department"],
        "biography_snippet": build_snippet(row["biography"]),
        "match_reason": row["match_reason"],
        "result_type": "person",
    }


def search_params(query: str, limit: int, offset: int):
    query_lower = query.lower()

    return {
        "query": query,
        "query_lower": query_lower,
        "starts": f"{query_lower}%",
        "contains": f"%{query_lower}%",
        "word_pattern": word_pattern_for_query(query),
        "word_start_pattern": word_start_pattern_for_query(query),
        "limit": limit,
        "offset": offset,
    }


def search_content(db: Session, query: str, limit: int, offset: int):
    params = search_params(query, limit, offset)

    count_query = text("""
        SELECT COUNT(*) AS total
        FROM content c
        WHERE LOWER(c.title) LIKE :contains
           OR LOWER(COALESCE(c.original_title, '')) LIKE :contains;
    """)

    data_query = text("""
        WITH matched_content AS (
            SELECT
                c.id,
                c.title,
                c.content_type,
                c.overview,
                c.poster_url,
                c.backdrop_url,
                c.release_date,
                c.latest_activity_date,
                c.age_rating,
                ARRAY[]::VARCHAR[] AS matched_people,
                CASE
                    WHEN LOWER(c.title) = :query_lower THEN 1
                    WHEN LOWER(c.title) LIKE :starts THEN 2
                    WHEN c.title ~* :word_start_pattern THEN 3
                    WHEN LOWER(c.title) LIKE :contains THEN 4
                    WHEN LOWER(COALESCE(c.original_title, '')) = :query_lower THEN 5
                    WHEN LOWER(COALESCE(c.original_title, '')) LIKE :starts THEN 6
                    WHEN COALESCE(c.original_title, '') ~* :word_start_pattern THEN 7
                    WHEN LOWER(COALESCE(c.original_title, '')) LIKE :contains THEN 8
                    ELSE 9
                END AS search_rank,
                CASE
                    WHEN LOWER(c.title) = :query_lower THEN 'Matched exact title'
                    WHEN LOWER(c.title) LIKE :starts THEN 'Matched title'
                    WHEN c.title ~* :word_start_pattern THEN 'Matched title'
                    WHEN LOWER(c.title) LIKE :contains THEN 'Matched title'
                    WHEN LOWER(COALESCE(c.original_title, '')) = :query_lower THEN 'Matched exact original title'
                    WHEN LOWER(COALESCE(c.original_title, '')) LIKE :starts THEN 'Matched original title'
                    WHEN COALESCE(c.original_title, '') ~* :word_start_pattern THEN 'Matched original title'
                    WHEN LOWER(COALESCE(c.original_title, '')) LIKE :contains THEN 'Matched original title'
                    ELSE NULL
                END AS match_reason
            FROM content c
            WHERE LOWER(c.title) LIKE :contains
               OR LOWER(COALESCE(c.original_title, '')) LIKE :contains
        )
        SELECT
            mc.id,
            mc.title,
            mc.content_type,
            mc.overview,
            mc.poster_url,
            mc.backdrop_url,
            mc.release_date,
            mc.latest_activity_date,
            mc.age_rating,
            mc.search_rank,
            mc.matched_people,
            mc.match_reason,
            COALESCE(
                ARRAY_AGG(g.name ORDER BY g.name) FILTER (WHERE g.name IS NOT NULL),
                ARRAY[]::VARCHAR[]
            ) AS genres
        FROM matched_content mc
        LEFT JOIN content_genres cg ON cg.content_id = mc.id
        LEFT JOIN genres g ON g.id = cg.genre_id
        GROUP BY
            mc.id,
            mc.title,
            mc.content_type,
            mc.overview,
            mc.poster_url,
            mc.backdrop_url,
            mc.release_date,
            mc.latest_activity_date,
            mc.age_rating,
            mc.search_rank,
            mc.matched_people,
            mc.match_reason
        ORDER BY
            mc.search_rank ASC,
            mc.title ASC,
            mc.id ASC
        LIMIT :limit OFFSET :offset;
    """)

    total = db.execute(count_query, params).mappings().first()["total"]
    rows = db.execute(data_query, params).mappings().all()

    return {
        "total": total,
        "items": [build_content_search_result(row) for row in rows],
    }


def search_people(db: Session, query: str, limit: int, offset: int):
    params = search_params(query, limit, offset)

    count_query = text("""
        SELECT COUNT(*) AS total
        FROM people p
        WHERE LOWER(p.name) LIKE :contains;
    """)

    data_query = text("""
        SELECT
            p.id,
            p.name,
            p.profile_url,
            p.known_for_department,
            p.biography,
            CASE
                WHEN LOWER(p.name) = :query_lower THEN 1
                WHEN LOWER(p.name) LIKE :starts THEN 2
                WHEN p.name ~* :word_start_pattern THEN 3
                WHEN LOWER(p.name) LIKE :contains THEN 4
                ELSE 5
            END AS search_rank,
            CASE
                WHEN LOWER(p.name) = :query_lower THEN 'Matched exact name'
                WHEN LOWER(p.name) LIKE :starts THEN 'Matched name'
                WHEN p.name ~* :word_start_pattern THEN 'Matched name'
                WHEN LOWER(p.name) LIKE :contains THEN 'Matched name'
                ELSE NULL
            END AS match_reason
        FROM people p
        WHERE LOWER(p.name) LIKE :contains
        ORDER BY
            search_rank ASC,
            p.name ASC,
            p.id ASC
        LIMIT :limit OFFSET :offset;
    """)

    total = db.execute(count_query, params).mappings().first()["total"]
    rows = db.execute(data_query, params).mappings().all()

    return {
        "total": total,
        "items": [build_person_search_result(row) for row in rows],
    }


def empty_search_response(query: str, search_type: str):
    return {
        "query": query,
        "type": search_type,
        "content_results": [],
        "person_results": [],
        "total_content_results": 0,
        "total_person_results": 0,
    }


def search_catalog_service(
    db: Session,
    query: str,
    search_type: str = "all",
    limit: int = 20,
    offset: int = 0,
):
    normalized_query = normalize_search_query(query)

    if not normalized_query:
        return empty_search_response(normalized_query, search_type)

    content_results = {"items": [], "total": 0}
    person_results = {"items": [], "total": 0}

    if search_type in ("all", "content"):
        content_results = search_content(db, normalized_query, limit, offset)

    if search_type in ("all", "person"):
        person_results = search_people(db, normalized_query, limit, offset)

    return {
        "query": normalized_query,
        "type": search_type,
        "content_results": content_results["items"],
        "person_results": person_results["items"],
        "total_content_results": content_results["total"],
        "total_person_results": person_results["total"],
    }
