from sqlalchemy import text
from sqlalchemy.orm import Session


GENERIC_REJECT_TERMS = (
    "jiohotstar",
    "netflix",
    "prime video",
    "amazon prime video",
    "apple tv",
    "netflix viewers",
    "prime video viewers",
    "amazon prime video viewers",
    "streaming viewers",
    "platform viewers",
    "availability viewers",
    "ott viewers",
    "provider",
    "keyword",
    "tmdb_keywords",
    "source_names",
    "mapping_version",
    "confidence",
    "source_signal",
    "source signal",
    "frontend_ready",
    "storage_ready",
)

WEAK_STANDALONE_LABELS = {
    "content",
    "drama",
    "streaming",
    "ott",
    "jiohotstar",
    "netflix",
    "prime video",
    "amazon prime video",
    "serious stories",
}

WEAK_SECONDARY_CHIPS = {
    "spy story",
    "spy thriller",
    "spy thrillers",
    "serious tone",
    "complex",
    "bold",
}

MOOD_TONE_ONLY_CHIPS = {
    "tense",
    "emotional",
    "playful",
    "serious",
    "serious tone",
    "surreal",
    "thoughtful",
    "foreboding",
    "dark tone",
    "gritty",
}

DISPLAY_WEAK_LABELS = WEAK_STANDALONE_LABELS | {
    "story",
    "stories",
    "serious",
    "serious stories",
}

DISPLAY_FEEL_LABELS = {
    "bleak",
    "dark",
    "dark tone",
    "emotional",
    "foreboding",
    "gritty",
    "high-adrenaline",
    "high adrenaline",
    "intense",
    "playful",
    "serious",
    "surreal",
    "tense",
    "thoughtful",
    "warm",
}

DISPLAY_PACING_LABELS = {
    "action-heavy",
    "character-driven",
    "dialogue-heavy",
    "fast-paced",
    "plot-driven",
    "slow-burn",
}

DISPLAY_IDENTITY_KEYWORDS = (
    "action",
    "adventure",
    "comedy",
    "crime",
    "documentary",
    "drama",
    "fantasy",
    "heist",
    "horror",
    "mystery",
    "sci-fi",
    "sci fi",
    "story",
    "thriller",
    "western",
)

DISPLAY_IDENTITY_LIKE_THEME_TERMS = (
    "action",
    "adventure",
    "comedy",
    "crime",
    "documentary",
    "drama",
    "fantasy",
    "heist",
    "horror",
    "mystery",
    "sci-fi",
    "sci fi",
    "story",
    "thriller",
    "western",
)

SIMILAR_DISPLAY_GROUPS = (
    {
        "high-stakes",
        "high stakes",
        "high intensity",
        "intense",
        "pressure-heavy",
        "constant pressure",
    },
    {"dark", "dark tone", "bleak", "foreboding", "gritty"},
    {"fantasy adventure", "fantasy world", "magical world"},
    {"superhero story", "superhero team story"},
)

LABEL_REWRITES = {
    "fantasy story viewers": "Fantasy stories",
    "fantasy adventure viewers": "Fantasy adventures",
    "space opera viewers": "Space-opera stories",
    "crime drama viewers": "Crime dramas",
    "character-driven series viewers": "Character-driven series",
    "serialized drama viewers": "Long-form dramas",
    "superhero story viewers": "Superhero stories",
    "animation style viewers": "Animated stories",
    "ai themes viewers": "AI-driven sci-fi",
    "artificial intelligence viewers": "AI-driven sci-fi",
    "space sci-fi viewers": "Space sci-fi",
    "dystopian future viewers": "Dystopian sci-fi",
    "gangster crime story viewers": "Gangster crime dramas",
    "friendship story viewers": "Friendship-led stories",
    "fantasy world viewers": "Fantasy adventures",
    "political power drama viewers": "Political power dramas",
    "organized crime story viewers": "Organized-crime dramas",
    "comic-book adaptation viewers": "Comic-book-based stories",
    "revenge story viewers": "Revenge stories",
    "investigation-led mystery viewers": "Investigation-led mysteries",
    "murder mystery viewers": "Murder mysteries",
    "serial-killer investigation viewers": "Crime investigations",
    "spy story viewers": "Spy thrillers",
    "heist story viewers": "Heist stories",
    "creature threat viewers": "Creature thrillers",
    "war story viewers": "War dramas",
    "coming-of-age viewers": "Coming-of-age stories",
}

