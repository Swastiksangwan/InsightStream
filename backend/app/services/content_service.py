from sqlalchemy.orm import Session
from sqlalchemy import text


CONTENT_SELECT_FIELDS = """
    c.id,
    c.title,
    c.content_type,
    c.overview,
    c.poster_url,
    c.backdrop_url,
    c.release_date,
    c.year,
    c.runtime,
    c.language,
    c.age_rating
"""


def build_content_object(content_row):
    return {
        "id": content_row["id"],
        "title": content_row["title"],
        "type": content_row["content_type"],
        "overview": content_row["overview"],
        "poster": content_row["poster_url"],
        "backdrop": content_row["backdrop_url"],
        "release_date": content_row["release_date"],
        "year": content_row["year"],
        "runtime": content_row["runtime"],
        "language": content_row["language"],
        "age_rating": content_row["age_rating"]
    }


def get_all_content_service(
    db: Session,
    content_type: str = None,
    search: str = None,
    limit: int = 10,
    offset: int = 0
):
    base_from_query = """
        FROM content
    """

    conditions = []
    params = {
        "limit": limit,
        "offset": offset
    }

    if content_type:
        conditions.append("content_type = :content_type")
        params["content_type"] = content_type

    if search:
        conditions.append("title ILIKE :search")
        params["search"] = f"%{search}%"

    if conditions:
        base_from_query += " WHERE " + " AND ".join(conditions)

    data_query = text(f"""
        SELECT
            id,
            title,
            content_type,
            overview,
            poster_url,
            backdrop_url,
            release_date,
            year,
            runtime,
            language,
            age_rating
        {base_from_query}
        ORDER BY release_date DESC
        LIMIT :limit OFFSET :offset;
    """)

    count_query = text(f"""
        SELECT COUNT(*) AS total
        {base_from_query};
    """)

    data_result = db.execute(data_query, params)
    rows = data_result.mappings().all()

    count_result = db.execute(count_query, params)
    total = count_result.mappings().first()["total"]

    items = [build_content_object(row) for row in rows]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


def get_all_genres_service(db: Session):
    query = text("""
        SELECT
            id,
            name
        FROM genres
        ORDER BY name ASC;
    """)

    result = db.execute(query)
    rows = result.mappings().all()

    return [dict(row) for row in rows]


def get_all_platforms_service(
    db: Session,
    platform_type: str = None
):
    base_query = """
        SELECT
            id,
            name,
            platform_type
        FROM platforms
    """

    params = {}

    if platform_type:
        base_query += " WHERE platform_type = :platform_type"
        params["platform_type"] = platform_type

    base_query += " ORDER BY platform_type ASC, name ASC;"

    query = text(base_query)

    result = db.execute(query, params)
    rows = result.mappings().all()

    return [dict(row) for row in rows]


def get_top_rated_content_service(
    db: Session,
    content_type: str = None,
    limit: int = 10,
    offset: int = 0
):
    base_from_query = """
        FROM content c
        JOIN content_summary cs ON cs.content_id = c.id
        WHERE cs.unified_score IS NOT NULL
    """

    params = {
        "limit": limit,
        "offset": offset
    }

    if content_type:
        base_from_query += " AND c.content_type = :content_type"
        params["content_type"] = content_type

    data_query = text(f"""
        SELECT
            {CONTENT_SELECT_FIELDS}
        {base_from_query}
        ORDER BY cs.unified_score DESC, c.release_date DESC, c.title ASC
        LIMIT :limit OFFSET :offset;
    """)

    count_query = text(f"""
        SELECT COUNT(*) AS total
        {base_from_query};
    """)

    data_result = db.execute(data_query, params)
    rows = data_result.mappings().all()

    count_result = db.execute(count_query, params)
    total = count_result.mappings().first()["total"]

    items = [build_content_object(row) for row in rows]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


