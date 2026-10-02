"""Original Reality tool: match a persona to viable neighborhood places."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from integrations.places import PlaceRecord, search_places

PERSONA_PROFILES = {
    "struggling novelist": {"preferred": {"literary": 28, "writing": 22, "bookstore": 18,
        "quiet": 14, "independent": 12, "historic": 8, "people watching": 8, "low cost": 8},
        "avoid": {"luxury": -30, "chain": -20, "touristy": -12}},
    "urban detective": {"preferred": {"historic": 25, "mysterious": 22, "observation": 18,
        "architecture": 15, "street": 12, "archive": 10}, "avoid": {"luxury": -20, "chain": -15}},
    "indie filmmaker": {"preferred": {"cinematic": 28, "independent": 20, "theater": 18,
        "street": 14, "photography": 14, "dramatic": 10, "historic": 8},
        "avoid": {"chain": -20, "luxury": -10}},
    "architecture apprentice": {"preferred": {"architecture": 30, "historic": 20,
        "industrial": 18, "design": 15, "landmark": 12, "observation": 10}, "avoid": {"chain": -12}},
    "city naturalist": {"preferred": {"nature": 30, "park": 24, "garden": 22,
        "waterfront": 18, "observation": 12, "quiet": 8, "free": 6},
        "avoid": {"touristy": -10, "luxury": -10}},
    "independent magazine editor": {"preferred": {"independent": 26, "design": 20,
        "creative": 18, "archive": 16, "community": 12, "bookstore": 10, "art": 10},
        "avoid": {"chain": -25, "luxury": -8}},
}
ALIASES = {"novelist": "struggling novelist", "writer": "struggling novelist",
    "detective": "urban detective", "filmmaker": "indie filmmaker",
    "architect": "architecture apprentice", "naturalist": "city naturalist",
    "editor": "independent magazine editor"}

# The model may describe a new persona, but it must translate that description
# into this vocabulary. Every positive tag below exists in the curated data, so
# a creative persona still has something concrete and testable to match against.
TAG_VOCABULARY = {
    "academic", "architecture", "archive", "art", "bookstore", "cafe",
    "cinematic", "community", "creative", "design", "dramatic", "food",
    "free", "gallery", "historic", "history", "independent", "industrial",
    "inspiration", "landmark", "library", "literary", "low cost", "museum",
    "music", "mysterious", "nature", "nostalgic", "observation", "park",
    "people watching", "photography", "playful", "quiet", "reflection",
    "storytelling", "street", "theater", "touristy", "waterfront", "writing",
}
AVOID_TAG_VOCABULARY = TAG_VOCABULARY | {"chain", "crowded", "luxury"}


@dataclass
class ScoredPlace:
    record: PlaceRecord
    score: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {**self.record.to_dict(), "theme_score": round(self.score, 1),
                "match_reasons": self.reasons}


def match_theme(persona: str, neighborhood: str, preferences: list[str] | None = None,
                desired_tags: list[str] | None = None, avoid_tags: list[str] | None = None,
                story_tone: str | None = None, max_results: int = 6, *,
                use_live_places: bool = True) -> dict[str, Any]:
    if not str(persona).strip():
        return _error("Persona is required.", "Ask what kind of person the user wants to be for the day.")
    profile_name, preferred, avoided = _profile_for(persona)
    requested, ignored_desired = _controlled_tags(desired_tags, TAG_VOCABULARY)
    rejected, ignored_avoid = _controlled_tags(avoid_tags, AVOID_TAG_VOCABULARY)
    # Custom tags supplement a preset profile too. This lets users ask for an
    # "filmmaker, but quiet and waterfront" without losing the preset weights.
    preferred = {**preferred, **{tag: 20 for tag in requested}}
    avoided = {**avoided, **{tag: -20 for tag in rejected}}
    prefs = {_tag(p) for p in (preferences or []) if str(p).strip()}
    categories = _search_categories(preferred | {p: 1 for p in prefs})
    found = search_places(neighborhood, categories, 20, use_live=use_live_places)
    if not found.ok or len(found.places) < max_results:
        found = search_places(neighborhood, max_results=20, use_live=use_live_places)
    if not found.ok:
        return _error(found.error, found.fix)
    scored, excluded = [], []
    for record in found.places:
        place = record.candidate
        if not place.open_now:
            excluded.append({"place": place.name, "reason": "reported closed"})
            continue
        tags, score, reasons = {_tag(t) for t in place.tags}, 0.0, []
        for tag, weight in preferred.items():
            if tag in tags:
                score += weight; reasons.append(f"Matches the persona through {tag!r} (+{weight})")
        for tag in sorted(prefs & tags):
            score += 12; reasons.append(f"Matches the user's preference for {tag!r} (+12)")
        for tag, penalty in avoided.items():
            if tag in tags:
                score += penalty; reasons.append(f"Weaker fit because it is {tag!r} ({penalty})")
        if place.est_cost == 0:
            score += 5; reasons.append("Free or no required purchase (+5)")
        if place.rating is not None and place.rating >= 4.6:
            score += 3; reasons.append("Strong public rating (+3)")
        if profile_name == "custom":
            words = {_tag(w) for w in re.findall(r"[a-zA-Z]+", persona) if len(w) > 3}
            for word in sorted(words & tags):
                score += 18; reasons.append(f"Matches persona keyword {word!r} (+18)")
        if not reasons:
            reasons.append("Provides category diversity, but has weak direct theme evidence")
        scored.append(ScoredPlace(record, score, reasons))
    scored.sort(key=lambda p: (-p.score, -(p.record.candidate.rating or 0), p.record.candidate.name))
    selected = _choose_diverse(scored, max(1, min(int(max_results), 10)))
    if not selected:
        return _error(f"No currently viable places matched {persona!r} in {neighborhood!r}.",
                      "Try another supported neighborhood, remove a preference, or use a broader persona.")
    return {"ok": True, "persona": persona.strip(), "profile_used": profile_name,
            "role_analysis": {"desired_tags": sorted(requested),
                              "avoid_tags": sorted(rejected),
                              "story_tone": str(story_tone or "").strip(),
                              "ignored_tags": sorted(ignored_desired | ignored_avoid)},
            "neighborhood": selected[0].record.neighborhood, "source": found.source,
            "places": [p.to_dict() for p in selected], "excluded": excluded,
            **({"warning": found.fix} if found.fix else {})}


def candidate_places(result: dict[str, Any]):
    from agents.adaptation.schemas import PlaceCandidate
    return [PlaceCandidate(p["place_id"], p["name"], p["tags"], p["indoor"], p["latitude"],
        p["longitude"], p["rating"], p["open_now"], p["estimated_cost"]) for p in result.get("places", [])]


def _profile_for(persona: str):
    text = " ".join(persona.lower().split())
    name = text if text in PERSONA_PROFILES else next((c for a, c in ALIASES.items() if a in text), "custom")
    if name == "custom":
        return name, {"creative": 10, "observation": 8, "independent": 6}, {"chain": -10}
    return name, PERSONA_PROFILES[name]["preferred"], PERSONA_PROFILES[name]["avoid"]


def _controlled_tags(values, allowed):
    normalized = {_tag(value) for value in (values or []) if str(value).strip()}
    return normalized & allowed, normalized - allowed


def _search_categories(weights):
    categories = {"bookstore", "cafe", "gallery", "museum", "park", "library", "theater",
                  "architecture", "landmark", "street", "garden"}
    return sorted(categories & set(weights))


def _choose_diverse(scored: list[ScoredPlace], limit: int):
    selected, counts = [], {}
    for cap in (1, 2):
        for item in scored:
            if item in selected or counts.get(item.record.category, 0) >= cap:
                continue
            selected.append(item); counts[item.record.category] = counts.get(item.record.category, 0) + 1
            if len(selected) == limit:
                return selected
    return selected


def _tag(value):
    return str(value).strip().lower().replace("_", " ").replace("-", " ")


def _error(error, fix):
    return {"ok": False, "error": error, "fix": fix}
