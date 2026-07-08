from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.services.insight_summary_service import build_insight_summary
from app.services.source_signal_service import get_content_decision_layer


MINIMUM_VOTE_COUNT_FOR_UNIFIED_SCORE = 50

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

CONTENT_RATING_SUMMARY_JOIN = f"""
    LEFT JOIN (
        SELECT
            cr.content_id,
            ROUND(
                SUM(
                    CASE
                        WHEN cr.normalized_score IS NOT NULL
                         AND COALESCE(rs.weight, 0) > 0
                         AND cr.vote_count IS NOT NULL
                         AND cr.vote_count >= {MINIMUM_VOTE_COUNT_FOR_UNIFIED_SCORE}
                        THEN cr.normalized_score * COALESCE(rs.weight, 0)
                        ELSE 0
                    END
                )
                / NULLIF(
                    SUM(
                        CASE
                            WHEN cr.normalized_score IS NOT NULL
                             AND COALESCE(rs.weight, 0) > 0
                             AND cr.vote_count IS NOT NULL
                             AND cr.vote_count >= {MINIMUM_VOTE_COUNT_FOR_UNIFIED_SCORE}
                            THEN COALESCE(rs.weight, 0)
                            ELSE 0
                        END
                    ),
                    0
                )
            )::INTEGER AS unified_score,
            COUNT(*) AS source_count,
            COUNT(*) FILTER (
                WHERE cr.normalized_score IS NOT NULL
                  AND COALESCE(rs.weight, 0) > 0
                  AND cr.vote_count IS NOT NULL
                  AND cr.vote_count >= {MINIMUM_VOTE_COUNT_FOR_UNIFIED_SCORE}
            ) AS scoring_source_count
        FROM content_ratings cr
        JOIN rating_sources rs ON rs.id = cr.rating_source_id
        WHERE rs.is_active = TRUE
        GROUP BY cr.content_id
    ) rating_summary ON rating_summary.content_id = c.id
"""

CONTENT_SCORE_SELECT_FIELDS = """
    rating_summary.unified_score,
    rating_summary.source_count,
    rating_summary.scoring_source_count
"""

TOP_RATED_ORDER_BY = """
    ORDER BY
        rating_summary.unified_score DESC NULLS LAST,
        rating_summary.scoring_source_count DESC NULLS LAST,
        rating_summary.source_count DESC NULLS LAST,
        c.year DESC NULLS LAST,
        c.title ASC
"""

RECENT_SORT_EXPRESSION = "COALESCE(c.latest_activity_date, c.release_date)"
DEFAULT_AVAILABILITY_REGION = "IN"
FALLBACK_AVAILABILITY_REGION = "US"
AVAILABILITY_TYPE_ALIASES = {
    "stream": "streaming",
    "streaming": "streaming",
    "rent": "rent",
    "rental": "rent",
    "buy": "buy",
    "purchase": "buy",
    "ads": "ads",
    "ad": "ads",
    "free": "free",
}


def row_value(row, key, default=None):
    return row[key] if key in row else default


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
        "age_rating": content_row["age_rating"],
        "unified_score": row_value(content_row, "unified_score"),
        "source_count": row_value(content_row, "source_count"),
        "scoring_source_count": row_value(content_row, "scoring_source_count"),
    }


def normalize_region_code(region_code: str = None) -> str:
    if not region_code or not region_code.strip():
        return DEFAULT_AVAILABILITY_REGION
    return region_code.strip().upper()


def normalize_availability_type(availability_type: str = None) -> str:
    if not availability_type or not availability_type.strip():
        return None

    normalized = availability_type.strip().lower()
    if normalized in {"any", "all"}:
        return None

    return AVAILABILITY_TYPE_ALIASES.get(normalized, normalized)


