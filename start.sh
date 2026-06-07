#!/usr/bin/env bash
# Backend (:8000) + Caddy (:7860 single port). Reflex 0.8 prod serves no
# frontend itself — the frontend is a static bundle exported at build time and
# served by Caddy (see Caddyfile) — so we run the backend only. `wait -n`
# returns as soon as either process exits so the container crashes loudly
# instead of limping along with half the stack dead.
set -euo pipefail

reflex run --env prod --backend-only &
caddy run --config /app/Caddyfile --adapter caddyfile &

wait -n
