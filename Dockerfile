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
# NIGHTREIGN_API_URL is baked into the frontend bundle here, so it must be the
# public origin the browser will hit on a single-port host. Default targets the
# HF Space; override with --build-arg for local single-port testing.
ARG NIGHTREIGN_API_URL=https://y4rd13-nightreign-relic-optimizer.hf.space
ENV NIGHTREIGN_API_URL=${NIGHTREIGN_API_URL}
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

# Caddy fronts the single port (7860) Hugging Face Spaces exposes.
COPY --from=caddy:2 /usr/bin/caddy /usr/local/bin/caddy

# Hugging Face Spaces run the container as uid 1000 with HOME=/home/user.
RUN useradd -m -u 1000 user
ENV HOME=/home/user

WORKDIR /app

COPY --from=builder --chown=user:user /app /app
# Caddyfile + start.sh come straight from the build context (not via the
# builder) so editing them never busts the expensive builder export layer.
COPY --chown=user:user Caddyfile start.sh /app/

# Baked into the frontend at build time AND read at runtime by the backend for
# CORS/allowed origins — must match the public origin (see builder ARG).
ARG NIGHTREIGN_API_URL=https://y4rd13-nightreign-relic-optimizer.hf.space
ENV NIGHTREIGN_API_URL=${NIGHTREIGN_API_URL}
# Pre-create the reflex cache dir so the unprivileged runtime user can write.
ENV REFLEX_DIR=/app/.reflex_cache
# Presets and the owned-relic inventory live in the browser (localStorage) —
# the server is stateless, so there are no preset/relic files on disk. rx.upload
# still needs a writable scratch dir for transient JSON imports; /tmp is fine
# (ephemeral by design — the file is consumed immediately on upload).
ENV REFLEX_UPLOADED_FILES_DIR=/tmp/nightreign_uploads
RUN chmod +x /app/start.sh && \
    mkdir -p /app/.reflex_cache /tmp/nightreign_uploads /home/user/.local /home/user/.cache && \
    chown -R user:user /app/.reflex_cache /tmp/nightreign_uploads /home/user

USER user

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860').read()"

CMD ["bash", "/app/start.sh"]
