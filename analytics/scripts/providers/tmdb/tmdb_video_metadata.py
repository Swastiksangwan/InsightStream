#!/usr/bin/env python3
"""Normalize TMDb video metadata and select a deterministic primary video."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


SUPPORTED_SITES = {
    "youtube": "YouTube",
    "vimeo": "Vimeo",
}
PLAYABLE_SITES = {"YouTube"}
YOUTUBE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
VIMEO_KEY_PATTERN = re.compile(r"^[0-9]{4,32}$")
GENERIC_SITE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._+-]{0,49}$")
GENERIC_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{4,255}$")
ACCESSIBILITY_VARIANT_PATTERN = re.compile(
    r"\b(?:"
    r"audio[\s-]+described|"
    r"audio[\s-]+description|"
    r"descriptive[\s-]+audio|"
    r"signed[\s-]+trailer|"
    r"(?:american[\s-]+)?sign[\s-]+language|"
    r"asl[\s-]+(?:trailer|version)"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VideoNormalizationResult:
    video: dict[str, Any] | None
    rejection_reason: str | None = None
    warnings: tuple[str, ...] = ()
    ignored: dict[str, Any] | None = None


@dataclass(frozen=True)
class VideoSnapshot:
    status: str
    is_complete: bool
    stale_cleanup_safe: bool
    raw_count: int
    accepted_count: int
    rejected_count: int
    rejected: list[dict[str, Any]]
    ignored_count: int
    ignored: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    videos: list[dict[str, Any]]
    primary_site: str | None
    primary_source_video_id: str | None
    retryable: bool
    failure_class: str
    error: str | None = None

    def as_preview_fields(self) -> dict[str, Any]:
        return {
            "videos_fetch_status": self.status,
            "videos_snapshot_complete": self.is_complete,
            "videos_stale_cleanup_safe": self.stale_cleanup_safe,
            "videos_fetch_error": self.error,
            "videos_raw_count": self.raw_count,
            "videos_accepted_count": self.accepted_count,
            "videos_rejected_count": self.rejected_count,
            "videos_rejected": self.rejected,
            "videos_ignored_count": self.ignored_count,
            "videos_ignored": self.ignored,
            "videos_warnings": self.warnings,
            "videos": self.videos,
            "primary_video_site": self.primary_site,
            "primary_video_source_id": self.primary_source_video_id,
            "videos_retryable": self.retryable,
            "videos_failure_class": self.failure_class,
        }


def clean_optional_text(value: Any, max_length: int | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if max_length is not None:
        return cleaned[:max_length]
    return cleaned


def canonical_site(value: Any) -> str | None:
    site = clean_optional_text(value, 50)
    if not site:
        return None
    return SUPPORTED_SITES.get(site.casefold())


def is_valid_source_video_id(site: str, value: Any) -> bool:
    key = clean_optional_text(value, 255)
    if not key:
        return False
    if site == "YouTube":
        return bool(YOUTUBE_KEY_PATTERN.fullmatch(key))
    if site == "Vimeo":
        return bool(VIMEO_KEY_PATTERN.fullmatch(key))
    return False


def normalize_timestamp(value: Any) -> str | None:
    text = clean_optional_text(value, 80)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_size(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def normalize_tmdb_video_record(record: Any) -> VideoNormalizationResult:
    if not isinstance(record, dict):
        return VideoNormalizationResult(None, "video record is not an object")

    raw_site = clean_optional_text(record.get("site"), 50)
    if not raw_site:
        return VideoNormalizationResult(None, "site is missing")

    source_video_id = clean_optional_text(record.get("key"), 255)
    if not source_video_id:
        return VideoNormalizationResult(None, "video key is missing")

    site = canonical_site(raw_site)
    if not site:
        if GENERIC_SITE_PATTERN.fullmatch(raw_site) and GENERIC_KEY_PATTERN.fullmatch(
            source_video_id
        ):
            return VideoNormalizationResult(
                None,
                ignored={
                    "site": raw_site,
                    "source_video_id": source_video_id,
                    "reason": "unsupported provider is intentionally not stored",
                },
            )
        return VideoNormalizationResult(
            None,
            "unsupported provider does not have a safe stable identity",
        )

    if not is_valid_source_video_id(site, source_video_id):
        return VideoNormalizationResult(
            None,
            "video key contains unsupported characters",
        )

    published_at = None
    warnings: list[str] = []
    if record.get("published_at") not in (None, ""):
        published_at = normalize_timestamp(record.get("published_at"))
        if published_at is None:
            warnings.append("published_at is malformed and was preserved as null")

    official = record.get("official")
    if not isinstance(official, bool):
        official = None

    return VideoNormalizationResult(
        {
            "source": "tmdb",
            "source_video_id": source_video_id,
            "site": site,
            "video_type": clean_optional_text(record.get("type"), 50),
            "name": clean_optional_text(record.get("name")),
            "official": official,
            "language_code": clean_optional_text(record.get("iso_639_1"), 16),
            "country_code": clean_optional_text(record.get("iso_3166_1"), 16),
            "published_at": published_at,
            "size": normalize_size(record.get("size")),
            "is_primary": False,
        },
        warnings=tuple(warnings),
    )


def normalize_tmdb_video(record: Any) -> tuple[dict[str, Any] | None, str | None]:
    result = normalize_tmdb_video_record(record)
    return result.video, result.rejection_reason


def _published_sort_value(value: str | datetime | None) -> float:
    if not value:
        return float("inf")
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return float("inf")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return -parsed.timestamp()


def _name_rank(video: dict[str, Any]) -> int:
    name = (video.get("name") or "").casefold()
    if "official trailer" in name:
        return 0
    if "main trailer" in name:
        return 1
    if "final trailer" in name:
        return 2
    if "trailer" in name:
        return 3
    if "official teaser" in name:
        return 4
    if "teaser" in name:
        return 5
    return 6


def is_accessibility_specific_variant(video_name: Any) -> bool:
    name = clean_optional_text(video_name)
    return bool(name and ACCESSIBILITY_VARIANT_PATTERN.search(name))


def primary_video_rank(
    video: dict[str, Any],
    preferred_language: str | None = "en",
) -> tuple[Any, ...] | None:
    if video.get("site") != "YouTube":
        return None

    video_type = (video.get("video_type") or "").casefold()
    if video_type not in {"trailer", "teaser"}:
        return None

    official = video.get("official") is True
    class_rank = {
        (True, "trailer"): 0,
        (True, "teaser"): 1,
        (False, "trailer"): 2,
        (False, "teaser"): 3,
    }[(official, video_type)]

    language = (video.get("language_code") or "").casefold()
    preferred = (preferred_language or "").casefold()
    language_rank = 0 if preferred and language == preferred else (1 if not language else 2)

    return (
        class_rank,
        language_rank,
        int(is_accessibility_specific_variant(video.get("name"))),
        _name_rank(video),
        _published_sort_value(video.get("published_at")),
        str(video.get("site") or ""),
        str(video.get("source_video_id") or ""),
    )


def select_primary_video(
    videos: list[dict[str, Any]],
    preferred_language: str | None = "en",
) -> tuple[str, str] | None:
    ranked = [
        (rank, video)
        for video in videos
        if (rank := primary_video_rank(video, preferred_language)) is not None
    ]
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0])
    selected = ranked[0][1]
    return str(selected["site"]), str(selected["source_video_id"])


def normalize_video_snapshot(
    details: dict[str, Any],
    preferred_language: str | None = "en",
) -> VideoSnapshot:
    if "videos" not in details:
        return VideoSnapshot(
            status="incomplete",
            is_complete=False,
            stale_cleanup_safe=False,
            raw_count=0,
            accepted_count=0,
            rejected_count=0,
            rejected=[],
            ignored_count=0,
            ignored=[],
            warnings=[],
            videos=[],
            primary_site=None,
            primary_source_video_id=None,
            retryable=False,
            failure_class="normalization_review",
            error="TMDb detail payload does not contain appended videos.",
        )

    videos_payload = details.get("videos")
    if not isinstance(videos_payload, dict) or not isinstance(
        videos_payload.get("results"), list
    ):
        return VideoSnapshot(
            status="incomplete",
            is_complete=False,
            stale_cleanup_safe=False,
            raw_count=0,
            accepted_count=0,
            rejected_count=0,
            rejected=[],
            ignored_count=0,
            ignored=[],
            warnings=[],
            videos=[],
            primary_site=None,
            primary_source_video_id=None,
            retryable=False,
            failure_class="normalization_review",
            error="TMDb appended videos payload is null or malformed.",
        )

    raw_results = videos_payload["results"]
    videos: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for index, record in enumerate(raw_results):
        result = normalize_tmdb_video_record(record)
        if result.ignored is not None:
            ignored.append({"index": index, **result.ignored})
            continue
        normalized = result.video
        if normalized is None:
            rejected.append(
                {"index": index, "reason": result.rejection_reason or "invalid video"}
            )
            continue
        warnings.extend(
            {"index": index, "field": "published_at", "reason": warning}
            for warning in result.warnings
        )
        identity = (normalized["site"].casefold(), normalized["source_video_id"])
        if identity in seen:
            rejected.append(
                {
                    "index": index,
                    "reason": "duplicate source video",
                    "harmless_duplicate": True,
                    "identity": {
                        "site": normalized["site"],
                        "source_video_id": normalized["source_video_id"],
                    },
                }
            )
            continue
        seen.add(identity)
        videos.append(normalized)

    primary_identity = select_primary_video(videos, preferred_language)
    for video in videos:
        video["is_primary"] = (
            str(video["site"]),
            str(video["source_video_id"]),
        ) == primary_identity

    has_unsafe_rejection = any(
        rejection.get("harmless_duplicate") is not True for rejection in rejected
    )
    status = "empty" if not raw_results else (
        "incomplete" if has_unsafe_rejection else "success"
    )
    error = None
    if has_unsafe_rejection:
        error = (
            "TMDb returned video records that could not be normalized; "
            "stale cleanup is disabled until a complete snapshot is available."
        )

    return VideoSnapshot(
        status=status,
        is_complete=not has_unsafe_rejection,
        stale_cleanup_safe=not has_unsafe_rejection,
        raw_count=len(raw_results),
        accepted_count=len(videos),
        rejected_count=len(rejected),
        rejected=rejected,
        ignored_count=len(ignored),
        ignored=ignored,
        warnings=warnings,
        videos=videos,
        primary_site=primary_identity[0] if primary_identity else None,
        primary_source_video_id=primary_identity[1] if primary_identity else None,
        retryable=False,
        failure_class="normalization_review" if has_unsafe_rejection else "none",
        error=error,
    )


def safe_video_urls(site: str, source_video_id: str) -> tuple[str | None, str | None]:
    canonical = canonical_site(site)
    if canonical != "YouTube" or not is_valid_source_video_id(
        "YouTube", source_video_id
    ):
        return None, None
    return (
        f"https://www.youtube.com/watch?v={source_video_id}",
        f"https://www.youtube-nocookie.com/embed/{source_video_id}",
    )
