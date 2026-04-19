from sqlalchemy.orm import Session
from sqlalchemy import text


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
    search: str = None
):
    base_query = """
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
        FROM content
    """

    conditions = []
    params = {}

    if content_type:
        conditions.append("content_type = :content_type")
        params["content_type"] = content_type

    if search:
        conditions.append("title ILIKE :search")
        params["search"] = f"%{search}%"

    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)

    base_query += " ORDER BY release_date DESC;"

    query = text(base_query)
    result = db.execute(query, params)
    rows = result.mappings().all()

    return [build_content_object(row) for row in rows]


def get_content_by_id_service(content_id: int, db: Session):
    query = text("""
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
        FROM content
        WHERE id = :content_id;
    """)
    result = db.execute(query, {"content_id": content_id})
    row = result.mappings().first()

    if not row:
        return None

    return build_content_object(row)


def get_content_details_service(content_id: int, db: Session):
    content_query = text("""
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
        FROM content
        WHERE id = :content_id;
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
            p.name AS platform_name,
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
            p.name AS platform_name,
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