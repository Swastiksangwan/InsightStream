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

RECENT_SORT_EXPRESSION = "COALESCE(c.latest_activity_date, c.release_date)"
DEFAULT_AVAILABILITY_REGION = "IN"
FALLBACK_AVAILABILITY_REGION = "US"


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


def get_region_aware_platforms(
    db: Session,
    content_id: int,
    region_code: str,
) -> list[dict]:
    platforms_query = text("""
        SELECT
            p.name AS name,
            ca.availability_type,
            p.platform_type,
            ca.region_code,
            ca.source_name,
            ca.source_provider_id,
            ca.display_priority
        FROM content_availability ca
        JOIN platforms p ON ca.platform_id = p.id
        WHERE ca.content_id = :content_id
          AND ca.region_code = :region_code
        ORDER BY
            CASE ca.availability_type
                WHEN 'streaming' THEN 1
                WHEN 'rent' THEN 2
                WHEN 'buy' THEN 3
                WHEN 'ads' THEN 4
                WHEN 'free' THEN 5
                ELSE 6
            END,
            ca.display_priority NULLS LAST,
            p.name;
    """)
    platforms_result = db.execute(
        platforms_query,
        {
            "content_id": content_id,
            "region_code": region_code,
        },
    )
    return [dict(row) for row in platforms_result.mappings().all()]