SIGNAL_DIMENSION_PRIORITY = {
    "audience_expectation": 1,
    "topic_theme": 2,
    "tone": 3,
    "mood": 4,
    "pacing": 5,
    "intensity": 6,
    "content_caution_proxy": 7,
}


def has_text(value):
    return isinstance(value, str) and bool(value.strip())


def title_case_phrase(value):
    if not has_text(value):
        return value
    words = value.strip().split()
    return " ".join(word[:1].upper() + word[1:] for word in words)


def sentence_case(value):
    if not has_text(value):
        return value
    stripped = value.strip()
    return stripped[:1].upper() + stripped[1:]


def lower_first(value):
    if not has_text(value):
        return value
    stripped = value.strip()
    return stripped[:1].lower() + stripped[1:]


def ensure_sentence(value):
    if not has_text(value):
        return value
    stripped = value.strip()
    return stripped if stripped.endswith(".") else f"{stripped}."


def article_for(value):
    if not has_text(value):
        return "a"
    return "an" if value.strip()[0].lower() in {"a", "e", "i", "o", "u"} else "a"


def unique_preserve_order(values):
    seen = set()
    output = []
    for value in values:
        if not has_text(value):
            continue
        cleaned = " ".join(value.strip().split())
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output


def json_list(value):
    if isinstance(value, list):
        return value
    return []


def json_dict(value):
    if isinstance(value, dict):
        return value
    return {}


def sanitize_label(value):
    if not has_text(value):
        return None

    cleaned = " ".join(value.strip().split())
    lower_value = cleaned.lower()

    if lower_value in LABEL_REWRITES:
        return LABEL_REWRITES[lower_value]

    if any(term in lower_value for term in GENERIC_REJECT_TERMS):
        return None

    if lower_value in WEAK_STANDALONE_LABELS:
        return None

    if lower_value.endswith(" viewers"):
        base = cleaned[: -len(" viewers")].strip()
        if not base or base.lower() in WEAK_STANDALONE_LABELS:
            return None
        return title_case_phrase(base)

    return cleaned


def sanitize_labels(values, limit=None):
    labels = unique_preserve_order(
        value for value in (sanitize_label(item) for item in values or []) if value
    )
    return labels[:limit] if limit is not None else labels


def display_safe_label(value):
    label = sanitize_label(value)
    if not label:
        return None

    if label.lower() in DISPLAY_WEAK_LABELS:
        return None

    return label


def similar_display_group(label):
    lower_label = label.lower()
    for group in SIMILAR_DISPLAY_GROUPS:
        if lower_label in group:
            return group
    return None


def more_specific_label(left, right):
    left_lower = left.lower()
    right_lower = right.lower()

    if left_lower in right_lower and left_lower != right_lower:
        return right
    if right_lower in left_lower and left_lower != right_lower:
        return left

    return left if len(left) >= len(right) else right


def compact_display_labels(values, limit=None):
    output = []
    for value in values or []:
        label = display_safe_label(value)
        if not label:
            continue

        label_lower = label.lower()
        replaced = False
        skip = False
        group = similar_display_group(label)

        for index, existing in enumerate(output):
            existing_lower = existing.lower()
            if existing_lower == label_lower:
                skip = True
                break

            if label_lower in existing_lower or existing_lower in label_lower:
                output[index] = more_specific_label(existing, label)
                replaced = True
                break

            existing_group = similar_display_group(existing)
            if group and existing_group and group is existing_group:
                output[index] = more_specific_label(existing, label)
                replaced = True
                break

        if skip or replaced:
            continue

        output.append(label)

    return output[:limit] if limit is not None else output


def signal_priority(signal):
    return SIGNAL_DIMENSION_PRIORITY.get(signal.get("dimension"), 99)


