import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

import anthropic
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ads.results_import import MAX_BYTES as REPORT_MAX_BYTES
from app.api import ads, ads_meta, ads_results, catalog, content, cover, drive, products
from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.content.claude_client import LLMError
from app.content.engines import ContentRejected
from app.deps import get_services
from app.generators.cover_image import MAX_BYTES
from app.security import (
    BodyLimitMiddleware,
    SecurityHeadersMiddleware,
    configure_logging,
    ensure_production_ready,
)
from app.worker import worker_loop

logger = logging.getLogger("productforge")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Con WORKER_INLINE=true el worker de jobs corre dentro de la API (desarrollo)."""
    ensure_production_ready(get_settings())
    if not get_settings().worker_inline:
        yield
        return
    stop = asyncio.Event()
    task = asyncio.create_task(worker_loop(get_services(), stop))
    yield
    stop.set()
    await task


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    # En producción no se publica el esquema de la API.
    docs = (
        {"docs_url": None, "redoc_url": None, "openapi_url": None}
        if settings.environment == "production"
        else {}
    )
    app = FastAPI(title="Productos Aurora API", version="0.7.0", lifespan=lifespan, **docs)
    app.add_middleware(
        BodyLimitMiddleware,
        max_bytes=settings.max_body_bytes,
        # La imagen de portada puede pesar hasta MAX_BYTES (+ margen); el endpoint corta igual.
        overrides={
            "/cover-images": MAX_BYTES + 64 * 1024,
            "/ads/results/import": REPORT_MAX_BYTES + 64 * 1024,
        },
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(content.router)
    app.include_router(products.router)
    app.include_router(products.files_router)
    app.include_router(drive.router)
    app.include_router(drive.product_router)
    app.include_router(catalog.router)
    app.include_router(cover.router)
    app.include_router(ads.router)
    app.include_router(ads_results.router)
    app.include_router(ads_meta.router)

    @app.exception_handler(ContentRejected)
    async def content_rejected(_: Request, exc: ContentRejected) -> JSONResponse:
        logger.warning("contenido rechazado por reglas: %s", exc.errors)
        return JSONResponse(
            {"detail": "la IA no logró cumplir las reglas del paquete", "errors": exc.errors},
            status_code=502,
        )

    @app.exception_handler(LLMError)
    async def llm_error(_: Request, exc: LLMError) -> JSONResponse:
        logger.warning("error de generación: %s", exc)
        return JSONResponse({"detail": str(exc)}, status_code=502)

    @app.exception_handler(anthropic.APIError)
    async def anthropic_error(_: Request, exc: anthropic.APIError) -> JSONResponse:
        # Sin detalles del proveedor hacia el cliente (pueden incluir ids internos).
        logger.error("error de la API de Claude: %s", type(exc).__name__)
        if isinstance(exc, anthropic.BadRequestError) and "credit balance" in str(exc):
            # Problema de cuenta, no de la petición: el usuario tiene que recargar créditos.
            detail = "la cuenta de Anthropic no tiene créditos (console.anthropic.com → Billing)"
            return JSONResponse({"detail": detail}, status_code=503)
        status = 503 if isinstance(exc, anthropic.RateLimitError) else 502
        return JSONResponse({"detail": "el servicio de IA no está disponible"}, status_code=status)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/me")
    def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> dict[str, str]:
        return {"id": str(user.id), "email": user.email}

    return app


app = create_app()
