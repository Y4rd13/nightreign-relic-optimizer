"""Effect registry and per-character candidate filtering.

Data pipeline:
  data/effects.json          — raw Cheat Engine rows (no damage metadata)
  data/baseline_effects.json — shared damage-model metadata
  data/characters/<id>.json  — per-character overrides (weapon-scope, char-tagged
                               bucket values, global constants)

`load_effects()` returns the raw CE roster — usable but with no damage
contribution.  `character_candidates(char_id)` applies baseline + character
metadata to build ready-to-solve Effect objects.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from . import characters as chars_mod

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "data" / "effects.json"
ENRICHED_PATH = ROOT / "data" / "effects_enriched.json"

ROLLABLE_TIERS = {"STD", "BTH", "DoN"}

ATTRIBUTE_GROUPS = {
    "CHARACTER", "ATTACK", "NONE", "HP_REST", "FP_REST", "MAGIC_UP",
    "POISON_UP", "FROST_UP", "CRYSTAL", "PURFUME", "SKILL", "SPELL",
    "ST_AFFINITY", "DISCOVERY",
}

CURSE_GROUP = "CURSE"
EXCLUSIVE_GROUPS = ATTRIBUTE_GROUPS - {"NONE"}

FAMILY_SUFFIX = re.compile(r"\s*\+\s*\d+\s*$")

# Pre-populated cache — the solver calls `Effect.family` >1M times in a
# typical run, all on a few hundred distinct names. Memoizing cuts ~1.5 s
# off each solve (profiler showed 1.4 s in `re.sub`).
_FAMILY_CACHE: dict[str, str] = {}


def _family_key(name: str) -> str:
    cached = _FAMILY_CACHE.get(name)
    if cached is not None:
        return cached
    out = FAMILY_SUFFIX.sub("", name).strip()
    _FAMILY_CACHE[name] = out
    return out


CHAR_TAG = re.compile(r"^\[([A-Za-z ]+)\]")


def _character_tag(name: str) -> Optional[str]:
    m = CHAR_TAG.match(name)
    if not m:
        return None
    return m.group(1).strip()


@dataclass
class Effect:
    effect_id: int
    sort_index: int
    tier: str
    flag: str
    group: str
    name: str
    stackable: bool = False

    label: str = ""
    bucket: Optional[str] = None
    mult: float = 1.0
    mult_scope: str = "all"
    additive: float = 0.0
    additive_scope: str = "phys"
    requires: Optional[str] = None
    uptime_default: float = 1.0
    scaling_stat: Optional[str] = None
    utility_value: float = 0.0
    debuff_cost: float = 0.0
    character_compat: bool = True
    harmful: bool = False
    notes: str = ""
    csv_details: str = ""
    csv_relic: str = ""

    effect_text: str = ""
    category: str = ""
    stack_self: Optional[bool] = None
    stack_other: Optional[bool] = None
    unobtainable: bool = False
    is_dn_xlsx: bool = False
    parsed: dict[str, Any] = field(default_factory=dict)

    # Synergy annotation: mapping from an uptime key (ult_active, trance_active,
    # incant_buff_active…) to the fraction this effect contributes if it's in
    # the build. The damage model sums these across the build to derive the
    # effective uptime that ult-gated / trance-gated effects actually see —
    # this is what lets Glass Necklace + L525 pull Ult uptime to ~0.95 without
    # the user fiddling with the slider.
    uptime_boosts: dict[str, float] = field(default_factory=dict)

    def ce_string(self) -> str:
        sort = self.sort_index if self.sort_index >= 0 else "N/A"
        return (
            f"{self.effect_id} : {sort}|{self.tier}|{self.flag}|"
            f"{self.group}|{self.name}"
        )

    def is_curse(self) -> bool:
        return self.group == CURSE_GROUP

    def requires_debuff(self) -> bool:
        return self.flag == "Y"

    def is_damage_effect(self) -> bool:
        return self.mult > 1.0 or self.additive > 0.0 or self.utility_value > 0.0

    def display_label(self) -> str:
        return self.label or self.name

    @property
    def family(self) -> str:
        return _family_key(self.name)

    @property
    def character_tag(self) -> Optional[str]:
        return _character_tag(self.name)


@lru_cache(maxsize=1)
def _raw_ce_rows() -> list[dict[str, Any]]:
    with REGISTRY_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _enriched_rows() -> dict[str, dict[str, Any]]:
    """Load xlsx-derived enrichment keyed by str(effect_id). Missing file → empty."""
    if not ENRICHED_PATH.exists():
        return {}
    with ENRICHED_PATH.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return raw.get("effects", {}) if isinstance(raw, dict) else {}


_DAMAGE_SCOPE_MAP = {
    "physical": "phys", "magic": "magic", "fire": "fire",
    "lightning": "lightning", "holy": "holy",
}


def _auto_additive_from_parsed(parsed: dict[str, Any]) -> tuple[float, str]:
    """Heuristic: when a character has no override, use xlsx-parsed values so
    every character at least accounts for damage effects. Returns (additive,
    additive_scope) — additive is a fraction (0.105 = +10.5%)."""
    if not parsed:
        return 0.0, "phys"
    pct = parsed.get("damage_mult_pct")
    if pct is not None:
        scope = _DAMAGE_SCOPE_MAP.get(parsed.get("damage_scope", ""), "phys")
        return float(pct) / 100.0, scope
    pct = parsed.get("attack_power_mult_pct")
    if pct is not None:
        return float(pct) / 100.0, "all"
    pct = parsed.get("weapon_damage_mult_pct")
    if pct is not None:
        return float(pct) / 100.0, "phys"
    pct = parsed.get("generic_damage_mult_pct")
    if pct is not None:
        return float(pct) / 100.0, "phys"
    return 0.0, "phys"


def _auto_utility_from_parsed(parsed: dict[str, Any]) -> float:
    """Utility fallback when no character override exists.

    Gauge-boost and cooldown-reduction effects translate into small utility
    values proportional to how much more often they let you fire the
    affected ability. Conservative linear approximations."""
    if not parsed:
        return 0.0
    pct = parsed.get("gauge_boost_pct")
    if pct is not None:
        return min(0.20, float(pct) / 200.0)
    pct = parsed.get("cooldown_reduction_pct")
    if pct is not None:
        # 10% skill cooldown reduction roughly maps to ~5% more total damage
        # for characters with a Trance-like damage multiplier on skill.
        return min(0.15, float(pct) / 200.0)
    return 0.0


def _auto_uptime_boosts_from_parsed(parsed: dict[str, Any]) -> dict[str, float]:
    """Derive uptime_boosts from parsed prose when the character JSON didn't
    annotate them explicitly. Lets a generic 'Reduces skill cooldown by 10%'
    pump trance_active uptime for every character with a trance-style skill."""
    if not parsed:
        return {}
    out: dict[str, float] = {}
    pct = parsed.get("cooldown_reduction_pct")
    scope = parsed.get("cooldown_scope", "")
    if pct is not None:
        # Linear map: 10% cooldown reduction → +0.10 trance_active uptime.
        if scope in ("skill", ""):
            out["trance_active"] = min(0.35, float(pct) / 100.0)
        elif scope in ("art", "ultimate"):
            out["ult_active"] = min(0.35, float(pct) / 100.0)
    gauge = parsed.get("gauge_boost_pct")
    gauge_scope = parsed.get("gauge_boost_scope", "")
    if gauge is not None:
        # +10% gauge gain → ~+0.08 ult uptime (gauge fills faster → more casts).
        if gauge_scope in ("ultimate", "art"):
            out.setdefault("ult_active", min(0.30, float(gauge) / 125.0))
        elif gauge_scope in ("skill", "character skill"):
            out.setdefault("trance_active", min(0.30, float(gauge) / 125.0))
    return out


# Keyword → uptime-gate key. Effects whose names contain one of these
# substrings (case-insensitive) are conditional on the enemy having that
# status applied; we auto-inject `requires=<key>` so the damage model gates
# them via ctx.enemy_X_uptime. Defaults to 0 so "+20% vs poisoned enemy"
# only scores when the user flags their weapon/incant actually inflicts it.
# Ordered most-specific → least-specific so "greatsword" matches before "sword",
# "great hammer" before "hammer", etc. Keys are lowercase substrings that may
# appear inside effect names like "Improved Hammer Attack Power" or
# "Improved Attack Power with 3+ Hammers Equipped". Values are the weapon
# slugs declared in each character JSON's `weapon_types` list.
_WEAPON_NAME_PATTERNS: tuple[tuple[str, str], ...] = (
    ("colossal sword",          "colossal_sword"),
    ("colossal weapon",         "colossal_weapon"),
    ("curved greatsword",       "curved_greatsword"),
    ("curved sword",            "curved_sword"),
    ("heavy thrusting sword",   "heavy_thrusting_sword"),
    ("thrusting sword",         "thrusting_sword"),
    ("straight sword",          "straight_sword"),
    ("great hammer",            "greathammer"),
    ("great spear",             "great_spear"),
    ("great shield",            "great_shield"),
    ("greatshield",             "great_shield"),
    ("greatsword",              "greatsword"),
    ("greataxe",                "greataxe"),
    ("greatbow",                "greatbow"),
    ("twinblade",               "twinblade"),
    ("sacred seal",             "sacred_seal"),
    ("light bow",               "light_bow"),
    ("crossbow",                "crossbow"),
    ("ballista",                "ballista"),
    ("halberd",                 "halberd"),
    ("katana",                  "katana"),
    ("reaper",                  "reaper"),
    ("dagger",                  "dagger"),
    ("hammer",                  "hammer"),
    ("flail",                   "flail"),
    ("spear",                   "spear"),
    ("axe",                     "axe"),
    ("bow",                     "bow"),
    ("staff",                   "staff"),
    ("torch",                   "torch"),
    ("shield",                  "shield"),
    ("fist",                    "fist"),
    ("claw",                    "claw"),
    ("whip",                    "whip"),
)

# Membership aliases: weapons a character can equip under a broad category.
# e.g. raider has `colossal_weapon` which covers colossal sword + greataxe +
# great hammer (etc.) in-game. Avoids over-filtering for such multi-weapon
# kits.
_WEAPON_ALIAS: dict[str, tuple[str, ...]] = {
    "colossal_weapon":  ("colossal_sword", "greataxe", "greathammer", "colossal_weapon"),
    # "sword" could implicitly cover sword variants — but characters declare
    # specific classes, so we keep this minimal. Extend only if needed.
}


# Effects with these substrings in the name are considered noise for a
# pure-damage build and filtered out of the auto-pool. They split into three
# buckets so the solver can revive the right subset when the user's build
# goal weights demand it (e.g. Guardian tank wants element negation; Scholar
# support wants ally-only effects).
_PURE_FILLER_FRAGMENTS = (
    # Starter items / treasure utilities
    "in possession at start",
    "start of expedition",
    "helps discover",
    # Sorcery specializations (cast-class only)
    "glintblade sorcery",
    "carian sword sorcery",
    "stone sorcery",
    "glintstone sorcery",
    "night sorcery",
    "gravity sorcery",
    "fundamentalist sorcery",
    "crystalian sorcery",
    "invisibility sorcery",
    "magma sorcery",
    "loretta's sorcery",
    "primeval sorcery",
    # Incantation specializations (cast-class only)
    "bestial incantation",
    "dragon cult incantation",
    "giants' incantation",
    "fundamentalist incantation",
    "golden order incantation",
    "erdtree incantation",
    "fire monks' incantation",
    "servants of rot incantation",
    "black flame incantation",
    "frenzied flame incantation",
    "death incantation",
    "two fingers' incantation",
    # Throwable item damage — negligible compared to main weapon output
    "improved throwing knife",
    "improved throwing pot",
    "improved throwing",
    # Perfume / Aromatic (perfume-only playstyle)
    "perfuming arts",
    "improved aromatic",
    "aromatic bottle",
    # Map / jar items
    "improved stonesword key",
    "improved small pouch",
    # Economy / expedition utilities — no combat impact
    "rune discount",
    "rune gain",
    "improved rune",
    "reduced rune cost",
    "rune pickup",
    "runes and item discovery",
    "item discovery",
    "faster revival",
    "improved phantom",
    # Exploration / map reveal
    "map reveal",
    "reveal map",
    "treasure marked upon map",
    "marked upon map",
)

# Revived when build_goal_weights["survival"] > 0.05. These are legit tank
# effects (Guardian halberd+great-shield) that only confuse damage builds.
_SURVIVAL_SPECIFIC_FRAGMENTS = (
    "poison resistance",
    "scarlet rot resistance",
    "bleed resistance",
    "hemorrhage resistance",
    "frost resistance",
    "sleep resistance",
    "madness resistance",
    "death blight resistance",
    "death-blight resistance",
    "magic damage negation",
    "fire damage negation",
    "lightning damage negation",
    "holy damage negation",
    "physical damage negation",
    "affinity damage negation",
)

# Revived when build_goal_weights["team"] > 0.05. Revenant/Scholar support
# builds; useless to solo damage builds.
_TEAM_SPECIFIC_FRAGMENTS = (
    "for allies but not for self",
    "for allies but, but not",
    "for nearby allies but",
    "items confer effect to all nearby allies",
    "items confer effect",
    "restores hp for allies",
    "raised stamina recovery for nearby",
)

def _is_non_combat_filler(
    name: str,
    *,
    allow_survival: bool = False,
    allow_team: bool = False,
) -> bool:
    """True if the effect name is "noise" for the current build goal.

    Pure filler (rune pickup, item discovery, sorcery specializations) is
    always filtered. Element-specific damage negation is filtered unless the
    user cares about survival (Guardian tank). Ally-only effects are filtered
    unless the user cares about team support (Revenant/Scholar).
    """
    n = (name or "").lower()
    if any(frag in n for frag in _PURE_FILLER_FRAGMENTS):
        return True
    if not allow_survival and any(frag in n for frag in _SURVIVAL_SPECIFIC_FRAGMENTS):
        return True
    if not allow_team and any(frag in n for frag in _TEAM_SPECIFIC_FRAGMENTS):
        return True
    # Generic resistance buffs — pure defensive. Only filtered when the user
    # isn't asking for survival effects.
    if not allow_survival and "resistance" in n and "attack" not in n and "improved" in n:
        return True
    # HP restoration from items (medicinal boluses etc.) — pure sustain.
    # Kept filtered even for survival builds since it's item-gated, not
    # passive — pure noise for solver decisions.
    if "hp restored when using" in n or "hp restoration when using" in n:
        return True
    return False


# Effect name → playstyle tag. Characters opt into tags they actually use
# via `playstyle_tags` in their JSON. Effects matching a tag NOT in the
# character's list score 0 (filtered from auto-pool). Order matters — more
# specific phrases matched first.
_PLAYSTYLE_NAME_PATTERNS: tuple[tuple[str, str], ...] = (
    # Guard / block / shield
    ("successful guarding",      "guard"),
    ("upon guarding",            "guard"),
    ("upon blocking",            "guard"),
    ("successful guard",         "guard"),
    ("guard counter",            "guard"),
    ("improved guard",           "guard"),
    ("while guarding",           "guard"),
    ("while blocking",           "guard"),
    ("stamina guarding",         "guard"),
    ("focus guarding",           "guard"),
    # Critical hit / riposte / parry
    ("upon critical hit",        "crit"),
    ("upon riposte",             "crit"),
    ("critical hit boosts",      "crit"),
    ("critical damage",          "crit"),
    ("improved critical",        "crit"),
    ("parry",                    "crit"),
    # Stance / stance break
    ("stance break",             "stance"),
    ("stance breaking",          "stance"),
    ("improved stance",          "stance"),
    # Charged attacks
    ("charged attack",           "charged"),
    ("charged blow",             "charged"),
    ("improved charged",         "charged"),
    # Backstab
    ("backstab",                 "crit"),
    ("critical hit stamina",     "crit"),
    # Sorcery specializations — damage boosts that only matter for caster
    # characters. Tagging them "cast" so Undertaker/Guardian/etc. skip them.
    ("glintstone",               "cast"),
    ("gravity stone",            "cast"),
    ("gravity sorcery",          "cast"),
    ("carian sword",             "cast"),
    ("carian sorcery",           "cast"),
    ("crystalian sorcery",       "cast"),
    ("night sorcery",            "cast"),
    ("magma sorcery",            "cast"),
    ("loretta's sorcery",        "cast"),
    ("primeval sorcery",         "cast"),
    ("fundamentalist sorcery",   "cast"),
    ("invisibility sorcery",     "cast"),
    ("stone sorcery",            "cast"),
    ("glintblade",               "cast"),
    # Incantation specializations
    ("bestial incantation",      "cast"),
    ("dragon cult",              "cast"),
    ("giants' incantation",      "cast"),
    ("golden order incantation", "cast"),
    ("erdtree incantation",      "cast"),
    ("fire monks' incantation",  "cast"),
    ("servants of rot",          "cast"),
    ("black flame",              "cast"),
    ("frenzied flame",           "cast"),
    ("death incantation",        "cast"),
    ("two fingers' incantation", "cast"),
)


def _detect_playstyle_tag(name: str) -> Optional[str]:
    """Return the playstyle this effect requires, or None if universal.
    Used to skip guard-based / crit-based / stance-based effects for
    characters whose kit doesn't use those mechanics."""
    n = (name or "").lower()
    for needle, tag in _PLAYSTYLE_NAME_PATTERNS:
        if needle in n:
            return tag
    return None