def prioritized_signal_labels(signals):
    ordered = sorted(
        signals,
        key=lambda signal: (
            signal_priority(signal),
            signal.get("label", "").lower(),
        ),
    )
    return unique_preserve_order(
        label
        for label in (sanitize_label(signal.get("label")) for signal in ordered)
        if label
    )


def prioritize_chips(stored_chips, signals, limit=5):
    primary_signal_labels = prioritized_signal_labels(
        signal
        for signal in signals
        if signal.get("dimension") in {"audience_expectation", "topic_theme"}
    )
    feel_signal_labels = prioritized_signal_labels(
        signal
        for signal in signals
        if signal.get("dimension") in {"tone", "mood"}
    )
    pacing_signal_labels = prioritized_signal_labels(
        signal for signal in signals if signal.get("dimension") == "pacing"
    )
    stored_labels = sanitize_labels(stored_chips)

    candidates = unique_preserve_order(
        primary_signal_labels + feel_signal_labels + pacing_signal_labels + stored_labels
    )
    strong_candidates = [
        label
        for label in candidates
        if label.lower() not in WEAK_SECONDARY_CHIPS
    ]
    if len(strong_candidates) >= 3:
        candidates = strong_candidates

    primary_count = sum(
        1
        for label in candidates
        if label in primary_signal_labels and label.lower() not in WEAK_SECONDARY_CHIPS
    )
    if primary_count >= 2:
        candidates = [
            label
            for label in candidates
            if label.lower() not in WEAK_SECONDARY_CHIPS or label not in primary_signal_labels
        ]

    return candidates[:limit]


def public_signal_rows(rows):
    signals = []
    for row in rows:
        signals.append(
            {
                "dimension": row["dimension"],
                "value": row["value"],
                "label": row["label"],
                "confidence": row["confidence"],
            }
        )
    return signals


def fetch_watch_guidance(db: Session, content_id: int):
    query = text("""
        SELECT
            content_id,
            watch_feel,
            chips,
            best_for,
            consider_first,
            keyword_counts,
            signal_sources,
            curated_override_applied,
            metadata_fallback_applied,
            storage_ready,
            frontend_ready,
            quality_summary
        FROM content_watch_guidance
        WHERE content_id = :content_id;
    """)
    row = db.execute(query, {"content_id": content_id}).mappings().first()
    return dict(row) if row else None


def fetch_active_source_signals(db: Session, content_id: int):
    query = text("""
        SELECT
            dimension,
            value,
            label,
            confidence
        FROM content_source_signals
        WHERE content_id = :content_id
          AND is_active = TRUE
        ORDER BY
            CASE dimension
                WHEN 'audience_expectation' THEN 1
                WHEN 'topic_theme' THEN 2
                WHEN 'tone' THEN 3
                WHEN 'mood' THEN 4
                WHEN 'pacing' THEN 5
                WHEN 'intensity' THEN 6
                WHEN 'content_caution_proxy' THEN 7
                ELSE 8
            END,
            label ASC;
    """)
    rows = db.execute(query, {"content_id": content_id}).mappings().all()
    return [dict(row) for row in rows]


def simplify_watch_feel_for_headline(watch_feel):
    if not has_text(watch_feel):
        return None

    phrase = watch_feel.strip().rstrip(".")
    lower_phrase = phrase.lower()
    for article in ("a ", "an "):
        if lower_phrase.startswith(article):
            phrase = phrase[len(article):]
            lower_phrase = phrase.lower()
            break

    for marker in (" built around ", " about ", " with "):
        if marker in lower_phrase:
            marker_index = lower_phrase.index(marker)
            if marker_index >= 12:
                phrase = phrase[:marker_index].strip()
                break

    return phrase[:1].lower() + phrase[1:] if phrase else None


def values_by_dimension(signals):
    grouped = {}
    for signal in signals:
        grouped.setdefault(signal["dimension"], []).append(signal["label"])
    return grouped


def first_signal_label(grouped, dimensions):
    for dimension in dimensions:
        for label in grouped.get(dimension) or []:
            sanitized = sanitize_label(label)
            if sanitized:
                return sanitized
    return None


