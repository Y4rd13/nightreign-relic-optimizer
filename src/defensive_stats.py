"""Defensive + utility stat roll-ups.

The damage model already tracks offensive scaling (buckets, additives, stat
deltas). This module collects the OTHER half of the character sheet —
damage negation per element, status resistance, poise, max HP, and
affinity attack power — by scanning active effect names and parsing
their effect_text descriptions.

Usage:
    stats = compute_defensive_stats(active_effect_ids, character_id)
    # {"damage_negation": {"physical": 25, "magic": 30, ...},
    #  "status_resistance": {"poison": 60, "bleed": 40, ...},
    #  "max_hp_pct": 20,
    #  "poise_pct": 15,
    #  "affinity_attack": {"holy": 12, "fire": 9, ...}}
"""

from __future__ import annotations

import re
from typing import Iterable

from .effects_db import effects_by_id_for_character


_PERCENT_RE = re.compile(r"by\s*(\d+(?:\.\d+)?)\s*%")
_FLAT_RE = re.compile(r"by\s*(\d+(?:\.\d+)?)\b")


_CATEGORY_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # (name_regex, top_category, sub_key)
    (re.compile(r"physical damage negation", re.I),  "damage_negation", "physical"),
    (re.compile(r"magic damage negation",    re.I),  "damage_negation", "magic"),
    (re.compile(r"fire damage negation",     re.I),  "damage_negation", "fire"),
    (re.compile(r"lightning damage negation", re.I), "damage_negation", "lightning"),
    (re.compile(r"holy damage negation",     re.I),  "damage_negation", "holy"),
    (re.compile(r"affinity damage negation", re.I),  "damage_negation", "affinity"),
    # Status resistance — "+N" flat value, not percent
    (re.compile(r"poison resistance",        re.I),  "status_resistance", "poison"),
    (re.compile(r"scarlet rot resistance",   re.I),  "status_resistance", "scarlet_rot"),
    (re.compile(r"(bleed|hemorrhage) resistance", re.I), "status_resistance", "bleed"),
    (re.compile(r"frost resistance",         re.I),  "status_resistance", "frost"),
    (re.compile(r"sleep resistance",         re.I),  "status_resistance", "sleep"),
    (re.compile(r"madness resistance",       re.I),  "status_resistance", "madness"),
    (re.compile(r"death[- ]?blight resistance", re.I), "status_resistance", "deathblight"),
    # HP / poise
    (re.compile(r"(increased )?maximum hp", re.I),   "max_hp_pct", ""),
    (re.compile(r"poise",                    re.I),  "poise_pct", ""),
    # Offensive affinity — attack power per element
    (re.compile(r"magic attack power",       re.I),  "affinity_attack", "magic"),
    (re.compile(r"fire attack power",        re.I),  "affinity_attack", "fire"),
    (re.compile(r"lightning attack power",   re.I),  "affinity_attack", "lightning"),
    (re.compile(r"holy attack power",        re.I),  "affinity_attack", "holy"),
]


# "Affinity Damage Negation" adds to magic, fire, lightning, holy simultaneously.
# Expand the single effect into 4 per-element entries with the same value.
_MULTI_ELEMENT_CATEGORIES = {"affinity"}


def _parse_numeric(text: str, expect_percent: bool) -> float:
    """Extract the numeric payload from an effect's description text.
    Examples:
        'Increases magic damage negation by 15%' → 15
        'Raises poison resistance by 60'         → 60
        '' or no match                           → 0
    """
    if not text:
        return 0.0
    if expect_percent:
        m = _PERCENT_RE.search(text)
        if m:
            return float(m.group(1))
    else:
        m = _FLAT_RE.search(text)
        if m:
            return float(m.group(1))
    return 0.0


def compute_defensive_stats(
    effect_ids: Iterable[int],
    character_id: str,
) -> dict:
    """Aggregate defensive + utility stats from the active effect set.

    Returns a dict with 4 top-level keys:
      · damage_negation → per-element percent (additive across effects)
      · status_resistance → per-ailment flat point total
      · max_hp_pct → total percent HP bonus
      · poise_pct → total percent stance-damage reduction
      · affinity_attack → per-element attack-power percent (additive)

    Uses effect.name regex to pick a category and effect_text regex to pull
    the numeric value (% or flat). Unrecognised effects are ignored so a
    single pass over the active set is enough. For the 'Affinity Damage
    Negation' umbrella, the value counts once per element.
    """
    ids_lookup = effects_by_id_for_character(character_id)
    out = {
        "damage_negation": {
            "physical": 0.0, "magic": 0.0, "fire": 0.0,
            "lightning": 0.0, "holy": 0.0,
        },
        "status_resistance": {
            "poison": 0.0, "scarlet_rot": 0.0, "bleed": 0.0,
            "frost": 0.0, "sleep": 0.0, "madness": 0.0, "deathblight": 0.0,
        },
        "max_hp_pct": 0.0,
        "poise_pct": 0.0,
        "affinity_attack": {
            "magic": 0.0, "fire": 0.0, "lightning": 0.0, "holy": 0.0,
        },
    }
    for eid in effect_ids:
        e = ids_lookup.get(int(eid))
        if e is None:
            continue
        name = e.name or ""
        text = getattr(e, "effect_text", "") or ""
        for pat, category, sub in _CATEGORY_PATTERNS:
            if not pat.search(name):
                continue
            is_percent = category != "status_resistance"
            value = _parse_numeric(text, expect_percent=is_percent)
            if value == 0.0:
                break
            if category == "damage_negation":
                if sub == "affinity":
                    # Splits across all 4 elements.
                    for el in ("magic", "fire", "lightning", "holy"):
                        out["damage_negation"][el] += value
                else:
                    out["damage_negation"][sub] += value
            elif category == "status_resistance":
                out["status_resistance"][sub] += value
            elif category == "affinity_attack":
                out["affinity_attack"][sub] += value
            elif category in ("max_hp_pct", "poise_pct"):
                out[category] += value
            break
    # Round to 1 decimal to keep display tidy.
    def _round(v):
        if isinstance(v, dict):
            return {k: round(x, 1) for k, x in v.items()}
        return round(v, 1)
    return {k: _round(v) for k, v in out.items()}
