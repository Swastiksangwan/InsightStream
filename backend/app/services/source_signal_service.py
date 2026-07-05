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

BLOCKED_PUBLIC_DISPLAY_PHRASES = (
    "all themes",
    "complex story",
    "bleak mood complex story",
    "built around all themes",
    "built around heist story",
    "built around spy story",
    "built around eerie",
    "heavier watch assassin story",
    "warm corruption story",
    "keyword",
    "tmdb_keywords",
    "source_names",
    "mapping_version",
    "provider keyword",
    "source_signal",
    "source signal",
    "jiohotstar viewers",
    "netflix viewers",
    "prime video viewers",
    "serialized drama viewers",
    "platform viewers",
    "availability viewers",
)

DISPLAY_LABEL_NORMALIZATIONS = {
    "bleak mood": "Bleak",
    "dark mood": "Dark",
    "detective investigation": "Investigation",
    "high intensity": "High-stakes",
    "high stakes": "High-stakes",
    "sci fi": "Sci-fi",
    "science fiction": "Sci-fi",
}

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
    "all themes",
    "complex story",
    "dark story",
    "serious story",
    "story",
    "heavier watch",
}

WEAK_SECONDARY_CHIPS = {
    "assassin story",
    "corruption story",
    "crime story",
    "detective investigation",
    "freedom story",
    "heavier watch",
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
    "serious stories",
    "bleak mood complex story",
}

