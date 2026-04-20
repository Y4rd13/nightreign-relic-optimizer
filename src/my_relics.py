"""My Relics — personal saved single-relic inventory (JSON persistence).

Unlike `presets.py` (full 6-slot build snapshots keyed by character), a
MyRelic is a single 1-to-3-attr relic the user has rolled/owns in-game.
The inventory is **global** — it is not scoped to any character, matching
how the real in-game relic inventory works across Nightfarers. Filtering
by character tag happens at display time in the named-relic dialog, not
at storage time.

Invariants enforced at upsert:
- `attr_ids` is re-sorted by `sort_index` ASC (game's display-order rule).
- `validate_relic()` is re-run; any hard error raises ValueError. This
  keeps illegal relics off disk even if the UI allows a bypass.
- `slot_tier` must be "common" or "deep" — "none" is validator-only and
  does not correspond to a real in-game slot.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .constraints import COMMON_TIERS, DEEP_TIERS
from .effects_db import Effect
from .validator import auto_sort, is_valid, validate_relic

_ALLOWED_COLORS = frozenset({"R", "G", "B", "Y", "U"})
_ALLOWED_SLOT_TIERS = frozenset({"common", "deep"})


def _default_path() -> Path:
    override = os.environ.get("NIGHTREIGN_MY_RELICS_FILE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "user_data" / "my_relics.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class MyRelic:
    id: str
    name: str
    color: str                       # R|G|B|Y|U
    slot_tier: str                   # common|deep
    attr_ids: list[int]              # 1-3, ascending sort_index
    debuff_id: int | None
    created_at: str
    updated_at: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "MyRelic":
        return cls(
            id=str(raw["id"]),
            name=str(raw.get("name", "")),
            color=str(raw.get("color", "U")),
            slot_tier=str(raw.get("slot_tier", "common")),
            attr_ids=[int(x) for x in raw.get("attr_ids", [])],
            debuff_id=int(raw["debuff_id"]) if raw.get("debuff_id") is not None else None,
            created_at=str(raw.get("created_at", _now_iso())),
            updated_at=str(raw.get("updated_at", raw.get("created_at", _now_iso()))),
        )


def load_all(path: Path | None = None) -> list[MyRelic]:
    path = path or _default_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [MyRelic.from_json(r) for r in raw]


def save_all(relics: Sequence[MyRelic], path: Path | None = None) -> None:
    path = path or _default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps([r.to_json() for r in relics], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def get(relic_id: str, path: Path | None = None) -> MyRelic | None:
    for r in load_all(path):
        if r.id == relic_id:
            return r
    return None


def _tier_set_for(slot_tier: str) -> frozenset[str]:
    if slot_tier == "common":
        return frozenset(COMMON_TIERS)
    if slot_tier == "deep":
        return frozenset(DEEP_TIERS)
    raise ValueError(f"slot_tier must be 'common' or 'deep', got {slot_tier!r}")


def upsert(
    *,
    name: str,
    color: str,
    slot_tier: str,
    effects: Sequence[Effect],
    debuff: Effect | None,
    relic_id: str | None = None,
    path: Path | None = None,
) -> MyRelic:
    """Persist a user relic, auto-sorting attrs and enforcing validation.

    Parameters
    ----------
    name      : required, trimmed and non-empty
    color     : R|G|B|Y|U — vessel-scene colour code
    slot_tier : "common" or "deep" — drives the tier-gate check
    effects   : 1-3 Effect objects (any order — will be re-sorted)
    debuff    : optional Effect (CURSE group)
    relic_id  : pass an existing id to update in place, None to create new

    Raises
    ------
    ValueError — if the relic fails any hard-severity validator rule, or
                 if required fields are missing / malformed.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    if color not in _ALLOWED_COLORS:
        raise ValueError(f"color must be one of {sorted(_ALLOWED_COLORS)}")
    if slot_tier not in _ALLOWED_SLOT_TIERS:
        raise ValueError(f"slot_tier must be one of {sorted(_ALLOWED_SLOT_TIERS)}")
    if not effects:
        raise ValueError("at least one effect is required")

    sorted_effects = auto_sort(effects)
    results = validate_relic(
        sorted_effects,
        debuff=debuff,
        slot_tier_set=_tier_set_for(slot_tier),
    )
    if not is_valid(results):
        bad = [r.message for r in results if r.severity == "error" and not r.ok]
        raise ValueError(f"relic failed validation: {'; '.join(bad)}")

    now = _now_iso()
    existing = load_all(path)
    prior = next((r for r in existing if r.id == relic_id), None) if relic_id else None
    relic = MyRelic(
        id=relic_id or str(uuid.uuid4()),
        name=name,
        color=color,
        slot_tier=slot_tier,
        attr_ids=[e.effect_id for e in sorted_effects],
        debuff_id=debuff.effect_id if debuff is not None else None,
        created_at=prior.created_at if prior else now,
        updated_at=now,
    )
    remaining = [r for r in existing if r.id != relic.id]
    remaining.append(relic)
    save_all(remaining, path)
    return relic


def delete(relic_id: str, path: Path | None = None) -> bool:
    before = load_all(path)
    after = [r for r in before if r.id != relic_id]
    if len(after) == len(before):
        return False
    save_all(after, path)
    return True
