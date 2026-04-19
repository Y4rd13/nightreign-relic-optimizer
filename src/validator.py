"""Single-relic validator used by the Validator tab.

Given a user-built relic (1 to 3 attrs, optional debuff, tier gate), run every
Nightreign roll rule and report results per-rule, with a severity ('error' or
'warning') so the UI can colour-code them.  Also exposes a helper to
auto-sort attrs by ascending `sort_index` (the in-game display order rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .constraints import EXCLUSIVE_GROUPS, CURSE_GROUP
from .effects_db import Effect, _family_key


@dataclass
class ValidationResult:
    rule: str
    ok: bool
    severity: str  # 'error' | 'warning' | 'info'
    message: str


def _group_counts(attrs: Sequence[Effect]) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in attrs:
        out[a.group] = out.get(a.group, 0) + 1
    return out


def auto_sort(attrs: Sequence[Effect]) -> list[Effect]:
    """Return attrs re-ordered to the canonical ascending-sort_index order."""
    return sorted(attrs, key=lambda a: (a.sort_index, a.effect_id))


def validate_relic(
    attrs: Sequence[Effect],
    *,
    debuff: Effect | None = None,
    slot_tier_set: frozenset[str] | None = None,
    character_tag: str | None = None,
) -> list[ValidationResult]:
    """Run every Nightreign rule on a single relic.

    Parameters
    ----------
    attrs          : 1 to 3 Effects (ordered as the user placed them)
    debuff         : optional CURSE effect attached to this relic
    slot_tier_set  : if provided, every attr's tier must be in this set
                     (e.g. {"STD","BTH"} for common slots, {"DoN","BTH"} for deep)
    character_tag  : if provided, any character-tagged attr must match
    """
    out: list[ValidationResult] = []

    # 1.  Attr count
    if len(attrs) == 0:
        out.append(ValidationResult("attr_count", False, "error", "Relic is empty."))
    elif len(attrs) > 3:
        out.append(ValidationResult(
            "attr_count", False, "error",
            f"Too many attributes: {len(attrs)}/3 (Grand relics hold 3).",
        ))
    else:
        out.append(ValidationResult(
            "attr_count", True, "info",
            f"{len(attrs)}/3 attributes filled.",
        ))

    # 2.  Duplicate effect IDs within the same relic
    ids = [a.effect_id for a in attrs]
    dupes = [i for i in set(ids) if ids.count(i) > 1]
    if dupes:
        out.append(ValidationResult(
            "duplicate_ids", False, "error",
            f"Same effect repeated on the relic: {dupes}. Only stackable NONE "
            f"effects with distinct IDs can repeat.",
        ))
    else:
        out.append(ValidationResult(
            "duplicate_ids", True, "info", "No duplicate effect IDs.",
        ))

    # 3.  Roll group uniqueness (except NONE)
    counts = _group_counts(attrs)
    bad_groups = [g for g, n in counts.items() if g in EXCLUSIVE_GROUPS and n > 1]
    if bad_groups:
        out.append(ValidationResult(
            "roll_groups", False, "error",
            f"Multiple effects share an exclusive roll group: {bad_groups}. "
            f"Only `NONE` can appear more than once on a single relic.",
        ))
    else:
        out.append(ValidationResult(
            "roll_groups", True, "info",
            "Roll groups OK (each non-NONE group appears at most once).",
        ))

    # 4.  Family uniqueness within the relic (Str +1 vs Str +3 etc)
    seen_fams: dict[str, int] = {}
    fam_conflicts: list[tuple[str, list[int]]] = []
    for a in attrs:
        seen_fams.setdefault(a.family, []).append(a.effect_id) if False else None
    # cleaner loop
    fams: dict[str, list[int]] = {}
    for a in attrs:
        fams.setdefault(a.family, []).append(a.effect_id)
    for f, fids in fams.items():
        if len(fids) > 1:
            fam_conflicts.append((f, fids))
    if fam_conflicts:
        msgs = "; ".join(f"'{f}' → {ids}" for f, ids in fam_conflicts)
        out.append(ValidationResult(
            "family_dedup", False, "warning",
            f"Multiple tiers of the same effect family — only the strongest applies: {msgs}",
        ))
    else:
        out.append(ValidationResult(
            "family_dedup", True, "info",
            "No family tier conflicts.",
        ))

    # 5.  Ascending sort_index (in-game display rule)
    display_idx = [a.sort_index for a in attrs]
    if display_idx != sorted(display_idx):
        out.append(ValidationResult(
            "sort_order", False, "error",
            f"Attributes are not in ascending sort_index order: "
            f"{display_idx}. Use Auto-sort to fix.",
        ))
    else:
        out.append(ValidationResult(
            "sort_order", True, "info",
            f"Ascending sort order respected: {display_idx}.",
        ))

    # 6.  Tier gate
    if slot_tier_set is not None:
        bad_tier = [a for a in attrs if a.tier not in slot_tier_set]
        if bad_tier:
            names = ", ".join(f"{a.effect_id} ({a.tier})" for a in bad_tier)
            out.append(ValidationResult(
                "tier_gate", False, "error",
                f"Effect tier not allowed in this slot "
                f"(expected {sorted(slot_tier_set)}): {names}",
            ))
        else:
            out.append(ValidationResult(
                "tier_gate", True, "info",
                f"All tiers within {sorted(slot_tier_set)}.",
            ))

    # 7.  Debuff linkage
    y_flag_attrs = [a for a in attrs if a.flag == "Y"]
    if y_flag_attrs:
        if debuff is None:
            out.append(ValidationResult(
                "debuff_required", False, "error",
                f"{len(y_flag_attrs)} Y-flag effect(s) on this relic require a "
                f"Debuff (CURSE) attached, but none is set.",
            ))
        elif debuff.group != CURSE_GROUP:
            out.append(ValidationResult(
                "debuff_type", False, "error",
                f"Debuff slot must hold a CURSE effect, got {debuff.group}.",
            ))
        else:
            out.append(ValidationResult(
                "debuff_required", True, "info",
                f"Y-flag effects present ({len(y_flag_attrs)}); debuff "
                f"{debuff.effect_id} ({debuff.name}) assigned.",
            ))
    elif debuff is not None:
        out.append(ValidationResult(
            "debuff_not_needed", True, "warning",
            "No Y-flag effects on this relic, so a Debuff is optional — "
            "leaving it set is harmless but unnecessary.",
        ))
    else:
        out.append(ValidationResult(
            "debuff_not_needed", True, "info",
            "No Y-flag effects and no debuff: clean relic.",
        ))

    # 8.  Character tag compatibility
    if character_tag:
        mismatches = []
        for a in attrs:
            t = a.character_tag
            if t and t.lower() != character_tag.lower():
                mismatches.append((a.effect_id, t))
        if mismatches:
            msgs = ", ".join(f"{eid} [{tag}]" for eid, tag in mismatches)
            out.append(ValidationResult(
                "character_tag", False, "error",
                f"Effects tagged for a different character: {msgs} "
                f"(current character: {character_tag}).",
            ))
        else:
            out.append(ValidationResult(
                "character_tag", True, "info",
                f"All character-tagged effects match {character_tag}.",
            ))

    return out


def summary(results: Sequence[ValidationResult]) -> dict[str, int]:
    counts = {"error": 0, "warning": 0, "info": 0}
    for r in results:
        counts[r.severity] = counts.get(r.severity, 0) + (0 if r.ok else 1)
    return counts


def is_valid(results: Sequence[ValidationResult]) -> bool:
    return all(r.ok for r in results if r.severity == "error")
