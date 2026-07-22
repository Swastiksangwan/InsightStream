import importlib.util
import sys
from datetime import datetime
from pathlib import Path


def load_tmdb_keywords_importer_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = (
        repo_root / "analytics" / "scripts" / "ingestion" / "import_tmdb_keywords_from_preview.py"
    )
    spec = importlib.util.spec_from_file_location(
        "import_tmdb_keywords_from_preview",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_tmdb_keywords_from_preview"] = module
    spec.loader.exec_module(module)
    return module


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class FakeConnection:
    def __init__(
        self,
        *,
        keyword_source=None,
        provider_keyword=None,
        content_keyword=None,
        content=None,
        provider_keyword_count=0,
        content_keyword_count=0,
    ):
        self.keyword_source = (
            keyword_source
            if keyword_source is not None
            else {
                "id": 44,
                "source_name": "tmdb",
                "display_name": "TMDb",
                "is_active": True,
            }
        )
        self.provider_keyword = provider_keyword
        self.content_keyword = content_keyword
        self.content = (
            content
            if content is not None
            else {"id": 123, "title": "Dune", "content_type": "movie"}
        )
        self.provider_keyword_count = provider_keyword_count
        self.content_keyword_count = content_keyword_count
        self.write_queries = []

    def execute(self, query, params=None):
        query_text = str(query)
        params = params or {}
        if "INSERT INTO keyword_sources" in query_text:
            self.write_queries.append(query_text)
            return FakeResult({"id": 44})
        if "INSERT INTO provider_keywords" in query_text:
            self.write_queries.append(query_text)
            return FakeResult({"id": 88})
        if "INSERT INTO content_keywords" in query_text or "UPDATE " in query_text:
            self.write_queries.append(query_text)
            return FakeResult()
        if "FROM keyword_sources" in query_text and "WHERE source_name" in query_text:
            return FakeResult(self.keyword_source)
        if "FROM provider_keywords" in query_text and "COUNT(*)" in query_text:
            return FakeResult({"total": self.provider_keyword_count})
        if "FROM content_keywords" in query_text and "COUNT(*)" in query_text:
            return FakeResult({"total": self.content_keyword_count})
        if "FROM provider_keywords" in query_text:
            return FakeResult(self.provider_keyword)
        if "FROM content_keywords" in query_text:
            return FakeResult(self.content_keyword)
        if "FROM content" in query_text:
            return FakeResult(
                {
                    "id": params.get("content_id", self.content["id"]),
                    "title": self.content["title"],
                    "content_type": self.content["content_type"],
                }
            )
        return FakeResult()


def preview_payload(items):
    return {
        "generated_at": "2026-06-30T12:00:00+00:00",
        "source": "tmdb_keywords",
        "db_write_performed": False,
        "items": items,
    }


def preview_item(**overrides):
    item = {
        "content_id": 123,
        "title": "Dune",
        "content_type": "movie",
        "tmdb_id": "438631",
        "fetch_status": "success",
        "keyword_count": 1,
        "keywords": [{"keyword_id": 4565, "keyword_name": "dystopia"}],
        "raw_keyword_count": 1,
        "fetched_at": "2026-06-30T12:00:00+00:00",
    }
    item.update(overrides)
    return item


def test_tmdb_keyword_importer_normalizes_keyword_record():
    importer = load_tmdb_keywords_importer_module()
    stats = importer.ImportStats(
        mode="DRY RUN",
        preview_file="preview.json",
        report_output="report.json",
    )

    record = importer.keyword_record_from_raw_keyword(
        {"keyword_id": 4565, "keyword_name": " Dystopia "},
        preview_item(),
        datetime(2026, 6, 30, 12, 0, 0),
        "tmdb-keywords-20260630T120000",
        "report.json",
        stats,
    )

    assert record is not None
    assert record.external_keyword_id == "4565"
    assert record.keyword_name == "Dystopia"
    assert record.normalized_keyword_name == "dystopia"
    assert record.confidence == "medium"
    assert record.raw_payload["tmdb_keyword_id"] == 4565


def test_tmdb_keyword_importer_dedupes_duplicate_keywords():
    importer = load_tmdb_keywords_importer_module()
    stats = importer.ImportStats(
        mode="DRY RUN",
        preview_file="preview.json",
        report_output="report.json",
    )

    records = importer.keyword_records_from_preview_item(
        preview_item(
            keywords=[
                {"keyword_id": 4565, "keyword_name": "dystopia"},
                {"keyword_id": 4565, "keyword_name": "dystopia"},
                {"keyword_id": 9882, "keyword_name": "space"},
            ]
        ),
        datetime(2026, 6, 30, 12, 0, 0),
        "tmdb-keywords-20260630T120000",
        "report.json",
        stats,
    )

    assert [record.external_keyword_id for record in records] == ["4565", "9882"]
    assert stats.duplicate_keywords_deduped == 1


def test_tmdb_keyword_importer_skips_failed_preview_rows():
    importer = load_tmdb_keywords_importer_module()
    conn = FakeConnection()

    stats = importer.process_preview(
        conn,
        preview_payload([preview_item(fetch_status="failed", error_message="timeout")]),
        Path("preview.json"),
        Path("report.json"),
        apply=False,
    )

    assert stats.failed_preview_rows == 1
    assert stats.content_keywords_inserted == 0
    assert conn.write_queries == []


def test_tmdb_keyword_importer_dry_run_does_not_write():
    importer = load_tmdb_keywords_importer_module()
    conn = FakeConnection()

    stats = importer.process_preview(
        conn,
        preview_payload([preview_item()]),
        Path("preview.json"),
        Path("report.json"),
        apply=False,
    )

    assert stats.provider_keywords_inserted == 1
    assert stats.content_keywords_inserted == 1
    assert stats.db_write_performed is False
    assert conn.write_queries == []


def test_tmdb_keyword_importer_apply_writes_keyword_rows():
    importer = load_tmdb_keywords_importer_module()
    conn = FakeConnection()

    stats = importer.process_preview(
        conn,
        preview_payload([preview_item()]),
        Path("preview.json"),
        Path("report.json"),
        apply=True,
    )

    assert stats.provider_keywords_inserted == 1
    assert stats.content_keywords_inserted == 1
    assert any("INSERT INTO provider_keywords" in query for query in conn.write_queries)
    assert any("INSERT INTO content_keywords" in query for query in conn.write_queries)
    assert any("keyword_id" in query for query in conn.write_queries)
    assert not any("provider_keyword_id" in query for query in conn.write_queries)


def test_tmdb_keyword_importer_is_idempotent_when_rows_match():
    importer = load_tmdb_keywords_importer_module()
    seen_at = datetime(2026, 6, 30, 12, 0, 0)
    conn = FakeConnection(
        provider_keyword={
            "id": 88,
            "keyword_name": "dystopia",
            "normalized_keyword_name": "dystopia",
        },
        content_keyword={
            "id": 99,
            "confidence": "medium",
            "raw_payload": {
                "tmdb_id": "438631",
                "tmdb_keyword_id": 4565,
                "keyword_name": "dystopia",
                "preview_generated_at": seen_at.isoformat(),
                "preview_source": "tmdb_keywords",
            },
            "first_seen_at": seen_at,
            "last_seen_at": seen_at,
            "fetched_at": seen_at,
            "source_preview_generated_at": seen_at,
            "import_run_id": "tmdb-keywords-20260630T120000",
            "import_report_path": "report.json",
        },
    )

    stats = importer.process_preview(
        conn,
        preview_payload([preview_item()]),
        Path("preview.json"),
        Path("report.json"),
        apply=False,
    )

    assert stats.provider_keywords_unchanged == 1
    assert stats.content_keywords_unchanged == 1
    assert stats.content_keywords_updated == 0
    assert conn.write_queries == []


def test_tmdb_keyword_importer_refresh_update_preserves_first_seen_at():
    importer = load_tmdb_keywords_importer_module()
    record = importer.KeywordPreviewRecord(
        content_id=123,
        title="Dune",
        content_type="movie",
        tmdb_id="438631",
        external_keyword_id="4565",
        keyword_name="dystopia",
        normalized_keyword_name="dystopia",
        confidence="medium",
        raw_payload={"tmdb_keyword_id": 4565, "keyword_name": "dystopia"},
        first_seen_at=datetime(2026, 6, 30, 12, 0, 0),
        last_seen_at=datetime(2026, 7, 1, 12, 0, 0),
        fetched_at=datetime(2026, 7, 1, 12, 0, 0),
        source_preview_generated_at=datetime(2026, 7, 1, 12, 0, 0),
        import_run_id="tmdb-keywords-20260701T120000",
        import_report_path="new-report.json",
    )

    updates = importer.content_keyword_update_plan(
        {
            "confidence": "medium",
            "raw_payload": {"tmdb_keyword_id": 4565, "keyword_name": "dystopia"},
            "first_seen_at": datetime(2026, 6, 30, 12, 0, 0),
            "last_seen_at": datetime(2026, 6, 30, 12, 0, 0),
            "fetched_at": datetime(2026, 6, 30, 12, 0, 0),
            "source_preview_generated_at": datetime(2026, 6, 30, 12, 0, 0),
            "import_run_id": "tmdb-keywords-20260630T120000",
            "import_report_path": "old-report.json",
        },
        record,
    )

    assert "first_seen_at" not in updates
    assert updates["last_seen_at"] == datetime(2026, 7, 1, 12, 0, 0)
    assert updates["import_report_path"] == "new-report.json"


def test_tmdb_keyword_importer_content_id_filter_does_not_delete_other_rows():
    importer = load_tmdb_keywords_importer_module()
    conn = FakeConnection()

    stats = importer.process_preview(
        conn,
        preview_payload([preview_item(content_id=123), preview_item(content_id=456)]),
        Path("preview.json"),
        Path("report.json"),
        apply=True,
        content_id_filter={123},
    )

    assert stats.content_rows_selected == 1
    assert not any("DELETE" in query.upper() for query in conn.write_queries)