def availability_filter_condition(
    include_platform: bool = True,
    include_availability_type: bool = False,
) -> str:
    platform_filter = "AND p_av.name ILIKE :platform" if include_platform else ""
    legacy_platform_filter = "AND p_legacy.name ILIKE :platform" if include_platform else ""
    availability_filter = (
        "AND ca.availability_type = :availability_type"
        if include_availability_type
        else ""
    )
    legacy_availability_filter = (
        "AND cp.availability_type = :availability_type"
        if include_availability_type
        else ""
    )

    return f"""
        (
            EXISTS (
                SELECT 1
                FROM content_availability ca
                JOIN platforms p_av ON p_av.id = ca.platform_id
                WHERE ca.content_id = c.id
                  AND ca.region_code = :availability_region
                  {platform_filter}
                  {availability_filter}
            )
            OR (
                NOT EXISTS (
                    SELECT 1
                    FROM content_availability ca_existing
                    WHERE ca_existing.content_id = c.id
                      AND ca_existing.region_code = :availability_region
                )
                AND EXISTS (
                    SELECT 1
                    FROM content_platforms cp
                    JOIN platforms p_legacy ON p_legacy.id = cp.platform_id
                    WHERE cp.content_id = c.id
                      {legacy_platform_filter}
                      {legacy_availability_filter}
                )
            )
        )
    """


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
        {rating_summary_join}
        WHERE rating_summary.unified_score IS NOT NULL
    """
    base_from_query = base_from_query.format(
        rating_summary_join=CONTENT_RATING_SUMMARY_JOIN,
    )

    params = {
        "limit": limit,
        "offset": offset
    }

    if content_type:
        base_from_query += " AND c.content_type = :content_type"
        params["content_type"] = content_type

    data_query = text(f"""
        SELECT
            {CONTENT_SELECT_FIELDS},
            {CONTENT_SCORE_SELECT_FIELDS}
        {base_from_query}
        {TOP_RATED_ORDER_BY}
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
    region: str = DEFAULT_AVAILABILITY_REGION,
    limit: int = 10,
    offset: int = 0
):
    base_from_query = """
        FROM content c
        WHERE
    """
    normalized_availability_type = normalize_availability_type(availability_type)

    params = {
        "platform": platform_name,
        "availability_region": normalize_region_code(region),
        "limit": limit,
        "offset": offset
    }
    conditions = [
        availability_filter_condition(
            include_platform=True,
            include_availability_type=normalized_availability_type is not None,
        )
    ]

    if normalized_availability_type:
        params["availability_type"] = normalized_availability_type

    if content_type:
        conditions.append("c.content_type = :content_type")
        params["content_type"] = content_type

    base_from_query += " AND ".join(conditions)

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
    region: str = DEFAULT_AVAILABILITY_REGION,
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
    normalized_availability_type = normalize_availability_type(availability_type)

    if genre:
        base_from_query += """
            JOIN content_genres cg ON cg.content_id = c.id
            JOIN genres g ON g.id = cg.genre_id
        """
        conditions.append("g.name ILIKE :genre")
        params["genre"] = genre

    if platform:
        conditions.append(
            availability_filter_condition(
                include_platform=True,
                include_availability_type=normalized_availability_type is not None,
            )
        )
        params["platform"] = platform
        params["availability_region"] = normalize_region_code(region)

        if normalized_availability_type:
            params["availability_type"] = normalized_availability_type

    elif normalized_availability_type:
        conditions.append(
            availability_filter_condition(
                include_platform=False,
                include_availability_type=True,
            )
        )
        params["availability_region"] = normalize_region_code(region)
        params["availability_type"] = normalized_availability_type

    if content_type:
        conditions.append("c.content_type = :content_type")
        params["content_type"] = content_type

    # PostgreSQL requires ORDER BY fields to appear in SELECT when using SELECT DISTINCT.
    # Score fields are included in the public list response for debugging/future UI.
    if sort_by == "top_rated":
        base_from_query += CONTENT_RATING_SUMMARY_JOIN
        select_fields = f"""
            {CONTENT_SELECT_FIELDS},
            {CONTENT_SCORE_SELECT_FIELDS}
        """
        order_by = TOP_RATED_ORDER_BY
    else:
        select_fields = f"""
            {CONTENT_SELECT_FIELDS},
            {RECENT_SORT_EXPRESSION} AS sort_recent_date
        """
        order_by = "ORDER BY sort_recent_date DESC, c.title ASC"

    if conditions:
        base_from_query += " WHERE " + " AND ".join(conditions)

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