def get_recent_content_service(
    db: Session,
    content_type: str = None,
    limit: int = 10,
    offset: int = 0
):
    base_from_query = """
        FROM content c
        WHERE c.release_date IS NOT NULL
    """

    params = {
        "limit": limit,
        "offset": offset
    }

    if content_type:
        base_from_query += " AND c.content_type = :content_type"
        params["content_type"] = content_type

    data_query = text(f"""
        SELECT
            {CONTENT_SELECT_FIELDS}
        {base_from_query}
        ORDER BY c.release_date DESC, c.title ASC
        LIMIT :limit OFFSET :offset;
    """)

    count_query = text(f"""
        SELECT COUNT(*) AS total
        {base_from_query};
    """)

    data_result = db.execute(data_query, params)
    rows = data_result.mappings().all()

    count_result = db.execute(count_query, params)
    total = count_result.mappings().first()["total"]

    items = [build_content_object(row) for row in rows]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


def get_content_by_genre_service(
    db: Session,
    genre_name: str,
    content_type: str = None,
    limit: int = 10,
    offset: int = 0
):
    base_from_query = """
        FROM content c
        JOIN content_genres cg ON cg.content_id = c.id
        JOIN genres g ON g.id = cg.genre_id
        WHERE g.name ILIKE :genre_name
    """

    params = {
        "genre_name": genre_name,
        "limit": limit,
        "offset": offset
    }

    if content_type:
        base_from_query += " AND c.content_type = :content_type"
        params["content_type"] = content_type

    data_query = text(f"""
        SELECT DISTINCT
            {CONTENT_SELECT_FIELDS}
        {base_from_query}
        ORDER BY c.release_date DESC, c.title ASC
        LIMIT :limit OFFSET :offset;
    """)

    count_query = text(f"""
        SELECT COUNT(DISTINCT c.id) AS total
        {base_from_query};
    """)

    data_result = db.execute(data_query, params)
    rows = data_result.mappings().all()

    count_result = db.execute(count_query, params)
    total = count_result.mappings().first()["total"]

    items = [build_content_object(row) for row in rows]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


def get_content_by_platform_service(
    db: Session,
    platform_name: str,
    content_type: str = None,
    availability_type: str = None,
    limit: int = 10,
    offset: int = 0
):
    base_from_query = """
        FROM content c
        JOIN content_platforms cp ON cp.content_id = c.id
        JOIN platforms p ON p.id = cp.platform_id
        WHERE p.name ILIKE :platform_name
    """

    params = {
        "platform_name": platform_name,
        "limit": limit,
        "offset": offset
    }

    if content_type:
        base_from_query += " AND c.content_type = :content_type"
        params["content_type"] = content_type

    if availability_type:
        base_from_query += " AND cp.availability_type = :availability_type"
        params["availability_type"] = availability_type

    data_query = text(f"""
        SELECT DISTINCT
            {CONTENT_SELECT_FIELDS}
        {base_from_query}
        ORDER BY c.release_date DESC, c.title ASC
        LIMIT :limit OFFSET :offset;
    """)

    count_query = text(f"""
        SELECT COUNT(DISTINCT c.id) AS total
        {base_from_query};
    """)

    data_result = db.execute(data_query, params)
    rows = data_result.mappings().all()

    count_result = db.execute(count_query, params)
    total = count_result.mappings().first()["total"]

    items = [build_content_object(row) for row in rows]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


