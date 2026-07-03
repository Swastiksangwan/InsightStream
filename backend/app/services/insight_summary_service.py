from datetime import date, datetime


UNSUPPORTED_MARKETING_PHRASES = (
    "must-watch",
    "masterpiece",
    "critically acclaimed",
    "audiences love",
    "universally loved",
)


def empty_insight_summary():
    return {
        "headline": None,
        "summary": None,
        "best_for": [],
        "key_signals": [],
        "watch_note": None,
        "generated_from": [],
        "confidence": "low",
    }


def has_text(value):
    return isinstance(value, str) and bool(value.strip())


def unique_preserve_order(values):
    seen = set()
    unique_values = []
    for value in values:
        if not has_text(value):
            continue
        key = value.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique_values.append(value.strip())
    return unique_values


def clean_summary_platform_name(value):
    if not has_text(value):
        return None

    name = " ".join(value.strip().split())
    lower_name = name.lower()

    if "amazon prime video" in lower_name:
        return "Amazon Prime Video"

    if lower_name.startswith("apple tv") and "channel" in lower_name:
        return "Apple TV"

    if lower_name.endswith(" with ads"):
        return name[: -len(" with ads")].strip()

    return name


def clean_summary_platform_names(names):
    return unique_preserve_order(
        name for name in (clean_summary_platform_name(value) for value in names) if name
    )


def title_case_phrase(value):
    if not has_text(value):
        return value
    return " ".join(word[:1].upper() + word[1:] for word in value.split())


def lower_first(value):
    if not has_text(value):
        return value
    stripped = value.strip()
    return stripped[:1].lower() + stripped[1:]


def article_for(phrase):
    if not has_text(phrase):
        return "A"
    return "An" if phrase.strip()[0].lower() in {"a", "e", "i", "o", "u"} else "A"


def sentence_case(value):
    if not has_text(value):
        return value
    stripped = value.strip()
    return stripped[:1].upper() + stripped[1:]


def format_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        try:
            parsed = date.fromisoformat(str(value))
        except ValueError:
            return str(value)

    return parsed.strftime("%b %d, %Y").replace(" 0", " ")


def format_status(status):
    if not has_text(status) or status == "unknown":
        return None
    status_map = {
        "ongoing": "ongoing",
        "ended": "completed",
        "cancelled": "cancelled",
        "upcoming": "upcoming",
    }
    return status_map.get(status.strip().lower(), status.strip().lower())


def normalized_genre_tokens(genres):
    tokens = []
    for genre in unique_preserve_order(genres or []):
        normalized = genre.lower().replace("&", "and").strip()
        if normalized in {"sci-fi and fantasy", "science fiction and fantasy"}:
            tokens.extend(["sci-fi", "fantasy"])
        elif normalized in {"science fiction", "sci fi"}:
            tokens.append("sci-fi")
        elif normalized == "history":
            tokens.append("history")
        else:
            tokens.append(normalized)
    return unique_preserve_order(tokens)


def readable_genre_label(genres):
    tokens = normalized_genre_tokens(genres)
    if not tokens:
        return None

    normalized = set(tokens)

    if {"drama", "history"} <= normalized:
        return "historical drama"
    if "animation" in normalized and ("action" in normalized or "adventure" in normalized):
        return "animated action-adventure"
    if {"fantasy", "drama"} <= normalized:
        return "fantasy-drama"
    if {"crime", "drama"} <= normalized:
        return "crime drama"
    if {"mystery", "sci-fi"} <= normalized:
        return "mystery sci-fi"
    if {"horror", "mystery"} <= normalized:
        return "mystery-horror"
    if {"comedy", "drama"} <= normalized:
        return "drama-comedy"
    if {"action", "adventure", "drama"} <= normalized:
        return "action-adventure drama"
    if {"action", "adventure"} <= normalized:
        return "action-adventure"

    selected = tokens[:2]
    if len(selected) == 1:
        return selected[0]

    return " ".join(selected)


def first_credit_name(credits, bucket_name, job_name=None):
    if not credits:
        return None

    for credit in credits.get(bucket_name, []) or []:
        if job_name and (credit.get("job") or "").lower() != job_name.lower():
            continue
        if has_text(credit.get("name")):
            return credit["name"].strip()

    if job_name:
        for credit in credits.get("crew", []) or []:
            job_matches = (credit.get("job") or "").lower() == job_name.lower()
            if job_matches and has_text(credit.get("name")):
                return credit["name"].strip()

    return None


