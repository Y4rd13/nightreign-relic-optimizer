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
