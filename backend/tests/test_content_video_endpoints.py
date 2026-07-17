import pytest
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


REPO_ROOT = Path(__file__).resolve().parents[2]


def create_content(db_session, title):
    content_id = db_session.execute(
        text(
            """
            INSERT INTO content (title, content_type, original_language)
            VALUES (:title, 'movie', 'en') RETURNING id
            """
        ),
        {"title": title},
    ).scalar_one()
    db_session.commit()
    return content_id


def test_content_details_return_only_ordered_trailers_and_teasers(client, db_session):
    content_id = create_content(db_session, "Neutral Video API Fixture")
    other_content_id = create_content(db_session, "Other Video API Fixture")
    try:
        primary_id = db_session.execute(
            text(
                """
                INSERT INTO content_videos (
                    content_id, source, source_video_id, site, video_type, name,
                    official, language_code, published_at
                ) VALUES (
                    :content_id, 'tmdb', 'primary01', 'YouTube', 'Trailer',
                    'Official Trailer', TRUE, 'en', '2026-01-02T00:00:00Z'
                ) RETURNING id
                """
            ),
            {"content_id": content_id},
        ).scalar_one()
        db_session.execute(
            text(
                """
                INSERT INTO content_videos (
                    content_id, source, source_video_id, site, video_type, name
                ) VALUES
                    (:content_id, 'tmdb', 'teaser001', 'YouTube', 'Teaser', 'Teaser'),
                    (:content_id, 'tmdb', 'teaser002', 'YouTube', 'tEaSeR', 'Second Teaser'),
                    (:content_id, 'tmdb', '12345678', 'Vimeo', 'Trailer', 'Vimeo Trailer'),
                    (:content_id, 'tmdb', 'clip0001', 'YouTube', 'Clip', 'Clip'),
                    (:content_id, 'tmdb', 'feature1', 'YouTube', 'Featurette', 'Featurette'),
                    (:content_id, 'tmdb', 'behind01', 'YouTube', 'Behind the Scenes', 'Behind'),
                    (:content_id, 'tmdb', 'blooper1', 'YouTube', 'Bloopers', 'Bloopers'),
                    (:content_id, 'tmdb', 'opening1', 'YouTube', 'Opening Credits', 'Opening')
                """
            ),
            {"content_id": content_id},
        )
        db_session.execute(
            text(
                """
                INSERT INTO content_videos (
                    content_id, source, source_video_id, site, video_type, name
                ) VALUES (
                    :content_id, 'tmdb', 'other001', 'YouTube', 'Trailer',
                    'Other Content Trailer'
                )
                """
            ),
            {"content_id": other_content_id},
        )
        db_session.execute(
            text(
                """
                INSERT INTO content_primary_videos (content_id, content_video_id)
                VALUES (:content_id, :video_id)
                """
            ),
            {"content_id": content_id, "video_id": primary_id},
        )
        db_session.commit()

        response = client.get(f"/content/{content_id}/details")
        assert response.status_code == 200
        data = response.json()
        assert [video["source_video_id"] for video in data["videos"]] == [
            "primary01",
            "12345678",
            "teaser001",
            "teaser002",
        ]
        assert len(data["videos"]) == 4
        assert db_session.execute(
            text("SELECT COUNT(*) FROM content_videos WHERE content_id = :content_id"),
            {"content_id": content_id},
        ).scalar_one() == 9
        assert {
            video["type"].casefold() for video in data["videos"]
        } == {"trailer", "teaser"}
        assert "other001" not in {
            video["source_video_id"] for video in data["videos"]
        }
        assert data["primary_video"]["source_video_id"] == "primary01"
        assert data["videos"][0] == data["primary_video"]
        assert data["primary_video"]["watch_url"] == (
            "https://www.youtube.com/watch?v=primary01"
        )
        assert data["primary_video"]["embed_url"] == (
            "https://www.youtube-nocookie.com/embed/primary01"
        )
        vimeo = next(video for video in data["videos"] if video["site"] == "Vimeo")
        assert vimeo["watch_url"] is None
        assert vimeo["embed_url"] is None
        assert vimeo["is_playable"] is False
        assert data["primary_video"]["is_playable"] is True
        assert "source_payload" not in data["primary_video"]
        assert data["content"]["title"] == "Neutral Video API Fixture"
    finally:
        db_session.execute(
            text("DELETE FROM content WHERE id IN (:content_id, :other_content_id)"),
            {
                "content_id": content_id,
                "other_content_id": other_content_id,
            },
        )
        db_session.commit()


