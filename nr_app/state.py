"""Reflex State: single source of truth for the optimizer UI.

Reflex serialises state over the wire on every event, so we use primitive
types (dicts keyed by strings, lists of ints) instead of tuples/sets.
Backend calls (`optimize`) are invoked inside event handlers and the
resulting build is cached into `build_slots` (list of dicts) for rendering.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any, Optional

import reflex as rx

from src import buffs as buffs_mod
from src import characters as chars_mod
from src import presets as presets_mod
from src import stats as stats_mod
from src.constraints import MODE_DEEP_NIGHT, MODE_STANDARD
from dataclasses import fields as _dc_fields
from src.damage_model import PlayContext, compute as _compute_contrib, naked_baseline
from src.defensive_stats import compute_defensive_stats
from src.effects_db import is_bundle_only_effect
from src.effects_db import (
    Effect,
    character_candidates,
    curses_for_character,
    effects_by_id_for_character,
    find_for_character,
)
from src.solver import OptimizerConfig, optimize, per_attr_contributions, top_k_alternatives
from src.validator import auto_sort, is_valid as relic_is_valid, validate_relic

CUSTOM_VESSEL = "__custom__"


_PLAY_CTX_FIELD_NAMES = {f.name for f in _dc_fields(PlayContext)}


def _migrated_preset_scores(p: presets_mod.Preset) -> dict[str, float]:
    """Presets saved before the multi-objective scoring lived on disk show
    `survival/utility/team/weighted = 0`. Detect that case and recompute
    the missing axes on the fly from the preset's stored attrs + ctx, so
    the My Builds / Compare tabs display honest values without requiring
    the user to re-save. Pure read-side migration; the JSON is untouched."""
    if (p.survival_score or p.utility_score or p.team_score
            or (p.weighted_score and p.weighted_score != p.total_boss_window)):
        return {
            "damage": p.damage_score or p.total_boss_window,
            "survival": p.survival_score,
            "utility": p.utility_score,
            "team": p.team_score,
            "weighted": p.weighted_score or p.total_boss_window,
        }
    try:
        eff_ids = effects_by_id_for_character(p.character_id)
        effects = [
            eff_ids[int(eid)]
            for s in p.slots for eid in s.attr_ids
            if int(eid) in eff_ids
        ]
        ctx_kwargs = {k: v for k, v in (p.ctx or {}).items()
                       if k in _PLAY_CTX_FIELD_NAMES}
        ctx = PlayContext(**ctx_kwargs)
        contrib = _compute_contrib(effects, ctx=ctx, character_id=p.character_id)
        return {
            "damage": contrib.damage_score,
            "survival": contrib.survival_score,
            "utility": contrib.utility_score,
            "team": contrib.team_score,
            "weighted": contrib.weighted_score,
        }
    except Exception:
        return {
            "damage": p.total_boss_window,
            "survival": 0.0, "utility": 0.0, "team": 0.0,
            "weighted": p.total_boss_window,
        }


# ── playstyle defaults — kept in one place so the reset buttons stay truthful ──
PLAYSTYLE_DEFAULTS: dict[str, float | int | bool] = {
    "evergaol_clears":   6,
    "invader_kills":     2,
    "grease_uptime":     0.75,
    "trance_uptime":     0.50,
    "ult_uptime":        0.35,
    "incant_uptime":     0.0,
    "took_damage_uptime": 0.70,
    "chain_last_hit":    0.25,
    "first_combo_hit":   0.25,
    "three_hammers":     True,
    "dual_wielding":     True,
    # Afflictions default off — only count "damage vs X-afflicted enemy" bonuses
    # when the user explicitly sets uptime (weapon coats / status incantations).
    "enemy_poisoned_uptime":    0.0,
    "enemy_scarlet_rot_uptime": 0.0,
    "enemy_frostbite_uptime":   0.0,
    "enemy_bleed_uptime":       0.0,
    "enemy_asleep_uptime":      0.0,
    "enemy_madness_uptime":     0.0,
    "enemy_deathblight_uptime": 0.0,
}


def _k(slot: int, attr: int) -> str:
    return f"{slot},{attr}"


def _unk(k: str) -> tuple[int, int]:
    s, a = k.split(",")
    return int(s), int(a)


class AttrRow(rx.Base):
    id: int = 0
    sort: int = -1
    tier: str = ""
    flag: str = ""
    group: str = ""
    name: str = ""
    family: str = ""
    character_tag: str = ""
    effect_text: str = ""
    category: str = ""
    # Marginal contribution of this specific attr to the weighted score
    # (populated by recompute via solver.per_attr_contributions). Drives the
    # "Why this effect?" pill on the attr row. 0 for fixed/legacy rows.
    contribution: float = 0.0
    # Per-axis breakdown — the tooltip shows damage/survival/utility/team
    # deltas so the user can tell whether a "+1.5" pill comes from damage
    # (good for DPS) or survival (a defensive effect, not damage).
    contrib_damage: float = 0.0
    contrib_survival: float = 0.0
    contrib_utility: float = 0.0
    contrib_team: float = 0.0
    # Dominant axis — drives the pill's background color so defense effects
    # don't look like damage pills.
    contrib_axis: str = "damage"
    # How much the engine actually knows about this effect's numeric value:
    #   "modeled"  — bucket / mult / additive / utility_value declared
    #   "textual"  — value only present in effect_text (e.g. "Increases … by 20%")
    #   "flat"     — no numeric value at all (flavour / informational)
    # Drives whether the slot pill shows a colored delta, a grey info hint, or
    # nothing — so the user never wonders "why no pill?".
    contrib_status: str = "flat"


class SlotData(rx.Base):
    index: int = 0
    name: str = ""
    color_hint: str = ""
    tiers: list[str] = []
    is_fixed: bool = False
    vessel_color: str = ""
    attrs: list[AttrRow] = []
    locked_labels: list[str] = []
    debuff: Optional[AttrRow] = None
    needs_debuff: bool = False
    named_relic_id: str = ""
    # Validation errors against canonical relic rules (duplicate ids, roll
    # groups, debuff missing, tier mismatch, character tag). Empty list → valid.
    # Drives the ⚠ badge in the slot header.
    validation_errors: list[str] = []
    validation_tooltip: str = ""


class BucketStat(rx.Base):
    name: str = ""
    value: float = 1.0


class CharStat(rx.Base):
    abbr: str = ""
    val: str = ""


class EffectiveStatRow(rx.Base):
    """One stat: base grade, effective grade, raw delta — for display + radar."""
    abbr: str = ""           # "STR"
    stat: str = ""           # "strength"
    base_grade: str = "D"
    base_raw: int = 0
    grade: str = "D"
    raw: int = 0
    delta: int = 0
    base_value: float = 1.0  # numeric grade (1-5) for radar — before relics
    value: float = 1.0       # numeric grade after relics


class PresetSlotRow(rx.Base):
    """One slot snapshot from a saved preset — effect IDs + names for display."""
    index: int = 0
    name: str = ""                     # "Slot 1 — Glass Necklace (Remembrance)"
    vessel_color: str = ""             # R|G|B|Y|U|"" (colour of the vessel slot)
    attr_ids: list[int] = []
    attr_names: list[str] = []         # parallel to attr_ids
    debuff_id: int = 0
    debuff_name: str = ""


class PresetRow(rx.Base):
    name: str = ""
    score: float = 0.0
    mode: str = ""
    date: str = ""
    character_id: str = ""
    character_name: str = ""
    character_icon: str = ""
    vessel_name: str = ""              # e.g. "Undertaker's Chalice" or "— no vessel —"
    vessel_colors: list[str] = []      # per-slot vessel colours for accent pills
    slots: list[PresetSlotRow] = []
    # Pre-computed metrics so the compare-tab bar chart doesn't need to re-solve.
    hammer_mult: float = 1.0
    hex_mult: float = 1.0
    utility_mult: float = 1.0
    additive_phys_pct: float = 0.0
    trance_uptime_pct: float = 0.0
    # Multi-objective scores for the 4-axis comparison chart + build-type tag.
    damage_score: float = 0.0
    survival_score: float = 0.0
    utility_score: float = 0.0
    team_score: float = 0.0
    weighted_score: float = 0.0
    build_type: str = "DPS build"      # dominant axis at save time


class NamedRelicRow(rx.Base):
    id: str = ""
    name: str = ""
    color: str = "U"
    source: str = ""                # legacy (deprecated — use source_type)
    source_type: str = ""           # remembrance | shop | boss_standard | boss_everdark | boss_dlc | other
    source_detail: str = ""         # human-readable "where" string
    character: str = ""
    description: str = ""
    verified: bool = False
    attrs: list[int] = []
    # True when the relic carries at least one effect that's not available
    # from normal rolls (N/A tier / ILLEGAL group promoted in memory). Drives
    # the "includes unrollable effects" badge in the picker.
    has_bundle_only: bool = False


class EditOption(rx.Base):
    id: int = 0
    sort: int = -1
    tier: str = ""
    flag: str = ""
    group: str = ""
    name: str = ""
    family: str = ""
    character_tag: str = ""
    utility: float = 0.0
    mult: float = 1.0
    additive: float = 0.0
    effect_text: str = ""
    category: str = ""


class ValidationRow(rx.Base):
    rule: str = ""
    ok: bool = True
    severity: str = "info"
    message: str = ""


class DefensiveRow(rx.Base):
    """One row of the defensive-stats table: label + numeric value + unit.
    Typed so Reflex knows `value` is a float for comparisons in templates."""
    label: str = ""
    value: float = 0.0
    unit: str = ""
    group: str = "body"


class AffinityRow(rx.Base):
    label: str = ""
    value: float = 0.0


class DormantPowerRow(rx.Base):
    id: int = 0
    description: str = ""
    formatted: str = ""       # effect_template rendered at selected tier
    category: str = ""
    tier: int = 0             # 0 = not picked, 1 = tier 1, 2 = tier 2
    max_tier: int = 1
    is_damage: bool = False


_TEXT_PCT_RE = re.compile(r"by\s*(\d+(?:\.\d+)?)\s*%", re.I)
_TEXT_FLAT_RE = re.compile(
    r"(?:by|restores?|raises?|increases?|reduces?)\s*(\d+(?:\.\d+)?)\b", re.I
)


def _classify_contrib_status(e: Effect) -> str:
    """Decide how backed-by-data the effect's value is. Mirrors the priority
    order used by `damage_model._effect_value_proxy`."""
    if (
        e.bucket
        or (e.mult or 1.0) > 1.0
        or (e.additive or 0.0) > 0.0
        or (e.utility_value or 0.0) > 0.0
    ):
        return "modeled"
    txt = (getattr(e, "effect_text", "") or "")
    if txt and (_TEXT_PCT_RE.search(txt) or _TEXT_FLAT_RE.search(txt)):
        return "textual"
    return "flat"


def _attr_row(e: Effect, contrib_info: dict | float = 0.0) -> AttrRow:
    """Build an AttrRow. `contrib_info` can be a float (legacy scalar) or a
    dict with per-axis breakdown {weighted, damage, survival, utility, team}
    — the dict form populates the tooltip showing WHICH axis the
    contribution came from."""
    if isinstance(contrib_info, dict):
        w = float(contrib_info.get("weighted", 0.0))
        cd = float(contrib_info.get("damage", 0.0))
        cs = float(contrib_info.get("survival", 0.0))
        cu = float(contrib_info.get("utility", 0.0))
        ct = float(contrib_info.get("team", 0.0))
        # Dominant axis = largest absolute axis contribution (for pill colour).
        parts = {"damage": cd, "survival": cs, "utility": cu, "team": ct}
        axis = max(parts.items(), key=lambda kv: abs(kv[1]))[0] if w != 0 else "damage"
    else:
        w = float(contrib_info)
        cd = cs = cu = ct = 0.0
        axis = "damage"
    return AttrRow(
        id=e.effect_id,
        sort=e.sort_index if e.sort_index >= 0 else -1,
        tier=e.tier,
        flag=e.flag,
        group=e.group,
        name=e.name,
        family=e.family,
        character_tag=e.character_tag or "",
        effect_text=getattr(e, "effect_text", "") or "",
        category=getattr(e, "category", "") or "",
        contribution=round(w, 2),
        contrib_damage=round(cd, 2),
        contrib_survival=round(cs, 2),
        contrib_utility=round(cu, 2),
        contrib_team=round(ct, 2),
        contrib_axis=axis,
        contrib_status=_classify_contrib_status(e),
    )


def _edit_option(e: Effect) -> EditOption:
    return EditOption(
        id=e.effect_id,
        sort=e.sort_index if e.sort_index >= 0 else -1,
        tier=e.tier,
        flag=e.flag,
        group=e.group,
        name=e.name,
        family=e.family,
        character_tag=e.character_tag or "",
        utility=e.utility_value,
        mult=e.mult,
        additive=e.additive,
        effect_text=getattr(e, "effect_text", "") or "",
        category=getattr(e, "category", "") or "",
    )


class State(rx.State):
    # ── identity ──────────────────────────────────────────────────
    character_id: str = "undertaker"
    mode: str = MODE_DEEP_NIGHT

    # ── vessel ────────────────────────────────────────────────────
    vessel_id: str = ""                                    # "" = none
    custom_vessel_colors: list[str] = ["U", "U", "U", "U", "U", "U"]

    # ── playstyle / weapons override ──────────────────────────────
    # Empty list means "use character JSON defaults". Letting the user edit
    # these lets them theorycraft off-meta builds (DEX Undertaker with
    # daggers, guard-focused Wylder, etc.).
    weapon_types_override: list[str] = []
    playstyle_tags_override: list[str] = []
    # Per-stat damage scaling weight override. Empty dict → use character
    # JSON's `damage_scaling`. Keys are stat slugs (strength, faith, …).
    damage_scaling_override: dict[str, float] = {}
    # Multi-objective build goal override. Empty dict → use character JSON's
    # `build_goal_weights`. Keys: damage / survival / utility / team. Lets
    # user steer the solver toward tank/support/utility even for characters
    # that default to pure damage.
    build_goal_weights_override: dict[str, float] = {}
    # Team composition — character ids of OTHER members (not the active
    # character). Drives the party-synergy filter: effects that reference
    # another character's kit (e.g. "near Totem Stela" = Raider ult) are
    # only shown to the solver when that character is in the team.
    # Empty = solo play. Up to 2 entries (3-player team including self).
    party_members_override: list[str] = []

    # ── playstyle context ─────────────────────────────────────────
    evergaol_clears: int = 6
    invader_kills: int = 2
    grease_uptime: float = 0.75
    trance_uptime: float = 0.50
    ult_uptime: float = 0.35
    incant_uptime: float = 0.0
    took_damage_uptime: float = 0.70
    chain_last_hit: float = 0.25
    first_combo_hit: float = 0.25
    three_hammers: bool = True
    dual_wielding: bool = True
    # Enemy afflictions (set > 0 only if your weapon/incant actually applies
    # the status — otherwise "damage vs X-afflicted enemy" relics score zero).
    enemy_poisoned_uptime: float = 0.0
    enemy_scarlet_rot_uptime: float = 0.0
    enemy_frostbite_uptime: float = 0.0
    enemy_bleed_uptime: float = 0.0
    enemy_asleep_uptime: float = 0.0
    enemy_madness_uptime: float = 0.0
    enemy_deathblight_uptime: float = 0.0

    # ── solver constraints ────────────────────────────────────────
    excluded_ids: list[int] = []
    locked_picks: dict[str, int] = {}           # "slot,attr" → effect_id
    debuff_picks: dict[str, int] = {}           # slot_idx (str) → curse effect_id
    dormant_picks: dict[str, int] = {}          # buff_id (str) → tier (1|2)

    # ── UI preferences ───────────────────────────────────────────
    show_charts: bool = True

    # Seed the stochastic solver uses. 0 = deterministic default path.
    # "Try variant" bumps this to a random int so SA explores a different
    # corner of the search space — useful when the user wants to see a
    # near-optimal alternative build.
    explore_seed: int = 0

    # Bumped on save/delete so @rx.var saved_presets re-reads the JSON file.
    # Without this, Reflex caches the first call and later saves never show up.
    preset_version: int = 0

    # ── computed build cache (populated by recompute()) ───────────
    build_slots: list[SlotData] = []
    damage_total: float = 0.0
    hammer_mult: float = 1.0
    hex_mult: float = 1.0
    additive_phys_pct: float = 0.0
    utility_mult: float = 1.0
    skill_uptime_pct: float = 0.0
    bucket_report: list[BucketStat] = []
    # Multi-objective breakdown from damage_model — populated each solve.
    survival_score: float = 0.0
    utility_score: float = 0.0
    team_score: float = 0.0
    weighted_score: float = 0.0

    # ── dialogs ───────────────────────────────────────────────────
    edit_dialog_open: bool = False
    edit_slot_idx: int = -1
    edit_attr_idx: int = -1
    edit_search: str = ""
    edit_group_filter: str = "All"

    named_dialog_open: bool = False
    named_slot_idx: int = -1
    named_source_filter: str = "all"   # all|remembrance|shop|boss_standard|boss_everdark|boss_dlc|other

    debuff_dialog_open: bool = False
    debuff_slot_idx: int = -1

    preset_dialog_open: bool = False
    preset_name_input: str = ""

    # ── tabs ──────────────────────────────────────────────────────
    active_tab: str = "optimizer"

    # ── validator state ───────────────────────────────────────────
    v_slot_tier: str = "common"                 # 'common' | 'deep' | 'none'
    v_attr_ids: list[int] = [0, 0, 0]
    v_debuff_id: int = 0
    v_search: list[str] = ["", "", ""]

    # ═════════════════════════════════════════════════════════════
    # DERIVED
    # ═════════════════════════════════════════════════════════════
    @rx.var
    def naked_baseline_score(self) -> float:
        """Damage score with 0 relics, under the current playstyle context.
        Used to normalise the hero damage number into a multiplier over
        bare-weapon baseline — makes it obvious the score is relative, not
        absolute HP damage."""
        return round(naked_baseline(self.character_id, ctx=self._ctx()), 2)

    @rx.var
    def damage_baseline_mult(self) -> float:
        """How many times harder the current build hits vs a naked character.
        Example: 84.37 / 29.43 ≈ 2.87× naked damage."""
        b = naked_baseline(self.character_id, ctx=self._ctx())
        if b <= 0:
            return 0.0
        return round(self.damage_total / b, 2)

    @rx.var
    def all_weapon_slugs(self) -> list[str]:
        return [
            "dagger", "straight_sword", "greatsword", "colossal_sword",
            "curved_sword", "curved_greatsword", "katana", "thrusting_sword",
            "heavy_thrusting_sword", "twinblade", "axe", "greataxe",
            "hammer", "greathammer", "flail", "spear", "great_spear",
            "halberd", "reaper", "fist", "claw", "whip",
            "colossal_weapon",
            "bow", "light_bow", "greatbow", "crossbow", "ballista",
            "staff", "sacred_seal", "torch", "shield", "great_shield",
        ]

    @rx.var
    def all_playstyle_tags(self) -> list[str]:
        return [
            "melee", "ranged", "cast", "guard", "crit",
            "stance", "charged", "successive", "trance_loop",
        ]

    @rx.var
    def effective_weapon_types(self) -> list[str]:
        """Weapons actually used by the solver: user override, else char default."""
        if self.weapon_types_override:
            return list(self.weapon_types_override)
        try:
            return list(chars_mod.get(self.character_id).weapon_types or [])
        except KeyError:
            return []

    @rx.var
    def effective_playstyle_tags(self) -> list[str]:
        if self.playstyle_tags_override:
            return list(self.playstyle_tags_override)
        try:
            return list(chars_mod.get(self.character_id).globals_.get("playstyle_tags") or [])
        except KeyError:
            return []

    @rx.var
    def playstyle_is_customized(self) -> bool:
        return (
            bool(self.weapon_types_override)
            or bool(self.playstyle_tags_override)
            or bool(self.damage_scaling_override)
            or bool(self.build_goal_weights_override)
        )

    @rx.var
    def effective_build_goal_weights(self) -> dict[str, float]:
        """Final weights used by the solver: override → JSON default →
        safe fallback. Four axes: damage / survival / utility / team."""
        if self.build_goal_weights_override:
            out = {k: float(self.build_goal_weights_override.get(k, 0.0))
                   for k in ("damage", "survival", "utility", "team")}
            return out
        try:
            declared = chars_mod.get(self.character_id).globals_.get("build_goal_weights") or {}
        except KeyError:
            declared = {}
        return {
            "damage": float(declared.get("damage", 1.0)),
            "survival": float(declared.get("survival", 0.2)),
            "utility": float(declared.get("utility", 0.3)),
            "team": float(declared.get("team", 0.0)),
        }

    @rx.var
    def build_goal_is_customized(self) -> bool:
        return bool(self.build_goal_weights_override)

    @rx.var
    def dominant_goal(self) -> str:
        """Which axis dominates the weighted score in the current build.
        Used to tag presets/hero with "DPS / Tank / Support / Utility"."""
        if self.weighted_score <= 0:
            return "damage"
        w = self.effective_build_goal_weights
        # Weighted contribution per axis, normalised so we can compare.
        contribs = {
            "damage": self.damage_total * w["damage"],
            "survival": self.survival_score * w["survival"],
            "utility": self.utility_score * w["utility"],
            "team": self.team_score * w["team"],
        }
        return max(contribs.items(), key=lambda kv: kv[1])[0]

    @rx.var
    def effective_party(self) -> list[str]:
        """Self + other party members, de-duped + cleaned. Drives the
        solver's party-synergy gate and the sidebar's team section."""
        out = [self.character_id]
        for m in self.party_members_override:
            if m and m != self.character_id and m not in out:
                out.append(m)
        return out[:3]   # max 3-player party

    @rx.var
    def party_size(self) -> int:
        return len(self.effective_party)

    @rx.var
    def party_slot_ids(self) -> list[str]:
        """Up to 2 optional team-mate slots (indices 0 and 1)."""
        raw = list(self.party_members_override)
        while len(raw) < 2:
            raw.append("")
        return raw[:2]

    @rx.var
    def dominant_goal_label(self) -> str:
        return {
            "damage": "DPS build",
            "survival": "Tank build",
            "utility": "Utility build",
            "team": "Support build",
        }.get(self.dominant_goal, "DPS build")

    @rx.var
    def effective_damage_scaling(self) -> dict[str, float]:
        """What the damage model actually uses: override or JSON default."""
        if self.damage_scaling_override:
            return dict(self.damage_scaling_override)
        try:
            return dict(chars_mod.get(self.character_id).globals_.get("damage_scaling", {}) or {})
        except KeyError:
            return {}

    @rx.var
    def stat_scaling_rows(self) -> list[dict[str, Any]]:
        """Rows used by the sidebar: one per stat with current weight."""
        eff = self.effective_damage_scaling
        order = ["strength", "dexterity", "intelligence", "faith",
                 "arcane", "vigor", "mind", "endurance"]
        abbr = {"strength": "STR", "dexterity": "DEX", "intelligence": "INT",
                "faith": "FAI", "arcane": "ARC", "vigor": "VGR",
                "mind": "MND", "endurance": "END"}
        return [
            {"stat": s, "abbr": abbr[s], "weight": float(eff.get(s, 0.0))}
            for s in order
        ]

    @rx.var
    def character_name(self) -> str:
        return chars_mod.get(self.character_id).name

    @rx.var
    def character_icon(self) -> str:
        return chars_mod.get(self.character_id).icon

    @rx.var
    def character_tagline(self) -> str:
        return chars_mod.get(self.character_id).tagline

    @rx.var
    def character_is_full(self) -> bool:
        return chars_mod.get(self.character_id).is_fully_tuned

    @rx.var
    def character_stats_flat(self) -> list[CharStat]:
        c = chars_mod.get(self.character_id)
        order = [("str", "strength"), ("dex", "dexterity"), ("int", "intelligence"),
                 ("fai", "faith"),     ("arc", "arcane"),   ("vgr", "vigor"),
                 ("end", "endurance"), ("mnd", "mind")]
        return [CharStat(abbr=a.upper(), val=c.stats.get(k, "?")) for a, k in order]

    @rx.var
    def defensive_stats(self) -> dict[str, Any]:
        """Defensive / utility roll-up from the current build — damage
        negation per element, status resistance, max HP, poise, affinity
        attack per element. Derived from active effect IDs via regex-parsing
        effect names + effect_text. Drives the 'Defense & Affinity' panel."""
        active_ids: list[int] = []
        for slot in self.build_slots:
            for a in slot.attrs:
                active_ids.append(int(a.id))
            if slot.debuff is not None:
                active_ids.append(int(slot.debuff.id))
        return compute_defensive_stats(active_ids, self.character_id)

    @rx.var
    def defensive_rows(self) -> list[DefensiveRow]:
        """Flat list of DefensiveRow for the UI table. Typed as rx.Base so
        the template can do numeric comparisons on `value` directly."""
        s = self.defensive_stats
        rows: list[DefensiveRow] = []
        rows.append(DefensiveRow(label="Max HP",
                                  value=float(s.get("max_hp_pct", 0)),
                                  unit="%", group="body"))
        rows.append(DefensiveRow(label="Poise (stance)",
                                  value=float(s.get("poise_pct", 0)),
                                  unit="%", group="body"))
        neg = s.get("damage_negation", {}) or {}
        for key, label in [("physical", "Physical"), ("magic", "Magic"),
                           ("fire", "Fire"), ("lightning", "Lightning"),
                           ("holy", "Holy")]:
            rows.append(DefensiveRow(label=label + " negation",
                                      value=float(neg.get(key, 0)),
                                      unit="%", group="elemental"))
        res = s.get("status_resistance", {}) or {}
        for key, label in [("poison", "Poison"), ("scarlet_rot", "Scarlet Rot"),
                           ("bleed", "Bleed"), ("frost", "Frost"),
                           ("sleep", "Sleep"), ("madness", "Madness"),
                           ("deathblight", "Death Blight")]:
            rows.append(DefensiveRow(label=label,
                                      value=float(res.get(key, 0)),
                                      unit="", group="status"))
        return rows

    @rx.var
    def affinity_attack_rows(self) -> list[AffinityRow]:
        """Per-element attack power bonus from the current build."""
        aff = (self.defensive_stats or {}).get("affinity_attack", {})
        return [
            AffinityRow(label="Holy",      value=float(aff.get("holy", 0))),
            AffinityRow(label="Magic",     value=float(aff.get("magic", 0))),
            AffinityRow(label="Fire",      value=float(aff.get("fire", 0))),
            AffinityRow(label="Lightning", value=float(aff.get("lightning", 0))),
        ]

    @rx.var
    def effective_stats(self) -> list[EffectiveStatRow]:
        """Base grades + relic-driven deltas, projected onto a numeric 1-5 scale
        for the radar chart. Uses only effect IDs currently in `build_slots`."""
        c = chars_mod.get(self.character_id)
        active_ids: list[int] = []
        for slot in self.build_slots:
            for a in slot.attrs:
                active_ids.append(a.id)
            if slot.debuff is not None:
                active_ids.append(slot.debuff.id)
        effective = stats_mod.compute_effective_stats(c.stats, active_ids)

        rows: list[EffectiveStatRow] = []
        for stat in stats_mod.STAT_ORDER:
            data = effective.get(stat, {})
            base_grade = data.get("base_grade", "D")
            grade = data.get("grade", "D")
            base_raw = int(data.get("base_raw", 0))
            raw = int(data.get("raw", 0))
            rows.append(EffectiveStatRow(
                abbr=stats_mod.STAT_ABBR[stat],
                stat=stat,
                base_grade=base_grade,
                base_raw=base_raw,
                grade=grade,
                raw=raw,
                delta=int(data.get("delta", 0)),
                # Fractional numeric: interpolates within a grade tier so
                # small deltas (e.g. +3 Strength on a C-grade character)
                # visibly move the radar axis even if the letter doesn't flip.
                base_value=round(stats_mod.raw_to_numeric_fractional(stat, base_raw), 3),
                value=round(stats_mod.raw_to_numeric_fractional(stat, raw), 3),
            ))
        return rows

    @rx.var
    def effective_stats_chart_data(self) -> list[dict[str, Any]]:
        """Plain-dict projection for recharts.RadarChart (which rejects
        typed rx.Base collections even when field names align)."""
        return [
            {
                "abbr": r.abbr,
                "value": r.value,
                "base_value": r.base_value,
                "grade": r.grade,
                "base_grade": r.base_grade,
                "delta": r.delta,
            }
            for r in self.effective_stats
        ]

    @rx.var
    def locked_effects_per_slot(self) -> list[list[int]]:
        """For each slot (0..5), the set of effect IDs currently locked in that
        slot — independent of attr-position. The UI uses this to show the
        LOCKED badge on the correct visual row after sort_index re-ordering."""
        out: list[list[int]] = [[], [], [], [], [], []]
        for k, eid in self.locked_picks.items():
            try:
                s = int(k.split(",")[0])
            except (ValueError, IndexError):
                continue
            if 0 <= s < len(out):
                out[s].append(int(eid))
        return out

    @rx.var
    def locked_keys_by_slot(self) -> list[list[int]]:
        """Per-slot list of locked attr_idx positions. Enables exact-position
        lock icon display (as opposed to effect_id based) so each row's icon
        toggles independently — critical for builds with duplicate effects
        (e.g. 3× Physical Attack +4 locked at different positions)."""
        out: list[list[int]] = [[], [], [], [], [], []]
        for k in self.locked_picks:
            try:
                s, a = k.split(",")
                si = int(s); ai = int(a)
            except (ValueError, IndexError):
                continue
            if 0 <= si < len(out):
                out[si].append(ai)
        return out

    @rx.var
    def slot_lock_state(self) -> list[str]:
        """Per-slot lock state: "none" | "partial" | "full". Drives the
        header Lock button's icon and color. Parallel to build_slots."""
        counts_per_slot = self.locked_effects_per_slot
        out: list[str] = []
        for i, slot in enumerate(self.build_slots):
            total = len(slot.attrs)
            locked = len(counts_per_slot[i]) if i < len(counts_per_slot) else 0
            if total == 0:
                out.append("none")
            elif locked >= total:
                out.append("full")
            elif locked > 0:
                out.append("partial")
            else:
                out.append("none")
        return out

    @rx.var
    def bucket_label_map(self) -> dict[str, str]:
        """Map internal bucket keys (B_L18, B_GREASE, …) to human-readable names.
        Delegates to `chars_mod.bucket_labels_for` which is lru_cached by
        character_id — avoids re-running regex on every recompute tick."""
        return chars_mod.bucket_labels_for(self.character_id)

    @rx.var
    def mult_stack_data(self) -> list[dict[str, Any]]:
        """Horizontal bar chart data: each bucket's % contribution above 1.0.
        Bucket keys are replaced with human-readable labels."""
        label_map = self.bucket_label_map
        rows: list[dict[str, Any]] = []
        for b in self.bucket_report:
            label = label_map.get(b.name, b.name)
            rows.append({
                "name": label,
                "value": round((b.value - 1.0) * 100, 1),
                "mult": b.value,
            })
        if self.utility_mult > 1.0:
            rows.append({
                "name": "Utility (skill uptime)",
                "value": round((self.utility_mult - 1.0) * 100, 1),
                "mult": self.utility_mult,
            })
        if self.additive_phys_pct > 0:
            rows.append({
                "name": "Additive physical",
                "value": round(self.additive_phys_pct, 1),
                "mult": 1.0 + self.additive_phys_pct / 100.0,
            })
        rows = [r for r in rows if r["value"] > 0.01]
        rows.sort(key=lambda r: -r["value"])
        return rows

    @rx.var
    def has_stat_shifts(self) -> bool:
        return any(r.grade != r.base_grade for r in self.effective_stats)

    @rx.var
    def damage_sources_with_colors(self) -> list[dict[str, Any]]:
        """Pie chart data with fill colours embedded — recharts Cell lookup."""
        data = self.damage_sources_data
        palette = ["#cba6f7", "#94e2d5", "#89b4fa", "#fab387"]   # mauve/teal/blue/peach
        return [
            {**row, "fill": palette[i % len(palette)]}
            for i, row in enumerate(data)
        ]

    @rx.var
    def damage_sources_data(self) -> list[dict[str, Any]]:
        """Pie chart data: hammer / hex relative share of total damage.
        Approximation from the exposed top-level mults + per-character rates."""
        c = chars_mod.get(self.character_id)
        g = c.globals_
        hammer_rate = float(g.get("hammer_hits_per_boss_window_s", 0.8))
        hex_rate = float(g.get("hex_casts_per_boss_window_s", 0.22))
        hex_coef = float(g.get("loathsome_hex_per_cast_coef", 0.30))
        boss_window = 30.0
        hammer_dmg = hammer_rate * boss_window * self.hammer_mult * (1.0 + self.additive_phys_pct / 100.0)
        hex_dmg = hex_rate * boss_window * self.hex_mult * hex_coef
        total = hammer_dmg + hex_dmg
        if total <= 0:
            return [{"name": "Hammer", "value": 0}, {"name": "Hex", "value": 0}]
        return [
            {"name": "Hammer", "value": round(hammer_dmg / total * 100, 1)},
            {"name": "Hex", "value": round(hex_dmg / total * 100, 1)},
        ]

    @rx.var
    def dormant_power_rows(self) -> list[DormantPowerRow]:
        """All non-unobtainable buffs with current tier (0 if not picked)."""
        active_tags = {"physical attack power", "affinity attack power",
                       "attack boost", "improved ultimate art",
                       "successive attacks boost", "improved stance",
                       "critical hit", "sorceries & incantations"}
        out: list[DormantPowerRow] = []
        for b in buffs_mod.list_buffs():
            key = str(b.id)
            tier = int(self.dormant_picks.get(key, 0))
            lowdesc = b.description.lower()
            is_dmg = any(t in lowdesc for t in active_tags)
            formatted = b.formatted(tier) if tier > 0 else b.description
            out.append(DormantPowerRow(
                id=b.id,
                description=b.description,
                formatted=formatted,
                category=b.category,
                tier=tier,
                max_tier=max(1, len(b.values)),
                is_damage=is_dmg,
            ))
        return out

    @rx.var
    def dormant_active_count(self) -> int:
        return sum(1 for t in self.dormant_picks.values() if int(t) >= 1)

    @rx.var
    def dormant_attack_mult(self) -> float:
        return round(buffs_mod.global_attack_mult(self._active_dormant()), 3)

    @rx.var
    def dormant_summary_text(self) -> str:
        """Short pill-text for the hero — only populated when damage-affecting
        buffs are active."""
        if self.dormant_active_count == 0:
            return ""
        m = self.dormant_attack_mult
        if m <= 1.0001:
            return f"{self.dormant_active_count} dormant"
        pct = (m - 1.0) * 100
        return f"{self.dormant_active_count} dormant · +{pct:.1f}% atk"

    @rx.var
    def character_abilities_text(self) -> str:
        c = chars_mod.get(self.character_id)
        return (
            f"Skill: {c.skill.get('name','')}  ·  "
            f"Ult: {c.ultimate.get('name','')}  ·  "
            f"Passive: {c.passive.get('name','')}"
        )

    @rx.var
    def character_option_ids(self) -> list[str]:
        return [c.id for c in chars_mod.list_characters()]

    @rx.var
    def character_option_labels(self) -> list[str]:
        out = []
        for c in chars_mod.list_characters():
            tag = "★ full data" if c.is_fully_tuned else "· baseline"
            out.append(f"{c.icon}  {c.name}  {tag}")
        return out

    @rx.var
    def vessel_option_ids(self) -> list[str]:
        ids = [""] + [v["id"] for v in chars_mod.vessels_for(self.character_id)] + [CUSTOM_VESSEL]
        return ids

    @rx.var
    def vessel_option_labels(self) -> list[str]:
        labels = ["— none selected —"]
        for v in chars_mod.vessels_for(self.character_id):
            dlc = f"  · {v['dlc']}" if v.get("dlc") else ""
            labels.append(f"{v['name']}  ({'  '.join(v.get('slots', []))}){dlc}")
        labels.append("✎ Custom (pick any colors)")
        return labels

    @rx.var
    def active_vessel_colors(self) -> list[str]:
        n = 6 if self.mode == MODE_DEEP_NIGHT else 3
        if not self.vessel_id:
            return []
        if self.vessel_id == CUSTOM_VESSEL:
            return self.custom_vessel_colors[:n]
        for v in chars_mod.list_vessels():
            if v["id"] == self.vessel_id:
                s = list(v.get("slots", []))
                while len(s) < n:
                    s.append("U")
                return s[:n]
        return []

    @rx.var
    def is_custom_vessel(self) -> bool:
        return self.vessel_id == CUSTOM_VESSEL

    @rx.var
    def mode_label(self) -> str:
        return ("Standard (3 relics)" if self.mode == MODE_STANDARD
                else "Deep of Night (6 relics)")

    @rx.var
    def num_slots(self) -> int:
        return 3 if self.mode == MODE_STANDARD else 6

    # ═════════════════════════════════════════════════════════════
    # SOLVE
    # ═════════════════════════════════════════════════════════════
    def _active_dormant(self) -> list[buffs_mod.ActiveBuff]:
        return [
            buffs_mod.ActiveBuff(id=int(bid), tier=int(tier))
            for bid, tier in self.dormant_picks.items()
            if int(tier) >= 1
        ]

    def _ctx(self) -> PlayContext:
        active = self._active_dormant()
        return PlayContext(
            evergaol_clears=self.evergaol_clears,
            invader_kills=self.invader_kills,
            three_hammers_equipped=self.three_hammers,
            dual_wielding=self.dual_wielding,
            grease_uptime=self.grease_uptime,
            trance_uptime_baseline=self.trance_uptime,
            incant_buff_uptime=self.incant_uptime,
            took_damage_uptime=self.took_damage_uptime,
            ult_active_uptime=self.ult_uptime,
            chain_last_hit_fraction=self.chain_last_hit,
            first_combo_hit_fraction=self.first_combo_hit,
            enemy_poisoned_uptime=self.enemy_poisoned_uptime,
            enemy_scarlet_rot_uptime=self.enemy_scarlet_rot_uptime,
            enemy_frostbite_uptime=self.enemy_frostbite_uptime,
            enemy_bleed_uptime=self.enemy_bleed_uptime,
            enemy_asleep_uptime=self.enemy_asleep_uptime,
            enemy_madness_uptime=self.enemy_madness_uptime,
            enemy_deathblight_uptime=self.enemy_deathblight_uptime,
            dormant_attack_mult=buffs_mod.global_attack_mult(active),
            damage_scaling_override=(
                dict(self.damage_scaling_override) if self.damage_scaling_override else None
            ),
            build_goal_weights_override=(
                dict(self.build_goal_weights_override) if self.build_goal_weights_override else None
            ),
        )

    def _cfg(self) -> OptimizerConfig:
        locks = {_unk(k): v for k, v in self.locked_picks.items()}
        forced_debuffs = {int(k): int(v) for k, v in self.debuff_picks.items()}
        return OptimizerConfig(
            character_id=self.character_id,
            mode=self.mode,
            ctx=self._ctx(),
            excluded_ids=frozenset(self.excluded_ids),
            locked_attrs=locks,
            forced_debuffs=forced_debuffs,
            weapon_types_override=(
                tuple(self.weapon_types_override) if self.weapon_types_override else None
            ),
            playstyle_tags_override=(
                tuple(self.playstyle_tags_override) if self.playstyle_tags_override else None
            ),
            party_members=tuple(self.effective_party),
            seed_offset=self.explore_seed,
        )

    def recompute(self):
        cfg = self._cfg()
        build, contrib = optimize(cfg)

        # Compute display ordering per slot: locked attrs at their lock
        # positions (by attr_idx), then solver-picked attrs by sort_index.
        # This is the visual order the UI will render AND the ordering
        # per_attr_contributions uses for its keys, so they stay in sync.
        display_order: list[list[Effect]] = []
        for idx, b in enumerate(build):
            slot_locks = sorted(
                ((int(k.split(",")[1]), int(v))
                 for k, v in self.locked_picks.items()
                 if int(k.split(",")[0]) == idx),
                key=lambda p: p[0],
            )
            remaining = list(b.attrs)
            matched_locked: list[Effect] = []
            for _ai, eid in slot_locks:
                for i, a in enumerate(remaining):
                    if a.effect_id == eid:
                        matched_locked.append(remaining.pop(i))
                        break
            remaining_sorted = sorted(
                remaining, key=lambda a: (a.sort_index, a.effect_id)
            )
            display_order.append(matched_locked + remaining_sorted)

        # Per-attr contribution attribution — "how much would the weighted
        # score drop if this effect were removed?". Runs once per solve
        # (~18 extra compute() calls), and the display uses the cached
        # values to render the per-row pill + tooltip breakdown.
        contributions = per_attr_contributions(
            build, cfg, display_order=display_order, include_axes=True,
        )

        slots: list[SlotData] = []
        vcolors = self.active_vessel_colors
        char_tag = chars_mod.get(self.character_id).tag
        named_lookup = {r["id"]: r for r in chars_mod.named_relics_for(self.character_id)}
        # Build a signature → relic_id table for fast bundle matching when
        # the solver itself placed a named relic (no locked_picks needed).
        sig_to_relic: dict[tuple[int, ...], str] = {}
        for r in chars_mod.named_relics_for(self.character_id):
            if not r.get("attrs_verified"):
                continue
            attrs = tuple(sorted(r.get("attrs", [])))
            if len(attrs) == 3 and attrs not in sig_to_relic:
                sig_to_relic[attrs] = r["id"]

        for idx, b in enumerate(build):
            vc = vcolors[idx] if idx < len(vcolors) else ""
            attrs_sorted = display_order[idx]
            # Priority 1: user-locked attrs match a named relic.
            named_id = self._named_relic_for_slot(idx)
            # Priority 2: solver-placed attrs match a named relic bundle.
            if not named_id:
                sig = tuple(sorted(a.effect_id for a in b.attrs))
                named_id = sig_to_relic.get(sig, "")

            # If a named relic matches this slot's attrs, rewrite the display
            # name so all slots feel uniform (slot 2 stops saying "Common Grand"
            # when it actually holds Besmirched Frame, etc.).
            display_name = b.slot.name
            if named_id and named_id in named_lookup:
                info = named_lookup[named_id]
                relic_name = info.get("name", "")
                suffix_map = {
                    "remembrance": " (Remembrance)",
                    "shop": " (Shop)",
                    "boss_standard": " (Boss)",
                    "boss_everdark": " (Everdark)",
                    "boss_dlc": " (DLC Boss)",
                    "other": "",
                }
                suffix = suffix_map.get(info.get("source_type", ""), "")
                if relic_name:
                    display_name = f"Slot {idx + 1} — {relic_name}{suffix}"

            # Validate the relic against canonical rules so the UI can flag
            # impossible builds (duplicate ids, roll-group conflicts, missing
            # debuff, tier mismatch, foreign character tag). Remembrance/named
            # relic slots are skipped — their trios are game-fixed and our
            # promoted N/A effects would trip sort_order spuriously.
            errors: list[str] = []
            if not b.slot.is_fixed and not named_id:
                tier_set = (
                    frozenset(b.slot.allowed_tiers) if b.slot.allowed_tiers else None
                )
                results = validate_relic(
                    auto_sort(b.attrs),
                    debuff=b.debuff,
                    slot_tier_set=tier_set,
                    character_tag=char_tag,
                )
                errors = [
                    r.message for r in results
                    if (not r.ok) and r.severity == "error"
                ]

            slots.append(SlotData(
                index=idx,
                name=display_name,
                color_hint=b.slot.color_hint,
                tiers=sorted(b.slot.allowed_tiers),
                is_fixed=b.slot.is_fixed,
                vessel_color=vc,
                attrs=[
                    _attr_row(a, contributions.get((idx, ai), {}))
                    for ai, a in enumerate(attrs_sorted)
                ],
                locked_labels=list(b.slot.fixed_locked_labels),
                debuff=_attr_row(b.debuff) if b.debuff else None,
                needs_debuff=b.needs_debuff(),
                named_relic_id=named_id,
                validation_errors=errors,
                validation_tooltip=" · ".join(errors),
            ))
        self.build_slots = slots
        self.damage_total = round(contrib.total_boss_window, 2)
        self.hammer_mult = round(contrib.hammer_mult, 3)
        self.hex_mult = round(contrib.hex_mult, 3)
        self.additive_phys_pct = round(contrib.additive_phys * 100, 2)
        self.utility_mult = round(contrib.utility_mult, 3)
        self.skill_uptime_pct = round(contrib.trance_uptime * 100, 1)
        self.bucket_report = [
            BucketStat(name=k, value=round(v, 3))
            for k, v in sorted(contrib.bucket_report.items())
        ]
        self.survival_score = round(contrib.survival_score, 2)
        self.utility_score = round(contrib.utility_score, 2)
        self.team_score = round(contrib.team_score, 2)
        self.weighted_score = round(contrib.weighted_score, 2)

    def _named_relic_for_slot(self, slot_idx: int) -> str:
        """Return the named-relic id currently pinned in slot_idx (empty if none)."""
        # A named relic is active if every attr lock in this slot matches its attrs_verified list.
        chosen_attrs = sorted(
            v for k, v in self.locked_picks.items()
            if int(k.split(",")[0]) == slot_idx
        )
        if not chosen_attrs:
            return ""
        for r in chars_mod.named_relics_for(self.character_id):
            if not r.get("attrs_verified"):
                continue
            if sorted(r.get("attrs", [])) == chosen_attrs:
                return r["id"]
        return ""

    # ═════════════════════════════════════════════════════════════
    # EVENTS — identity
    # ═════════════════════════════════════════════════════════════
    def set_character(self, cid: str):
        """Switch characters — clears ALL per-character overrides so stale
        picks (effect IDs that don't exist for the new character, weapon
        slugs that don't match, build goals tuned for a different class)
        can't leak across the switch."""
        if cid == self.character_id:
            return
        self.character_id = cid
        self.excluded_ids = []
        self.locked_picks = {}
        self.debuff_picks = {}
        self.dormant_picks = {}
        self.vessel_id = ""
        self.weapon_types_override = []
        self.playstyle_tags_override = []
        self.damage_scaling_override = {}
        self.build_goal_weights_override = {}
        self.explore_seed = 0
        self.recompute()

    def set_mode(self, m: str):
        if m == self.mode:
            return
        self.mode = m
        # Drop locks AND debuff picks in now-missing deep slots (3-5).
        if m == MODE_STANDARD:
            self.locked_picks = {
                k: v for k, v in self.locked_picks.items()
                if int(k.split(",")[0]) < 3
            }
            self.debuff_picks = {
                k: v for k, v in self.debuff_picks.items()
                if int(k) < 3
            }
        self.recompute()

    def set_vessel(self, vid: str):
        self.vessel_id = "" if vid == "__none__" else vid
        self.recompute()

    def set_custom_color(self, slot_idx: int, color: str):
        colors = list(self.custom_vessel_colors)
        while len(colors) < 6:
            colors.append("U")
        colors[slot_idx] = color
        self.custom_vessel_colors = colors
        if self.vessel_id == CUSTOM_VESSEL:
            self.recompute()

    # ═════════════════════════════════════════════════════════════
    # EVENTS — playstyle sliders
    # ═════════════════════════════════════════════════════════════
    # Sliders have two handlers:
    #   · set_X       (on_change)       — updates the value live while dragging
    #                                      so the label/reset-chip update smoothly
    #                                      but does NOT trigger a solve.
    #   · set_X_commit (on_value_commit) — fires once when the user releases the
    #                                      thumb; triggers recompute().
    # Toggles (checkboxes) are discrete — they fire once per click, so they
    # update and recompute in the same handler.
    # Generic slider handlers — replace 18 near-identical per-field methods.
    # `drag_*` fires during drag (no recompute), `commit_*` on release.
    def drag_slider(self, field: str, v: list[float]):
        """Update a numeric state field from a slider drag event.
        Cast to int if the field's current value is int, else float."""
        cur = getattr(self, field, None)
        if isinstance(cur, bool):
            setattr(self, field, bool(v[0]))
        elif isinstance(cur, int):
            setattr(self, field, int(v[0]))
        else:
            setattr(self, field, float(v[0]))

    def commit_slider(self, field: str, v: list[float]):
        self.drag_slider(field, v)
        self.recompute()

    def toggle_hammers(self, v: bool):
        self.three_hammers = bool(v); self.recompute()
    def toggle_dual(self, v: bool):
        self.dual_wielding = bool(v); self.recompute()

    # ── playstyle / weapons overrides ─────────────────────────────
    def toggle_weapon(self, weapon: str):
        """Add/remove a weapon class from the override list. Empty override
        list reverts to the character JSON defaults."""
        current = set(self.weapon_types_override) if self.weapon_types_override else set(
            chars_mod.get(self.character_id).weapon_types or []
        )
        if weapon in current:
            current.discard(weapon)
        else:
            current.add(weapon)
        self.weapon_types_override = sorted(current)
        self.recompute()

    def toggle_playstyle_tag(self, tag: str):
        current = set(self.playstyle_tags_override) if self.playstyle_tags_override else set(
            chars_mod.get(self.character_id).globals_.get("playstyle_tags") or []
        )
        if tag in current:
            current.discard(tag)
        else:
            current.add(tag)
        self.playstyle_tags_override = sorted(current)
        self.recompute()

    def reset_playstyle_weapons(self):
        """Clear overrides → fall back to character JSON defaults."""
        self.weapon_types_override = []
        self.playstyle_tags_override = []
        self.damage_scaling_override = {}
        self.recompute()

    # ── damage scaling weight per stat ────────────────────────────
    def set_stat_scaling(self, stat: str, v: list[float]):
        """Slider on_change — update the per-stat scaling weight without
        triggering recompute (handled by _commit variant on release)."""
        current = dict(self.damage_scaling_override) if self.damage_scaling_override else dict(
            chars_mod.get(self.character_id).globals_.get("damage_scaling", {}) or {}
        )
        value = float(v[0])
        if value <= 0.001:
            current.pop(stat, None)
        else:
            current[stat] = round(value, 2)
        self.damage_scaling_override = current

    def set_stat_scaling_commit(self, stat: str, v: list[float]):
        self.set_stat_scaling(stat, v)
        self.recompute()

    # ── build goal weights (damage/survival/utility/team) ─────────
    def _set_goal_axis(self, axis: str, value: float):
        """Mutate a single axis of the goal weights, preserving others."""
        base = dict(self.build_goal_weights_override) if self.build_goal_weights_override else dict(
            self.effective_build_goal_weights
        )
        base[axis] = max(0.0, min(1.0, round(float(value), 2)))
        # Only commit if different from character JSON default — otherwise
        # clear the override so `effective` falls back to the declared values.
        try:
            declared = chars_mod.get(self.character_id).globals_.get("build_goal_weights") or {}
        except KeyError:
            declared = {}
        declared_full = {
            "damage": float(declared.get("damage", 1.0)),
            "survival": float(declared.get("survival", 0.2)),
            "utility": float(declared.get("utility", 0.3)),
            "team": float(declared.get("team", 0.0)),
        }
        if all(abs(base.get(k, 0.0) - declared_full[k]) < 0.005 for k in declared_full):
            self.build_goal_weights_override = {}
        else:
            self.build_goal_weights_override = {k: round(base.get(k, 0.0), 2) for k in declared_full}

    def set_goal_damage(self, v: list[float]):
        self._set_goal_axis("damage", v[0])
    def set_goal_survival(self, v: list[float]):
        self._set_goal_axis("survival", v[0])
    def set_goal_utility(self, v: list[float]):
        self._set_goal_axis("utility", v[0])
    def set_goal_team(self, v: list[float]):
        self._set_goal_axis("team", v[0])

    def set_goal_damage_commit(self, v: list[float]):
        self._set_goal_axis("damage", v[0]); self.recompute()
    def set_goal_survival_commit(self, v: list[float]):
        self._set_goal_axis("survival", v[0]); self.recompute()
    def set_goal_utility_commit(self, v: list[float]):
        self._set_goal_axis("utility", v[0]); self.recompute()
    def set_goal_team_commit(self, v: list[float]):
        self._set_goal_axis("team", v[0]); self.recompute()

    def reset_build_goals(self):
        self.build_goal_weights_override = {}
        self.recompute()

    # ── team composition ──────────────────────────────────────────
    def set_party_size(self, size: int):
        """Radio buttons (1 / 2 / 3) — trims or extends the party list.
        Solo = just self (no filtering change). Duo = self + 1 teammate
        (one picker visible). Trio = self + 2 (two pickers)."""
        size = max(1, min(3, int(size)))
        current = list(self.party_members_override)
        needed = size - 1   # minus self
        if len(current) > needed:
            current = current[:needed]
        while len(current) < needed:
            current.append("")   # empty slot — user picks via dropdown
        self.party_members_override = current
        self.recompute()

    def set_party_member(self, slot_idx: int, cid: str):
        """Pick a character for the Nth team-mate slot (0 or 1)."""
        current = list(self.party_members_override)
        while len(current) <= slot_idx:
            current.append("")
        # Guard against picking self (would be a no-op synergy-wise).
        if cid == self.character_id:
            cid = ""
        # Guard against picking the same character twice.
        if cid and cid in current and current.index(cid) != slot_idx:
            current[slot_idx] = ""
        else:
            current[slot_idx] = cid
        self.party_members_override = current
        self.recompute()

    def reset_party(self):
        self.party_members_override = []
        self.recompute()

    # ═════════════════════════════════════════════════════════════
    # EVENTS — locks, exclusions
    # ═════════════════════════════════════════════════════════════
    def lock_attr(self, slot_idx: int, attr_idx: int, effect_id: int):
        self.locked_picks[_k(slot_idx, attr_idx)] = effect_id
        self.recompute()

    def unlock_all(self):
        self.locked_picks = {}
        self.recompute()

    def lock_slot(self, slot_idx: int):
        """Lock every currently-displayed attr in this slot. After this the
        solver treats the slot as fixed and only optimises the other slots.
        Effects are locked by (slot_idx, attr_idx) → effect_id, which is what
        `_apply_locks` in the solver reads."""
        if slot_idx < 0 or slot_idx >= len(self.build_slots):
            return
        slot = self.build_slots[slot_idx]
        picks = dict(self.locked_picks)
        for attr_i, a in enumerate(slot.attrs):
            picks[_k(slot_idx, attr_i)] = int(a.id)
        self.locked_picks = picks
        self.recompute()

    def unlock_slot(self, slot_idx: int):
        """Remove every lock in this slot so the solver can freely re-roll it."""
        self.locked_picks = {
            k: v for k, v in self.locked_picks.items()
            if int(k.split(",")[0]) != slot_idx
        }
        self.recompute()

    def toggle_slot_lock(self, slot_idx: int):
        """Smart toggle used by the slot-header lock button.

          · 0–2 attrs locked → lock the remaining ones (full lock)
          · 3/3 locked → unlock all
        The UI only needs one button this way, driven by `slot_lock_state`."""
        if slot_idx < 0 or slot_idx >= len(self.build_slots):
            return
        count = sum(
            1 for k in self.locked_picks
            if int(k.split(",")[0]) == slot_idx
        )
        slot = self.build_slots[slot_idx]
        if count >= len(slot.attrs) and len(slot.attrs) > 0:
            self.unlock_slot(slot_idx)
        else:
            self.lock_slot(slot_idx)

    def toggle_attr_lock(self, slot_idx: int, attr_idx: int):
        """Lock/unlock a single attr at an exact visual position.

        Exact-position toggle: if the key (slot_idx, attr_idx) is already
        locked, unlock it; otherwise lock this position. This avoids the
        "click at pos 1 removes the lock at pos 2" bug that affects builds
        with duplicate effect_ids (e.g. 3× Physical Attack +4). The matching
        display logic in `recompute()` re-keys locks to current visual
        positions after each solve so icons stay in sync with attrs after
        sort reordering.
        """
        if slot_idx < 0 or slot_idx >= len(self.build_slots):
            return
        slot = self.build_slots[slot_idx]
        if attr_idx < 0 or attr_idx >= len(slot.attrs):
            return
        target_eid = int(slot.attrs[attr_idx].id)
        key = _k(slot_idx, attr_idx)
        if key in self.locked_picks:
            picks = {k: v for k, v in self.locked_picks.items() if k != key}
        else:
            picks = {**self.locked_picks, key: target_eid}
        self.locked_picks = picks
        self.recompute()

    def reset_playstyle_field(self, field_name: str):
        """Restore a single playstyle slider/toggle to its default."""
        if field_name in PLAYSTYLE_DEFAULTS:
            setattr(self, field_name, PLAYSTYLE_DEFAULTS[field_name])
            self.recompute()

    def reset_playstyle_all(self):
        """Restore every playstyle slider/toggle to the defaults at once."""
        for k, v in PLAYSTYLE_DEFAULTS.items():
            setattr(self, k, v)
        self.recompute()

    # ── dormant powers ────────────────────────────────────────
    def cycle_dormant(self, buff_id: int):
        """Cycle tier 0 → 1 → 2 → 0 for a given buff id."""
        key = str(int(buff_id))
        cur = self.dormant_picks.get(key, 0)
        info = buffs_mod.buffs_by_id().get(int(buff_id))
        max_tier = max(1, len(info.values)) if info else 1
        nxt = (cur + 1) % (max_tier + 1)
        picks = dict(self.dormant_picks)
        if nxt == 0:
            picks.pop(key, None)
        else:
            picks[key] = nxt
        self.dormant_picks = picks
        self.recompute()

    def clear_dormant(self):
        self.dormant_picks = {}
        self.recompute()

    # ── UI prefs ──────────────────────────────────────────────
    def toggle_charts(self):
        self.show_charts = not self.show_charts

    def explore_variant(self):
        """Re-solve with a fresh random seed so the simulated-annealing
        walk explores a different path. Finds near-optimal alternatives
        the default seeds happened to miss."""
        import random as _r
        self.explore_seed = _r.randint(1, 1_000_000)
        self.recompute()

    def reset_explore_seed(self):
        """Back to the deterministic default solver path."""
        if self.explore_seed != 0:
            self.explore_seed = 0
            self.recompute()

    def exclude(self, eid: int):
        if eid not in self.excluded_ids:
            self.excluded_ids = self.excluded_ids + [eid]
            self.recompute()

    def reset_excluded(self):
        self.excluded_ids = []
        self.recompute()

    # ═════════════════════════════════════════════════════════════
    # EVENTS — edit dialog
    # ═════════════════════════════════════════════════════════════
    def open_edit(self, slot_idx: int, attr_idx: int):
        self.edit_slot_idx = slot_idx
        self.edit_attr_idx = attr_idx
        self.edit_search = ""
        self.edit_group_filter = "All"
        self.edit_dialog_open = True

    def close_edit(self):
        self.edit_dialog_open = False
        self.edit_slot_idx = -1
        self.edit_attr_idx = -1

    def on_edit_open_change(self, v: bool):
        if not v:
            self.close_edit()

    def set_edit_search(self, s: str):
        self.edit_search = s

    def set_edit_group(self, g: str):
        self.edit_group_filter = g

    def apply_edit(self, effect_id: int):
        if self.edit_slot_idx >= 0 and self.edit_attr_idx >= 0:
            slot_i, attr_i = self.edit_slot_idx, self.edit_attr_idx
            # Strip any existing lock that points to the effect currently at
            # this visual position — we're replacing it, not stacking on top.
            if (slot_i < len(self.build_slots)
                    and attr_i < len(self.build_slots[slot_i].attrs)):
                old_eid = int(self.build_slots[slot_i].attrs[attr_i].id)
                self.locked_picks = {
                    k: v for k, v in self.locked_picks.items()
                    if not (int(k.split(",")[0]) == slot_i and int(v) == old_eid)
                }
            self.lock_attr(slot_i, attr_i, effect_id)
        self.close_edit()

    @rx.var
    def edit_dialog_title(self) -> str:
        if self.edit_slot_idx < 0:
            return ""
        return f"Edit Slot {self.edit_slot_idx + 1} · Attr {self.edit_attr_idx + 1}"

    @rx.var
    def edit_options(self) -> list[EditOption]:
        if self.edit_slot_idx < 0 or self.edit_slot_idx >= len(self.build_slots):
            return []
        slot = self.build_slots[self.edit_slot_idx]
        allowed = set(slot.tiers)
        pool = character_candidates(
            self.character_id,
            include_character_specific=True,
            include_wrong_weapon=True,
        )
        q = self.edit_search.strip().lower()
        g = self.edit_group_filter
        # Priority: CHARACTER → ATTACK → NONE → others (alphabetical).
        # Within a group, rank ID (matches in-game sort).
        prio = {"CHARACTER": 0, "ATTACK": 1, "NONE": 2}
        out: list[EditOption] = []
        for e in pool:
            if e.tier not in allowed:
                continue
            if g != "All" and e.group != g:
                continue
            hay = f"{e.effect_id} {e.tier} {e.group} {e.name}".lower()
            if q and q not in hay:
                continue
            out.append(_edit_option(e))
        out.sort(key=lambda d: (prio.get(d.group, 9), d.group, d.id))
        return out[:150]

    @rx.var
    def edit_current_id(self) -> int:
        """ID of the effect currently in the attr being edited (0 if empty)."""
        if (self.edit_slot_idx < 0 or self.edit_attr_idx < 0
                or self.edit_slot_idx >= len(self.build_slots)):
            return 0
        slot = self.build_slots[self.edit_slot_idx]
        if self.edit_attr_idx >= len(slot.attrs):
            return 0
        return slot.attrs[self.edit_attr_idx].id

    @rx.var
    def edit_current_name(self) -> str:
        if (self.edit_slot_idx < 0 or self.edit_attr_idx < 0
                or self.edit_slot_idx >= len(self.build_slots)):
            return ""
        slot = self.build_slots[self.edit_slot_idx]
        if self.edit_attr_idx >= len(slot.attrs):
            return ""
        a = slot.attrs[self.edit_attr_idx]
        return f"{a.id} · {a.tier} {a.group} · {a.name}"

    @rx.var
    def edit_groups_available(self) -> list[str]:
        if self.edit_slot_idx < 0 or self.edit_slot_idx >= len(self.build_slots):
            return ["All"]
        slot = self.build_slots[self.edit_slot_idx]
        allowed = set(slot.tiers)
        pool = character_candidates(
            self.character_id,
            include_character_specific=True,
            include_wrong_weapon=True,
        )
        groups = sorted({e.group for e in pool if e.tier in allowed})
        return ["All"] + groups

    # ═════════════════════════════════════════════════════════════
    # EVENTS — named-relic dialog
    # ═════════════════════════════════════════════════════════════
    def open_named(self, slot_idx: int):
        self.named_slot_idx = slot_idx
        self.named_dialog_open = True

    def close_named(self):
        self.named_dialog_open = False
        self.named_slot_idx = -1

    def on_named_open_change(self, v: bool):
        if not v:
            self.close_named()

    # ═════════════════════════════════════════════════════════════
    # EVENTS — debuff dialog
    # ═════════════════════════════════════════════════════════════
    def open_debuff(self, slot_idx: int):
        self.debuff_slot_idx = int(slot_idx)
        self.debuff_dialog_open = True

    def close_debuff(self):
        self.debuff_dialog_open = False
        self.debuff_slot_idx = -1

    def on_debuff_open_change(self, v: bool):
        if not v:
            self.close_debuff()

    def apply_debuff(self, curse_id: int):
        if self.debuff_slot_idx >= 0:
            key = str(self.debuff_slot_idx)
            if int(curse_id) == 0:
                self.debuff_picks.pop(key, None)
            else:
                picks = dict(self.debuff_picks)
                picks[key] = int(curse_id)
                self.debuff_picks = picks
            self.recompute()
        self.close_debuff()

    @rx.var
    def debuff_options(self) -> list[EditOption]:
        """All curse effects available for the current character."""
        out: list[EditOption] = []
        for c in curses_for_character(self.character_id):
            out.append(EditOption(
                id=c.effect_id,
                sort=c.sort_index if c.sort_index >= 0 else -1,
                tier=c.tier,
                flag=c.flag,
                group=c.group,
                name=c.name,
                family=c.family,
                character_tag=c.character_tag or "",
                utility=c.utility_value,
                mult=c.mult,
                additive=c.additive,
                effect_text=getattr(c, "effect_text", "") or "",
                category=getattr(c, "category", "") or "",
            ))
        out.sort(key=lambda d: (d.id,))
        return out

    @rx.var
    def debuff_dialog_title(self) -> str:
        if self.debuff_slot_idx < 0:
            return ""
        return f"Debuff for Slot {self.debuff_slot_idx + 1}"

    @rx.var
    def debuff_current_id(self) -> int:
        if (self.debuff_slot_idx < 0
                or self.debuff_slot_idx >= len(self.build_slots)):
            return 0
        slot = self.build_slots[self.debuff_slot_idx]
        return slot.debuff.id if slot.debuff is not None else 0

    def apply_named(self, relic_id: str):
        if relic_id == "__unlock__":
            for ai in range(3):
                self.locked_picks.pop(_k(self.named_slot_idx, ai), None)
            self.recompute()
        else:
            for r in chars_mod.named_relics_for(self.character_id):
                if r["id"] == relic_id:
                    if r.get("attrs_verified") and r.get("attrs"):
                        for ai, eid in enumerate(r["attrs"]):
                            self.locked_picks[_k(self.named_slot_idx, ai)] = eid
                        self.recompute()
                    break
        self.close_named()

    @rx.var
    def named_relics_list(self) -> list[NamedRelicRow]:
        cid = self.character_id
        filt = self.named_source_filter
        out = []
        # Priority: verified relics first, then by source_type bucket, then name.
        bucket_order = {
            "remembrance": 0, "shop": 1, "boss_standard": 2,
            "boss_everdark": 3, "boss_dlc": 4, "other": 5,
        }
        relics = chars_mod.named_relics_for(cid)
        # Remembrance relics for *this* character float to the top; other
        # characters' remembrance relics are filtered out entirely.
        filtered = []
        for r in relics:
            st = r.get("source_type", r.get("source", ""))
            ch = r.get("character", "any")
            if st == "remembrance" and ch != cid:
                continue
            if filt != "all" and st != filt:
                continue
            filtered.append((r, st))
        filtered.sort(key=lambda rs: (
            0 if rs[0].get("attrs_verified") else 1,
            bucket_order.get(rs[1], 9),
            rs[0].get("name", ""),
        ))
        for r, st in filtered:
            attrs = list(r.get("attrs", []))
            has_bundle_only = (
                bool(r.get("attrs_verified"))
                and any(is_bundle_only_effect(eid) for eid in attrs)
            )
            out.append(NamedRelicRow(
                id=r["id"],
                name=r["name"],
                color=r.get("color", "U"),
                source=r.get("source", ""),
                source_type=st,
                source_detail=r.get("source_detail", ""),
                character=r.get("character", "any"),
                description=r.get("description", ""),
                verified=bool(r.get("attrs_verified")),
                attrs=attrs,
                has_bundle_only=has_bundle_only,
            ))
        return out

    @rx.var
    def named_source_buckets(self) -> list[str]:
        """Ordered list of source filters the user can toggle between."""
        return ["all", "remembrance", "shop", "boss_standard",
                "boss_everdark", "boss_dlc", "other"]

    def set_named_source_filter(self, f: str):
        self.named_source_filter = f

    # ═════════════════════════════════════════════════════════════
    # EVENTS — presets
    # ═════════════════════════════════════════════════════════════
    def open_preset(self):
        self.preset_dialog_open = True
        self.preset_name_input = ""

    def close_preset(self):
        self.preset_dialog_open = False

    def on_preset_open_change(self, v: bool):
        if not v:
            self.close_preset()

    def set_preset_name(self, s: str):
        self.preset_name_input = s

    def save_preset(self):
        name = self.preset_name_input.strip()
        if not name:
            return rx.toast.error("Please enter a preset name.")
        cfg = self._cfg()
        build, contrib = optimize(cfg)
        locks = {_unk(k): v for k, v in self.locked_picks.items()}
        presets_mod.upsert(
            name=name,
            character_id=self.character_id,
            mode=self.mode,
            build=build,
            contrib=contrib,
            ctx=self._ctx(),
            excluded_ids=self.excluded_ids,
            locked_attrs=locks,
            vessel_id=self.vessel_id or None,
        )
        self.preset_version += 1
        self.close_preset()
        return rx.toast.success(f"Saved preset '{name}'")

    @rx.var
    def saved_presets(self) -> list[PresetRow]:
        # `preset_version` is only here to force Reflex to re-run this var
        # after save_preset / delete_preset mutate the JSON on disk.
        _ = self.preset_version
        out = []
        vessel_lookup = {v["id"]: v for v in chars_mod.list_vessels()}
        for p in presets_mod.list_for_character(self.character_id):
            char = chars_mod.get(p.character_id)
            # Resolve vessel: show friendly name + per-slot colour list.
            vessel_name = "— no vessel —"
            vessel_colors: list[str] = []
            if p.vessel_id and p.vessel_id in vessel_lookup:
                v = vessel_lookup[p.vessel_id]
                vessel_name = v.get("name", p.vessel_id)
                vessel_colors = list(v.get("slots", []))
            elif p.vessel_id == "__custom__":
                vessel_name = "Custom vessel"
            # Resolve each slot's effect ids → names via the effect DB.
            eff_ids = effects_by_id_for_character(p.character_id)
            # Build a signature → named-relic lookup once so we can re-derive
            # "Glass Necklace", etc. when a preset's slot attrs match a verified
            # named relic (the stored slot_name might be just "Common Grand"
            # if the preset was saved before the display-rename logic existed).
            named_sig_to_relic: dict[tuple[int, ...], dict] = {}
            for r in chars_mod.named_relics_for(p.character_id):
                if not r.get("attrs_verified"):
                    continue
                attrs_t = tuple(sorted(r.get("attrs", [])))
                if len(attrs_t) == 3 and attrs_t not in named_sig_to_relic:
                    named_sig_to_relic[attrs_t] = r
            suffix_map = {
                "remembrance": " (Remembrance)",
                "shop": " (Shop)",
                "boss_standard": " (Boss)",
                "boss_everdark": " (Everdark)",
                "boss_dlc": " (DLC Boss)",
                "other": "",
            }
            slot_rows: list[PresetSlotRow] = []
            for s in p.slots:
                names = []
                for eid in s.attr_ids:
                    e = eff_ids.get(int(eid))
                    names.append(e.name if e else f"#{eid}")
                debuff_name = ""
                if s.debuff_id:
                    e = eff_ids.get(int(s.debuff_id))
                    debuff_name = e.name if e else f"#{s.debuff_id}"
                vcolor = vessel_colors[s.slot_index] if s.slot_index < len(vessel_colors) else ""
                # Re-derive display name if these 3 attrs match a known named relic.
                attr_sig = tuple(sorted(int(x) for x in s.attr_ids))
                display_name = s.slot_name
                if len(attr_sig) == 3 and attr_sig in named_sig_to_relic:
                    relic = named_sig_to_relic[attr_sig]
                    suffix = suffix_map.get(
                        relic.get("source_type", relic.get("source", "")), ""
                    )
                    display_name = f"Slot {s.slot_index + 1} — {relic['name']}{suffix}"
                slot_rows.append(PresetSlotRow(
                    index=s.slot_index,
                    name=display_name,
                    vessel_color=vcolor,
                    attr_ids=list(s.attr_ids),
                    attr_names=names,
                    debuff_id=int(s.debuff_id or 0),
                    debuff_name=debuff_name,
                ))
            # Multi-objective scores — recompute on-the-fly if the preset
            # was saved before those columns existed.
            migrated = _migrated_preset_scores(p)
            w = p.build_goal_weights or (char.globals_.get("build_goal_weights") or {
                "damage": 1.0, "survival": 0.2, "utility": 0.3, "team": 0.0
            })
            contribs = {
                "damage": migrated["damage"] * float(w.get("damage", 1.0)),
                "survival": migrated["survival"] * float(w.get("survival", 0.0)),
                "utility": migrated["utility"] * float(w.get("utility", 0.0)),
                "team": migrated["team"] * float(w.get("team", 0.0)),
            }
            if max(contribs.values()) <= 0:
                build_type = "DPS build"
            else:
                dominant = max(contribs.items(), key=lambda kv: kv[1])[0]
                build_type = {
                    "damage": "DPS build",
                    "survival": "Tank build",
                    "utility": "Utility build",
                    "team": "Support build",
                }[dominant]

            out.append(PresetRow(
                name=p.name,
                score=round(p.total_boss_window, 2),
                mode=p.mode,
                date=p.created_at[:10],
                character_id=p.character_id,
                character_name=char.name,
                character_icon=char.icon,
                vessel_name=vessel_name,
                vessel_colors=vessel_colors,
                slots=slot_rows,
                hammer_mult=round(p.hammer_mult, 3),
                hex_mult=round(p.hex_mult, 3),
                utility_mult=round(p.utility_mult, 3),
                additive_phys_pct=round(p.additive_phys * 100, 2),
                trance_uptime_pct=round(p.trance_uptime * 100, 1),
                damage_score=round(migrated["damage"], 2),
                survival_score=round(migrated["survival"], 2),
                utility_score=round(migrated["utility"], 2),
                team_score=round(migrated["team"], 2),
                weighted_score=round(migrated["weighted"], 2),
                build_type=build_type,
            ))
        out.sort(key=lambda d: -d.score)
        return out

    @rx.var
    def preset_compare_chart_data(self) -> list[dict[str, Any]]:
        """Plain-dict projection used by recharts BarChart in the compare tab.
        One row per preset with the 4 multi-objective axes + legacy metrics."""
        return [
            {
                "name": p.name,
                # 4-axis multi-objective breakdown
                "damage": p.damage_score,
                "survival": p.survival_score,
                "utility": p.utility_score,
                "team": p.team_score,
                # Legacy numeric-mult columns retained so older charts keep
                # rendering without a schema migration.
                "hammer_mult_pct": round((p.hammer_mult - 1.0) * 100, 1),
                "hex_mult_pct": round((p.hex_mult - 1.0) * 100, 1),
                "utility_mult_pct": round((p.utility_mult - 1.0) * 100, 1),
                "additive_phys_pct": p.additive_phys_pct,
                "trance_uptime_pct": p.trance_uptime_pct,
            }
            for p in self.saved_presets
        ]

    def load_preset(self, name: str):
        """Restore every attr of every slot as a user lock. Slot 0 is
        included — legacy code skipped it when slot 0 was a truly-fixed
        Remembrance slot, but now it's a regular slot and skipping it
        caused named relics (Glass Necklace) to display as 'Common Grand'
        after load because the solver re-picked different attrs."""
        p = presets_mod.get(name, self.character_id)
        if p is None:
            return rx.toast.error(f"Preset '{name}' not found")
        self.excluded_ids = list(p.excluded_ids)
        self.vessel_id = p.vessel_id or ""
        new_locks: dict[str, int] = {}
        for s_i, ps in enumerate(p.slots):
            for a_i, eid in enumerate(ps.attr_ids):
                new_locks[_k(s_i, a_i)] = int(eid)
        self.locked_picks = new_locks
        self.recompute()
        return rx.toast.success(f"Loaded '{name}' ({p.total_boss_window:.2f} dmg)")

    def delete_preset(self, name: str):
        presets_mod.delete(name, self.character_id)
        self.preset_version += 1
        return rx.toast.info(f"Deleted '{name}'")

    # ═════════════════════════════════════════════════════════════
    # EVENTS — tabs
    # ═════════════════════════════════════════════════════════════
    def set_tab(self, t: str):
        self.active_tab = t

    # ═════════════════════════════════════════════════════════════
    # VALIDATOR TAB
    # ═════════════════════════════════════════════════════════════
    def set_v_tier(self, t: str): self.v_slot_tier = t

    def set_v_attr(self, idx: int, eid: int):
        if eid > 0:
            a = list(self.v_attr_ids)
            while len(a) < 3:
                a.append(0)
            a[idx] = eid
            self.v_attr_ids = a

    def clear_v_attr(self, idx: int):
        a = list(self.v_attr_ids)
        a[idx] = 0
        self.v_attr_ids = a

    def set_v_debuff(self, eid: int):
        self.v_debuff_id = int(eid) if eid else 0

    def set_v_search(self, idx: int, s: str):
        sl = list(self.v_search)
        while len(sl) < 3:
            sl.append("")
        sl[idx] = s
        self.v_search = sl

    def v_auto_sort(self):
        ids_sorted = sorted(
            [x for x in self.v_attr_ids if x > 0],
            key=lambda e: find_for_character(e, self.character_id).sort_index,
        )
        while len(ids_sorted) < 3:
            ids_sorted.append(0)
        self.v_attr_ids = ids_sorted

    @rx.var
    def v_is_valid(self) -> bool:
        for r in self.v_results:
            if r.severity == "error" and not r.ok:
                return False
        return True

    @rx.var
    def v_candidate_options_0(self) -> list[AttrRow]:
        return self._v_candidates_for(0)

    @rx.var
    def v_candidate_options_1(self) -> list[AttrRow]:
        return self._v_candidates_for(1)

    @rx.var
    def v_candidate_options_2(self) -> list[AttrRow]:
        return self._v_candidates_for(2)

    def _v_candidates_for(self, idx: int) -> list[AttrRow]:
        tier_set = {
            "common": {"STD", "BTH"},
            "deep":   {"DoN", "BTH"},
            "none":   None,
        }[self.v_slot_tier]
        pool = character_candidates(
            self.character_id,
            include_character_specific=True,
            include_wrong_weapon=True,
        )
        q = (self.v_search[idx] if idx < len(self.v_search) else "").strip().lower()
        rows: list[AttrRow] = []
        for e in pool:
            if tier_set is not None and e.tier not in tier_set:
                continue
            hay = f"{e.effect_id} {e.tier} {e.group} {e.name}".lower()
            if q and q not in hay:
                continue
            rows.append(_attr_row(e))
        rows.sort(key=lambda r: (r.group, r.id))
        return rows[:120]

    @rx.var
    def v_curse_options(self) -> list[AttrRow]:
        out: list[AttrRow] = [AttrRow(id=0, name="— none —")]
        for c in curses_for_character(self.character_id):
            out.append(_attr_row(c))
        return out

    @rx.var
    def v_results(self) -> list[ValidationRow]:
        effs = [
            find_for_character(x, self.character_id)
            for x in self.v_attr_ids if x > 0
        ]
        debuff = None
        if self.v_debuff_id:
            try:
                debuff = find_for_character(self.v_debuff_id, self.character_id)
            except KeyError:
                debuff = None
        tier_set = {
            "common": frozenset({"STD", "BTH"}),
            "deep":   frozenset({"DoN", "BTH"}),
            "none":   None,
        }[self.v_slot_tier]
        char = chars_mod.get(self.character_id)
        res = validate_relic(effs, debuff=debuff, slot_tier_set=tier_set, character_tag=char.tag)
        return [
            ValidationRow(rule=r.rule, ok=r.ok, severity=r.severity, message=r.message)
            for r in res
        ]