def has_credit_data(credits):
    if not credits:
        return False
    return any(
        credits.get(bucket)
        for bucket in ("cast", "directors", "creators", "crew")
    )


def rating_context(ratings):
    score = (ratings or {}).get("unified_score")
    if score is None:
        return {
            "score": None,
            "strength": None,
            "headline_phrase": None,
            "signal": None,
            "summary_phrase": None,
        }

    sources = (ratings or {}).get("sources") or []
    scoring_source_count = (ratings or {}).get("scoring_source_count")
    if scoring_source_count is None:
        scoring_source_count = (ratings or {}).get("source_count") or len(sources)
    if scoring_source_count <= 0:
        scoring_source_count = 1

    source_name = (
        f"{scoring_source_count} scoring source"
        f"{'' if scoring_source_count == 1 else 's'}"
    )

    if score >= 80:
        strength = "Strong"
        headline_phrase = "strong audience backing"
    elif score >= 70:
        strength = "Positive"
        headline_phrase = "positive audience backing"
    elif score >= 60:
        strength = "Mixed-to-positive"
        headline_phrase = "mixed-to-positive audience signal"
    else:
        strength = "Moderate"
        headline_phrase = "moderate rating signal"

    signal = f"{strength} · {score}/100 from {source_name}"

    return {
        "score": score,
        "strength": strength,
        "headline_phrase": headline_phrase,
        "signal": signal,
        "summary_phrase": lower_first(headline_phrase),
    }


def region_label(region_code):
    return {
        "IN": "India",
        "US": "US",
    }.get(region_code, region_code)


def platform_names_for_types(platforms, availability_types):
    names = []
    normalized_types = set(availability_types)
    for platform in platforms:
        availability_type = str(platform.get("availability_type") or "").lower()
        if availability_type not in normalized_types:
            continue
        if has_text(platform.get("name")):
            names.append(platform["name"].strip())
    return clean_summary_platform_names(names)


def format_platform_names(names):
    if not names:
        return None
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}, {names[1]}"
    return f"{names[0]}, {names[1]} + more"


def availability_context(platforms):
    if not platforms:
        return None

    types = {
        str(platform.get("availability_type") or "").lower()
        for platform in platforms
    }
    region_code = next(
        (
            platform.get("region_code")
            for platform in platforms
            if platform.get("region_code")
        ),
        None,
    )
    region = region_label(region_code)
    suffix = f" in {region}" if region else ""

    if "streaming" in types:
        kind = "streaming"
        names = platform_names_for_types(platforms, {"streaming"})
        platform_text = format_platform_names(names)
        value = f"Streaming{suffix}"
        if platform_text:
            value += f" on {platform_text}"
        summary_phrase = f"{platform_text or 'streaming'} availability{suffix}"
    elif "rent" in types or "buy" in types:
        kind = "rent_buy"
        names = platform_names_for_types(platforms, {"rent", "buy"})
        platform_text = format_platform_names(names)
        value = f"Rent/buy{suffix}"
        if platform_text:
            value += f" on {platform_text}"
        summary_phrase = f"rent/buy availability{suffix}"
    elif "free" in types or "ads" in types:
        kind = "free_ads"
        names = platform_names_for_types(platforms, {"free", "ads"})
        platform_text = format_platform_names(names)
        value = f"Free/ad-supported{suffix}"
        if platform_text:
            value += f" on {platform_text}"
        summary_phrase = f"free or ad-supported availability{suffix}"
    else:
        kind = "listed"
        names = []
        platform_text = None
        value = f"Availability listed{suffix}"
        summary_phrase = f"availability data{suffix}"

    return {
        "kind": kind,
        "value": value,
        "summary_phrase": summary_phrase,
        "platform_names": names,
        "platform_text": platform_text,
        "region": region,
    }


def add_signal(signals, label, value):
    if has_text(value):
        signals.append({"label": label, "value": value.strip()})


def add_generated_from(generated_from, source):
    if source not in generated_from:
        generated_from.append(source)


def compute_confidence(
    has_overview,
    has_genres,
    has_rating,
    has_availability,
    has_credits,
):
    present = sum([has_overview, has_genres, has_rating, has_availability, has_credits])
    if present >= 5:
        return "high"
    if present >= 3:
        return "medium"
    return "low"


