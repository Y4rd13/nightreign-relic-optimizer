FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

# Bun is Reflex's default runtime for installing frontend packages.
RUN curl -fsSL https://bun.sh/install | bash \
    && ln -s /root/.bun/bin/bun /usr/local/bin/bun
ENV BUN_INSTALL=/root/.bun
ENV PATH=$BUN_INSTALL/bin:$PATH

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY rxconfig.py ./
COPY assets/ ./assets/
COPY nr_app/ ./nr_app/
COPY src/ ./src/
COPY data/ ./data/

# Build the Reflex frontend bundle (installs npm/bun deps + next build).
# Using `reflex run --env prod` bootstraps frontend + backend on first run;
# doing it during docker build lets the image start instantly at runtime.
ENV REFLEX_TELEMETRY_ENABLED=false
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev && \
    uv run reflex init && \
    uv run reflex export --env prod --frontend-only --no-zip


FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    REFLEX_TELEMETRY_ENABLED=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

# Install bun to a system-wide location so the unprivileged user can run it.
RUN curl -fsSL https://bun.sh/install | bash \
    && mv /root/.bun/bin/bun /usr/local/bin/bun \
    && chmod +x /usr/local/bin/bun

RUN groupadd --system app && useradd --system --gid app --home /app --shell /bin/false app

WORKDIR /app

COPY --from=builder --chown=app:app /app /app

# Pre-create the reflex cache dir so the unprivileged runtime user can write.
ENV REFLEX_DIR=/app/.reflex_cache
# `user_data/` is the bind-mount target for persistent presets — kept outside
# /app/data/ (which the image owns) so `docker build` rebuilds never wipe it.
ENV NIGHTREIGN_PRESETS_FILE=/app/user_data/presets.json
RUN mkdir -p /app/.reflex_cache /app/.local /app/.cache /app/user_data && \
    chown -R app:app /app/.reflex_cache /app/.local /app/.cache /app/user_data

USER app

EXPOSE 3000 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000').read()"

CMD ["reflex", "run", "--env", "prod"]
