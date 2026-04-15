from sqlalchemy.orm import Session
from sqlalchemy import text


def add_to_watch_later_service(user_id: int, content_id: int, db: Session):
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
        FROM watch_later
        WHERE user_id = :user_id AND content_id = :content_id;
    """)
    existing_result = db.execute(existing_query, {
        "user_id": user_id,
        "content_id": content_id
    })
    existing_row = existing_result.mappings().first()

    if existing_row:
        return {"message": "Already in watch later"}

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
        return {"message": "Already in watched"}

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