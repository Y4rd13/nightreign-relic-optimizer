"""Slot-level relic rules: tier gating, roll groups, sort order, debuff linkage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .effects_db import (
    ATTRIBUTE_GROUPS,
    CURSE_GROUP,
    EXCLUSIVE_GROUPS,
    Effect,
)

COMMON_TIERS = {"STD", "BTH"}
DEEP_TIERS = {"DoN", "BTH"}
ATTRS_PER_RELIC = 3
TOTAL_RELICS = 6


@dataclass
class RelicSlot:
    index: int
    name: str
    allowed_tiers: frozenset[str]
    color_hint: str = ""
    is_fixed: bool = False
    fixed_effects: tuple[int, ...] = ()
    fixed_locked_labels: tuple[str, ...] = ()

    @property
    def is_deep(self) -> bool:
        return "DoN" in self.allowed_tiers and "STD" not in self.allowed_tiers


MODE_STANDARD = "standard"
MODE_DEEP_NIGHT = "don"


def default_slots(
    mode: str = MODE_DEEP_NIGHT,
    character_id: str | None = None,
    override_remembrance: bool = True,   # kept for call-site compat; ignored now
) -> list[RelicSlot]:
    """Build the slot layout for the chosen game mode.

    - MODE_STANDARD: 3 relics, all STD/BTH, no Deep slots.
    - MODE_DEEP_NIGHT: 6 relics, slots 1-3 STD/BTH, slots 4-6 DoN/BTH.

    No slot is pre-fixed any more: the solver evaluates every candidate
    (free-rolled + named-relic bundles) and picks the best combination on
    its own. If it chooses a Remembrance/shop/boss named relic, that relic's
    three fixed effects are locked into the slot as a group — `src/solver.py
    ::_named_relic_sweep()` is where that bundle comparison happens.
    """
    slot_1 = RelicSlot(
        0,
        "Slot 1 — Common Grand",
        frozenset(COMMON_TIERS),
        color_hint="green",
        is_fixed=False,
    )
    commons = [
        slot_1,
        RelicSlot(1, "Slot 2 — Common Grand", frozenset(COMMON_TIERS), color_hint="yellow"),
        RelicSlot(2, "Slot 3 — Common Grand", frozenset(COMMON_TIERS), color_hint="any"),
    ]
    if mode == MODE_STANDARD:
        return commons
    deeps = [
        RelicSlot(3, "Slot 4 — Deep Grand", frozenset(DEEP_TIERS), color_hint="blue"),
        RelicSlot(4, "Slot 5 — Deep Grand", frozenset(DEEP_TIERS), color_hint="green"),
        RelicSlot(5, "Slot 6 — Deep Grand", frozenset(DEEP_TIERS), color_hint="yellow"),
    ]
    return commons + deeps


def _remembrance_fixed_for(character_id: str | None) -> dict:
    fallback = {
        "name": "Glass Necklace",
        "fixed_effects": [7036800, 7000902],
        "locked_labels": ["Successive Attacks Boost Attack Power"],
        "color_hint": "green",
    }
    if character_id is None:
        return fallback
    try:
        from . import characters as chars_mod
        c = chars_mod.get(character_id)
    except KeyError:
        return fallback
    if c.remembrance_slots:
        r = c.remembrance_slots[0]
        return {
            "name": r.get("name", "Remembrance Relic"),
            "fixed_effects": r.get("fixed_effects", []),
            "locked_labels": r.get("locked_labels", []),
            "color_hint": r.get("color_hint", "green"),
        }
    # Character has no remembrance declared → free slot (no fixed effects)
    return {
        "name": f"{c.name} Remembrance",
        "fixed_effects": [],
        "locked_labels": [],
        "color_hint": "green",
    }


@dataclass
class RelicBuild:
    slot: RelicSlot
    attrs: list[Effect] = field(default_factory=list)
    debuff: Effect | None = None

    def free_slots(self) -> int:
        return ATTRS_PER_RELIC - len(self.attrs)

    def has_group(self, group: str) -> bool:
        return any(a.group == group for a in self.attrs)

    def group_count(self, group: str) -> int:
        return sum(1 for a in self.attrs if a.group == group)

    def ids(self) -> list[int]:
        return [a.effect_id for a in self.attrs]

    def can_accept(self, eff: Effect) -> tuple[bool, str]:
        if eff.tier not in self.slot.allowed_tiers:
            return False, f"tier {eff.tier} not allowed in {self.slot.name}"
        if self.free_slots() <= 0:
            return False, "slot full"
        if eff.group in EXCLUSIVE_GROUPS and self.has_group(eff.group):
            return False, f"group {eff.group} already filled"
        if eff.group not in ATTRIBUTE_GROUPS:
            return False, f"group {eff.group} is not a valid attribute group"
        return True, ""

    def add(self, eff: Effect) -> None:
        ok, reason = self.can_accept(eff)
        if not ok:
            raise ValueError(f"cannot add {eff.effect_id}: {reason}")
        self.attrs.append(eff)
        self.attrs.sort(key=lambda a: (a.sort_index, a.effect_id))

    def remove_at(self, attr_idx: int) -> Effect:
        return self.attrs.pop(attr_idx)

    def needs_debuff(self) -> bool:
        return any(a.flag == "Y" for a in self.attrs)


def build_initial(slots: Sequence[RelicSlot], effects_by_id: dict[int, Effect]) -> list[RelicBuild]:
    out = []
    for s in slots:
        b = RelicBuild(slot=s)
        if s.is_fixed:
            for eid in s.fixed_effects:
                b.attrs.append(effects_by_id[eid])
            b.attrs.sort(key=lambda a: (a.sort_index, a.effect_id))
        out.append(b)
    return out


def validate_build(build: Sequence[RelicBuild]) -> list[str]:
    errors: list[str] = []
    for b in build:
        if b.slot.is_fixed:
            continue
        if len(b.attrs) > ATTRS_PER_RELIC:
            errors.append(f"{b.slot.name}: too many attrs ({len(b.attrs)})")
        for g in EXCLUSIVE_GROUPS:
            if b.group_count(g) > 1:
                errors.append(f"{b.slot.name}: {g} appears more than once")
        for a in b.attrs:
            if a.tier not in b.slot.allowed_tiers:
                errors.append(
                    f"{b.slot.name}: effect {a.effect_id} is tier {a.tier}, "
                    f"not allowed (required {sorted(b.slot.allowed_tiers)})"
                )
        sorted_idx = [a.sort_index for a in b.attrs]
        if sorted_idx != sorted(sorted_idx):
            errors.append(f"{b.slot.name}: attrs are not in ascending sort_index order")
        if b.needs_debuff() and b.debuff is None:
            errors.append(f"{b.slot.name}: at least one Y-flag effect but no debuff selected")
    return errors
