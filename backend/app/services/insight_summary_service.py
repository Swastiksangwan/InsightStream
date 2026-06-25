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


def title_case_phrase(value):
    if not has_text(value):
        return value
    return " ".join(word.capitalize() for word in value.split())


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


def readable_genre_label(genres):
    selected = unique_preserve_order(genres or [])[:3]
    if not selected:
        return None

    normalized = {genre.lower() for genre in selected}

    if {"drama", "history"} <= normalized:
        return "historical drama"
    if "animation" in normalized and ("action" in normalized or "adventure" in normalized):
        return "animated action-adventure"
    if {"crime", "drama"} <= normalized:
        return "crime drama"

    lowered = [genre.lower() for genre in selected]
    if len(lowered) == 1:
        return lowered[0]
    if len(lowered) == 2:
        return "-".join(lowered)

    return f"{', '.join(lowered[:-1])}, and {lowered[-1]}"


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
            "descriptor": None,
            "signal": None,
            "summary_phrase": None,
        }

    sources = (ratings or {}).get("sources") or []
    source_count = (ratings or {}).get("source_count") or len(sources)
    if source_count == 1 and sources:
        source = sources[0]
        category = source.get("source_category") or "rating"
        source_text = f"{source.get('display_name', 'source')} {category} rating"
    else:
        source_text = f"{source_count} rating sources"

    if score >= 80:
        descriptor = "high-rated"
    elif score >= 70:
        descriptor = "well-rated"
    elif score >= 60:
        descriptor = "mixed-to-positive"
    else:
        descriptor = "moderate rating signal"

    return {
        "score": score,
        "descriptor": descriptor,
        "signal": f"{score}/100 InsightStream Score from {source_text}",
        "summary_phrase": f"{score}/100 InsightStream Score from {source_text}",
    }


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
    region_label = {
        "IN": "India",
        "US": "US",
    }.get(region_code, region_code)

    suffix = f" in {region_label}" if region_label else ""
    if "streaming" in types:
        value = f"Streaming{suffix}"
        summary_phrase = f"streaming availability{suffix}"
    elif "rent" in types or "buy" in types:
        value = f"Rent/buy{suffix}"
        summary_phrase = f"rent/buy availability{suffix}"
    elif "free" in types or "ads" in types:
        value = f"Free/ad-supported{suffix}"
        summary_phrase = f"free or ad-supported availability{suffix}"
    else:
        value = f"Availability listed{suffix}"
        summary_phrase = f"availability data{suffix}"

    return {
        "value": value,
        "summary_phrase": summary_phrase,
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
    year = content.get("year")
    subject = genre_label or "movie"
    director_clause = f" from {director}" if director else ""

    descriptor = rating["descriptor"]
    if descriptor == "moderate rating signal":
        headline = f"{sentence_case(subject)} with a moderate rating signal{director_clause}."
    elif descriptor:
        headline = f"{sentence_case(descriptor)} {subject}{director_clause}."
    else:
        headline = f"{sentence_case(subject)}{director_clause}."

    base_parts = []
    if year:
        base_parts.append(str(year))
    base_parts.append(subject)
    base = f"{article_for(' '.join(base_parts))} {' '.join(base_parts)}{director_clause}"

    support = []
    if rating["summary_phrase"]:
        support.append(rating["summary_phrase"])
    if availability:
        support.append(availability["summary_phrase"])

    summary = base
    if support:
        summary += f", supported by {' and '.join(support)}"
    summary += "."

    return headline, summary


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
    subject_parts = []
    if status_label:
        subject_parts.append(status_label)
    if genre_label:
        subject_parts.append(genre_label)
    subject_parts.append("series")
    subject = " ".join(subject_parts)
    creator_clause = f" from {creator}" if creator else ""

    descriptor = rating["descriptor"]
    if descriptor == "moderate rating signal":
        headline = f"{sentence_case(subject)} with a moderate rating signal{creator_clause}."
    elif descriptor:
        headline = f"{sentence_case(descriptor)} {subject}{creator_clause}."
    else:
        headline = f"{sentence_case(subject)}{creator_clause}."

    base = f"{article_for(subject)} {subject}"
    if released_seasons:
        base += f" with {released_seasons} released season{'s' if released_seasons != 1 else ''}"
    if creator:
        base += f" from {creator}"

    support = []
    if rating["summary_phrase"]:
        support.append(rating["summary_phrase"])
    if availability:
        support.append(availability["summary_phrase"])

    summary = base
    if support:
        summary += f", supported by {' and '.join(support)}"
    summary += "."

    return headline, summary


def build_best_for(content_type, genre_label, director, creator, runtime, series_status):
    best_for = []
    if genre_label:
        best_for.append(f"{title_case_phrase(genre_label)} viewers")

    if content_type == "series":
        status_label = format_status(series_status)
        if status_label == "ongoing":
            best_for.append("Ongoing series viewers")
        elif status_label == "completed":
            best_for.append("Completed series viewers")
        elif status_label == "upcoming":
            best_for.append("Upcoming series trackers")
        if creator:
            best_for.append(f"{creator} fans")
    else:
        if director:
            best_for.append(f"{director} fans")
        if runtime and runtime > 150:
            best_for.append("Long-form films")

    return unique_preserve_order(best_for)[:4]


def build_watch_note(content_type, genre_label, runtime, series_metadata):
    if content_type == "movie" and runtime and runtime > 150:
        subject = genre_label or "movie"
        return f"Best suited for viewers comfortable with a long {subject}."

    if content_type == "series" and series_metadata:
        status_label = format_status(series_metadata.get("series_status_normalized"))
        if series_metadata.get("next_episode_air_date"):
            return "Useful for viewers following an active series with a stored next episode date."
        if (
            series_metadata.get("has_announced_season")
            and series_metadata.get("next_season_number")
        ):
            return "Useful for viewers who want to know both released and announced season information."
        if status_label == "completed":
            return "Useful for viewers who prefer completed series."

    return None


def build_insight_summary(content_detail: dict) -> dict:
    content = content_detail.get("content") or {}
    genres = content_detail.get("genres") or []
    platforms = content_detail.get("platforms") or []
    ratings = content_detail.get("ratings") or {}
    series_metadata = content_detail.get("series_metadata") or None
    credits = content_detail.get("credits") or {}

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

    if has_overview or has_genres:
        add_generated_from(generated_from, "metadata")

    if rating["signal"]:
        add_signal(key_signals, "Rating", rating["signal"])
        add_generated_from(generated_from, "ratings")

    if availability:
        add_signal(key_signals, "Availability", availability["value"])
        add_generated_from(generated_from, "availability")

    if content.get("age_rating"):
        add_signal(key_signals, "Age rating", content["age_rating"])
        add_generated_from(generated_from, "certification")

    if content_type == "movie":
        if runtime and runtime > 150:
            add_signal(key_signals, "Runtime", "Long movie")
        add_signal(key_signals, "Director", director)
    else:
        if series_metadata:
            add_generated_from(generated_from, "series_metadata")
        status_label = format_status(
            (series_metadata or {}).get("series_status_normalized")
        )
        add_signal(
            key_signals,
            "Series status",
            title_case_phrase(status_label) if status_label else None,
        )
        released_seasons = (series_metadata or {}).get("released_seasons_count")
        if released_seasons is not None:
            add_signal(key_signals, "Released seasons", str(released_seasons))
        next_season_number = (series_metadata or {}).get("next_season_number")
        if next_season_number:
            next_season_value = f"Season {next_season_number}"
            next_season_date = format_date(
                (series_metadata or {}).get("next_season_air_date")
            )
            next_season_year = (series_metadata or {}).get("next_season_year")
            if next_season_date:
                next_season_value += f" · {next_season_date}"
            elif next_season_year:
                next_season_value += f" · {next_season_year}"
            add_signal(key_signals, "Next season", next_season_value)
        next_episode_date = format_date(
            (series_metadata or {}).get("next_episode_air_date")
        )
        add_signal(key_signals, "Next episode", next_episode_date)
        add_signal(key_signals, "Creator", creator)

    if has_credits:
        add_generated_from(generated_from, "credits")

    best_for = build_best_for(
        content_type,
        genre_label,
        director,
        creator,
        runtime,
        (series_metadata or {}).get("series_status_normalized"),
    )
    watch_note = build_watch_note(content_type, genre_label, runtime, series_metadata)
    confidence = compute_confidence(
        has_overview,
        has_genres,
        has_rating,
        has_availability,
        has_credits,
    )

    return {
        "headline": headline,
        "summary": summary,
        "best_for": best_for,
        "key_signals": key_signals,
        "watch_note": watch_note,
        "generated_from": generated_from,
        "confidence": confidence,
    }
