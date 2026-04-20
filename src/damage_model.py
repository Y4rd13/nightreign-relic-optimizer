"""Damage model for Undertaker.

Model
-----
For each hit of damage we compute:

    damage_per_hit = base_ar
                   * skill_mod
                   * Π (1 + bucket_strength[b] * bucket_uptime[b])
                   * (1 + Σ additive_i * uptime_i * scaling_i)

Boss-window damage (30s) sums hammer and Loathsome Hex contributions:

    total = hammer_hits * damage_per_hammer_hit
          + hex_casts   * damage_per_hex_cast

Design choices
--------------
* Multiplicative buckets are binary per bucket: selecting >1 effect in the
  same bucket only gives the strongest. Buckets multiply vs each other.
* The Trance always-on mult (×1.15) is applied via `trance_uptime`.
* Utility effects (poise, sustain, CD reduction) add into `utility_mult`
  which multiplies final damage to represent effective-DPS gains.
* `config` carries player-controlled context (evergaol clears, trance
  uptime, grease usage, etc.) so the optimizer can simulate different
  playstyles without rebuilding effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from . import characters as chars_mod
from . import stats as stats_mod
from .effects_db import Effect


@dataclass
class PlayContext:
    """Player-controlled context that the solver holds constant while optimizing."""

    evergaol_clears: int = 6
    invader_kills: int = 2
    three_hammers_equipped: bool = True
    dual_wielding: bool = True
    two_handing: bool = False
    grease_uptime: float = 0.75
    trance_uptime_baseline: float = 0.50
    incant_buff_uptime: float = 0.0
    took_damage_uptime: float = 0.70
    # Enemy-affliction uptimes — gate "damage vs X-afflicted enemy" effects.
    # Default 0.0 means "my weapon/incant does not inflict this status" so the
    # conditional bonus scores as zero in the solver. Set to > 0 only when the
    # player has a reliable source (e.g. poison-coated weapon, frost incant).
    enemy_poisoned_uptime: float = 0.0
    enemy_scarlet_rot_uptime: float = 0.0
    enemy_frostbite_uptime: float = 0.0
    enemy_bleed_uptime: float = 0.0
    enemy_asleep_uptime: float = 0.0
    enemy_madness_uptime: float = 0.0
    enemy_deathblight_uptime: float = 0.0
    ult_active_uptime: float = 0.35
    first_combo_hit_fraction: float = 0.25
    chain_last_hit_fraction: float = 0.25

    boss_window_s: float = 30.0

    # Dormant powers layer — folded in as a single global mult so it stacks
    # cleanly on top of the relic pool without touching the solver's roll-group
    # accounting.
    dormant_attack_mult: float = 1.0

    # User override for per-stat damage scaling weights. None = use character
    # JSON defaults. Enables off-meta builds (e.g. DEX-Undertaker).
    damage_scaling_override: Optional[dict] = None

    # User override for multi-objective build goal weights (damage / survival /
    # utility / team). None = use character JSON defaults. Lets the user tell
    # the solver "I'm building Guardian as a tank, survival weight = 1.0".
    build_goal_weights_override: Optional[dict] = None


@dataclass
class BuildContribution:
    per_hammer_hit: float
    per_hex_cast: float
    hammer_mult: float
    hex_mult: float
    additive_phys: float
    additive_all: float
    utility_mult: float
    bucket_report: dict[str, float]
    trance_uptime: float
    total_boss_window: float
    # Multi-objective breakdown. `damage_score` mirrors total_boss_window (kept
    # separate so the naming is symmetric with survival/utility/team). The
    # scores are on comparable scales so solver can blend them by weights.
    damage_score: float = 0.0
    survival_score: float = 0.0
    utility_score: float = 0.0
    team_score: float = 0.0
    weighted_score: float = 0.0

    def summary(self) -> dict[str, float]:
        return {
            "per_hammer_hit": self.per_hammer_hit,
            "per_hex_cast": self.per_hex_cast,
            "hammer_mult": self.hammer_mult,
            "hex_mult": self.hex_mult,
            "additive_phys": self.additive_phys,
            "additive_all": self.additive_all,
            "utility_mult": self.utility_mult,
            "trance_uptime": self.trance_uptime,
            "total_boss_window": self.total_boss_window,
            "damage_score": self.damage_score,
            "survival_score": self.survival_score,
            "utility_score": self.utility_score,
            "team_score": self.team_score,
            "weighted_score": self.weighted_score,
        }


def _base_uptime_mapping(ctx: PlayContext) -> dict[str, float]:
    return {
        "trance_active": ctx.trance_uptime_baseline,
        "ult_active": ctx.ult_active_uptime,
        "grease_used": ctx.grease_uptime,
        "took_damage_recently": ctx.took_damage_uptime,
        # Enemy-affliction gates (used by 6260xxx / 7260xxx effects — "damage
        # vs X-afflicted enemy"). Zero by default so the solver does not stack
        # unobtainable bonuses.
        "enemy_poisoned": ctx.enemy_poisoned_uptime,
        "enemy_scarlet_rot": ctx.enemy_scarlet_rot_uptime,
        "enemy_frostbite": ctx.enemy_frostbite_uptime,
        "enemy_bleed": ctx.enemy_bleed_uptime,
        "enemy_asleep": ctx.enemy_asleep_uptime,
        "enemy_madness": ctx.enemy_madness_uptime,
        "enemy_deathblight": ctx.enemy_deathblight_uptime,
        "dual_wielding": 1.0 if ctx.dual_wielding else 0.0,
        "two_handing": 1.0 if ctx.two_handing else 0.0,
        "three_hammers_equipped": 1.0 if ctx.three_hammers_equipped else 0.0,
        # Generic "3+ of the character's primary weapon equipped" — gates all
        # `Improved Attack Power with 3+ X Equipped` effects (one per weapon
        # class). Bound to the same ctx flag as the hammer-specific gate so
        # one toggle drives both; weapon-scope filtering (_detect_weapon_slug)
        # keeps only the right effect per character in the candidate pool.
        "three_primary_equipped": 1.0 if ctx.three_hammers_equipped else 0.0,
        "incant_buff_active": ctx.incant_buff_uptime,
        "first_combo_hit": ctx.first_combo_hit_fraction,
        "chain_last_hit": ctx.chain_last_hit_fraction,
    }


def _effective_uptimes(effects: Iterable[Effect], ctx: PlayContext) -> dict[str, float]:
    """Start from the user-slider baselines, then fold in every effect's
    declared `uptime_boosts`. Capped at 1.0. This is what lets L525 / Glass
    Necklace's Ult Gauge synergies propagate into the solver's scoring
    without anyone touching the sliders."""
    uptimes = _base_uptime_mapping(ctx)
    for e in effects:
        boosts = getattr(e, "uptime_boosts", None) or {}
        for key, delta in boosts.items():
            if key in uptimes:
                uptimes[key] = min(1.0, uptimes[key] + float(delta))
    return uptimes


def _condition_uptime(eff: Effect, ctx: PlayContext,
                      effective_uptimes: dict[str, float] | None = None) -> float:
    requires = eff.requires
    if not requires:
        return float(eff.uptime_default)
    mapping = effective_uptimes or _base_uptime_mapping(ctx)
    return mapping.get(requires, float(eff.uptime_default))


NON_REGULAR_SCOPES = {"crit", "counter"}


def _scaling_count(scaling_stat: str | None, ctx: PlayContext) -> float:
    if not scaling_stat:
        return 1.0
    mapping = {
        "evergaol_clears": float(ctx.evergaol_clears),
        "invader_kills": float(ctx.invader_kills),
    }
    return mapping.get(scaling_stat, 1.0)


def _stat_scaling_mult(
    effects: Iterable[Effect],
    character_id: str,
    globals_: dict,
    override: Optional[dict] = None,
) -> float:
    """Convert raw stat deltas from relics into a damage multiplier.

    Each character declares `damage_scaling` = {stat → weight}, where weight is
    the fraction of damage that scales with that stat. Example: Undertaker sets
    {strength: 0.4, faith: 0.4}, meaning STR contributes 40% of weapon scaling,
    FAI another 40%. The remaining 20% is independent of stats.

    User may pass `override` to replace the character-declared weights (e.g.
    theorycrafting a DEX-Undertaker).

    Mult = Π (1 + weight · (delta / base_raw)). Using the grade-midpoint raw
    as the reference base. Returns 1.0 if no scaling is declared."""
    weights = override if override else (globals_.get("damage_scaling") if globals_ else None)
    if not weights:
        return 1.0
    try:
        char = chars_mod.get(character_id)
    except KeyError:
        return 1.0
    base_stats = char.stats or {}
    # Gather raw deltas from active effects via the stat_effects table.
    active_ids = [e.effect_id for e in effects]
    effective = stats_mod.compute_effective_stats(base_stats, active_ids)

    mult = 1.0
    for stat, weight in weights.items():
        w = float(weight)
        if w <= 0:
            continue
        data = effective.get(stat, {})
        delta = int(data.get("delta", 0))
        base_raw = int(data.get("base_raw", 0)) or 1
        mult *= 1.0 + w * (delta / base_raw)
    # Guard against pathological inputs sinking damage below a floor.
    return max(0.25, mult)


# ──────────────────────────────────────────────────────────────────
# Multi-objective goal classification.
#
# Every effect is classified into ONE primary goal (damage / survival /
# utility / team) so the solver can optimize for build types beyond pure
# damage (e.g. Guardian tank, Scholar support). The classifier uses name
# keywords because the effect database doesn't have an explicit category
# column — this is a pragmatic compromise until/if we add one.
# ──────────────────────────────────────────────────────────────────

_SURVIVAL_NAME_KEYWORDS: tuple[str, ...] = (
    "maximum hp",
    "damage negation",
    "phys damage negation",
    "physical damage negation",
    "magic damage negation",
    "fire damage negation",
    "lightning damage negation",
    "holy damage negation",
    "dark damage negation",
    "poise",
    "hp regeneration",
    "hp restoration",
    "hp flask",
    "flask charge",
    "absorption",
    "robust",
    "damage reduction",
    "stamina recovery",
    "focus recovery",
    "negate fall",
    "status ailment resistance",
    "resistance",
    "guard boost",
    "stamina guarding",
)

_TEAM_NAME_KEYWORDS: tuple[str, ...] = (
    "for allies",
    "to allies",
    "for ally",
    "with allies",
    "with ally",
    "allied",
    "allies near",
    "nearby ally",
    "nearby allies",
    "ally damage",
    "party",
    "revive",
    "raise ally",
    "raise character",
    "kindred",
    "retinue",
    "spirit ally",
    "summon spirit",
    "spectral",
    "restoration to allies",
    "heal allies",
    "team heal",
)


# Per-effect classification cache. Goal category and value proxy are pure
# functions of the Effect, so we memoize by effect_id — the solver calls
# these ~2.7M times per full solve across 4 characters and this cache cuts
# that bottleneck dramatically.
_GOAL_CACHE: dict[int, str] = {}
_VALUE_CACHE: dict[int, float] = {}


def _classify_goal(eff: Effect) -> str:
    """Returns the primary goal category for this effect.

    Priority order: team → survival → damage (if it has damage properties)
    → utility. An effect is only `team` if its text is specifically about
    allies; otherwise a heal on the user counts as `survival`.
    """
    cached = _GOAL_CACHE.get(eff.effect_id)
    if cached is not None:
        return cached
    name = (eff.name or "").lower()
    if any(kw in name for kw in _TEAM_NAME_KEYWORDS):
        out = "team"
    elif any(kw in name for kw in _SURVIVAL_NAME_KEYWORDS):
        out = "survival"
    elif eff.bucket is not None or eff.mult > 1.0 or eff.additive > 0.0:
        out = "damage"
    elif any(name.startswith(s) for s in (
        "strength +", "dexterity +", "intelligence +", "faith +", "arcane +"
    )):
        out = "damage"
    elif eff.utility_value > 0.0:
        out = "utility"
    else:
        out = "damage"
    _GOAL_CACHE[eff.effect_id] = out
    return out


# Raw-value scale factors to bring survival/utility/team into roughly the
# same range as boss-window damage scores (~20-100 for most characters).
# Calibration goal: a "pure X" build should have axis X dominate the weighted
# sum at full weight, but NOT so high that a tiny side-weight (e.g. 0.3 on
# utility for a DPS character) pulls the solver away from damage picks —
# utility values already multiply damage via utility_mult, so we must avoid
# double-counting. Current tuning:
#   · Guardian tank (survival=1.0) hits ~100-150 survival contribution
#   · DPS chars (survival=0.2-0.4) see survival contrib << damage contrib
_GOAL_SCALE = {
    "survival": 250.0,
    "utility": 200.0,
    "team": 400.0,
}


import re as _re
_EFFECT_TEXT_PCT_RE = _re.compile(r"by\s*(\d+(?:\.\d+)?)\s*%")
_EFFECT_TEXT_FLAT_RE = _re.compile(r"(?:by|restores?|raises?|increases?)\s*(\d+(?:\.\d+)?)\b")


def _effect_value_proxy(eff: Effect) -> float:
    """Picks a single scalar representing 'how much value this effect
    provides'. Memoized by effect_id — the solver calls this millions of
    times in hot paths.

    Source of truth, in order:
      1. Declared numeric fields (utility_value / additive / mult-1)
      2. Effect name for "+N%" style suffixes
      3. effect_text for "by N%" / "restores N" patterns (many in-game
         effects carry their value only in the descriptive text, e.g.
         'Improved Flask HP Restoration' → "Increases HP gained from
         flasks by 10%")
      4. Name keyword fallbacks (negation, resistance, ally, etc.)
    """
    cached = _VALUE_CACHE.get(eff.effect_id)
    if cached is not None:
        return cached
    v = max(
        float(eff.utility_value),
        float(eff.additive),
        float(eff.mult - 1.0) if eff.mult > 1.0 else 0.0,
    )
    if v > 0:
        _VALUE_CACHE[eff.effect_id] = v
        return v
    name_lower = (eff.name or "").lower()
    for token in ("+5%", "+4%", "+3%", "+2%", "+1%"):
        if token in name_lower:
            v = int(token[1]) / 100.0
            _VALUE_CACHE[eff.effect_id] = v
            return v
    # Parse effect_text for numeric values so defense/utility effects that
    # carry their value only in the description (Flask HP Restoration,
    # Magic Damage Negation+1, etc.) score non-zero. Heavily scaled down —
    # a "15% magic negation" is a narrow defensive buff, NOT comparable in
    # value to a "15% damage mult" on offense. Using /500 puts text-parsed
    # pcts in the 0.02-0.05 range — same magnitude as the keyword fallbacks
    # below — so they don't let the solver prefer defense over damage for
    # a DPS character with survival weight 0.2.
    text = (getattr(eff, "effect_text", "") or "").lower()
    if text:
        m = _EFFECT_TEXT_PCT_RE.search(text)
        if m:
            pct = float(m.group(1))
            v = min(pct / 500.0, 0.10)
            _VALUE_CACHE[eff.effect_id] = v
            return v
        m = _EFFECT_TEXT_FLAT_RE.search(text)
        if m:
            flat = float(m.group(1))
            v = min(flat / 5000.0, 0.05)
            _VALUE_CACHE[eff.effect_id] = v
            return v
    if "maximum hp" in name_lower:
        _VALUE_CACHE[eff.effect_id] = 0.04
        return 0.04
    if "negation" in name_lower or "poise" in name_lower:
        _VALUE_CACHE[eff.effect_id] = 0.03
        return 0.03
    for kw in ("for allies", "for ally", "allied", "nearby all",
               "retinue", "kindred"):
        if kw in name_lower:
            _VALUE_CACHE[eff.effect_id] = 0.05
            return 0.05
    if "resistance" in name_lower:
        _VALUE_CACHE[eff.effect_id] = 0.02
        return 0.02
    _VALUE_CACHE[eff.effect_id] = 0.0
    return 0.0


def _compute_goal_scores(effects: Iterable[Effect],
                         damage_total: float) -> tuple[float, float, float, float]:
    """Classifies each effect and sums its value into the corresponding goal
    bucket. Returns (damage_score, survival_score, utility_score, team_score).

    Damage_score mirrors boss-window damage to keep units consistent."""
    buckets = {"damage": 0.0, "survival": 0.0, "utility": 0.0, "team": 0.0}
    for e in effects:
        goal = _classify_goal(e)
        value = _effect_value_proxy(e)
        buckets[goal] += value
    survival = buckets["survival"] * _GOAL_SCALE["survival"]
    utility = buckets["utility"] * _GOAL_SCALE["utility"]
    team = buckets["team"] * _GOAL_SCALE["team"]
    # Damage score comes from the full damage_model (boss-window damage),
    # not from summing per-effect additives — those are already baked in.
    return damage_total, survival, utility, team


def _resolve_goal_weights(ctx: PlayContext, globals_: dict) -> dict[str, float]:
    """Pick final goal weights: user override → character JSON → safe fallback."""
    override = getattr(ctx, "build_goal_weights_override", None)
    if override:
        return {
            "damage": float(override.get("damage", 1.0)),
            "survival": float(override.get("survival", 0.0)),
            "utility": float(override.get("utility", 0.0)),
            "team": float(override.get("team", 0.0)),
        }
    declared = (globals_ or {}).get("build_goal_weights") or {}
    return {
        "damage": float(declared.get("damage", 1.0)),
        "survival": float(declared.get("survival", 0.2)),
        "utility": float(declared.get("utility", 0.3)),
        "team": float(declared.get("team", 0.0)),
    }


def compute(
    effects: Iterable[Effect],
    debuffs: Iterable[Effect] = (),
    ctx: PlayContext | None = None,
    character_id: str = "undertaker",
    detailed: bool = True,
) -> BuildContribution:
    # `detailed=False` skips the goal-score classification and bucket_report
    # packaging. The solver's inner loop only reads `weighted_score`, so for
    # the ~300k compute() calls during a solve we can save significant work.
    # UI callers (recompute, hero panel, etc.) default to `detailed=True`.
    ctx = ctx or PlayContext()
    g: dict[str, Any] = chars_mod.merged_globals(character_id)
    effects = list(effects)

    trance_base = float(g.get("trance_multiplier", 1.15))

    # Compose effective uptimes once per build. This lets "trance_active"
    # and "ult_active" rise dynamically when synergy effects (L525, Ult Gauge
    # boosts, etc.) are in the build — no more fixed slider ceiling.
    effective_up = _effective_uptimes(effects, ctx)
    trance_uptime = effective_up.get("trance_active", ctx.trance_uptime_baseline)

    # Fraction of total damage that's magic/fire/lightning/holy (0.0 for
    # pure physical characters like Undertaker). Used to weight the impact of
    # `affinity_only` multipliers accurately — a +10% affinity buff on a char
    # with 5% affinity damage is worth +0.5% total, not +10%.
    affinity_weight = float(g.get("affinity_damage_fraction", 0.0))

    buckets: dict[str, tuple[float, str]] = {}
    for e in effects:
        if e.bucket is None or e.mult <= 1.0:
            continue
        if e.mult_scope in NON_REGULAR_SCOPES:
            continue
        # Affinity-only multipliers boost magic/fire/lightning/holy damage.
        # Pure physical characters see zero benefit; hybrids see a fraction
        # proportional to how much of their damage is affinity.
        if e.mult_scope == "affinity_only":
            if affinity_weight <= 0.0:
                continue
            # Scale the effective mult by the affinity fraction: a +10% buff
            # on a 5%-affinity char becomes effectively 1 + 0.10*0.05 = 1.005.
            cond_up = _condition_uptime(e, ctx, effective_up)
            if cond_up <= 0.0:
                continue
            scaled_mult = 1.0 + (e.mult - 1.0) * cond_up * affinity_weight
            prior = buckets.get(e.bucket)
            if prior is None or scaled_mult > prior[0]:
                buckets[e.bucket] = (scaled_mult, "all")   # folds into global
            continue
        cond_up = _condition_uptime(e, ctx, effective_up)
        if cond_up <= 0.0:
            continue
        effective = 1.0 + (e.mult - 1.0) * cond_up
        prior = buckets.get(e.bucket)
        if prior is None or effective > prior[0]:
            buckets[e.bucket] = (effective, e.mult_scope)

    hammer_scope_mult = 1.0
    hex_scope_mult = 1.0
    for bucket_name, (val, scope) in buckets.items():
        if scope == "hammer":
            hammer_scope_mult *= val
        elif scope == "hex_only":
            hex_scope_mult *= val

    # Character's hex / ranged damage affinity (for Undertaker, hex is holy).
    # Affinity-typed additives (magic/fire/lightning/holy) match hex damage
    # when their scope equals this type. All other elemental scopes stay zero.
    hex_affinity = str(g.get("hex_damage_type", "") or "").lower()

    additive_by_family_phys: dict[str, float] = {}
    additive_by_family_all: dict[str, float] = {}
    stackable_phys = 0.0
    stackable_all = 0.0
    for e in effects:
        if e.additive == 0:
            continue
        cond = _condition_uptime(e, ctx, effective_up)
        scale = _scaling_count(e.scaling_stat, ctx)
        add = e.additive * cond * scale
        fam = e.family
        scope = e.additive_scope
        # Elemental additives route to hex damage only if the character's hex
        # uses that damage type. Otherwise they contribute nothing.
        if scope in ("magic", "fire", "lightning", "holy"):
            if scope == hex_affinity:
                scope = "hex_only"
            else:
                continue
        if e.stackable:
            if scope in ("phys", "all"):
                stackable_phys += add
            if scope in ("all", "hex_only"):
                stackable_all += add
        else:
            if scope == "phys":
                additive_by_family_phys[fam] = max(
                    additive_by_family_phys.get(fam, 0.0), add
                )
            elif scope == "all":
                additive_by_family_phys[fam] = max(
                    additive_by_family_phys.get(fam, 0.0), add
                )
                additive_by_family_all[fam] = max(
                    additive_by_family_all.get(fam, 0.0), add
                )
            elif scope == "hex_only":
                additive_by_family_all[fam] = max(
                    additive_by_family_all.get(fam, 0.0), add
                )
    additive_phys = sum(additive_by_family_phys.values()) + stackable_phys
    additive_all = sum(additive_by_family_all.values()) + stackable_all

    additive_phys += float(g.get("successive_attack_additive", 0.08)) * float(
        g.get("successive_attack_uptime", 0.70)
    )

    utility_mult = 1.0
    utility_by_family: dict[str, float] = {}
    for e in effects:
        if e.utility_value <= 0.0:
            continue
        fam = e.family
        utility_by_family[fam] = max(utility_by_family.get(fam, 0.0), e.utility_value)
    for v in utility_by_family.values():
        utility_mult *= 1.0 + v

    for d in debuffs:
        utility_mult *= max(0.01, 1.0 - d.debuff_cost)

    all_bucket_product = 1.0
    for bucket_name, (val, scope) in buckets.items():
        if scope in ("hammer", "hex_only"):
            continue
        all_bucket_product *= val

    trance_scope = 1.0 + (trance_base - 1.0) * trance_uptime

    hammer_mult = all_bucket_product * hammer_scope_mult * trance_scope * utility_mult
    hex_mult = all_bucket_product * hex_scope_mult * trance_scope * utility_mult

    per_hammer = hammer_mult * (1.0 + additive_phys)
    per_hex = hex_mult * (1.0 + additive_all + additive_phys * 0.5)

    hammer_rate = float(g.get("hammer_hits_per_boss_window_s", 0.8))
    hex_rate = float(g.get("hex_casts_per_boss_window_s", 0.22))
    hex_coef = float(g.get("loathsome_hex_per_cast_coef", 0.30))

    # Character stat scaling (STR/FAI/etc. deltas from relics propagate here).
    stat_mult = _stat_scaling_mult(
        effects, character_id, g,
        override=getattr(ctx, "damage_scaling_override", None),
    )

    hammer_damage = hammer_rate * ctx.boss_window_s * per_hammer * stat_mult
    hex_damage = hex_rate * ctx.boss_window_s * per_hex * hex_coef * stat_mult
    total = (hammer_damage + hex_damage) * ctx.dormant_attack_mult

    weights = _resolve_goal_weights(ctx, g)

    # Fast path for solver hot loop: skip expensive per-effect goal
    # classification and bucket_report dict construction when we only need
    # the weighted score. Also skip goal computation entirely when all
    # non-damage weights are zero (common for pure-DPS characters).
    non_damage_active = (weights["survival"] > 0
                          or weights["utility"] > 0
                          or weights["team"] > 0)
    if not detailed and not non_damage_active:
        weighted = total * weights["damage"]
        return BuildContribution(
            per_hammer_hit=per_hammer,
            per_hex_cast=per_hex * hex_coef,
            hammer_mult=hammer_mult,
            hex_mult=hex_mult,
            additive_phys=additive_phys,
            additive_all=additive_all,
            utility_mult=utility_mult,
            bucket_report={},
            trance_uptime=trance_uptime,
            total_boss_window=total,
            damage_score=total,
            weighted_score=weighted,
        )

    damage_score, survival_score, utility_score, team_score = _compute_goal_scores(
        effects, total
    )
    weighted = (
        damage_score * weights["damage"]
        + survival_score * weights["survival"]
        + utility_score * weights["utility"]
        + team_score * weights["team"]
    )
    bucket_report_flat = {k: v[0] for k, v in buckets.items()} if detailed else {}

    return BuildContribution(
        per_hammer_hit=per_hammer,
        per_hex_cast=per_hex * hex_coef,
        hammer_mult=hammer_mult,
        hex_mult=hex_mult,
        additive_phys=additive_phys,
        additive_all=additive_all,
        utility_mult=utility_mult,
        bucket_report=bucket_report_flat,
        trance_uptime=trance_uptime,
        total_boss_window=total,
        damage_score=damage_score,
        survival_score=survival_score,
        utility_score=utility_score,
        team_score=team_score,
        weighted_score=weighted,
    )


def naked_baseline(character_id: str = "undertaker",
                   ctx: PlayContext | None = None) -> float:
    """Damage score the character produces with zero relics — useful for
    normalising build scores into a `N×` multiplier over bare weapon."""
    return compute([], ctx=ctx, character_id=character_id).total_boss_window


if __name__ == "__main__":
    from .effects_db import find_for_character
    for char in ["undertaker", "wylder", "ironeye"]:
        empty = compute([], character_id=char)
        print(f"{char} naked: {empty.total_boss_window:.2f}")
