import importlib.util
import sys
from pathlib import Path


def load_importer_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = (
        repo_root / "analytics" / "scripts" / "import_person_details_from_preview.py"
    )
    spec = importlib.util.spec_from_file_location(
        "import_person_details_from_preview",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_person_details_from_preview"] = module
    spec.loader.exec_module(module)
    return module


def load_fetch_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "analytics" / "scripts" / "fetch_tmdb_person_details.py"
    spec = importlib.util.spec_from_file_location("fetch_tmdb_person_details", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_tmdb_person_details"] = module
    spec.loader.exec_module(module)
    return module


def existing_person(**overrides):
    person = {
        "id": 901,
        "name": "Example Person",
        "biography": None,
        "profile_url": None,
        "known_for_department": None,
        "birthday": None,
        "place_of_birth": None,
    }
    person.update(overrides)
    return person


def preview_item(**overrides):
    item = {
        "person_id": 901,
        "source_name": "tmdb",
        "source_person_id": "12345",
        "name": "Example Person",
        "biography": "Example biography.",
        "profile_url": "https://image.tmdb.org/t/p/w185/profile.jpg",
        "known_for_department": "Acting",
        "birthday": "1995-12-27",
        "place_of_birth": "New York City, New York, USA",
    }
    item.update(overrides)
    return item


def test_fetch_preview_includes_birthday_and_place_of_birth():
    fetcher = load_fetch_module()
    local_person = fetcher.LocalPerson(
        person_id=901,
        source_person_id="12345",
        name="Example Person",
        biography=None,
        profile_url=None,
        known_for_department=None,
        birthday=None,
        place_of_birth=None,
    )

    item = fetcher.map_person_preview(
        local_person,
        {
            "name": "Example Person",
            "biography": "Example biography.",
            "profile_path": "/profile.jpg",
            "known_for_department": "Acting",
            "birthday": "1995-12-27",
            "place_of_birth": "New York City, New York, USA",
        },
    )

    assert item["birthday"] == "1995-12-27"
    assert item["place_of_birth"] == "New York City, New York, USA"
    assert item["importable_fields"]["birthday"] is True
    assert item["importable_fields"]["place_of_birth"] is True


def test_person_importer_plans_birthday_and_birthplace_updates():
    importer = load_importer_module()
    stats = importer.ImportStats(mode="DRY RUN", db_aware=True)

    updates = importer.planned_updates(existing_person(), preview_item(), stats.warnings)
    importer.increment_update_counts(stats, updates)

    assert updates["birthday"] == "1995-12-27"
    assert updates["place_of_birth"] == "New York City, New York, USA"
    assert stats.birthday_updates == 1
    assert stats.place_of_birth_updates == 1


def test_person_importer_does_not_overwrite_with_blank_values():
    importer = load_importer_module()
    stats = importer.ImportStats(mode="DRY RUN", db_aware=True)

    updates = importer.planned_updates(
        existing_person(
            birthday="1995-12-27",
            place_of_birth="New York City, New York, USA",
        ),
        preview_item(birthday="", place_of_birth=None),
        stats.warnings,
    )

    assert "birthday" not in updates
    assert "place_of_birth" not in updates
    assert stats.warnings == []


def test_person_importer_preserves_existing_birthday_conflict():
    importer = load_importer_module()
    stats = importer.ImportStats(mode="DRY RUN", db_aware=True)

    updates = importer.planned_updates(
        existing_person(birthday="1990-01-01"),
        preview_item(birthday="1995-12-27"),
        stats.warnings,
    )

    assert "birthday" not in updates
    assert any(
        "existing birthday differs from preview; preserved existing value" in warning
        for warning in stats.warnings
    )


def test_person_importer_prints_row_level_birthday_and_birthplace(capsys):
    importer = load_importer_module()
    stats = importer.ImportStats(mode="DRY RUN", db_aware=True)
    person = existing_person()
    updates = importer.planned_updates(person, preview_item(), stats.warnings)
    importer.increment_update_counts(stats, updates)
    importer.record_person_update_row(stats, person, updates)

    importer.print_stats(stats)
    output = capsys.readouterr().out

    assert "Birthday updates planned: 1" in output
    assert "Place-of-birth updates planned: 1" in output
    assert "Would update person rows:" in output
    assert "- Example Person [id=901]" in output
    assert "  - birthday: <empty> -> 1995-12-27" in output
    assert "  - place_of_birth: <empty> -> New York City, New York, USA" in output
