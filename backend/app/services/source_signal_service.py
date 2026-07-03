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


def get_content_decision_layer(
    db: Session,
    content_id: int,
    include_debug: bool = False,
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
    signal_quality = {
        "storage_ready": bool(guidance.get("storage_ready")) if guidance else False,
        "frontend_ready": bool(guidance.get("frontend_ready")) if guidance else False,
        "has_watch_guidance": guidance is not None,
        "has_source_signals": bool(signal_rows),
    }
    decision_layer = {
        "watch_profile": watch_profile,
        "decision_support": decision_support,
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
