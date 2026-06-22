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
        WITH credit_match_rows AS (
            SELECT
                cp.content_id,
                CASE
                    WHEN LOWER(p.name) = :query_lower THEN 5
                    WHEN LOWER(p.name) LIKE :starts THEN 6
                    WHEN p.name ~* :word_start_pattern THEN 6
                    WHEN LOWER(p.name) LIKE :contains THEN 7
                    ELSE 12
                END AS credit_rank
            FROM content_people cp
            JOIN people p ON p.id = cp.person_id
            WHERE LOWER(p.name) LIKE :contains
               OR p.name ~* :word_start_pattern
               OR LOWER(COALESCE(cp.role_type, '')) LIKE :contains
               OR LOWER(COALESCE(cp.job, '')) LIKE :contains
               OR LOWER(COALESCE(cp.department, '')) LIKE :contains
        ),
        credit_matches AS (
            SELECT
                content_id,
                MIN(credit_rank) AS credit_rank
            FROM credit_match_rows
            GROUP BY content_id
        ),
        genre_matches AS (
            SELECT
                cg.content_id,
                TRUE AS genre_match
            FROM content_genres cg
            JOIN genres g ON g.id = cg.genre_id
            WHERE LOWER(g.name) LIKE :contains
               OR g.name ~* :word_start_pattern
            GROUP BY cg.content_id
        )
        SELECT COUNT(*) AS total
        FROM content c
        LEFT JOIN credit_matches cm ON cm.content_id = c.id
        LEFT JOIN genre_matches gm ON gm.content_id = c.id
        WHERE LOWER(c.title) LIKE :contains
           OR c.title ~* :word_start_pattern
           OR LOWER(COALESCE(c.overview, '')) LIKE :contains
           OR COALESCE(c.overview, '') ~* :word_pattern
           OR LOWER(c.content_type) LIKE :contains
           OR cm.credit_rank IS NOT NULL
           OR gm.genre_match IS TRUE;
    """)

    data_query = text("""
        WITH credit_match_rows AS (
            SELECT
                cp.content_id,
                p.name,
                CASE cp.role_type
                    WHEN 'cast' THEN 'cast'
                    WHEN 'director' THEN 'director'
                    WHEN 'creator' THEN 'creator'
                    ELSE COALESCE(NULLIF(cp.job, ''), NULLIF(cp.department, ''), 'crew')
                END AS match_role,
                CASE cp.role_type
                    WHEN 'director' THEN 1
                    WHEN 'creator' THEN 2
                    WHEN 'cast' THEN 3
                    ELSE 4
                END AS role_priority,
                CASE
                    WHEN LOWER(p.name) = :query_lower THEN 5
                    WHEN LOWER(p.name) LIKE :starts THEN 6
                    WHEN p.name ~* :word_start_pattern THEN 6
                    WHEN LOWER(p.name) LIKE :contains THEN 7
                    ELSE 12
                END AS credit_rank
            FROM content_people cp
            JOIN people p ON p.id = cp.person_id
            WHERE LOWER(p.name) LIKE :contains
               OR p.name ~* :word_start_pattern
               OR LOWER(COALESCE(cp.role_type, '')) LIKE :contains
               OR LOWER(COALESCE(cp.job, '')) LIKE :contains
               OR LOWER(COALESCE(cp.department, '')) LIKE :contains
        ),
        credit_matches AS (
            SELECT
                content_id,
                MIN(credit_rank) AS credit_rank,
                COALESCE(
                    ARRAY_AGG(name ORDER BY credit_rank ASC, name ASC) FILTER (WHERE credit_rank <= 7),
                    ARRAY[]::VARCHAR[]
                ) AS matched_people,
                (ARRAY_AGG(
                    'Matched ' || match_role || ': ' || name
                    ORDER BY credit_rank ASC, role_priority ASC, name ASC
                ))[1] AS match_reason
            FROM credit_match_rows
            GROUP BY content_id
        ),
        genre_matches AS (
            SELECT
                cg.content_id,
                TRUE AS genre_match
            FROM content_genres cg
            JOIN genres g ON g.id = cg.genre_id
            WHERE LOWER(g.name) LIKE :contains
               OR g.name ~* :word_start_pattern
            GROUP BY cg.content_id
        ),
        matched_content AS (
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
                COALESCE(cm.matched_people, ARRAY[]::VARCHAR[]) AS matched_people,
                CASE
                    WHEN LOWER(c.title) = :query_lower THEN 1
                    WHEN LOWER(c.title) LIKE :starts THEN 2
                    WHEN c.title ~* :word_start_pattern THEN 3
                    WHEN LOWER(c.title) LIKE :contains THEN 4
                    WHEN cm.credit_rank = 5 THEN 5
                    WHEN cm.credit_rank = 6 THEN 6
                    WHEN cm.credit_rank = 7 THEN 7
                    WHEN gm.genre_match IS TRUE THEN 8
                    WHEN COALESCE(c.overview, '') ~* :word_pattern THEN 9
                    WHEN LOWER(COALESCE(c.overview, '')) LIKE :contains THEN 10
                    WHEN LOWER(c.content_type) LIKE :contains THEN 11
                    ELSE COALESCE(cm.credit_rank, 12)
                END AS search_rank,
                CASE
                    WHEN LOWER(c.title) = :query_lower THEN 'Matched exact title'
                    WHEN LOWER(c.title) LIKE :starts THEN 'Matched title'
                    WHEN c.title ~* :word_start_pattern THEN 'Matched title'
                    WHEN LOWER(c.title) LIKE :contains THEN 'Matched title'
                    WHEN cm.credit_rank IS NOT NULL THEN cm.match_reason
                    WHEN gm.genre_match IS TRUE THEN 'Matched genre'
                    WHEN COALESCE(c.overview, '') ~* :word_pattern THEN 'Matched overview'
                    WHEN LOWER(COALESCE(c.overview, '')) LIKE :contains THEN 'Matched overview'
                    WHEN LOWER(c.content_type) LIKE :contains THEN 'Matched content type'
                    ELSE NULL
                END AS match_reason
            FROM content c
            LEFT JOIN credit_matches cm ON cm.content_id = c.id
            LEFT JOIN genre_matches gm ON gm.content_id = c.id
            WHERE LOWER(c.title) LIKE :contains
               OR c.title ~* :word_start_pattern
               OR LOWER(COALESCE(c.overview, '')) LIKE :contains
               OR COALESCE(c.overview, '') ~* :word_pattern
               OR LOWER(c.content_type) LIKE :contains
               OR cm.credit_rank IS NOT NULL
               OR gm.genre_match IS TRUE
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
            COALESCE(mc.latest_activity_date, mc.release_date) DESC NULLS LAST,
            mc.title ASC
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
        WHERE LOWER(p.name) LIKE :contains
           OR p.name ~* :word_start_pattern
           OR LOWER(COALESCE(p.known_for_department, '')) LIKE :contains
           OR COALESCE(p.known_for_department, '') ~* :word_start_pattern
           OR COALESCE(p.biography, '') ~* :word_pattern
           OR LOWER(COALESCE(p.biography, '')) LIKE :contains;
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
                WHEN LOWER(COALESCE(p.known_for_department, '')) LIKE :contains THEN 5
                WHEN COALESCE(p.biography, '') ~* :word_pattern THEN 6
                ELSE 7
            END AS search_rank,
            CASE
                WHEN LOWER(p.name) = :query_lower THEN 'Matched exact name'
                WHEN LOWER(p.name) LIKE :starts THEN 'Matched name'
                WHEN p.name ~* :word_start_pattern THEN 'Matched name'
                WHEN LOWER(p.name) LIKE :contains THEN 'Matched name'
                WHEN LOWER(COALESCE(p.known_for_department, '')) LIKE :contains THEN 'Matched department'
                WHEN COALESCE(p.biography, '') ~* :word_pattern THEN 'Matched biography'
                WHEN LOWER(COALESCE(p.biography, '')) LIKE :contains THEN 'Matched biography'
                ELSE NULL
            END AS match_reason
        FROM people p
        WHERE LOWER(p.name) LIKE :contains
           OR p.name ~* :word_start_pattern
           OR LOWER(COALESCE(p.known_for_department, '')) LIKE :contains
           OR COALESCE(p.known_for_department, '') ~* :word_start_pattern
           OR COALESCE(p.biography, '') ~* :word_pattern
           OR LOWER(COALESCE(p.biography, '')) LIKE :contains
        ORDER BY
            search_rank ASC,
            p.id ASC,
            p.name ASC
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
