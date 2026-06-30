import importlib.util
import sys
from pathlib import Path


def load_merge_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "analytics" / "scripts" / "merge_tmdb_keywords_retry_preview.py"
    spec = importlib.util.spec_from_file_location(
        "merge_tmdb_keywords_retry_preview",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["merge_tmdb_keywords_retry_preview"] = module
    spec.loader.exec_module(module)
    return module


def success_item(content_id=1, title="Inception", content_type="movie", tmdb_id="27205"):
    return {
        "content_id": content_id,
        "title": title,
        "content_type": content_type,
        "tmdb_id": tmdb_id,
        "fetch_status": "success",
        "keyword_count": 1,
        "keywords": [{"keyword_id": 5565, "keyword_name": "dream"}],
        "raw_keyword_count": 1,
        "attempt_count": 2,
        "retry_performed": True,
        "retry_attempts_performed": 1,
        "fetched_at": "2026-06-30T00:00:00+00:00",
    }


def failed_item(
    content_id=1,
    title="Inception",
    content_type="movie",
    tmdb_id="27205",
    error_message="timeout",
):
    return {
        "content_id": content_id,
        "title": title,
        "content_type": content_type,
        "tmdb_id": tmdb_id,
        "fetch_status": "failed",
        "error_status_code": None,
        "error_message": error_message,
        "attempt_count": 3,
        "retry_performed": True,
        "retry_attempts_performed": 2,
        "fetched_at": "2026-06-30T00:00:00+00:00",
    }


def test_merge_replaces_failed_row_with_successful_retry_row():
    module = load_merge_module()
    merged, merged_successful, unresolved = module.merge_preview_items(
        [failed_item(), success_item(content_id=2, title="Dune", tmdb_id="438631")],
        [success_item()],
    )

    assert merged_successful == 1
    assert unresolved == 0
    assert merged[0]["fetch_status"] == "success"
    assert [item["content_id"] for item in merged] == [1, 2]


def test_merge_preserves_unresolved_retry_failure():
    module = load_merge_module()
    retry_failure = failed_item(error_message="still timed out")

    merged, merged_successful, unresolved = module.merge_preview_items(
        [failed_item()],
        [retry_failure],
    )

    assert merged_successful == 0
    assert unresolved == 1
    assert merged == [retry_failure]


def test_merge_avoids_duplicate_content_ids():
    module = load_merge_module()
    merged, _, _ = module.merge_preview_items(
        [failed_item(), failed_item()],
        [success_item()],
    )

    assert len(merged) == 1
    assert merged[0]["fetch_status"] == "success"


def test_merge_recalculates_report_counters(tmp_path):
    module = load_merge_module()
    items = [
        success_item(),
        success_item(content_id=2, title="Breaking Bad", content_type="series", tmdb_id="1396"),
        failed_item(content_id=3, title="Missing", tmdb_id="999"),
    ]
    report = module.build_merged_report(
        {
            "generated_at": "2026-06-30T00:00:00+00:00",
            "total_local_titles_checked": 3,
            "warnings": [],
        },
        items,
        tmp_path / "tmdb_keywords_preview.json",
        tmp_path / "tmdb_keywords_report.json",
        {
            "merged_retry_at": "2026-06-30T01:00:00+00:00",
            "merged_successful_retry_items": 2,
            "unresolved_retry_failures": 1,
            "merged_retry_source_preview": "retry-preview.json",
            "merged_retry_source_report": "retry-report.json",
        },
    )

    assert report["successful_fetches"] == 2
    assert report["failed_fetches"] == 1
    assert report["titles_with_keywords"] == 2
    assert report["titles_with_zero_keywords"] == 0
    assert report["total_keywords_fetched"] == 2
    assert report["unique_keywords"] == 1
    assert report["movie_successful_fetches"] == 1
    assert report["series_successful_fetches"] == 1
    assert report["errors_by_status_code"] == {"unknown": 1}
    assert report["merged_successful_retry_items"] == 2


def test_cleanup_deletes_temp_files_but_never_main_paths(tmp_path):
    module = load_merge_module()
    main_preview = tmp_path / "tmdb_keywords_preview.json"
    main_report = tmp_path / "tmdb_keywords_report.json"
    retry_preview = tmp_path / "tmdb_keywords_retry_preview.json"
    backup_preview = tmp_path / "tmdb_keywords_preview.before_retry_merge.json"
    for path in [main_preview, main_report, retry_preview, backup_preview]:
        path.write_text("{}", encoding="utf-8")

    deleted = module.cleanup_temp_files(
        [main_preview, main_report, retry_preview, backup_preview],
        [main_preview, main_report],
        allow_cleanup=True,
    )

    assert sorted(path.name for path in deleted) == [
        "tmdb_keywords_preview.before_retry_merge.json",
        "tmdb_keywords_retry_preview.json",
    ]
    assert main_preview.exists()
    assert main_report.exists()
    assert not retry_preview.exists()
    assert not backup_preview.exists()


def test_cleanup_skips_when_not_allowed(tmp_path):
    module = load_merge_module()
    temp_file = tmp_path / "tmdb_keywords_retry_preview.json"
    temp_file.write_text("{}", encoding="utf-8")

    deleted = module.cleanup_temp_files(
        [temp_file],
        [],
        allow_cleanup=False,
    )

    assert deleted == []
    assert temp_file.exists()
