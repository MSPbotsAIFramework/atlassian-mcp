# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv==0.13.7

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS production

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    MCP_HTTP_HOST=0.0.0.0 \
    MCP_HTTP_PORT=8080 \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/health || exit 1

CMD ["python", "-m", "uvicorn", "atlassian_mcp.server:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8080"]
