#!/usr/bin/env python3
"""
Inspection/local-update script for poster and backdrop URLs.

- This script reads a sanitized processed preview.
- It does not fetch TMDb or call external APIs.
- It does not modify schema.
- It does not update ratings, summaries, genres, runtime, overview, or person data.
- TMDb is currently a replaceable prototype metadata provider.

Dry run:
    python3 analytics/scripts/update_posters_from_tmdb_preview.py

Apply:
    python3 analytics/scripts/update_posters_from_tmdb_preview.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


REPO_ROOT = Path(__file__).resolve().parents[2]
PREVIEW_PATH = REPO_ROOT / "analytics" / "processed" / "tmdb" / "sample_mapping_preview.json"
DATABASE_URL_ENV = "DATABASE_URL"

MEDIA_TYPE_TO_CONTENT_TYPE = {
    "movie": "movie",
    "tv": "series",
}


@dataclass
class UpdatePlan:
    index: int
    title: str
    tmdb_id: int
    content_id: int
    content_type: str
    current_poster_url: str | None
    current_backdrop_url: str | None
    new_poster_url: str
    new_backdrop_url: str | None


@dataclass
class SkippedItem:
    index: int
    title: str
    reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect and optionally apply local poster/backdrop updates from "
            "analytics/processed/tmdb/sample_mapping_preview.json."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates to local PostgreSQL. Without this flag, only prints planned updates.",
    )
    return parser.parse_args()


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def title_matches(preview_title: str, content_title: str) -> bool:
    return normalize_title(preview_title) == normalize_title(content_title)


def load_preview(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Missing preview file: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Malformed preview JSON in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Preview JSON root must be an object.")

    items = data.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Preview JSON must contain an items list.")

    if not items:
        raise RuntimeError("Preview JSON items list is empty.")

    return data


def get_database_url() -> str:
    database_url = os.getenv(DATABASE_URL_ENV)
    if not database_url:
        raise RuntimeError(
            f"Missing {DATABASE_URL_ENV}. Export it before running this script."
        )
    return database_url


def fetch_content_row(connection, tmdb_id: int, content_type: str):
    query = text(
        """
        SELECT
            id,
            title,
            content_type,
            poster_url,
            backdrop_url
        FROM content
        WHERE tmdb_id = :tmdb_id
          AND content_type = :content_type;
        """
    )
    result = connection.execute(
        query,
        {
            "tmdb_id": tmdb_id,
            "content_type": content_type,
        },
    )
    return result.mappings().first()


def validate_preview_item(item: Any, index: int) -> tuple[dict[str, Any] | None, SkippedItem | None]:
    if not isinstance(item, dict):
        return None, SkippedItem(index, "<unknown>", "unexpected item shape")

    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        return None, SkippedItem(index, "<missing title>", "preview title is empty")

    source_provider = item.get("source_provider")
    if source_provider != "tmdb":
        return None, SkippedItem(title=title, index=index, reason="source provider not tmdb")

    tmdb_id = item.get("tmdb_id")
    if not isinstance(tmdb_id, int):
        return None, SkippedItem(index, title, "missing tmdb_id")

    media_type = item.get("media_type")
    if media_type not in MEDIA_TYPE_TO_CONTENT_TYPE:
        return None, SkippedItem(index, title, "unsupported media_type")

    poster_url = item.get("poster_url")
    if not isinstance(poster_url, str) or not poster_url.strip():
        return None, SkippedItem(index, title, "missing poster_url")

    backdrop_url = item.get("backdrop_url")
    if backdrop_url is not None and not isinstance(backdrop_url, str):
        return None, SkippedItem(index, title, "invalid backdrop_url")

    return item, None


def build_update_plans(
    connection,
    preview_items: list[Any],
) -> tuple[list[UpdatePlan], list[SkippedItem]]:
    plans: list[UpdatePlan] = []
    skipped: list[SkippedItem] = []

    for index, raw_item in enumerate(preview_items, start=1):
        item, skip = validate_preview_item(raw_item, index)
        if skip:
            skipped.append(skip)
            continue

        assert item is not None
        title = item["title"].strip()
        tmdb_id = item["tmdb_id"]
        media_type = item["media_type"]
        content_type = MEDIA_TYPE_TO_CONTENT_TYPE[media_type]

        try:
            row = fetch_content_row(connection, tmdb_id, content_type)
        except SQLAlchemyError as exc:
            skipped.append(SkippedItem(index, title, f"SQL read failed: {exc}"))
            continue

        if not row:
            skipped.append(SkippedItem(index, title, "content row not found"))
            continue

        content_title = row["title"]
        if not title_matches(title, content_title):
            skipped.append(
                SkippedItem(
                    index,
                    title,
                    f"title mismatch: preview '{title}' vs database '{content_title}'",
                )
            )
            continue

        plans.append(
            UpdatePlan(
                index=index,
                title=content_title,
                tmdb_id=tmdb_id,
                content_id=row["id"],
                content_type=content_type,
                current_poster_url=row["poster_url"],
                current_backdrop_url=row["backdrop_url"],
                new_poster_url=item["poster_url"].strip(),
                new_backdrop_url=item.get("backdrop_url").strip()
                if isinstance(item.get("backdrop_url"), str) and item.get("backdrop_url").strip()
                else None,
            )
        )

    return plans, skipped


def print_plan(plans: list[UpdatePlan], skipped: list[SkippedItem], apply: bool) -> None:
    mode = "APPLY mode" if apply else "DRY RUN mode"
    print(f"{mode}: poster/backdrop update preview")
    print(f"Planned/matched rows: {len(plans)}")
    print(f"Skipped rows: {len(skipped)}")

    for plan in plans:
        status = "UPDATED" if apply else "UPDATE PLANNED"
        print(f"\n{status}: {plan.title} ({plan.content_type}, tmdb_id={plan.tmdb_id})")
        print(f"  content_id: {plan.content_id}")
        print(f"  current poster:   {plan.current_poster_url or '<empty>'}")
        print(f"  new poster:       {plan.new_poster_url}")
        print(f"  current backdrop: {plan.current_backdrop_url or '<empty>'}")
        print(f"  new backdrop:     {plan.new_backdrop_url or '<unchanged; preview missing>'}")

    for item in skipped:
        print(f"\nSKIPPED: {item.title} (preview item {item.index})")
        print(f"  reason: {item.reason}")

    if not apply:
        print("\nNo database writes were made.")
        print("Rerun with --apply to update local PostgreSQL.")


def apply_updates(database_url: str, plans: list[UpdatePlan]) -> None:
    engine = create_engine(database_url)

    try:
        with engine.begin() as connection:
            for plan in plans:
                if plan.new_backdrop_url:
                    query = text(
                        """
                        UPDATE content
                        SET
                            poster_url = :poster_url,
                            backdrop_url = :backdrop_url
                        WHERE id = :content_id;
                        """
                    )
                    params = {
                        "poster_url": plan.new_poster_url,
                        "backdrop_url": plan.new_backdrop_url,
                        "content_id": plan.content_id,
                    }
                else:
                    query = text(
                        """
                        UPDATE content
                        SET poster_url = :poster_url
                        WHERE id = :content_id;
                        """
                    )
                    params = {
                        "poster_url": plan.new_poster_url,
                        "content_id": plan.content_id,
                    }

                result = connection.execute(query, params)
                if result.rowcount != 1:
                    raise RuntimeError(
                        f"Expected to update 1 row for {plan.title}, updated {result.rowcount}."
                    )
    except SQLAlchemyError as exc:
        raise RuntimeError(f"SQL update failed; transaction rolled back: {exc}") from exc


def main() -> int:
    args = parse_args()

    try:
        preview = load_preview(PREVIEW_PATH)
        database_url = get_database_url()
    except RuntimeError as exc:
        print(f"Error: {exc}")
        return 1

    try:
        engine = create_engine(database_url)
        with engine.connect() as connection:
            plans, skipped = build_update_plans(connection, preview["items"])
    except SQLAlchemyError as exc:
        print(f"Error: database connection or read failed: {exc}")
        return 1
    except RuntimeError as exc:
        print(f"Error: {exc}")
        return 1

    if args.apply and plans:
        try:
            apply_updates(database_url, plans)
        except RuntimeError as exc:
            print(f"Error: {exc}")
            return 1

    print_plan(plans, skipped, args.apply)

    if args.apply:
        print(f"\nRows updated: {len(plans)}")
        print(f"Rows skipped: {len(skipped)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