def numeric_or_none(value):
    if value is None:
        return None
    return float(value)


def round_unified_score(value):
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def get_empty_ratings_response():
    return {
        "unified_score": None,
        "source_count": 0,
        "scoring_source_count": 0,
        "sources": [],
    }


def get_detail_ratings(db: Session, content_id: int):
    ratings_query = text("""
        SELECT
            rs.source_name,
            rs.display_name,
            rs.source_category,
            rs.weight,
            cr.raw_score,
            cr.raw_score_scale,
            cr.normalized_score,
            cr.vote_count,
            cr.rating_count_label,
            cr.rating_url,
            cr.fetched_at
        FROM content_ratings cr
        JOIN rating_sources rs ON rs.id = cr.rating_source_id
        WHERE cr.content_id = :content_id
          AND rs.is_active = TRUE
        ORDER BY
            CASE rs.source_category
                WHEN 'audience' THEN 1
                WHEN 'critic' THEN 2
                WHEN 'theatrical' THEN 3
                WHEN 'internal' THEN 4
                ELSE 5
            END,
            rs.display_name ASC;
    """)
    ratings_rows = db.execute(ratings_query, {"content_id": content_id}).mappings().all()

    if not ratings_rows:
        return get_empty_ratings_response()

    sources = []
    weighted_total = 0.0
    weight_total = 0.0
    scoring_source_count = 0

    for row in ratings_rows:
        normalized_score = numeric_or_none(row["normalized_score"])
        weight = numeric_or_none(row["weight"]) or 0
        vote_count = row["vote_count"]
        has_unified_score_confidence = (
            vote_count is not None
            and vote_count >= MINIMUM_VOTE_COUNT_FOR_UNIFIED_SCORE
        )

        included_in_unified_score = (
            normalized_score is not None
            and weight > 0
            and has_unified_score_confidence
        )

        if included_in_unified_score:
            weighted_total += normalized_score * weight
            weight_total += weight
            scoring_source_count += 1

        sources.append(
            {
                "source_name": row["source_name"],
                "display_name": row["display_name"],
                "source_category": row["source_category"],
                "raw_score": numeric_or_none(row["raw_score"]),
                "raw_score_scale": numeric_or_none(row["raw_score_scale"]),
                "normalized_score": normalized_score,
                "vote_count": vote_count,
                "rating_count_label": row["rating_count_label"],
                "rating_url": row["rating_url"],
                "fetched_at": row["fetched_at"],
                "included_in_unified_score": included_in_unified_score,
            }
        )

    unified_score = round_unified_score(weighted_total / weight_total) if weight_total else None

    return {
        "unified_score": unified_score,
        "source_count": len(sources),
        "scoring_source_count": scoring_source_count,
        "sources": sources,
    }


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

    ratings = get_detail_ratings(db, content_id)
    credits = get_content_credits_service(content_id, db)
    decision_layer = get_content_decision_layer(
        db,
        content_id,
        display_context={
            "content": content,
            "genres": genres,
            "platforms": platforms,
            "ratings": ratings,
            "credits": credits,
            "series_metadata": series_metadata,
        },
    )

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

    insight_summary = build_insight_summary(
        {
            "content": content,
            "genres": genres,
            "platforms": platforms,
            "ratings": ratings,
            "series_metadata": series_metadata,
            "credits": credits,
            "decision_layer": decision_layer,
        }
    )

    return {
        "content": content,
        "genres": genres,
        "platforms": platforms,
        "ratings": ratings,
        "series_metadata": series_metadata,
        "insight_summary": insight_summary,
        "decision_layer": decision_layer,
        "summary": summary
    }
