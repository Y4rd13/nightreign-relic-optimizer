"""User-relic inventory persistence + validation gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import my_relics as mr
from src.effects_db import find_for_character

# Effect IDs reused across tests. Picked from a real Undertaker build so the
# triplet is guaranteed to be group-legal + ascending sort_index.
E_CHAR   = 7036800   # CHARACTER group, sort 60
E_NONE   = 7000902   # NONE group,      sort 444
E_ATTACK = 7037600   # ATTACK group,    sort 600
E_CHAR_2 = 7037300   # CHARACTER group, sort 63 — would collide with E_CHAR


@pytest.fixture
def tmp_relics_path(tmp_path: Path) -> Path:
    return tmp_path / "my_relics.json"


def _ef(eid: int):
    return find_for_character(eid, "undertaker")


def test_upsert_creates_and_round_trips(tmp_relics_path):
    r = mr.upsert(
        name="Green roll A",
        color="G",
        slot_tier="common",
        effects=[_ef(E_CHAR), _ef(E_NONE), _ef(E_ATTACK)],
        debuff=None,
        path=tmp_relics_path,
    )
    assert r.id
    assert r.attr_ids == [E_CHAR, E_NONE, E_ATTACK]
    assert r.slot_tier == "common"
    assert r.color == "G"
    assert r.debuff_id is None

    loaded = mr.get(r.id, path=tmp_relics_path)
    assert loaded is not None
    assert loaded == r


def test_upsert_autosorts_attrs(tmp_relics_path):
    """Passing effects out of sort_index order must be re-ordered on save."""
    r = mr.upsert(
        name="unsorted input",
        color="U",
        slot_tier="common",
        effects=[_ef(E_ATTACK), _ef(E_CHAR), _ef(E_NONE)],   # 600, 60, 444
        debuff=None,
        path=tmp_relics_path,
    )
    assert r.attr_ids == [E_CHAR, E_NONE, E_ATTACK]          # 60, 444, 600


def test_upsert_rejects_invalid_relic(tmp_relics_path):
    """Two CHARACTER-group effects on one relic violate roll-group uniqueness."""
    with pytest.raises(ValueError, match="relic failed validation"):
        mr.upsert(
            name="illegal double-character",
            color="G",
            slot_tier="common",
            effects=[_ef(E_CHAR), _ef(E_CHAR_2)],
            debuff=None,
            path=tmp_relics_path,
        )
    assert not tmp_relics_path.exists() or mr.load_all(tmp_relics_path) == []


def test_upsert_rejects_wrong_tier(tmp_relics_path):
    """STD effects declared on a deep slot are hard-rejected by the tier gate."""
    with pytest.raises(ValueError, match="relic failed validation"):
        mr.upsert(
            name="wrong tier",
            color="G",
            slot_tier="deep",
            effects=[_ef(E_CHAR), _ef(E_NONE)],   # STD-only, fails deep gate
            debuff=None,
            path=tmp_relics_path,
        )


def test_upsert_rejects_empty_name(tmp_relics_path):
    with pytest.raises(ValueError, match="name is required"):
        mr.upsert(
            name="   ",
            color="G",
            slot_tier="common",
            effects=[_ef(E_CHAR)],
            debuff=None,
            path=tmp_relics_path,
        )


def test_upsert_rejects_bad_color(tmp_relics_path):
    with pytest.raises(ValueError, match="color must be"):
        mr.upsert(
            name="weird color",
            color="Z",
            slot_tier="common",
            effects=[_ef(E_CHAR)],
            debuff=None,
            path=tmp_relics_path,
        )


def test_upsert_rejects_none_slot_tier(tmp_relics_path):
    """'none' is validator-only — real relics always have a concrete tier."""
    with pytest.raises(ValueError, match="slot_tier must be"):
        mr.upsert(
            name="no tier",
            color="G",
            slot_tier="none",
            effects=[_ef(E_CHAR)],
            debuff=None,
            path=tmp_relics_path,
        )


def test_upsert_replaces_by_id(tmp_relics_path):
    r1 = mr.upsert(
        name="first",
        color="G",
        slot_tier="common",
        effects=[_ef(E_CHAR)],
        debuff=None,
        path=tmp_relics_path,
    )
    r2 = mr.upsert(
        relic_id=r1.id,
        name="first renamed",
        color="Y",
        slot_tier="common",
        effects=[_ef(E_CHAR), _ef(E_NONE)],
        debuff=None,
        path=tmp_relics_path,
    )
    assert r2.id == r1.id
    assert r2.created_at == r1.created_at   # preserved across update
    all_ = mr.load_all(tmp_relics_path)
    assert len(all_) == 1
    assert all_[0].name == "first renamed"
    assert all_[0].color == "Y"
    assert all_[0].attr_ids == [E_CHAR, E_NONE]


def test_delete_removes_only_matching_id(tmp_relics_path):
    r1 = mr.upsert(name="a", color="G", slot_tier="common",
                   effects=[_ef(E_CHAR)], debuff=None, path=tmp_relics_path)
    r2 = mr.upsert(name="b", color="R", slot_tier="common",
                   effects=[_ef(E_NONE)], debuff=None, path=tmp_relics_path)
    assert mr.delete(r1.id, path=tmp_relics_path) is True
    assert mr.delete("nonexistent-id", path=tmp_relics_path) is False
    remaining = mr.load_all(tmp_relics_path)
    assert [r.id for r in remaining] == [r2.id]


def test_load_all_tolerates_corrupt_file(tmp_relics_path):
    tmp_relics_path.write_text("{not json", encoding="utf-8")
    assert mr.load_all(tmp_relics_path) == []


def test_load_all_missing_file_returns_empty(tmp_relics_path):
    assert not tmp_relics_path.exists()
    assert mr.load_all(tmp_relics_path) == []


def test_export_import_round_trip(tmp_relics_path, tmp_path):
    r1 = mr.upsert(name="alpha", color="G", slot_tier="common",
                   effects=[_ef(E_CHAR), _ef(E_NONE)], debuff=None,
                   path=tmp_relics_path)
    r2 = mr.upsert(name="beta", color="R", slot_tier="common",
                   effects=[_ef(E_ATTACK)], debuff=None, path=tmp_relics_path)
    payload = mr.export_relics([r1.id, r2.id], path=tmp_relics_path)
    assert payload["type"] == "relics"
    assert len(payload["items"]) == 2

    dst = tmp_path / "fresh.json"
    report = mr.import_relics(payload, path=dst)
    assert report.imported == 2
    assert [r.id for r in mr.load_all(dst)] == [r1.id, r2.id]


def test_import_skips_duplicate_by_default(tmp_relics_path):
    r1 = mr.upsert(name="dup", color="G", slot_tier="common",
                   effects=[_ef(E_CHAR)], debuff=None, path=tmp_relics_path)
    payload = mr.export_relics([r1.id], path=tmp_relics_path)
    report = mr.import_relics(payload, path=tmp_relics_path)
    assert report.imported == 0 and report.skipped == 1


def test_import_overwrite_replaces_by_id(tmp_relics_path):
    r1 = mr.upsert(name="orig", color="G", slot_tier="common",
                   effects=[_ef(E_CHAR)], debuff=None, path=tmp_relics_path)
    payload = mr.export_relics([r1.id], path=tmp_relics_path)
    payload["items"][0]["name"] = "renamed by import"
    report = mr.import_relics(payload, overwrite=True, path=tmp_relics_path)
    assert report.overwritten == 1
    loaded = mr.get(r1.id, path=tmp_relics_path)
    assert loaded and loaded.name == "renamed by import"


def test_import_rejects_wrong_type(tmp_relics_path):
    bad = {"schema": mr.EXPORT_SCHEMA, "type": "builds", "items": []}
    report = mr.import_relics(bad, path=tmp_relics_path)
    assert report.errors and "Wrong type" in report.errors[0]


def test_import_flags_malformed_items(tmp_relics_path):
    good = mr.upsert(name="good", color="G", slot_tier="common",
                     effects=[_ef(E_CHAR)], debuff=None, path=tmp_relics_path)
    payload = mr.export_relics([good.id], path=tmp_relics_path)
    # Inject an item with a bad color code.
    payload["items"].append({
        "id": "bad-uuid", "name": "garbage", "color": "Z",
        "slot_tier": "common", "attr_ids": [E_CHAR], "debuff_id": None,
        "created_at": "2026-04-20T00:00:00+00:00",
        "updated_at": "2026-04-20T00:00:00+00:00",
    })
    report = mr.import_relics(payload, path=tmp_relics_path)
    assert any("invalid color" in e for e in report.errors)
    # 'good' was already present → skipped; malformed → error; net 0 imported.
    assert report.imported == 0


def test_storage_is_global_not_scoped(tmp_relics_path):
    """MyRelic JSON has no character_id field — single inventory across chars."""
    mr.upsert(name="shared", color="G", slot_tier="common",
              effects=[_ef(E_CHAR)], debuff=None, path=tmp_relics_path)
    raw = json.loads(tmp_relics_path.read_text(encoding="utf-8"))
    assert "character_id" not in raw[0]
