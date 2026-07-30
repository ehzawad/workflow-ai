FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --all-extras --no-editable

COPY vault ./vault
COPY evals ./evals
COPY examples ./examples

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/.workflow-ai \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080
VOLUME ["/app/vault", "/app/.workflow-ai"]

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"

ENTRYPOINT ["workflow-ai"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]
