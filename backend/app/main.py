from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import CurrentUser, get_current_user
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="ProductForge API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/me")
    def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> dict[str, str]:
        return {"id": str(user.id), "email": user.email}

    return app


app = create_app()