def test_primary_video_must_belong_to_same_content_and_cascades_on_video_delete(
    db_session,
):
    first_content_id = create_content(db_session, "Primary Ownership Fixture A")
    second_content_id = create_content(db_session, "Primary Ownership Fixture B")
    video_id = db_session.execute(
        text(
            """
            INSERT INTO content_videos (
                content_id, source, source_video_id, site, video_type
            ) VALUES (
                :content_id, 'tmdb', 'owned001', 'YouTube', 'Trailer'
            ) RETURNING id
            """
        ),
        {"content_id": second_content_id},
    ).scalar_one()
    db_session.commit()
    try:
        with pytest.raises(IntegrityError):
            db_session.execute(
                text(
                    """
                    INSERT INTO content_primary_videos (content_id, content_video_id)
                    VALUES (:content_id, :video_id)
                    """
                ),
                {"content_id": first_content_id, "video_id": video_id},
            )
            db_session.commit()
        db_session.rollback()

        db_session.execute(
            text(
                """
                INSERT INTO content_primary_videos (content_id, content_video_id)
                VALUES (:content_id, :video_id)
                """
            ),
            {"content_id": second_content_id, "video_id": video_id},
        )
        db_session.commit()
        db_session.execute(
            text("DELETE FROM content_videos WHERE id = :video_id"),
            {"video_id": video_id},
        )
        db_session.commit()
        assert db_session.execute(
            text(
                "SELECT COUNT(*) FROM content_primary_videos WHERE content_id = :id"
            ),
            {"id": second_content_id},
        ).scalar_one() == 0
    finally:
        db_session.execute(
            text("DELETE FROM content WHERE id IN (:first_id, :second_id)"),
            {"first_id": first_content_id, "second_id": second_content_id},
        )
        db_session.commit()


def test_content_details_without_videos_returns_empty_additive_shape(client, db_session):
    content_id = create_content(db_session, "No Video API Fixture")
    try:
        response = client.get(f"/content/{content_id}/details")
        assert response.status_code == 200
        data = response.json()
        assert data["videos"] == []
        assert data["primary_video"] is None
        assert "genres" in data
        assert "ratings" in data
        assert "insight_summary" in data
    finally:
        db_session.execute(text("DELETE FROM content WHERE id = :id"), {"id": content_id})
        db_session.commit()


def test_video_hardening_migration_is_idempotent_and_schema_matches(db_session):
    migration_sql = (
        REPO_ROOT / "backend" / "migrations" / "014_add_content_video_metadata.sql"
    ).read_text(encoding="utf-8")
    db_session.connection().exec_driver_sql(migration_sql)
    db_session.commit()
    db_session.connection().exec_driver_sql(migration_sql)
    db_session.commit()

    columns = set(
        db_session.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'content_video_fetch_state'
                """
            )
        ).scalars()
    )
    constraints = set(
        db_session.execute(
            text(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid IN (
                    'content_videos'::regclass,
                    'content_primary_videos'::regclass,
                    'content_video_fetch_state'::regclass
                )
                """
            )
        ).scalars()
    )
    indexes = set(
        db_session.execute(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename IN ('content_videos', 'content_video_fetch_state')
                """
            )
        ).scalars()
    )
    assert {"last_attempted_at", "last_fetched_at"} <= columns
    assert "fk_content_primary_videos_owned_video" in constraints
    assert "uq_content_videos_content_id_id" in constraints
    assert "chk_content_video_fetch_state_empty_status" in constraints
    assert "idx_content_videos_content_id" not in indexes
    assert "idx_content_videos_content_source" not in indexes
    assert "idx_content_video_fetch_state_status" not in indexes


def test_video_hardening_migration_preserves_existing_rows(db_session):
    content_id = create_content(db_session, "Migration Preservation Video Fixture")
    video_id = db_session.execute(
        text(
            """
            INSERT INTO content_videos (
                content_id, source, source_video_id, site, video_type
            ) VALUES (
                :content_id, 'tmdb', 'preserve01', 'YouTube', 'Trailer'
            ) RETURNING id
            """
        ),
        {"content_id": content_id},
    ).scalar_one()
    db_session.commit()
    try:
        migration_sql = (
            REPO_ROOT / "backend" / "migrations" / "014_add_content_video_metadata.sql"
        ).read_text(encoding="utf-8")
        db_session.connection().exec_driver_sql(migration_sql)
        db_session.commit()
        assert db_session.execute(
            text(
                """
                SELECT source_video_id FROM content_videos
                WHERE content_id = :content_id AND id = :video_id
                """
            ),
            {"content_id": content_id, "video_id": video_id},
        ).scalar_one() == "preserve01"
    finally:
        db_session.execute(text("DELETE FROM content WHERE id = :id"), {"id": content_id})
        db_session.commit()


def test_fetch_state_rejects_inconsistent_empty_flag(db_session):
    content_id = create_content(db_session, "Fetch State Constraint Fixture")
    try:
        with pytest.raises(IntegrityError):
            db_session.execute(
                text(
                    """
                    INSERT INTO content_video_fetch_state (
                        content_id, source, last_fetch_status, source_snapshot_empty
                    ) VALUES (:content_id, 'tmdb', 'empty', FALSE)
                    """
                ),
                {"content_id": content_id},
            )
            db_session.commit()
        db_session.rollback()
    finally:
        db_session.execute(text("DELETE FROM content WHERE id = :id"), {"id": content_id})
        db_session.commit()


def test_schema_rebuild_declares_final_video_integrity_rules():
    schema_sql = (REPO_ROOT / "backend" / "schema.sql").read_text(encoding="utf-8")
    assert "uq_content_videos_content_id_id UNIQUE (content_id, id)" in schema_sql
    assert "fk_content_primary_videos_owned_video" in schema_sql
    assert "REFERENCES content_videos(content_id, id) ON DELETE CASCADE" in schema_sql
    assert "chk_content_video_fetch_state_empty_status" in schema_sql
