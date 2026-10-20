import logging
from typing import Annotated

import anthropic
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import content
from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.content.claude_client import LLMError
from app.content.engines import ContentRejected

logger = logging.getLogger("productforge")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="ProductForge API", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(content.router)

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
