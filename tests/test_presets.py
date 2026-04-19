"""Preset persistence + round-trip + backward-compat migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import presets as presets_mod
from src.damage_model import PlayContext
from src.solver import OptimizerConfig, optimize


@pytest.fixture
def tmp_presets_path(tmp_path: Path) -> Path:
    """Isolated presets.json in a pytest tmp dir. Restores none — file-scope."""
    return tmp_path / "presets.json"


def test_preset_round_trip_preserves_scores(tmp_presets_path):
    """Save a fresh solve, load it, multi-objective scores survive verbatim."""
    cfg = OptimizerConfig(character_id="undertaker")
    build, contrib = optimize(cfg)
    presets_mod.upsert(
        name="qa_rt",
        character_id="undertaker",
        mode=cfg.mode,
        build=build,
        contrib=contrib,
        ctx=cfg.ctx,
        excluded_ids=[],
        locked_attrs={},
        path=tmp_presets_path,
    )
    loaded = presets_mod.get("qa_rt", "undertaker", path=tmp_presets_path)
    assert loaded is not None
    assert loaded.damage_score == contrib.damage_score
    assert loaded.survival_score == contrib.survival_score
    assert loaded.utility_score == contrib.utility_score
    assert loaded.team_score == contrib.team_score
    assert loaded.weighted_score == contrib.weighted_score


def test_old_preset_loads_with_missing_multi_objective(tmp_presets_path):
    """Legacy preset JSON without survival_score/utility_score/team_score
    must load cleanly with zeros (not raise)."""
    legacy = [{
        "name": "legacy",
        "character_id": "undertaker",
        "mode": "don",
        "created_at": "2025-01-01T00:00:00+00:00",
        "total_boss_window": 100.0,
        "ctx": {},
        "excluded_ids": [],
        "locked_attrs": {},
        "slots": [],
        "vessel_id": None,
    }]
    tmp_presets_path.write_text(json.dumps(legacy))
    out = presets_mod.load_all(tmp_presets_path)
    assert len(out) == 1
    p = out[0]
    assert p.damage_score == 100.0  # falls back to total_boss_window
    assert p.survival_score == 0.0
    assert p.utility_score == 0.0
    assert p.team_score == 0.0


def test_preset_migration_recomputes_missing_scores():
    """Legacy preset (no multi-objective columns) must get scores recomputed
    from its stored attrs + ctx. Skip in environments without reflex since
    the migration helper lives in nr_app.state."""
    reflex = pytest.importorskip("reflex")
    from nr_app.state import _migrated_preset_scores

    class _FakePreset:
        character_id = "undertaker"
        total_boss_window = 96.0
        damage_score = 96.0
        survival_score = 0.0
        utility_score = 0.0
        team_score = 0.0
        weighted_score = 96.0
        ctx = {}
        build_goal_weights: dict = {}
        slots = [type("S", (), {"attr_ids": [7036800, 7000902, 7037600]})()]

    out = _migrated_preset_scores(_FakePreset())
    assert out["damage"] > 0
    assert out["weighted"] >= out["damage"]


def test_named_relic_missing_effect_ids_skipped():
    """Relics that reference missing effect_ids must be marked
    attrs_verified=False AND their attr signatures must not appear in the
    solver's bundle sweep. Name collisions are fine (multiple verified
    variants can share a name) — we check by signature."""
    from src import characters as chars_mod
    from src.solver import _bundles_for
    rels = chars_mod.named_relics_for("undertaker")
    broken = [r for r in rels if 7082500 in r.get("attrs", [])
                               or 7260710 in r.get("attrs", [])]
    assert broken, "expected at least 1 relic with broken effect_id"
    for r in broken:
        assert r.get("attrs_verified") is False, (
            f"{r['name']} references missing effect but is still verified"
        )
    # Bundles are matched by attr signature (sorted tuple), not name.
    bundle_sigs = {tuple(sorted(b.attrs)) for b in _bundles_for("undertaker")}
    for r in broken:
        sig = tuple(sorted(r.get("attrs", [])))
        assert sig not in bundle_sigs, (
            f"broken bundle {r['name']} with attrs {sig} leaked into solver"
        )
