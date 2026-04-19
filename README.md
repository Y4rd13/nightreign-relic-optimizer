# Nightreign Relic Optimizer

Multi-objective build calculator for every Nightfarer in **Elden Ring: Nightreign**.
Picks the mathematically optimal 6-relic loadout (3 common + 3 Deep of Night)
respecting every in-game rule — roll groups, sort order, tier gating,
stackability, debuff linkage — and weighs damage vs. survival vs. utility
vs. team-support according to the character's preferred playstyle.

Supports all 10 Nightfarers (Wylder, Guardian, Ironeye, Duchess, Raider,
Revenant, Recluse, Executor, Scholar, Undertaker) and both Standard mode
(3 relics) and Deep of Night mode (6 relics).

## Features

- **Multi-objective solver** — each Nightfarer declares a build-goal profile
  (Undertaker → damage, Guardian → tank, Scholar → utility, Revenant →
  team support). Sliders let you re-weight on the fly.
- **Per-attr attribution** — every effect on screen shows how much it
  contributes to the weighted score, colored by dominant axis (damage /
  survival / utility / team).
- **Defense panel** — live readout of damage negation per element, status
  resistance, max HP, poise, and per-element affinity attack %.
- **Lock system** — pin individual attributes or entire slots; the solver
  respects them and optimizes everything else around.
- **Try variant** — re-rolls the simulated-annealing seed so you can see
  near-optimal alternative compositions.
- **Presets** — save, load, compare builds; stored outside the container
  on a bind-mounted volume so rebuilds don't wipe them.
- **Validator tab** — hand-build a single relic and the UI tells you
  exactly which Nightreign rules it breaks.

## Quick start (Docker)

```bash
# 1. Clone
git clone https://github.com/Y4rd13/nightreign-relic-optimizer.git
cd nightreign-relic-optimizer

# 2. Build + run
docker build -t nightreign-optimizer .
docker run --rm \
    -p 3000:3000 -p 8000:8000 \
    -v "$(pwd)/user_data:/app/user_data" \
    --name nightreign \
    nightreign-optimizer
```

Open **http://localhost:3000**. The backend WebSocket + API runs on
port 8000. First boot takes ~3 min while Reflex builds the frontend bundle;
subsequent starts are instant.

### Persisting builds across rebuilds

The `-v "$(pwd)/user_data:/app/user_data"` flag above maps the host
`user_data/` directory to the container's preset store. Your saved
builds live in `user_data/presets.json` and survive container rebuilds,
version upgrades, and `docker rm`.

### Stopping / restarting

```bash
docker stop nightreign            # stop
docker start nightreign           # resume (same presets)
docker rm nightreign              # remove container (presets survive on host)
```

## Local development (without Docker)

Requires [uv](https://github.com/astral-sh/uv) (Python package manager) and
Python 3.10+.

```bash
uv sync                           # install deps into .venv
uv run reflex init                # one-time Reflex init
uv run reflex run                 # dev server (hot reload)
```

Runs at `http://localhost:3000`. Source changes in `nr_app/` or `src/` are
picked up automatically.

### CLI smoke test

```bash
uv run python -c "
from src.solver import optimize, OptimizerConfig
for char in ['undertaker', 'guardian', 'scholar']:
    build, contrib = optimize(OptimizerConfig(character_id=char))
    print(f'{char}: weighted={contrib.weighted_score:.1f}')
"
```

### Running tests

```bash
uv run pytest tests/              # 33 tests, ~35 s
```

## How the solver works

1. **Greedy pack** — for each of the 18 attribute slots, pick the candidate
   with the highest marginal damage gain given everything placed so far.
2. **Local search** — for every placed attr, sweep alternative candidates
   and keep the swap if it improves the weighted score.
3. **2-swap local search** — try swapping pairs of attrs between slots.
4. **Simulated annealing × 6 restarts** — escape local optima with a
   temperature-schedule random walk.
5. **Named relic sweep** — check each slot against verified named relics
   (Glass Necklace, boss drops, etc.) and swap if better.

The objective is a weighted sum:

```
final_score = damage    × w_damage
            + survival  × w_survival
            + utility   × w_utility
            + team      × w_team
```

where the four axes are independently computed from the active effect set
and the `w_*` weights come from the character's `build_goal_weights`
JSON (overridable via sidebar sliders).

## Architecture

```
src/
├── parser.py           # Cheat Engine table + CSV → data/effects.json
├── effects_db.py       # Effect model + filtering + family dedup
├── damage_model.py     # Multi-objective scoring (damage/survival/utility/team)
├── defensive_stats.py  # Defense + affinity roll-up for the UI
├── constraints.py      # RelicSlot + tier / roll-group rules
├── solver.py           # Greedy + SA + local search + attribution
├── presets.py          # Preset save/load
├── stats.py            # Stat thresholds + fractional grade numeric
├── characters.py       # Character registry + merged effect meta
└── buffs.py            # Dormant powers layer

nr_app/
├── state.py            # Reflex State (UI + derived vars + handlers)
├── components/
│   ├── sidebar.py      # Character, mode, vessel, sliders, presets
│   ├── hero.py         # Score panel + goal breakdown
│   ├── slot_card.py    # Per-slot attrs + lock toggles + contribution pills
│   ├── stats_chart.py  # Radar + multiplier stack + defense + affinity
│   ├── compare_tab.py  # Side-by-side preset comparison
│   └── my_builds_tab.py# Saved builds list with slot detail
└── nr_app.py           # Page layout + tabs

data/
├── characters/*.json   # Per-character stats, weapons, playstyle tags, goal weights
├── baseline_effects.json # Effect metadata (buckets / additives / utility values)
├── effects.json        # Parsed effect registry from CE + CSV
├── named_relics.json   # Named relic bundles (Remembrance / shop / boss drops)
├── stat_effects.json   # Stat-delta curses (STR/DEX swaps, etc.)
└── vessels.json        # Chalice color layouts

tests/                  # Pytest suite (solver, damage model, effects, presets)
```

## Data tuning status

- **Fully tuned**: Undertaker (hammer + Loathsome Hex, all 5 buckets + L18/L21/L49/L519/L525 synergies).
- **Baseline model**: the other 9 Nightfarers use generic effects (Str+3,
  Evergaol, PhysAtkUp+4, etc.) correctly but character-specific weapon +
  ability buckets need manual tuning in `data/characters/<name>.json`.

## Data sources

- `Nightreign_RelicV16.ct` — Cheat Engine table (source of truth for
  tier, flag, roll group, sort index, effect id).
- `nightreign_relic_effects.csv` — stackability + community notes.
- Manually curated multiplier values in `data/baseline_effects.json`.

## License

MIT — do whatever you want, no warranty.
