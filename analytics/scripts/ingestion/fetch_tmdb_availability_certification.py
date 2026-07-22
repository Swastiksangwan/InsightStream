#!/usr/bin/env python3
"""
Fetch inspection-only availability and certification metadata from TMDb.

This script:
- reads configured ingestion targets
- fetches raw TMDb watch-provider and certification payloads
- writes a processed provider-neutral preview
- does not write to PostgreSQL
- does not modify backend/frontend/schema/sample_data files

Default run processes the current pipeline-test target only:

    python3 -m analytics.scripts.ingestion.fetch_tmdb_availability_certification

Focused run:

    python3 -m analytics.scripts.ingestion.fetch_tmdb_availability_certification --source-id 872585
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
    from requests import RequestException
except ImportError:  # pragma: no cover - helpful when dependencies are not installed.
    requests = None

    class RequestException(Exception):
        pass


API_BASE_URL = "https://api.themoviedb.org/3"
TOKEN_ENV_VAR = "TMDB_READ_ACCESS_TOKEN"
from analytics.scripts.common.paths import REPO_ROOT
DEFAULT_TARGETS_PATH = REPO_ROOT / "analytics" / "config" / "content_ingestion_targets.json"
RAW_OUTPUT_DIR = REPO_ROOT / "analytics" / "raw" / "tmdb"
PROCESSED_DIR = REPO_ROOT / "analytics" / "processed" / "tmdb"
PROCESSED_OUTPUT_PATH = PROCESSED_DIR / "availability_certification_preview.json"
RUN_REPORT_DIR = PROCESSED_DIR / "run_reports"
RUN_REPORT_OUTPUT_PATH = RUN_REPORT_DIR / "availability_certification_fetch_run_report.json"
PRIMARY_REGION = "IN"
FALLBACK_REGIONS = ["US"]
SUPPORTED_CONTENT_TYPES = {"movie", "series"}
AVAILABILITY_TYPE_MAP = {
    "flatrate": "streaming",
    "rent": "rent",
    "buy": "buy",
    "ads": "ads",
    "free": "free",
}
MOVIE_RELEASE_TYPE_NAMES = {
    1: "premiere",
    2: "theatrical_limited",
    3: "theatrical",
    4: "digital",
    5: "physical",
    6: "tv",
}


@dataclass(frozen=True)
class Target:
    title: str
    content_type: str
    source_name: str
    source_id: str
    priority: str | None
    ingestion_status: str | None
    notes: str | None


@dataclass
class FetchStats:
    targets_loaded: int = 0
    targets_processed: int = 0
    targets_skipped: int = 0
    targets_fetched: int = 0
    targets_reused: int = 0
    availability_rows: int = 0
    certification_rows: int = 0
    warnings: list[str] | None = None
    failures: list[str] | None = None
    raw_files_fetched: list[str] | None = None
    raw_files_reused: list[str] | None = None
    per_target: list[dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []
        if self.failures is None:
            self.failures = []
        if self.raw_files_fetched is None:
            self.raw_files_fetched = []
        if self.raw_files_reused is None:
            self.raw_files_reused = []
        if self.per_target is None:
            self.per_target = []


class PreviewFetchError(RuntimeError):
    pass


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--limit must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("--limit must be a positive integer")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch TMDb availability/certification raw data and write an "
            "inspection-only processed preview."
        )
    )
    parser.add_argument(
        "--targets",
        default=str(DEFAULT_TARGETS_PATH.relative_to(REPO_ROOT)),
        help=(
            "Path to ingestion target JSON. Defaults to "
            f"{DEFAULT_TARGETS_PATH.relative_to(REPO_ROOT)}."
        ),
    )
    parser.add_argument(
        "--priority",
        help="Process only targets with this priority value.",
    )
    parser.add_argument(
        "--source-id",
        help="Process one TMDb source_id from the target config.",
    )
    parser.add_argument(
        "--title",
        help="Process one target by exact title match, case-insensitive.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all valid TMDb targets. Defaults to pipeline-test targets only.",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        help="Cap selected targets after filtering.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refetch raw files even when cached raw files already exist.",
    )
    return parser.parse_args(argv)


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def resolve_path(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def clean_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if value is not None:
        text_value = str(value).strip()
        return text_value or None
    return None


def load_targets(path: Path) -> tuple[list[Target], list[str], int]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PreviewFetchError(f"Missing target config: {relative_path(path)}") from exc
    except json.JSONDecodeError as exc:
        raise PreviewFetchError(
            f"Malformed target JSON in {relative_path(path)}: {exc}"
        ) from exc

    if not isinstance(data, dict) or not isinstance(data.get("targets"), list):
        raise PreviewFetchError(
            f"Target config must contain a top-level 'targets' array: {relative_path(path)}"
        )

    targets: list[Target] = []
    warnings: list[str] = []
    skipped = 0

    for index, raw_target in enumerate(data["targets"], start=1):
        if not isinstance(raw_target, dict):
            warnings.append(f"Target #{index}: expected object; skipped.")
            skipped += 1
            continue

        title = clean_text(raw_target.get("title"))
        content_type = (clean_text(raw_target.get("content_type")) or "").lower()
        source_name = (clean_text(raw_target.get("source_name")) or "").lower()
        source_id = clean_text(raw_target.get("source_id"))
        priority = clean_text(raw_target.get("priority"))
        ingestion_status = clean_text(raw_target.get("ingestion_status"))
        notes = clean_text(raw_target.get("notes"))
        label = title or f"target #{index}"

        if (ingestion_status or "").lower() == "skip":
            warnings.append(f"{label}: ingestion_status is skip; skipped.")
            skipped += 1
            continue

        errors: list[str] = []
        if not title:
            errors.append("missing title")
        if content_type not in SUPPORTED_CONTENT_TYPES:
            errors.append("content_type must be movie or series")
        if source_name != "tmdb":
            errors.append("source_name must be tmdb")
        if not source_id:
            errors.append("missing source_id")
        elif not source_id.isdigit() or int(source_id) <= 0:
            errors.append("source_id must be a positive TMDb ID")

        if errors:
            warnings.append(f"{label}: invalid target ({'; '.join(errors)}); skipped.")
            skipped += 1
            continue

        targets.append(
            Target(
                title=title or "",
                content_type=content_type,
                source_name=source_name,
                source_id=source_id or "",
                priority=priority,
                ingestion_status=ingestion_status,
                notes=notes,
            )
        )

    return targets, warnings, skipped


def filter_targets(targets: list[Target], args: argparse.Namespace) -> list[Target]:
    if args.all:
        selected = targets
    elif args.priority or args.source_id or args.title:
        selected = targets
    else:
        default_targets = [
            target
            for target in targets
            if (target.priority or "").lower() == "pipeline_test"
        ]
        selected = default_targets or [
            target for target in targets if target.source_id == "872585"
        ]

    if args.priority:
        priority = str(args.priority).strip().lower()
        selected = [
            target for target in selected if (target.priority or "").lower() == priority
        ]

    if args.source_id:
        source_id = str(args.source_id).strip()
        selected = [target for target in selected if target.source_id == source_id]

    if args.title:
        title = str(args.title).strip().lower()
        selected = [target for target in selected if target.title.lower() == title]

    if args.limit:
        selected = selected[: args.limit]

    return selected


def filters_used(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "all": args.all,
        "priority": args.priority,
        "source_id": args.source_id,
        "title": args.title,
        "limit": args.limit,
        "refresh": args.refresh,
    }


def fetch_tmdb_json(path: str, token: str) -> dict[str, Any]:
    if requests is None:
        raise PreviewFetchError(
            "Missing dependency 'requests'. Run `pip install -r backend/requirements.txt`."
        )

    url = f"{API_BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=20)
    except RequestException as exc:
        raise PreviewFetchError(f"Request failed for {path}: {exc}") from exc

    if response.status_code == 429:
        raise PreviewFetchError(f"TMDb rate limit hit for {path}. Wait and try again.")

    if not response.ok:
        raise PreviewFetchError(
            f"TMDb request failed for {path}: HTTP {response.status_code} - "
            f"{response.text[:300]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise PreviewFetchError(f"TMDb returned malformed JSON for {path}") from exc

    if not isinstance(data, dict):
        raise PreviewFetchError(f"TMDb returned unexpected JSON shape for {path}.")

    return data


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_cached_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PreviewFetchError(f"Missing cached raw file: {relative_path(path)}") from exc
    except json.JSONDecodeError as exc:
        raise PreviewFetchError(
            f"Malformed cached raw JSON in {relative_path(path)}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise PreviewFetchError(
            f"Cached raw JSON has unexpected shape: {relative_path(path)}"
        )

    return data


def fetch_or_reuse_json(
    api_path: str,
    raw_path: Path,
    token: str | None,
    refresh: bool,
) -> tuple[dict[str, Any], dict[str, str]]:
    if raw_path.exists() and not refresh:
        return load_cached_json(raw_path), {
            "path": relative_path(raw_path),
            "status": "reused",
        }

    if not token:
        raise PreviewFetchError(
            f"Missing {TOKEN_ENV_VAR}; cannot fetch {api_path} for {relative_path(raw_path)}."
        )

    data = fetch_tmdb_json(api_path, token)
    save_json(raw_path, data)
    return data, {
        "path": relative_path(raw_path),
        "status": "fetched",
    }


def raw_prefix(target: Target) -> str:
    media_type = "movie" if target.content_type == "movie" else "tv"
    return f"{media_type}_{target.source_id}"


def fetch_raw_payloads(
    target: Target,
    token: str | None,
    refresh: bool,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    prefix = raw_prefix(target)

    if target.content_type == "movie":
        availability_path = f"/movie/{target.source_id}/watch/providers"
        certification_path = f"/movie/{target.source_id}/release_dates"
        availability_file = RAW_OUTPUT_DIR / f"{prefix}_watch_providers.json"
        certification_file = RAW_OUTPUT_DIR / f"{prefix}_release_dates.json"
    else:
        availability_path = f"/tv/{target.source_id}/watch/providers"
        certification_path = f"/tv/{target.source_id}/content_ratings"
        availability_file = RAW_OUTPUT_DIR / f"{prefix}_watch_providers.json"
        certification_file = RAW_OUTPUT_DIR / f"{prefix}_content_ratings.json"

    availability, availability_result = fetch_or_reuse_json(
        availability_path,
        availability_file,
        token,
        refresh,
    )
    certification, certification_result = fetch_or_reuse_json(
        certification_path,
        certification_file,
        token,
        refresh,
    )

    return availability, certification, [availability_result, certification_result]


def region_list() -> list[str]:
    return [PRIMARY_REGION, *FALLBACK_REGIONS]


def provider_rows_for_region(
    availability_payload: dict[str, Any],
    region_code: str,
    warnings: list[str],
) -> list[dict[str, Any]]:
    results = availability_payload.get("results")
    if not isinstance(results, dict):
        warnings.append("Watch-provider response has no usable results object.")
        return []

    region_result = results.get(region_code)
    if not isinstance(region_result, dict):
        warnings.append(f"No {region_code} availability returned.")
        return []

    rows: list[dict[str, Any]] = []
    known_non_provider_keys = {"link"}

    for group_name, providers in region_result.items():
        if group_name in known_non_provider_keys:
            continue

        availability_type = AVAILABILITY_TYPE_MAP.get(group_name)
        if not availability_type:
            warnings.append(
                f"Unknown TMDb availability group '{group_name}' for {region_code}; skipped."
            )
            continue

        if not isinstance(providers, list):
            warnings.append(
                f"TMDb availability group '{group_name}' for {region_code} was not a list."
            )
            continue

        for provider in providers:
            if not isinstance(provider, dict):
                warnings.append(
                    f"Invalid provider row in {region_code}/{group_name}; skipped."
                )
                continue

            source_provider_id = provider.get("provider_id")
            if source_provider_id is None:
                warnings.append(
                    f"Provider '{provider.get('provider_name')}' in {region_code}/{group_name} has no source_provider_id."
                )

            rows.append(
                {
                    "region_code": region_code,
                    "availability_type": availability_type,
                    "provider_name": provider.get("provider_name"),
                    "source_provider_id": (
                        str(source_provider_id) if source_provider_id is not None else None
                    ),
                    "display_priority": provider.get("display_priority"),
                    "logo_path": provider.get("logo_path"),
                    "source_name": "tmdb",
                }
            )

    return rows


def normalize_availability(
    availability_payload: dict[str, Any],
    warnings: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for region_code in region_list():
        rows.extend(provider_rows_for_region(availability_payload, region_code, warnings))
    return rows


def certification_priority(country_code: str, index: int) -> int:
    if country_code == PRIMARY_REGION:
        return index + 1
    fallback_offset = 100
    try:
        fallback_index = FALLBACK_REGIONS.index(country_code)
    except ValueError:
        fallback_index = len(FALLBACK_REGIONS)
    return fallback_offset + (fallback_index * 100) + index + 1


def normalize_movie_certifications(
    certification_payload: dict[str, Any],
    warnings: list[str],
) -> list[dict[str, Any]]:
    results = certification_payload.get("results")
    if not isinstance(results, list):
        warnings.append("Movie release_dates response has no usable results array.")
        return []

    rows: list[dict[str, Any]] = []
    by_region = {
        item.get("iso_3166_1"): item
        for item in results
        if isinstance(item, dict) and item.get("iso_3166_1") in region_list()
    }

    for region_code in region_list():
        region_entry = by_region.get(region_code)
        if not isinstance(region_entry, dict):
            warnings.append(f"No {region_code} certification region returned.")
            continue

        release_dates = region_entry.get("release_dates")
        if not isinstance(release_dates, list):
            warnings.append(f"{region_code} release_dates was not a list.")
            continue

        region_rows = []
        for release_index, release in enumerate(release_dates):
            if not isinstance(release, dict):
                continue

            certification = clean_text(release.get("certification"))
            if not certification:
                continue

            release_type = release.get("type")
            region_rows.append(
                {
                    "country_code": region_code,
                    "certification": certification,
                    "rating_system": region_code,
                    "source_name": "tmdb",
                    "source_priority": certification_priority(
                        region_code,
                        release_index,
                    ),
                    "release_type": release_type,
                    "release_type_name": MOVIE_RELEASE_TYPE_NAMES.get(release_type),
                    "notes": None,
                }
            )

        if not region_rows:
            warnings.append(f"No non-empty {region_code} certification returned.")
        rows.extend(region_rows)

    return rows


def normalize_tv_certifications(
    certification_payload: dict[str, Any],
    warnings: list[str],
) -> list[dict[str, Any]]:
    results = certification_payload.get("results")
    if not isinstance(results, list):
        warnings.append("TV content_ratings response has no usable results array.")
        return []

    rows: list[dict[str, Any]] = []
    by_region = {
        item.get("iso_3166_1"): item
        for item in results
        if isinstance(item, dict) and item.get("iso_3166_1") in region_list()
    }

    for region_code in region_list():
        region_entry = by_region.get(region_code)
        if not isinstance(region_entry, dict):
            warnings.append(f"No {region_code} certification region returned.")
            continue

        rating = clean_text(region_entry.get("rating"))
        if not rating:
            warnings.append(f"No non-empty {region_code} certification returned.")
            continue

        rows.append(
            {
                "country_code": region_code,
                "certification": rating,
                "rating_system": region_code,
                "source_name": "tmdb",
                "source_priority": certification_priority(region_code, 0),
                "notes": None,
            }
        )

    return rows


def choose_certification(
    certifications: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for country_code in region_list():
        matching = [
            row
            for row in certifications
            if row.get("country_code") == country_code and row.get("certification")
        ]
        if not matching:
            continue

        chosen = sorted(
            matching,
            key=lambda row: (
                row.get("source_priority") if row.get("source_priority") is not None else 9999,
                str(row.get("certification") or ""),
            ),
        )[0]
        notes = None
        if country_code != PRIMARY_REGION:
            notes = f"Used {country_code} fallback because {PRIMARY_REGION} certification was unavailable."
        return {
            "country_code": chosen.get("country_code"),
            "certification": chosen.get("certification"),
            "rating_system": chosen.get("rating_system"),
            "source_name": chosen.get("source_name"),
            "notes": notes,
        }

    return None


def build_preview_item(
    target: Target,
    availability_payload: dict[str, Any],
    certification_payload: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = []
    availability = normalize_availability(availability_payload, warnings)

    if target.content_type == "movie":
        certifications = normalize_movie_certifications(certification_payload, warnings)
    else:
        certifications = normalize_tv_certifications(certification_payload, warnings)

    chosen_certification = choose_certification(certifications)
    if not chosen_certification:
        warnings.append("No IN or US certification candidate found.")

    return {
        "title": target.title,
        "content_type": target.content_type,
        "source_name": target.source_name,
        "source_id": target.source_id,
        "availability": availability,
        "certifications": certifications,
        "chosen_certification": chosen_certification,
        "warnings": warnings,
    }


def count_availability_for_region(item: dict[str, Any], region_code: str) -> int:
    availability = item.get("availability")
    if not isinstance(availability, list):
        return 0
    return sum(1 for row in availability if row.get("region_code") == region_code)


def print_item_summary(item: dict[str, Any]) -> None:
    title = item.get("title")
    in_count = count_availability_for_region(item, PRIMARY_REGION)
    us_count = count_availability_for_region(item, "US")
    certifications = item.get("certifications") or []
    chosen = item.get("chosen_certification")
    chosen_text = "none"
    if isinstance(chosen, dict) and chosen.get("certification"):
        chosen_text = (
            f"{chosen.get('certification')} "
            f"({chosen.get('country_code')}/{chosen.get('rating_system')})"
        )
    warnings = item.get("warnings") or []

    print(f"- {title}")
    print(f"  IN availability rows: {in_count}")
    print(f"  US availability rows: {us_count}")
    print(f"  certification rows: {len(certifications)}")
    print(f"  chosen certification: {chosen_text}")
    print(f"  warnings: {len(warnings)}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    targets_path = resolve_path(args.targets)
    token = os.environ.get(TOKEN_ENV_VAR)

    if not token:
        print(
            f"{TOKEN_ENV_VAR} is not set. Existing raw files can still be reused, "
            "but missing raw files or --refresh will fail."
        )

    try:
        targets, target_warnings, skipped_targets = load_targets(targets_path)
    except PreviewFetchError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    selected_targets = filter_targets(targets, args)
    if not selected_targets:
        selector = args.source_id or args.title or "default pipeline_test target"
        print(f"No matching TMDb targets found for {selector}.", file=sys.stderr)
        return 1

    stats = FetchStats(
        targets_loaded=len(targets),
        targets_skipped=skipped_targets,
        warnings=target_warnings.copy(),
    )
    items: list[dict[str, Any]] = []

    RAW_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    RUN_REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Target config: {relative_path(targets_path)}")
    print(f"Targets loaded: {len(targets)}")
    print(f"Targets selected: {len(selected_targets)}")
    print(f"Targets not selected: {len(targets) - len(selected_targets)}")
    print(f"Filters used: {filters_used(args)}")

    for target in selected_targets:
        print(f"\nProcessing {target.title} ({target.content_type}, TMDb {target.source_id})...")
        try:
            availability_payload, certification_payload, raw_file_results = fetch_raw_payloads(
                target,
                token,
                args.refresh,
            )
        except PreviewFetchError as exc:
            message = f"{target.title}: fetch failed: {exc}"
            stats.warnings.append(message)
            stats.failures.append(message)
            stats.per_target.append(
                {
                    "title": target.title,
                    "content_type": target.content_type,
                    "source_name": target.source_name,
                    "source_id": target.source_id,
                    "priority": target.priority,
                    "status": "failed",
                    "raw_files": [],
                    "warnings": [str(exc)],
                }
            )
            print(f"  Warning: {message}")
            continue

        stats.targets_processed += 1
        for raw_file in raw_file_results:
            if raw_file["status"] == "fetched":
                stats.raw_files_fetched.append(raw_file["path"])
            else:
                stats.raw_files_reused.append(raw_file["path"])
            print(f"  {raw_file['status']} {raw_file['path']}")

        item = build_preview_item(target, availability_payload, certification_payload)
        stats.availability_rows += len(item["availability"])
        stats.certification_rows += len(item["certifications"])
        stats.warnings.extend(f"{target.title}: {warning}" for warning in item["warnings"])
        items.append(item)
        target_status = (
            "fetched"
            if any(raw_file["status"] == "fetched" for raw_file in raw_file_results)
            else "reused"
        )
        if target_status == "fetched":
            stats.targets_fetched += 1
        else:
            stats.targets_reused += 1
        stats.per_target.append(
            {
                "title": target.title,
                "content_type": target.content_type,
                "source_name": target.source_name,
                "source_id": target.source_id,
                "priority": target.priority,
                "status": target_status,
                "raw_files": raw_file_results,
                "warnings": item["warnings"],
            }
        )
        print_item_summary(item)

    preview = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inspection_only": True,
        "source_provider": "tmdb",
        "primary_region": PRIMARY_REGION,
        "fallback_regions": FALLBACK_REGIONS,
        "items": items,
        "summary": {
            "targets_loaded": stats.targets_loaded,
            "targets_processed": stats.targets_processed,
            "targets_skipped": stats.targets_skipped,
            "availability_rows": stats.availability_rows,
            "certification_rows": stats.certification_rows,
            "warnings": len(stats.warnings),
        },
    }
    save_json(PROCESSED_OUTPUT_PATH, preview)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "script_name": Path(__file__).name,
        "target_config_path": relative_path(targets_path),
        "filters_used": filters_used(args),
        "targets_loaded": len(targets),
        "targets_selected": len(selected_targets),
        "targets_processed": stats.targets_processed,
        "targets_skipped": stats.targets_skipped,
        "raw_files_fetched": stats.raw_files_fetched,
        "raw_files_reused": stats.raw_files_reused,
        "warnings": stats.warnings,
        "failures": stats.failures,
        "per_target": stats.per_target,
    }
    save_json(RUN_REPORT_OUTPUT_PATH, report)

    print("\nSummary")
    print(f"Processed preview: {relative_path(PROCESSED_OUTPUT_PATH)}")
    print(f"Run report: {relative_path(RUN_REPORT_OUTPUT_PATH)}")
    print(f"Filters used: {filters_used(args)}")
    print(f"Selected target count: {len(selected_targets)}")
    print(f"Targets processed: {stats.targets_processed}")
    print(f"Fetched count: {stats.targets_fetched}")
    print(f"Reused count: {stats.targets_reused}")
    print(f"Skipped count: {stats.targets_skipped}")
    print(f"Failure count: {len(stats.failures)}")
    print(f"Availability rows: {stats.availability_rows}")
    print(f"Certification rows: {stats.certification_rows}")
    print(f"Warnings: {len(stats.warnings)}")
    if stats.warnings:
        for warning in stats.warnings[:10]:
            print(f"  - {warning}")
        if len(stats.warnings) > 10:
            print(f"  ... {len(stats.warnings) - 10} more warnings")
    print("No database changes were made.")
    print("No backend, frontend, schema, or sample_data changes were made.")

    return 0 if stats.targets_processed else 1


if __name__ == "__main__":
    raise SystemExit(main())
