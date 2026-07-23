import json
import subprocess
from copy import deepcopy
from pathlib import Path

from analytics.scripts.source_signals import build_unmapped_keyword_review as review
from analytics.scripts.source_signals.build_keyword_signal_preview import (
    load_mapping_config,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def mapping_config():
    return load_mapping_config(
        REPO_ROOT / "analytics" / "config" / "source_signal_keyword_mapping.json"
    )


def row(content_id, title, keyword, normalized=None):
    return {
        "content_id": content_id,
        "title": title,
        "content_type": "movie",
        "keyword_name": keyword,
        "normalized_keyword_name": normalized or keyword,
    }


def test_review_report_is_deterministic_and_uses_canonical_normalization():
    rows = [
        row(2, "Second", "Neo-Noir"),
        row(1, "First", "neo noir"),
        row(3, "Third", "Unmapped / Cue"),
        row(4, "Fourth", "unmapped_cue"),
        row(5, "Fifth", "unmapped-cue"),
    ]
    report = review.build_review_report(
        rows,
        mapping_config(),
        {},
        top=1,
        minimum_title_count=3,
        generated_at="2026-07-22T00:00:00+00:00",
    )

    assert report["normalization"]["version"] == "source-signal-keyword-v1"
    assert [item["normalized_keyword"] for item in report["keywords"]] == [
        "unmapped cue"
    ]
    assert report["keywords"][0]["affected_title_count"] == 3
    assert [item["content_id"] for item in report["keywords"][0]["sample_affected_titles"]] == [
        5,
        4,
        3,
    ]


def test_reviewed_decisions_record_mapping_exclusion_and_manual_review():
    decisions = review.load_review_decisions(
        REPO_ROOT
        / "analytics"
        / "config"
        / "source_signal_keyword_review_decisions.json"
    )
    rows = [
        row(1, "Thoughtful Film", "introspective"),
        row(2, "City Film", "new york city"),
        row(3, "Ambiguous Film", "awestruck"),
    ]
    report = review.build_review_report(
        rows,
        mapping_config(),
        decisions,
        top=1,
        minimum_title_count=3,
        generated_at="2026-07-22T00:00:00+00:00",
    )
    entries = {item["normalized_keyword"]: item for item in report["keywords"]}

    assert entries["introspective"]["runtime_mapping_status"] == "mapped"
    assert entries["introspective"]["decision_action"] == "map"
    assert entries["introspective"]["decision_consistency"] == "consistent"
    assert entries["introspective"]["proposed_mapping"]
    assert entries["new york city"]["runtime_mapping_status"] == "excluded"
    assert entries["new york city"]["proposed_classification"] == "location_or_setting"
    assert entries["awestruck"]["proposed_action"] == "leave_unmapped"
    assert entries["awestruck"]["human_review_required"] is True


def test_review_decision_file_is_normalized_and_valid():
    path = (
        REPO_ROOT
        / "analytics"
        / "config"
        / "source_signal_keyword_review_decisions.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    document = review.load_review_document(path)
    decisions = document["decisions"]

    assert payload["normalization_contract"] == "source-signal-keyword-v1"
    assert payload["supports_mapping_version"] == mapping_config()["mapping_version"]
    assert set(decisions) == set(payload["decisions"])
    assert all(
        item["classification"] in review.VALID_CLASSIFICATIONS
        and item["action"] in review.VALID_ACTIONS
        for item in decisions.values()
    )
    review.validate_review_document(document, mapping_config())


def test_review_decisions_match_every_runtime_action_exactly():
    path = REPO_ROOT / "analytics" / "config" / "source_signal_keyword_review_decisions.json"
    document = review.load_review_document(path)
    mapping = mapping_config()

    review.validate_review_document(document, mapping)
    for keyword, decision in document["decisions"].items():
        if decision["action"] == "map":
            assert decision["mapping"] == mapping["keyword_mappings"][keyword]["signals"]
        elif decision["action"] == "exclude":
            assert keyword in mapping["excluded_keywords"]
        elif decision["action"] == "spoiler_unsafe":
            assert keyword in mapping["spoiler_unsafe_keywords"]
        else:
            assert keyword not in mapping["keyword_mappings"]
            assert keyword not in mapping["excluded_keywords"]
            assert keyword not in mapping["spoiler_unsafe_keywords"]


def test_review_validation_rejects_version_and_mapping_drift():
    path = REPO_ROOT / "analytics" / "config" / "source_signal_keyword_review_decisions.json"
    document = review.load_review_document(path)
    mapping = mapping_config()

    wrong_version = deepcopy(document)
    wrong_version["supports_mapping_version"] = "wrong"
    try:
        review.validate_review_document(wrong_version, mapping)
    except ValueError as exc:
        assert "version" in str(exc)
    else:
        raise AssertionError("version drift must fail validation")

    wrong_mapping = deepcopy(document)
    wrong_mapping["decisions"]["tragedy"]["mapping"][0]["weight"] = 99
    try:
        review.validate_review_document(wrong_mapping, mapping)
    except ValueError as exc:
        assert "differs" in str(exc)
    else:
        raise AssertionError("mapping drift must fail validation")


def test_review_report_compares_baseline_and_candidate_without_fabrication():
    candidate = mapping_config()
    baseline = deepcopy(candidate)
    baseline["mapping_version"] = "baseline"
    baseline["keyword_mappings"].pop("introspective")
    rows = [row(1, "Thoughtful Film", "introspective")]
    decisions = review.load_review_decisions(
        REPO_ROOT / "analytics" / "config" / "source_signal_keyword_review_decisions.json"
    )

    without_baseline = review.build_review_report(
        rows, candidate, decisions, generated_at="2026-07-22T00:00:00+00:00"
    )
    assert without_baseline["keywords"][0]["status_before"] is None
    assert without_baseline["keywords"][0]["no_runtime_change"] is None

    with_baseline = review.build_review_report(
        rows,
        candidate,
        decisions,
        baseline_mapping=baseline,
        generated_at="2026-07-22T00:00:00+00:00",
    )
    entry = with_baseline["keywords"][0]
    assert entry["status_before"] == "unmapped"
    assert entry["status_after"] == "mapped"
    assert entry["mapping_added"] is True
    assert with_baseline["versions"]["baseline_mapping_version"] == "baseline"


class FakeTransaction:
    def __init__(self):
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True


class FakeReadOnlyConnection:
    class Dialect:
        name = "postgresql"

    dialect = Dialect()

    def __init__(self):
        self.transaction = FakeTransaction()
        self.queries = []

    def begin(self):
        return self.transaction

    def execute(self, query, params=None):
        self.queries.append(str(query))


def test_review_database_read_uses_explicit_read_only_transaction(monkeypatch):
    connection = FakeReadOnlyConnection()
    monkeypatch.setattr(review, "fetch_imported_tmdb_keywords", lambda _connection: [])

    assert review.fetch_review_rows_read_only(connection) == []
    assert connection.queries == ["SET TRANSACTION READ ONLY"]
    assert connection.transaction.rolled_back is True


def test_locations_franchises_and_lifecycle_terms_do_not_map_to_signals():
    mapping = mapping_config()
    blocked = {
        "new york city",
        "london england",
        "marvel cinematic universe mcu",
        "miniseries",
        "prequel",
    }

    assert blocked.isdisjoint(mapping["keyword_mappings"])
    assert blocked <= mapping["excluded_keywords"]


def test_bounty_hunter_is_held_for_manual_review():
    mapping = mapping_config()
    decisions = review.load_review_decisions(
        REPO_ROOT / "analytics" / "config" / "source_signal_keyword_review_decisions.json"
    )

    assert decisions["bounty hunter"]["action"] == "leave_unmapped"
    assert decisions["bounty hunter"]["human_review_required"] is True
    assert "bounty hunter" not in mapping["keyword_mappings"]
    assert "bounty hunter" not in mapping["excluded_keywords"]
    assert "bounty hunter" not in mapping["spoiler_unsafe_keywords"]


def test_generated_review_path_is_git_ignored():
    path = "analytics/processed/source_signal_reviews/source_signal_unmapped_keyword_review.json"
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0