def theme_phrase(label):
    if not has_text(label):
        return None
    lower_label = label.lower()
    if "memory and identity" in lower_label:
        return "memory-and-identity themes"
    if "sci-fi" in lower_label or "sci fi" in lower_label:
        return lower_first(label)
    if lower_label.endswith("story") or lower_label.endswith("stories"):
        return lower_first(label)
    return lower_first(label)


def feel_phrase(label):
    if not has_text(label):
        return None
    lower_label = label.lower()
    if lower_label in {"surreal", "thoughtful", "foreboding", "tense", "gritty"}:
        return f"{lower_label} tone"
    if lower_label.endswith("tone"):
        return lower_label
    return lower_first(label)


def pacing_reason(pacing, identity, watch_feel):
    if not has_text(pacing):
        return None
    lower_pacing = pacing.lower()
    lower_watch_feel = (watch_feel or "").lower()

    if "plot-driven" in lower_pacing and (
        "memory" in lower_watch_feel
        or "identity" in lower_watch_feel
        or "puzzle" in lower_watch_feel
        or "heist" in (identity or "").lower()
    ):
        return "Plot-driven structure makes it better for viewers who enjoy puzzle-like stories."

    if "fast" in lower_pacing:
        return "Fast-paced structure points toward a higher-energy watch."

    if "slow" in lower_pacing:
        return "Slower pacing makes it better for a more focused watch."

    return f"{sentence_case(pacing)} structure helps set the viewing rhythm."


def build_decision_headline(watch_profile):
    identity = simplify_watch_feel_for_headline(watch_profile.get("watch_feel"))
    if identity:
        return f"Best suited for viewers looking for {article_for(identity)} {identity}."

    best_for = watch_profile.get("best_for") or []
    if best_for:
        return f"Best suited for {lower_first(best_for[0])}."

    chips = watch_profile.get("chips") or []
    if chips:
        return f"Best suited for {lower_first(chips[0])}."

    return None


def build_decision_reasons(watch_profile, signals):
    reasons = []
    chips = watch_profile.get("chips") or []
    best_for = watch_profile.get("best_for") or []
    grouped = values_by_dimension(signals)

    identity = first_signal_label(grouped, ("audience_expectation", "topic_theme"))
    if not identity:
        identity = next(
            (
                chip
                for chip in chips
                if chip.lower() not in MOOD_TONE_ONLY_CHIPS
                and chip.lower() not in WEAK_SECONDARY_CHIPS
            ),
            None,
        )

    theme = first_signal_label(grouped, ("topic_theme",))
    if theme and identity and theme.lower() == identity.lower():
        theme = None

    if identity and theme:
        reasons.append(
            f"Strong {lower_first(identity)} identity with {theme_phrase(theme)}."
        )
    elif identity:
        reasons.append(f"Strong {lower_first(identity)} identity.")

    feel = first_signal_label(grouped, ("mood", "tone"))
    if feel:
        feel_text = feel_phrase(feel)
        if theme:
            reasons.append(
                f"{sentence_case(feel_text)} gives it a distinctive watch feel."
            )
        else:
            reasons.append(f"{sentence_case(feel_text)} shapes the watch feel.")

    pacing = first_signal_label(grouped, ("pacing",))
    pacing_text = pacing_reason(
        pacing,
        identity,
        watch_profile.get("watch_feel"),
    )
    if pacing_text:
        reasons.append(pacing_text)

    if best_for and len(reasons) < 2:
        reasons.append(f"Works best for {lower_first(best_for[0])}.")

    if len(reasons) < 2:
        secondary_chip = next(
            (
                chip
                for chip in chips
                if chip != identity
                and chip.lower() not in MOOD_TONE_ONLY_CHIPS
                and chip.lower() not in WEAK_SECONDARY_CHIPS
            ),
            None,
        )
        if secondary_chip:
            reasons.append(
                f"Secondary signals point toward {lower_first(secondary_chip)}."
            )

    if len(reasons) < 2 and has_text(watch_profile.get("watch_feel")):
        reasons.append("The watch feel is specific enough for a clearer watch decision.")

    return unique_preserve_order(reasons)[:4]


