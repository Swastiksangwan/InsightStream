import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "analytics" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_importer():
    path = SCRIPTS_DIR / "import_content_videos_from_preview.py"
    spec = importlib.util.spec_from_file_location("content_video_importer", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def video(key, name="Official Trailer", video_type="Trailer"):
    return {
        "source": "tmdb",
        "source_video_id": key,
        "site": "YouTube",
        "video_type": video_type,
        "name": name,
        "official": True,
        "language_code": "en",
        "country_code": "US",
        "published_at": "2026-01-01T00:00:00Z",
        "size": 1080,
        "is_primary": video_type == "Trailer",
    }


def preview_item(
    source_id,
    videos,
    status="success",
    complete=True,
    stale_cleanup_safe=True,
    title="Video Fixture",
    source_fetched_at="2026-01-01T00:00:00Z",
):
    return {
        "title": title,
        "source_id": source_id,
        "tmdb_id": int(source_id),
        "original_language": "en",
        "videos_preferred_language": "en",
        "videos_requested_languages": ["en", "null"],
        "videos_fetch_status": status,
        "videos_snapshot_complete": complete,
        "videos_stale_cleanup_safe": stale_cleanup_safe,
        "videos_fetch_error": None if complete else "fetch failed",
        "videos_source_fetched_at": source_fetched_at,
        "videos_timestamp_origin": "network",
        "videos_request_signature": "a" * 64,
        "videos_raw_count": len(videos),
        "videos_accepted_count": len(videos),
        "videos_rejected_count": 0,
        "videos_rejected": [],
        "videos_ignored_count": 0,
        "videos_ignored": [],
        "videos_warnings": [],
        "videos_retryable": False,
        "videos_failure_class": "none" if complete else "normalization_review",
        "videos": videos,
    }


def test_preview_and_importer_use_the_same_explicit_primary_language_policy():
    importer = load_importer()
    from tmdb_video_metadata import normalize_video_snapshot

    for index, original_language in enumerate(("ja", "ko"), start=1):
        source_records = [
            {
                "key": f"english_policy{index}",
                "site": "YouTube",
                "type": "Trailer",
                "name": "Official Trailer",
                "official": True,
                "iso_639_1": "en",
            },
            {
                "key": f"source_policy{index}",
                "site": "YouTube",
                "type": "Trailer",
                "name": "Official Trailer",
                "official": True,
                "iso_639_1": original_language,
            },
        ]
        preview = normalize_video_snapshot(
            {"videos": {"results": source_records}},
            preferred_language="en",
        )
        item = preview_item(str(999999000 + index), preview.videos)
        item.update(preview.as_preview_fields())
        item["original_language"] = original_language
        item["videos_preferred_language"] = "en"
        item["videos_requested_languages"] = [
            "en",
            original_language,
            "null",
        ]

        normalized, warnings, safe = importer.normalize_preview_videos(item, "en")
        selected = next(video for video in normalized if video["is_primary"])
        assert warnings == []
        assert safe is True
        assert preview.primary_site == "YouTube"
        assert preview.primary_source_video_id == f"english_policy{index}"
        assert (selected["site"], selected["source_video_id"]) == (
            preview.primary_site,
            preview.primary_source_video_id,
        )


def test_importer_primary_selection_uses_site_and_source_id_identity():
    importer = load_importer()
    from tmdb_video_metadata import normalize_video_snapshot

    snapshot = normalize_video_snapshot(
        {
            "videos": {
                "results": [
                    {
                        "key": "12345678",
                        "site": "Vimeo",
                        "type": "Trailer",
                        "official": True,
                    },
                    {
                        "key": "12345678",
                        "site": "YouTube",
                        "type": "Trailer",
                        "official": True,
                    },
                ]
            }
        }
    )
    item = preview_item("999999010", snapshot.videos)
    item.update(snapshot.as_preview_fields())

    normalized, warnings, safe = importer.normalize_preview_videos(item, "en")
    plan = importer.build_video_plan([], normalized, None)

    assert warnings == []
    assert safe is True
    assert plan.selected_identity == ("YouTube", "12345678")
    assert [
        (entry["site"], entry["source_video_id"])
        for entry in normalized
        if entry["is_primary"]
    ] == [("YouTube", "12345678")]


def test_preview_and_importer_prefer_same_standard_trailer_over_accessibility_variant():
    importer = load_importer()
    from tmdb_video_metadata import normalize_video_snapshot

    snapshot = normalize_video_snapshot(
        {
            "videos": {
                "results": [
                    {
                        "key": "standard4",
                        "site": "YouTube",
                        "type": "Trailer",
                        "name": "Official Trailer",
                        "official": True,
                        "iso_639_1": "en",
                        "published_at": "2025-01-01T00:00:00Z",
                    },
                    {
                        "key": "described3",
                        "site": "YouTube",
                        "type": "Trailer",
                        "name": "Official Trailer [Audio Described]",
                        "official": True,
                        "iso_639_1": "en",
                        "published_at": "2025-02-01T00:00:00Z",
                    },
                ]
            }
        },
        preferred_language="en",
    )
    item = preview_item("999999011", snapshot.videos)
    item.update(snapshot.as_preview_fields())

    normalized, warnings, safe = importer.normalize_preview_videos(item, "en")
    plan = importer.build_video_plan([], normalized, None, preferred_language="en")

    assert warnings == []
    assert safe is True
    preview_primary = (snapshot.primary_site, snapshot.primary_source_video_id)
    assert preview_primary == ("YouTube", "standard4")
    assert plan.selected_identity == preview_primary
    assert len(plan.inserts) == 2
    assert {video["source_video_id"] for video in normalized} == {
        "standard4",
        "described3",
    }


def test_import_timestamp_requires_explicit_timezone():
    importer = load_importer()

    assert importer.parse_timestamp("2026-01-01T10:30:00Z") == datetime(
        2026, 1, 1, 10, 30, tzinfo=timezone.utc
    )
    assert importer.parse_timestamp("2026-01-01T16:00:00+05:30") == datetime(
        2026, 1, 1, 10, 30, tzinfo=timezone.utc
    )
    assert importer.parse_timestamp("2026-01-01T10:30:00") is None
    assert importer.parse_timestamp("not-a-timestamp") is None


def test_video_plan_is_idempotent_and_detects_updates_and_stale_rows():
    importer = load_importer()
    existing = [{"id": 1, **video("video001")}, {"id": 2, **video("stale001")}]
    unchanged = importer.build_video_plan(existing, [video("video001")], ("YouTube", "video001"))
    assert unchanged.inserts == []
    assert unchanged.updates == []
    assert unchanged.stale_ids == [2]
    assert unchanged.primary_changed is False

    changed_video = video("video001", name="Updated Trailer")
    changed = importer.build_video_plan(existing[:1], [changed_video], None)
    assert changed.updates == [changed_video]
    assert changed.primary_changed is True

    unsafe = importer.build_video_plan(
        [{"id": 1, **video("current01", video_type="Teaser")}],
        [video("better001")],
        ("YouTube", "current01"),
        stale_cleanup_safe=False,
    )
    assert unsafe.selected_identity == ("YouTube", "current01")
    assert unsafe.primary_changed is False


def test_apply_is_idempotent_removes_stale_only_after_success_and_preserves_other_source(
    db_session,
):
    importer = load_importer()
    external_id = "999990014"
    content_id = db_session.execute(
        text(
            """
            INSERT INTO content (title, content_type, original_language)
            VALUES ('Neutral Video Import Fixture', 'movie', 'en')
            RETURNING id
            """
        )
    ).scalar_one()
    db_session.execute(
        text(
            """
            INSERT INTO external_ids (content_id, source_name, external_id)
            VALUES (:content_id, 'tmdb', :external_id)
            """
        ),
        {"content_id": content_id, "external_id": external_id},
    )
    db_session.execute(
        text(
            """
            INSERT INTO content_videos (
                content_id, source, source_video_id, site, video_type, name
            ) VALUES (
                :content_id, 'curated', 'curated01', 'YouTube', 'Trailer', 'Curated'
            )
            """
        ),
        {"content_id": content_id},
    )
    db_session.commit()

    fetched_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    item = preview_item(external_id, [video("first001"), video("teaser01", video_type="Teaser")])
    try:
        first = importer.ImportStats(mode="APPLY")
        importer.process_item(db_session, item, fetched_at, True, first)
        db_session.commit()
        assert first.videos_inserted == 2
        assert first.primary_changes == 1

        second = importer.ImportStats(mode="APPLY")
        importer.process_item(db_session, item, fetched_at, True, second)
        db_session.commit()
        assert second.videos_inserted == 0
        assert second.videos_updated == 0
        assert second.videos_removed == 0
        assert second.primary_changes == 0

        reduced = preview_item(external_id, [video("first001")])
        third = importer.ImportStats(mode="APPLY")
        importer.process_item(db_session, reduced, fetched_at, True, third)
        db_session.commit()
        assert third.videos_removed == 1

        failed = preview_item(
            external_id,
            [],
            status="failed",
            complete=False,
            stale_cleanup_safe=False,
            source_fetched_at=None,
        )
        fourth = importer.ImportStats(mode="APPLY")
        importer.process_item(db_session, failed, fetched_at, True, fourth)
        db_session.commit()
        assert fourth.videos_removed == 0

        rows = db_session.execute(
            text(
                """
                SELECT source, source_video_id
                FROM content_videos WHERE content_id = :content_id
                ORDER BY source, source_video_id
                """
            ),
            {"content_id": content_id},
        ).all()
        assert rows == [("curated", "curated01"), ("tmdb", "first001")]
    finally:
        db_session.execute(text("DELETE FROM content WHERE id = :id"), {"id": content_id})
        db_session.commit()


def test_successful_empty_snapshot_removes_tmdb_rows_and_logging_names_title(
    db_session,
    capsys,
):
    importer = load_importer()
    external_id = "999990015"
    content_id = db_session.execute(
        text(
            """
            INSERT INTO content (title, content_type)
            VALUES ('Empty Video Snapshot Fixture', 'series') RETURNING id
            """
        )
    ).scalar_one()
    db_session.execute(
        text(
            """
            INSERT INTO external_ids (content_id, source_name, external_id)
            VALUES (:content_id, 'tmdb', :external_id)
            """
        ),
        {"content_id": content_id, "external_id": external_id},
    )
    db_session.execute(
        text(
            """
            INSERT INTO content_videos (
                content_id, source, source_video_id, site, video_type
            ) VALUES (:content_id, 'tmdb', 'remove001', 'YouTube', 'Trailer')
            """
        ),
        {"content_id": content_id},
    )
    db_session.commit()
    try:
        stats = importer.ImportStats(mode="APPLY")
        importer.process_item(
            db_session,
            preview_item(
                external_id,
                [],
                status="empty",
                title="Empty Video Snapshot Fixture",
            ),
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            True,
            stats,
        )
        db_session.commit()
        importer.print_report(stats)
        output = capsys.readouterr().out
        assert "Empty Video Snapshot Fixture" in output
        assert stats.videos_removed == 1
        assert db_session.execute(
            text("SELECT COUNT(*) FROM content_videos WHERE content_id = :id"),
            {"id": content_id},
        ).scalar_one() == 0
    finally:
        db_session.execute(text("DELETE FROM content WHERE id = :id"), {"id": content_id})
        db_session.commit()


def test_incomplete_snapshots_upsert_accepted_videos_without_deleting_or_clearing_primary(
    db_session,
):
    importer = load_importer()
    external_id = "999990016"
    content_id = db_session.execute(
        text(
            """
            INSERT INTO content (title, content_type, original_language)
            VALUES ('Unsafe Video Snapshot Fixture', 'movie', 'en') RETURNING id
            """
        )
    ).scalar_one()
    db_session.execute(
        text(
            """
            INSERT INTO external_ids (content_id, source_name, external_id)
            VALUES (:content_id, 'tmdb', :external_id)
            """
        ),
        {"content_id": content_id, "external_id": external_id},
    )
    primary_id = db_session.execute(
        text(
            """
            INSERT INTO content_videos (
                content_id, source, source_video_id, site, video_type, name,
                official, language_code
            ) VALUES (
                :content_id, 'tmdb', 'existing1', 'YouTube', 'Trailer',
                'Official Trailer', TRUE, 'en'
            ) RETURNING id
            """
        ),
        {"content_id": content_id},
    ).scalar_one()
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

    try:
        mixed = preview_item(
            external_id,
            [video("accepted1", video_type="Teaser")],
            status="incomplete",
            complete=False,
            stale_cleanup_safe=False,
        )
        mixed["videos_fetch_error"] = "one source record was malformed"
        stats = importer.ImportStats(mode="APPLY")
        importer.process_item(
            db_session,
            mixed,
            datetime(2026, 1, 2, tzinfo=timezone.utc),
            True,
            stats,
        )
        db_session.commit()

        assert db_session.execute(
            text(
                """
                SELECT source_video_id FROM content_videos
                WHERE content_id = :content_id AND source = 'tmdb'
                ORDER BY source_video_id
                """
            ),
            {"content_id": content_id},
        ).scalars().all() == ["accepted1", "existing1"]
        assert db_session.execute(
            text(
                """
                SELECT cv.source_video_id
                FROM content_primary_videos cpv
                JOIN content_videos cv ON cv.id = cpv.content_video_id
                WHERE cpv.content_id = :content_id
                """
            ),
            {"content_id": content_id},
        ).scalar_one() == "existing1"

        all_rejected = preview_item(
            external_id,
            [],
            status="incomplete",
            complete=False,
            stale_cleanup_safe=False,
        )
        all_rejected["videos_raw_count"] = 1
        all_rejected["videos_rejected_count"] = 1
        all_rejected["videos_rejected"] = [
            {"index": 0, "reason": "source video key is empty"}
        ]
        all_rejected["videos_fetch_error"] = "all source records were rejected"
        rejected_stats = importer.ImportStats(mode="APPLY")
        importer.process_item(
            db_session,
            all_rejected,
            datetime(2026, 1, 3, tzinfo=timezone.utc),
            True,
            rejected_stats,
        )
        db_session.commit()
        assert rejected_stats.videos_removed == 0
        assert rejected_stats.primary_changes == 0
        assert db_session.execute(
            text("SELECT COUNT(*) FROM content_videos WHERE content_id = :content_id"),
            {"content_id": content_id},
        ).scalar_one() == 2

        falsely_authoritative = preview_item(
            external_id,
            [],
            status="success",
            complete=True,
            stale_cleanup_safe=True,
        )
        falsely_authoritative.update(
            {
                "videos_raw_count": 1,
                "videos_rejected_count": 1,
                "videos_rejected": [
                    {"index": 0, "reason": "unsupported source site"}
                ],
            }
        )
        spoofed_stats = importer.ImportStats(mode="APPLY")
        importer.process_item(
            db_session,
            falsely_authoritative,
            datetime(2026, 1, 4, tzinfo=timezone.utc),
            True,
            spoofed_stats,
        )
        db_session.commit()
        assert spoofed_stats.videos_removed == 0
        assert spoofed_stats.reports[0]["effective_status"] == "incomplete"
        assert db_session.execute(
            text("SELECT COUNT(*) FROM content_videos WHERE content_id = :content_id"),
            {"content_id": content_id},
        ).scalar_one() == 2
    finally:
        db_session.execute(text("DELETE FROM content WHERE id = :id"), {"id": content_id})
        db_session.commit()


def test_incomplete_snapshot_preserves_primary_from_another_source(db_session):
    importer = load_importer()
    external_id = "999990019"
    content_id = db_session.execute(
        text(
            """
            INSERT INTO content (title, content_type)
            VALUES ('External Primary Fixture', 'movie') RETURNING id
            """
        )
    ).scalar_one()
    db_session.execute(
        text(
            """
            INSERT INTO external_ids (content_id, source_name, external_id)
            VALUES (:content_id, 'tmdb', :external_id)
            """
        ),
        {"content_id": content_id, "external_id": external_id},
    )
    curated_id = db_session.execute(
        text(
            """
            INSERT INTO content_videos (
                content_id, source, source_video_id, site, video_type, official
            ) VALUES (
                :content_id, 'curated', 'curated02', 'YouTube', 'Trailer', TRUE
            ) RETURNING id
            """
        ),
        {"content_id": content_id},
    ).scalar_one()
    db_session.execute(
        text(
            """
            INSERT INTO content_primary_videos (content_id, content_video_id)
            VALUES (:content_id, :video_id)
            """
        ),
        {"content_id": content_id, "video_id": curated_id},
    )
    db_session.commit()

    try:
        item = preview_item(
            external_id,
            [video("accepted2")],
            status="incomplete",
            complete=False,
            stale_cleanup_safe=False,
        )
        stats = importer.ImportStats(mode="APPLY")
        importer.process_item(
            db_session,
            item,
            datetime(2026, 1, 5, tzinfo=timezone.utc),
            True,
            stats,
        )
        db_session.commit()

        primary = db_session.execute(
            text(
                """
                SELECT cv.source, cv.source_video_id
                FROM content_primary_videos cpv
                JOIN content_videos cv ON cv.id = cpv.content_video_id
                WHERE cpv.content_id = :content_id
                """
            ),
            {"content_id": content_id},
        ).one()
        assert primary == ("curated", "curated02")
        assert stats.reports[0]["primary_preserved"] is True
        assert stats.primary_changes == 0
    finally:
        db_session.execute(text("DELETE FROM content WHERE id = :id"), {"id": content_id})
        db_session.commit()


def test_failed_attempt_preserves_previous_successful_fetch_time(db_session):
    importer = load_importer()
    external_id = "999990017"
    content_id = db_session.execute(
        text(
            """
            INSERT INTO content (title, content_type)
            VALUES ('Video Fetch State Fixture', 'movie') RETURNING id
            """
        )
    ).scalar_one()
    db_session.execute(
        text(
            """
            INSERT INTO external_ids (content_id, source_name, external_id)
            VALUES (:content_id, 'tmdb', :external_id)
            """
        ),
        {"content_id": content_id, "external_id": external_id},
    )
    db_session.commit()

    try:
        successful = preview_item(
            external_id,
            [video("state001")],
            source_fetched_at="2026-01-01T10:00:00Z",
        )
        importer.process_item(
            db_session,
            successful,
            datetime(2026, 1, 2, tzinfo=timezone.utc),
            True,
            importer.ImportStats(mode="APPLY"),
        )
        db_session.commit()

        failed = preview_item(
            external_id,
            [],
            status="failed",
            complete=False,
            stale_cleanup_safe=False,
            source_fetched_at=None,
        )
        importer.process_item(
            db_session,
            failed,
            datetime(2026, 1, 3, tzinfo=timezone.utc),
            True,
            importer.ImportStats(mode="APPLY"),
        )
        db_session.commit()

        row = db_session.execute(
            text(
                """
                SELECT last_attempted_at, last_fetched_at, last_fetch_status,
                       source_snapshot_empty, last_fetch_retryable,
                       last_failure_class, consecutive_failure_count
                FROM content_video_fetch_state
                WHERE content_id = :content_id AND source = 'tmdb'
                """
            ),
            {"content_id": content_id},
        ).one()
        assert row.last_attempted_at == datetime(2026, 1, 3, tzinfo=timezone.utc)
        assert row.last_fetched_at == datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
        assert row.last_fetch_status == "failed"
        assert row.source_snapshot_empty is False
        assert row.last_fetch_retryable is False
        assert row.last_failure_class == "normalization_review"
        assert row.consecutive_failure_count == 1
    finally:
        db_session.execute(text("DELETE FROM content WHERE id = :id"), {"id": content_id})
        db_session.commit()


def test_naive_source_timestamp_disables_cleanup_and_preserves_primary_and_fetch_time(
    db_session,
):
    importer = load_importer()
    external_id = "999990020"
    content_id = db_session.execute(
        text(
            """
            INSERT INTO content (title, content_type)
            VALUES ('Naive Video Timestamp Fixture', 'movie') RETURNING id
            """
        )
    ).scalar_one()
    db_session.execute(
        text(
            """
            INSERT INTO external_ids (content_id, source_name, external_id)
            VALUES (:content_id, 'tmdb', :external_id)
            """
        ),
        {"content_id": content_id, "external_id": external_id},
    )
    db_session.commit()

    first_fetched_at = "2026-01-01T10:00:00Z"
    first_attempted_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    unsafe_attempted_at = datetime(2026, 1, 3, tzinfo=timezone.utc)
    try:
        importer.process_item(
            db_session,
            preview_item(
                external_id,
                [video("timezone1")],
                source_fetched_at=first_fetched_at,
            ),
            first_attempted_at,
            True,
            importer.ImportStats(mode="APPLY"),
        )
        db_session.commit()

        naive_empty = preview_item(
            external_id,
            [],
            status="empty",
            source_fetched_at="2026-01-03T10:00:00",
        )
        stats = importer.ImportStats(mode="APPLY")
        importer.process_item(
            db_session,
            naive_empty,
            unsafe_attempted_at,
            True,
            stats,
        )
        db_session.commit()

        assert stats.videos_removed == 0
        assert stats.primary_changes == 0
        assert stats.reports[0]["effective_status"] == "incomplete"
        assert "source fetch timestamp is missing or malformed" in stats.reports[0][
            "reason"
        ]
        primary = db_session.execute(
            text(
                """
                SELECT cv.site, cv.source_video_id
                FROM content_primary_videos cpv
                JOIN content_videos cv ON cv.id = cpv.content_video_id
                WHERE cpv.content_id = :content_id
                """
            ),
            {"content_id": content_id},
        ).one()
        assert primary == ("YouTube", "timezone1")

        state = db_session.execute(
            text(
                """
                SELECT last_attempted_at, last_fetched_at, last_fetch_status
                FROM content_video_fetch_state
                WHERE content_id = :content_id AND source = 'tmdb'
                """
            ),
            {"content_id": content_id},
        ).one()
        assert state.last_attempted_at == unsafe_attempted_at
        assert state.last_fetched_at == datetime(
            2026, 1, 1, 10, tzinfo=timezone.utc
        )
        assert state.last_fetch_status == "incomplete"
    finally:
        db_session.execute(text("DELETE FROM content WHERE id = :id"), {"id": content_id})
        db_session.commit()
