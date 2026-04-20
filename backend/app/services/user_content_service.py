from sqlalchemy.orm import Session
from sqlalchemy import text
from app.services.content_service import build_content_object


def check_user_exists(user_id: int, db: Session):
    query = text("""
        SELECT id
        FROM users
        WHERE id = :user_id;
    """)
    result = db.execute(query, {"user_id": user_id})
    return result.mappings().first()


def add_to_watch_later_service(user_id: int, content_id: int, db: Session):
    user_row = check_user_exists(user_id, db)
    if not user_row:
        return {"error": "User not found"}

    content_check_query = text("""
        SELECT id
        FROM content
        WHERE id = :content_id;
    """)
    content_result = db.execute(content_check_query, {"content_id": content_id})
    content_row = content_result.mappings().first()

    if not content_row:
        return {"error": "Content not found"}

    watched_check_query = text("""
        SELECT id
        FROM watched
        WHERE user_id = :user_id AND content_id = :content_id;
    """)
    watched_result = db.execute(watched_check_query, {
        "user_id": user_id,
        "content_id": content_id
    })
    watched_row = watched_result.mappings().first()

    if watched_row:
        return {"error": "Content is already in watched"}

    existing_query = text("""
        SELECT id
        FROM watch_later
        WHERE user_id = :user_id AND content_id = :content_id;
    """)
    existing_result = db.execute(existing_query, {
        "user_id": user_id,
        "content_id": content_id
    })
    existing_row = existing_result.mappings().first()

    if existing_row:
        return {"error": "Content is already in watch later"}

    insert_query = text("""
        INSERT INTO watch_later (user_id, content_id)
        VALUES (:user_id, :content_id);
    """)
    db.execute(insert_query, {
        "user_id": user_id,
        "content_id": content_id
    })
    db.commit()

    return {"message": "Added to watch later"}


def add_to_watched_service(user_id: int, content_id: int, db: Session):
    user_row = check_user_exists(user_id, db)
    if not user_row:
        return {"error": "User not found"}

    content_check_query = text("""
        SELECT id
        FROM content
        WHERE id = :content_id;
    """)
    content_result = db.execute(content_check_query, {"content_id": content_id})
    content_row = content_result.mappings().first()

    if not content_row:
        return {"error": "Content not found"}

    existing_query = text("""
        SELECT id
        FROM watched
        WHERE user_id = :user_id AND content_id = :content_id;
    """)
    existing_result = db.execute(existing_query, {
        "user_id": user_id,
        "content_id": content_id
    })
    existing_row = existing_result.mappings().first()

    if existing_row:
        return {"error": "Content is already in watched"}

    delete_watch_later_query = text("""
        DELETE FROM watch_later
        WHERE user_id = :user_id AND content_id = :content_id;
    """)
    db.execute(delete_watch_later_query, {
        "user_id": user_id,
        "content_id": content_id
    })

    insert_query = text("""
        INSERT INTO watched (user_id, content_id)
        VALUES (:user_id, :content_id);
    """)
    db.execute(insert_query, {
        "user_id": user_id,
        "content_id": content_id
    })
    db.commit()

    return {"message": "Added to watched"}


def get_watch_later_service(user_id: int, db: Session):
    user_row = check_user_exists(user_id, db)
    if not user_row:
        return {"error": "User not found"}

    query = text("""
        SELECT
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
        FROM watch_later wl
        JOIN content c ON wl.content_id = c.id
        WHERE wl.user_id = :user_id
        ORDER BY wl.added_at DESC;
    """)
    result = db.execute(query, {"user_id": user_id})
    rows = result.mappings().all()

    return [build_content_object(row) for row in rows]


def get_watched_service(user_id: int, db: Session):
    user_row = check_user_exists(user_id, db)
    if not user_row:
        return {"error": "User not found"}

    query = text("""
        SELECT
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
        FROM watched w
        JOIN content c ON w.content_id = c.id
        WHERE w.user_id = :user_id
        ORDER BY w.watched_at DESC;
    """)
    result = db.execute(query, {"user_id": user_id})
    rows = result.mappings().all()

    return [build_content_object(row) for row in rows]


def remove_from_watch_later_service(user_id: int, content_id: int, db: Session):
    user_row = check_user_exists(user_id, db)
    if not user_row:
        return {"error": "User not found"}

    existing_query = text("""
        SELECT id
        FROM watch_later
        WHERE user_id = :user_id AND content_id = :content_id;
    """)
    existing_result = db.execute(existing_query, {
        "user_id": user_id,
        "content_id": content_id
    })
    existing_row = existing_result.mappings().first()

    if not existing_row:
        return {"error": "Content is not in watch later"}

    delete_query = text("""
        DELETE FROM watch_later
        WHERE user_id = :user_id AND content_id = :content_id;
    """)
    db.execute(delete_query, {
        "user_id": user_id,
        "content_id": content_id
    })
    db.commit()

    return {"message": "Removed from watch later"}


def remove_from_watched_service(user_id: int, content_id: int, db: Session):
    user_row = check_user_exists(user_id, db)
    if not user_row:
        return {"error": "User not found"}

    existing_query = text("""
        SELECT id
        FROM watched
        WHERE user_id = :user_id AND content_id = :content_id;
    """)
    existing_result = db.execute(existing_query, {
        "user_id": user_id,
        "content_id": content_id
    })
    existing_row = existing_result.mappings().first()

    if not existing_row:
        return {"error": "Content is not in watched"}

    delete_query = text("""
        DELETE FROM watched
        WHERE user_id = :user_id AND content_id = :content_id;
    """)
    db.execute(delete_query, {
        "user_id": user_id,
        "content_id": content_id
    })
    db.commit()

    return {"message": "Removed from watched"}