# Contexto de build: la RAÍZ del repo (necesita backend/ y prompts/).
#   docker build -f backend/Dockerfile .
FROM python:3.12-slim

# Fase 3 agregará aquí las librerías nativas de WeasyPrint (pango, harfbuzz).
COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PROMPTS_DIR=/app/prompts

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY prompts ./prompts

RUN useradd --create-home appuser
USER appuser

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
# Railway inyecta $PORT.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
