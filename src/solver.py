"""Relic optimizer: iterative-marginal greedy + local-search improvement.

Algorithm
---------
1. Start with fixed-slot effects (e.g. Glass Necklace locked attrs).
2. Rank each candidate by its marginal damage gain **given the current state**
   (not relative to naked).  Re-rank after every placement because multiplicative
   buckets amplify additive effects that already exist in the build.
3. Greedy-place the best-valued candidate in the first feasible (slot, attr)
   position, honoring tier/roll-group/stackability rules.
4. Repeat until all 18 attribute slots are filled (or no legal candidate
   remains → fall back to best neutral NONE filler).
5. Local search: for each placed attr, sweep alternative candidates; keep
   the swap if it improves total damage.  Iterate until no improvement or
   step cap reached.
6. Auto-pick the minimum-cost debuff for any relic with Y-flag attrs.

Top-k alternatives
------------------
After an optimal build is found, `top_k_alternatives(build, slot_idx, attr_idx,
k)` returns the k best **feasible** replacements for that attr, computing
damage for each substitution.  Effects the user has excluded are filtered out
of the candidate pool throughout.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional, Sequence

from . import characters as chars_mod
from .constraints import (
    MODE_DEEP_NIGHT,
    RelicBuild,
    RelicSlot,
    build_initial,
    default_slots,
    validate_build,
)
from .damage_model import BuildContribution, PlayContext, compute
from .effects_db import (
    Effect,
    character_candidates,
    curses_for_character,
    effects_by_id_for_character,
)


# ──────────────────────────────────────────────────────────────────
# Named relic bundles — loaded from data/named_relics.json so the solver
# can treat Remembrance / shop / boss relics as atomic 3-effect choices.
# ──────────────────────────────────────────────────────────────────

# Internal R/G/B/Y → slot color_hint strings used by constraints.py.
_RELIC_COLOR_TO_HINT = {"R": "red", "G": "green", "B": "blue", "Y": "yellow"}


@dataclass(frozen=True)
class NamedRelicBundle:
    id: str
    name: str
    color: str          # "R" | "G" | "B" | "Y" | "U"
    source_type: str
    attrs: tuple[int, ...]
    is_dn: bool = False   # True if all 3 effects are DoN-tier


def _bundles_for(character_id: str) -> list[NamedRelicBundle]:
    ids = effects_by_id_for_character(character_id)
    out: list[NamedRelicBundle] = []
    seen_attr_sigs: set[tuple[int, ...]] = set()
    for r in chars_mod.named_relics_for(character_id):
        if not r.get("attrs_verified"):
            continue
        attrs = tuple(r.get("attrs", []))
        if len(attrs) != 3:
            continue
        sig = tuple(sorted(attrs))
        if sig in seen_attr_sigs:
            continue   # same effect triple under two names — keep one
        effects = [ids.get(a) for a in attrs]
        if any(e is None for e in effects):
            continue
        # Reject bundles containing effects that are structurally un-pickable
        # for this character (character-tagged to someone else).
        from .effects_db import character_compatible
        if any(not character_compatible(e, character_id) for e in effects):
            continue
        is_dn = all(e.tier in ("DoN", "BTH") for e in effects if e is not None)
        seen_attr_sigs.add(sig)
        out.append(NamedRelicBundle(
            id=r["id"],
            name=r["name"],
            color=(r.get("color", "U") or "U").upper(),
            source_type=r.get("source_type", r.get("source", "other") or "other"),
            attrs=attrs,
            is_dn=is_dn,
        ))
    return out


def _bundle_fits_slot(bundle: NamedRelicBundle, slot: RelicSlot) -> bool:
    """Tier compat + color compat. Universal (U) bundles fit any color hint."""
    # Tier: every bundle effect must be rollable in this slot.
    ids_needed = set(bundle.attrs)
    # We rely on the caller to have validated effects exist for the character.
    # Skip DN bundles in STD-only slots and vice-versa.
    if "DoN" in slot.allowed_tiers and "STD" not in slot.allowed_tiers:
        # Deep slot — bundle must be DN-capable (at least BTH/DoN).
        if not bundle.is_dn:
            return False
    if "STD" in slot.allowed_tiers and "DoN" not in slot.allowed_tiers:
        # Common slot — bundle must not be DN-only.
        if bundle.is_dn:
            return False
    # Color: "U" fits any; otherwise must match slot's color_hint when set.
    if bundle.color == "U":
        return True
    hint = slot.color_hint
    if hint in ("", "any"):
        return True
    return _RELIC_COLOR_TO_HINT.get(bundle.color, "") == hint


@dataclass
class OptimizerConfig:
    character_id: str = "undertaker"
    mode: str = MODE_DEEP_NIGHT
    ctx: PlayContext = field(default_factory=PlayContext)
    excluded_ids: frozenset[int] = frozenset()
    locked_attrs: dict[tuple[int, int], int] = field(default_factory=dict)
    local_search_passes: int = 3
    curse_whitelist: frozenset[int] = frozenset({6830200, 6840000, 6830400, 6851300, 6820000})
    override_remembrance: bool = False
    forced_debuffs: dict[int, int] = field(default_factory=dict)  # slot_idx → curse_id
    # User overrides for the candidate pool. None = use character JSON defaults.
    # Letting the user set these lets them theorycraft a DEX-Undertaker (daggers
    # instead of hammers) or a guard-focused build for any character, etc.
    weapon_types_override: Optional[tuple[str, ...]] = None
    playstyle_tags_override: Optional[tuple[str, ...]] = None
    # Party composition (character ids including the current one). Default
    # None = solo play (character_id only). Used to gate effects that
    # reference another character's kit (e.g. "near Totem Stela" → Raider).
    party_members: Optional[tuple[str, ...]] = None

    # SA / multi-restart knobs.  Defaults picked so a full solve finishes in
    # ~1-2 s on the reference build.
    n_restarts: int = 6
    sa_iters_per_restart: int = 700
    sa_temp_scale: float = 0.02
    sa_temp_final: float = 0.01
    # Seed offset lets the UI force the stochastic search down a different
    # path without changing any inputs. Default 0 = deterministic solve.
    # The "Try variant" button bumps it to a random non-zero value so the
    # SA explores neighbourhoods the default seeds missed.
    seed_offset: int = 0

    def allow(self, eid: int) -> bool:
        return eid not in self.excluded_ids


def _score(build: Sequence[RelicBuild], cfg: OptimizerConfig) -> float:
    """Scalar objective the solver maximises. Uses the weighted multi-objective
    score from damage_model so non-damage goals (survival / utility / team)
    are honoured per the character's build-goal weights (or user override via
    `ctx.build_goal_weights_override`). Calls compute() with `detailed=False`
    to skip bucket_report and (for pure-damage builds) goal_score computation
    — these are only needed for UI, not optimisation."""
    eff = [a for b in build for a in b.attrs]
    debuffs = [b.debuff for b in build if b.debuff is not None]
    contrib = compute(
        eff, debuffs=debuffs, ctx=cfg.ctx,
        character_id=cfg.character_id, detailed=False,
    )
    return contrib.weighted_score


def _is_non_stackable_duplicate(
    eff: Effect,
    placed_ids: Counter,
    placed_families: Counter | None = None,
) -> bool:
    if eff.stackable:
        return False
    if placed_ids[eff.effect_id] >= 1:
        return True
    if placed_families is not None and placed_families[eff.family] >= 1:
        return True
    return False


def _placed_families(build: Sequence[RelicBuild]) -> Counter:
    c: Counter = Counter()
    for b in build:
        for a in b.attrs:
            if not a.stackable:
                c[a.family] += 1
    return c


_STAT_NAME_PATTERN = (
    "Strength +", "Dexterity +", "Intelligence +", "Faith +",
    "Arcane +", "Vigor +", "Mind +", "Endurance +",
)


def _matches_scaling_stat(eff: Effect, character_id: str) -> bool:
    """True if the effect is a stat-boost that scales damage for the character
    according to its `damage_scaling` weights. Lets the greedy pool include
    Strength/Faith +N for Undertaker even though their direct `additive` is 0
    — their real contribution comes from `_stat_scaling_mult`."""
    try:
        weights = chars_mod.get(character_id).globals_.get("damage_scaling", {}) or {}
    except Exception:
        return False
    if not weights:
        return False
    name = eff.name or ""
    stat_name_map = {
        "strength": "Strength +", "dexterity": "Dexterity +",
        "intelligence": "Intelligence +", "faith": "Faith +",
        "arcane": "Arcane +", "vigor": "Vigor +",
        "mind": "Mind +", "endurance": "Endurance +",
    }
    for stat, weight in weights.items():
        if float(weight) <= 0:
            continue
        frag = stat_name_map.get(stat)
        if frag and name.startswith(frag):
            return True
    return False


def _candidate_pool(cfg: OptimizerConfig, interest_only: bool = True) -> list[Effect]:
    """Effects the solver considers for auto-placement.

    `interest_only=True` → goal-contributing only (greedy picks). We include
    damage contributors plus survival/team effects when the character has
    non-zero weight for those dimensions (Guardian tank / Revenant summoner).
    `interest_only=False` → also include zero-value filler (for SA
    exploration and _best_filler) but STILL drop affliction-conditional
    effects whose gating uptime is zero — those are noise either way.
    """
    from .damage_model import (
        _base_uptime_mapping,
        _classify_goal,
        _resolve_goal_weights,
    )
    uptime_map = _base_uptime_mapping(cfg.ctx)
    try:
        char = chars_mod.get(cfg.character_id)
        goal_weights = _resolve_goal_weights(cfg.ctx, char.globals_)
    except Exception:
        goal_weights = {"damage": 1.0, "survival": 0.0, "utility": 0.0, "team": 0.0}
    pool = character_candidates(
        cfg.character_id,
        weapon_types=list(cfg.weapon_types_override) if cfg.weapon_types_override is not None else None,
        playstyle_tags=list(cfg.playstyle_tags_override) if cfg.playstyle_tags_override is not None else None,
        build_goal_weights=goal_weights,
        party_members=list(cfg.party_members) if cfg.party_members else None,
    )
    out = []
    for e in pool:
        if not cfg.allow(e.effect_id):
            continue
        # Always drop effects gated by an affliction uptime of 0 — they
        # don't contribute now and only confuse the solver's exploration.
        if e.requires and uptime_map.get(e.requires, 1.0) <= 0.0:
            continue
        if interest_only:
            is_damage = (
                e.mult > 1.0
                or e.additive > 0.0
                or e.utility_value > 0.0
                or e.effect_id == 6500900
                or _matches_scaling_stat(e, cfg.character_id)
            )
            if is_damage:
                out.append(e)
                continue
            # Also include survival/team effects when the character values
            # them (weight > 0). Without this, Guardian's damage-negation
            # effects would never enter the greedy pool.
            goal = _classify_goal(e)
            if goal in ("survival", "team") and goal_weights.get(goal, 0.0) > 0.05:
                out.append(e)
        else:
            out.append(e)
    return out


def _feasible_positions(
    eff: Effect,
    build: Sequence[RelicBuild],
    placed_ids: Counter,
    cfg: OptimizerConfig,
) -> list[int]:
    positions = []
    if _is_non_stackable_duplicate(eff, placed_ids):
        return positions
    for idx, b in enumerate(build):
        if b.slot.is_fixed:
            continue
        ok, _ = b.can_accept(eff)
        if ok:
            positions.append(idx)
    return positions


def _marginal_gain(
    build: Sequence[RelicBuild],
    eff: Effect,
    slot_idx: int,
    cfg: OptimizerConfig,
) -> float:
    target = build[slot_idx]
    if target.free_slots() <= 0:
        return -1e9
    before = _score(build, cfg)
    target.attrs.append(eff)
    target.attrs.sort(key=lambda a: (a.sort_index, a.effect_id))
    after = _score(build, cfg)
    target.attrs.remove(eff)
    target.attrs.sort(key=lambda a: (a.sort_index, a.effect_id))
    return after - before


def _pick_cheapest_curse(cfg: OptimizerConfig) -> Optional[Effect]:
    all_curses = curses_for_character(cfg.character_id)
    options = [c for c in all_curses if c.effect_id in cfg.curse_whitelist]
    if not options:
        options = all_curses
    options.sort(key=lambda c: (c.debuff_cost, c.effect_id))
    return options[0] if options else None


def _auto_debuffs(build: Sequence[RelicBuild], cfg: OptimizerConfig) -> None:
    """Fill every Y-flag slot with a curse. User-forced debuffs (from the
    state's debuff_picks dict) override the cheapest-curse default."""
    curse = _pick_cheapest_curse(cfg)
    forced = cfg.forced_debuffs or {}
    all_curses = {c.effect_id: c for c in curses_for_character(cfg.character_id)}
    for slot_idx, b in enumerate(build):
        forced_id = forced.get(slot_idx)
        if forced_id and forced_id in all_curses:
            b.debuff = all_curses[forced_id]
            continue
        if b.needs_debuff() and b.debuff is None:
            b.debuff = curse


def _initial_placed_ids(build: Sequence[RelicBuild]) -> Counter:
    c: Counter = Counter()
    for b in build:
        for a in b.attrs:
            c[a.effect_id] += 1
    return c


def _apply_locks(
    build: list[RelicBuild],
    cfg: OptimizerConfig,
    ids: dict[int, Effect],
) -> list[tuple[int, int]]:
    """Place every `cfg.locked_attrs` entry in its target slot.

    User locks are authoritative — we bypass the roll-group exclusivity check
    that `can_accept` enforces for free-roll placements. If the user has
    manually locked two effects from the same group (e.g. two ATTACK-group
    effects in one slot), we trust they know what relic they own or want to
    simulate. We still reject locks that are physically impossible: wrong
    tier for the slot, or the slot is fixed (Remembrance), or the slot is
    already full.

    Returns the list of (slot_idx, attr_idx) pairs that were successfully
    locked so callers can protect them from swap moves.
    """
    pinned: list[tuple[int, int]] = []
    for (slot_idx, attr_idx), eid in cfg.locked_attrs.items():
        eff = ids.get(eid)
        if eff is None:
            continue
        target = build[slot_idx]
        if target.slot.is_fixed:
            continue
        if eff.tier not in target.slot.allowed_tiers:
            continue
        if target.free_slots() <= 0:
            continue
        target.attrs.append(eff)
        target.attrs.sort(key=lambda a: (a.sort_index, a.effect_id))
        try:
            actual_idx = next(
                i for i, a in enumerate(target.attrs) if a.effect_id == eff.effect_id
            )
            pinned.append((slot_idx, actual_idx))
        except StopIteration:
            continue
    return pinned


def greedy_pack(cfg: OptimizerConfig, rng: random.Random | None = None) -> list[RelicBuild]:
    ids = effects_by_id_for_character(cfg.character_id)
    slots = default_slots(cfg.mode, cfg.character_id, cfg.override_remembrance)
    build = build_initial(slots, ids)
    _apply_locks(build, cfg, ids)

    pool = _candidate_pool(cfg)
    total_free = sum(b.free_slots() for b in build if not b.slot.is_fixed)

    for _ in range(total_free):
        placed = _initial_placed_ids(build)
        placed_fam = _placed_families(build)
        options: list[tuple[float, Effect, int]] = []
        for eff in pool:
            if _is_non_stackable_duplicate(eff, placed, placed_fam):
                continue
            for pos in _feasible_positions(eff, build, placed, cfg):
                gain = _marginal_gain(build, eff, pos, cfg)
                if gain > -1e17:
                    options.append((gain, eff, pos))
        if not options:
            break
        options.sort(key=lambda x: -x[0])
        if rng is None:
            _, eff, pos = options[0]
        else:
            # Randomised tie-break over top candidates, weighted by gain.
            top = options[:5]
            max_gain = max(g for g, _, _ in top)
            weights = [max(0.001, g - max_gain * 0.2) for g, _, _ in top]
            _, eff, pos = rng.choices(top, weights=weights, k=1)[0]
        build[pos].attrs.append(eff)
        build[pos].attrs.sort(key=lambda a: (a.sort_index, a.effect_id))

    for b in build:
        while b.free_slots() > 0 and not b.slot.is_fixed:
            placed = _initial_placed_ids(build)
            placed_fam = _placed_families(build)
            filler = _best_filler(b, placed, placed_fam, cfg)
            if filler is None:
                break
            b.attrs.append(filler)
            b.attrs.sort(key=lambda a: (a.sort_index, a.effect_id))

    _auto_debuffs(build, cfg)
    return build


def _clone(build: Sequence[RelicBuild]) -> list[RelicBuild]:
    out = []
    for b in build:
        nb = RelicBuild(slot=b.slot, debuff=b.debuff)
        nb.attrs = list(b.attrs)
        out.append(nb)
    return out


def _is_pinned(cfg: OptimizerConfig, slot_idx: int, attr_idx: int, attrs: Sequence[Effect]) -> bool:
    """True if the attr at (slot_idx, attr_idx) is user-locked.

    Matches by effect_id within the slot, NOT by exact (slot, attr) key.
    After solver sort (sort_index ordering), a locked effect can end up at
    a position whose lock key was never set — matching by effect_id keeps
    the pin regardless of sort-induced position drift. Count-aware so only
    the first N positions with the locked effect_id are considered pinned
    when the user has N locks for that effect (e.g. 2 copies of Phys Atk
    +4 locked; a solver-placed 3rd copy remains swappable)."""
    if attr_idx >= len(attrs):
        return False
    target_eid = attrs[attr_idx].effect_id
    lock_count = 0
    for (si, _ai), eid in cfg.locked_attrs.items():
        if si == slot_idx and eid == target_eid:
            lock_count += 1
    if lock_count == 0:
        return False
    # Count occurrences of target_eid up to and including this position.
    occurrence = sum(1 for i in range(attr_idx + 1)
                      if attrs[i].effect_id == target_eid)
    return occurrence <= lock_count


def _attempt_swap(
    build: list[RelicBuild],
    cfg: OptimizerConfig,
    slot_idx: int,
    attr_idx: int,
    new_eff: Effect,
) -> tuple[bool, float]:
    relic = build[slot_idx]
    if attr_idx >= len(relic.attrs):
        return False, 0.0
    if _is_pinned(cfg, slot_idx, attr_idx, relic.attrs):
        return False, 0.0
    if relic.attrs[attr_idx].effect_id == new_eff.effect_id:
        return False, 0.0

    current = relic.attrs.pop(attr_idx)
    placed = _initial_placed_ids(build)
    placed_fam = _placed_families(build)
    if _is_non_stackable_duplicate(new_eff, placed, placed_fam):
        relic.attrs.insert(attr_idx, current)
        return False, 0.0
    ok, _ = relic.can_accept(new_eff)
    if not ok:
        relic.attrs.insert(attr_idx, current)
        return False, 0.0
    relic.attrs.append(new_eff)
    relic.attrs.sort(key=lambda a: (a.sort_index, a.effect_id))
    return True, _score(build, cfg)


def _simulated_annealing(
    build: list[RelicBuild],
    cfg: OptimizerConfig,
    rng: random.Random,
) -> list[RelicBuild]:
    pool = _candidate_pool(cfg, interest_only=False)
    n_iters = cfg.sa_iters_per_restart
    if n_iters <= 0:
        return build

    cur_score = _score(build, cfg)
    best = _clone(build)
    best_score = cur_score

    T0 = max(0.5, cur_score * cfg.sa_temp_scale)
    T_final = cfg.sa_temp_final
    log_ratio = math.log(T_final / T0)

    non_fixed = [i for i, b in enumerate(build) if not b.slot.is_fixed]
    if not non_fixed:
        return build

    for it in range(n_iters):
        T = T0 * math.exp(log_ratio * it / n_iters)

        slot_idx = rng.choice(non_fixed)
        relic = build[slot_idx]
        if not relic.attrs:
            continue
        attr_idx = rng.randrange(len(relic.attrs))
        if _is_pinned(cfg, slot_idx, attr_idx, relic.attrs):
            continue

        # Sample a candidate biased toward higher value.  We deliberately
        # allow any legal effect (not just interest_only) so the walk can
        # explore fillers too.
        cand = rng.choice(pool)
        current = relic.attrs[attr_idx]
        relic.attrs.pop(attr_idx)
        placed = _initial_placed_ids(build)
        placed_fam = _placed_families(build)
        if cand.effect_id == current.effect_id or _is_non_stackable_duplicate(
            cand, placed, placed_fam
        ) or not relic.can_accept(cand)[0]:
            relic.attrs.insert(attr_idx, current)
            continue
        relic.attrs.append(cand)
        relic.attrs.sort(key=lambda a: (a.sort_index, a.effect_id))

        new_score = _score(build, cfg)
        delta = new_score - cur_score

        accept = delta >= 0 or (T > 1e-9 and rng.random() < math.exp(delta / T))
        if accept:
            cur_score = new_score
            if new_score > best_score:
                best_score = new_score
                best = _clone(build)
        else:
            relic.attrs.remove(cand)
            relic.attrs.insert(attr_idx, current)

    _auto_debuffs(best, cfg)
    return best


def _two_swap_local_search(
    build: list[RelicBuild],
    cfg: OptimizerConfig,
) -> list[RelicBuild]:
    """Try swapping pairs of attrs between different slots, one pair at a time.

    Useful when a BTH effect currently in a common slot would score higher
    in a deep slot (or vice versa) and the single-swap search can't find it
    because both attrs are locally optimal in their current positions.
    """
    improved = True
    while improved:
        improved = False
        cur_score = _score(build, cfg)
        non_fixed = [i for i, b in enumerate(build) if not b.slot.is_fixed]
        for a_slot in non_fixed:
            for b_slot in non_fixed:
                if b_slot <= a_slot:
                    continue
                for a_idx in range(len(build[a_slot].attrs)):
                    if _is_pinned(cfg, a_slot, a_idx, build[a_slot].attrs):
                        continue
                    for b_idx in range(len(build[b_slot].attrs)):
                        if _is_pinned(cfg, b_slot, b_idx, build[b_slot].attrs):
                            continue
                        ea = build[a_slot].attrs[a_idx]
                        eb = build[b_slot].attrs[b_idx]
                        # Must be legal in the other slot's tier gate + group.
                        if ea.tier not in build[b_slot].slot.allowed_tiers:
                            continue
                        if eb.tier not in build[a_slot].slot.allowed_tiers:
                            continue
                        build[a_slot].attrs.pop(a_idx)
                        build[b_slot].attrs.pop(b_idx)
                        a_ok, _ = build[a_slot].can_accept(eb)
                        b_ok, _ = build[b_slot].can_accept(ea)
                        if not (a_ok and b_ok):
                            build[a_slot].attrs.insert(a_idx, ea)
                            build[b_slot].attrs.insert(b_idx, eb)
                            continue
                        build[a_slot].attrs.append(eb)
                        build[b_slot].attrs.append(ea)
                        build[a_slot].attrs.sort(key=lambda a: (a.sort_index, a.effect_id))
                        build[b_slot].attrs.sort(key=lambda a: (a.sort_index, a.effect_id))
                        new_score = _score(build, cfg)
                        if new_score > cur_score + 1e-6:
                            cur_score = new_score
                            improved = True
                        else:
                            build[a_slot].attrs.remove(eb)
                            build[b_slot].attrs.remove(ea)
                            build[a_slot].attrs.insert(a_idx, ea)
                            build[b_slot].attrs.insert(b_idx, eb)
    _auto_debuffs(build, cfg)
    return build


def _best_filler(
    relic: RelicBuild,
    placed: Counter,
    placed_fam: Counter,
    cfg: OptimizerConfig,
) -> Optional[Effect]:
    """Pick the most useful effect for an otherwise empty slot position.

    Ranked by:
      · `utility + additive + mult-1` — declarative damage-proxy score
      · bias by goal classification × character's build_goal_weights so
        e.g. Guardian picks damage-negation fillers over stat fillers
      · plus a small bonus for stats that appear in the character's
        `damage_scaling` weights (so Faith +3 beats Vigor +3 for Undertaker).
    Zero-contribution candidates are still considered but ranked last; they
    only fill the slot when nothing better is placeable.
    """
    from .damage_model import (
        _base_uptime_mapping,
        _classify_goal,
        _effect_value_proxy,
        _resolve_goal_weights,
    )

    pool = _candidate_pool(cfg, interest_only=False)
    try:
        char = chars_mod.get(cfg.character_id)
        scaling_weights = char.globals_.get("damage_scaling", {}) or {}
        goal_weights = _resolve_goal_weights(cfg.ctx, char.globals_)
    except Exception:
        scaling_weights = {}
        goal_weights = {"damage": 1.0, "survival": 0.0, "utility": 0.0, "team": 0.0}
    stat_name_map = {
        "strength": "Strength", "dexterity": "Dexterity",
        "intelligence": "Intelligence", "faith": "Faith",
        "arcane": "Arcane", "vigor": "Vigor", "mind": "Mind",
        "endurance": "Endurance",
    }
    uptime_map = _base_uptime_mapping(cfg.ctx)

    best: Optional[Effect] = None
    best_score = -1e18
    for e in pool:
        ok, _ = relic.can_accept(e)
        if not ok:
            continue
        if _is_non_stackable_duplicate(e, placed, placed_fam):
            continue
        # Gate by requires→uptime as in the greedy path — don't weight an
        # affliction-conditional effect by its raw additive when the user
        # isn't actually inflicting that status.
        cond = 1.0
        if e.requires:
            cond = uptime_map.get(e.requires, float(e.uptime_default))
        damage_proxy = (
            e.utility_value
            + e.additive * 0.5 * cond
            + (e.mult - 1.0) * 0.5 * cond
        )
        goal = _classify_goal(e)
        value_proxy = _effect_value_proxy(e)
        goal_w = goal_weights.get(goal, 0.0)
        # Score mixes the damage heuristic with the goal-weighted value.
        # Damage-focused build: damage_proxy dominates. Tank build:
        # survival-tagged effects get strongly upweighted.
        score = damage_proxy * goal_weights.get("damage", 1.0) \
              + value_proxy * goal_w * (1.0 if goal != "damage" else 0.0)
        for stat, weight in scaling_weights.items():
            frag = stat_name_map.get(stat)
            if frag and e.name.startswith(frag + " +"):
                score += float(weight) * 0.05
                break
        if score > best_score:
            best_score = score
            best = e
    return best


def local_search(build: list[RelicBuild], cfg: OptimizerConfig) -> list[RelicBuild]:
    pool = _candidate_pool(cfg)
    improved = True
    passes = 0
    while improved and passes < cfg.local_search_passes:
        improved = False
        passes += 1
        cur_score = _score(build, cfg)
        for slot_idx, b in enumerate(build):
            if b.slot.is_fixed:
                continue
            # Preserve named-relic bundles: you can't own 1/3 of Glass
            # Necklace in the game, so local search must not split them.
            if _slot_is_bundle(build, slot_idx, cfg):
                continue
            for attr_idx in range(len(b.attrs)):
                current = b.attrs[attr_idx]
                # Use _is_pinned (effect_id-aware) — position-based check
                # breaks when sort_index reorders attrs off their lock key.
                if _is_pinned(cfg, slot_idx, attr_idx, b.attrs):
                    continue
                if current.effect_id in (
                    b.slot.fixed_effects if b.slot.is_fixed else ()
                ):
                    continue
                b.attrs.pop(attr_idx)
                placed = _initial_placed_ids(build)
                placed_fam = _placed_families(build)
                best_eff = current
                best_score = cur_score
                for cand in pool:
                    if cand.effect_id == current.effect_id:
                        continue
                    if _is_non_stackable_duplicate(cand, placed, placed_fam):
                        continue
                    ok, _ = b.can_accept(cand)
                    if not ok:
                        continue
                    b.attrs.append(cand)
                    b.attrs.sort(key=lambda a: (a.sort_index, a.effect_id))
                    s = _score(build, cfg)
                    b.attrs.remove(cand)
                    if s > best_score + 1e-6:
                        best_score = s
                        best_eff = cand
                b.attrs.insert(attr_idx, best_eff)
                b.attrs.sort(key=lambda a: (a.sort_index, a.effect_id))
                if best_eff.effect_id != current.effect_id:
                    improved = True
                    cur_score = best_score
    _auto_debuffs(build, cfg)
    return build


def _slot_is_bundle(build: list[RelicBuild], slot_idx: int, cfg: OptimizerConfig) -> bool:
    """True if this slot's 3 attr ids exactly match a verified named-relic
    bundle — used to protect bundle integrity from local_search rewrites
    (you can't own half of Glass Necklace in the game)."""
    if slot_idx >= len(build):
        return False
    attrs_sig = tuple(sorted(a.effect_id for a in build[slot_idx].attrs))
    if len(attrs_sig) != 3:
        return False
    for b in _bundles_for(cfg.character_id):
        if tuple(sorted(b.attrs)) == attrs_sig:
            return True
    return False


def _named_relic_sweep(build: list[RelicBuild], cfg: OptimizerConfig) -> list[RelicBuild]:
    """Post-pass: for each slot, consider replacing its 3 rolled effects with
    each compatible named-relic bundle (Glass Necklace etc.). Keep the single
    swap that most improves total damage, repeat until no further gain.

    This is what makes 'the algorithm picks the best between free-rolled and
    named-relic options' real — it runs after the SA stage so we only compare
    against strong baselines, not mid-optimization junk."""
    ids_lookup = effects_by_id_for_character(cfg.character_id)
    bundles = _bundles_for(cfg.character_id)
    if not bundles:
        return build

    locked = cfg.locked_attrs or {}
    # A slot with any user-locked attr is off-limits — honour explicit intent.
    def _slot_is_user_locked(slot_idx: int) -> bool:
        return any(s == slot_idx for (s, _a) in locked.keys())

    max_passes = 4
    for _ in range(max_passes):
        baseline = _score(build, cfg)
        best_gain = 1e-6
        best_swap: tuple[int, NamedRelicBundle] | None = None

        for slot_idx, b in enumerate(build):
            if b.slot.is_fixed:
                continue
            if _slot_is_user_locked(slot_idx):
                continue
            original_attrs = list(b.attrs)
            for bundle in bundles:
                if not _bundle_fits_slot(bundle, b.slot):
                    continue
                bundle_effects = [ids_lookup[a] for a in bundle.attrs]
                # Reject if any effect would clash with groups already placed
                # elsewhere (uniqueness across whole build is hard; leave the
                # per-slot group check — EXCLUSIVE_GROUPS duplicates inside one
                # slot are allowed in the game for named relics).
                b.attrs = bundle_effects
                trial_score = _score(build, cfg)
                gain = trial_score - baseline
                if gain > best_gain:
                    best_gain = gain
                    best_swap = (slot_idx, bundle)
                b.attrs = original_attrs

        if best_swap is None:
            break
        slot_idx, bundle = best_swap
        build[slot_idx].attrs = [ids_lookup[a] for a in bundle.attrs]
        build[slot_idx].attrs.sort(key=lambda a: (a.sort_index, a.effect_id))

    _auto_debuffs(build, cfg)
    return build


def optimize(cfg: Optional[OptimizerConfig] = None) -> tuple[list[RelicBuild], BuildContribution]:
    cfg = cfg or OptimizerConfig()
    variant_mode = cfg.seed_offset != 0

    # First pass: deterministic greedy + local search gives a strong baseline.
    # In variant-mode we skip it — we want alternative compositions, not the
    # baseline everyone else already gets.
    best = greedy_pack(cfg)
    best = local_search(best, cfg)
    best = _two_swap_local_search(best, cfg)
    best_score = _score(best, cfg)
    if variant_mode:
        # Stash the deterministic composition so we can reject candidates
        # that end up identical after local search.
        deterministic_ids = sorted(a.effect_id for b in best for a in b.attrs)
        best_score = -1e9   # force any valid candidate to win initially
    else:
        deterministic_ids = None

    # Multi-restart randomised greedy + simulated annealing to escape local
    # optima the deterministic pass can get stuck in. `seed_offset` lets the
    # UI re-roll the exploration when the user asks for a variant build.
    for restart in range(max(0, cfg.n_restarts)):
        rng = random.Random(restart * 9973 + 1 + cfg.seed_offset)
        cand = greedy_pack(cfg, rng=rng)
        cand = local_search(cand, cfg)
        cand = _simulated_annealing(cand, cfg, rng=rng)
        cand = local_search(cand, cfg)
        cand = _two_swap_local_search(cand, cfg)
        cand_score = _score(cand, cfg)
        if variant_mode:
            cand_ids = sorted(a.effect_id for b in cand for a in b.attrs)
            # Reject pure duplicates of the deterministic result — we want a
            # different composition, even if it scores a hair less.
            if cand_ids == deterministic_ids:
                continue
            if cand_score > best_score + 1e-6:
                best = cand
                best_score = cand_score
        else:
            if cand_score > best_score + 1e-6:
                best = cand
                best_score = cand_score

    # Variant-mode fallback: if no different composition survived the search,
    # fall back to the deterministic baseline so we still render *a* build.
    if variant_mode and best_score <= -1e8:
        best = greedy_pack(cfg)
        best = local_search(best, cfg)
        best = _two_swap_local_search(best, cfg)
        best_score = _score(best, cfg)

    # Named-relic bundle sweep: try swapping each slot to a verified named
    # relic (Remembrance / shop / boss). Runs last so it compares against the
    # strongest free-rolled baseline the SA/local-search produced.
    best = _named_relic_sweep(best, cfg)
    # One more light polish so roll-groups stay consistent around the swap.
    best = local_search(best, cfg)

    eff = [a for b in best for a in b.attrs]
    debuffs = [b.debuff for b in best if b.debuff is not None]
    contrib = compute(
        eff, debuffs=debuffs, ctx=cfg.ctx, character_id=cfg.character_id
    )
    return best, contrib


def top_k_alternatives(
    build: Sequence[RelicBuild],
    slot_idx: int,
    attr_idx: int,
    k: int = 5,
    cfg: Optional[OptimizerConfig] = None,
) -> list[tuple[Effect, float]]:
    cfg = cfg or OptimizerConfig()
    relic = build[slot_idx]
    if attr_idx >= len(relic.attrs):
        return []
    current = relic.attrs[attr_idx]
    working: list[RelicBuild] = []
    for b in build:
        rb = RelicBuild(slot=b.slot, debuff=b.debuff)
        rb.attrs = list(b.attrs)
        working.append(rb)
    rel = working[slot_idx]
    rel.attrs.pop(attr_idx)
    placed = _initial_placed_ids(working)
    placed_fam = _placed_families(working)
    pool = _candidate_pool(cfg, interest_only=False)

    scored: list[tuple[Effect, float]] = []
    for cand in pool:
        if cand.effect_id == current.effect_id:
            continue
        if _is_non_stackable_duplicate(cand, placed, placed_fam):
            continue
        ok, _ = rel.can_accept(cand)
        if not ok:
            continue
        rel.attrs.append(cand)
        rel.attrs.sort(key=lambda a: (a.sort_index, a.effect_id))
        s = _score(working, cfg)
        rel.attrs.remove(cand)
        scored.append((cand, s))
    scored.sort(key=lambda x: -x[1])
    return scored[:k]


def describe_effect_contribution(
    full_build: Sequence[RelicBuild],
    target: Effect,
    cfg: Optional[OptimizerConfig] = None,
) -> float:
    """Marginal weighted-score drop if a single copy of `target.effect_id`
    were removed from the build. Uses weighted_score (not raw damage) so
    the attribution is consistent with what the solver optimises."""
    cfg = cfg or OptimizerConfig()
    eff_all = [a for b in full_build for a in b.attrs]
    debuffs = [b.debuff for b in full_build if b.debuff is not None]
    with_target = compute(
        eff_all, debuffs=debuffs, ctx=cfg.ctx,
        character_id=cfg.character_id, detailed=False,
    ).weighted_score
    # Remove exactly one copy (duplicates are kept on the rest so the delta
    # represents THIS attr's contribution, not "all copies combined").
    removed = False
    without: list[Effect] = []
    for e in eff_all:
        if not removed and e.effect_id == target.effect_id:
            removed = True
            continue
        without.append(e)
    wo_score = compute(
        without, debuffs=debuffs, ctx=cfg.ctx,
        character_id=cfg.character_id, detailed=False,
    ).weighted_score
    return with_target - wo_score


def per_attr_contributions(
    full_build: Sequence[RelicBuild],
    cfg: Optional[OptimizerConfig] = None,
    display_order: Optional[Sequence[Sequence[Effect]]] = None,
    include_axes: bool = False,
) -> dict[tuple[int, int], float] | dict[tuple[int, int], dict[str, float]]:
    """Batch per-attr weighted-score contribution: {(slot_idx, attr_idx) →
    delta}. `display_order`, when provided, is a list (one entry per slot)
    of Effect lists in the order the UI shows them.

    `include_axes=True` returns {(si, ai) → {weighted, damage, survival,
    utility, team}} — useful for tooltips that break down why an effect
    is valuable. Default returns scalar weighted deltas only (faster)."""
    cfg = cfg or OptimizerConfig()
    all_attrs: list[tuple[int, int, Effect]] = []
    if display_order is not None:
        for si, slot_attrs in enumerate(display_order):
            for ai, attr in enumerate(slot_attrs):
                all_attrs.append((si, ai, attr))
    else:
        for si, relic in enumerate(full_build):
            sorted_attrs = sorted(relic.attrs, key=lambda a: (a.sort_index, a.effect_id))
            for ai, attr in enumerate(sorted_attrs):
                all_attrs.append((si, ai, attr))
    eff_all = [a for (_, _, a) in all_attrs]
    debuffs = [b.debuff for b in full_build if b.debuff is not None]
    baseline = compute(
        eff_all, debuffs=debuffs, ctx=cfg.ctx,
        character_id=cfg.character_id, detailed=include_axes,
    )
    out: dict = {}
    for idx, (si, ai, _) in enumerate(all_attrs):
        without = eff_all[:idx] + eff_all[idx + 1:]
        wo = compute(
            without, debuffs=debuffs, ctx=cfg.ctx,
            character_id=cfg.character_id, detailed=include_axes,
        )
        if include_axes:
            out[(si, ai)] = {
                "weighted": round(baseline.weighted_score - wo.weighted_score, 2),
                "damage": round(baseline.damage_score - wo.damage_score, 2),
                "survival": round(baseline.survival_score - wo.survival_score, 2),
                "utility": round(baseline.utility_score - wo.utility_score, 2),
                "team": round(baseline.team_score - wo.team_score, 2),
            }
        else:
            out[(si, ai)] = round(baseline.weighted_score - wo.weighted_score, 2)
    return out


if __name__ == "__main__":
    from .formatter import render_build_tree

    build, contrib = optimize()
    print(render_build_tree(build, contrib))
    errs = validate_build(build)
    if errs:
        print("\nVALIDATION ERRORS:")
        for e in errs:
            print(f"  ✗ {e}")
    else:
        print("\n✓ All constraints satisfied.")
