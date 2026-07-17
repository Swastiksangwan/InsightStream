from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


YOUTUBE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


def safe_video_urls(site: str, source_video_id: str) -> tuple[str | None, str | None]:
    if site != "YouTube" or not YOUTUBE_KEY_PATTERN.fullmatch(source_video_id):
        return None, None
    return (
        f"https://www.youtube.com/watch?v={source_video_id}",
        f"https://www.youtube-nocookie.com/embed/{source_video_id}",
    )


def get_content_videos(db: Session, content_id: int) -> dict[str, Any]:
    rows = db.execute(
        text(
            """
            SELECT
                cv.id,
                cv.source,
                cv.source_video_id,
                cv.site,
                cv.video_type,
                cv.name,
                cv.official,
                cv.language_code,
                cv.country_code,
                cv.published_at,
                cv.size,
                (cpv.content_video_id = cv.id) AS is_primary
            FROM content_videos cv
            LEFT JOIN content_primary_videos cpv
              ON cpv.content_id = cv.content_id
            WHERE cv.content_id = :content_id
              AND LOWER(COALESCE(cv.video_type, '')) IN ('trailer', 'teaser')
            ORDER BY
                (cpv.content_video_id = cv.id) DESC,
                CASE
                    WHEN LOWER(COALESCE(cv.video_type, '')) = 'trailer'
                         AND cv.official IS TRUE THEN 0
                    WHEN LOWER(COALESCE(cv.video_type, '')) = 'teaser'
                         AND cv.official IS TRUE THEN 1
                    WHEN LOWER(COALESCE(cv.video_type, '')) = 'trailer' THEN 2
                    WHEN LOWER(COALESCE(cv.video_type, '')) = 'teaser' THEN 3
                    ELSE 4
                END,
                cv.published_at DESC NULLS LAST,
                cv.source_video_id ASC,
                cv.id ASC
            """
        ),
        {"content_id": content_id},
    ).mappings().all()

    videos: list[dict[str, Any]] = []
    primary_video = None
    for row in rows:
        watch_url, embed_url = safe_video_urls(
            str(row["site"]),
            str(row["source_video_id"]),
        )
        video = {
            "id": row["id"],
            "source": row["source"],
            "source_video_id": row["source_video_id"],
            "site": row["site"],
            "type": row["video_type"],
            "name": row["name"],
            "official": row["official"],
            "language_code": row["language_code"],
            "country_code": row["country_code"],
            "published_at": row["published_at"],
            "size": row["size"],
            "is_primary": bool(row["is_primary"]),
            "watch_url": watch_url,
            "embed_url": embed_url,
            "is_playable": embed_url is not None,
        }
        videos.append(video)
        if video["is_primary"]:
            primary_video = video

    return {"videos": videos, "primary_video": primary_video}
