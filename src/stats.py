"""Character stats: base grades, raw-point thresholds, and relic-applied deltas.

Grade thresholds are *approximate* — From's published numbers are not fully
datamined for every stat. Known anchors: STR S ≈ 70 pts, INT S ≈ 50 pts.
Others are interpolated so that +20-point character-swap curses can plausibly
shift a stat by 1-2 letter grades (matching community playtesting).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

STAT_THRESHOLDS: dict[str, dict[str, int]] = {
    "strength":     {"D": 0, "C": 26, "B": 41, "A": 56, "S": 70},
    "dexterity":    {"D": 0, "C": 21, "B": 36, "A": 51, "S": 65},
    "intelligence": {"D": 0, "C": 16, "B": 26, "A": 36, "S": 50},
    "faith":        {"D": 0, "C": 16, "B": 26, "A": 36, "S": 50},
    "arcane":       {"D": 0, "C": 16, "B": 29, "A": 41, "S": 55},
    "vigor":        {"D": 0, "C": 21, "B": 36, "A": 51, "S": 70},
    "endurance":    {"D": 0, "C": 16, "B": 26, "A": 36, "S": 50},
    "mind":         {"D": 0, "C": 16, "B": 26, "A": 36, "S": 50},
}

STAT_ORDER = ["vigor", "mind", "endurance", "strength", "dexterity", "intelligence", "faith", "arcane"]
STAT_ABBR = {"vigor": "VGR", "mind": "MND", "endurance": "END",
             "strength": "STR", "dexterity": "DEX", "intelligence": "INT",
             "faith": "FAI", "arcane": "ARC"}
GRADES = ["D", "C", "B", "A", "S"]
GRADE_INDEX = {g: i for i, g in enumerate(GRADES)}


def grade_to_base_raw(stat: str, grade: str) -> int:
    """Midpoint raw value for a grade — used to seed the character's baseline."""
    if stat not in STAT_THRESHOLDS or grade not in GRADES:
        return 0
    lo = STAT_THRESHOLDS[stat][grade]
    idx = GRADE_INDEX[grade]
    if idx < len(GRADES) - 1:
        hi = STAT_THRESHOLDS[stat][GRADES[idx + 1]]
        return (lo + hi) // 2
    return lo + 15


def raw_to_grade(stat: str, raw: int) -> str:
    if stat not in STAT_THRESHOLDS:
        return "D"
    thresholds = STAT_THRESHOLDS[stat]
    current = "D"
    for g in GRADES:
        if raw >= thresholds[g]:
            current = g
    return current


_STAT_EFFECTS_CACHE: dict[int, dict[str, int]] | None = None


def _load_stat_effects() -> dict[int, dict[str, int]]:
    global _STAT_EFFECTS_CACHE
    if _STAT_EFFECTS_CACHE is None:
        p = Path(__file__).parent.parent / "data" / "stat_effects.json"
        raw = json.loads(p.read_text())
        _STAT_EFFECTS_CACHE = {
            int(k): v for k, v in raw.items()
            if not k.startswith("_") and isinstance(v, dict)
        }
    return _STAT_EFFECTS_CACHE


def stat_deltas_for_effect(effect_id: int) -> dict[str, int]:
    return _load_stat_effects().get(effect_id, {})


def compute_effective_stats(
    base_stats: dict[str, str],
    active_effect_ids: Iterable[int],
) -> dict[str, dict]:
    """Apply active relic effects to base grades → effective raw + grade per stat.

    Returns:
        dict[stat_full_name] -> {
            "base_grade": str ("D"-"S"),
            "base_raw": int,
            "delta": int (signed),
            "raw": int (final after clamp to ≥0),
            "grade": str (effective letter grade),
        }
    """
    deltas: dict[str, int] = {s: 0 for s in STAT_THRESHOLDS}
    lookup = _load_stat_effects()
    for eid in active_effect_ids:
        d = lookup.get(int(eid), {})
        for k, v in d.items():
            if k in deltas:
                deltas[k] += v

    out: dict[str, dict] = {}
    for stat in STAT_THRESHOLDS:
        grade = base_stats.get(stat, "D")
        base_raw = grade_to_base_raw(stat, grade)
        final_raw = max(0, base_raw + deltas[stat])
        out[stat] = {
            "base_grade": grade,
            "base_raw": base_raw,
            "delta": deltas[stat],
            "raw": final_raw,
            "grade": raw_to_grade(stat, final_raw),
        }
    return out


def grade_numeric(grade: str) -> float:
    """D→1, C→2, B→3, A→4, S→5 — for radar-chart axis values."""
    return float(GRADE_INDEX.get(grade, 0) + 1)


def raw_to_numeric_fractional(stat: str, raw: int) -> float:
    """Like grade_numeric but interpolated within each tier so the radar
    chart moves smoothly with sub-grade point increases (+3 Strength on a
    C-grade character bumps the value slightly even if the letter doesn't
    flip to B). D→1.0, D+half→1.5, C→2.0, ..., S→5.0, S+anything→max 5.5."""
    if stat not in STAT_THRESHOLDS:
        return 1.0
    thresholds = STAT_THRESHOLDS[stat]
    raw = max(0, int(raw))
    for i, g in enumerate(GRADES):
        lo = thresholds[g]
        if i < len(GRADES) - 1:
            hi = thresholds[GRADES[i + 1]]
        else:
            hi = lo + 30  # S tier has no cap; approximate width
        if raw < hi or i == len(GRADES) - 1:
            # Interpolate inside this tier.
            width = max(1, hi - lo)
            frac = min(1.0, max(0.0, (raw - lo) / width))
            # i+1 = grade letter value (D=1), + frac pushes toward next tier.
            return float(i + 1) + frac
    return float(len(GRADES))
