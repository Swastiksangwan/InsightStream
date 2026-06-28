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
    assert "Calculated from rating sources with vote confidence." in source


def test_letterboxd_card_uses_snapshot_language_without_fake_vote_count():
    source = rating_list_source()

    assert "Film-community snapshot" in source
    assert "Dataset snapshot; may not reflect the latest live score." in source
    assert "isLetterboxd" in source


def test_rating_source_links_open_in_new_tab_safely():
    source = rating_list_source()

    assert 'target="_blank"' in source
    assert 'rel="noopener noreferrer"' in source
    assert "href={source.rating_url}" in source
