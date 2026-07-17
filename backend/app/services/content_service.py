from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session
from sqlalchemy import bindparam, text

from app.services.insight_summary_service import build_insight_summary
from app.services.content_video_service import get_content_videos
from app.services.source_signal_service import get_content_decision_layer


MINIMUM_VOTE_COUNT_FOR_UNIFIED_SCORE = 50
HOME_DEFAULT_LIMIT = 10
HOME_MIN_LIMIT = 4
HOME_MAX_LIMIT = 20
HOME_CANDIDATE_POOL_CAP = 100
HOME_HIGH_SCORE_FLOOR = 70
HOME_MAX_PLATFORM_BUCKETS = 5
HOME_REFRESH_TIMEZONE = "Asia/Kolkata"
HOME_POSTER_REQUIRED_WHERE = "c.poster_url IS NOT NULL AND c.poster_url <> ''"
HOME_PLATFORM_PREFERRED_ORDER = {
    "Netflix": 1,
    "Prime Video": 2,
    "JioHotstar": 3,
    "Apple TV+": 4,
    "YouTube": 5,
}
HOME_CHIP_MAX_LENGTH = 18
HOME_CARD_PLATFORM_MAX_LENGTH = 18
HOME_CHIP_LABEL_MAP = {
    "organized-crime drama": "Crime",
    "organised-crime drama": "Crime",
    "organized crime": "Crime",
    "organised crime": "Crime",
    "cartel crime drama": "Crime",
    "crime drama": "Crime",
    "gangster crime": "Gangster",
    "gangster crime story": "Gangster",
    "psychological drama": "Psychological",
    "psychological thriller": "Psychological",
    "fantasy adventure": "Fantasy",
    "sci-fi adventure": "Sci-fi",
    "space sci-fi": "Space sci-fi",
    "space survival sci-fi": "Space sci-fi",
    "superhero story": "Superhero",
    "superhero team story": "Superhero",
    "animated superhero drama": "Superhero",
    "disaster drama": "Disaster",
    "disaster survival": "Survival",
    "martial-arts action": "Martial arts",
    "family-focused story": "Family",
    "family focused story": "Family",
    "family drama": "Family",
    "workplace comedy": "Comedy",
    "workplace drama": "Workplace",
    "kitchen workplace drama": "Kitchen",
    "dystopian future": "Dystopian",
    "political drama": "Political",
    "political power drama": "Political",
    "conspiracy thriller": "Conspiracy",
    "creature threat": "Creature threat",
    "creature thriller": "Creature",
    "survival drama": "Survival",
    "post-apocalyptic survival drama": "Survival",
    "revenge drama": "Revenge",
    "historical action epic": "Historical epic",
    "historical drama": "Historical",
    "character-driven drama": "Character-driven",
    "serial-killer investigation": "Serial killer",
    "memory and identity": "Identity",
    "power struggle": "Power struggle",
    "dark tone": "Dark",
    "light tone": "Light",
    "high intensity": "High intensity",
    "slow-burn": "Slow-burn",
    "puzzle-like": "Puzzle-like",
}
HOMEPAGE_FRESHNESS_DATE_EXPRESSION = """
    CASE
        WHEN c.content_type = 'series' THEN COALESCE(
            csm.next_episode_air_date,
            csm.last_episode_air_date,
            csm.last_air_date,
            c.latest_activity_date,
            c.release_date
        )
        ELSE COALESCE(c.release_date, c.latest_activity_date)
    END
"""

try:
    HOME_REFRESH_ZONE = ZoneInfo(HOME_REFRESH_TIMEZONE)
except ZoneInfoNotFoundError:
    HOME_REFRESH_ZONE = timezone(timedelta(hours=5, minutes=30))

CONTENT_SELECT_FIELDS = """
    c.id,
    c.title,
    c.original_title,
    c.content_type,
    c.overview,
    c.poster_url,
    c.backdrop_url,
    c.release_date,
    c.year,
    c.runtime,
    c.language,
    c.original_language,
    c.age_rating
"""
LANGUAGE_DISPLAY_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "ml": "Malayalam",
    "kn": "Kannada",
    "bn": "Bengali",
    "mr": "Marathi",
    "pa": "Punjabi",
    "gu": "Gujarati",
    "ur": "Urdu",
    "ko": "Korean",
    "ja": "Japanese",
    "zh": "Chinese",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
    "tr": "Turkish",
    "th": "Thai",
    "vi": "Vietnamese",
    "id": "Indonesian",
    "pl": "Polish",
    "nl": "Dutch",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
    "cs": "Czech",
    "el": "Greek",
    "he": "Hebrew",
    "fa": "Persian",
}

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
    original_language = row_value(content_row, "original_language")
    language = content_row["language"]

    return {
        "id": content_row["id"],
        "title": content_row["title"],
        "original_title": row_value(content_row, "original_title"),
        "type": content_row["content_type"],
        "overview": content_row["overview"],
        "poster": content_row["poster_url"],
        "backdrop": content_row["backdrop_url"],
        "release_date": content_row["release_date"],
        "year": content_row["year"],
        "runtime": content_row["runtime"],
        "language": language,
        "original_language": original_language,
        "original_language_name": display_language_name(original_language or language),
        "age_rating": content_row["age_rating"],
        "unified_score": row_value(content_row, "unified_score"),
        "source_count": row_value(content_row, "source_count"),
        "scoring_source_count": row_value(content_row, "scoring_source_count"),
    }


