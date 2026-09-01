FROM python:3.13.15-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home /app app \
    && mkdir -p /data/barcodes \
    && chown -R app:app /data/barcodes

COPY pyproject.toml README.md ./
COPY apps ./apps
COPY packages ./packages
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic-server1.ini alembic-server2.ini ./

RUN python -m pip install --no-cache-dir .

USER app

FROM base AS development

USER root
RUN python -m pip install --no-cache-dir ".[dev]"
USER app

FROM base AS runtime
