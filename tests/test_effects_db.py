"""Effects-db filters: playstyle, non-combat, weapon class."""

from __future__ import annotations

from src.effects_db import _family_key, character_candidates


def test_undertaker_pool_excludes_sorcery_damage_effects():
    """Glintstone / Gravity Stone damage effects are cast-tagged → filtered
    out of Undertaker's pool (no 'cast' in playstyle_tags)."""
    names = {e.name.lower() for e in character_candidates("undertaker")}
    leaks = [n for n in names if "glintstone" in n or "gravity stone" in n]
    assert leaks == [], f"sorcery leaked into Undertaker pool: {leaks}"


def test_undertaker_pool_excludes_guard_effects():
    """Undertaker doesn't have 'guard' in playstyle_tags — any 'while/upon
    guarding' effect must be filtered."""
    names = {e.name.lower() for e in character_candidates("undertaker")}
    leaks = [n for n in names if "guarding" in n or "upon blocking" in n]
    assert leaks == [], f"guard effects leaked: {leaks}"


def test_recluse_pool_includes_sorcery_effects():
    """Sorcery-specialization effects MUST appear for a caster (Recluse has
    'cast' playstyle tag), otherwise the filter is overzealous."""
    names = {e.name.lower() for e in character_candidates("recluse")}
    has_sorcery = any("glintstone" in n or "sorcery" in n for n in names)
    assert has_sorcery, "Recluse has no sorcery-related effects in its pool"


def test_guardian_pool_includes_damage_negation_when_survival_weighted():
    """Guardian with survival weight > 0 should see defensive effects
    (Magic/Fire/Lightning Damage Negation) in its candidate pool."""
    names = {
        e.name.lower() for e in character_candidates(
            "guardian",
            build_goal_weights={"damage": 0.4, "survival": 1.0, "utility": 0.4, "team": 0.2},
        )
    }
    has_negation = any("damage negation" in n for n in names)
    assert has_negation, "Guardian (survival=1) missing damage negation effects"


def test_family_key_strips_plus_numeric_suffix():
    """'Physical Attack +4' → 'Physical Attack' — family grouping for
    non-stackable dedup relies on this."""
    assert _family_key("Physical Attack +4") == "Physical Attack"
    assert _family_key("Strength +3") == "Strength"
    assert _family_key("Unrelated Effect") == "Unrelated Effect"


def test_party_synergy_filter_solo():
    """Raider-synergy effects (e.g. 'near Totem Stela') must NOT appear
    for a non-Raider character playing solo — Totem Stela is Raider's
    ultimate, so it's not on the field."""
    pool = {e.effect_id for e in character_candidates("wylder", party_members=["wylder"])}
    assert 7030000 not in pool, "'Improved Poise Near Totem Stela' leaked to solo Wylder"
    assert 7090300 not in pool


def test_party_synergy_filter_duo():
    """Once Raider joins the party, those same effects become legit picks
    for the other character — they can stack around Raider's Totem Stela."""
    pool = {e.effect_id for e in character_candidates("wylder", party_members=["wylder", "raider"])}
    assert 7030000 in pool, "Totem Stela synergy should unlock when Raider is in party"
    assert 7090300 in pool


def test_party_synergy_filter_raider_self():
    """Raider's own synergy effects must always be available to them,
    regardless of party size."""
    pool = {e.effect_id for e in character_candidates("raider", party_members=["raider"])}
    assert 7030000 in pool


def test_family_key_memoized():
    """Calling twice with the same input shouldn't re-run the regex (cache hit)."""
    from src.effects_db import _FAMILY_CACHE
    _FAMILY_CACHE.clear()
    _family_key("Test Effect +3")
    assert "Test Effect +3" in _FAMILY_CACHE
