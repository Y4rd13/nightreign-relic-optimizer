# CLAUDE.md

## Project

Nightreign Relic Optimizer — Reflex SPA that picks the mathematically
optimal 6-relic build for every Nightfarer in **Elden Ring: Nightreign**
under multi-objective goal weights (damage / survival / utility / team).

## Stack

- **Framework**: Reflex 0.8+ (Python SPA compiling to React/Next.js)
- **Language**: Python 3.12
- **Package manager**: uv
- **Testing**: pytest
- **Runtime**: Docker (multi-stage uv + bun builder, unprivileged runtime)
- **Persistence**: JSON files on a bind-mounted host volume (no database)

## Architecture

Layered separation between pure-Python domain logic and the Reflex UI:

```
src/                     # Pure domain — no Reflex, no UI
├── parser.py            # Cheat Engine table + CSV → data/effects.json
├── effects_db.py        # Effect model, filtering, family dedup, caching
├── damage_model.py      # PlayContext + compute() + multi-objective scoring
├── defensive_stats.py   # Defense + affinity roll-up (regex-parsed effect text)
├── constraints.py       # RelicSlot, RelicBuild, tier gate, roll groups
├── solver.py            # Greedy + SA + local search + attribution
├── presets.py           # Preset save/load (JSON)
├── stats.py             # Stat thresholds, fractional grade numeric
├── characters.py        # Per-character JSON registry + merged effect meta
├── buffs.py             # Dormant powers
└── validator.py         # Single-relic rule validator

nr_app/                  # Reflex UI layer
├── state.py             # rx.State — ~1500 lines: state fields + @rx.var derived + event handlers
├── theme.py             # Catppuccin Mocha palette (PAL, COLOR_SLOT, etc.)
├── widgets.py           # Small reusable components (badges, pills, buttons)
├── nr_app.py            # Page layout + tab router
└── components/
    ├── sidebar.py       # Character, mode, vessel, all sliders, presets
    ├── hero.py          # Damage score + 4-axis goal panel
    ├── slot_card.py     # Per-slot attrs + lock toggles + contribution pills
    ├── stats_chart.py   # Radar + mult stack + damage sources + defense + affinity
    ├── compare_tab.py   # Side-by-side preset bar charts
    ├── my_builds_tab.py # Saved builds with slot detail
    ├── dormant_powers.py# Dormant buffs picker
    ├── named_relic_dialog.py
    ├── debuff_dialog.py
    └── edit_dialog.py

data/                    # Authoritative data (checked in)
├── characters/*.json    # One file per Nightfarer — stats, weapon_types, playstyle_tags, build_goal_weights, per-character effect overrides
├── baseline_effects.json# Damage-model metadata per effect (bucket, mult, additive, utility)
├── effects.json         # Parsed registry from the CE table (1071 entries)
├── named_relics.json    # Named relic bundles (Remembrance, shop, boss drops)
├── stat_effects.json    # Stat-delta curses (STR/DEX swaps, +1/+2/+3 lines)
└── vessels.json         # Chalice color layouts

tests/                   # Pytest — 33 tests covering the 9 bug classes we've hit
user_data/               # Runtime preset store (bind-mount target, gitignored)
```

## Commands

```bash
# Local dev
uv sync                           # install deps into .venv
uv run reflex init                # one-time Reflex init
uv run reflex run                 # dev server, hot reload at :3000

# Testing
uv run pytest tests/              # full suite (~35 s)
uv run pytest tests/test_solver.py -v  # single module

# Docker
docker build -t nightreign-optimizer .
docker run --rm -p 3000:3000 -p 8000:8000 \
    -v "$(pwd)/user_data:/app/user_data" \
    --name nightreign nightreign-optimizer
docker exec nightreign /app/.venv/bin/python3 -m pytest /app/tests
```

## Local development (Docker hot-reload)

The repo deploys via `docker build + docker run`. For iteration, use
`docker cp` to push file changes without a rebuild and `docker restart`
to pick them up — the first full build takes ~3 min, subsequent restarts
~15 s:

```bash
docker cp src/solver.py nightreign:/app/src/solver.py
docker cp nr_app/state.py nightreign:/app/nr_app/state.py
docker restart nightreign
sleep 14 && curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3000
```

## Code Conventions

- Pure-domain modules in `src/` MUST NOT import from `nr_app/`. The
  dependency flow is strictly `nr_app/ → src/`, never the other direction.
- Reflex state handlers live on `State` in `nr_app/state.py`. Event
  handlers can call into `src/` but must not perform UI rendering.
