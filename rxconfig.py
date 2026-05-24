"""Reflex config.

Frontend runs on :3000 and the backend WebSocket on :8000. In production both
sit behind a single port via Caddy (see Caddyfile), so the compiled frontend
must reach the backend at the public origin rather than localhost:8000. That
origin is baked into the bundle at build time, hence the NIGHTREIGN_API_URL env
override; the default keeps two-port local dev working unchanged.
"""

from __future__ import annotations

import os

import reflex as rx

api_url = os.environ.get("NIGHTREIGN_API_URL", "http://localhost:8000")

config = rx.Config(
    app_name="nr_app",
    frontend_port=3000,
    backend_port=8000,
    api_url=api_url,
    telemetry_enabled=False,
    show_built_with_reflex=False,
)