def _playstyle_matches_tags(name: str, playstyle_tags: list[str],
                              char_weapons: list[str]) -> bool:
    """True if the effect's required playstyle (guard/crit/stance/…) is
    declared in `playstyle_tags`. Universal effects always pass."""
    tag = _detect_playstyle_tag(name)
    if tag is None:
        return True
    tags = set(playstyle_tags or [])
    if tags:
        return tag in tags
    # No explicit declaration → infer from weapons (backwards-compat).
    weapons = set(char_weapons or [])
    if tag == "guard":
        return bool(weapons & {"great_shield", "shield"})
    if tag == "crit":
        return bool(weapons & {"dagger","katana","curved_sword","bow","light_bow"})
    if tag == "charged":
        return bool(weapons & {"colossal_sword","colossal_weapon","greataxe","greathammer"})
    return bool(weapons & {
        "dagger","straight_sword","greatsword","colossal_sword","curved_sword",
        "curved_greatsword","katana","thrusting_sword","heavy_thrusting_sword",
        "axe","greataxe","hammer","greathammer","flail","spear","great_spear",
        "halberd","reaper","fist","claw","whip","twinblade","colossal_weapon",
    })


_WEAPON_ACTION_TRIGGERS = (
    "attack power", "damage", "equipped", "critical damage", "stance",
    "charged", "weapon", "counterattack", "counter attack",
    "guard counter", "attacks", "blow", "discover",
)


