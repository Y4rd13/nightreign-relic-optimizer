"""State handler ↔ localStorage blob contract.

These exercise the Reflex State directly (instantiable under pytest — the
rx.State guard checks PYTEST_CURRENT_TEST). They lock in the stateless-server
behaviour: every preset / my-relic mutation must round-trip through the
browser blob, never a server-side file.
"""

from __future__ import annotations

import pytest

reflex = pytest.importorskip("reflex")

from src import my_relics as my_relics_mod  # noqa: E402
from src import presets as presets_mod  # noqa: E402

# A roll-group-legal Undertaker common triplet (see test_my_relics).
LEGAL_TRIPLET = [7036800, 7000902, 7037600]


def _state():
    from nr_app.state import State
    s = State()
    s.character_id = "undertaker"
    return s


def test_save_preset_writes_blob_and_sets_active():
    s = _state()
    s.preset_name_input = "freshbuild"
    s.save_preset()
    assert s.active_preset_name == "freshbuild"
    names = [p.name for p in presets_mod.deserialize(s.presets_blob)]
    assert "freshbuild" in names


def test_save_active_preset_writes_to_blob():
    s = _state()
    s.active_preset_name = "loaded"
    s.save_active_preset()
    presets = presets_mod.deserialize(s.presets_blob)
    assert any(p.name == "loaded" and p.character_id == "undertaker" for p in presets)


def test_save_active_preset_without_name_does_not_write():
    s = _state()
    s.active_preset_name = ""
    s.save_active_preset()
    assert presets_mod.deserialize(s.presets_blob) == []


def test_delete_preset_removes_from_blob_and_clears_active():
    s = _state()
    s.preset_name_input = "todelete"
    s.save_preset()
    assert s.active_preset_name == "todelete"
    s.delete_preset("todelete")
    assert all(p.name != "todelete" for p in presets_mod.deserialize(s.presets_blob))
    assert s.active_preset_name == ""


def test_character_switch_clears_active_preset():
    s = _state()
    s.preset_name_input = "keep"
    s.save_preset()
    assert s.active_preset_name == "keep"
    s.set_character("guardian")
    assert s.active_preset_name == ""
    # The saved build still lives in the blob (only the active pointer cleared).
    assert any(p.name == "keep" for p in presets_mod.deserialize(s.presets_blob))


def test_save_my_relic_writes_to_my_relics_blob():
    s = _state()
    s.v_slot_tier = "common"
    s.v_attr_ids = list(LEGAL_TRIPLET)
    s.my_relic_name_input = "myrelic"
    s.my_relic_color_input = "G"
    s.save_my_relic()
    relics = my_relics_mod.deserialize(s.my_relics_blob)
    assert any(r.name == "myrelic" for r in relics)


def test_delete_my_relic_removes_from_blob():
    s = _state()
    s.v_slot_tier = "common"
    s.v_attr_ids = list(LEGAL_TRIPLET)
    s.my_relic_name_input = "doomed"
    s.my_relic_color_input = "G"
    s.save_my_relic()
    relic_id = my_relics_mod.deserialize(s.my_relics_blob)[0].id
    s.delete_my_relic(relic_id)
    assert my_relics_mod.deserialize(s.my_relics_blob) == []
