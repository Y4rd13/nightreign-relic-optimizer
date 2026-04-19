"""Character registry: loads per-character JSON + baseline_effects.json."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CHARACTERS_DIR = ROOT / "data" / "characters"
BASELINE_PATH = ROOT / "data" / "baseline_effects.json"
VESSELS_PATH = ROOT / "data" / "vessels.json"


@dataclass
class Character:
    id: str
    name: str
    dlc: str
    tag: str
    icon: str
    tagline: str
    stats: dict[str, str]
    weapon_types: list[str]
    dual_wield: bool
    skill: dict[str, str]
    ultimate: dict[str, str]
    passive: dict[str, str]
    data_quality: str
    remembrance_slots: list[dict[str, Any]]
    globals_: dict[str, Any]
    effects: dict[str, dict[str, Any]]

    @property
    def is_fully_tuned(self) -> bool:
        return self.data_quality == "full"


@lru_cache(maxsize=1)
def load_baseline() -> dict[str, Any]:
    if not BASELINE_PATH.exists():
        return {"global": {}, "effects": {}}
    with BASELINE_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_character_file(path: Path) -> Character:
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return Character(
        id=raw["id"],
        name=raw["name"],
        dlc=raw.get("dlc", "base"),
        tag=raw["tag"],
        icon=raw.get("icon", "⚔️"),
        tagline=raw.get("tagline", ""),
        stats=raw.get("stats", {}),
        weapon_types=raw.get("weapon_types", []),
        dual_wield=bool(raw.get("dual_wield", False)),
        skill=raw.get("skill", {}),
        ultimate=raw.get("ultimate", {}),
        passive=raw.get("passive", {}),
        data_quality=raw.get("data_quality", "skeleton"),
        remembrance_slots=raw.get("remembrance_slots", []),
        globals_=raw.get("global", {}),
        effects=raw.get("effects", {}),
    )


@lru_cache(maxsize=1)
def list_characters() -> list[Character]:
    if not CHARACTERS_DIR.exists():
        return []
    out = []
    for path in sorted(CHARACTERS_DIR.glob("*.json")):
        try:
            out.append(_load_character_file(path))
        except (KeyError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"failed to load {path}: {exc}") from exc
    order_map = {
        "undertaker": 0, "scholar": 1,
        "wylder": 2, "guardian": 3, "ironeye": 4, "duchess": 5,
        "raider": 6, "revenant": 7, "recluse": 8, "executor": 9,
    }
    out.sort(key=lambda c: (order_map.get(c.id, 99), c.name))
    return out


def get(character_id: str) -> Character:
    for c in list_characters():
        if c.id == character_id:
            return c
    raise KeyError(character_id)


def merged_effects_meta(character_id: str) -> dict[str, dict[str, Any]]:
    """Return effect-id → metadata dict merged from baseline + character overrides."""
    base = load_baseline().get("effects", {})
    char = get(character_id)
    merged: dict[str, dict[str, Any]] = {}
    for eid, meta in base.items():
        merged[eid] = dict(meta)
    for eid, meta in char.effects.items():
        merged.setdefault(eid, {}).update(meta)
    return merged


_BUCKET_LABEL_PREFIX = re.compile(r"^L\d+\s+")


@lru_cache(maxsize=16)
def bucket_labels_for(character_id: str) -> dict[str, str]:
    """Character-scoped lookup: bucket_key → human-readable label.

    Pure function of the merged effects meta, so memoized per character.
    Used by the UI to humanise internal bucket keys (B_L18 → "3+ Hammers
    Equipped") in the multiplier stack chart on every recompute."""
    meta = merged_effects_meta(character_id)
    out: dict[str, str] = {}
    for _eid, m in meta.items():
        bucket = m.get("bucket")
        if not bucket:
            continue
        label = str(m.get("label", "") or "")
        cleaned = _BUCKET_LABEL_PREFIX.sub("", label).strip()
        if bucket not in out or len(cleaned) > len(out[bucket]):
            out[bucket] = cleaned or bucket
    return out


def merged_globals(character_id: str) -> dict[str, Any]:
    base = dict(load_baseline().get("global", {}))
    char = get(character_id)
    base.update(char.globals_)
    return base


@lru_cache(maxsize=1)
def list_vessels() -> list[dict[str, Any]]:
    if not VESSELS_PATH.exists():
        return []
    with VESSELS_PATH.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return raw.get("vessels", [])


def vessels_for(character_id: str) -> list[dict[str, Any]]:
    return [
        v for v in list_vessels()
        if v.get("character") == character_id or v.get("character") == "any"
    ]


NAMED_RELICS_PATH = ROOT / "data" / "named_relics.json"


@lru_cache(maxsize=1)
def list_named_relics() -> list[dict[str, Any]]:
    if not NAMED_RELICS_PATH.exists():
        return []
    with NAMED_RELICS_PATH.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return raw.get("relics", [])


def named_relics_for(character_id: str) -> list[dict[str, Any]]:
    return [
        r for r in list_named_relics()
        if r.get("character") == character_id or r.get("character") == "any"
    ]


if __name__ == "__main__":
    chars = list_characters()
    print(f"{len(chars)} characters loaded:")
    for c in chars:
        marker = " ★" if c.is_fully_tuned else ""
        print(f"  {c.icon} {c.name:12s} ({c.id:10s}) · {c.tag} · {c.tagline}{marker}")
    print(f"\n{len(list_vessels())} vessels loaded")
