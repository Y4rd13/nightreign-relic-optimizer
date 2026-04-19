"""Dormant Powers (permanent buffs earned per expedition).

Data source: data/buffs.json — auto-imported from the relics.pro xlsx
compendium. Each buff has an id, description, and 1-2 tier values.

The optimizer treats dormant powers as a separate multiplier layer: they
stack on top of the relic pool but don't interact with roll groups.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
BUFFS_PATH = ROOT / "data" / "buffs.json"


@dataclass
class BuffInfo:
    id: int
    description: str
    effect_template: str
    values: list[float]
    format: str = "pct"
    category: str = ""
    stack_self: bool | None = None
    stack_other: bool | None = None
    unobtainable: bool = False
    notes: str = ""

    def tier_value(self, tier: int) -> float:
        """Return the numeric value for tier 1 or 2 (1-indexed). 0 if missing."""
        if tier < 1 or not self.values:
            return 0.0
        idx = min(tier - 1, len(self.values) - 1)
        return self.values[idx]

    def formatted(self, tier: int) -> str:
        v = self.tier_value(tier)
        if not v:
            return self.description
        suffix = "%" if self.format == "pct" else ""
        tpl = self.effect_template or "{}"
        try:
            return tpl.format(f"{v:g}{suffix}")
        except (IndexError, KeyError, ValueError):
            return f"{self.description}  {v:g}{suffix}"


@lru_cache(maxsize=1)
def list_buffs() -> list[BuffInfo]:
    if not BUFFS_PATH.exists():
        return []
    with BUFFS_PATH.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    out: list[BuffInfo] = []
    for b in raw.get("buffs", []):
        if b.get("unobtainable"):
            continue
        out.append(BuffInfo(
            id=int(b["id"]),
            description=b.get("description", ""),
            effect_template=b.get("effect_template", ""),
            values=list(b.get("values", [])),
            format=b.get("format", "pct"),
            category=b.get("category", ""),
            stack_self=b.get("stack_self"),
            stack_other=b.get("stack_other"),
            unobtainable=bool(b.get("unobtainable", False)),
            notes=b.get("notes", ""),
        ))
    # Alphabetical by category then description for stable ordering.
    out.sort(key=lambda x: (x.category or "z", x.description))
    return out


@lru_cache(maxsize=1)
def buffs_by_id() -> dict[int, BuffInfo]:
    return {b.id: b for b in list_buffs()}


# ────────────────────────────────────────────────────────────────────
# Damage / stat impact helpers — offensive buffs add a global mult
# ────────────────────────────────────────────────────────────────────

# Keywords in description that we know affect damage directly.
_ATTACK_DESCRIPTORS = (
    "physical attack power",
    "affinity attack power",
    "attack boost",
    "improved ultimate art",
    "successive attacks boost",
    "improved stance",
    "critical hit",
    "sorceries & incantations",
)


def _is_damage_buff(b: BuffInfo) -> bool:
    d = b.description.lower()
    return any(kw in d for kw in _ATTACK_DESCRIPTORS)


@dataclass
class ActiveBuff:
    """A user-selected dormant power with a chosen tier."""
    id: int
    tier: int = 1


def resolve_active(active: Iterable[ActiveBuff]) -> list[tuple[BuffInfo, int, float]]:
    """Return (info, tier, value) triples for each active buff."""
    table = buffs_by_id()
    out = []
    for a in active:
        info = table.get(a.id)
        if info is None:
            continue
        out.append((info, a.tier, info.tier_value(a.tier)))
    return out


def global_attack_mult(active: Iterable[ActiveBuff]) -> float:
    """Compose a single multiplier from damage-related buffs.

    Treats each pct as additive within the mult (1.10 * 1.15 = 1.265),
    matching how Nightreign stacks distinct damage sources."""
    m = 1.0
    for info, _tier, value in resolve_active(active):
        if not _is_damage_buff(info) or info.format != "pct":
            continue
        m *= (1.0 + value / 100.0)
    return m


def max_stat_bonus(active: Iterable[ActiveBuff]) -> dict[str, float]:
    """Return {'hp': pct, 'fp': pct, 'stamina': pct, 'poise': pct, ...} from buffs."""
    bonuses: dict[str, float] = {}
    for info, _tier, value in resolve_active(active):
        if info.format != "pct":
            continue
        d = info.description.lower()
        if "maximum hp" in d:
            bonuses["hp"] = bonuses.get("hp", 0.0) + value
        elif "maximum fp" in d:
            bonuses["fp"] = bonuses.get("fp", 0.0) + value
        elif "maximum stamina" in d:
            bonuses["stamina"] = bonuses.get("stamina", 0.0) + value
        elif "poise" in d:
            bonuses["poise"] = bonuses.get("poise", 0.0) + value
    return bonuses
