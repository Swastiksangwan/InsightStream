from pathlib import Path


def rating_list_source() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "frontend" / "components" / "RatingList.tsx").read_text(
        encoding="utf-8"
    )


def test_ratings_card_uses_scoring_source_language():
    source = rating_list_source()

    assert "scoring source" in source
    assert "Source ratings available" in source
    assert "vote-backed average" in source
    assert "Based on one vote-backed source." in source
    assert "not enough vote-backed data for a score yet" in source


def test_letterboxd_card_uses_snapshot_language_without_fake_vote_count():
    source = rating_list_source()

    assert "Film-community signal" in source
    assert "Snapshot source" in source
    assert "Open source page" in source
    assert "Snapshot rating; live score may differ." in source
    assert "isLetterboxd" in source


def test_rating_source_links_open_in_new_tab_safely():
    source = rating_list_source()

    assert 'target="_blank"' in source
    assert 'rel="noopener noreferrer"' in source
    assert "href={source.rating_url}" in source