def _detect_weapon_slug(name: str) -> Optional[str]:
    """Extract the primary weapon class from an effect name if the name clearly
    refers to a weapon-type-specific action (damage, attacks, stance, equip,
    counterattacks, discovery…). Returns a slug that matches character
    `weapon_types`, or None if the effect is weapon-agnostic."""
    n = (name or "").lower()
    if not any(kw in n for kw in _WEAPON_ACTION_TRIGGERS):
        return None
    for needle, slug in _WEAPON_NAME_PATTERNS:
        if needle in n:
            return slug
    return None


def _weapon_effect_matches_character(name: str, weapon_types: list[str]) -> bool:
    """True if the effect either doesn't reference a weapon OR references one
    the character can actually equip. Unrecognised effects pass through."""
    slug = _detect_weapon_slug(name)
    if slug is None:
        # Sorcery/incantation effects: only useful for caster characters. A
        # hammer-only character (Undertaker) doesn't benefit from "Improved
        # Glintblade Sorcery" regardless of whether the solver sees it as
        # score=0.
        n = (name or "").lower()
        if "sorcery" in n or "incantation" in n:
            caster = any(w in weapon_types for w in ("staff", "sacred_seal"))
            return caster
        return True
    if not weapon_types:
        return True
    if slug in weapon_types:
        return True
    for owned in weapon_types:
        if slug in _WEAPON_ALIAS.get(owned, ()):
            return True
    return False


