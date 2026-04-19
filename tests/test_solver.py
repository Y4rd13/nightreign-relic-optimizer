"""Solver contract tests — cover the bug classes we hit during development."""

from __future__ import annotations

import pytest

from src.damage_model import PlayContext
from src.solver import OptimizerConfig, optimize, per_attr_contributions


def _solve(char_id: str, **ctx_kwargs):
    ctx = PlayContext(**ctx_kwargs) if ctx_kwargs else PlayContext()
    return optimize(OptimizerConfig(character_id=char_id, ctx=ctx))


ALL_CHARACTERS = [
    "undertaker", "wylder", "guardian", "ironeye", "duchess",
    "raider", "revenant", "recluse", "executor", "scholar",
]


@pytest.mark.parametrize("char", ALL_CHARACTERS)
def test_every_character_solves(char):
    """Regression guard: every character must produce a complete build."""
    build, contrib = _solve(char)
    assert len(build) == 6, f"{char} didn't return 6 slots"
    total_attrs = sum(len(b.attrs) for b in build)
    assert total_attrs == 18, f"{char} has {total_attrs} attrs, expected 18"
    assert contrib.weighted_score > 0, f"{char} weighted_score is 0"


def test_deterministic_seed_produces_stable_build():
    """Seed=0 (default) must give bit-identical results on back-to-back solves."""
    build_a, contrib_a = _solve("undertaker")
    build_b, contrib_b = _solve("undertaker")
    ids_a = tuple(sorted(a.effect_id for b in build_a for a in b.attrs))
    ids_b = tuple(sorted(a.effect_id for b in build_b for a in b.attrs))
    assert ids_a == ids_b
    assert contrib_a.weighted_score == contrib_b.weighted_score


def test_variant_mode_produces_different_composition():
    """seed_offset != 0 must return a different effect set than seed=0."""
    base = OptimizerConfig(character_id="undertaker", seed_offset=0)
    variant = OptimizerConfig(character_id="undertaker", seed_offset=99999)
    build_a, _ = optimize(base)
    build_b, _ = optimize(variant)
    ids_a = sorted(a.effect_id for b in build_a for a in b.attrs)
    ids_b = sorted(a.effect_id for b in build_b for a in b.attrs)
    assert ids_a != ids_b, "variant mode returned identical composition"


def test_locks_preserved_across_weight_change():
    """User locks must survive a rebuild triggered by changing build-goal
    weights — the solver cannot silently drop pinned effects."""
    locks = {(3, 0): 7081200, (3, 1): 7081200, (3, 2): 7081200}
    ctx_a = PlayContext(build_goal_weights_override={
        "damage": 1.0, "survival": 0.0, "utility": 0.0, "team": 0.0,
    })
    ctx_b = PlayContext(build_goal_weights_override={
        "damage": 0.3, "survival": 1.0, "utility": 0.0, "team": 0.0,
    })
    build_a, _ = optimize(OptimizerConfig(
        character_id="undertaker", ctx=ctx_a, locked_attrs=locks,
    ))
    build_b, _ = optimize(OptimizerConfig(
        character_id="undertaker", ctx=ctx_b, locked_attrs=locks,
    ))
    slot3_ids_a = sorted(a.effect_id for a in build_a[3].attrs)
    slot3_ids_b = sorted(a.effect_id for a in build_b[3].attrs)
    assert slot3_ids_a == [7081200, 7081200, 7081200]
    assert slot3_ids_b == [7081200, 7081200, 7081200]


def test_goal_weights_change_result():
    """Guardian with survival=1 must pick a different build than survival=0."""
    ctx_dps = PlayContext(build_goal_weights_override={
        "damage": 1.0, "survival": 0.0, "utility": 0.0, "team": 0.0,
    })
    ctx_tank = PlayContext(build_goal_weights_override={
        "damage": 0.0, "survival": 1.0, "utility": 0.0, "team": 0.0,
    })
    build_dps, _ = optimize(OptimizerConfig(character_id="guardian", ctx=ctx_dps))
    build_tank, _ = optimize(OptimizerConfig(character_id="guardian", ctx=ctx_tank))
    ids_dps = sorted(a.effect_id for b in build_dps for a in b.attrs)
    ids_tank = sorted(a.effect_id for b in build_tank for a in b.attrs)
    assert ids_dps != ids_tank, (
        "Guardian DPS vs Tank builds should differ significantly"
    )


def test_locks_preserved_after_partial_unlock():
    """Regression: user locks all 3 attrs, unlocks attr3 — the remaining
    2 locked effects must still be in the slot after re-solve. Previously,
    SA would sort attrs by sort_index and `_is_pinned` (position-based)
    would fail to protect locked effects that drifted off their lock key,
    letting SA swap them for unrelated fillers."""
    # Full user locks: slot 3 (UI "slot 4") has 3 locks, slot 4 has 3 locks.
    # Simulate user unlocking (3, 2) and (4, 2) by omitting those keys.
    locks = {
        (3, 0): 7081200,   # Improved Attack Power 3+ Hammers
        (3, 1): 6611400,   # Improved Flask HP Restoration  (sort 207)
        (4, 0): 6500900,   # L525
        (4, 1): 7331200,   # Improved Hammer Atk
    }
    cfg = OptimizerConfig(character_id="undertaker", locked_attrs=locks)
    build, _ = optimize(cfg)
    slot3_ids = {a.effect_id for a in build[3].attrs}
    slot4_ids = {a.effect_id for a in build[4].attrs}
    assert 7081200 in slot3_ids, "slot 3 lost 7081200 lock"
    assert 6611400 in slot3_ids, "slot 3 lost 6611400 lock (the critical bug)"
    assert 6500900 in slot4_ids, "slot 4 lost 6500900 lock"
    assert 7331200 in slot4_ids, "slot 4 lost 7331200 lock"


def test_per_attr_contributions_sum_approximates_baseline():
    """Each attr's contribution is the delta from removing it. Summing every
    attr's contribution should give roughly the full weighted_score (not
    exactly, because the damage model is non-linear — but the same order)."""
    build, contrib = _solve("undertaker")
    cfg = OptimizerConfig(character_id="undertaker")
    contribs = per_attr_contributions(build, cfg)
    total = sum(contribs.values())
    # Should be within 30% of weighted_score (non-linearity allowed).
    assert contrib.weighted_score * 0.6 < total < contrib.weighted_score * 1.4, (
        f"per-attr sum {total:.1f} diverges too far from weighted {contrib.weighted_score:.1f}"
    )