def get_discover_content_service(
    db: Session,
    content_type: str = None,
    genre: str = None,
    platform: str = None,
    availability_type: str = None,
    sort_by: str = "recent",
    limit: int = 10,
    offset: int = 0
):
    base_from_query = """
        FROM content c
        LEFT JOIN content_summary cs ON cs.content_id = c.id
    """

    conditions = []
    params = {
        "limit": limit,
        "offset": offset
    }

    if genre:
        base_from_query += """
            JOIN content_genres cg ON cg.content_id = c.id
            JOIN genres g ON g.id = cg.genre_id
        """
        conditions.append("g.name ILIKE :genre")
        params["genre"] = genre

    if platform:
        base_from_query += """
            JOIN content_platforms cp ON cp.content_id = c.id
            JOIN platforms p ON p.id = cp.platform_id
        """
        conditions.append("p.name ILIKE :platform")
        params["platform"] = platform

        if availability_type:
            conditions.append("cp.availability_type = :availability_type")
            params["availability_type"] = availability_type

    elif availability_type:
        base_from_query += """
            JOIN content_platforms cp ON cp.content_id = c.id
        """
        conditions.append("cp.availability_type = :availability_type")
        params["availability_type"] = availability_type

    if content_type:
        conditions.append("c.content_type = :content_type")
        params["content_type"] = content_type

    if conditions:
        base_from_query += " WHERE " + " AND ".join(conditions)

    # PostgreSQL requires ORDER BY fields to appear in SELECT when using SELECT DISTINCT.
    # So for top-rated sorting, include cs.unified_score only as an internal sort field.
    if sort_by == "top_rated":
        select_fields = f"""
            {CONTENT_SELECT_FIELDS},
            cs.unified_score AS sort_unified_score
        """
        order_by = "ORDER BY sort_unified_score DESC NULLS LAST, c.release_date DESC, c.title ASC"
    else:
        select_fields = CONTENT_SELECT_FIELDS
        order_by = "ORDER BY c.release_date DESC, c.title ASC"

    data_query = text(f"""
        SELECT DISTINCT
            {select_fields}
        {base_from_query}
        {order_by}
        LIMIT :limit OFFSET :offset;
    """)

    count_query = text(f"""
        SELECT COUNT(DISTINCT c.id) AS total
        {base_from_query};
    """)

    data_result = db.execute(data_query, params)
    rows = data_result.mappings().all()

    count_result = db.execute(count_query, params)
    total = count_result.mappings().first()["total"]

    # build_content_object ignores the internal sort_unified_score field,
    # so the API response shape stays unchanged.
    items = [build_content_object(row) for row in rows]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }

def get_content_by_id_service(content_id: int, db: Session):
    query = text(f"""
        SELECT
            {CONTENT_SELECT_FIELDS}
        FROM content c
        WHERE c.id = :content_id;
    """)
    result = db.execute(query, {"content_id": content_id})
    row = result.mappings().first()

    if not row:
        return None

    return build_content_object(row)


def build_cast_credit(row):
    return {
        "person_id": row["person_id"],
        "name": row["name"],
        "character_name": row["character_name"],
        "profile_url": row["profile_url"],
        "known_for_department": row["known_for_department"],
        "display_order": row["display_order"],
    }


def build_crew_credit(row):
    return {
        "person_id": row["person_id"],
        "name": row["name"],
        "profile_url": row["profile_url"],
        "known_for_department": row["known_for_department"],
        "job": row["job"],
        "department": row["department"],
        "display_order": row["display_order"],
    }