_AFFLICTION_TRIGGERS = (
    ("scarlet rot-afflicted", "enemy_scarlet_rot"),
    ("poison-afflicted",      "enemy_poisoned"),
    ("frostbite-afflicted",   "enemy_frostbite"),
    ("bleed-afflicted",       "enemy_bleed"),
    ("hemorrhage-afflicted",  "enemy_bleed"),
    ("sleeping",              "enemy_asleep"),
    ("mad",                   "enemy_madness"),   # "enemy maddened" etc.
    ("deathblight",           "enemy_deathblight"),
    ("death-blight",          "enemy_deathblight"),
)


def _detect_affliction_requires(name: str) -> Optional[str]:
    n = (name or "").lower()
    # Only gate "facing X-afflicted enemy" style attack-power effects —
    # not resistance effects, which are never conditional on the enemy.
    if "facing" not in n and "afflicted" not in n and "vicinity" not in n:
        return None
    for key, req in _AFFLICTION_TRIGGERS:
        if key in n:
            return req
    return None


def _apply_meta(row: dict[str, Any], meta: dict[str, Any],
                enriched: dict[str, Any]) -> Effect:
    # Character override wins; otherwise fall back to xlsx parsed numbers.
    meta_mult = meta.get("mult")
    meta_add = meta.get("additive")
    meta_util = meta.get("utility_value")
    parsed = enriched.get("parsed", {})
    if meta_add is None and meta_mult is None:
        auto_add, auto_scope = _auto_additive_from_parsed(parsed)
    else:
        auto_add, auto_scope = 0.0, "phys"
    auto_util = 0.0 if meta_util is not None else _auto_utility_from_parsed(parsed)
    # Auto-gate affliction-conditional effects unless the character meta
    # explicitly overrode `requires` already.
    requires = meta.get("requires")
    if requires is None:
        requires = _detect_affliction_requires(row.get("name", ""))

    return Effect(
        effect_id=row["effect_id"],
        sort_index=row["sort_index"],
        tier=row["tier"],
        flag=row["flag"],
        group=row["group"],
        name=row["name"],
        stackable=bool(row.get("stackable", False)),
        label=meta.get("label", ""),
        bucket=meta.get("bucket"),
        mult=float(meta_mult) if meta_mult is not None else 1.0,
        mult_scope=meta.get("mult_scope", "all"),
        additive=float(meta_add) if meta_add is not None else auto_add,
        additive_scope=meta.get("additive_scope", auto_scope if auto_add else "phys"),
        requires=requires,
        uptime_default=float(meta.get("uptime_default", 1.0)),
        scaling_stat=meta.get("scaling_stat"),
        utility_value=float(meta["utility_value"]) if meta.get("utility_value") is not None else auto_util,
        debuff_cost=float(meta.get("debuff_cost", 0.0)),
        harmful=bool(meta.get("harmful", False)),
        notes=meta.get("notes", ""),
        csv_details=row.get("csv_details", ""),
        csv_relic=row.get("csv_relic", ""),
        effect_text=enriched.get("effect_text", ""),
        category=enriched.get("category", ""),
        stack_self=enriched.get("stack_self"),
        stack_other=enriched.get("stack_other"),
        unobtainable=bool(enriched.get("unobtainable", False)),
        is_dn_xlsx=bool(enriched.get("is_dn", False)),
        parsed=parsed or {},
        uptime_boosts=dict(meta.get("uptime_boosts")
                           or _auto_uptime_boosts_from_parsed(parsed)),
    )


