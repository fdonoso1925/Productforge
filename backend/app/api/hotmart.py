"""Hotmart: leer las ventas para el dashboard (solo lectura) y vincular productos de la app."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import CurrentUser, get_current_user
from app.db.supabase import NotFound
from app.deps import ServicesDep
from app.hotmart.client import HotmartError
from app.hotmart.sync import MAX_DAYS, run_sync
from app.security import work_rate_limit

router = APIRouter(prefix="/hotmart")
User = Annotated[CurrentUser, Depends(get_current_user)]

# Una sola lectura a la vez por usuario (abrir el dashboard en dos pestañas no duplica trabajo).
_running: set[str] = set()


class HotmartStatusOut(BaseModel):
    configured: bool
    synced_at: str | None = None
    last_error: str | None = None
    count: int = 0


@router.get("/status")
async def hotmart_status(user: User, services: ServicesDep) -> HotmartStatusOut:
    if services.hotmart is None or not services.hotmart.configured():
        return HotmartStatusOut(configured=False)
    state = await services.hotmart_repo.get_sync(user.id) or {}
    return HotmartStatusOut(
        configured=True,
        synced_at=state.get("synced_at"),
        last_error=state.get("last_error"),
        count=state.get("count", 0),
    )


class SyncIn(BaseModel):
    days: int = Field(default=90, ge=1, le=MAX_DAYS)


class SyncOut(BaseModel):
    sales: int


@router.post("/sync", dependencies=[Depends(work_rate_limit)])
async def hotmart_sync(user: User, services: ServicesDep, body: SyncIn | None = None) -> SyncOut:
    """Trae de Hotmart las ventas del período y actualiza su estado (reembolsos incluidos)."""
    if services.hotmart is None or not services.hotmart.configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Hotmart no está configurado")
    key = str(user.id)
    if key in _running:
        raise HTTPException(status.HTTP_409_CONFLICT, "ya se está leyendo Hotmart")
    _running.add(key)
    try:
        count = await run_sync(
            services.hotmart, services.hotmart_repo, user.id, (body or SyncIn()).days
        )
    except HotmartError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    finally:
        _running.discard(key)
    return SyncOut(sales=count)


class LinkIn(BaseModel):
    product_id: UUID | None = None  # nulo = quitar el vínculo


@router.put("/products/{hotmart_product_id}/link", status_code=status.HTTP_204_NO_CONTENT)
async def link_product(
    hotmart_product_id: int, body: LinkIn, user: User, services: ServicesDep
) -> None:
    """Vincula un producto de Hotmart con uno de la app para cruzar ventas con el gasto."""
    if body.product_id is not None:
        try:
            await services.products.get(body.product_id, user.id)
        except NotFound:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "producto no encontrado") from None
    await services.hotmart_repo.link(user.id, hotmart_product_id, body.product_id)