def get_legacy_platforms(db: Session, content_id: int) -> list[dict]:
    platforms_query = text("""
        SELECT
            p.name AS name,
            cp.availability_type,
            p.platform_type,
            NULL::VARCHAR AS region_code,
            NULL::VARCHAR AS source_name,
            NULL::VARCHAR AS source_provider_id,
            NULL::INTEGER AS display_priority
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
    return [dict(row) for row in platforms_result.mappings().all()]


def get_detail_platforms(db: Session, content_id: int) -> list[dict]:
    primary_platforms = get_region_aware_platforms(
        db,
        content_id,
        DEFAULT_AVAILABILITY_REGION,
    )
    if primary_platforms:
        return primary_platforms

    fallback_platforms = get_region_aware_platforms(
        db,
        content_id,
        FALLBACK_AVAILABILITY_REGION,
    )
    if fallback_platforms:
        return fallback_platforms

    return get_legacy_platforms(db, content_id)


def get_display_certification(
    db: Session,
    content_id: int,
    fallback_age_rating,
) -> dict:
    certification_query = text("""
        SELECT
            certification,
            country_code,
            rating_system,
            source_name
        FROM content_certifications
        WHERE content_id = :content_id
          AND country_code IN (:primary_region, :fallback_region)
          AND certification IS NOT NULL
          AND certification <> ''
        ORDER BY
            CASE country_code
                WHEN :primary_region THEN 1
                WHEN :fallback_region THEN 2
                ELSE 3
            END,
            source_priority NULLS LAST,
            certification ASC
        LIMIT 1;
    """)
    certification_result = db.execute(
        certification_query,
        {
            "content_id": content_id,
            "primary_region": DEFAULT_AVAILABILITY_REGION,
            "fallback_region": FALLBACK_AVAILABILITY_REGION,
        },
    )
    certification_row = certification_result.mappings().first()

    if certification_row:
        return {
            "age_rating": certification_row["certification"],
            "age_rating_region": certification_row["country_code"],
            "age_rating_source": certification_row["source_name"],
            "age_rating_system": certification_row["rating_system"],
        }

    return {
        "age_rating": fallback_age_rating,
        "age_rating_region": None,
        "age_rating_source": None,
        "age_rating_system": None,
    }


def get_series_metadata(db: Session, content_id: int):
    series_query = text("""
        SELECT
            number_of_seasons,
            number_of_episodes,
            series_status,
            series_status_normalized,
            in_production,
            first_air_date,
            last_air_date,
            last_episode_air_date,
            next_episode_air_date,
            series_type,
            released_seasons_count,
            announced_seasons_count,
            next_season_number,
            next_season_air_date,
            next_season_year,
            has_announced_season,
            season_summary_note
        FROM content_series_metadata
        WHERE content_id = :content_id;
    """)
    series_result = db.execute(series_query, {"content_id": content_id})
    series_row = series_result.mappings().first()

    if not series_row:
        return None

    return dict(series_row)


def get_all_content_service(
    db: Session,
    content_type: str = None,
    search: str = None,
    limit: int = 10,
    offset: int = 0
):
    base_from_query = """
        FROM content c
    """

    conditions = []
    params = {
        "limit": limit,
        "offset": offset
    }

    if content_type:
        conditions.append("c.content_type = :content_type")
        params["content_type"] = content_type

    if search:
        conditions.append("c.title ILIKE :search")
        params["search"] = f"%{search}%"

    if conditions:
        base_from_query += " WHERE " + " AND ".join(conditions)

    data_query = text(f"""
        SELECT
            {CONTENT_SELECT_FIELDS}
        {base_from_query}
        ORDER BY {RECENT_SORT_EXPRESSION} DESC, c.title ASC
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
        WHERE COALESCE(c.latest_activity_date, c.release_date) IS NOT NULL
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
        ORDER BY {RECENT_SORT_EXPRESSION} DESC, c.title ASC
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
            {CONTENT_SELECT_FIELDS},
            {RECENT_SORT_EXPRESSION} AS sort_recent_date
        {base_from_query}
        ORDER BY sort_recent_date DESC, c.title ASC
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
            {CONTENT_SELECT_FIELDS},
            {RECENT_SORT_EXPRESSION} AS sort_recent_date
        {base_from_query}
        ORDER BY sort_recent_date DESC, c.title ASC
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
    # Internal sort fields are ignored by build_content_object(), keeping the API shape stable.
    if sort_by == "top_rated":
        select_fields = f"""
            {CONTENT_SELECT_FIELDS},
            cs.unified_score AS sort_unified_score
        """
        order_by = "ORDER BY sort_unified_score DESC NULLS LAST, c.release_date DESC, c.title ASC"
    else:
        select_fields = f"""
            {CONTENT_SELECT_FIELDS},
            {RECENT_SORT_EXPRESSION} AS sort_recent_date
        """
        order_by = "ORDER BY sort_recent_date DESC, c.title ASC"

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
        "role_type": row["role_type"],
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
            CASE WHEN cp.role_type = 'cast' THEN 1 ELSE 2 END,
            CASE
                WHEN cp.role_type = 'cast' AND cp.display_order IS NULL THEN 1
                ELSE 0
            END,
            cp.display_order ASC,
            CASE COALESCE(cp.job, '')
                WHEN 'Creator' THEN 1
                WHEN 'Director' THEN 2
                WHEN 'Writer' THEN 3
                WHEN 'Screenplay' THEN 4
                WHEN 'Story' THEN 5
                WHEN 'Executive Producer' THEN 6
                WHEN 'Producer' THEN 7
                ELSE 8
            END,
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
    unified_crew_keys = set()

    def append_unified_crew(row):
        key = (
            row["person_id"],
            row["job"] or row["role_type"] or "",
            row["department"] or "",
        )
        if key in unified_crew_keys:
            return
        unified_crew_keys.add(key)
        grouped_credits["crew"].append(build_crew_credit(row))

    for row in rows:
        role_type = row["role_type"]
        if role_type == "cast":
            if len(grouped_credits["cast"]) < 10:
                grouped_credits["cast"].append(build_cast_credit(row))
        elif role_type == "director":
            credit = build_crew_credit(row)
            grouped_credits["directors"].append(credit)
            append_unified_crew(row)
        elif role_type == "creator":
            credit = build_crew_credit(row)
            grouped_credits["creators"].append(credit)
            append_unified_crew(row)
        elif role_type == "crew":
            append_unified_crew(row)

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
    content.update(
        get_display_certification(
            db,
            content_id,
            content_row["age_rating"],
        )
    )

    series_metadata = None
    if content_row["content_type"] == "series":
        series_metadata = get_series_metadata(db, content_id)

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

    platforms = get_detail_platforms(db, content_id)

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
        "series_metadata": series_metadata,
        "summary": summary
    }