def build_movie_summary(content, genre_label, director, rating, availability):
    runtime = content.get("runtime")
    subject = genre_label or "movie"
    rating_phrase = rating["headline_phrase"]
    has_rent_buy_access = availability and availability["kind"] == "rent_buy"

    if runtime and runtime > 150 and rating_phrase:
        headline = f"Long-form {subject} with {rating_phrase}."
    elif has_rent_buy_access and rating_phrase:
        headline = f"Rent/buy movie with {rating_phrase}."
    elif rating_phrase and director:
        headline = f"{sentence_case(subject)} with {rating_phrase} and a clear creative signal."
    elif rating_phrase:
        headline = f"{sentence_case(subject)} with {rating_phrase}."
    elif runtime and runtime > 150:
        headline = f"Long-form {subject} with local decision signals."
    else:
        headline = f"{sentence_case(subject)} with local decision signals."

    identity_parts = ["long-form" if runtime and runtime > 150 else None, subject]
    identity = " ".join(part for part in identity_parts if part)
    summary = f"{article_for(identity)} {identity}"
    support = []
    if rating["summary_phrase"]:
        support.append(rating["summary_phrase"])
    if availability:
        support.append(availability["summary_phrase"])
    if support:
        summary += f" with {' and '.join(support)}"
    summary += "."

    if runtime and runtime > 150:
        summary += " Better for a planned watch session than a quick casual pick."
    elif has_rent_buy_access:
        summary += " A better fit when you are comfortable renting or buying."

    return headline, summary


def format_next_season(series_metadata):
    next_season_number = (series_metadata or {}).get("next_season_number")
    if not next_season_number:
        return None

    next_season = f"Season {next_season_number}"
    next_season_date = format_date((series_metadata or {}).get("next_season_air_date"))
    next_season_year = (series_metadata or {}).get("next_season_year")
    if next_season_date:
        return f"{next_season} dated {next_season_date}"
    if next_season_year:
        return f"{next_season} expected in {next_season_year}"
    return f"{next_season} announced"


def format_season_commitment(series_metadata):
    if not series_metadata:
        return None

    released_seasons = series_metadata.get("released_seasons_count")
    parts = []
    if released_seasons is not None:
        parts.append(
            f"{released_seasons} released season{'s' if released_seasons != 1 else ''}"
        )

    next_season = format_next_season(series_metadata)
    if next_season:
        parts.append(next_season)

    return ", ".join(parts) if parts else None


def build_series_summary(
    content,
    genre_label,
    creator,
    rating,
    availability,
    series_metadata,
):
    status_label = format_status((series_metadata or {}).get("series_status_normalized"))
    released_seasons = (series_metadata or {}).get("released_seasons_count")
    subject = f"{genre_label or 'series'} series"
    rating_phrase = rating["headline_phrase"]
    next_episode_date = format_date((series_metadata or {}).get("next_episode_air_date"))
    next_season = format_next_season(series_metadata)

    if status_label == "ongoing" and next_episode_date:
        headline = f"Active {subject} with an upcoming episode date."
    elif status_label == "ongoing" and rating_phrase:
        headline = f"Ongoing {subject} with {rating_phrase}."
    elif status_label == "completed" and rating_phrase:
        headline = f"Completed {subject} with {rating_phrase}."
    elif status_label == "completed":
        headline = f"Completed {subject} suited for binge viewing."
    elif status_label == "upcoming":
        headline = f"Upcoming {subject} with local decision signals."
    elif rating_phrase:
        headline = f"{sentence_case(subject)} with {rating_phrase}."
    else:
        headline = f"{sentence_case(subject)} with local decision signals."

    identity_parts = []
    if status_label:
        identity_parts.append(status_label)
    identity_parts.append(subject)
    identity = " ".join(identity_parts)
    base = f"{article_for(identity)} {identity}"
    if released_seasons:
        base += f" with {released_seasons} released season{'s' if released_seasons != 1 else ''}"
    if next_episode_date:
        base += f" and a next episode dated {next_episode_date}"
    elif next_season:
        base += f" and {next_season}"

    support = []
    if rating["summary_phrase"]:
        support.append(rating["summary_phrase"])
    if availability:
        support.append(availability["summary_phrase"])

    summary = base
    if support:
        connector = " and " if " with " in summary else " with "
        summary += f"{connector}{' and '.join(support)}"
        if status_label == "completed":
            summary += ". Good fit for a finished binge with no weekly-release wait"
        elif status_label == "ongoing":
            summary += ". Best for viewers who want to follow an active series; wait if you prefer completed shows"
        else:
            summary += ". Useful local context before deciding where it fits"
    else:
        summary += "."

    if not summary.endswith("."):
        summary += "."

    return headline, summary


