#!/usr/bin/env python3
"""
Inspection-only TMDb sample fetch script.

- This script does not modify PostgreSQL.
- It uses TMDb as a prototype metadata provider.
- TMDb data must be used according to TMDb terms.
- Do not commit API tokens.
- Run from repository root:

    export TMDB_READ_ACCESS_TOKEN="..."
    python3 analytics/scripts/fetch_tmdb_sample.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
    from requests import RequestException
except ImportError:  # pragma: no cover - helpful when dependencies are not installed yet.
    requests = None

    class RequestException(Exception):
        pass


API_BASE_URL = "https://api.themoviedb.org/3"
TOKEN_ENV_VAR = "TMDB_READ_ACCESS_TOKEN"
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_OUTPUT_DIR = REPO_ROOT / "analytics" / "raw" / "tmdb"
PROCESSED_OUTPUT_DIR = REPO_ROOT / "analytics" / "processed" / "tmdb"
PREVIEW_OUTPUT_PATH = PROCESSED_OUTPUT_DIR / "sample_mapping_preview.json"


@dataclass(frozen=True)
class SampleTitle:
    title: str
    media_type: str
    tmdb_id: int | None
    year: int | None = None


# Current seeded titles from backend/sample_data.sql.
SAMPLE_TITLES = [
    SampleTitle("Interstellar", "movie", 157336, 2014),
    SampleTitle("Inception", "movie", 27205, 2010),
    SampleTitle("The Dark Knight", "movie", 155, 2008),
    SampleTitle("Parasite", "movie", 496243, 2019),
    SampleTitle("Dune: Part Two", "movie", 693134, 2024),
    SampleTitle("Barbie", "movie", 346698, 2023),
    SampleTitle("Spider-Man: Across the Spider-Verse", "movie", 569094, 2023),
    SampleTitle("Red Notice", "movie", 512195, 2021),
    SampleTitle("Breaking Bad", "tv", 1396, 2008),
    SampleTitle("The Mandalorian", "tv", 157339, 2019),
    SampleTitle("The Last of Us", "tv", 100088, 2023),
    SampleTitle("Stranger Things", "tv", 66732, 2016),
    SampleTitle("The Boys", "tv", 76479, 2019),
    SampleTitle("Dark", "tv", 70523, 2017),
    SampleTitle("The Witcher", "tv", 71912, 2019),
]


class TmdbFetchError(RuntimeError):
    pass


def fetch_tmdb_json(
    path: str,
    token: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if requests is None:
        raise TmdbFetchError(
            "Missing dependency 'requests'. Run `pip install -r backend/requirements.txt`."
        )

    url = f"{API_BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
    except RequestException as exc:
        raise TmdbFetchError(f"Request failed for {path}: {exc}") from exc

    if response.status_code == 429:
        raise TmdbFetchError(
            f"TMDb rate limit hit for {path}. Wait and try again."
        )

    if not response.ok:
        raise TmdbFetchError(
            f"TMDb request failed for {path}: HTTP {response.status_code} - {response.text[:300]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise TmdbFetchError(f"TMDb returned malformed JSON for {path}") from exc

    if not isinstance(data, dict):
        raise TmdbFetchError(f"TMDb returned unexpected JSON shape for {path}")

    return data


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def title_matches(expected: str, actual: str | None) -> bool:
    expected_normalized = normalize_title(expected)
    actual_normalized = normalize_title(actual)
    return bool(
        expected_normalized
        and actual_normalized
        and (
            expected_normalized in actual_normalized
            or actual_normalized in expected_normalized
        )
    )


def year_from_date(date_value: str | None) -> int | None:
    if not date_value or len(date_value) < 4:
        return None
    try:
        return int(date_value[:4])
    except ValueError:
        return None


def choose_image_size(
    available_sizes: list[str],
    preferred_size: str,
    fallback_size: str = "original",
) -> str | None:
    if preferred_size in available_sizes:
        return preferred_size
    if fallback_size in available_sizes:
        return fallback_size
    if available_sizes:
        return available_sizes[-1]
    return None


def build_tmdb_image_url(
    configuration: dict[str, Any],
    image_path: str | None,
    image_kind: str,
) -> str | None:
    if not image_path:
        return None

    images = configuration.get("images", {})
    secure_base_url = images.get("secure_base_url")
    if not secure_base_url:
        return None

    if image_kind == "poster":
        size = choose_image_size(images.get("poster_sizes", []), "w500")
    elif image_kind == "backdrop":
        size = choose_image_size(images.get("backdrop_sizes", []), "w1280")
    else:
        size = "original"

    if not size:
        return None

    return f"{secure_base_url}{size}{image_path}"


def find_first_reasonable_search_result(
    sample: SampleTitle,
    token: str,
) -> tuple[int | None, str | None]:
    search_path = "/search/movie" if sample.media_type == "movie" else "/search/tv"
    params: dict[str, Any] = {
        "query": sample.title,
        "include_adult": "false",
    }

    if sample.year:
        if sample.media_type == "movie":
            params["year"] = sample.year
        else:
            params["first_air_date_year"] = sample.year

    try:
        data = fetch_tmdb_json(search_path, token, params=params)
    except TmdbFetchError as exc:
        return None, f"Fallback search failed: {exc}"

    results = data.get("results", [])
    if not isinstance(results, list) or not results:
        return None, "Fallback search returned no results."

    for result in results:
        result_title = result.get("title") or result.get("name")
        if title_matches(sample.title, result_title):
            result_id = result.get("id")
            if isinstance(result_id, int):
                return result_id, "TMDb ID came from fallback search; manually verify before database use."

    first_result = results[0]
    result_id = first_result.get("id")
    if isinstance(result_id, int):
        return result_id, "TMDb ID came from first fallback search result; manually verify before database use."

    return None, "Fallback search did not return a usable TMDb ID."


def get_details_title(details: dict[str, Any], media_type: str) -> str | None:
    if media_type == "movie":
        return details.get("title")
    return details.get("name")


def build_error_preview_item(sample: SampleTitle, error_message: str) -> dict[str, Any]:
    return {
        "source_provider": "tmdb",
        "tmdb_id": sample.tmdb_id,
        "media_type": sample.media_type,
        "title": sample.title,
        "overview": None,
        "release_date": None,
        "year": sample.year,
        "runtime": None,
        "original_language": None,
        "status": None,
        "poster_path": None,
        "backdrop_path": None,
        "poster_url": None,
        "backdrop_url": None,
        "genres": [],
        "vote_average": None,
        "vote_count": None,
        "popularity": None,
        "imdb_id": None,
        "top_cast_names": [],
        "director_or_creator_names": [],
        "mapping_notes": [error_message],
    }


def fetch_title_payloads(
    sample: SampleTitle,
    token: str,
) -> tuple[int, dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    notes: list[str] = []
    tmdb_id = sample.tmdb_id

    if sample.media_type not in {"movie", "tv"}:
        raise TmdbFetchError(
            f"Unsupported media_type '{sample.media_type}' for {sample.title}."
        )

    if not tmdb_id:
        raise TmdbFetchError(f"No usable TMDb ID for {sample.title}.")

    details_path = f"/{sample.media_type}/{tmdb_id}"
    external_ids_path = f"/{sample.media_type}/{tmdb_id}/external_ids"
    credits_path = f"/{sample.media_type}/{tmdb_id}/credits"

    details = fetch_tmdb_json(details_path, token)
    actual_title = get_details_title(details, sample.media_type)

    if not actual_title:
        notes.append(
            f"Media type validation warning: expected TMDb {sample.media_type} payload for {sample.title}, but no title/name field was returned."
        )

    if not title_matches(sample.title, actual_title):
        note = (
            f"Title mismatch: seed expected '{sample.title}', "
            f"TMDb returned '{actual_title}'. Manually verify tmdb_id {tmdb_id}."
        )
        notes.append(note)
        print(f"  Warning: {note}")

    external_ids = fetch_tmdb_json(external_ids_path, token)
    credits = fetch_tmdb_json(credits_path, token)

    return tmdb_id, details, external_ids, credits, notes


def top_cast_names(credits: dict[str, Any], limit: int = 5) -> list[str]:
    cast = credits.get("cast", [])
    if not isinstance(cast, list):
        return []
    names = [item.get("name") for item in cast if item.get("name")]
    return names[:limit]


def crew_names_by_jobs(
    credits: dict[str, Any],
    jobs: set[str],
    limit: int = 8,
) -> list[str]:
    crew = credits.get("crew", [])
    if not isinstance(crew, list):
        return []

    names: list[str] = []
    for item in crew:
        job = item.get("job")
        name = item.get("name")
        if job in jobs and name and name not in names:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def map_common_preview_fields(
    details: dict[str, Any],
    external_ids: dict[str, Any],
    credits: dict[str, Any],
    configuration: dict[str, Any],
    media_type: str,
    notes: list[str],
) -> dict[str, Any]:
    poster_path = details.get("poster_path")
    backdrop_path = details.get("backdrop_path")
    genres = details.get("genres", [])

    genre_names = []
    if isinstance(genres, list):
        genre_names = [genre.get("name") for genre in genres if genre.get("name")]

    if not poster_path:
        notes.append("Missing poster_path.")
    if not backdrop_path:
        notes.append("Missing backdrop_path.")
    if not genre_names:
        notes.append("No genres returned.")
    if not external_ids.get("imdb_id"):
        notes.append("No imdb_id returned.")

    return {
        "source_provider": "tmdb",
        "tmdb_id": details.get("id"),
        "media_type": media_type,
        "overview": details.get("overview"),
        "runtime": None,
        "original_language": details.get("original_language"),
        "status": details.get("status"),
        "poster_path": poster_path,
        "backdrop_path": backdrop_path,
        "poster_url": build_tmdb_image_url(configuration, poster_path, "poster"),
        "backdrop_url": build_tmdb_image_url(configuration, backdrop_path, "backdrop"),
        "genres": genre_names,
        "vote_average": details.get("vote_average"),
        "vote_count": details.get("vote_count"),
        "popularity": details.get("popularity"),
        "imdb_id": external_ids.get("imdb_id"),
        "top_cast_names": top_cast_names(credits),
        "director_or_creator_names": [],
        "mapping_notes": notes,
    }


def map_tmdb_movie_preview(
    details: dict[str, Any],
    external_ids: dict[str, Any],
    credits: dict[str, Any],
    configuration: dict[str, Any],
    notes: list[str],
) -> dict[str, Any]:
    release_date = details.get("release_date")
    preview = map_common_preview_fields(
        details,
        external_ids,
        credits,
        configuration,
        "movie",
        notes,
    )
    preview.update(
        {
            "title": details.get("title"),
            "release_date": release_date,
            "year": year_from_date(release_date),
            "runtime": details.get("runtime"),
            "director_or_creator_names": crew_names_by_jobs(credits, {"Director"}),
        }
    )

    if not preview["runtime"]:
        notes.append("Missing runtime.")
    if not preview["director_or_creator_names"]:
        notes.append("No director found in credits.")

    return preview


def map_tmdb_tv_preview(
    details: dict[str, Any],
    external_ids: dict[str, Any],
    credits: dict[str, Any],
    configuration: dict[str, Any],
    notes: list[str],
) -> dict[str, Any]:
    release_date = details.get("first_air_date")
    episode_run_time = details.get("episode_run_time")
    runtime = None
    if isinstance(episode_run_time, list) and episode_run_time:
        runtime = episode_run_time[0]

    created_by = details.get("created_by", [])
    creator_names = []
    if isinstance(created_by, list):
        creator_names = [
            creator.get("name") for creator in created_by if creator.get("name")
        ]

    crew_creator_names = crew_names_by_jobs(
        credits,
        {"Creator", "Showrunner", "Director"},
    )
    director_or_creator_names = []
    for name in creator_names + crew_creator_names:
        if name not in director_or_creator_names:
            director_or_creator_names.append(name)

    preview = map_common_preview_fields(
        details,
        external_ids,
        credits,
        configuration,
        "tv",
        notes,
    )
    preview.update(
        {
            "title": details.get("name"),
            "release_date": release_date,
            "year": year_from_date(release_date),
            "runtime": runtime,
            "director_or_creator_names": director_or_creator_names,
        }
    )

    if not runtime:
        notes.append("Missing or empty episode_run_time; runtime is approximate/null.")
    if not director_or_creator_names:
        notes.append("No creator/director names found.")

    return preview


def raw_filename(media_type: str, tmdb_id: int, payload_name: str) -> str:
    return f"{media_type}_{tmdb_id}_{payload_name}.json"


def print_preview_table(items: list[dict[str, Any]]) -> None:
    print("\nMapped preview:")
    header = (
        "Title",
        "Type",
        "Year",
        "Runtime",
        "Genres",
        "Poster",
        "Backdrop",
        "IMDb",
        "Notes",
    )
    print(
        f"{header[0]:34} {header[1]:6} {header[2]:6} {header[3]:8} "
        f"{header[4]:34} {header[5]:7} {header[6]:8} {header[7]:5} {header[8]:5}"
    )
    print("-" * 130)
    for item in items:
        genres = ", ".join(item.get("genres") or [])
        if len(genres) > 32:
            genres = genres[:29] + "..."
        notes_count = len(item.get("mapping_notes") or [])
        print(
            f"{str(item.get('title') or '')[:34]:34} "
            f"{str(item.get('media_type') or '')[:6]:6} "
            f"{str(item.get('year') or '')[:6]:6} "
            f"{str(item.get('runtime') or '')[:8]:8} "
            f"{genres[:34]:34} "
            f"{'yes' if item.get('poster_url') else 'no':7} "
            f"{'yes' if item.get('backdrop_url') else 'no':8} "
            f"{'yes' if item.get('imdb_id') else 'no':5} "
            f"{notes_count if notes_count else '-':5}"
        )


def print_preview_totals(items: list[dict[str, Any]], total_fetched: int) -> None:
    total_with_poster = sum(1 for item in items if item.get("poster_url"))
    total_with_backdrop = sum(1 for item in items if item.get("backdrop_url"))
    total_with_imdb = sum(1 for item in items if item.get("imdb_id"))
    total_with_notes = sum(1 for item in items if item.get("mapping_notes"))

    print("\nPreview totals:")
    print(f"- Total fetched: {total_fetched}")
    print(f"- Total preview items: {len(items)}")
    print(f"- Total with poster_url: {total_with_poster}")
    print(f"- Total with backdrop_url: {total_with_backdrop}")
    print(f"- Total with imdb_id: {total_with_imdb}")
    print(f"- Total with warnings/mapping_notes: {total_with_notes}")


def main() -> int:
    token = os.getenv(TOKEN_ENV_VAR)
    if not token:
        print(
            f"Missing {TOKEN_ENV_VAR}. Set it before running:\n"
            f'  export {TOKEN_ENV_VAR}="..."\n'
            "No TMDb requests were made."
        )
        return 1

    RAW_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        configuration = fetch_tmdb_json("/configuration", token)
    except TmdbFetchError as exc:
        print(f"Could not fetch TMDb configuration: {exc}")
        return 1

    save_json(RAW_OUTPUT_DIR / "configuration.json", configuration)

    mapped_items: list[dict[str, Any]] = []
    raw_files: list[Path] = [RAW_OUTPUT_DIR / "configuration.json"]
    errors: list[str] = []
    total_fetched = 0

    for sample in SAMPLE_TITLES:
        print(f"Fetching {sample.title} ({sample.media_type})...")
        try:
            tmdb_id, details, external_ids, credits, notes = fetch_title_payloads(
                sample,
                token,
            )
        except TmdbFetchError as exc:
            message = f"{sample.title}: {exc}"
            print(f"  Error: {message}")
            errors.append(message)
            mapped_items.append(build_error_preview_item(sample, str(exc)))
            continue

        details_path = RAW_OUTPUT_DIR / raw_filename(
            sample.media_type,
            tmdb_id,
            "details",
        )
        external_ids_path = RAW_OUTPUT_DIR / raw_filename(
            sample.media_type,
            tmdb_id,
            "external_ids",
        )
        credits_path = RAW_OUTPUT_DIR / raw_filename(
            sample.media_type,
            tmdb_id,
            "credits",
        )

        save_json(details_path, details)
        save_json(external_ids_path, external_ids)
        save_json(credits_path, credits)
        raw_files.extend([details_path, external_ids_path, credits_path])

        if sample.media_type == "movie":
            mapped = map_tmdb_movie_preview(
                details,
                external_ids,
                credits,
                configuration,
                notes,
            )
        else:
            mapped = map_tmdb_tv_preview(
                details,
                external_ids,
                credits,
                configuration,
                notes,
            )
        mapped_items.append(mapped)
        total_fetched += 1

    if not mapped_items:
        print("No titles were mapped. Check the token, network, and TMDb IDs.")
        return 1

    preview_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inspection_only": True,
        "source_provider": "tmdb",
        "licensing_note": (
            "Prototype/non-commercial inspection only. Follow TMDb terms, do not commit API keys, "
            "do not use TMDb content for ML/AI training, and do not assume permanent storage rights."
        ),
        "items": mapped_items,
    }
    save_json(PREVIEW_OUTPUT_PATH, preview_payload)

    print("\nTitles fetched:")
    for item in mapped_items:
        print(f"- {item.get('title')} ({item.get('media_type')}, {item.get('tmdb_id')})")

    print("\nRaw files saved:")
    for path in raw_files:
        print(f"- {path.relative_to(REPO_ROOT)}")

    print(f"\nProcessed preview saved: {PREVIEW_OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print_preview_table(mapped_items)
    print_preview_totals(mapped_items, total_fetched)

    warning_items = [
        item for item in mapped_items if item.get("mapping_notes")
    ]
    if warning_items:
        print("\nMapping warnings:")
        for item in warning_items:
            print(f"- {item.get('title')}:")
            for note in item.get("mapping_notes") or []:
                print(f"  - {note}")

    if errors:
        print("\nWarnings/errors:")
        for error in errors:
            print(f"- {error}")

    print("\nNo database changes were made.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
