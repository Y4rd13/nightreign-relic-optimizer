#!/usr/bin/env bash
# Launch Reflex (frontend :3000 + backend :8000) and Caddy (:7860 single port)
# together. `wait -n` returns as soon as either process exits so the container
# crashes loudly instead of limping along with half the stack dead.
set -euo pipefail

reflex run --env prod &
caddy run --config /app/Caddyfile --adapter caddyfile &

wait -n