def best_genre_chip(content_type, genre_label, runtime=None, status_label=None):
    if not genre_label:
        return None

    if content_type == "movie":
        if runtime and runtime > 150:
            return f"Long-form {genre_label}"
        return title_case_phrase(genre_label)

    if status_label == "ongoing":
        return f"Serialized {genre_label}"
    if status_label == "completed":
        return f"{title_case_phrase(genre_label)} binge"

    return title_case_phrase(genre_label)


def access_chip(availability):
    if not availability:
        return None
    names = availability.get("platform_names") or []
    if availability["kind"] == "streaming" and names:
        return f"{names[0]} viewers"
    if availability["kind"] == "rent_buy":
        return "Rent/buy viewers"
    if availability["kind"] == "free_ads":
        return "Free/ad-supported viewers"
    return None


def build_best_for(content_type, genre_label, runtime, series_status, rating, availability):
    best_for = []
    status_label = format_status(series_status)

    genre_chip = best_genre_chip(content_type, genre_label, runtime, status_label)
    if genre_chip:
        best_for.append(genre_chip)

    if content_type == "series":
        if status_label == "ongoing":
            best_for.append("Ongoing release followers")
        elif status_label == "completed":
            best_for.append("Completed-series binge")
        elif status_label == "upcoming":
            best_for.append("Upcoming series trackers")

    access = access_chip(availability)
    if access:
        best_for.append(access)

    if rating["score"] is not None and rating["score"] >= 80:
        best_for.append("Strong audience score")

    return unique_preserve_order(best_for)[:4]


def build_watch_note(content_type, runtime, series_metadata, availability, confidence):
    if content_type == "movie":
        if runtime and runtime > 150:
            return "Better for a focused watch session than a quick casual pick."
        if availability and availability["kind"] == "rent_buy":
            return "A better fit when you are comfortable renting or buying; no streaming option is currently stored for India."
        if confidence == "low":
            return "Decision support is limited because ratings, availability, or credits are incomplete."
        return None

    if content_type == "series" and series_metadata:
        status_label = format_status(series_metadata.get("series_status_normalized"))
        if status_label == "ongoing" and series_metadata.get("next_episode_air_date"):
            return "Best for viewers who want to follow an active release; wait if you prefer completed seasons."
        if (
            status_label == "ongoing"
            and series_metadata.get("has_announced_season")
            and series_metadata.get("next_season_number")
        ):
            return "Good for catching up before the next season; wait if you only watch completed shows."
        if status_label == "ongoing":
            return "Best for viewers who want to follow an active series; wait if you prefer completed shows."
        if status_label == "completed":
            return "Good fit for a finished binge with no weekly-release wait."

    if confidence == "low":
        return "Decision support is limited because ratings, availability, or credits are incomplete."

    return None


def ensure_sentence(value):
    if not has_text(value):
        return value
    stripped = value.strip()
    return stripped if stripped.endswith(".") else f"{stripped}."


def source_watch_profile(decision_layer):
    if not decision_layer:
        return None
    profile = decision_layer.get("watch_profile") or {}
    if has_text(profile.get("watch_feel")):
        return profile
    if profile.get("chips") or profile.get("best_for") or profile.get("consider_first"):
        return profile
    return None


def source_profile_summary(
    watch_profile,
    content_type,
    rating,
    availability,
    series_metadata,
):
    watch_feel = watch_profile.get("watch_feel")
    if not has_text(watch_feel):
        return None

    summary = ensure_sentence(watch_feel)
    support = []
    if rating["summary_phrase"]:
        support.append(rating["summary_phrase"])
    if availability:
        support.append(availability["summary_phrase"])

    if content_type == "series":
        status_label = format_status(
            (series_metadata or {}).get("series_status_normalized")
        )
        if status_label == "ongoing":
            support.append("ongoing-series context")
        elif status_label == "completed":
            support.append("completed-series context")

    if support:
        summary += f" It also has {' and '.join(unique_preserve_order(support))}."

    return summary


def source_profile_signal_value(watch_profile):
    chips = watch_profile.get("chips") or []
    if chips:
        return ", ".join(chips[:2])

    best_for = watch_profile.get("best_for") or []
    if best_for:
        return best_for[0]

    return None


