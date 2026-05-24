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


def _seed_preset(path, name="A", character_id="undertaker"):
    cfg = OptimizerConfig(character_id=character_id)
    build, contrib = optimize(cfg)
    return presets_mod.upsert(
        name=name, character_id=character_id, mode=cfg.mode,
        build=build, contrib=contrib, ctx=cfg.ctx,
        excluded_ids=[], locked_attrs={}, path=path,
    )


def test_export_import_round_trip(tmp_presets_path, tmp_path):
    """Exporting then importing into an empty store reproduces the preset."""
    src = _seed_preset(tmp_presets_path, "rt")
    payload = presets_mod.export_presets(
        [("rt", src.character_id)], path=tmp_presets_path
    )
    assert payload["schema"] == presets_mod.EXPORT_SCHEMA
    assert payload["type"] == "builds"
    assert len(payload["items"]) == 1

    dst = tmp_path / "fresh.json"
    report = presets_mod.import_presets(payload, path=dst)
    assert report.imported == 1 and report.skipped == 0 and report.errors == []

    loaded = presets_mod.get("rt", src.character_id, path=dst)
    assert loaded is not None
    assert loaded.damage_score == src.damage_score
    assert [s.attr_ids for s in loaded.slots] == [s.attr_ids for s in src.slots]


def test_import_skips_duplicate_by_default(tmp_presets_path):
    """Re-importing the same payload leaves existing items untouched."""
    _seed_preset(tmp_presets_path, "dup")
    payload = presets_mod.export_presets(
        [("dup", "undertaker")], path=tmp_presets_path
    )
    report = presets_mod.import_presets(payload, path=tmp_presets_path)
    assert report.imported == 0
    assert report.skipped == 1
    assert report.overwritten == 0


def test_import_overwrite_replaces_existing(tmp_presets_path):
    """With overwrite=True, same-key payload replaces the stored preset."""
    src = _seed_preset(tmp_presets_path, "ow")
    payload = presets_mod.export_presets(
        [("ow", "undertaker")], path=tmp_presets_path
    )
    # Mutate the in-memory preset to prove the overwrite actually landed.
    payload["items"][0]["damage_score"] = 9999.0
    report = presets_mod.import_presets(
        payload, overwrite=True, path=tmp_presets_path
    )
    assert report.overwritten == 1
    assert report.skipped == 0
    loaded = presets_mod.get("ow", "undertaker", path=tmp_presets_path)
    assert loaded is not None and loaded.damage_score == 9999.0
    assert loaded.damage_score != src.damage_score


def test_upsert_same_key_replaces_in_place(tmp_presets_path):
    """Contract the 'Save' (in-place) UX relies on: calling upsert twice with
    the same (name, character_id) must overwrite — never produce a duplicate —
    and the second call's payload must be what gets read back."""
    cfg = OptimizerConfig(character_id="undertaker")
    build, contrib = optimize(cfg)
    first = presets_mod.upsert(
        name="v1", character_id="undertaker", mode=cfg.mode,
        build=build, contrib=contrib, ctx=cfg.ctx,
        excluded_ids=[], locked_attrs={}, path=tmp_presets_path,
    )
    # Second call for the SAME key with a different payload (non-empty
    # excluded_ids) — simulates the user loading v1, editing, then saving.
    second = presets_mod.upsert(
        name="v1", character_id="undertaker", mode=cfg.mode,
        build=build, contrib=contrib, ctx=cfg.ctx,
        excluded_ids=[12345, 67890], locked_attrs={}, path=tmp_presets_path,
    )
    all_for_char = presets_mod.list_for_character("undertaker", path=tmp_presets_path)
    assert len(all_for_char) == 1, "upsert must replace, not append"
    assert all_for_char[0].excluded_ids == [12345, 67890]
    # Different character_id with same name is a different key — must NOT
    # collide with the undertaker entry (guards the character scoping).
    presets_mod.upsert(
        name="v1", character_id="guardian", mode=cfg.mode,
        build=build, contrib=contrib, ctx=cfg.ctx,
        excluded_ids=[], locked_attrs={}, path=tmp_presets_path,
    )
    assert len(presets_mod.load_all(tmp_presets_path)) == 2
    assert second.name == first.name


def test_import_rejects_unknown_schema(tmp_presets_path):
    bad = {"schema": "foo/9", "type": "builds", "items": []}
    report = presets_mod.import_presets(bad, path=tmp_presets_path)
    assert report.errors and "Unknown schema" in report.errors[0]
    assert report.imported == 0


def test_import_rejects_wrong_type(tmp_presets_path):
    bad = {"schema": presets_mod.EXPORT_SCHEMA, "type": "relics", "items": []}
    report = presets_mod.import_presets(bad, path=tmp_presets_path)
    assert report.errors and "Wrong type" in report.errors[0]


def test_import_continues_past_invalid_item(tmp_presets_path, tmp_path):
    """A malformed item is counted as error but the valid ones still import."""
    src = _seed_preset(tmp_presets_path, "ok")
    payload = presets_mod.export_presets(
        [("ok", "undertaker")], path=tmp_presets_path
    )
    payload["items"].insert(0, {"name": "broken"})  # missing required fields

    dst = tmp_path / "partial.json"
    report = presets_mod.import_presets(payload, path=dst)
    assert report.imported == 1
    assert len(report.errors) == 1
    assert presets_mod.get("ok", "undertaker", path=dst) is not None


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