def build_decision_cautions(watch_profile, signals):
    cautions = sanitize_labels(watch_profile.get("consider_first") or [], limit=2)
    if cautions:
        return cautions

    high_intensity = any(
        signal["dimension"] == "intensity"
        and signal["label"].strip().lower() in {"high", "high intensity", "intense"}
        for signal in signals
    )
    if high_intensity:
        return ["May feel heavier or more intense than casual viewing."]

    return []


def build_watch_profile(guidance, signals=None):
    if not guidance:
        return {
            "watch_feel": None,
            "chips": [],
            "best_for": [],
            "consider_first": [],
        }

    public_signals = signals or []
    return {
        "watch_feel": (
            guidance["watch_feel"] if has_text(guidance["watch_feel"]) else None
        ),
        "chips": prioritize_chips(
            json_list(guidance.get("chips")),
            public_signals,
            limit=5,
        ),
        "best_for": sanitize_labels(json_list(guidance.get("best_for")), limit=4),
        "consider_first": sanitize_labels(
            json_list(guidance.get("consider_first")),
            limit=2,
        ),
    }


def signal_labels_for_dimensions(signals, dimensions):
    return [
        signal.get("label")
        for signal in sorted(signals, key=signal_priority)
        if signal.get("dimension") in dimensions
    ]


def genre_context_text(display_context):
    genres = (display_context or {}).get("genres") or []
    return " ".join(
        genre.lower()
        for genre in genres
        if has_text(genre)
    )


def has_scifi_context(display_context, all_label_text):
    genre_text = genre_context_text(display_context)
    return any(
        marker in f"{all_label_text} {genre_text}"
        for marker in ("sci-fi", "sci fi", "science fiction")
    )


def has_animation_context(display_context, all_label_text):
    genre_text = genre_context_text(display_context)
    return "animation" in f"{all_label_text} {genre_text}"


def enrich_identity_labels(labels, watch_profile, signals, display_context=None):
    watch_feel = (watch_profile.get("watch_feel") or "").lower()
    all_label_text = " ".join(
        [watch_feel]
        + [label.lower() for label in labels or [] if has_text(label)]
        + [
            (signal.get("label") or "").lower()
            for signal in signals or []
            if has_text(signal.get("label"))
        ]
    )

    enriched = []
    for label in labels:
        lower_label = label.lower()
        if lower_label == "heist story" and has_scifi_context(
            display_context,
            all_label_text,
        ):
            enriched.append("Sci-fi heist")
            continue
        if lower_label in {"fantasy adventure", "fantasy world"} and (
            "political power drama" in all_label_text
            or "power struggle" in all_label_text
            or "dark fantasy" in all_label_text
        ):
            enriched.append("Political dark fantasy")
            continue
        if lower_label == "dark fantasy" and (
            "political" in all_label_text
            or "power struggle" in all_label_text
            or "succession" in all_label_text
        ):
            enriched.append("Political dark fantasy")
            continue
        if lower_label == "superhero story" and has_animation_context(
            display_context,
            all_label_text,
        ):
            enriched.append("Animated superhero drama")
            continue
        enriched.append(label)

    if "Sci-fi heist" in enriched:
        enriched = [label for label in enriched if label.lower() != "heist story"]
    if "Political dark fantasy" in enriched:
        enriched = [
            label
            for label in enriched
            if label.lower() not in {"fantasy adventure", "fantasy world", "dark fantasy"}
        ]

    return compact_display_labels(enriched, limit=3)


def remove_profile_overlaps(values, blocked_values, limit=None):
    blocked = {value.lower() for value in blocked_values or [] if has_text(value)}
    filtered = []
    for value in values or []:
        lower_value = value.lower()
        if lower_value in blocked:
            continue
        if any(
            lower_value in blocked_value or blocked_value in lower_value
            for blocked_value in blocked
        ):
            continue
        filtered.append(value)
    return compact_display_labels(filtered, limit=limit)


def is_identity_like_theme(label):
    if not has_text(label):
        return False
    lower_label = label.lower()
    return any(term in lower_label for term in DISPLAY_IDENTITY_LIKE_THEME_TERMS)


