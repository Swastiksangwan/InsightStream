"""Pure deterministic planning and rendering for Decision Insight Formatter v2.

This module intentionally has no database or provider dependencies. Callers pass
already-loaded signals, including internal safety provenance, and content context.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


DECISION_INSIGHT_FORMATTER_VERSION = "2.0.2"
# Compatibility alias for older internal imports and serialized fixtures.
INSIGHT_FORMATTER_VERSION = DECISION_INSIGHT_FORMATTER_VERSION

INSIGHT_CONCEPT_ALIASES = {
    "romance": {
        "romance",
        "romantic connection",
        "romantic drama",
        "relationship story",
        "love story",
        "music-driven romantic drama",
    },
    "family": {
        "family bonds",
        "family conflict",
        "family drama",
        "family-focused story",
        "family relationship",
        "family relationships",
        "found family",
    },
    "class": {
        "class differences",
        "class divide",
        "class tension",
        "social class",
    },
    "coming_of_age": {"coming-of-age", "coming-of-age story"},
    "workplace": {
        "kitchen workplace drama",
        "medical workplace",
        "workplace comedy",
        "workplace drama",
        "workplace story",
    },
    "emotion": {"emotional", "emotional character drama"},
    "live_music": {
        "concert film",
        "live music",
        "live music performance",
        "music performance",
    },
    "investigation": {
        "crime mystery",
        "detective investigation",
        "federal investigation",
        "investigation",
        "investigation-led",
        "investigation-led mystery",
        "amateur investigation",
        "action-crime investigation",
        "action-crime investigation series",
        "medical investigation",
        "murder investigation",
        "police investigation",
        "serial-killer investigation",
    },
    "survival": {
        "desert survival",
        "human resilience",
        "island survival",
        "struggle for survival",
        "survival",
        "survival drama",
        "survival story",
        "psychological survival thriller",
        "space survival drama",
        "zombie survival",
    },
    "war_identity": {
        "war",
        "war documentary",
        "war drama",
        "war story",
        "world war ii drama",
    },
    "history_identity": {
        "historical documentary",
        "history",
        "history documentary",
        "period setting",
    },
    "human_cost": {"human cost", "human cost of war"},
    "military_mission": {"military mission"},
    "war_setting": {"world war ii setting"},
    "crime": {
        "crime drama",
        "crime story",
        "crime thriller",
        "crime world",
        "historical crime drama",
        "neo-noir crime",
        "true crime",
    },
    "supernatural_identity": {
        "folk horror mystery",
        "supernatural horror",
        "supernatural story",
    },
    "afterlife": {"afterlife story"},
    "revenge": {"revenge", "revenge story", "revenge western"},
    "power": {
        "ambition and power",
        "court politics",
        "family power struggle",
        "political pressure",
        "political power drama",
        "political survival",
        "power struggle",
        "royal power drama",
    },
    "legal": {
        "courtroom drama",
        "legal conflict",
        "legal drama",
        "legal thriller",
    },
    "technology_society": {"technology and society"},
    "future_context": {"dystopian future", "future society"},
    "post apocalyptic": {
        "post-apocalyptic survival drama",
        "post-apocalyptic world",
    },
    "music": {
        "music",
        "music documentary",
        "music-driven story",
        "music-driven romantic drama",
        "musical",
    },
    "nature": {"nature", "nature documentary"},
    "body": {"body horror", "body transformation"},
    "creature": {
        "creature disaster",
        "creature suspense",
        "creature threat",
        "creature thriller",
    },
    "conspiracy": {"conspiracy", "conspiracy thriller"},
    "superhero": {
        "superhero",
        "animated superhero drama",
        "mythic superhero mystery",
        "superhero crime thriller",
        "superhero story",
        "superhero team story",
        "supernatural superhero adventure",
    },
}

INSIGHT_ABOUT_PHRASES = {
    "addiction": "addiction",
    "alien encounter": "an alien encounter",
    "ambition and power": "ambition and power",
    "ambition and rivalry": "ambition and rivalry",
    "animation style": "animation style",
    "anime style": "anime style",
    "artistic ambition": "artistic ambition",
    "body transformation": "body transformation",
    "character pressure": "character pressure",
    "class differences": "differences in class and status",
    "class divide": "differences in class and status",
    "class tension": "differences in class and status",
    "cold war": "Cold War pressure",
    "coming-of-age": "coming-of-age",
    "conspiracy": "conspiracy",
    "conservation": "conservation",
    "corporate corruption": "institutional corruption",
    "corruption story": "institutional corruption",
    "creature suspense": "creature suspense",
    "creature threat": "an escalating creature threat",
    "desert survival": "survival in a hostile environment",
    "dreamlike reality": "dreamlike reality",
    "duty": "duty and responsibility",
    "dystopian future": "a dystopian future",
    "economic pressure": "economic pressure",
    "enslavement": "enslavement",
    "fairy-tale world": "a fairy-tale world",
    "family conflict": "family conflict",
    "family relationship": "family relationships",
    "family relationships": "family relationships",
    "found family": "found family",
    "federal investigation": "a federal investigation",
    "fellowship": "fellowship",
    "friendship": "friendship",
    "friendship story": "friendship",
    "future society": "a future society",
    "grief and healing": "grief and healing",
    "heroic teamwork": "heroic teamwork",
    "historical power struggle": "a struggle for political power",
    "honor": "honor",
    "hope": "hope",
    "human cost": "the human cost",
    "identity": "identity",
    "identity and self-image": "identity and self-image",
    "identity conflict": "identity conflict",
    "investigation": "an investigation",
    "investigation-led": "the pressure of an investigation",
    "detective investigation": "an investigation",
    "legacy sequel": "an established legacy",
    "legal conflict": "legal conflict",
    "live music performance": "live performance",
    "loneliness": "loneliness",
    "magical world": "a magical world",
    "manipulation": "control and manipulation",
    "medical workplace": "workplace pressure in a hospital",
    "memory and identity": "memory and identity",
    "mental health": "mental health",
    "moral pressure": "moral pressure",
    "moral responsibility": "moral responsibility",
    "mythology": "mythology",
    "obsession": "obsession",
    "police investigation": "a police investigation",
    "political conflict": "political conflict",
    "political pressure": "the pressures of public duty",
    "political survival": "survival within public life",
    "post-apocalyptic world": "a post-apocalyptic world",
    "psychological pressure": "mounting personal pressure",
    "power struggle": "struggles for power",
    "racial injustice": "racial injustice",
    "racial inequality": "racial inequality",
    "rebellion": "rebellion",
    "reincarnation": "reincarnation",
    "rescue mission": "a rescue mission",
    "revenge story": "revenge",
    "road-trip story": "a life-changing journey",
    "robotics": "robotics",
    "romance": "romance",
    "scientific ambition": "scientific ambition",
    "self-aware": "self-awareness",
    "social critique": "social critique",
    "space conflict": "conflict in space",
    "superhuman powers": "superhuman powers",
    "supernatural story": "supernatural forces",
    "survival": "survival",
    "survival story": "survival under pressure",
    "technology and society": "technology and society",
    "time-travel story": "time travel",
    "undercover operation": "an undercover operation",
    "unlikely companionship": "an unlikely bond",
    "war": "war",
    "war story": "the human cost of war",
    "workplace story": "workplace pressure",
}

INSIGHT_ADJECTIVES = {
    "atmospheric": "atmospheric",
    "bleak": "bleak",
    "bold": "bold",
    "cynical": "cynical",
    "dark": "dark",
    "dark tone": "dark",
    "darkly funny": "darkly funny",
    "eerie": "eerie",
    "emotional": "emotional",
    "energetic": "energetic",
    "foreboding": "foreboding",
    "gentle": "gentle",
    "gritty": "gritty",
    "harsh": "harsh",
    "high stakes": "high-stakes",
    "high-stakes": "high-stakes",
    "intimate": "intimate",
    "light": "light",
    "melancholy": "melancholic",
    "playful": "playful",
    "relaxed": "relaxed",
    "serious": "serious",
    "serious tone": "serious",
    "sobering": "sobering",
    "stylish": "stylish",
    "surreal": "surreal",
    "suspenseful": "suspenseful",
    "tense": "tense",
    "thoughtful": "thoughtful",
    "warm": "warm",
}

RAW_TAXONOMY_DIFFERENTIATORS = {
    "animation style",
    "anime style",
}

IDENTITY_TRUST_TIER_LABELS = {
    1: "curated_override_identity",
    2: "high_confidence_audience_identity",
    3: "governed_metadata_or_explicit_identity",
    4: "medium_confidence_identity_signal",
    5: "explicit_inferred_identity",
    6: "identity_like_topic_theme",
    7: "generic_metadata_fallback",
}

GOVERNED_GENRE_IDENTITIES = {
    "animated adventure",
    "body horror satire",
    "concert film",
    "dark fantasy",
    "historical crime drama",
    "historical drama",
    "historical music drama",
    "horror comedy",
    "music driven horror",
    "music documentary",
    "nature documentary",
    "political dark fantasy",
    "romantic drama",
    "war documentary",
    "war drama",
}

INSIGHT_GENERIC_IDENTITIES = {
    "comedy",
    "crime",
    "crime story",
    "comedy drama",
    "comedy/drama",
    "documentary",
    "drama",
    "music-driven story",
    "story",
}

DOMINANT_IDENTITY_LABELS = {
    "action-crime investigation",
    "action-crime investigation series",
    "afterlife story",
    "animated superhero drama",
    "courtroom drama",
    "cyberpunk action sci-fi",
    "dark sci-fi anthology",
    "emotional space sci-fi",
    "hard-edged action series",
    "historical crime drama",
    "historical revenge epic",
    "kitchen workplace drama",
    "mythic superhero mystery",
    "nature documentary",
    "neo-noir crime",
    "neo-noir crime thriller",
    "political dark fantasy",
    "political-action mystery",
    "post-apocalyptic survival drama",
    "prison drama",
    "psychological survival thriller",
    "satirical sci-fi anthology",
    "sci-fi heist",
    "sci-fi mystery",
    "serial-killer investigation",
    "space survival drama",
    "supernatural superhero adventure",
    "tech dystopia anthology",
    "war drama",
}

# These mappings live in topic_theme for taxonomy compatibility, but their
# governed copy role names a kind of story rather than merely a subject.
IDENTITY_BEARING_TOPIC_LABELS = {
    "afterlife story",
}

IDENTITY_NOUNS = {
    "adventure",
    "anthology",
    "caper",
    "comedy",
    "documentary",
    "drama",
    "epic",
    "fantasy",
    "film",
    "horror",
    "mystery",
    "opera",
    "procedural",
    "romance",
    "satire",
    "series",
    "story",
    "thriller",
    "western",
}

WEAK_IDENTITY_LABELS = {
    "assassin story",
    "corruption story",
    "crime story",
    "freedom story",
    "spy story",
    "supernatural story",
}

RELIABLE_CONTEXT_IDENTITIES = {
    "action-crime investigation",
    "action-crime investigation series",
    "cyberpunk action sci-fi",
    "dark sci-fi anthology",
    "emotional space sci-fi",
    "historical crime drama",
    "kitchen workplace drama",
    "mythic superhero mystery",
    "neo-noir crime",
    "neo-noir crime thriller",
    "political dark fantasy",
    "prison drama",
    "psychological survival thriller",
    "satirical sci-fi anthology",
    "sci-fi heist",
    "sci-fi mystery",
    "serial-killer investigation",
    "spy story",
    "space survival drama",
    "supernatural superhero adventure",
    "tech dystopia anthology",
}

# Lexical variants are governed as families so compatibility and inference use
# the same deterministic evidence contract.
EVIDENCE_FAMILIES = {
    "cartel": (
        "cartel",
        "cartels",
        "drug cartel",
        "drug cartels",
    ),
    "serial_killer": (
        "serial killer",
        "serial killers",
        "serial-killer",
        "serial-killers",
    ),
    "spy": (
        "spy",
        "spies",
        "undercover spy",
        "undercover spies",
        "secret agent",
        "secret agents",
        "intelligence agent",
        "intelligence agents",
        "intelligence service",
        "intelligence services",
        "intelligence officer",
        "intelligence officers",
        "intelligence operative",
        "intelligence operatives",
        "soviet agent",
        "soviet agents",
        "sleeper agent",
        "sleeper agents",
        "posing as",
        "living undercover",
        "espionage",
        "kgb",
        "mi5",
        "mi6",
    ),
}

GOVERNED_IDENTITY_COPY_ROLES = {
    "aviation action",
    "martial arts action",
}

# Preserve only governed acronym and proper-name forms. This registry is applied
# at the final display-realization boundary rather than repeated in templates.
GOVERNED_DISPLAY_CASING = (
    ("world war ii", "World War II"),
    ("wwii", "WWII"),
    ("mi5", "MI5"),
    ("mi6", "MI6"),
    ("fbi", "FBI"),
    ("cia", "CIA"),
    ("kgb", "KGB"),
    ("ai", "AI"),
)

IDENTITY_EVIDENCE_LABEL_FAMILIES = (
    ("mythic_scifi", ("mythic sci fi", "mythic sci-fi")),
    ("space_scifi", ("space sci fi", "space sci-fi", "space opera")),
    ("superhero", ("superhero",)),
    ("organized_crime", ("organized crime", "cartel")),
    ("investigation", ("investigation", "investigative", "detective")),
    ("creature", ("creature", "kaiju")),
    ("fantasy", ("fantasy",)),
    ("heist", ("heist", "caper")),
    ("action", ("action", "martial arts")),
    ("spy", ("spy", "espionage")),
    ("war", ("war drama", "war story", "world war")),
)

IDENTITY_SIGNAL_CORROBORATION = {
    "mythic_scifi": ("destiny", "mythology", "mythic", "prophecy"),
    "space_scifi": ("space", "space opera", "space sci fi"),
    "superhero": ("superhero", "superhuman powers", "heroic teamwork"),
    "organized_crime": ("organized crime", "cartel", "crime world"),
    "investigation": ("investigation", "detective", "federal investigation"),
    "creature": ("creature", "kaiju", "monster"),
    "fantasy": ("dark fantasy", "fairy tale", "magical world", "mythic fantasy"),
    "heist": ("heist", "caper", "robbery"),
    "action": ("action", "martial arts"),
    "spy": ("spy", "espionage", "intelligence work", "undercover operation"),
    "war": ("war", "world war"),
}

IDENTITY_GENRE_CORROBORATION = {
    "mythic_scifi": {"sci fi", "science fiction"},
    "space_scifi": {"sci fi", "science fiction"},
    "superhero": {"action", "adventure", "animation"},
    "organized_crime": {"crime"},
    "investigation": {"crime", "mystery", "thriller"},
    "creature": {"horror", "sci fi", "science fiction"},
    "fantasy": {"fantasy"},
    "heist": {"action", "comedy", "crime"},
    "action": {"action"},
    "spy": {"action", "crime", "drama", "thriller", "war", "war politics"},
    "war": {"war", "war politics"},
}

INCIDENTAL_IDENTITY_FAMILIES = {
    "creature",
    "investigation",
    "organized_crime",
    "space_scifi",
    "war",
}

INCIDENTAL_DIFFERENTIATOR_FAMILIES = {
    "creature",
    "investigation",
    "organized_crime",
    "prison",
    "war_identity",
}

INSIGHT_CONTEXT_RULES = (
    {
        "rule": "explicit_racial_inequality",
        "required": (),
        "any": ("racial inequality",),
        "phrase": "racial inequality",
        "family": "racial injustice",
        "evidence_scope": "equivalent",
    },
    {
        "rule": "studio_workplace",
        "required": ("studio",),
        "any": ("film", "movie", "creative", "executive"),
        "phrase": "pressure inside a film studio",
        "family": "creative_industry",
        "evidence_scope": "narrower",
    },
    {
        "rule": "matchmaking",
        "required": (),
        "any": ("matchmaker", "matchmaking"),
        "phrase": "modern matchmaking",
        "family": "matchmaking",
        "evidence_scope": "equivalent",
    },
    {
        "rule": "family_estrangement",
        "required": (),
        "any": ("estranged", "family rift", "fractured family"),
        "phrase": "strained family bonds",
        "family": "family",
        "evidence_scope": "narrower",
    },
    {
        "rule": "live_performance",
        "required": (),
        "any": ("concert", "live performance", "on stage", "stage performance"),
        "phrase": "live performance",
        "family": "live_music",
        "evidence_scope": "equivalent",
    },
    {
        "rule": "concert_staging",
        "required": ("concert film",),
        "any": ("creative choreography", "cinematic performance"),
        "phrase": "cinematic staging and choreography",
        "family": "performance_staging",
        "evidence_scope": "narrower",
    },
    {
        "rule": "artistic_ambition",
        "required": (),
        "any": (
            "aspiring actor",
            "aspiring actress",
            "aspiring artist",
            "aspiring filmmaker",
            "aspiring musician",
            "dreams of becoming an accomplished musician",
            "creative ambitions",
        ),
        "phrase": "artistic ambition",
        "family": "artistic_ambition",
        "evidence_scope": "equivalent",
    },
    {
        "rule": "investigation",
        "required": (),
        "any": (
            "investigates",
            "investigation",
            "investigator",
            "detective",
            "fbi",
            "homicide detectives",
            "police investigator",
        ),
        "phrase": "an investigation",
        "family": "investigation",
        "evidence_scope": "narrower",
    },
    {
        "rule": "military_mission",
        "required": (),
        "any": (
            "military mission",
            "soldiers are tasked",
            "men are tasked",
            "tasked with",
        ),
        "phrase": "a military mission",
        "family": "military_mission",
        "genres": ("war",),
        "evidence_scope": "narrower",
    },
    {
        "rule": "war_experience",
        "required": (),
        "any": ("war", "battle", "occupation", "soldier", "troops", "marines"),
        "phrase": "the human experience of conflict",
        "family": "human_cost",
        "genres": ("war",),
        "evidence_scope": "narrower",
    },
    {
        "rule": "survival",
        "required": (),
        "any": (
            "stranded",
            "tries to survive",
            "fight to survive",
            "struggle to survive",
            "group of survivors",
        ),
        "phrase": "survival under pressure",
        "family": "survival",
        "evidence_scope": "narrower",
    },
    {
        "rule": "outbreak",
        "required": (),
        "any": ("strange plague", "spreading plague", "deadly outbreak"),
        "phrase": "a spreading outbreak",
        "family": "outbreak",
        "evidence_scope": "narrower",
    },
    {
        "rule": "rescue_mission",
        "required": (),
        "any": ("sets off to rescue", "tasked with bringing", "rescue mission"),
        "phrase": "a rescue mission",
        "family": "rescue mission",
        "evidence_scope": "equivalent",
    },
    {
        "rule": "multigenerational_migration",
        "required": ("family",),
        "any": ("immigrant", "homeland", "across four generations"),
        "phrase": "migration across generations",
        "family": "migration",
        "evidence_scope": "narrower",
    },
)

DIMENSION_ORDER = {
    "audience_expectation": 0,
    "topic_theme": 1,
    "tone": 2,
    "mood": 3,
    "pacing": 4,
    "intensity": 5,
    "content_caution_proxy": 6,
}
CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class InsightComponent:
    text: str
    role: str
    concept_family: str
    source: str
    evidence: str
    supported: bool = True
    confidence: str | None = None
    trust_tier: int | None = None
    selection_rationale: str | None = None
    corroboration_sources: tuple[str, ...] = ()
    corroboration_count: int = 0
    centrality_class: str | None = None
    explicit_premise_evidence: bool = False
    incidental_context: bool = False


@dataclass(frozen=True)
class IdentityCandidate:
    label: str
    trust_tier: int
    confidence: str | None
    source: str
    evidence: str
    position: int
    corroboration_sources: tuple[str, ...] = ()
    corroboration_count: int = 0
    centrality_class: str = "uncorroborated"
    explicit_premise_evidence: bool = False
    incidental_context: bool = False
    ranking_rationale: str | None = None


@dataclass
class InsightPlan:
    primary_identity: InsightComponent | None = None
    tone_modifier: InsightComponent | None = None
    mood_modifier: InsightComponent | None = None
    primary_differentiator: InsightComponent | None = None
    secondary_differentiator: InsightComponent | None = None
    pacing_modifier: InsightComponent | None = None
    audience_modifier: InsightComponent | None = None
    template_family: str = "identity_about"
    rejected_candidates: list[dict[str, Any]] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    curated_override_applied: bool = False
    curated_identity_available: bool = False
    curated_identity_evaluation: str = "not_applicable"
    formatter_version: str = INSIGHT_FORMATTER_VERSION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def insight_normalized(value: Any) -> str:
    if not has_text(value):
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def normalize_display_phrase(value: Any) -> str | None:
    if not has_text(value):
        return None
    normalized = " ".join(value.strip().split())
    normalized = re.sub(
        r"\b(serious|dark|gritty)\s+tone\b",
        r"\1",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\b(bleak|warm)\s+mood\b",
        r"\1",
        normalized,
        flags=re.IGNORECASE,
    )
    return realize_display_casing(normalized)


def realize_display_casing(value: str) -> str:
    """Restore governed token casing without title-casing arbitrary prose."""

    output = value
    for source, replacement in GOVERNED_DISPLAY_CASING:
        output = re.sub(
            rf"(?<![A-Za-z0-9]){re.escape(source)}(?![A-Za-z0-9])",
            replacement,
            output,
            flags=re.IGNORECASE,
        )
    return output


def lower_first(value: str) -> str:
    lowered = value[:1].lower() + value[1:] if value else value
    return realize_display_casing(lowered)


def sentence_case(value: str) -> str:
    return value[:1].upper() + value[1:] if value else value


def ensure_sentence(value: str | None) -> str | None:
    if not has_text(value):
        return value
    value = realize_display_casing(value.strip())
    return value if value.endswith((".", "!", "?")) else f"{value}."


def article_for(value: str) -> str:
    normalized = insight_normalized(value)
    return "an" if normalized[:1] in {"a", "e", "i", "o", "u"} else "a"


def unique_preserve_order(values: list[Any]) -> list[Any]:
    seen = set()
    output = []
    for value in values:
        key = insight_normalized(value)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def insight_concept_family(value: Any) -> str:
    normalized = insight_normalized(value)
    adjective_tokens = {
        insight_normalized(adjective) for adjective in INSIGHT_ADJECTIVES.values()
    } | {"hard edged", "pressure cooker", "quiet", "restrained", "self aware"}
    for family, aliases in INSIGHT_CONCEPT_ALIASES.items():
        normalized_aliases = {insight_normalized(alias) for alias in aliases}
        if normalized in normalized_aliases or any(
            normalized.endswith(f" {alias}")
            and normalized[: -(len(alias) + 1)] in adjective_tokens
            for alias in normalized_aliases
        ):
            return family
    return normalized


def signal_priority(signal: dict[str, Any]) -> tuple[Any, ...]:
    return (
        DIMENSION_ORDER.get(signal.get("dimension"), 99),
        CONFIDENCE_ORDER.get(insight_normalized(signal.get("confidence")), 99),
        insight_normalized(signal.get("label")),
        insight_normalized(signal.get("value")),
    )


def safe_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        signal
        for signal in signals or []
        if signal.get("spoiler_safe") is not False and has_text(signal.get("label"))
    ]


def signal_labels_for_dimensions(
    signals: list[dict[str, Any]], dimensions: set[str]
) -> list[str]:
    return [
        signal["label"]
        for signal in sorted(safe_signals(signals), key=signal_priority)
        if signal.get("dimension") in dimensions
    ]


def insight_signal_match(
    label: str,
    signals: list[dict[str, Any]],
    dimensions: set[str] | None = None,
) -> dict[str, Any] | None:
    normalized = insight_normalized(label)
    family = insight_concept_family(label)
    candidates = [
        signal
        for signal in safe_signals(signals)
        if not dimensions or signal.get("dimension") in dimensions
    ]
    for signal in candidates:
        if insight_normalized(signal.get("label")) == normalized:
            return signal
    if dimensions and dimensions <= {"tone", "mood"}:
        normalized_role = re.sub(r"\s+(tone|mood)$", "", normalized)
        for signal in candidates:
            signal_role = re.sub(
                r"\s+(tone|mood)$",
                "",
                insight_normalized(signal.get("label")),
            )
            if signal_role == normalized_role:
                return signal
    for signal in candidates:
        if insight_concept_family(signal.get("label")) == family:
            return signal
    return None


def identity_has_copy_role(label: str) -> bool:
    normalized = insight_normalized(label)
    dominant = {insight_normalized(value) for value in DOMINANT_IDENTITY_LABELS}
    return bool(
        normalized
        and (
            normalized in dominant
            or normalized in GOVERNED_IDENTITY_COPY_ROLES
            or normalized in INSIGHT_GENERIC_IDENTITIES
            or normalized.split()[-1] in IDENTITY_NOUNS
            or normalized.endswith((" sci fi", " sci-fi", " heist"))
        )
    )


def identity_score(
    label: str,
    position: int,
    signals: list[dict[str, Any]],
) -> int:
    normalized = insight_normalized(label)
    dominant = {insight_normalized(value) for value in DOMINANT_IDENTITY_LABELS}
    if not identity_has_copy_role(label):
        return -100
    score = max(0, 12 - position)
    if normalized in INSIGHT_GENERIC_IDENTITIES or normalized in WEAK_IDENTITY_LABELS:
        score -= 18
    signal = insight_signal_match(label, signals)
    reliable_context = {
        insight_normalized(value) for value in RELIABLE_CONTEXT_IDENTITIES
    }
    if normalized in dominant and (signal or normalized in reliable_context):
        score += 18
    score += min(len(normalized.split()), 4) * 3
    if any(
        marker in normalized
        for marker in (
            "afterlife",
            "crime",
            "horror",
            "thriller",
            "western",
            "sci fi",
            "fantasy",
            "investigation",
            "workplace",
            "historical",
            "romance",
            "romantic",
            "concert",
            "musical",
            "documentary",
            "gangster",
        )
    ):
        score += 8
    if signal:
        score += {"high": 6, "medium": 3, "low": 1}.get(
            insight_normalized(signal.get("confidence")), 0
        )
        if signal.get("dimension") == "audience_expectation":
            score += 2
    return score


def signal_source_names(signal: dict[str, Any] | None) -> set[str]:
    if not signal:
        return set()
    values = signal.get("source_names") or signal.get("sources") or []
    return {
        insight_normalized(value)
        for value in values
        if has_text(value)
    }


def rejected_source_signal_concept_families(plan: InsightPlan) -> set[str]:
    """Return concepts rejected from source-signal identity candidates."""

    return {
        insight_concept_family(item.get("candidate"))
        for item in plan.rejected_candidates
        if item.get("reason") == "identity_metadata_conflict"
        and str(item.get("source") or "").startswith("source_signal:")
        and has_text(item.get("candidate"))
    }


def text_uses_concept_family(value: Any, family: str) -> bool:
    normalized = insight_normalized(value)
    if not normalized or not family:
        return False
    aliases = INSIGHT_CONCEPT_ALIASES.get(family) or {family.replace("_", " ")}
    return any(
        phrase_present(normalized, alias)
        or phrase_present(normalized, f"{insight_normalized(alias)}s")
        for alias in aliases
        if insight_normalized(alias)
    )


def signal_uses_rejected_concept(
    signal: dict[str, Any], rejected_families: set[str]
) -> bool:
    return bool(
        rejected_families
        and insight_concept_family(signal.get("label") or signal.get("value"))
        in rejected_families
    )


def identity_compatibility(
    candidate: IdentityCandidate,
    signals: list[dict[str, Any]],
    display_context: dict[str, Any],
) -> tuple[bool, str, str]:
    """Validate identity meaning against metadata and independent evidence."""

    normalized = insight_normalized(candidate.label)
    genres = {
        insight_normalized(genre)
        for genre in (display_context or {}).get("genres") or []
        if has_text(genre)
    }
    overview = insight_normalized(
        ((display_context or {}).get("content") or {}).get("overview")
    )
    independent_labels = " ".join(
        insight_normalized(signal.get("label") or signal.get("value"))
        for signal in signals
        if insight_normalized(signal.get("label")) != normalized
    )
    evidence_text = f"{overview} {independent_labels}".strip()

    def has_genre(*values: str) -> bool:
        return any(insight_normalized(value) in genres for value in values)

    def has_evidence(*phrases: str) -> bool:
        return any(phrase_present(evidence_text, phrase) for phrase in phrases)

    metadata_available = bool(genres or overview)

    if has_genre("documentary"):
        documentary_compatible = (
            "documentary" in normalized
            or normalized in {"concert film"}
        )
        if not documentary_compatible:
            return False, "documentary_rejects_fictional_identity", "genre:Documentary"

    if "romantic drama" in normalized or normalized in {"romance", "romantic comedy"}:
        if not (
            has_genre("romance")
            or has_evidence(
                "romantic relationship",
                "love story",
                "romance",
                "romantic connection",
            )
        ):
            return False, "missing_central_romance_evidence", "requires Romance genre or explicit romance premise"

    if "superhero" in normalized:
        if not has_evidence("superhero", "super hero", "comic-book roots", "comic book"):
            return False, "missing_superhero_evidence", "requires independent superhero or comic-book evidence"
        if has_genre("history", "music") and not has_genre("action", "animation", "fantasy", "sci-fi"):
            return False, "superhero_conflicts_with_metadata", "historical/music metadata"

    if "cyberpunk" in normalized and not has_evidence("cyberpunk"):
        return False, "missing_explicit_cyberpunk_evidence", "requires explicit cyberpunk evidence"

    if "anthology" in normalized and not has_evidence("anthology"):
        return False, "missing_explicit_anthology_evidence", "requires explicit anthology structure"

    if "cartel" in normalized and not (
        evidence_family_matches(overview, "cartel")
        or any(
            phrase_present(overview, phrase)
            for phrase in ("organized crime", "drug trafficking", "drug trade")
        )
    ):
        return False, "missing_cartel_or_organized_crime_evidence", "requires explicit cartel or organized-crime premise"

    if normalized in {"spy story", "spy thriller"}:
        compatible_genre = has_genre(
            "drama",
            "thriller",
            "crime",
            "action",
            "war & politics",
            "war",
        )
        if not compatible_genre or not evidence_family_matches(overview, "spy"):
            return False, "missing_central_spy_evidence", "requires an explicit spy/agent premise and compatible genre metadata"

    if normalized == "aviation action":
        governed_source = candidate.source.startswith(
            ("curated_override:", "source_signal:")
        )
        if not governed_source or not has_genre("action"):
            return False, "missing_aviation_action_evidence", "requires a curated/source identity and Action metadata"

    if normalized == "dark fantasy":
        explicit_dark_fantasy = candidate.source.startswith(
            (
                "source_signal:audience_expectation",
                "source_signal:topic_theme",
                "curated_override:",
            )
        ) or phrase_present(overview, "dark fantasy") or any(
            insight_normalized(signal.get("label")) == "dark fantasy"
            for signal in signals
        )
        if (metadata_available and not has_genre("fantasy")) or not explicit_dark_fantasy:
            return False, "missing_explicit_dark_fantasy_evidence", "requires Fantasy metadata and an explicit dark-fantasy signal"

    if normalized in {"war drama", "war story"} or normalized.startswith("world war"):
        central_war = has_genre("war", "war & politics") or (
            candidate.confidence == "high"
            and has_evidence("soldiers", "military unit", "battlefield", "during the war")
        )
        if not central_war:
            return False, "incidental_war_evidence", "requires War metadata or a central war premise"

    if normalized == "prison drama":
        explicit_prison_identity = (
            (
                candidate.source.startswith(
                    ("source_signal:audience_expectation", "curated_override:audience_expectation")
                )
                or (
                    candidate.source == "inferred_context"
                    and candidate.trust_tier <= 3
                )
            )
            and has_evidence("prison", "inmate", "warden", "prison system", "long sentence")
        )
        if not explicit_prison_identity:
            return False, "incidental_prison_context", "requires an explicit prison identity and central premise"

    if normalized == "serial killer investigation" and not evidence_family_matches(
        overview,
        "serial_killer",
    ):
        return False, "missing_serial_killer_evidence", "generic murder or detective evidence is insufficient"

    if normalized == "psychological survival thriller":
        has_survival = has_evidence(
            "survival",
            "struggle for survival",
            "survival story",
            "survival under pressure",
            "tries to survive",
            "fight to survive",
            "stranded",
            "wilderness survival",
        )
        compatible_genre = has_genre("thriller", "horror")
        if not has_survival or not compatible_genre or (
            has_genre("animation", "family", "adventure") and not compatible_genre
        ):
            return False, "missing_central_survival_thriller_evidence", "requires physical survival evidence and Thriller/Horror metadata"

    if "fantasy adventure" in normalized and not has_genre("fantasy"):
        return False, "fantasy_identity_conflicts_with_metadata", "requires Fantasy genre"

    if "sci fi" in normalized or "sci-fi" in candidate.label.casefold():
        if not has_genre("sci-fi", "science fiction"):
            return False, "scifi_identity_conflicts_with_metadata", "requires Sci-Fi genre"

    if "crime" in normalized and not (
        has_genre("crime")
        or any(
            phrase_present(overview, phrase)
            for phrase in ("crime", "criminal", "murder", "police", "detective")
        )
    ):
        if metadata_available or not candidate.source.startswith("source_signal:audience_expectation"):
            return False, "crime_identity_conflicts_with_metadata", "requires Crime metadata or explicit crime premise"

    if "fantasy" in normalized and not (
        has_genre("fantasy") or has_evidence("fantasy world", "mythical land")
    ):
        if metadata_available or not candidate.source.startswith("source_signal:audience_expectation"):
            return False, "fantasy_identity_conflicts_with_metadata", "requires Fantasy metadata or explicit fantasy premise"

    identity_genre_markers = {
        "comedy": "comedy",
        "documentary": "documentary",
        "horror": "horror",
        "mystery": "mystery",
        "romance": "romance",
        "thriller": "thriller",
        "western": "western",
    }
    matched_markers = {
        genre for marker, genre in identity_genre_markers.items() if marker in normalized
    }
    if matched_markers and not (matched_markers & genres):
        if candidate.trust_tier >= 5:
            return False, "identity_genre_not_supported", f"required one of:{','.join(sorted(matched_markers))}"

    return True, "compatible", f"genres:{','.join(sorted(genres)) or 'none'}"


def genre_identity(candidates: list[str], display_context: dict[str, Any]) -> str | None:
    genres = {
        insight_normalized(genre)
        for genre in (display_context or {}).get("genres") or []
        if has_text(genre)
    }
    all_identity_text = insight_normalized(" ".join(candidates))
    if "documentary" in genres:
        if "concert film" in all_identity_text and "music" in genres:
            return "Concert film"
        if any(
            marker in all_identity_text
            for marker in ("war drama", "war story", "world war")
        ):
            return "War documentary"
        if any(
            marker in all_identity_text
            for marker in ("historical drama", "history documentary")
        ):
            return "History documentary"
        for companion, identity in (
            ("war", "War documentary"),
            ("history", "History documentary"),
            ("music", "Music documentary"),
            ("nature", "Nature documentary"),
        ):
            if companion in genres:
                return identity
        return "Documentary"
    if "horror" in genres and "music driven" in all_identity_text:
        return "Music-driven horror"
    if "horror" in genres and "body horror satire" in all_identity_text:
        return "Body-horror satire"
    if {"history", "music", "drama"} <= genres:
        return "Historical music drama"
    if {"horror", "comedy"} <= genres:
        return "Horror comedy"
    if {"romance", "drama"} <= genres:
        return "Romantic drama"
    if {"crime", "history"} <= genres:
        return "Historical crime drama"
    if {"crime", "thriller"} <= genres:
        return "Crime thriller"
    if any("war" in genre for genre in genres):
        return "War drama"
    if {"history", "drama"} <= genres:
        return "Historical drama"
    if "fantasy" in genres:
        if "dark fantasy" in all_identity_text:
            return "Dark fantasy"
        if any(marker in all_identity_text for marker in ("political power", "court intrigue", "royal power")):
            return "Political dark fantasy"
        if "adventure" in genres:
            return "Fantasy adventure"
        return "Fantasy drama" if "drama" in genres else "Fantasy story"
    if {"animation", "adventure"} <= genres:
        return "Animated adventure"
    for genre, identity in (
        ("documentary", "Documentary"),
        ("horror", "Horror"),
        ("crime", "Crime story"),
        ("thriller", "Thriller"),
        ("comedy", "Comedy"),
        ("drama", "Drama"),
    ):
        if genre in genres:
            return identity
    return None


def inferred_identity_trust(
    label: str,
    display_context: dict[str, Any],
) -> tuple[int, str]:
    normalized = insight_normalized(label)
    strictly_governed = {
        "dark sci fi anthology",
        "mythic superhero mystery",
        "satirical sci fi anthology",
        "supernatural superhero adventure",
        "sci fi heist",
        "psychological survival thriller",
        "tech dystopia anthology",
    }
    if normalized in strictly_governed:
        return 3, "strict_multi_evidence_inference"
    overview = insight_normalized(
        ((display_context or {}).get("content") or {}).get("overview")
    )
    explicit_rules = {
        "cyberpunk action sci fi": ("cyberpunk", "cyber-punk"),
        "prison drama": ("prison inmate", "prison system", "corrupt warden"),
        "action crime investigation": ("police investigator", "federal investigator"),
        "action crime investigation series": ("police investigator", "federal investigator"),
        "mythic superhero mystery": ("superhero", "super hero", "comic book"),
        "supernatural superhero adventure": ("superhero", "super hero", "comic book"),
        "sci fi heist": ("heist",),
        "psychological survival thriller": ("survival", "stranded", "plane crash"),
    }
    phrases = explicit_rules.get(normalized) or ()
    if normalized == "serial killer investigation" and evidence_family_matches(
        overview,
        "serial_killer",
    ):
        return 3, "explicit_premise_identity"
    if normalized in {"spy story", "spy thriller"} and evidence_family_matches(
        overview,
        "spy",
    ):
        return 3, "explicit_premise_identity"
    if any(phrase_present(overview, phrase) for phrase in phrases):
        return 3, "explicit_premise_identity"
    return 5, "governed_inferred_identity"


def identity_evidence_family(label: Any) -> str | None:
    normalized = insight_normalized(label)
    for family, markers in IDENTITY_EVIDENCE_LABEL_FAMILIES:
        if any(phrase_present(normalized, marker) for marker in markers):
            return family
    return None


def identity_has_explicit_premise(family: str | None, overview: str) -> bool:
    if not family or not overview:
        return False
    if family == "spy":
        return evidence_family_matches(overview, "spy")
    phrases = {
        "mythic_scifi": ("prophecy", "destiny", "messiah", "mythic"),
        "space_scifi": ("in space", "cosmic", "intergalactic", "spacecraft"),
        "superhero": ("superhero", "super hero", "avengers", "one hero"),
        "organized_crime": ("organized crime", "criminal organization", "cartel"),
        "investigation": (
            "investigates",
            "investigation",
            "detective",
            "solve the case",
            "hunt a serial killer",
        ),
        "creature": ("creature", "kaiju", "monster"),
        "fantasy": (
            "fantasy",
            "faun",
            "labyrinth",
            "lost princess",
            "underground kingdom",
            "magical world",
            "mythical land",
        ),
        "heist": ("heist", "art thief", "robbery", "caper"),
        "action": ("face off", "martial arts", "assassin", "defeating"),
        "war": (
            "battlefield",
            "military unit",
            "soldier",
            "troops",
            "resistance fighter",
            "resistance",
            "nazi",
            "nazis",
            "occupation",
            "occupied",
            "fighting the war",
        ),
    }.get(family, ())
    return any(phrase_present(overview, phrase) for phrase in phrases)


def corroborate_identity_candidate(
    candidate: IdentityCandidate,
    signals: list[dict[str, Any]],
    display_context: dict[str, Any],
) -> IdentityCandidate:
    """Attach independent evidence families without flattening trust tiers."""

    family = identity_evidence_family(candidate.label)
    sources: set[str] = set()
    if candidate.source.startswith("curated_override:"):
        sources.add("curated_identity")
    elif candidate.source.startswith("source_signal:audience_expectation"):
        sources.add("audience_expectation")
    elif candidate.source.startswith("source_signal:topic_theme"):
        sources.add("topic_theme")
    elif candidate.source == "genre_context":
        sources.add("content_genre")
    elif candidate.source == "inferred_context":
        sources.add("governed_context")

    signal_markers = IDENTITY_SIGNAL_CORROBORATION.get(family or "", ())
    for signal in safe_signals(signals):
        dimension = signal.get("dimension")
        if dimension not in {"audience_expectation", "topic_theme"}:
            continue
        signal_text = signal.get("label") or signal.get("value")
        signal_family = identity_evidence_family(signal_text)
        marker_match = any(
            phrase_present(insight_normalized(signal_text), marker)
            for marker in signal_markers
        )
        if family and (signal_family == family or marker_match):
            sources.add(dimension)

    genres = {
        insight_normalized(genre)
        for genre in (display_context or {}).get("genres") or []
        if has_text(genre)
    }
    if genres & IDENTITY_GENRE_CORROBORATION.get(family or "", set()):
        sources.add("content_genre")

    overview = insight_normalized(
        ((display_context or {}).get("content") or {}).get("overview")
    )
    explicit_premise = identity_has_explicit_premise(family, overview)
    if explicit_premise:
        sources.add("explicit_overview")

    incidental = bool(
        family in INCIDENTAL_IDENTITY_FAMILIES
        and not explicit_premise
        and "curated_identity" not in sources
    )
    if incidental:
        centrality = "incidental_context"
    elif explicit_premise:
        centrality = "explicit_premise"
    elif len(sources) >= 2:
        centrality = "corroborated"
    else:
        centrality = "single_source"
    return IdentityCandidate(
        label=candidate.label,
        trust_tier=candidate.trust_tier,
        confidence=candidate.confidence,
        source=candidate.source,
        evidence=candidate.evidence,
        position=candidate.position,
        corroboration_sources=tuple(sorted(sources)),
        corroboration_count=len(sources),
        centrality_class=centrality,
        explicit_premise_evidence=explicit_premise,
        incidental_context=incidental,
        ranking_rationale=candidate.ranking_rationale,
    )


def apply_identity_centrality_guard(
    ranked: list[IdentityCandidate],
) -> tuple[IdentityCandidate | None, str]:
    """Resolve close ranking contests without replacing trust-tier authority."""

    if not ranked:
        return None, "no_compatible_identity"
    selected = ranked[0]
    if selected.trust_tier == 1:
        return selected, "curated_tier_authority"

    alternatives = []
    for candidate in ranked[1:]:
        same_tier = candidate.trust_tier == selected.trust_tier
        governed_genre_guard = bool(
            selected.source == "genre_context"
            and candidate.trust_tier == selected.trust_tier + 1
        )
        if not (same_tier or governed_genre_guard):
            continue
        required_gain = 2 if governed_genre_guard else 1
        materially_stronger = (
            candidate.corroboration_count
            >= selected.corroboration_count + required_gain
        )
        central_enough = bool(
            candidate.explicit_premise_evidence
            and (
                selected.incidental_context
                or candidate.corroboration_count >= 4
            )
        )
        if materially_stronger and central_enough:
            alternatives.append(candidate)

    if not alternatives:
        return selected, "trust_tier_then_specificity"
    chosen = sorted(
        alternatives,
        key=lambda candidate: (
            -candidate.corroboration_count,
            candidate.trust_tier,
            CONFIDENCE_ORDER.get(candidate.confidence or "", 99),
            candidate.position,
            insight_normalized(candidate.label),
        ),
    )[0]
    return chosen, "explicit_premise_with_stronger_independent_corroboration"


def select_identity(
    display_profile: dict[str, Any],
    watch_profile: dict[str, Any],
    signals: list[dict[str, Any]],
    display_context: dict[str, Any],
    plan: InsightPlan,
) -> InsightComponent | None:
    raw_labels = unique_preserve_order(
        signal_labels_for_dimensions(signals, {"audience_expectation", "topic_theme"})
        + list(display_profile.get("identity") or [])
        + [display_context.get("inferred_identity")]
    )
    candidate_rows: list[IdentityCandidate] = []
    curated_identity_signals: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()

    def add_candidate(candidate: IdentityCandidate) -> None:
        key = (insight_normalized(candidate.label), candidate.trust_tier, candidate.source)
        if not candidate.label or key in seen:
            return
        seen.add(key)
        candidate_rows.append(candidate)

    position = 0
    for signal in sorted(safe_signals(signals), key=signal_priority):
        if signal.get("dimension") not in {"audience_expectation", "topic_theme"}:
            continue
        label = signal.get("label")
        confidence = insight_normalized(signal.get("confidence")) or None
        curated = (
            bool(watch_profile.get("curated_override_applied"))
            and "curated override" in signal_source_names(signal)
        )
        curated_identity_signal = bool(
            curated
            and (
                signal.get("dimension") == "audience_expectation"
                or identity_has_copy_role(label)
            )
        )
        if curated_identity_signal:
            curated_identity_signals.append(signal)
        if not identity_has_copy_role(label):
            if curated_identity_signal:
                plan.rejected_candidates.append(
                    {
                        "candidate": label,
                        "role": "primary_identity",
                        "reason": "missing_identity_copy_role",
                        "source": f"curated_override:{signal.get('dimension')}:{signal.get('value')}",
                        "confidence": confidence,
                    }
                )
            continue
        if curated:
            tier = 1
        elif signal.get("dimension") == "audience_expectation":
            tier = 2 if confidence == "high" else 4 if confidence == "medium" else 6
        elif insight_normalized(label) in IDENTITY_BEARING_TOPIC_LABELS:
            tier = 4 if confidence in {"high", "medium"} else 6
        else:
            tier = 6
        add_candidate(
            IdentityCandidate(
                label=label,
                trust_tier=tier,
                confidence=confidence,
                source=(
                    f"curated_override:{signal.get('dimension')}:{signal.get('value')}"
                    if curated
                    else f"source_signal:{signal.get('dimension')}:{signal.get('value')}"
                ),
                evidence=f"{signal.get('dimension')}:{label}",
                position=position,
            )
        )
        position += 1

    genre_based = genre_identity(raw_labels, display_context)
    if genre_based:
        governed_genre = insight_normalized(genre_based) in GOVERNED_GENRE_IDENTITIES
        add_candidate(
            IdentityCandidate(
                label=genre_based,
                trust_tier=3 if governed_genre else 7,
                confidence="high" if governed_genre else None,
                source="genre_context",
                evidence=f"genres:{','.join((display_context or {}).get('genres') or [])}",
                position=position,
            )
        )
        position += 1

    inferred = display_context.get("inferred_identity")
    if has_text(inferred):
        inferred_tier, inferred_reason = inferred_identity_trust(
            inferred,
            display_context,
        )
        add_candidate(
            IdentityCandidate(
                label=inferred,
                trust_tier=inferred_tier,
                confidence="high" if inferred_tier == 3 else "medium",
                source="inferred_context",
                evidence=f"inferred_identity:{inferred};rule={inferred_reason}",
                position=position,
            )
        )
        position += 1

    for label in display_profile.get("identity") or []:
        if not identity_has_copy_role(label):
            plan.rejected_candidates.append(
                {"candidate": label, "role": "primary_identity", "reason": "missing_identity_copy_role"}
            )
            continue
        if any(insight_normalized(row.label) == insight_normalized(label) for row in candidate_rows):
            continue
        add_candidate(
            IdentityCandidate(
                label=label,
                trust_tier=7,
                confidence=None,
                source="display_profile",
                evidence=f"profile.identity:{label}",
                position=position,
            )
        )
        position += 1

    compatible: list[IdentityCandidate] = []
    for candidate in candidate_rows:
        if not identity_has_copy_role(candidate.label):
            plan.rejected_candidates.append(
                {"candidate": candidate.label, "role": "primary_identity", "reason": "missing_identity_copy_role"}
            )
            continue
        accepted, reason, evidence = identity_compatibility(candidate, signals, display_context)
        if not accepted:
            plan.rejected_candidates.append(
                {
                    "candidate": candidate.label,
                    "role": "primary_identity",
                    "reason": "identity_metadata_conflict",
                    "conflict_reason": reason,
                    "source": candidate.source,
                    "confidence": candidate.confidence,
                    "evidence": evidence,
                    "trust_tier": candidate.trust_tier,
                }
            )
            continue
        compatible.append(
            corroborate_identity_candidate(candidate, signals, display_context)
        )

    ranked = sorted(
        compatible,
        key=lambda candidate: (
            candidate.trust_tier,
            CONFIDENCE_ORDER.get(candidate.confidence or "", 99),
            -identity_score(candidate.label, candidate.position, signals),
            candidate.position,
            insight_normalized(candidate.label),
        ),
    )
    selected, selection_rationale = apply_identity_centrality_guard(ranked)
    if not curated_identity_signals:
        plan.curated_identity_evaluation = "not_applicable"
    elif selected and selected.source.startswith("curated_override:"):
        plan.curated_identity_evaluation = "selected"
    elif curated_identity_signals:
        plan.curated_identity_evaluation = "evaluated_rejected"
    if not selected:
        return None
    for candidate in ranked:
        if candidate is selected:
            continue
        if insight_normalized(candidate.label) != insight_normalized(selected.label):
            displaced_by_centrality = bool(
                ranked
                and candidate is ranked[0]
                and selected is not ranked[0]
            )
            plan.rejected_candidates.append(
                {
                    "candidate": candidate.label,
                    "role": "primary_identity",
                    "reason": (
                        "stronger_corroborated_candidate_selected"
                        if displaced_by_centrality
                        else "lower_trust_or_specificity"
                    ),
                    "source": candidate.source,
                    "confidence": candidate.confidence,
                    "trust_tier": candidate.trust_tier,
                    "evidence": candidate.evidence,
                    "corroboration_sources": candidate.corroboration_sources,
                    "corroboration_count": candidate.corroboration_count,
                    "centrality_class": candidate.centrality_class,
                    "explicit_premise_evidence": candidate.explicit_premise_evidence,
                    "incidental_context": candidate.incidental_context,
                    "ranking_rationale": (
                        "lost to explicit premise with materially stronger independent corroboration"
                        if displaced_by_centrality
                        else "lower trust, confidence, specificity, or centrality"
                    ),
                }
            )
    return InsightComponent(
        text=normalize_display_phrase(selected.label) or selected.label,
        role="identity",
        concept_family=insight_concept_family(selected.label),
        source=selected.source,
        evidence=selected.evidence,
        confidence=selected.confidence,
        trust_tier=selected.trust_tier,
        selection_rationale=(
            f"selected {IDENTITY_TRUST_TIER_LABELS[selected.trust_tier]};"
            f"rule={selection_rationale}"
        ),
        corroboration_sources=selected.corroboration_sources,
        corroboration_count=selected.corroboration_count,
        centrality_class=selected.centrality_class,
        explicit_premise_evidence=selected.explicit_premise_evidence,
        incidental_context=selected.incidental_context,
    )


def phrase_present(text: str, phrase: str) -> bool:
    normalized_phrase = insight_normalized(phrase)
    return bool(
        normalized_phrase
        and re.search(
            rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])",
            text,
        )
    )


def evidence_family_matches(text: Any, family: str) -> bool:
    """Match a governed lexical family without arbitrary substring checks."""

    normalized = insight_normalized(text)
    if family == "spy":
        # Avoid treating the third-person verb in "spies on" as a spy premise.
        normalized = re.sub(r"\bspies on\b", "", normalized)
    variants = EVIDENCE_FAMILIES.get(family) or ()
    return bool(
        normalized
        and any(phrase_present(normalized, variant) for variant in variants)
    )


def genre_matches(genres: set[str], required: str) -> bool:
    required = insight_normalized(required)
    return any(
        genre == required
        or genre.startswith(f"{required} ")
        or genre.endswith(f" {required}")
        for genre in genres
    )


def context_components(display_context: dict[str, Any]) -> list[InsightComponent]:
    content = (display_context or {}).get("content") or {}
    overview = insight_normalized(content.get("overview"))
    genres = {
        insight_normalized(genre)
        for genre in (display_context or {}).get("genres") or []
        if has_text(genre)
    }
    components = []
    if not overview:
        return components
    for rule in INSIGHT_CONTEXT_RULES:
        required_genres = {
            insight_normalized(value) for value in rule.get("genres") or ()
        }
        if required_genres and not all(
            genre_matches(genres, required) for required in required_genres
        ):
            continue
        required = [value for value in rule["required"] if phrase_present(overview, value)]
        if len(required) != len(rule["required"]):
            continue
        alternatives = [value for value in rule["any"] if phrase_present(overview, value)]
        if rule["any"] and not alternatives:
            continue
        matched = required + alternatives[:1]
        components.append(
            InsightComponent(
                text=rule["phrase"],
                role="about_phrase",
                concept_family=rule["family"],
                source="overview_rule",
                evidence=(
                    f"rule={rule['rule']};matched={','.join(matched)};"
                    f"scope={rule['evidence_scope']}"
                ),
                confidence="high",
            )
        )
    return components


def theme_component(
    label: str,
    signals: list[dict[str, Any]],
    plan: InsightPlan,
) -> InsightComponent | None:
    normalized = insight_normalized(label)
    if normalized in RAW_TAXONOMY_DIFFERENTIATORS:
        plan.rejected_candidates.append(
            {
                "candidate": label,
                "role": "about_phrase",
                "reason": "raw_taxonomy_not_user_facing",
            }
        )
        return None
    signal = insight_signal_match(label, signals, dimensions={"topic_theme"})
    if not signal:
        return None
    phrase = {
        insight_normalized(key): value
        for key, value in INSIGHT_ABOUT_PHRASES.items()
    }.get(normalized)
    if not phrase:
        plan.rejected_candidates.append(
            {
                "candidate": label,
                "role": "about_phrase",
                "reason": "missing_about_copy_role",
            }
        )
        return None
    return InsightComponent(
        text=phrase,
        role="about_phrase",
        concept_family=insight_concept_family(label),
        source=f"source_signal:{signal.get('dimension')}:{signal.get('value')}",
        evidence=f"topic_theme:{label}",
        confidence=signal.get("confidence"),
    )


def differentiator_is_incidental(
    component: InsightComponent,
    display_context: dict[str, Any],
    identity: InsightComponent | None,
) -> bool:
    if component.source == "overview_rule":
        return False
    family = component.concept_family
    normalized = insight_normalized(component.text)
    if family not in INCIDENTAL_DIFFERENTIATOR_FAMILIES:
        if normalized.startswith("organized crime"):
            family = "organized_crime"
        elif normalized.startswith("prison"):
            family = "prison"
        else:
            return False

    overview = insight_normalized(
        ((display_context or {}).get("content") or {}).get("overview")
    )
    genres = {
        insight_normalized(genre)
        for genre in (display_context or {}).get("genres") or []
        if has_text(genre)
    }
    if family == "war_identity":
        return not (
            genres & {"war", "war politics"}
            or identity_has_explicit_premise("war", overview)
        )
    if family == "creature":
        central_identity_family = identity_evidence_family(
            identity.text if identity else ""
        )
        explicit_creature = identity_has_explicit_premise("creature", overview) or any(
            phrase_present(overview, marker)
            for marker in ("dinosaur", "dinosaurs", "supernatural threat")
        )
        return bool(
            not explicit_creature
            and central_identity_family in {"mythic_scifi", "space_scifi"}
        )
    # These concepts need affirmative incidental evidence before suppression;
    # absence from a short overview is not enough to demote a governed signal.
    return False


def select_differentiators(
    display_profile: dict[str, Any],
    signals: list[dict[str, Any]],
    display_context: dict[str, Any],
    identity: InsightComponent | None,
    plan: InsightPlan,
) -> list[InsightComponent]:
    contexts = context_components(display_context)
    priority_rules = {
        "explicit_racial_inequality",
        "studio_workplace",
        "matchmaking",
        "family_estrangement",
    }
    exclusive_context_rules = {"explicit_racial_inequality"}

    def context_rule(component: InsightComponent) -> str:
        return component.evidence.split(";", 1)[0].split("=", 1)[-1]

    priority_context = [
        component for component in contexts if context_rule(component) in priority_rules
    ]
    fallback_context = [
        component for component in contexts if context_rule(component) not in priority_rules
    ]
    labels = unique_preserve_order(
        signal_labels_for_dimensions(signals, {"topic_theme"})
        + list(display_profile.get("themes") or [])
    )
    themes = []
    identity_family = identity.concept_family if identity else None
    for label in labels:
        label_family = insight_concept_family(label)
        if identity_family and label_family == identity_family:
            plan.rejected_candidates.append(
                {
                    "candidate": label,
                    "role": "about_phrase",
                    "reason": "duplicate_concept_family",
                    "concept_family": label_family,
                }
            )
            continue
        component = theme_component(label, signals, plan)
        if component is not None:
            themes.append(component)
    candidates = priority_context + themes + fallback_context
    selected = []
    seen_families = {identity.concept_family} if identity else set()
    identity_text = insight_normalized(identity.text if identity else "")
    for candidate_index, candidate in enumerate(candidates):
        if differentiator_is_incidental(candidate, display_context, identity):
            plan.rejected_candidates.append(
                {
                    "candidate": candidate.text,
                    "role": candidate.role,
                    "reason": "incidental_context_suppressed",
                    "concept_family": candidate.concept_family,
                    "source": candidate.source,
                    "evidence": candidate.evidence,
                }
            )
            continue
        if selected and candidate.confidence == "low":
            plan.rejected_candidates.append(
                {
                    "candidate": candidate.text,
                    "role": candidate.role,
                    "reason": "low_confidence_secondary",
                }
            )
            continue
        if (
            candidate.concept_family in seen_families
            or (
                candidate.concept_family
                in {"conspiracy", "investigation", "post apocalyptic", "survival"}
                and candidate.concept_family in identity_text
            )
        ):
            plan.rejected_candidates.append(
                {
                    "candidate": candidate.text,
                    "role": candidate.role,
                    "reason": "duplicate_concept_family",
                    "concept_family": candidate.concept_family,
                }
            )
            continue
        if any(
            candidate.text in existing.text or existing.text in candidate.text
            for existing in selected
        ):
            plan.rejected_candidates.append(
                {
                    "candidate": candidate.text,
                    "role": candidate.role,
                    "reason": "duplicate_phrase",
                }
            )
            continue
        selected.append(candidate)
        seen_families.add(candidate.concept_family)
        if context_rule(candidate) in exclusive_context_rules:
            for remainder in candidates[candidate_index + 1 :]:
                plan.rejected_candidates.append(
                    {
                        "candidate": remainder.text,
                        "role": remainder.role,
                        "reason": "lower_priority_than_explicit_context",
                        "concept_family": remainder.concept_family,
                        "source": remainder.source,
                        "evidence": remainder.evidence,
                    }
                )
            break
        if len(selected) == 2:
            break
    return selected


def select_modifier(
    display_profile: dict[str, Any],
    signals: list[dict[str, Any]],
    identity: InsightComponent | None,
    plan: InsightPlan,
) -> InsightComponent | None:
    identity_text = insight_normalized(identity.text if identity else "")
    feel_labels = [
        label for label in display_profile.get("feel") or [] if has_text(label)
    ]
    if any(
        identity_text.startswith(f"{insight_normalized(adjective)} ")
        for adjective in INSIGHT_ADJECTIVES.values()
    ):
        return None
    comedy_order = {"playful": 0, "light": 1, "darkly funny": 2, "satirical": 3}
    ranked_labels = []
    for position, label in enumerate(feel_labels):
        signal = insight_signal_match(label, signals, dimensions={"tone", "mood"})
        ranked_labels.append((label, signal, position))
    ranked_labels.sort(
        key=lambda item: (
            CONFIDENCE_ORDER.get(insight_normalized((item[1] or {}).get("confidence")), 99),
            comedy_order.get(insight_normalized(item[0]), 20) if "comedy" in identity_text else 0,
            item[2],
            insight_normalized(item[0]),
        )
    )
    for label, signal, _position in ranked_labels:
        adjective = INSIGHT_ADJECTIVES.get(insight_normalized(label))
        if not adjective:
            plan.rejected_candidates.append(
                {
                    "candidate": label,
                    "role": "modifier",
                    "reason": "no_adjective_copy_role",
                }
            )
            continue
        if adjective in identity_text:
            continue
        return InsightComponent(
            text=adjective,
            role="adjective",
            concept_family=insight_concept_family(label),
            source=(
                f"source_signal:{signal.get('dimension')}:{signal.get('value')}"
                if signal
                else "display_profile"
            ),
            evidence=(
                f"{signal.get('dimension')}:{label}"
                if signal
                else f"profile.feel:{label}"
            ),
            confidence=signal.get("confidence") if signal else None,
        )
    return None


def select_pacing(
    display_profile: dict[str, Any],
    signals: list[dict[str, Any]],
) -> InsightComponent | None:
    pace = display_profile.get("pace")
    if not has_text(pace):
        return None
    pacing_signals = [
        signal
        for signal in safe_signals(signals)
        if signal.get("dimension") == "pacing"
    ]
    pacing_signal = sorted(pacing_signals, key=signal_priority)[0] if pacing_signals else None
    source_pace = pacing_signal.get("label") if pacing_signal else pace
    normalized = insight_normalized(source_pace)
    if "dialogue" in normalized:
        copy_text = "dialogue-driven"
    elif "slow" in normalized or "measured" in normalized:
        copy_text = "measured"
    elif "fast" in normalized or "action" in normalized:
        copy_text = "fast-moving"
    elif "character" in normalized:
        copy_text = "character-driven"
    else:
        copy_text = lower_first(normalize_display_phrase(source_pace) or source_pace)
        if " and " in copy_text:
            copy_text = copy_text.split(" and ", 1)[0]
    return InsightComponent(
        text=copy_text,
        role="pacing_phrase",
        concept_family=insight_concept_family(pace),
        source=(
            f"source_signal:pacing:{pacing_signal.get('value')}"
            if pacing_signal
            else "display_profile"
        ),
        evidence=(
            f"pacing:{pacing_signal.get('label')}"
            if pacing_signal
            else f"profile.pace:{pace}"
        ),
        confidence=pacing_signal.get("confidence") if pacing_signal else None,
    )


def rating_source_provenance(ratings: dict[str, Any]) -> dict[str, Any]:
    sources = [source for source in ratings.get("sources") or [] if isinstance(source, dict)]
    configured_count = int(ratings.get("scoring_source_count") or 0)
    if sources:
        has_explicit_inclusion = any(
            "included_in_unified_score" in source for source in sources
        )
        included = (
            [source for source in sources if source.get("included_in_unified_score") is True]
            if has_explicit_inclusion
            else sources[:configured_count]
        )
        source_count = len(included)
        categories = sorted(
            {
                insight_normalized(source.get("source_category"))
                for source in included
                if insight_normalized(source.get("source_category"))
            }
        )
        source_names = sorted(
            {
                insight_normalized(source.get("source_name") or source.get("display_name"))
                for source in included
                if insight_normalized(source.get("source_name") or source.get("display_name"))
            }
        )
    else:
        source_count = configured_count
        categories = []
        source_names = []
    return {
        "source_count": source_count,
        "categories": categories,
        "source_names": source_names,
        "audience_only": source_count >= 1 and categories == ["audience"],
    }


def audience_modifier(display_context: dict[str, Any]) -> InsightComponent | None:
    ratings = (display_context or {}).get("ratings") or {}
    score = ratings.get("unified_score")
    provenance = rating_source_provenance(ratings)
    count = provenance["source_count"]
    if score is None or count < 2 or score < 70:
        return None
    strength = (
        "exceptional"
        if score >= 90
        else "strong"
        if score >= 80
        else "positive"
    )
    support_kind = "audience backing" if provenance["audience_only"] else "cross-source ratings"
    return InsightComponent(
        text=f"{strength} {support_kind}",
        role="supporting_phrase",
        concept_family=(
            "audience_backing" if provenance["audience_only"] else "cross_source_ratings"
        ),
        source="rating_summary",
        evidence=(
            f"unified_score:{score};scoring_sources:{count};"
            f"categories:{','.join(provenance['categories']) or 'unknown'};"
            f"sources:{','.join(provenance['source_names']) or 'unavailable'}"
        ),
    )


def select_template(plan: InsightPlan) -> str:
    identity = insight_normalized(
        plan.primary_identity.text if plan.primary_identity else ""
    )
    if "documentary" in identity and plan.primary_differentiator:
        return "documentary_examination"
    if "character drama" in identity and plan.primary_differentiator:
        return "character_exploration"
    if (
        plan.pacing_modifier
        and not plan.tone_modifier
        and plan.primary_differentiator
        and "driven" not in plan.pacing_modifier.text
    ):
        return "experience_driven"
    if plan.primary_differentiator and any(
        marker in insight_normalized(plan.primary_differentiator.text)
        for marker in ("conflict", "investigation", "mission", "pressure", "struggle", "threat")
    ):
        return "identity_conflict"
    if (
        plan.primary_differentiator
        and plan.primary_differentiator.concept_family
        in {
            "addiction",
            "artistic ambition",
            "class",
            "emotion",
            "family",
            "friendship",
            "grief and healing",
            "human_cost",
            "identity",
            "mental health",
            "obsession",
            "racial injustice",
            "romance",
            "social critique",
        }
    ):
        return "thematic_exploration"
    if plan.secondary_differentiator and any(
        marker in identity for marker in ("horror comedy", "satire")
    ):
        return "hybrid_blend"
    if plan.secondary_differentiator:
        return "layered_exploration"
    return "identity_about"


def build_insight_plan(
    display_profile: dict[str, Any],
    watch_profile: dict[str, Any],
    signals: list[dict[str, Any]],
    display_context: dict[str, Any] | None = None,
) -> InsightPlan:
    context = dict(display_context or {})
    safe = safe_signals(signals)
    plan = InsightPlan()
    plan.curated_override_applied = bool(
        watch_profile.get("curated_override_applied")
    )
    plan.curated_identity_available = any(
        signal.get("dimension") in {"audience_expectation", "topic_theme"}
        and (
            signal.get("dimension") == "audience_expectation"
            or identity_has_copy_role(signal.get("label"))
        )
        and "curated override" in signal_source_names(signal)
        for signal in safe
    )
    if plan.curated_identity_available:
        plan.curated_identity_evaluation = "not_evaluated"
    for signal in signals or []:
        if signal.get("spoiler_safe") is False:
            plan.rejected_candidates.append(
                {
                    "candidate": signal.get("label"),
                    "role": "signal",
                    "reason": "spoiler_unsafe",
                }
            )
    plan.primary_identity = select_identity(
        display_profile,
        watch_profile,
        safe,
        context,
        plan,
    )
    rejected_families = rejected_source_signal_concept_families(plan)
    compatible_safe = [
        signal
        for signal in safe
        if not signal_uses_rejected_concept(signal, rejected_families)
    ]
    plan.tone_modifier = select_modifier(
        display_profile,
        compatible_safe,
        plan.primary_identity,
        plan,
    )
    differentiators = select_differentiators(
        display_profile,
        compatible_safe,
        context,
        plan.primary_identity,
        plan,
    )
    if differentiators:
        plan.primary_differentiator = differentiators[0]
    if len(differentiators) > 1:
        plan.secondary_differentiator = differentiators[1]
    plan.pacing_modifier = select_pacing(display_profile, compatible_safe)
    if plan.pacing_modifier:
        compared = [
            component
            for component in (
                plan.primary_identity,
                plan.primary_differentiator,
                plan.secondary_differentiator,
            )
            if component
        ]
        pacing_root = insight_normalized(plan.pacing_modifier.text).replace(
            " driven", ""
        )
        if (
            plan.pacing_modifier.concept_family
            in {component.concept_family for component in compared}
            or (
                pacing_root
                and pacing_root
                in insight_normalized(
                    " ".join(component.text for component in compared)
                )
            )
        ):
            plan.rejected_candidates.append(
                {
                    "candidate": plan.pacing_modifier.text,
                    "role": "pacing_phrase",
                    "reason": "sentence_component_overlap",
                }
            )
            plan.pacing_modifier = None
    plan.audience_modifier = audience_modifier(context)
    plan.template_family = select_template(plan)
    plan.validation_errors = validate_insight_plan(plan)
    return plan


def validate_insight_plan(plan: InsightPlan) -> list[str]:
    errors = []
    if not plan.primary_identity or not plan.primary_identity.supported:
        errors.append("missing_supported_identity")
    components = [
        component
        for component in (
            plan.primary_identity,
            plan.tone_modifier,
            plan.mood_modifier,
            plan.primary_differentiator,
            plan.secondary_differentiator,
            plan.pacing_modifier,
            plan.audience_modifier,
        )
        if component
    ]
    if any(not component.supported for component in components):
        errors.append("unsupported_component")
    families = [
        component.concept_family
        for component in (
            plan.primary_identity,
            plan.primary_differentiator,
            plan.secondary_differentiator,
        )
        if component and component.concept_family
    ]
    if len(families) != len(set(families)):
        errors.append("duplicate_concept_family")
    if any(
        component and component.role != "about_phrase"
        for component in (
            plan.primary_differentiator,
            plan.secondary_differentiator,
        )
    ):
        errors.append("invalid_differentiator_role")
    return errors


def insight_subject(plan: InsightPlan) -> str:
    identity = lower_first(normalize_display_phrase(plan.primary_identity.text) or "")
    modifier = plan.tone_modifier.text if plan.tone_modifier else None
    if modifier and insight_normalized(modifier) not in insight_normalized(identity):
        leading_identity = insight_normalized(identity).split()[:1]
        governed_adjectives = {
            insight_normalized(value) for value in INSIGHT_ADJECTIVES.values()
        } | {"restrained", "quiet", "character driven"}
        if leading_identity and leading_identity[0] in governed_adjectives:
            return f"{modifier}, {identity}".strip()
        return f"{modifier} {identity}".strip()
    return identity


def join_differentiators(primary: str, secondary: str | None) -> str:
    if not secondary:
        return primary
    connector = " alongside " if " and " in primary or " and " in secondary else " and "
    return f"{primary}{connector}{secondary}"


def pacing_suffix(component: InsightComponent | None) -> str | None:
    if not component:
        return None
    normalized = insight_normalized(component.text)
    if "dialogue" in normalized:
        return "driven by dialogue"
    if "measured" in normalized or "slow" in normalized:
        return "with a measured pace"
    if "fast" in normalized or "action" in normalized:
        return "with a fast-moving rhythm"
    if "character" in normalized:
        return "with a character-driven rhythm"
    return None


def render_decision_headline(plan: InsightPlan) -> str | None:
    if plan.validation_errors or not plan.primary_identity:
        return None
    subject = insight_subject(plan)
    if not has_text(subject):
        return None
    return ensure_sentence(
        f"Best suited for viewers looking for {article_for(subject)} {subject}"
    )


def render_insight_plan(plan: InsightPlan) -> str | None:
    if plan.validation_errors or not plan.primary_identity:
        return None
    subject = insight_subject(plan)
    article = article_for(subject).capitalize()
    primary = plan.primary_differentiator.text if plan.primary_differentiator else None
    secondary = (
        plan.secondary_differentiator.text
        if plan.secondary_differentiator
        else None
    )
    if plan.template_family == "documentary_examination" and primary:
        sentence = f"{article} {subject} examining {primary}"
        if secondary:
            sentence += (
                f" alongside {secondary}"
                if " and " in primary or " and " in secondary
                else f" through {secondary}"
            )
    elif plan.template_family in {"character_exploration", "thematic_exploration"} and primary:
        sentence = f"{article} {subject} exploring {join_differentiators(primary, secondary)}"
    elif plan.template_family == "experience_driven" and primary:
        paced_subject = f"{plan.pacing_modifier.text} {subject}".strip()
        sentence = f"{article_for(paced_subject).capitalize()} {paced_subject} about {primary}"
        if secondary:
            sentence += (
                f" alongside {secondary}"
                if " and " in primary or " and " in secondary
                else f" and {secondary}"
            )
    elif plan.template_family == "hybrid_blend" and primary and secondary:
        sentence = f"{article} {subject} that blends {primary} with {secondary}"
    elif plan.template_family == "identity_conflict" and primary:
        sentence = f"{article} {subject} shaped by {join_differentiators(primary, secondary)}"
    elif plan.template_family == "layered_exploration" and primary and secondary:
        sentence = f"{article} {subject} shaped by {join_differentiators(primary, secondary)}"
    else:
        sentence = f"{article} {subject}"
        if primary:
            sentence += f" about {primary}"
        if secondary:
            sentence += (
                f" alongside {secondary}"
                if " and " in primary or " and " in secondary
                else f" and {secondary}"
            )
        elif suffix := pacing_suffix(plan.pacing_modifier):
            sentence += f" {suffix}"
    sentence = re.sub(r"\s+,", ",", sentence)
    sentence = re.sub(r",\s+and\s+", " and ", sentence)
    sentence = re.sub(r"\s{2,}", " ", sentence).strip()
    sentence = ensure_sentence(sentence)
    if sentence and len(sentence) > 180:
        sentence = ensure_sentence(sentence[:177].rsplit(" ", 1)[0])
    return sentence


def build_primary_insight(
    display_profile: dict[str, Any],
    watch_profile: dict[str, Any],
    display_context: dict[str, Any] | None = None,
    signals: list[dict[str, Any]] | None = None,
) -> str | None:
    plan = build_insight_plan(
        display_profile,
        watch_profile,
        signals or [],
        display_context=display_context,
    )
    return render_insight_plan(plan)