def display_language_name(value: str = None) -> str:
    if not value or not str(value).strip():
        return None

    language_value = str(value).strip()
    normalized_code = language_value.lower()
    if normalized_code in LANGUAGE_DISPLAY_NAMES:
        return LANGUAGE_DISPLAY_NAMES[normalized_code]

    if language_value.isalpha() and len(language_value) <= 3:
        return language_value.upper()

    return language_value


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


def clamp_home_limit(limit_per_section: int = None) -> int:
    if limit_per_section is None:
        return HOME_DEFAULT_LIMIT
    return max(HOME_MIN_LIMIT, min(HOME_MAX_LIMIT, int(limit_per_section)))


def home_candidate_pool_size(limit_per_section: int) -> int:
    return min(max(limit_per_section * 5, 40), HOME_CANDIDATE_POOL_CAP)


def get_home_reference_date() -> date:
    return datetime.now(HOME_REFRESH_ZONE).date()


def daily_seed(reference_date: date) -> str:
    return reference_date.isoformat()


def weekly_seed(reference_date: date) -> str:
    iso_year, iso_week, _weekday = reference_date.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def deterministic_rotation_value(seed: str, rotation_key: str, content_id: int) -> int:
    digest = sha256(f"{seed}:{rotation_key}:{content_id}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def quality_sort_key(row: dict):
    return (
        -(row.get("unified_score") or -1),
        -(row.get("scoring_source_count") or 0),
        -(row.get("source_count") or 0),
        -(row.get("year") or 0),
        row.get("title") or "",
    )


def select_rotated_rows(
    rows: list[dict],
    limit: int,
    seed: str,
    rotation_key: str,
    preserve_quality_order: bool = True,
) -> list[dict]:
    decorated = sorted(
        rows,
        key=lambda row: (
            deterministic_rotation_value(seed, rotation_key, row["id"]),
            row["id"],
        ),
    )
    selected = decorated[:limit]
    if preserve_quality_order:
        return sorted(selected, key=quality_sort_key)
    return selected


def balanced_content_type_mix(rows: list[dict], limit: int) -> list[dict]:
    if len(rows) <= limit:
        return rows

    by_type = {
        "movie": [row for row in rows if row.get("content_type") == "movie"],
        "series": [row for row in rows if row.get("content_type") == "series"],
    }
    if not by_type["movie"] or not by_type["series"]:
        return rows[:limit]

    selected = []
    used_ids = set()
    type_counts = {"movie": 0, "series": 0}
    max_one_type = max(1, limit - 2) if limit >= 4 else limit

    for row in rows:
        content_type = row.get("content_type")
        if type_counts.get(content_type, 0) >= max_one_type:
            continue
        selected.append(row)
        used_ids.add(row["id"])
        type_counts[content_type] = type_counts.get(content_type, 0) + 1
        if len(selected) >= limit:
            break

    for row in rows:
        if len(selected) >= limit:
            break
        if row["id"] not in used_ids:
            selected.append(row)
            used_ids.add(row["id"])

    return selected


def sql_rows(result) -> list[dict]:
    return [dict(row) for row in result.mappings().all()]


def json_array(value) -> list:
    return value if isinstance(value, list) else []


def home_candidate_query(
    where_clause: str,
    order_by: str,
    limit: int,
    extra_select: str = "",
    extra_join: str = "",
) -> str:
    return f"""
        SELECT
            {CONTENT_SELECT_FIELDS},
            {CONTENT_SCORE_SELECT_FIELDS},
            cwg.watch_feel,
            cwg.chips,
            cwg.best_for,
            cwg.consider_first
            {extra_select}
        FROM content c
        {CONTENT_RATING_SUMMARY_JOIN}
        LEFT JOIN content_watch_guidance cwg ON cwg.content_id = c.id
        {extra_join}
        WHERE {HOME_POSTER_REQUIRED_WHERE}
          AND {where_clause}
        {order_by}
        LIMIT :pool_limit;
    """


def fetch_home_candidates(
    db: Session,
    *,
    where_clause: str,
    order_by: str,
    pool_limit: int,
    params: dict = None,
    bindparams: list = None,
    extra_select: str = "",
    extra_join: str = "",
) -> list[dict]:
    query = text(
        home_candidate_query(
            where_clause,
            order_by,
            pool_limit,
            extra_select=extra_select,
            extra_join=extra_join,
        )
    )
    for bind_param in bindparams or []:
        query = query.bindparams(bind_param)

    query_params = {"pool_limit": pool_limit}
    query_params.update(params or {})
    return sql_rows(db.execute(query, query_params))


def signal_match_clause() -> str:
    return """
        EXISTS (
            SELECT 1
            FROM content_source_signals css
            WHERE css.content_id = c.id
              AND css.is_active = TRUE
              AND css.dimension IN :signal_dimensions
              AND (
                  LOWER(css.value) IN :signal_terms
                  OR LOWER(css.label) IN :signal_terms
              )
        )
    """


def signal_exclusion_clause() -> str:
    return """
        NOT EXISTS (
            SELECT 1
            FROM content_source_signals css_ex
            WHERE css_ex.content_id = c.id
              AND css_ex.is_active = TRUE
              AND (
                  LOWER(css_ex.value) IN :excluded_signal_terms
                  OR LOWER(css_ex.label) IN :excluded_signal_terms
              )
        )
    """


def fetch_signal_bucket_candidates(
    db: Session,
    *,
    signal_terms: list[str],
    signal_dimensions: list[str],
    pool_limit: int,
    excluded_terms: list[str] = None,
) -> list[dict]:
    exclusion_where = ""
    bindparams = [
        bindparam("signal_terms", expanding=True),
        bindparam("signal_dimensions", expanding=True),
    ]
    params = {
        "signal_terms": [term.lower() for term in signal_terms],
        "signal_dimensions": signal_dimensions,
        "pool_limit": pool_limit,
    }
    if excluded_terms:
        exclusion_where = f"AND {signal_exclusion_clause()}"
        bindparams.append(bindparam("excluded_signal_terms", expanding=True))
        params["excluded_signal_terms"] = [term.lower() for term in excluded_terms]

    query = text(
        home_candidate_query(
            where_clause=f"""
                {signal_match_clause()}
                {exclusion_where}
                AND rating_summary.unified_score IS NOT NULL
                AND cwg.content_id IS NOT NULL
            """,
            order_by="""
                ORDER BY
                    rating_summary.unified_score DESC NULLS LAST,
                    rating_summary.scoring_source_count DESC NULLS LAST,
                    rating_summary.source_count DESC NULLS LAST,
                    c.year DESC NULLS LAST,
                    c.title ASC
            """,
            limit=pool_limit,
        )
    ).bindparams(*bindparams)
    return sql_rows(db.execute(query, params))


def normalize_platform_display_name(name: str) -> str:
    normalized = (name or "").strip().lower()
    if normalized in {"amazon prime video", "prime video"} or "amazon prime video" in normalized:
        return "Prime Video"
    if normalized in {"jiohotstar", "disney+ hotstar", "hotstar"}:
        return "JioHotstar"
    if normalized in {"apple tv", "apple tv+"}:
        return "Apple TV+"
    if normalized == "youtube":
        return "YouTube"
    if normalized == "netflix":
        return "Netflix"
    return name


def normalize_home_card_platform_label(name: str):
    if not isinstance(name, str) or not name.strip():
        return None

    raw_name = " ".join(name.strip().split())
    normalized = raw_name.lower()
    if "sony pictures" in normalized:
        return "Sony Pictures"
    if "vi movies" in normalized or "movies and tv" in normalized:
        return None

    display_name = normalize_platform_display_name(raw_name)
    if not display_name:
        return None
    if len(display_name) > HOME_CARD_PLATFORM_MAX_LENGTH:
        return None
    return display_name


def home_display_platforms(platforms: list[str]) -> list[str]:
    display_platforms = []
    seen = set()
    for platform in platforms:
        display_name = normalize_home_card_platform_label(platform)
        if not display_name:
            continue
        key = display_name.lower()
        if key in seen:
            continue
        seen.add(key)
        display_platforms.append(display_name)
    return display_platforms


def home_primary_platform(platforms: list[str]):
    display_platforms = home_display_platforms(platforms)
    if not display_platforms:
        return None

    preferred = [
        platform
        for platform in display_platforms
        if platform in HOME_PLATFORM_PREFERRED_ORDER
    ]
    if preferred:
        return sorted(
            preferred,
            key=lambda platform: HOME_PLATFORM_PREFERRED_ORDER[platform],
        )[0]
    return display_platforms[0]


def platform_bucket_id(name: str) -> str:
    return (
        normalize_platform_display_name(name)
        .lower()
        .replace("+", "plus")
        .replace("&", "and")
        .replace(" ", "_")
        .replace("-", "_")
    )


def fetch_home_platform_bucket_defs(db: Session) -> list[dict]:
    rows = sql_rows(
        db.execute(
            text(
                """
                SELECT p.name, COUNT(DISTINCT ca.content_id) AS total_content
                FROM content_availability ca
                JOIN platforms p ON p.id = ca.platform_id
                WHERE ca.region_code = :region
                  AND ca.availability_type = 'streaming'
                GROUP BY p.name
                UNION ALL
                SELECT p.name, COUNT(DISTINCT cp.content_id) AS total_content
                FROM content_platforms cp
                JOIN platforms p ON p.id = cp.platform_id
                WHERE cp.availability_type = 'streaming'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM content_availability ca
                      WHERE ca.content_id = cp.content_id
                        AND ca.region_code = :region
                  )
                GROUP BY p.name;
                """
            ),
            {"region": DEFAULT_AVAILABILITY_REGION},
        )
    )

    grouped: dict[str, dict] = {}
    for row in rows:
        display_name = normalize_platform_display_name(row["name"])
        bucket_id = platform_bucket_id(display_name)
        bucket = grouped.setdefault(
            bucket_id,
            {
                "bucket_id": bucket_id,
                "label": display_name,
                "platform_names": [],
                "total_content": 0,
            },
        )
        if row["name"] not in bucket["platform_names"]:
            bucket["platform_names"].append(row["name"])
        bucket["total_content"] += row["total_content"] or 0

    homepage_buckets = [
        bucket
        for bucket in grouped.values()
        if bucket["label"] in HOME_PLATFORM_PREFERRED_ORDER
    ]
    return sorted(
        homepage_buckets,
        key=lambda item: (
            HOME_PLATFORM_PREFERRED_ORDER[item["label"]],
            -(item["total_content"] or 0),
            item["label"],
        ),
    )[:HOME_MAX_PLATFORM_BUCKETS]


def fetch_platform_candidates(
    db: Session,
    *,
    platform_names: list[str],
    pool_limit: int,
) -> list[dict]:
    platform_condition = """
        (
            EXISTS (
                SELECT 1
                FROM content_availability ca
                JOIN platforms p_av ON p_av.id = ca.platform_id
                WHERE ca.content_id = c.id
                  AND ca.region_code = :region
                  AND ca.availability_type = 'streaming'
                  AND p_av.name IN :platform_names
            )
            OR (
                NOT EXISTS (
                    SELECT 1
                    FROM content_availability ca_existing
                    WHERE ca_existing.content_id = c.id
                      AND ca_existing.region_code = :region
                )
                AND EXISTS (
                    SELECT 1
                    FROM content_platforms cp
                    JOIN platforms p_legacy ON p_legacy.id = cp.platform_id
                    WHERE cp.content_id = c.id
                      AND cp.availability_type = 'streaming'
                      AND p_legacy.name IN :platform_names
                )
            )
        )
    """
    query = text(
        home_candidate_query(
            where_clause=f"""
                {platform_condition}
                AND rating_summary.unified_score IS NOT NULL
            """,
            order_by=TOP_RATED_ORDER_BY,
            limit=pool_limit,
        )
    ).bindparams(bindparam("platform_names", expanding=True))

    return sql_rows(
        db.execute(
            query,
            {
                "platform_names": platform_names,
                "region": DEFAULT_AVAILABILITY_REGION,
                "pool_limit": pool_limit,
            },
        )
    )


def fetch_home_platforms_for_ids(db: Session, content_ids: set[int]) -> dict[int, list[str]]:
    if not content_ids:
        return {}

    query = text(
        """
        SELECT
            ca.content_id,
            p.name,
            ca.availability_type,
            ca.display_priority,
            CASE ca.availability_type
                WHEN 'streaming' THEN 1
                WHEN 'rent' THEN 2
                WHEN 'buy' THEN 3
                WHEN 'ads' THEN 4
                WHEN 'free' THEN 5
                ELSE 6
            END AS availability_sort,
            1 AS source_priority
        FROM content_availability ca
        JOIN platforms p ON p.id = ca.platform_id
        WHERE ca.content_id IN :content_ids
          AND ca.region_code = :region
        UNION ALL
        SELECT
            cp.content_id,
            p.name,
            cp.availability_type,
            NULL::INTEGER AS display_priority,
            CASE cp.availability_type
                WHEN 'streaming' THEN 1
                WHEN 'rent' THEN 2
                WHEN 'buy' THEN 3
                WHEN 'ads' THEN 4
                WHEN 'free' THEN 5
                ELSE 6
            END AS availability_sort,
            2 AS source_priority
        FROM content_platforms cp
        JOIN platforms p ON p.id = cp.platform_id
        WHERE cp.content_id IN :content_ids
          AND NOT EXISTS (
              SELECT 1
              FROM content_availability ca_existing
              WHERE ca_existing.content_id = cp.content_id
                AND ca_existing.region_code = :region
          )
        ORDER BY
            content_id,
            source_priority,
            availability_sort,
            display_priority NULLS LAST,
            name ASC;
        """
    ).bindparams(bindparam("content_ids", expanding=True))

    platforms: dict[int, list[str]] = {}
    seen: dict[int, set[str]] = {}
    rows = sql_rows(
        db.execute(
            query,
            {
                "content_ids": sorted(content_ids),
                "region": DEFAULT_AVAILABILITY_REGION,
            },
        )
    )
    for row in rows:
        content_id = row["content_id"]
        display_name = normalize_platform_display_name(row["name"])
        key = display_name.lower()
        seen.setdefault(content_id, set())
        if key in seen[content_id]:
            continue
        platforms.setdefault(content_id, []).append(display_name)
        seen[content_id].add(key)

    return platforms


def fetch_home_signal_labels_for_ids(db: Session, content_ids: set[int]) -> dict[int, list[str]]:
    if not content_ids:
        return {}

    query = text(
        """
        SELECT
            content_id,
            label,
            dimension
        FROM content_source_signals
        WHERE content_id IN :content_ids
          AND is_active = TRUE
        ORDER BY
            content_id,
            CASE dimension
                WHEN 'audience_expectation' THEN 1
                WHEN 'topic_theme' THEN 2
                WHEN 'tone' THEN 3
                WHEN 'mood' THEN 4
                WHEN 'pacing' THEN 5
                WHEN 'intensity' THEN 6
                ELSE 7
            END,
            label ASC;
        """
    ).bindparams(bindparam("content_ids", expanding=True))

    labels: dict[int, list[str]] = {}
    for row in sql_rows(db.execute(query, {"content_ids": sorted(content_ids)})):
        labels.setdefault(row["content_id"], []).append(row["label"])
    return labels


HOME_TECHNICAL_TERMS = (
    "tmdb",
    "keyword",
    "source_names",
    "mapping_version",
    "provider",
    "frontend_ready",
    "storage_ready",
    "backend_display_fallback",
)
HOME_WEAK_CHIPS = {
    "content",
    "drama",
    "drama viewers",
    "story viewers",
    "generic story",
    "complex story",
    "heavier watch",
    "bleak mood",
    "dark story",
    "serious story",
    "story",
    "stories",
}


def clean_home_label(value):
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = " ".join(value.strip().split())
    lower_value = cleaned.lower()
    if any(term in lower_value for term in HOME_TECHNICAL_TERMS):
        return None
    if lower_value.endswith(" viewers"):
        return None
    if lower_value in HOME_WEAK_CHIPS:
        return None
    return cleaned


def normalize_home_chip_label(label):
    cleaned = clean_home_label(label)
    if not cleaned:
        return None

    normalized_key = (
        cleaned.lower()
        .replace("–", "-")
        .replace("—", "-")
        .replace("‑", "-")
    )
    normalized_key = " ".join(normalized_key.split())
    compact_label = HOME_CHIP_LABEL_MAP.get(normalized_key, cleaned)
    compact_label = " ".join(compact_label.strip().split())
    if not clean_home_label(compact_label):
        return None
    if len(compact_label) > HOME_CHIP_MAX_LENGTH:
        return None
    return compact_label


def content_type_label(content_type: str) -> str:
    return "Series" if content_type == "series" else "Movie"


def truncate_sentence(value: str, max_length: int = 120) -> str:
    if len(value) <= max_length:
        return value
    trimmed = value[: max_length - 1].rsplit(" ", 1)[0].rstrip(" ,.;")
    return f"{trimmed}."


def lower_first_phrase(value: str) -> str:
    if not value:
        return value
    return value[:1].lower() + value[1:]


def build_home_chips(row: dict, signal_labels: list[str]) -> list[str]:
    candidates = []
    candidates.extend(json_array(row.get("chips")))
    candidates.extend(signal_labels)

    chips = []
    seen = set()
    for candidate in candidates:
        label = normalize_home_chip_label(candidate)
        if not label:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        chips.append(label)
        if len(chips) >= 4:
            break

    if not chips and row.get("unified_score") is not None:
        chips.append("High-scoring")
    if len(chips) < 2:
        type_chip = content_type_label(row.get("content_type"))
        if type_chip.lower() not in {chip.lower() for chip in chips}:
            chips.append(type_chip)

    return chips[:4]


def build_home_decision_reason(row: dict, chips: list[str], platforms: list[str]) -> str:
    score = row.get("unified_score")
    if chips:
        primary = lower_first_phrase(chips[0])
        if score is not None and score >= 85 and len(chips) >= 2:
            return truncate_sentence(
                f"High-scoring {primary} with {lower_first_phrase(chips[1])}."
            )
        if len(chips) >= 2:
            return truncate_sentence(f"{chips[0]} with {lower_first_phrase(chips[1])}.")
        if score is not None:
            return truncate_sentence(f"High-scoring {primary}.")

    watch_feel = clean_home_label(row.get("watch_feel"))
    if watch_feel:
        return truncate_sentence(watch_feel)

    if platforms:
        return truncate_sentence(f"Available on {platforms[0]}.")
    return f"{content_type_label(row.get('content_type'))} from the catalog."


def build_home_card(
    row: dict,
    platform_map: dict[int, list[str]],
    signal_label_map: dict[int, list[str]],
) -> dict:
    platforms = home_display_platforms(platform_map.get(row["id"], []))
    chips = build_home_chips(row, signal_label_map.get(row["id"], []))
    decision_reason = build_home_decision_reason(row, chips, platforms)

    return {
        "id": row["id"],
        "title": row["title"],
        "content_type": row["content_type"],
        "year": row["year"],
        "poster_url": row["poster_url"],
        "backdrop_url": row["backdrop_url"],
        "runtime": row["runtime"],
        "age_rating": row["age_rating"],
        "release_date": row["release_date"],
        "unified_score": row.get("unified_score"),
        "source_count": row.get("source_count"),
        "scoring_source_count": row.get("scoring_source_count"),
        "primary_platform": home_primary_platform(platforms),
        "platforms": platforms[:3],
        "decision_reason": decision_reason,
        "chips": chips,
    }


def build_home_cards(
    rows: list[dict],
    platform_map: dict[int, list[str]],
    signal_label_map: dict[int, list[str]],
) -> list[dict]:
    seen = set()
    cards = []
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        cards.append(build_home_card(row, platform_map, signal_label_map))
    return cards


def collect_content_ids_from_sections(section_sources):
    content_ids: set[int] = set()
    for value in section_sources.values():
        if isinstance(value, list):
            for row in value:
                content_ids.add(row["id"])
        elif isinstance(value, dict):
            for rows in value.values():
                for row in rows:
                    content_ids.add(row["id"])
    return content_ids


def get_home_content_service(
    db: Session,
    limit_per_section: int = None,
    reference_date=None,
) -> dict:
    limit = clamp_home_limit(limit_per_section)
    pool_limit = home_candidate_pool_size(limit)
    reference_date = reference_date or get_home_reference_date()
    day_seed = daily_seed(reference_date)
    week_seed = weekly_seed(reference_date)

    high_quality_where = """
        rating_summary.unified_score IS NOT NULL
        AND rating_summary.unified_score >= :high_score_floor
        AND cwg.content_id IS NOT NULL
    """
    high_quality_params = {"high_score_floor": HOME_HIGH_SCORE_FLOOR}

    weekly_pool = fetch_home_candidates(
        db,
        where_clause=high_quality_where,
        order_by=TOP_RATED_ORDER_BY,
        pool_limit=pool_limit,
        params=high_quality_params,
    )
    weekly_rows = balanced_content_type_mix(
        select_rotated_rows(
            weekly_pool,
            pool_limit,
            week_seed,
            "weekly_picks",
            preserve_quality_order=False,
        ),
        limit,
    )

    top_pool = fetch_home_candidates(
        db,
        where_clause="""
            rating_summary.unified_score IS NOT NULL
            AND rating_summary.unified_score >= :high_score_floor
        """,
        order_by=TOP_RATED_ORDER_BY,
        pool_limit=pool_limit,
        params=high_quality_params,
    )
    top_rated_rows = select_rotated_rows(
        top_pool,
        limit,
        day_seed,
        "top_rated",
        preserve_quality_order=True,
    )

    recent_rows = fetch_home_candidates(
        db,
        where_clause=f"({HOMEPAGE_FRESHNESS_DATE_EXPRESSION}) IS NOT NULL",
        order_by="""
            ORDER BY
                homepage_freshness_date DESC NULLS LAST,
                rating_summary.unified_score DESC NULLS LAST,
                rating_summary.source_count DESC NULLS LAST,
                c.title ASC
        """,
        pool_limit=limit,
        extra_select=f", {HOMEPAGE_FRESHNESS_DATE_EXPRESSION} AS homepage_freshness_date",
        extra_join="LEFT JOIN content_series_metadata csm ON csm.content_id = c.id",
    )

    mood_bucket_defs = [
        {
            "bucket_id": "fast_paced",
            "label": "Fast-Paced",
            "subtitle": "Momentum, missions, action, and plot-forward stories.",
            "terms": [
                "action-heavy",
                "fast-moving",
                "fast-paced",
                "propulsive",
                "mission-driven",
                "plot-driven",
                "survival-driven",
                "chase",
                "pursuit",
                "action spectacle",
            ],
            "dimensions": ["pacing", "intensity", "topic_theme"],
            "excluded_terms": [
                "slow-burn",
                "meditative",
                "contemplative",
                "reflective",
                "gentle",
                "quiet",
                "dialogue-heavy",
                "cozy",
                "comfort",
            ],
        },
        {
            "bucket_id": "slow_burn_thoughtful",
            "label": "Slow-Burn & Thoughtful",
            "subtitle": "Reflective, layered, or puzzle-like watches.",
            "terms": [
                "slow-burn",
                "meditative",
                "contemplative",
                "reflective",
                "thoughtful",
                "philosophical",
                "dialogue-heavy",
                "puzzle-like",
                "mind-bending",
            ],
            "dimensions": ["pacing", "tone", "mood"],
            "excluded_terms": [
                "fast-paced",
                "fast-moving",
                "action-heavy",
                "propulsive",
                "mission-driven",
                "plot-driven",
                "chase",
                "pursuit",
                "action spectacle",
                "survival-driven",
                "heist story",
                "high intensity",
            ],
        },
        {
            "bucket_id": "dark_intense",
            "label": "Dark & Intense",
            "subtitle": "Tense, suspenseful, gritty, or higher-stakes picks.",
            "terms": [
                "tense",
                "suspenseful",
                "dark",
                "dark tone",
                "high intensity",
                "psychological thriller",
                "horror",
                "dystopian",
                "dystopian future",
                "gritty",
                "bleak",
                "foreboding",
                "organized crime",
                "crime drama",
                "violent crime",
                "brutal",
                "morally grey",
            ],
            "dimensions": ["mood", "tone", "intensity", "audience_expectation", "topic_theme"],
            "excluded_terms": [
                "warm",
                "light",
                "playful",
                "gentle",
                "uplifting",
                "feel-good",
                "comfort",
                "cozy",
                "family-focused",
                "charming",
            ],
        },
        {
            "bucket_id": "light_comfort",
            "label": "Light Watch",
            "subtitle": "Warmer, playful, gentle, or heartfelt choices.",
            "terms": [
                "warm",
                "light",
                "playful",
                "uplifting",
                "family-focused",
                "family-focused story",
                "workplace comedy",
                "comedy",
                "gentle",
                "hopeful",
                "feel-good",
                "comfort",
                "cozy",
                "charming",
            ],
            "dimensions": ["mood", "tone", "audience_expectation", "topic_theme"],
            "excluded_terms": [
                "dark",
                "dark tone",
                "tense",
                "suspenseful",
                "high intensity",
                "high-stakes",
                "psychological thriller",
                "psychological",
                "horror",
                "dystopian",
                "dystopian future",
                "gritty",
                "bleak",
                "foreboding",
                "organized crime",
                "crime drama",
                "violent crime",
                "brutal",
                "morally grey",
                "survival",
                "survival drama",
                "survival-driven",
                "crisis",
                "serious tone",
                "disaster story",
                "disaster drama",
                "body horror",
                "disaster",
                "trauma",
                "revenge",
                "serial killer",
                "murder",
                "war",
                "grief-heavy",
                "melancholic",
                "action-heavy",
            ],
        },
    ]

    mood_rows_by_bucket = {}
    for bucket in mood_bucket_defs:
        pool = fetch_signal_bucket_candidates(
            db,
            signal_terms=bucket["terms"],
            signal_dimensions=bucket["dimensions"],
            pool_limit=pool_limit,
            excluded_terms=bucket.get("excluded_terms"),
        )
        mood_rows_by_bucket[bucket["bucket_id"]] = select_rotated_rows(
            pool,
            limit,
            day_seed,
            f"mood_pace:{bucket['bucket_id']}",
            preserve_quality_order=True,
        )

    platform_defs = fetch_home_platform_bucket_defs(db)
    platform_rows_by_bucket = {}
    for platform in platform_defs:
        pool = fetch_platform_candidates(
            db,
            platform_names=platform["platform_names"],
            pool_limit=pool_limit,
        )
        platform_rows_by_bucket[platform["bucket_id"]] = select_rotated_rows(
            pool,
            limit,
            day_seed,
            f"platform_picks:{platform['bucket_id']}",
            preserve_quality_order=True,
        )

    series_pool = fetch_home_candidates(
        db,
        where_clause="""
            c.content_type = 'series'
            AND rating_summary.unified_score IS NOT NULL
            AND cwg.content_id IS NOT NULL
        """,
        order_by="""
            ORDER BY
                rating_summary.unified_score DESC NULLS LAST,
                rating_summary.source_count DESC NULLS LAST,
                c.year DESC NULLS LAST,
                c.title ASC
        """,
        pool_limit=pool_limit,
    )
    binge_rows = select_rotated_rows(
        series_pool,
        limit,
        day_seed,
        "binge_worthy_series",
        preserve_quality_order=True,
    )

    section_sources = {
        "weekly_picks": weekly_rows,
        "top_rated": top_rated_rows,
        "recent_releases": recent_rows,
        "mood_pace": mood_rows_by_bucket,
        "platform_picks": platform_rows_by_bucket,
        "binge_worthy_series": binge_rows,
    }
    content_ids = collect_content_ids_from_sections(section_sources)
    platform_map = fetch_home_platforms_for_ids(db, content_ids)
    signal_label_map = fetch_home_signal_labels_for_ids(db, content_ids)

    mood_buckets = []
    for bucket in mood_bucket_defs:
        bucket_id = bucket["bucket_id"]
        mood_buckets.append(
            {
                "bucket_id": bucket_id,
                "label": bucket["label"],
                "subtitle": bucket["subtitle"],
                "refresh_strategy": "daily_bucket_rotation",
                "refresh_cadence": "daily",
                "items": build_home_cards(
                    mood_rows_by_bucket[bucket_id],
                    platform_map,
                    signal_label_map,
                ),
            }
        )

    platform_buckets = []
    platform_lookup = {platform["bucket_id"]: platform for platform in platform_defs}
    for bucket_id, rows in platform_rows_by_bucket.items():
        platform = platform_lookup[bucket_id]
        platform_buckets.append(
            {
                "bucket_id": bucket_id,
                "label": platform["label"],
                "subtitle": f"Strong picks streaming on {platform['label']}.",
                "refresh_strategy": "daily_platform_rotation",
                "refresh_cadence": "daily",
                "items": build_home_cards(rows, platform_map, signal_label_map),
            }
        )

    return {
        "hero": {
            "title": "Find what to watch next",
            "subtitle": "Browse by rating, mood, platform, or watch style.",
            "quick_filters": [
                {"label": "Top Rated", "filter_key": "top_rated"},
                {"label": "Fast-Paced", "filter_key": "fast_paced"},
                {"label": "Dark & Intense", "filter_key": "dark_intense"},
                {"label": "Light Watch", "filter_key": "light_comfort"},
            ],
        },
        "sections": [
            {
                "section_id": "weekly_picks",
                "title": "This Week’s Picks",
                "subtitle": "A fresh weekly mix of strong movies and series.",
                "section_type": "poster_rail",
                "refresh_strategy": "weekly_rotation",
                "refresh_cadence": "weekly",
                "items": build_home_cards(weekly_rows, platform_map, signal_label_map),
            },
            {
                "section_id": "top_rated",
                "title": "Top Rated Picks",
                "subtitle": "High-scoring titles from the catalog, refreshed daily for variety.",
                "section_type": "poster_rail",
                "refresh_strategy": "daily_rotation_from_ranked_pool",
                "refresh_cadence": "daily",
                "items": build_home_cards(top_rated_rows, platform_map, signal_label_map),
            },
            {
                "section_id": "recent_releases",
                "title": "New & Recently Active",
                "subtitle": "Newer movies and recently active series from the catalog.",
                "section_type": "poster_rail",
                "refresh_strategy": "homepage_freshness_order",
                "refresh_cadence": "data_driven",
                "items": build_home_cards(recent_rows, platform_map, signal_label_map),
            },
            {
                "section_id": "mood_pace",
                "title": "Watch by Mood & Pace",
                "subtitle": "Pick something that matches how you want to watch.",
                "section_type": "bucketed_rail",
                "refresh_strategy": "daily_bucket_rotation",
                "refresh_cadence": "daily",
                "buckets": mood_buckets,
            },
            {
                "section_id": "platform_picks",
                "title": "Popular Platforms",
                "subtitle": "Strong picks grouped by where they are available.",
                "section_type": "bucketed_rail",
                "refresh_strategy": "daily_platform_rotation",
                "refresh_cadence": "daily",
                "buckets": platform_buckets,
            },
            {
                "section_id": "binge_worthy_series",
                "title": "Binge-Worthy Series",
                "subtitle": "Highly rated series worth starting.",
                "section_type": "poster_rail",
                "refresh_strategy": "daily_series_rotation",
                "refresh_cadence": "daily",
                "items": build_home_cards(binge_rows, platform_map, signal_label_map),
            },
        ],
        "generated_for": reference_date.isoformat(),
        "refresh_note": (
            "Weekly picks refresh by ISO week. Top-rated, mood, platform, and "
            "series sections rotate deterministically by day; recent releases "
            "follow movie release dates and series freshness metadata."
        ),
    }


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
    video_metadata = get_content_videos(db, content_id)
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
        "videos": video_metadata["videos"],
        "primary_video": video_metadata["primary_video"],
        "series_metadata": series_metadata,
        "insight_summary": insight_summary,
        "decision_layer": decision_layer,
        "summary": summary
    }
