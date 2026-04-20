"""Preset storage (JSON) — save/load/diff build snapshots."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .constraints import RelicBuild
from .damage_model import BuildContribution, PlayContext
from .effects_db import Effect, effects_by_id_for_character, find_for_character


def _default_path() -> Path:
    override = os.environ.get("NIGHTREIGN_PRESETS_FILE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "data" / "presets.json"


@dataclass
class PresetSlot:
    slot_index: int
    slot_name: str
    color_hint: str
    attr_ids: list[int]
    debuff_id: int | None


@dataclass
class Preset:
    name: str
    character_id: str
    mode: str
    created_at: str
    total_boss_window: float
    ctx: dict[str, Any]
    excluded_ids: list[int]
    locked_attrs: dict[str, int]
    slots: list[PresetSlot]
    vessel_id: str | None = None
    # Derived metrics captured at save time so the compare tab can render a
    # bar chart without re-solving each preset.
    hammer_mult: float = 1.0
    hex_mult: float = 1.0
    utility_mult: float = 1.0
    additive_phys: float = 0.0        # fraction (0.18 = 18%)
    trance_uptime: float = 0.0        # effective trance uptime
    # Multi-objective breakdown — damage_score mirrors total_boss_window; the
    # others let the compare tab render all four goal axes.
    damage_score: float = 0.0
    survival_score: float = 0.0
    utility_score: float = 0.0
    team_score: float = 0.0
    weighted_score: float = 0.0
    # Snapshot of the build-goal weights used when this preset was saved.
    build_goal_weights: dict[str, float] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "Preset":
        slots = [PresetSlot(**s) for s in raw.get("slots", [])]
        return cls(
            name=raw["name"],
            character_id=raw.get("character_id", "undertaker"),
            mode=raw.get("mode", "don"),
            created_at=raw["created_at"],
            total_boss_window=float(raw.get("total_boss_window", 0.0)),
            ctx=dict(raw.get("ctx", {})),
            excluded_ids=list(raw.get("excluded_ids", [])),
            locked_attrs={str(k): int(v) for k, v in raw.get("locked_attrs", {}).items()},
            slots=slots,
            vessel_id=raw.get("vessel_id"),
            hammer_mult=float(raw.get("hammer_mult", 1.0)),
            hex_mult=float(raw.get("hex_mult", 1.0)),
            utility_mult=float(raw.get("utility_mult", 1.0)),
            additive_phys=float(raw.get("additive_phys", 0.0)),
            trance_uptime=float(raw.get("trance_uptime", 0.0)),
            damage_score=float(raw.get("damage_score", raw.get("total_boss_window", 0.0))),
            survival_score=float(raw.get("survival_score", 0.0)),
            utility_score=float(raw.get("utility_score", 0.0)),
            team_score=float(raw.get("team_score", 0.0)),
            weighted_score=float(raw.get("weighted_score", raw.get("total_boss_window", 0.0))),
            build_goal_weights={k: float(v) for k, v in (raw.get("build_goal_weights") or {}).items()},
        )


def _preset_from_build(
    name: str,
    character_id: str,
    mode: str,
    build: Sequence[RelicBuild],
    contrib: BuildContribution,
    ctx: PlayContext,
    excluded_ids: Iterable[int],
    locked_attrs: dict[tuple[int, int], int],
    vessel_id: str | None = None,
) -> Preset:
    return Preset(
        name=name,
        character_id=character_id,
        mode=mode,
        created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        total_boss_window=float(contrib.total_boss_window),
        ctx=asdict(ctx),
        excluded_ids=sorted(int(x) for x in excluded_ids),
        locked_attrs={f"{s},{a}": int(e) for (s, a), e in locked_attrs.items()},
        vessel_id=vessel_id,
        hammer_mult=float(contrib.hammer_mult),
        hex_mult=float(contrib.hex_mult),
        utility_mult=float(contrib.utility_mult),
        additive_phys=float(contrib.additive_phys),
        trance_uptime=float(contrib.trance_uptime),
        damage_score=float(contrib.damage_score),
        survival_score=float(contrib.survival_score),
        utility_score=float(contrib.utility_score),
        team_score=float(contrib.team_score),
        weighted_score=float(contrib.weighted_score),
        build_goal_weights={
            k: float(v) for k, v in (getattr(ctx, "build_goal_weights_override", None) or {}).items()
        },
        slots=[
            PresetSlot(
                slot_index=i,
                slot_name=b.slot.name,
                color_hint=b.slot.color_hint,
                attr_ids=[a.effect_id for a in b.attrs],
                debuff_id=b.debuff.effect_id if b.debuff is not None else None,
            )
            for i, b in enumerate(build)
        ],
    )


def load_all(path: Path | None = None) -> list[Preset]:
    path = path or _default_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [Preset.from_json(r) for r in raw]


def save_all(presets: Sequence[Preset], path: Path | None = None) -> None:
    path = path or _default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps([p.to_json() for p in presets], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def upsert(
    name: str,
    character_id: str,
    mode: str,
    build: Sequence[RelicBuild],
    contrib: BuildContribution,
    ctx: PlayContext,
    excluded_ids: Iterable[int],
    locked_attrs: dict[tuple[int, int], int],
    vessel_id: str | None = None,
    path: Path | None = None,
) -> Preset:
    preset = _preset_from_build(
        name=name,
        character_id=character_id,
        mode=mode,
        build=build,
        contrib=contrib,
        ctx=ctx,
        excluded_ids=excluded_ids,
        locked_attrs=locked_attrs,
        vessel_id=vessel_id,
    )
    key = (name, character_id)
    all_ = [p for p in load_all(path) if (p.name, p.character_id) != key]
    all_.append(preset)
    save_all(all_, path)
    return preset


def delete(name: str, character_id: str, path: Path | None = None) -> bool:
    before = load_all(path)
    after = [p for p in before if (p.name, p.character_id) != (name, character_id)]
    if len(after) == len(before):
        return False
    save_all(after, path)
    return True


def get(name: str, character_id: str, path: Path | None = None) -> Preset | None:
    for p in load_all(path):
        if p.name == name and p.character_id == character_id:
            return p
    return None


def list_for_character(character_id: str, path: Path | None = None) -> list[Preset]:
    return [p for p in load_all(path) if p.character_id == character_id]


EXPORT_SCHEMA = "nightreign-export/1"


@dataclass
class ImportReport:
    imported: int = 0
    skipped: int = 0
    overwritten: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"Imported {self.imported}"]
        if self.skipped:
            parts.append(f"Skipped {self.skipped}")
        if self.overwritten:
            parts.append(f"Overwrote {self.overwritten}")
        if self.errors:
            parts.append(f"Errors {len(self.errors)}")
        return " · ".join(parts)


def export_presets(
    keys: Sequence[tuple[str, str]],
    path: Path | None = None,
) -> dict[str, Any]:
    """Assemble an export payload for presets identified by (name, character_id).
    Unknown keys are silently dropped (caller pre-filters the selection)."""
    index = {(p.name, p.character_id): p for p in load_all(path)}
    items: list[dict[str, Any]] = []
    for k in keys:
        preset = index.get((k[0], k[1]))
        if preset is not None:
            items.append(preset.to_json())
    return {
        "schema": EXPORT_SCHEMA,
        "type": "builds",
        "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "items": items,
    }


def import_presets(
    payload: Any,
    *,
    overwrite: bool = False,
    path: Path | None = None,
) -> ImportReport:
    """Merge presets from a previously-exported payload into the on-disk store.

    Duplicate key is `(name, character_id)` — matching `upsert`. When
    `overwrite` is False, existing entries are left untouched and counted in
    `skipped`; when True, they are replaced and counted in `overwritten`."""
    report = ImportReport()
    if not isinstance(payload, dict):
        report.errors.append("Payload is not a JSON object")
        return report
    if payload.get("schema") != EXPORT_SCHEMA:
        report.errors.append(f"Unknown schema: {payload.get('schema')!r}")
        return report
    if payload.get("type") != "builds":
        report.errors.append(
            f"Wrong type: expected 'builds', got {payload.get('type')!r}"
        )
        return report

    items = payload.get("items")
    if not isinstance(items, list):
        report.errors.append("Payload 'items' is missing or not a list")
        return report

    existing = load_all(path)
    key_index: dict[tuple[str, str], int] = {
        (p.name, p.character_id): i for i, p in enumerate(existing)
    }
    changed = False
    for raw in items:
        try:
            preset = Preset.from_json(raw)
        except Exception as e:
            report.errors.append(f"Invalid preset: {e}")
            continue
        key = (preset.name, preset.character_id)
        if key in key_index:
            if overwrite:
                existing[key_index[key]] = preset
                report.overwritten += 1
                changed = True
            else:
                report.skipped += 1
        else:
            key_index[key] = len(existing)
            existing.append(preset)
            report.imported += 1
            changed = True

    if changed:
        save_all(existing, path)
    return report


def resolve(preset: Preset) -> list[tuple[PresetSlot, list[Effect], Effect | None]]:
    """Expand effect ids → Effect objects for rendering (character-scoped)."""
    out = []
    for s in preset.slots:
        eff_list = []
        for eid in s.attr_ids:
            try:
                eff_list.append(find_for_character(eid, preset.character_id))
            except KeyError:
                continue
        debuff_eff = None
        if s.debuff_id is not None:
            try:
                debuff_eff = find_for_character(s.debuff_id, preset.character_id)
            except KeyError:
                debuff_eff = None
        out.append((s, eff_list, debuff_eff))
    return out
