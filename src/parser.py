"""Parse Cheat Engine .ct XML and CSV catalog into a unified effect registry."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

CE_LINE = re.compile(
    r"(?P<id>\d+):(?P<sort>\d+|N/A)\|"
    r"(?P<tier>STD|BTH|DoN|ILLEGAL|N/A)\|"
    r"(?P<flag>[YN])\|"
    r"(?P<group>[A-Z_/]+)\|"
    r"(?P<name>[^<\r\n]+?)\s*$"
)


@dataclass
class EffectRow:
    effect_id: int
    sort_index: int
    tier: str
    flag: str
    group: str
    name: str
    stackable: bool = False
    csv_details: str = ""
    csv_category: str = ""
    csv_relic: str = ""

    def ce_string(self) -> str:
        return (
            f"{self.effect_id} : {self.sort_index}|{self.tier}|{self.flag}|"
            f"{self.group}|{self.name}"
        )


def parse_ct(ct_path: Path) -> list[EffectRow]:
    seen_ids: set[int] = set()
    rows: list[EffectRow] = []
    with ct_path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            m = CE_LINE.search(raw)
            if not m:
                continue
            eid = int(m.group("id"))
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            sort_raw = m.group("sort")
            sort_val = int(sort_raw) if sort_raw.isdigit() else -1
            rows.append(
                EffectRow(
                    effect_id=eid,
                    sort_index=sort_val,
                    tier=m.group("tier"),
                    flag=m.group("flag"),
                    group=m.group("group"),
                    name=m.group("name").strip(),
                )
            )
    return rows


def _norm(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_csv_stackability(csv_path: Path) -> dict[str, tuple[bool, str, str, str]]:
    """Return normalized_name → (stackable, details, category, relic_name)."""
    out: dict[str, tuple[bool, str, str, str]] = {}
    with csv_path.open("r", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            eff = row.get("Relic Effect", "").strip()
            if not eff:
                continue
            stack_val = (row.get("Stackable") or "").strip().lower()
            stackable = stack_val.startswith("y")
            key = _norm(eff)
            out[key] = (
                stackable,
                (row.get("Details") or "").strip(),
                (row.get("Category") or "").strip(),
                (row.get("Relic Name") or "").strip(),
            )
    return out


def merge(ct_rows: list[EffectRow], csv_map: dict) -> list[EffectRow]:
    for r in ct_rows:
        key = _norm(r.name)
        hit = csv_map.get(key)
        if hit is None:
            for k, v in csv_map.items():
                if key.startswith(k) or k.startswith(key):
                    hit = v
                    break
        if hit is not None:
            r.stackable, r.csv_details, r.csv_category, r.csv_relic = hit
    return ct_rows


def write_registry(rows: list[EffectRow], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump([asdict(r) for r in rows], fh, ensure_ascii=False, indent=2)


def build_registry(
    ct_path: Path, csv_path: Path, out_path: Path
) -> list[EffectRow]:
    ct_rows = parse_ct(ct_path)
    csv_map = load_csv_stackability(csv_path)
    merged = merge(ct_rows, csv_map)
    write_registry(merged, out_path)
    return merged


if __name__ == "__main__":
    import sys

    ct = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "/mnt/c/Users/dharm/Documents/nightreign/"
        "Nightreign_RelicV16-125-16-0-1765383293/Nightreign_RelicV16.ct"
    )
    csv_p = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
        "/mnt/c/Users/dharm/Documents/nightreign/nightreign_relic_effects.csv"
    )
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(
        Path(__file__).parent.parent / "data" / "effects.json"
    )
    rows = build_registry(ct, csv_p, out)
    by_tier: dict[str, int] = {}
    by_group: dict[str, int] = {}
    stack_count = 0
    for r in rows:
        by_tier[r.tier] = by_tier.get(r.tier, 0) + 1
        by_group[r.group] = by_group.get(r.group, 0) + 1
        if r.stackable:
            stack_count += 1
    print(f"Parsed {len(rows)} effects → {out}")
    print(f"  tiers: {by_tier}")
    print(f"  groups: {by_group}")
    print(f"  stackable: {stack_count}")
