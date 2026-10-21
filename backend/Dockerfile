# Contexto de build: la RAÍZ del repo (necesita backend/, prompts/ y templates/).
#   docker build -f backend/Dockerfile .
FROM python:3.12-slim

# Librerías nativas de WeasyPrint.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 \
    PROMPTS_DIR=/app/prompts TEMPLATES_DIR=/app/templates

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY prompts ./prompts
COPY templates ./templates

RUN useradd --create-home appuser
USER appuser

# En la imagen se corre siempre como producción: valida la configuración al arrancar y
# no publica /docs. Para probar la imagen en local pasa -e ENVIRONMENT=development.
ENV PATH="/app/.venv/bin:$PATH" ENVIRONMENT=production
EXPOSE 8000
# Railway inyecta $PORT.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