def build_insight_summary(content_detail: dict) -> dict:
    content = content_detail.get("content") or {}
    genres = content_detail.get("genres") or []
    platforms = content_detail.get("platforms") or []
    ratings = content_detail.get("ratings") or {}
    series_metadata = content_detail.get("series_metadata") or None
    credits = content_detail.get("credits") or {}
    decision_layer = content_detail.get("decision_layer") or None
    watch_profile = source_watch_profile(decision_layer)

    has_overview = has_text(content.get("overview"))
    has_genres = bool(genres)
    has_availability = bool(platforms)
    has_credits = has_credit_data(credits)
    rating = rating_context(ratings)
    has_rating = rating["score"] is not None

    if not any([
        has_overview,
        has_genres,
        has_availability,
        has_credits,
        has_rating,
        series_metadata,
        watch_profile,
    ]):
        return empty_insight_summary()

    content_type = content.get("type")
    genre_label = readable_genre_label(genres)
    runtime = content.get("runtime")
    key_signals = []
    generated_from = []

    availability = availability_context(platforms)
    director = (
        first_credit_name(credits, "directors")
        or first_credit_name(credits, "crew", "Director")
    )
    creator = (
        first_credit_name(credits, "creators")
        or first_credit_name(credits, "crew", "Creator")
    )

    if content_type == "series":
        headline, summary = build_series_summary(
            content,
            genre_label,
            creator,
            rating,
            availability,
            series_metadata,
        )
    else:
        headline, summary = build_movie_summary(
            content,
            genre_label,
            director,
            rating,
            availability,
        )

    if watch_profile:
        if has_text(watch_profile.get("watch_feel")):
            headline = ensure_sentence(watch_profile["watch_feel"])
        enriched_summary = source_profile_summary(
            watch_profile,
            content_type,
            rating,
            availability,
            series_metadata,
        )
        if enriched_summary:
            summary = enriched_summary

    if has_overview or has_genres:
        add_generated_from(generated_from, "metadata")

    if watch_profile:
        watch_fit_signal = source_profile_signal_value(watch_profile)
        add_signal(key_signals, "Watch fit", watch_fit_signal)
        add_generated_from(generated_from, "watch_profile")

    if rating["signal"]:
        add_signal(key_signals, "Audience", rating["signal"])
        add_generated_from(generated_from, "ratings")

    if availability:
        add_signal(key_signals, "Access", availability["value"])
        add_generated_from(generated_from, "availability")

    if content_type == "movie":
        if runtime and runtime > 150:
            add_signal(key_signals, "Runtime", "Long movie")
        if director:
            add_signal(key_signals, "Creative lead", f"Directed by {director}")
    else:
        if series_metadata:
            add_generated_from(generated_from, "series_metadata")
        status_label = format_status(
            (series_metadata or {}).get("series_status_normalized")
        )
        season_commitment = format_season_commitment(series_metadata)
        if status_label == "completed":
            add_signal(
                key_signals,
                "Series status",
                f"Completed — {season_commitment}" if season_commitment else "Completed",
            )
        elif season_commitment:
            add_signal(key_signals, "Watch fit", season_commitment)

        next_episode_date = format_date(
            (series_metadata or {}).get("next_episode_air_date")
        )
        next_season = format_next_season(series_metadata)
        if status_label == "ongoing" and next_episode_date:
            add_signal(
                key_signals,
                "Series status",
                f"Ongoing, next episode {next_episode_date}",
            )
        elif status_label == "ongoing" and next_season:
            add_signal(key_signals, "Series status", f"Ongoing, {next_season}")
        elif status_label and status_label != "completed":
            add_signal(key_signals, "Series status", title_case_phrase(status_label))
        if creator:
            add_signal(key_signals, "Creative lead", f"Created by {creator}")

    if content.get("age_rating"):
        add_signal(key_signals, "Age rating", content["age_rating"])
        add_generated_from(generated_from, "certification")

    if has_credits:
        add_generated_from(generated_from, "credits")

    confidence = compute_confidence(
        has_overview,
        has_genres,
        has_rating,
        has_availability,
        has_credits,
    )
    best_for = build_best_for(
        content_type,
        genre_label,
        runtime,
        (series_metadata or {}).get("series_status_normalized"),
        rating,
        availability,
    )
    if watch_profile:
        best_for = unique_preserve_order(
            (watch_profile.get("best_for") or [])
            + (watch_profile.get("chips") or [])
            + best_for
        )[:4]
    watch_note = build_watch_note(
        content_type,
        runtime,
        series_metadata,
        availability,
        confidence,
    )
    if watch_profile and watch_profile.get("consider_first"):
        watch_note = watch_profile["consider_first"][0]

    return {
        "headline": headline,
        "summary": summary,
        "best_for": best_for,
        "key_signals": key_signals[:5],
        "watch_note": watch_note,
        "generated_from": generated_from,
        "confidence": confidence,
    }
