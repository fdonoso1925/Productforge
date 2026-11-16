"""Hotmart: leer las ventas para el dashboard (solo lectura) y vincular productos de la app."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import CurrentUser, get_current_user
from app.db.supabase import NotFound
from app.deps import ServicesDep
from app.hotmart.client import HotmartError, now_utc
from app.hotmart.fx import MAX_DAYS as MAX_RATE_DAYS
from app.hotmart.sync import MAX_DAYS, period_bounds, run_sync
from app.integrations.credentials import resolve_hotmart
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
    client = await resolve_hotmart(services, user.id)
    if client is None or not client.configured():
        return HotmartStatusOut(configured=False)
    state = await services.hotmart_repo.get_sync(user.id) or {}
    return HotmartStatusOut(
        configured=True,
        synced_at=state.get("synced_at"),
        last_error=state.get("last_error"),
        count=state.get("count", 0),
    )


class SyncIn(BaseModel):
    """Los últimos `days` días o, si vienen fechas, ese rango (días completos, `end` incluido)."""

    days: int = Field(default=90, ge=1, le=MAX_DAYS)
    start: date | None = None
    end: date | None = None


class SyncOut(BaseModel):
    sales: int


@router.post("/sync", dependencies=[Depends(work_rate_limit)])
async def hotmart_sync(user: User, services: ServicesDep, body: SyncIn | None = None) -> SyncOut:
    """Trae de Hotmart las ventas del período y actualiza su estado (reembolsos incluidos)."""
    client = await resolve_hotmart(services, user.id)
    if client is None or not client.configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Hotmart no está configurado")
    sync = body or SyncIn()
    try:
        period_bounds(sync.days, sync.start, sync.end, now_utc())
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    key = str(user.id)
    if key in _running:
        raise HTTPException(status.HTTP_409_CONFLICT, "ya se está leyendo Hotmart")
    _running.add(key)
    try:
        count = await run_sync(
            client, services.hotmart_repo, user.id, sync.days, sync.start, sync.end
        )
    except HotmartError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    finally:
        _running.discard(key)
    return SyncOut(sales=count)


class RatesIn(BaseModel):
    days: list[date] = Field(default_factory=list, max_length=MAX_RATE_DAYS)
    currencies: list[Annotated[str, Field(pattern=r"^[A-Za-z]{3}$")]] = Field(
        default_factory=list, max_length=20
    )


class RatesOut(BaseModel):
    """Unidades de cada moneda por 1 USD: por día y el último conocido (si falta un día)."""

    by_day: dict[str, dict[str, float]]
    latest: dict[str, float]


@router.post("/rates", dependencies=[Depends(work_rate_limit)])
async def hotmart_rates(body: RatesIn, user: User, services: ServicesDep) -> RatesOut:
    """Tipos de cambio a USD para mostrar el dashboard en dólares (fuente pública, sin clave)."""
    fx = getattr(services, "fx", None)
    if fx is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "tipos de cambio no disponibles")
    by_day, latest = await fx.rates(body.days, body.currencies)
    return RatesOut(by_day=by_day, latest=latest)


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
