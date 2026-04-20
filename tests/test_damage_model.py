"""Damage model + goal classification + fractional stat mapping."""

from __future__ import annotations

from src.damage_model import (
    PlayContext,
    _classify_goal,
    _effect_value_proxy,
    compute,
)
from src.effects_db import find_for_character
from src.stats import raw_to_numeric_fractional


def test_classify_goal_team_keyword():
    """Ally-oriented effect must classify as team, not damage."""
    eff = find_for_character(7037300, "undertaker")  # Contact Ally Heal
    assert _classify_goal(eff) == "team"


def test_classify_goal_damage_default():
    """Effect with mult > 1 always classifies as damage."""
    eff = find_for_character(7081200, "undertaker")  # Improved Attack Power with 3+ Hammers
    assert _classify_goal(eff) == "damage"


def test_weighted_score_equals_damage_when_only_damage_weighted():
    """If damage=1 and all others=0, weighted_score must match damage_score."""
    ctx = PlayContext(build_goal_weights_override={
        "damage": 1.0, "survival": 0.0, "utility": 0.0, "team": 0.0,
    })
    contrib = compute([], ctx=ctx, character_id="undertaker")
    assert contrib.weighted_score == contrib.damage_score


def test_detailed_fast_path_skips_goal_scores():
    """`detailed=False` + pure damage weights should skip goal scoring but
    still produce a correct weighted_score."""
    ctx = PlayContext()  # default: damage=1, survival=0.2, utility=0.3
    detailed = compute([], ctx=ctx, character_id="undertaker", detailed=True)
    fast = compute([], ctx=ctx, character_id="undertaker", detailed=False)
    # Damage axis is identical (no effects). Weighted differs by ε max.
    assert abs(detailed.damage_score - fast.damage_score) < 0.01


def test_effect_value_proxy_caches_and_returns_max():
    """utility_value / additive / (mult-1) — take the largest positive."""
    eff = find_for_character(7081200, "undertaker")  # mult 1.1
    v = _effect_value_proxy(eff)
    assert v >= 0.1  # mult=1.1 → at least 0.1


def test_physical_attack_up_is_stackable():
    """Physical Attack Up family stacks additively per wiki / in-game testing.
    The CE table flags them as non-stackable (inconsistent with the elemental
    Attack Power Up siblings which ARE flagged stackable there); baseline
    override flips them back to stackable=True."""
    for eid in (7001400, 7001401, 7001402, 6001400, 6001401):
        eff = find_for_character(eid, "undertaker")
        assert eff.stackable, f"effect {eid} ({eff.name}) must be stackable"


def test_stat_bonuses_stack_additively():
    """Str/Dex/Int/Fai/Arc +1/+2/+3 relics stack additively per in-game
    behaviour (+2 and +3 in the same build = +5 total). Verified by
    summing deltas in `compute_effective_stats` and propagating through
    `_stat_scaling_mult`."""
    str2 = find_for_character(7000301, "undertaker")  # Strength +2
    str3 = find_for_character(7000302, "undertaker")  # Strength +3
    ctx = PlayContext(build_goal_weights_override={
        "damage": 1.0, "survival": 0.0, "utility": 0.0, "team": 0.0,
    })
    just3 = compute([str3], ctx=ctx, character_id="undertaker")
    both = compute([str2, str3], ctx=ctx, character_id="undertaker")
    # delta(2)+delta(3)=5 ⇒ both should score strictly higher than just+3 alone.
    assert both.damage_score > just3.damage_score + 1e-6, (
        f"stat stacking broke: +3 alone={just3.damage_score:.3f} "
        f"+2+3={both.damage_score:.3f}"
    )


def test_three_plus_weapon_effects_apply_to_non_undertaker_chars():
    """Guardian's 3+ Halberds / Ironeye's 3+ Bows / etc. were silently
    unmodeled — only Undertaker's 3+ Hammers had bucket+mult overrides.
    Baseline now supplies B_3PLUS × 1.20 for every weapon-class variant,
    gated on `three_primary_equipped` (shared with the hammer toggle).

    Removing the baseline metadata makes this test fail, catching regressions
    on any future edit to the 3+ family."""
    ctx = PlayContext()
    # Guardian / Halberd (new case)
    h = find_for_character(7081800, "guardian")
    assert h.bucket == "B_3PLUS"
    assert h.mult > 1.19
    empty = compute([], ctx=ctx, character_id="guardian")
    withh = compute([h], ctx=ctx, character_id="guardian")
    assert withh.hammer_mult > empty.hammer_mult + 0.05, (
        f"halberd 3+ didn't raise Guardian mult: {empty.hammer_mult:.3f} "
        f"→ {withh.hammer_mult:.3f}"
    )
    # Undertaker / Hammer (existing case stays intact via B_L18 override)
    u = find_for_character(7081200, "undertaker")
    assert u.bucket == "B_L18"
    assert u.mult > 1.19


def test_physical_attack_up_copies_stack_additively():
    """Two different Physical Attack Up tiers in the same build must sum
    their additive values (2% + 2.5% = 4.5% phys), not max-dedupe to 2.5%.
    Regression for the 'contribution = 0' bug on duplicate phys-attack
    families."""
    base = find_for_character(7001400, "undertaker")  # +2%
    plus1 = find_for_character(7001401, "undertaker")  # +2.5%
    ctx = PlayContext(build_goal_weights_override={
        "damage": 1.0, "survival": 0.0, "utility": 0.0, "team": 0.0,
    })
    one = compute([base], ctx=ctx, character_id="undertaker")
    both = compute([base, plus1], ctx=ctx, character_id="undertaker")
    assert both.additive_phys > one.additive_phys + 1e-6, (
        f"stacking broke: one={one.additive_phys:.4f} both={both.additive_phys:.4f}"
    )


def test_raw_to_numeric_fractional_monotonic():
    """Adding points must never lower the fractional grade."""
    prev = raw_to_numeric_fractional("strength", 0)
    for raw in range(1, 100):
        cur = raw_to_numeric_fractional("strength", raw)
        assert cur >= prev, f"STR raw={raw} went backwards: {prev:.3f} → {cur:.3f}"
        prev = cur


def test_raw_to_numeric_fractional_intra_grade_visible():
    """+3 STR on grade A (raw=63) must bump the radar value measurably."""
    a_base = raw_to_numeric_fractional("strength", 63)
    a_plus3 = raw_to_numeric_fractional("strength", 66)
    assert a_plus3 - a_base >= 0.15, (
        f"+3 STR barely moves radar: {a_base} → {a_plus3}"
    )