DISPLAY_FEEL_LABELS = {
    "atmospheric",
    "bleak",
    "cynical",
    "dark",
    "dark tone",
    "darkly funny",
    "emotional",
    "eerie",
    "foreboding",
    "gritty",
    "high-adrenaline",
    "high adrenaline",
    "high-stakes",
    "intense",
    "playful",
    "pressure-heavy",
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

DOMINANT_IDENTITY_LABELS = {
    "action-crime investigation",
    "action-crime investigation series",
    "animated superhero drama",
    "courtroom drama",
    "cyberpunk action sci-fi",
    "dark sci-fi anthology",
    "emotional space sci-fi",
    "hard-edged action series",
    "historical revenge epic",
    "kitchen workplace drama",
    "mythic superhero mystery",
    "nature documentary",
    "neo-noir crime thriller",
    "political dark fantasy",
    "prison drama",
    "psychological survival thriller",
    "satirical sci-fi anthology",
    "sci-fi heist",
    "serial-killer investigation",
    "space survival drama",
    "supernatural superhero adventure",
    "tech dystopia anthology",
}

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

IDENTITY_LIKE_THEME_LABELS = {
    "action story",
    "adventure story",
    "crime drama",
    "crime story",
    "drama",
    "fantasy adventure",
    "fantasy story",
    "heist story",
    "horror story",
    "investigation-led mystery",
    "serialized drama",
    "spy story",
    "superhero story",
}

WEAK_IDENTITY_LABELS = {
    "assassin story",
    "adventure story",
    "complex story",
    "corruption story",
    "crime story",
    "dark story",
    "drama",
    "fantasy story",
    "freedom story",
    "heavier watch",
    "horror story",
    "serious story",
    "story",
}

NON_THEME_LABELS = DISPLAY_FEEL_LABELS | {
    "1940s setting",
    "1950s setting",
    "1960s setting",
    "1970s setting",
    "1980s setting",
    "1990s setting",
    "2000s setting",
    "detective investigation",
    "offbeat comedy",
    "period setting",
}

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

DISPLAY_LABEL_RANKS = {
    "identity": {
        "prison drama": 1,
        "neo-noir crime thriller": 1,
        "serial-killer investigation": 1,
        "action-crime investigation": 1,
        "action-crime investigation series": 1,
        "hard-edged action series": 1,
        "satirical sci-fi anthology": 1,
        "dark sci-fi anthology": 1,
        "tech dystopia anthology": 1,
        "psychological survival thriller": 1,
        "mythic superhero mystery": 1,
        "supernatural superhero adventure": 1,
        "sci-fi heist": 1,
        "political dark fantasy": 1,
        "cyberpunk action sci-fi": 1,
        "kitchen workplace drama": 1,
        "courtroom drama": 1,
        "legal thriller": 1,
        "emotional space sci-fi": 1,
        "space survival drama": 1,
        "animated superhero drama": 1,
        "psychological thriller": 1,
        "nature documentary": 1,
        "crime story": 18,
        "heist story": 8,
        "assassin story": 25,
        "corruption story": 25,
        "freedom story": 25,
        "fantasy story": 20,
        "adventure story": 20,
        "drama": 30,
    },
    "theme": {
        "memory and identity": 1,
        "reality and control": 1,
        "technology and society": 1,
        "moral consequences": 1,
        "surveillance and control": 1,
        "identity conflict": 1,
        "mythology": 1,
        "serial-killer investigation": 1,
        "power struggle": 1,
        "family conflict": 2,
        "moral decline": 2,
        "survival": 2,
        "trauma": 2,
        "group collapse": 2,
        "past consequences": 2,
        "institutional corruption": 2,
        "hope": 2,
        "endurance": 2,
        "friendship": 2,
        "investigation": 2,
        "grief": 2,
        "ambition": 2,
        "rebellion": 2,
        "sacrifice": 2,
        "humanity's future": 2,
        "humanity’s future": 2,
        "dystopian future": 8,
        "1940s setting": 30,
    },
    "feel": {
        "surreal": 1,
        "foreboding": 1,
        "tense": 2,
        "pressure-heavy": 2,
        "thoughtful": 2,
        "atmospheric": 2,
        "high-adrenaline": 2,
        "warm": 2,
        "cynical": 3,
        "bleak": 3,
        "dark": 4,
        "dark tone": 4,
        "intense": 5,
        "high-stakes": 5,
    },
}

BEST_FOR_LABEL_REWRITES = {
    "action-crime investigation": "Crime investigations",
    "assassin story": None,
    "crime investigation": "Crime investigations",
    "crime investigations": "Crime investigations",
    "mythic superhero mystery": "Superhero mysteries",
    "offbeat comedy": "Offbeat comedies",
    "police investigation": "Crime investigations",
    "prison drama": "Prison dramas",
    "prison dramas": "Prison dramas",
    "psychological survival thriller": "Psychological thrillers",
    "psychological thriller": "Psychological thrillers",
    "satirical sci-fi": "Satirical sci-fi",
    "satirical sci-fi anthology": "Satirical sci-fi",
    "serial-killer investigation": "Crime investigations",
    "survival mystery": "Survival mysteries",
    "survival stories": "Survival stories",
    "superhero mystery": "Superhero mysteries",
}

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


def title_case_label(value):
    if not has_text(value):
        return value

    preserve_lower = {"and", "or", "of", "the", "a", "an", "to", "in"}
    words = []
    for index, word in enumerate(value.strip().split()):
        if index > 0 and word.lower() in preserve_lower:
            words.append(word.lower())
        else:
            words.append(word[:1].upper() + word[1:])
    return " ".join(words)


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


def contains_any(value, terms):
    text_value = value or ""
    return any(term in text_value for term in terms)


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

    if lower_value in DISPLAY_LABEL_NORMALIZATIONS:
        cleaned = DISPLAY_LABEL_NORMALIZATIONS[lower_value]
        lower_value = cleaned.lower()

    if lower_value in LABEL_REWRITES:
        return LABEL_REWRITES[lower_value]

    if any(term in lower_value for term in GENERIC_REJECT_TERMS):
        return None

    if any(phrase in lower_value for phrase in BLOCKED_PUBLIC_DISPLAY_PHRASES):
        return None

    if lower_value in WEAK_STANDALONE_LABELS:
        return None

    if lower_value.endswith(" viewers"):
        base = cleaned[: -len(" viewers")].strip()
        if not base or base.lower() in WEAK_STANDALONE_LABELS:
            return None
        return title_case_phrase(base)

    return cleaned


def blocked_public_display_phrases(value):
    if not has_text(value):
        return []
    lower_value = value.lower()
    return [
        phrase
        for phrase in BLOCKED_PUBLIC_DISPLAY_PHRASES
        if phrase in lower_value
    ]


def sanitize_public_display_text(value):
    if not has_text(value):
        return None
    cleaned = " ".join(value.strip().split())
    if blocked_public_display_phrases(cleaned):
        return None
    if any(term in cleaned.lower() for term in GENERIC_REJECT_TERMS):
        return None
    return cleaned


def display_has_blocked_public_phrase(display):
    return bool(blocked_public_display_phrases(str(display)))


def sanitize_labels(values, limit=None):
    labels = unique_preserve_order(
        value for value in (sanitize_label(item) for item in values or []) if value
    )
    return labels[:limit] if limit is not None else labels


def display_safe_label(value):
    label = sanitize_label(value)
    if not label:
        return None

    if is_weak_display_label(label):
        return None

    return label


def is_weak_display_label(value):
    if not has_text(value):
        return True
    lower_value = value.lower().strip()
    return lower_value in DISPLAY_WEAK_LABELS or bool(
        blocked_public_display_phrases(lower_value)
    )


def is_identity_like_label(value):
    if not has_text(value):
        return False
    lower_value = value.lower().strip()
    if lower_value in IDENTITY_LIKE_THEME_LABELS:
        return True
    if lower_value.endswith(" story") or lower_value.endswith(" stories"):
        return True
    return any(term in lower_value for term in DISPLAY_IDENTITY_LIKE_THEME_TERMS)


def is_theme_like_label(value):
    if not has_text(value) or is_weak_display_label(value):
        return False
    lower_value = value.lower().strip()
    if lower_value in NON_THEME_LABELS or lower_value.endswith(" setting"):
        return False
    return not is_identity_like_label(value)


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


def rank_display_labels(labels, group=None):
    ranked = unique_preserve_order(labels)
    if not group:
        return ranked
    ranks = DISPLAY_LABEL_RANKS.get(group or "", {})
    return sorted(
        ranked,
        key=lambda label: (
            ranks.get(label.lower(), 10),
            1 if label.lower() in WEAK_IDENTITY_LABELS else 0,
            label.lower(),
        ),
    )


def compact_display_labels(values, limit=None, group=None):
    output = []
    for value in values or []:
        label = display_safe_label(value)
        if not label:
            continue

        label_lower = label.lower()
        replaced = False
        skip = False
        similar_group = similar_display_group(label)

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
            if similar_group and existing_group and similar_group is existing_group:
                output[index] = more_specific_label(existing, label)
                replaced = True
                break

        if skip or replaced:
            continue

        output.append(label)

    output = rank_display_labels(output, group=group)
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
    cautions = build_display_cautions(watch_profile, signals, limit=2)
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


def content_context_text(display_context):
    content = (display_context or {}).get("content") or {}
    values = [
        content.get("title"),
        content.get("overview"),
        content.get("type"),
    ]
    return " ".join(value.lower() for value in values if has_text(value))


def has_scifi_context(display_context, all_label_text):
    genre_text = genre_context_text(display_context)
    return any(
        marker in f"{all_label_text} {genre_text} {content_context_text(display_context)}"
        for marker in ("sci-fi", "sci fi", "science fiction")
    )


def has_animation_context(display_context, all_label_text):
    genre_text = genre_context_text(display_context)
    return (
        "animation"
        in f"{all_label_text} {genre_text} {content_context_text(display_context)}"
    )


def has_genre_context(display_context, *markers):
    genre_text = genre_context_text(display_context)
    return any(marker in genre_text for marker in markers)


def combined_display_text(watch_profile, signals, labels=None, display_context=None):
    genre_text = genre_context_text(display_context)
    content_text = content_context_text(display_context)
    parts = [
        genre_text,
        content_text,
        watch_profile.get("watch_feel") or "",
        *(watch_profile.get("chips") or []),
        *(watch_profile.get("best_for") or []),
        *(labels or []),
        *(
            signal.get("label") or ""
            for signal in signals or []
            if has_text(signal.get("label"))
        ),
    ]
    return " ".join(part.lower() for part in parts if has_text(part))


def content_type_context(display_context):
    content = (display_context or {}).get("content") or {}
    return (content.get("type") or "").lower()


def is_weak_identity_label(value):
    if not has_text(value):
        return True
    lower_value = value.lower()
    return lower_value in WEAK_IDENTITY_LABELS or is_weak_display_label(value)


def infer_context_identity(watch_profile, signals, display_context=None):
    text_value = combined_display_text(
        watch_profile,
        signals,
        display_context=display_context,
    )

    has_scifi = has_scifi_context(display_context, text_value)
    has_fantasy = has_genre_context(display_context, "fantasy") or "fantasy" in text_value
    has_animation = has_animation_context(display_context, text_value)
    has_action = has_genre_context(display_context, "action") or "action" in text_value
    has_crime = has_genre_context(display_context, "crime") or "crime" in text_value
    has_history = has_genre_context(display_context, "history", "historical")
    has_documentary = has_genre_context(display_context, "documentary")
    has_mystery = (
        has_genre_context(display_context, "mystery") or "mystery" in text_value
    )
    has_thriller = has_genre_context(display_context, "thriller") or "thriller" in text_value
    has_horror = has_genre_context(display_context, "horror") or "horror" in text_value
    is_series = content_type_context(display_context) == "series"

    if contains_any(text_value, ("prison", "inmate", "warden")):
        return "Prison drama"

    if has_scifi and "heist" in text_value:
        return "Sci-fi heist"

    if has_scifi and "space" in text_value and any(
        term in text_value
        for term in ("survival", "family", "time", "humanity", "future")
    ):
        if "emotional" in text_value or "family" in text_value:
            return "Emotional space sci-fi"
        return "Space survival drama"

    if has_scifi and contains_any(
        text_value,
        ("anthology", "technology", "innovation", "society", "surveillance"),
    ):
        if contains_any(text_value, ("satire", "satirical", "darkly funny")):
            return "Satirical sci-fi anthology"
        if "anthology" in text_value:
            return "Dark sci-fi anthology"
        if contains_any(text_value, ("dystopia", "dystopian")) and contains_any(
            text_value,
            ("technology", "innovation", "society", "surveillance"),
        ):
            return "Tech dystopia anthology"

    if (
        has_crime
        and (has_thriller or has_mystery)
        and contains_any(
            text_value,
            ("serial killer", "serial-killer", "homicide", "detective", "murder", "sins"),
        )
    ):
        if contains_any(text_value, ("neo noir", "neo-noir", "detective", "sins")):
            return "Neo-noir crime thriller"
        return "Serial-killer investigation"

    if has_action and has_crime and contains_any(
        text_value,
        (
            "police",
            "military",
            "military police",
            "investigator",
            "ex-military",
            "drifter",
            "lone investigator",
            "corruption",
            "conspiracy",
        ),
    ):
        return (
            "Action-crime investigation series"
            if is_series
            else "Action-crime investigation"
        )

    if contains_any(text_value, ("psychological thriller", "psychological")) and (
        contains_any(
            text_value,
            ("survival", "trauma", "wilderness", "group collapse", "past consequences"),
        )
        or has_horror
        or has_mystery
    ):
        return "Psychological survival thriller"

    if (has_horror or has_mystery or has_thriller) and contains_any(
        text_value,
        ("survival", "plane crash", "wilderness", "trauma", "group collapse"),
    ):
        return "Psychological survival thriller"

    if "superhero" in text_value and contains_any(
        text_value,
        (
            "egypt",
            "egyptian",
            "gods",
            "myth",
            "mythology",
            "identity",
            "identities",
            "blackout",
        ),
    ):
        if has_mystery or contains_any(text_value, ("mystery", "identity", "blackout")):
            return "Mythic superhero mystery"
        return "Supernatural superhero adventure"

    if has_scifi and "cyberpunk" in text_value:
        return "Cyberpunk action sci-fi"
    if has_scifi and any(term in text_value for term in ("reality", "control")) and (
        "action" in text_value or "martial" in text_value
    ):
        return "Cyberpunk action sci-fi"
    if has_fantasy and any(
        term in text_value
        for term in ("political", "power struggle", "succession", "court intrigue")
    ):
        return "Political dark fantasy"
    if "kitchen" in text_value and "workplace" in text_value:
        return "Kitchen workplace drama"
    if any(term in text_value for term in ("courtroom", "legal")):
        if "thriller" in text_value:
            return "Legal thriller"
        return "Courtroom drama"
    if has_animation and "superhero" in text_value:
        return "Animated superhero drama"
    if has_documentary and any(
        term in text_value for term in ("nature", "wildlife", "planet")
    ):
        return "Nature documentary"
    if has_documentary:
        return "Documentary"

    if has_scifi:
        return (
            "Sci-fi drama"
            if has_genre_context(display_context, "drama")
            else "Sci-fi story"
        )
    if has_crime:
        return "Crime drama"
    if has_history:
        return "Historical drama"
    if has_animation and has_genre_context(display_context, "adventure"):
        return "Animated adventure"

    return None


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

    return compact_display_labels(enriched, limit=3, group="identity")


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


def identity_overlaps(left, right):
    if not has_text(left) or not has_text(right):
        return False
    left_lower = left.lower()
    right_lower = right.lower()
    return left_lower in right_lower or right_lower in left_lower


def merge_context_identity(identity, fallback_identity):
    if not fallback_identity:
        return identity

    current = identity or []
    current_lower = {label.lower() for label in current}
    fallback_lower = fallback_identity.lower()

    if fallback_lower in current_lower:
        return current

    if not current or all(is_weak_identity_label(label) for label in current):
        return [fallback_identity] + [
            label for label in current if not is_weak_identity_label(label)
        ]

    related_replacements = {
        "action-crime investigation": {
            "assassin story",
            "crime story",
            "police investigation",
        },
        "action-crime investigation series": {
            "assassin story",
            "crime story",
            "police investigation",
        },
        "dark sci-fi anthology": {"crime story", "dystopian future"},
        "mythic superhero mystery": {
            "comic-book adaptation",
            "superhero story",
            "superhero team story",
        },
        "neo-noir crime thriller": {
            "crime story",
            "detective investigation",
            "investigation-led mystery",
        },
        "prison drama": {
            "corruption story",
            "freedom story",
            "period drama",
        },
        "psychological survival thriller": {
            "horror story",
            "psychological thriller",
            "survival story",
        },
        "satirical sci-fi anthology": {"crime story", "dystopian future"},
        "sci-fi heist": {"heist story"},
        "serial-killer investigation": {
            "crime story",
            "detective investigation",
            "investigation-led mystery",
        },
        "tech dystopia anthology": {"crime story", "dystopian future"},
        "political dark fantasy": {
            "dark fantasy",
            "fantasy adventure",
            "fantasy story",
            "fantasy world",
            "political power drama",
        },
        "animated superhero drama": {"superhero story", "superhero team story"},
    }
    if fallback_lower in related_replacements:
        return [fallback_identity] + [
            label
            for label in current
            if label.lower() not in related_replacements[fallback_lower]
        ]

    if any(identity_overlaps(label, fallback_identity) for label in current):
        return [
            fallback_identity if identity_overlaps(label, fallback_identity) else label
            for label in current
        ]

    if fallback_lower in {
        "action-crime investigation",
        "action-crime investigation series",
        "dark sci-fi anthology",
        "mythic superhero mystery",
        "neo-noir crime thriller",
        "prison drama",
        "psychological survival thriller",
        "satirical sci-fi anthology",
        "sci-fi heist",
        "serial-killer investigation",
        "tech dystopia anthology",
        "political dark fantasy",
        "cyberpunk action sci-fi",
        "kitchen workplace drama",
        "emotional space sci-fi",
        "space survival drama",
    }:
        return [fallback_identity] + current

    return current


def is_identity_like_theme(label):
    return is_identity_like_label(label)


def prioritize_theme_labels(labels):
    compacted = compact_display_labels(labels, group="theme")
    core_themes = [
        label for label in compacted if is_theme_like_label(label)
    ]

    return compact_display_labels(core_themes, group="theme")


def primary_theme_labels(themes):
    prioritized = prioritize_theme_labels(themes)
    core_themes = [
        theme for theme in prioritized if is_theme_like_label(theme)
    ]
    return core_themes[:3]


def inferred_context_themes(watch_profile, signals, display_context=None):
    text_value = combined_display_text(
        watch_profile,
        signals,
        display_context=display_context,
    )
    themes = []

    if contains_any(text_value, ("technology", "innovation", "society")):
        themes.append("Technology and society")
    if contains_any(
        text_value,
        ("moral consequence", "moral consequences", "morality", "ethical", "ethics"),
    ):
        themes.append("Moral consequences")
    if contains_any(text_value, ("surveillance", "control", "controlled")):
        themes.append("Surveillance and control")

    if contains_any(text_value, ("serial killer", "serial-killer", "homicide", "sins")):
        themes.append("Serial-killer investigation")
    if contains_any(text_value, ("moral decay", "decay", "corruption")):
        themes.append(
            "Moral decay" if "moral" in text_value else "Institutional corruption"
        )
    if contains_any(
        text_value,
        ("justice", "detective", "investigation", "investigator"),
    ):
        themes.append("Investigation")

    if contains_any(text_value, ("prison", "inmate", "warden")):
        if "hope" in text_value:
            themes.append("Hope")
        if contains_any(text_value, ("endurance", "resilience", "years", "sentence")):
            themes.append("Endurance")
        if "friendship" in text_value or "friend" in text_value:
            themes.append("Friendship")
        if contains_any(text_value, ("corruption", "warden", "institution")):
            themes.append("Institutional corruption")

    if contains_any(text_value, ("survival", "survive", "wilderness", "plane crash")):
        themes.append("Survival")
    if "trauma" in text_value:
        themes.append("Trauma")
    if contains_any(text_value, ("group collapse", "group", "fracture", "fractures")):
        themes.append("Group collapse")
    if contains_any(text_value, ("past consequences", "past", "aftermath")):
        themes.append("Past consequences")

    if contains_any(text_value, ("military", "ex-military", "military police")):
        themes.append("Military background")
    if contains_any(text_value, ("lone investigator", "drifter", "investigator")):
        themes.append("Lone investigator")
    if "conspiracy" in text_value:
        themes.append("Conspiracy")

    if contains_any(text_value, ("egypt", "egyptian", "gods", "myth", "mythology")):
        themes.append("Mythology")
    if contains_any(
        text_value,
        ("identity conflict", "dual identity", "identities", "blackout"),
    ):
        themes.append("Identity conflict")

    return unique_preserve_order(themes)


def refine_theme_labels(themes, identity):
    refined = compact_display_labels(themes, group="theme")
    lower_themes = {theme.lower() for theme in refined}
    identity_text = " ".join(identity or []).lower()

    if "serial-killer investigation" in lower_themes:
        refined = [
            theme
            for theme in refined
            if theme.lower() not in {"investigation", "detective investigation"}
        ]

    if "investigation" in identity_text and len(refined) > 1:
        refined = [theme for theme in refined if theme.lower() != "investigation"]

    broader_tech_themes = {
        "technology and society",
        "moral consequences",
        "surveillance and control",
    }
    if lower_themes & broader_tech_themes and len(refined) > 1:
        refined = [theme for theme in refined if theme.lower() != "dystopian future"]

    if len(refined) > 3:
        refined = refined[:3]

    return refined


def singular_best_for_key(label):
    lower_label = label.lower()
    if lower_label.endswith("ies"):
        return f"{lower_label[:-3]}y"
    if lower_label.endswith("s"):
        return lower_label[:-1]
    return lower_label


def normalize_best_for_label(label):
    sanitized = sanitize_label(label)
    if not sanitized:
        return None

    lower_label = sanitized.lower()
    if lower_label in BEST_FOR_LABEL_REWRITES:
        return BEST_FOR_LABEL_REWRITES[lower_label]

    if lower_label.startswith("stories about "):
        return f"Stories about {lower_label[len('stories about '):]}"

    if lower_label in WEAK_IDENTITY_LABELS or lower_label in WEAK_SECONDARY_CHIPS:
        return None

    if lower_label.endswith(" story"):
        return f"{title_case_label(sanitized[:-len(' story')])} stories"
    if lower_label.endswith(" drama"):
        return f"{title_case_label(sanitized)}s"
    if lower_label.endswith(" thriller"):
        return f"{title_case_label(sanitized)}s"

    return title_case_label(sanitized)


def sentence_case_best_for_label(label):
    if not has_text(label):
        return label
    value = label.strip()
    words = value.split()
    if len(words) <= 1:
        return value
    preserved_terms = {"AI", "Sci-fi", "World", "War", "II"}
    normalized_words = [
        word if word in preserved_terms else word[:1].lower() + word[1:]
        for word in words[1:]
    ]
    return " ".join([words[0], *normalized_words])


def build_display_best_for(best_for, identity, themes, limit=2):
    candidates = []
    identity_text = " ".join(identity or []).lower()
    for value in list(best_for or []) + list(identity or []) + list(themes or []):
        normalized = normalize_best_for_label(value)
        if (
            normalized
            and normalized.lower() == "crime dramas"
            and "sci-fi anthology" in identity_text
        ):
            continue
        if normalized:
            candidates.append(normalized)

    output = []
    seen = set()
    for candidate in candidates:
        key = singular_best_for_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        output.append(candidate)

    return [
        sentence_case_best_for_label(label)
        for label in compact_display_labels(output, limit=limit)
    ]



def has_signal_label(signals, dimensions, terms):
    for signal in signals or []:
        if dimensions and signal.get("dimension") not in dimensions:
            continue
        label = (signal.get("label") or "").lower()
        value = (signal.get("value") or "").lower()
        if any(term in f"{label} {value}" for term in terms):
            return True
    return False


def generic_caution_text(value):
    lower_value = value.lower()
    return (
        "better suited for viewers comfortable with darker or more intense stories"
        in lower_value
        or "may feel complex" in lower_value
        or "more intense than casual viewing" in lower_value
    )


def specific_caution_candidates(watch_profile, signals):
    candidates = []
    pace_text = " ".join(
        [
            watch_profile.get("watch_feel") or "",
            *(watch_profile.get("chips") or []),
            *(watch_profile.get("best_for") or []),
        ]
    ).lower()

    if (
        has_signal_label(signals, {"pacing"}, {"plot-driven"})
        or "puzzle" in pace_text
        or "complex" in pace_text
    ):
        candidates.append("Dense structure may require attention.")

    if has_signal_label(signals, {"pacing"}, {"slow-burn", "slow burn"}):
        candidates.append("Slow-burn pacing may feel deliberate.")

    if has_signal_label(
        signals,
        {"mood", "tone", "intensity"},
        {"dark", "bleak", "foreboding", "intense", "high-stakes"},
    ):
        candidates.append("Darker tone may not suit casual viewing.")

    if has_signal_label(
        signals,
        {"content_caution_proxy"},
        {"violence", "mature", "adult", "frightening", "intense material"},
    ):
        candidates.append(
            "May be better suited for viewers comfortable with mature or intense material."
        )

    return unique_preserve_order(candidates)


def build_display_cautions(watch_profile, signals, limit=1):
    stored = sanitize_labels(watch_profile.get("consider_first") or [])
    specific = specific_caution_candidates(watch_profile, signals)

    if stored and not any(generic_caution_text(caution) for caution in stored):
        return compact_display_labels(stored, limit=limit)

    return compact_display_labels(specific or stored, limit=limit)


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


def refine_feel_labels(feel, watch_profile, signals, display_context=None):
    refined = compact_display_labels(feel, group="feel")
    lower_values = {label.lower() for label in refined}
    text_value = combined_display_text(
        watch_profile,
        signals,
        labels=refined,
        display_context=display_context,
    )

    if "warm" in lower_values and "cynical" in lower_values and not contains_any(
        text_value,
        ("satire", "satirical", "darkly funny", "dark comedy"),
    ):
        refined = [label for label in refined if label.lower() != "warm"]

    return refined[:2]


def build_display_profile(watch_profile, signals, display_context=None):
    chips = watch_profile.get("chips") or []
    best_for = watch_profile.get("best_for") or []
    consider_first = watch_profile.get("consider_first") or []

    audience_identity_labels = signal_labels_for_dimensions(
        signals,
        {"audience_expectation"},
    )
    topic_labels = (
        signal_labels_for_dimensions(signals, {"topic_theme"})
        + inferred_context_themes(
            watch_profile,
            signals,
            display_context=display_context,
        )
    )
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
        group="identity",
    )
    identity = enrich_identity_labels(
        identity_candidates,
        watch_profile,
        signals,
        display_context=display_context,
    )
    identity = merge_context_identity(
        identity,
        infer_context_identity(
            watch_profile,
            signals,
            display_context=display_context,
        ),
    )
    identity = compact_display_labels(identity, limit=3, group="identity")
    strong_identity = [
        label
        for label in identity
        if label.lower() not in WEAK_SECONDARY_CHIPS
        and not is_weak_identity_label(label)
    ]
    if strong_identity:
        identity = strong_identity[:3]

    topic_theme_candidates = refine_theme_labels(
        remove_profile_overlaps(
            prioritize_theme_labels(topic_labels),
            identity,
            limit=5,
        ),
        identity,
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
        themes = refine_theme_labels(themes, identity)

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
        group="feel",
    )
    feel = refine_feel_labels(
        feel_candidates,
        watch_profile,
        signals,
        display_context=display_context,
    )
    if identity and identity[0].lower() == "prison drama":
        feel = compact_display_labels(
            [
                "Serious",
                *(
                    label
                    for label in feel
                    if label.lower() not in {"warm", "cynical"}
                ),
            ],
            limit=2,
            group="feel",
        )

    return {
        "identity": identity[:3],
        "themes": themes[:3],
        "feel": feel[:2],
        "pace": build_display_pace(watch_profile, signals),
        "best_for": build_display_best_for(best_for, identity, themes, limit=2),
        "consider_first": build_display_cautions(watch_profile, signals, limit=1),
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

    if score is None or scoring_count < 2:
        return None

    if score >= 90:
        return "exceptional audience backing"
    if score >= 80:
        return "strong audience backing"
    if score >= 70:
        return "positive audience backing"

    return None


def theme_clause_for_identity(identity_phrase, themes):
    theme_text = join_short_list(themes[:3])
    if not theme_text:
        return None

    lower_identity = identity_phrase.lower()
    first_theme = themes[0].lower() if themes else ""

    if first_theme == "serial-killer investigation":
        return "built around a serial-killer investigation"

    if "kitchen workplace drama" in lower_identity:
        return f"shaped by {theme_text}"

    if any(
        marker in lower_identity
        for marker in (
            "anthology",
            "cyberpunk",
            "prison drama",
            "psychological survival thriller",
            "reality-bending",
        )
    ):
        return f"about {theme_text}"

    return f"built around {theme_text}"


def build_primary_insight(display_profile, watch_profile, display_context=None):
    identity = (display_profile.get("identity") or [None])[0]
    watch_feel = watch_profile.get("watch_feel")

    if not has_text(identity):
        simplified = simplify_watch_feel_for_headline(watch_feel)
        identity = sentence_case(simplified) if simplified else None

    if not has_text(identity):
        return None

    if is_weak_identity_label(identity):
        fallback_identity = infer_context_identity(
            watch_profile,
            [],
            display_context=display_context,
        )
        if fallback_identity:
            identity = fallback_identity

    identity_phrase = lower_first(identity)
    identity_starts_with_feel = any(
        identity_phrase.startswith(feel_label)
        for feel_label in DISPLAY_FEEL_LABELS
    )
    feel = next(
        (
            label
            for label in display_profile.get("feel") or []
            if has_text(label)
            and not identity_starts_with_feel
            and label.lower() not in identity_phrase.lower()
        ),
        None,
    )
    feel_prefix = f"{lower_first(feel)} " if feel else ""
    subject = f"{feel_prefix}{identity_phrase}".strip()
    sentence = f"{article_for(subject).capitalize()} {subject}"

    themes = primary_theme_labels(display_profile.get("themes") or [])
    if themes:
        clause = theme_clause_for_identity(identity_phrase, themes)
        if clause:
            sentence += f" {clause}"
    elif display_profile.get("pace"):
        sentence += f" with {lower_first(display_profile['pace'])} structure"
    elif feel:
        sentence += f" with a {lower_first(feel)} tone"

    audience_phrase = strong_audience_backing_phrase(display_context)
    if audience_phrase and len(sentence) <= 126:
        sentence += f", with {audience_phrase}"

    sentence = ensure_sentence(sentence)
    if len(sentence) > 180:
        sentence = ensure_sentence(sentence[:177].rsplit(" ", 1)[0])

    if sanitize_public_display_text(sentence):
        return sentence

    fallback = f"{article_for(identity_phrase).capitalize()} {identity_phrase}"
    if display_profile.get("pace"):
        fallback += f" with {lower_first(display_profile['pace'])} structure"
    elif feel:
        fallback += f" with a {lower_first(feel)} tone"
    return ensure_sentence(fallback) if sanitize_public_display_text(fallback) else None


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