def prioritize_theme_labels(labels):
    compacted = compact_display_labels(labels)
    core_themes = [
        label for label in compacted if not is_identity_like_theme(label)
    ]

    if not core_themes:
        return compacted

    return compact_display_labels(core_themes)


def primary_theme_labels(themes):
    prioritized = prioritize_theme_labels(themes)
    core_themes = [
        theme for theme in prioritized if not is_identity_like_theme(theme)
    ]
    return (core_themes or prioritized)[:2]


def build_display_pace(watch_profile, signals):
    pacing_labels = compact_display_labels(
        signal_labels_for_dimensions(signals, {"pacing"})
        + [
            chip
            for chip in watch_profile.get("chips") or []
            if has_text(chip) and chip.lower() in DISPLAY_PACING_LABELS
        ],
        limit=2,
    )

    if not pacing_labels:
        return None

    primary = pacing_labels[0]
    lower_primary = primary.lower()
    watch_text = " ".join(
        [watch_profile.get("watch_feel") or ""]
        + (watch_profile.get("chips") or [])
        + (watch_profile.get("best_for") or [])
    ).lower()

    if "plot-driven" in lower_primary:
        if any(
            term in watch_text
            for term in ("puzzle", "heist", "memory", "identity")
        ):
            return "Plot-driven and puzzle-like"
        return "Plot-driven"
    if "slow" in lower_primary:
        if any(term in watch_text for term in ("investigation", "mystery", "courtroom")):
            return "Slow-burn and investigative"
        return "Slow-burn"
    if "fast" in lower_primary or "action-heavy" in lower_primary:
        return "Fast-paced and action-led"
    if "character-driven" in lower_primary:
        return "Character-driven"
    if "dialogue" in lower_primary:
        return "Dialogue-driven"

    return primary


def build_display_profile(watch_profile, signals, display_context=None):
    chips = watch_profile.get("chips") or []
    best_for = watch_profile.get("best_for") or []
    consider_first = watch_profile.get("consider_first") or []

    audience_identity_labels = signal_labels_for_dimensions(
        signals,
        {"audience_expectation"},
    )
    topic_labels = signal_labels_for_dimensions(signals, {"topic_theme"})
    topic_identity_labels = [
        label
        for label in topic_labels
        if has_text(label)
        and any(keyword in label.lower() for keyword in DISPLAY_IDENTITY_KEYWORDS)
    ]
    identity_candidates = compact_display_labels(
        audience_identity_labels
        + topic_identity_labels
        + [
            chip
            for chip in chips
            if has_text(chip)
            and any(
                keyword in chip.lower()
                for keyword in DISPLAY_IDENTITY_KEYWORDS
            )
            and chip.lower() not in DISPLAY_FEEL_LABELS
            and chip.lower() not in DISPLAY_PACING_LABELS
            and chip.lower() not in WEAK_SECONDARY_CHIPS
        ],
        limit=5,
    )
    identity = enrich_identity_labels(
        identity_candidates,
        watch_profile,
        signals,
        display_context=display_context,
    )
    strong_identity = [
        label
        for label in identity
        if label.lower() not in WEAK_SECONDARY_CHIPS
    ]
    if strong_identity:
        identity = strong_identity[:3]

    topic_theme_candidates = remove_profile_overlaps(
        prioritize_theme_labels(topic_labels),
        identity,
        limit=4,
    )
    if topic_theme_candidates:
        themes = topic_theme_candidates
    else:
        chip_theme_candidates = [
            chip
            for chip in chips
            if has_text(chip)
            and chip.lower() not in DISPLAY_FEEL_LABELS
            and chip.lower() not in DISPLAY_PACING_LABELS
            and chip.lower() not in WEAK_SECONDARY_CHIPS
        ]
        themes = remove_profile_overlaps(
            prioritize_theme_labels(chip_theme_candidates),
            identity,
            limit=3,
        )

    feel_candidates = compact_display_labels(
        signal_labels_for_dimensions(signals, {"mood"})
        + signal_labels_for_dimensions(signals, {"tone"})
        + signal_labels_for_dimensions(signals, {"intensity"})
        + [
            chip
            for chip in chips
            if has_text(chip) and chip.lower() in DISPLAY_FEEL_LABELS
        ],
        limit=5,
    )
    feel = compact_display_labels(feel_candidates, limit=2)

    return {
        "identity": identity[:3],
        "themes": themes[:3],
        "feel": feel[:2],
        "pace": build_display_pace(watch_profile, signals),
        "best_for": compact_display_labels(best_for, limit=2),
        "consider_first": compact_display_labels(consider_first, limit=2),
    }