# ---------------------------------------------------------------------------
# Pure (blob-based) functions — the localStorage refactor moves persistence
# from a server-side JSON file to a browser string blob. These operate on
# in-memory lists/strings with no file I/O.
# ---------------------------------------------------------------------------


def _mk_preset(name="k", character_id="undertaker", excluded_ids=None):
    cfg = OptimizerConfig(character_id=character_id)
    build, contrib = optimize(cfg)
    return presets_mod._preset_from_build(
        name=name, character_id=character_id, mode=cfg.mode,
        build=build, contrib=contrib, ctx=cfg.ctx,
        excluded_ids=excluded_ids or [], locked_attrs={},
    )


def test_serialize_deserialize_round_trip():
    """serialize(list)->str and deserialize(str)->list are inverses, scores survive."""
    p = _mk_preset(name="blob1", excluded_ids=[7])
    blob = presets_mod.serialize([p])
    assert isinstance(blob, str)
    out = presets_mod.deserialize(blob)
    assert len(out) == 1
    assert out[0].name == "blob1"
    assert out[0].excluded_ids == [7]
    assert out[0].damage_score == p.damage_score


def test_deserialize_tolerates_empty_and_garbage():
    """LocalStorage may hold '', invalid JSON, or a non-list — never raise."""
    assert presets_mod.deserialize("") == []
    assert presets_mod.deserialize("[]") == []
    assert presets_mod.deserialize("not json at all") == []
    assert presets_mod.deserialize("{}") == []  # object, not list


def test_upsert_in_list_replaces_by_key_not_append():
    lst = presets_mod.upsert_in_list([], _mk_preset(excluded_ids=[1]))
    assert len(lst) == 1
    lst = presets_mod.upsert_in_list(lst, _mk_preset(excluded_ids=[2, 3]))
    assert len(lst) == 1, "same (name, character_id) must replace, not append"
    assert lst[0].excluded_ids == [2, 3]
    # Different character with the same name is a distinct key.
    lst = presets_mod.upsert_in_list(lst, _mk_preset(character_id="guardian"))
    assert len(lst) == 2


def test_delete_from_list_removes_only_matching_key():
    lst = [_mk_preset(name="A", character_id="undertaker"),
           _mk_preset(name="A", character_id="guardian")]
    out = presets_mod.delete_from_list(lst, "A", "undertaker")
    assert len(out) == 1
    assert out[0].character_id == "guardian"
    # Deleting a non-existent key is a no-op (returns an equal-length list).
    assert len(presets_mod.delete_from_list(out, "nope", "undertaker")) == 1


def test_get_in_list_and_list_for_character_in_list():
    lst = [_mk_preset(name="A", character_id="undertaker"),
           _mk_preset(name="B", character_id="undertaker"),
           _mk_preset(name="A", character_id="guardian")]
    got = presets_mod.get_in_list(lst, "B", "undertaker")
    assert got is not None and got.name == "B"
    assert presets_mod.get_in_list(lst, "B", "guardian") is None
    undertaker = presets_mod.list_for_character_in_list(lst, "undertaker")
    assert {p.name for p in undertaker} == {"A", "B"}
    assert len(presets_mod.list_for_character_in_list(lst, "guardian")) == 1


def test_export_from_list_builds_payload():
    lst = [_mk_preset(name="X", character_id="undertaker", excluded_ids=[5])]
    payload = presets_mod.export_from_list(lst, [("X", "undertaker")])
    assert payload["schema"] == presets_mod.EXPORT_SCHEMA
    assert payload["type"] == "builds"
    assert len(payload["items"]) == 1
    assert payload["items"][0]["name"] == "X"
    # Unknown keys are silently dropped.
    assert presets_mod.export_from_list(lst, [("nope", "undertaker")])["items"] == []


def test_import_into_list_adds_skips_overwrites():
    base = [_mk_preset(name="A", character_id="undertaker")]
    payload = presets_mod.export_from_list(
        [_mk_preset(name="B", character_id="undertaker", excluded_ids=[9])],
        [("B", "undertaker")],
    )
    merged, report = presets_mod.import_into_list(base, payload)
    assert report.imported == 1
    assert {p.name for p in merged} == {"A", "B"}
    # Re-importing the same key skips by default (no append).
    merged2, report2 = presets_mod.import_into_list(merged, payload)
    assert report2.imported == 0 and report2.skipped == 1
    assert len(merged2) == 2
    # overwrite=True replaces the stored entry.
    payload["items"][0]["damage_score"] = 12345.0
    merged3, report3 = presets_mod.import_into_list(merged, payload, overwrite=True)
    assert report3.overwritten == 1
    got = presets_mod.get_in_list(merged3, "B", "undertaker")
    assert got is not None and got.damage_score == 12345.0


def test_import_into_list_rejects_bad_payload_leaves_list_unchanged():
    base = [_mk_preset(name="A", character_id="undertaker")]
    merged, report = presets_mod.import_into_list(
        base, {"schema": "bogus/9", "type": "builds", "items": []}
    )
    assert report.errors and "Unknown schema" in report.errors[0]
    assert merged == base