@lru_cache(maxsize=16)
def load_effects_for_character(character_id: str) -> list[Effect]:
    meta_map = chars_mod.merged_effects_meta(character_id)
    enriched_map = _enriched_rows()
    rows = _raw_ce_rows()
    out: list[Effect] = []
    for r in rows:
        eid_key = str(r["effect_id"])
        meta = meta_map.get(eid_key, {})
        enriched = enriched_map.get(eid_key, {})
        e = _apply_meta(r, meta, enriched)
        out.append(e)
    _promote_named_relic_effects(out, character_id)
    return out


def _promote_named_relic_effects(effects: list[Effect], character_id: str) -> None:
    """Upgrade ILLEGAL/N-A effects listed in verified named relics so the solver
    can place them when the user locks the relic.

    The CE roster marks many Remembrance/shop/boss relic-specific effects as
    tier=N/A, group=ILLEGAL because their roll mechanics are unknown. But they
    are real in-game effects, and if a verified named-relic bundle references
    them, the user must be able to lock that bundle. Promote them to a legal
    tier+group in-memory so can_accept() accepts them — the source data stays
    untouched.
    """
    by_id = {e.effect_id: e for e in effects}
    for relic in chars_mod.named_relics_for(character_id):
        if not relic.get("attrs_verified"):
            continue
        promoted_tier = "DoN" if relic.get("is_dn") else "STD"
        for eid in relic.get("attrs", []):
            e = by_id.get(int(eid))
            if e is None:
                continue
            if e.tier in ROLLABLE_TIERS and e.group in ATTRIBUTE_GROUPS:
                continue   # already rollable
            e.tier = promoted_tier
            if e.group not in ATTRIBUTE_GROUPS:
                is_damage = (e.mult > 1.0001) or (abs(e.additive) > 1e-6) or bool(e.bucket)
                e.group = "ATTACK" if is_damage else "NONE"
            if e.sort_index < 0:
                e.sort_index = e.effect_id % 1000