def join_short_list(values):
    cleaned = [
        lower_first(value)
        for value in values or []
        if has_text(value)
    ]
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0]
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def strong_audience_backing_phrase(display_context):
    ratings = (display_context or {}).get("ratings") or {}
    score = ratings.get("unified_score")
    scoring_count = ratings.get("scoring_source_count") or 0

    if score is not None and score >= 75 and scoring_count >= 2:
        return "strong audience backing"

    return None


def build_primary_insight(display_profile, watch_profile, display_context=None):
    identity = (display_profile.get("identity") or [None])[0]
    watch_feel = watch_profile.get("watch_feel")

    if not has_text(identity):
        simplified = simplify_watch_feel_for_headline(watch_feel)
        identity = sentence_case(simplified) if simplified else None

    if not has_text(identity):
        return None

    identity_phrase = lower_first(identity)
    feel = next(
        (
            label
            for label in display_profile.get("feel") or []
            if has_text(label) and label.lower() not in identity_phrase.lower()
        ),
        None,
    )
    feel_prefix = f"{lower_first(feel)} " if feel else ""
    subject = f"{feel_prefix}{identity_phrase}".strip()
    sentence = f"{article_for(subject).capitalize()} {subject}"

    themes = primary_theme_labels(display_profile.get("themes") or [])
    if themes:
        sentence += f" built around {join_short_list(themes[:2])}"
    elif display_profile.get("pace"):
        sentence += f" with {lower_first(display_profile['pace'])} structure"

    audience_phrase = strong_audience_backing_phrase(display_context)
    if audience_phrase and len(sentence) <= 126:
        sentence += f", with {audience_phrase}"

    sentence = ensure_sentence(sentence)
    if len(sentence) > 180:
        sentence = ensure_sentence(sentence[:177].rsplit(" ", 1)[0])

    return sentence


def format_scoring_source_count(count):
    return f"{count} scoring source{'s' if count != 1 else ''}"


def build_audience_fact(display_context):
    ratings = (display_context or {}).get("ratings") or {}
    score = ratings.get("unified_score")
    if score is None:
        return None

    scoring_count = ratings.get("scoring_source_count") or 0
    if scoring_count > 0:
        return {
            "label": "Audience",
            "value": f"{score}/100 from {format_scoring_source_count(scoring_count)}",
        }

    return {"label": "Audience", "value": f"{score}/100"}


def availability_kind(platforms):
    platform_types = {
        (platform.get("availability_type") or "").lower()
        for platform in platforms or []
        if isinstance(platform, dict)
    }
    if "streaming" in platform_types or "stream" in platform_types:
        return "Streaming"
    if "rent" in platform_types and "buy" in platform_types:
        return "Rent/buy"
    if "rent" in platform_types:
        return "Rent"
    if "buy" in platform_types:
        return "Buy"
    if "free" in platform_types or "ads" in platform_types:
        return "Free/ad-supported"
    return "Availability"


def availability_region(platforms):
    regions = unique_preserve_order(
        platform.get("region_code")
        for platform in platforms or []
        if isinstance(platform, dict) and has_text(platform.get("region_code"))
    )
    if "IN" in regions:
        return "India"
    if len(regions) == 1:
        return regions[0]
    return None


def build_access_fact(display_context):
    platforms = (display_context or {}).get("platforms") or []
    if not platforms:
        return None

    kind = availability_kind(platforms)
    region = availability_region(platforms)
    return {
        "label": "Access",
        "value": f"{kind} in {region}" if region else kind,
    }


def first_credit_name(credits, group_name):
    for credit in (credits or {}).get(group_name) or []:
        if isinstance(credit, dict) and has_text(credit.get("name")):
            return credit["name"].strip()
    return None