def get_content_credits_service(content_id: int, db: Session):
    content_exists_query = text("""
        SELECT id
        FROM content
        WHERE id = :content_id;
    """)
    content_result = db.execute(content_exists_query, {"content_id": content_id})
    content_row = content_result.mappings().first()

    if not content_row:
        return None

    credits_query = text("""
        SELECT
            cp.role_type,
            cp.character_name,
            cp.job,
            cp.department,
            cp.display_order,
            p.id AS person_id,
            p.name,
            p.profile_url,
            p.known_for_department
        FROM content_people cp
        JOIN people p ON p.id = cp.person_id
        WHERE cp.content_id = :content_id
        ORDER BY
            CASE cp.role_type
                WHEN 'cast' THEN 1
                WHEN 'director' THEN 2
                WHEN 'creator' THEN 3
                WHEN 'crew' THEN 4
                ELSE 5
            END,
            CASE WHEN cp.display_order IS NULL THEN 1 ELSE 0 END,
            cp.display_order ASC,
            cp.department ASC NULLS LAST,
            cp.job ASC NULLS LAST,
            p.name ASC;
    """)
    credits_result = db.execute(credits_query, {"content_id": content_id})
    rows = credits_result.mappings().all()

    grouped_credits = {
        "content_id": content_id,
        "cast": [],
        "directors": [],
        "creators": [],
        "crew": [],
    }

    for row in rows:
        role_type = row["role_type"]
        if role_type == "cast":
            grouped_credits["cast"].append(build_cast_credit(row))
        elif role_type == "director":
            grouped_credits["directors"].append(build_crew_credit(row))
        elif role_type == "creator":
            grouped_credits["creators"].append(build_crew_credit(row))
        elif role_type == "crew":
            grouped_credits["crew"].append(build_crew_credit(row))

    return grouped_credits


def get_content_details_service(content_id: int, db: Session):
    content_query = text(f"""
        SELECT
            {CONTENT_SELECT_FIELDS}
        FROM content c
        WHERE c.id = :content_id;
    """)
    content_result = db.execute(content_query, {"content_id": content_id})
    content_row = content_result.mappings().first()

    if not content_row:
        return None

    content = build_content_object(content_row)

    genres_query = text("""
        SELECT g.name
        FROM content_genres cg
        JOIN genres g ON cg.genre_id = g.id
        WHERE cg.content_id = :content_id
        ORDER BY g.name;
    """)
    genres_result = db.execute(genres_query, {"content_id": content_id})
    genres_rows = genres_result.mappings().all()
    genres = [row["name"] for row in genres_rows]

    platforms_query = text("""
        SELECT
            p.name AS name,
            cp.availability_type
        FROM content_platforms cp
        JOIN platforms p ON cp.platform_id = p.id
        WHERE cp.content_id = :content_id
        ORDER BY
            CASE cp.availability_type
                WHEN 'streaming' THEN 1
                WHEN 'rent' THEN 2
                WHEN 'buy' THEN 3
                ELSE 4
            END,
            p.name;
    """)
    platforms_result = db.execute(platforms_query, {"content_id": content_id})
    platforms_rows = platforms_result.mappings().all()
    platforms = [dict(row) for row in platforms_rows]

    ratings_query = text("""
        SELECT
            p.name AS platform,
            r.original_score,
            r.original_scale,
            r.normalized_score,
            r.rating_count,
            r.reviewer_group
        FROM ratings r
        JOIN platforms p ON r.platform_id = p.id
        WHERE r.content_id = :content_id
        ORDER BY
            CASE r.reviewer_group
                WHEN 'critic' THEN 1
                WHEN 'audience' THEN 2
                WHEN 'general' THEN 3
                ELSE 4
            END,
            p.name;
    """)
    ratings_result = db.execute(ratings_query, {"content_id": content_id})
    ratings_rows = ratings_result.mappings().all()
    ratings = [dict(row) for row in ratings_rows]

    summary_query = text("""
        SELECT
            unified_score,
            critic_score,
            audience_score,
            review_summary,
            pros,
            cons,
            verdict
        FROM content_summary
        WHERE content_id = :content_id;
    """)
    summary_result = db.execute(summary_query, {"content_id": content_id})
    summary_row = summary_result.mappings().first()

    summary = None
    if summary_row:
        summary = {
            "unified_score": summary_row["unified_score"],
            "critic_score": summary_row["critic_score"],
            "audience_score": summary_row["audience_score"],
            "review_summary": summary_row["review_summary"],
            "pros": summary_row["pros"],
            "cons": summary_row["cons"],
            "verdict": summary_row["verdict"],
        }

    return {
        "content": content,
        "genres": genres,
        "platforms": platforms,
        "ratings": ratings,
        "summary": summary
    }