- `@rx.var` properties are pure functions of state — they must be
  deterministic so Reflex's dependency tracking works.
- Per-character data lives in `data/characters/<id>.json`. Schema:
  `{id, name, stats, weapon_types, playstyle_tags, build_goal_weights, global: {...}, effects: {...}}`.
- Effect metadata lives in `data/baseline_effects.json` (applies to all
  characters) and can be overridden per-character in
  `data/characters/<id>.json` under `effects: {"<effect_id>": {...}}`.
- `from __future__ import annotations` at the top of new Python files.
- Complete type hints; no implicit `Any`.
- Comments only in English, only when non-obvious (explain WHY, not WHAT).
- Drag sliders use `on_change` (no recompute) + `on_value_commit` (recompute)
  — never recompute on drag, only on release.

## Critical Invariants

Non-negotiable — any PR violating these is 🔴 BLOCKING in code review:

- **The solver must preserve user locks across every pass.** `_is_pinned`
  uses effect_id + occurrence count (not exact `(slot, attr_idx)` key)
  because the solver re-sorts attrs by `sort_index` after each placement
  and a position-based check would silently let SA swap locked effects
  out. Every pass (`greedy_pack`, `local_search`, `_two_swap_local_search`,
  `_simulated_annealing`, `_named_relic_sweep`) must consult `_is_pinned`.
- **`compute()` results must be identical for the same effect set + ctx.**
  The solver calls `compute()` hundreds of thousands of times per solve;
  hidden randomness would corrupt the weighted_score comparison loop.
- **`per_attr_contributions` keys must match the UI's display order.**
  When the caller provides `display_order`, the returned `(slot_idx, attr_idx)`
  keys refer to the order the UI will render — not the internal `b.attrs`
  order. Otherwise the contribution pills show up on the wrong rows.
- **Effect caches (`_GOAL_CACHE`, `_VALUE_CACHE`, `_FAMILY_CACHE`) must be
  pure functions of `effect_id` / `name`.** No character-specific or
  context-specific state can leak into them — a cache hit for Undertaker
  will be reused by Scholar.
- **Preset persistence stays in `/app/user_data/` (or `$NIGHTREIGN_PRESETS_FILE`).**
  Never write to `/app/data/` at runtime — that path is owned by the
  image and gets overwritten on `docker build`.
- **Defensive stats are derived, never stored.** `compute_defensive_stats`
  scans the active effect set every render; don't persist it or cache it
  on the preset — recomputing is cheap and avoids schema churn.
- **Character-JSON is the source of truth for stats, weapon_types,
  playstyle_tags, build_goal_weights, and per-character effect overrides.**
  Hardcoding these in `src/` is forbidden.
- **Tests cover the 9 bug classes we've fixed — they must keep passing.**
  Regressions we explicitly guard against: solver lock preservation, toggle
  of duplicate effects, fractional stat radar movement, Undertaker pool
  filter (no glintstone / guard leakage), preset round-trip with missing
  multi-objective columns, broken named relic effect IDs skipped by the
  bundle sweep.

## Multi-objective scoring

Each character declares four build-goal weights in its JSON:

```jsonc
"build_goal_weights": {
  "damage":   1.0,
  "survival": 0.2,
  "utility":  0.3,
  "team":     0.0
}
```

The damage model produces four independent axis scores per build and the
solver maximises:

```
weighted_score = damage    × w_damage
               + survival  × w_survival
               + utility   × w_utility
               + team      × w_team
```

Axes are scaled so a "pure X" build lands in ~20-200 range across
characters. Calibration constants live in `_GOAL_SCALE`
(`src/damage_model.py`). Changes to those constants re-balance the
whole solver — touch with care and re-run the full test suite.

## Performance

The solver is the hot path: ~1.5 s per character solve on the reference
build. Key optimisations already in place:

- `_classify_goal` and `_effect_value_proxy` memoised by `effect_id`
  (~2.7M calls → hash lookups).
- `_family_key` regex memoised (~1.3M calls → dict hit).
- `compute(detailed=False)` fast-path skips goal-score classification +
  bucket_report packaging for solver calls that only need `weighted_score`.
- `bucket_labels_for(character_id)` memoised via `lru_cache`.

Do not un-cache these without profiling — they're collectively worth
~3× in total solve time.

## Git Conventions

- Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`).
- Keep PRs focused — one behaviour change per PR.
- All PRs target `main`; tests must pass before merge.