def build_creative_fact(display_context):
    content = (display_context or {}).get("content") or {}
    credits = (display_context or {}).get("credits") or {}
    content_type = content.get("type")

    if content_type == "series":
        creator = first_credit_name(credits, "creators")
        if creator:
            return {"label": "Creative lead", "value": f"Created by {creator}"}

    director = first_credit_name(credits, "directors")
    if director:
        return {"label": "Creative lead", "value": f"Directed by {director}"}

    return None


def build_age_rating_fact(display_context):
    content = (display_context or {}).get("content") or {}
    age_rating = content.get("age_rating")
    if has_text(age_rating):
        return {"label": "Age rating", "value": age_rating.strip()}
    return None


def build_series_status_fact(display_context):
    series_metadata = (display_context or {}).get("series_metadata") or {}
    status = series_metadata.get("series_status_normalized") or series_metadata.get(
        "series_status"
    )
    if not has_text(status):
        return None

    status_label = title_case_phrase(status.replace("_", " "))
    season_count = series_metadata.get("number_of_seasons")
    if season_count:
        return {
            "label": "Series status",
            "value": (
                f"{status_label} · {season_count} "
                f"season{'s' if season_count != 1 else ''}"
            ),
        }

    return {"label": "Series status", "value": status_label}


def build_runtime_fact(display_context):
    content = (display_context or {}).get("content") or {}
    runtime = content.get("runtime")
    if not runtime:
        return None
    if content.get("type") == "movie" and runtime >= 150:
        return {"label": "Runtime", "value": f"{runtime} min"}
    return None


def build_supporting_facts(display_context):
    candidates = [
        build_audience_fact(display_context),
        build_access_fact(display_context),
        build_creative_fact(display_context),
        build_age_rating_fact(display_context),
        build_series_status_fact(display_context),
        build_runtime_fact(display_context),
    ]

    facts = []
    seen_labels = set()
    for fact in candidates:
        if not fact:
            continue
        label = sanitize_label(fact.get("label"))
        value = sanitize_label(fact.get("value"))
        if not label or not value:
            continue
        label_key = label.lower()
        if label_key in seen_labels:
            continue
        seen_labels.add(label_key)
        facts.append({"label": label, "value": value})

    return facts[:4]


def build_decision_display(watch_profile, signals, display_context=None):
    profile = build_display_profile(
        watch_profile,
        signals,
        display_context=display_context,
    )
    return {
        "primary_insight": build_primary_insight(
            profile,
            watch_profile,
            display_context,
        ),
        "profile": profile,
        "supporting_facts": build_supporting_facts(display_context),
    }


def get_content_decision_layer(
    db: Session,
    content_id: int,
    include_debug: bool = False,
    display_context: dict = None,
):
    guidance = fetch_watch_guidance(db, content_id)
    signal_rows = fetch_active_source_signals(db, content_id)

    if not guidance and not signal_rows:
        return None

    public_signals = public_signal_rows(signal_rows)
    watch_profile = build_watch_profile(guidance, public_signals)
    decision_support = {
        "headline": build_decision_headline(watch_profile),
        "reasons": build_decision_reasons(watch_profile, public_signals),
        "cautions": build_decision_cautions(watch_profile, public_signals),
    }
    display = build_decision_display(
        watch_profile,
        public_signals,
        display_context=display_context,
    )
    signal_quality = {
        "storage_ready": bool(guidance.get("storage_ready")) if guidance else False,
        "frontend_ready": bool(guidance.get("frontend_ready")) if guidance else False,
        "has_watch_guidance": guidance is not None,
        "has_source_signals": bool(signal_rows),
    }
    decision_layer = {
        "watch_profile": watch_profile,
        "decision_support": decision_support,
        "display": display,
        "signal_quality": signal_quality,
    }

    if include_debug:
        decision_layer["debug"] = {
            "signals": public_signals,
            "keyword_counts": (
                json_dict(guidance.get("keyword_counts")) if guidance else {}
            ),
            "signal_sources": (
                json_list(guidance.get("signal_sources")) if guidance else []
            ),
        }

    return decision_layer