def character_compatible(eff: Effect, character_id: str) -> bool:
    char = chars_mod.get(character_id)
    tag = eff.character_tag
    if tag is None:
        return True
    return tag.lower() == char.tag.lower()


def effects_by_id_for_character(character_id: str) -> dict[int, Effect]:
    return {e.effect_id: e for e in load_effects_for_character(character_id)}


def character_candidates(
    character_id: str,
    *,
    weapon_types: Optional[list[str]] = None,
    playstyle_tags: Optional[list[str]] = None,
    include_harmful: bool = False,
    include_character_specific: bool = True,
    include_wrong_weapon: bool = False,
    build_goal_weights: Optional[dict] = None,
) -> list[Effect]:
    """Effects the solver may consider for this character.

    `character_compatible` already strips [Other-Character]-tagged effects
    (e.g. [Duchess] effects are invisible to Undertaker). The remaining
    [Own-Character]-tagged effects are legit game content carried by named
    relics the user can obtain — L525 Trance Loop, L521 Chain Final Blow,
    L520 Contact Allies for Undertaker, etc. They are NOT the same as
    `ILLEGAL` tier/group effects (which are truly unrollable).

    Filters still applied:
      · tier not in {STD, BTH, DoN}          (unrollable)
      · group not in ATTRIBUTE_GROUPS        (ILLEGAL / curse-only)
      · e.harmful                            (debuff side-effects)
      · weapon class mismatch                (e.g. "Axe Atk Power" for
                                              hammer-only character)
      · starter-item / discovery filler      (zero damage value)

    Toggles:
      · include_character_specific=False — legacy flag, for callers that
        explicitly want ONLY untagged effects. Default True so the solver
        picks character-unique synergies.
      · include_wrong_weapon=True — show off-class + filler (Edit dialog).
      · build_goal_weights={damage, survival, utility, team} — when non-zero
        survival/team weights are present, the filter revives the matching
        subset of defensive/ally-only effects (Guardian wants element
        negation; Revenant wants team heals).
    """
    pool = load_effects_for_character(character_id)
    # Weapons / playstyle filter: caller-provided override wins, otherwise
    # fall back to character JSON defaults.
    char_weapons: list[str] = []
    char_playstyle: list[str] = []
    # Resolve goal weights: caller override → character JSON default → zeros.
    goal_w: dict[str, float] = {"damage": 1.0, "survival": 0.0, "utility": 0.0, "team": 0.0}
    try:
        char = chars_mod.get(character_id)
        char_weapons = list(char.weapon_types or [])
        char_playstyle = list(char.globals_.get("playstyle_tags") or [])
        declared = char.globals_.get("build_goal_weights") or {}
        for k in goal_w:
            goal_w[k] = float(declared.get(k, goal_w[k]))
    except KeyError:
        pass
    if weapon_types is not None:
        char_weapons = list(weapon_types)
    if playstyle_tags is not None:
        char_playstyle = list(playstyle_tags)
    if build_goal_weights:
        for k in goal_w:
            if k in build_goal_weights:
                goal_w[k] = float(build_goal_weights[k])
    allow_survival = goal_w.get("survival", 0.0) > 0.05
    allow_team = goal_w.get("team", 0.0) > 0.05
    out = []
    for e in pool:
        if not character_compatible(e, character_id):
            continue
        if e.tier not in ROLLABLE_TIERS:
            continue
        if e.group not in ATTRIBUTE_GROUPS:
            continue
        if (not include_harmful) and e.harmful:
            continue
        if (not include_character_specific) and e.character_tag:
            continue
        if (not include_wrong_weapon) and not _weapon_effect_matches_character(
            e.name, char_weapons
        ):
            continue
        if (not include_wrong_weapon) and _is_non_combat_filler(
            e.name, allow_survival=allow_survival, allow_team=allow_team,
        ):
            continue
        # Playstyle gate: skip guard/crit/stance/charged effects when the
        # character's kit doesn't use them. Undertaker doesn't block →
        # "Art gauge on guard" is noise.
        if (not include_wrong_weapon) and not _playstyle_matches_tags(
            e.name, char_playstyle, char_weapons
        ):
            continue
        out.append(e)
    return out


def curses_for_character(character_id: str) -> list[Effect]:
    return [e for e in load_effects_for_character(character_id) if e.is_curse()]


def find_for_character(effect_id: int, character_id: str) -> Effect:
    return effects_by_id_for_character(character_id)[effect_id]



if __name__ == "__main__":
    from collections import Counter
    for char_id in ["undertaker", "wylder", "ironeye"]:
        cands = character_candidates(char_id)
        tagged = [e for e in cands if e.character_tag]
        print(f"{char_id}: {len(cands)} candidates, {len(tagged)} char-tagged")
        for e in tagged[:5]:
            print(f"  {e.ce_string()}")
