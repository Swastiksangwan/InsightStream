import importlib.util
import sys
from pathlib import Path


def load_source_signal_importer_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = (
        repo_root / "analytics" / "scripts" / "import_source_signals_from_preview.py"
    )
    spec = importlib.util.spec_from_file_location(
        "import_source_signals_from_preview",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_source_signals_from_preview"] = module
    spec.loader.exec_module(module)
    return module


class FakeResult:
    def __init__(self, rows=None, row=None):
        self.rows = rows if rows is not None else []
        self.row = row

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        if self.row is not None:
            return self.row
        return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(
        self,
        *,
        content_rows=None,
        existing_signals=None,
        existing_guidance=None,
        ready_count=1,
    ):
        self.content_rows = content_rows if content_rows is not None else [
            {"id": 123, "title": "Dune", "content_type": "movie"},
            {"id": 456, "title": "Spare", "content_type": "movie"},
        ]
        self.existing_signals = existing_signals if existing_signals is not None else []
        self.existing_guidance = existing_guidance if existing_guidance is not None else []
        self.ready_count = ready_count
        self.write_queries = []
        self.write_params = []

    def execute(self, query, params=None):
        query_text = str(query)
        params = params or {}
        if "SELECT id, title, content_type" in query_text and "FROM content" in query_text:
            return FakeResult(rows=self.content_rows)
        if "COUNT(DISTINCT c.id) AS total" in query_text:
            return FakeResult(row={"total": self.ready_count})
        if "FROM content_source_signals" in query_text and "WHERE content_id = ANY" in query_text:
            selected = set(params.get("content_ids") or [])
            rows = [
                row
                for row in self.existing_signals
                if row["content_id"] in selected
            ]
            return FakeResult(rows=rows)
        if "FROM content_watch_guidance" in query_text and "WHERE content_id = ANY" in query_text:
            selected = set(params.get("content_ids") or [])
            rows = [
                row
                for row in self.existing_guidance
                if row["content_id"] in selected
            ]
            return FakeResult(rows=rows)
        if "INSERT INTO source_signal_import_runs" in query_text:
            self.write_queries.append(query_text)
            self.write_params.append(params)
            return FakeResult(row={"id": 9001})
        if (
            "INSERT INTO content_source_signals" in query_text
            or "DELETE FROM content_source_signals" in query_text
            or "INSERT INTO content_watch_guidance" in query_text
        ):
            self.write_queries.append(query_text)
            self.write_params.append(params)
            return FakeResult()
        return FakeResult()


def preview_payload(items):
    return {
        "generated_at": "2026-07-02T12:00:00+00:00",
        "source": "tmdb_keyword_signal_preview",
        "db_write_performed": False,
        "mapping_version": "2026-07-02-v3.1",
        "items": items,
    }


def report_payload(**overrides):
    report = {
        "generated_at": "2026-07-02T12:01:00+00:00",
        "db_write_performed": False,
        "mapping_version": "2026-07-02-v3.1",
        "override_version": "2026-07-02-v3.1",
        "preview_generator_version": "2026-07-02-v3.2.1",
        "semantic_qa_version": "2026-07-02-v3.2.1",
        "titles_seen": 1,
        "semantic_quality_summary": {
            "generic_watch_feel_count": 0,
            "semantic_conflict_count": 0,
            "curated_review_candidate_count": 0,
        },
        "coverage_by_content_type": {"movie": {"titles_seen": 1}},
        "signals_by_source": {"tmdb_keywords": 2},
        "errors": [],
        "warnings": [],
    }
    report.update(overrides)
    return report


def preview_item(**overrides):
    item = {
        "content_id": 123,
        "title": "Dune",
        "content_type": "movie",
        "mapping_version": "2026-07-02-v3.1",
        "keyword_counts": {"raw_keywords": 2, "mapped_keywords": 2},
        "signals": {
            "audience_expectation": [
                {
                    "value": "space sci-fi",
                    "label": "Space sci-fi",
                    "confidence": "medium",
                    "sources": ["tmdb_keywords"],
                }
            ],
            "mood": [
                {
                    "value": "tense",
                    "label": "Tense",
                    "confidence": "medium",
                    "sources": ["tmdb_keywords"],
                }
            ],
        },
        "watch_guidance": {
            "watch_feel": "A tense space sci-fi.",
            "chips": ["Space sci-fi", "Tense"],
            "best_for": ["Space sci-fi"],
            "consider_first": [],
        },
        "curated_override_applied": False,
        "metadata_fallback_applied": False,
    }
    item.update(overrides)
    return item


def build_plan(importer, conn=None, preview=None, report=None, **kwargs):
    return importer.build_import_plan(
        conn or FakeConnection(),
        preview or preview_payload([preview_item()]),
        report or report_payload(),
        Path("preview.json"),
        Path("source_report.json"),
        Path("import_report.json"),
        **{
            "write_requested": False,
            "allow_semantic_qa_issues": False,
            "allow_partial_preview": False,
            "content_type_filter": "all",
            "content_id_filter": None,
            **kwargs,
        },
    )


def matching_existing_signal():
    return {
        "id": 77,
        "content_id": 123,
        "dimension": "audience_expectation",
        "value": "space sci-fi",
        "label": "Space sci-fi",
        "confidence": "medium",
        "source_names": ["tmdb_keywords"],
        "source_payload": {
            "mapping_version": "2026-07-02-v3.1",
            "override_version": "2026-07-02-v3.1",
            "preview_generator_version": "2026-07-02-v3.2.1",
            "semantic_qa_version": "2026-07-02-v3.2.1",
            "content_type": "movie",
            "curated_override_applied": False,
            "metadata_fallback_applied": False,
        },
        "is_active": True,
    }


def matching_existing_guidance():
    return {
        "content_id": 123,
        "watch_feel": "A tense space sci-fi.",
        "chips": ["Space sci-fi", "Tense"],
        "best_for": ["Space sci-fi"],
        "consider_first": [],
        "keyword_counts": {"raw_keywords": 2, "mapped_keywords": 2},
        "signal_sources": ["tmdb_keywords"],
        "curated_override_applied": False,
        "metadata_fallback_applied": False,
        "storage_ready": True,
        "frontend_ready": False,
        "quality_summary": {"mapping_version": "2026-07-02-v3.1"},
    }


def test_source_signal_importer_dry_run_does_not_write():
    importer = load_source_signal_importer_module()
    conn = FakeConnection()

    plan = build_plan(importer, conn=conn)

    assert plan.signals_to_insert == 2
    assert plan.guidance_to_insert == 1
    assert plan.db_write_performed is False
    assert conn.write_queries == []


def test_source_signal_importer_write_imports_signals_and_guidance():
    importer = load_source_signal_importer_module()
    conn = FakeConnection()
    plan = build_plan(importer, conn=conn, write_requested=True)

    importer.apply_import_plan(conn, plan, Path("preview.json"), Path("report.json"))

    assert plan.db_write_performed is True
    assert plan.run_id == 9001
    assert any("INSERT INTO source_signal_import_runs" in query for query in conn.write_queries)
    assert any("INSERT INTO content_source_signals" in query for query in conn.write_queries)
    assert any("INSERT INTO content_watch_guidance" in query for query in conn.write_queries)


def test_source_signal_importer_is_idempotent_when_rows_match():
    importer = load_source_signal_importer_module()
    conn = FakeConnection(
        existing_signals=[
            matching_existing_signal(),
            {
                **matching_existing_signal(),
                "id": 78,
                "dimension": "mood",
                "value": "tense",
                "label": "Tense",
            },
        ],
        existing_guidance=[matching_existing_guidance()],
    )

    plan = build_plan(importer, conn=conn)

    assert plan.signals_to_insert == 0
    assert plan.signals_to_update == 0
    assert plan.signals_unchanged == 2
    assert plan.guidance_to_insert == 0
    assert plan.guidance_to_update == 0
    assert plan.guidance_unchanged == 1


def test_source_signal_importer_deletes_obsolete_selected_signals():
    importer = load_source_signal_importer_module()
    conn = FakeConnection(
        existing_signals=[
            matching_existing_signal(),
            {
                **matching_existing_signal(),
                "id": 79,
                "dimension": "tone",
                "value": "obsolete",
                "label": "Obsolete",
            },
        ],
    )

    plan = build_plan(importer, conn=conn)

    assert plan.signals_to_delete_or_deactivate == 1
    assert plan.obsolete_signal_ids == [79]


def test_source_signal_partial_import_fails_without_allow_flag():
    importer = load_source_signal_importer_module()
    conn = FakeConnection(ready_count=2)

    plan = build_plan(
        importer,
        conn=conn,
        write_requested=True,
        content_id_filter={123},
    )

    assert plan.is_partial_preview is True
    assert any("partial" in error.lower() for error in plan.errors)


def test_source_signal_partial_import_updates_only_selected_content_ids():
    importer = load_source_signal_importer_module()
    conn = FakeConnection(
        existing_signals=[
            matching_existing_signal(),
            {
                **matching_existing_signal(),
                "id": 101,
                "content_id": 456,
                "value": "other-content-signal",
            },
        ],
        ready_count=2,
    )

    plan = build_plan(
        importer,
        conn=conn,
        write_requested=True,
        allow_partial_preview=True,
        content_id_filter={123},
    )

    assert plan.errors == []
    assert all(record.content_id == 123 for record in plan.signal_records)
    assert 101 not in plan.obsolete_signal_ids


def test_source_signal_semantic_qa_issues_block_write_unless_allowed():
    importer = load_source_signal_importer_module()
    report = report_payload(
        semantic_quality_summary={
            "generic_watch_feel_count": 1,
            "semantic_conflict_count": 0,
            "curated_review_candidate_count": 1,
        }
    )

    blocked = build_plan(importer, report=report, write_requested=True)
    allowed = build_plan(
        importer,
        report=report,
        write_requested=True,
        allow_semantic_qa_issues=True,
    )

    assert any("semantic qa" in error.lower() for error in blocked.errors)
    assert not any("semantic qa" in error.lower() for error in allowed.errors)


def test_source_signal_missing_content_id_blocks_import():
    importer = load_source_signal_importer_module()
    plan = build_plan(
        importer,
        preview=preview_payload([preview_item(content_id=999)]),
    )

    assert plan.missing_content_rows == 1
    assert plan.errors


def test_source_signal_invalid_dimension_and_confidence_block_import():
    importer = load_source_signal_importer_module()
    item = preview_item(
        signals={
            "bad_dimension": [
                {
                    "value": "bad",
                    "label": "Bad",
                    "confidence": "medium",
                    "sources": ["tmdb_keywords"],
                }
            ],
            "mood": [
                {
                    "value": "tense",
                    "label": "Tense",
                    "confidence": "certain",
                    "sources": ["tmdb_keywords"],
                }
            ],
        }
    )

    plan = build_plan(importer, preview=preview_payload([item]))

    assert plan.invalid_preview_rows >= 2
    assert any("unknown signal dimension" in error for error in plan.errors)
    assert any("incomplete" in error for error in plan.errors)


def test_source_signal_guidance_lists_are_stored_as_jsonb():
    importer = load_source_signal_importer_module()
    conn = FakeConnection()
    record = importer.guidance_record_from_item(preview_item(), importer.ImportPlan(
        mode="DRY RUN",
        preview_path="preview.json",
        report_path="report.json",
        import_report_path="import_report.json",
    ))

    importer.upsert_watch_guidance(conn, record, 12)

    query = conn.write_queries[0]
    assert "CAST(:chips AS JSONB)" in query
    assert "CAST(:best_for AS JSONB)" in query
    assert conn.write_params[0]["curated_override_applied"] is False
    assert conn.write_params[0]["metadata_fallback_applied"] is False


def test_source_signal_guidance_storage_ready_and_frontend_not_ready_by_default():
    importer = load_source_signal_importer_module()
    conn = FakeConnection()
    record = importer.guidance_record_from_item(preview_item(), importer.ImportPlan(
        mode="DRY RUN",
        preview_path="preview.json",
        report_path="report.json",
        import_report_path="import_report.json",
    ))

    importer.upsert_watch_guidance(conn, record, 12)

    query = conn.write_queries[0]
    assert "storage_ready = TRUE" in query
    assert "frontend_ready = FALSE" in query
