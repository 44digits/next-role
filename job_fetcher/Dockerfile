FROM ghcr.io/astral-sh/uv:0.13.8 AS uv

FROM python:3.13-slim

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src ./src
RUN groupadd --system fetcher \
    && useradd --system --gid fetcher --create-home fetcher

USER fetcher

ENTRYPOINT ["/opt/venv/bin/python", "-m", "job_fetcher"]
