# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Only what ONNX Runtime and Pillow actually need at runtime.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------------------------- #
# deps
# --------------------------------------------------------------------------- #
FROM base AS deps

COPY pyproject.toml README.md ./
COPY app ./app
# Install into a prefix we can copy wholesale into the runtime stage, keeping
# build tooling and pip caches out of the final image.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .

# --------------------------------------------------------------------------- #
# test - used by CI, never shipped
# --------------------------------------------------------------------------- #
FROM deps AS test

COPY pyproject.toml README.md ./
COPY tests ./tests
COPY scripts ./scripts
COPY contracts ./contracts
RUN /opt/venv/bin/pip install "pytest==9.1.1" "pytest-cov==7.1.0" "pytest-asyncio>=0.24,<2" \
    "httpx==0.28.1" "ruff==0.17.2" "mypy==2.4.0" "openapi-spec-validator==0.9.0" \
    "pyyaml==6.0.3" "jsonschema==4.26.0" "pip-audit==2.10.1" "onnx>=1.17,<2"

CMD ["/opt/venv/bin/python", "-m", "pytest"]

# --------------------------------------------------------------------------- #
# runtime
# --------------------------------------------------------------------------- #
FROM base AS runtime

RUN groupadd --system --gid 1001 vision \
    && useradd --system --uid 1001 --gid vision --create-home vision

COPY --from=deps /opt/venv /opt/venv
COPY --chown=vision:vision app ./app
COPY --chown=vision:vision contracts ./contracts
COPY --chown=vision:vision scripts ./scripts

# Models are deliberately not baked into the image: they are mounted at deploy
# time (VISION_MODEL_DIR) so a model-only release does not need a new image.
RUN mkdir -p /app/models && chown vision:vision /app/models

ENV PATH="/opt/venv/bin:$PATH" \
    VISION_APP_ENV=production \
    PORT=8001

USER vision

EXPOSE 8001

# readyz, not livez: a container whose models failed to load is alive but
# cannot serve, and must not be reported healthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:${PORT}/readyz || exit 1

CMD ["sh", "-c", "exec uvicorn app.asgi:app --host 0.0.0.0 --port ${PORT} --workers 1 --no-server-header"]
