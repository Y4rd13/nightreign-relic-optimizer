"""Reflex config. Runs on port 8502 so it can live alongside Streamlit (8501)."""

import reflex as rx

config = rx.Config(
    app_name="nr_app",
    frontend_port=3000,
    backend_port=8000,
    # Use a single origin for Reflex (it serves frontend + backend behind the
    # same port in prod via `reflex run --env prod`).
    telemetry_enabled=False,
    show_built_with_reflex=False,
)
