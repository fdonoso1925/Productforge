"""Creativos, fase 8: subir un lote a Meta (siempre EN PAUSA) y traer sus métricas."""

from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.ads.meta.client import MetaError
from app.ads.meta.jobs import publishable
from app.api.ads import JobOut, owned_batch
from app.auth import CurrentUser, get_current_user
from app.deps import ServicesDep
from app.security import work_rate_limit

router = APIRouter(prefix="/ads")
User = Annotated[CurrentUser, Depends(get_current_user)]

DEFAULT_COUNTRIES = {"es": ["MX", "CO", "AR", "CL", "PE"], "pt": ["BR"]}
MAX_DAILY_BUDGET = 1000  # en la moneda de la cuenta; es un tope de cordura, no de costo


class MetaStatusOut(BaseModel):
    configured: bool
    missing: list[str] = []
    account_name: str | None = None
    currency: str | None = None
    account_active: bool | None = None
    sales_available: bool = False
    default_countries: dict[str, list[str]] = DEFAULT_COUNTRIES
    error: str | None = None


@router.get("/meta/status")
async def meta_status(user: User, services: ServicesDep) -> MetaStatusOut:
    s = services.settings
    required = {
        "META_ACCESS_TOKEN": s.meta_access_token,
        "META_AD_ACCOUNT_ID": s.meta_ad_account_id,
        "META_PAGE_ID": s.meta_page_id,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing or services.meta is None:
        return MetaStatusOut(configured=False, missing=missing)
    try:
        account = await services.meta.account_info()
    except MetaError as exc:
        return MetaStatusOut(configured=True, error=str(exc), sales_available=bool(s.meta_pixel_id))
    return MetaStatusOut(
        configured=True,
        account_name=account.name,
        currency=account.currency,
        account_active=account.status == 1,
        sales_available=bool(s.meta_pixel_id),
    )


class MetaPublishIn(BaseModel):
    link_url: str = Field(min_length=10, max_length=500)
    objective: Literal["traffic", "sales"] = "traffic"
    daily_budget: float = Field(gt=0, le=MAX_DAILY_BUDGET)
    countries: list[str] = Field(min_length=1, max_length=25)

    @field_validator("link_url")
    @classmethod
    def https_link(cls, value: str) -> str:
        parts = urlsplit(value.strip())
        if parts.scheme != "https" or not parts.hostname or "." not in parts.hostname:
            raise ValueError("el enlace debe ser una URL https:// completa")
        if parts.username or parts.password:
            raise ValueError("el enlace no puede llevar usuario ni clave")
        return value.strip()

    @field_validator("countries")
    @classmethod
    def iso_countries(cls, value: list[str]) -> list[str]:
        codes = [c.strip().upper() for c in value]
        if any(len(c) != 2 or not c.isalpha() for c in codes):
            raise ValueError("los países van como códigos de 2 letras (MX, BR…)")
        return sorted(set(codes))


class MetaBatchOut(BaseModel):
    status: str = "none"  # none | publishing | done | partial | error
    total: int = 0
    uploaded: int = 0
    failed: int = 0
    skipped: int = 0
    objective: str | None = None
    daily_budget: float | None = None
    campaign_id: str | None = None
    synced_at: str | None = None
    active_ads: int = 0  # anuncios que alguien ya activó en Ads Manager
    error: str | None = None


def batch_meta_out(state: dict, *, publishing: bool) -> MetaBatchOut:
    statuses = state.get("statuses") or {}
    return MetaBatchOut(
        status="publishing" if publishing else state.get("status", "none"),
        total=state.get("total", 0),
        uploaded=state.get("uploaded", 0),
        failed=state.get("failed", 0),
        skipped=state.get("skipped", 0),
        objective=state.get("objective"),
        daily_budget=state.get("daily_budget"),
        campaign_id=state.get("campaign_id"),
        synced_at=state.get("synced_at"),
        active_ads=sum(1 for v in statuses.values() if v == "ACTIVE"),
        error=state.get("error"),
    )


@router.get("/batches/{batch_id}/meta")
async def batch_meta(batch_id: UUID, user: User, services: ServicesDep) -> MetaBatchOut:
    batch = await owned_batch(services, batch_id, user)
    running = bool(
        await services.jobs.active_for_batch(batch_id, kind="ad_meta_publish")
        or await services.jobs.active_for_batch(batch_id, kind="ad_meta_sync")
    )
    return batch_meta_out(batch.get("meta") or {}, publishing=running)


def require_meta(services) -> None:
    if services.meta is None or not services.meta.configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Meta no está configurado")


@router.post(
    "/batches/{batch_id}/meta",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(work_rate_limit)],
)
async def batch_to_meta(
    batch_id: UUID, body: MetaPublishIn, user: User, services: ServicesDep
) -> JobOut:
    """Crea campaña, conjunto y anuncios del lote en Meta, todo en PAUSA. No activa nada."""
    batch = await owned_batch(services, batch_id, user)
    require_meta(services)
    if body.objective == "sales" and not services.settings.meta_pixel_id.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, {"errors": ["falta META_PIXEL_ID"]}
        )
    creatives = await services.ad_creatives.list_for_batch(batch["id"])
    if not any(publishable(c) for c in creatives):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "no hay imágenes compuestas y aptas para subir"
        )
    for kind in ("ad_meta_publish", "ad_meta_sync"):
        if await services.jobs.active_for_batch(batch_id, kind=kind):
            raise HTTPException(status.HTTP_409_CONFLICT, "ya hay una operación con Meta en curso")
    previous = batch.get("meta") or {}
    # Con una campaña ya creada se reutiliza (completa lo que falte); cambiar objetivo, presupuesto
    # o enlace exige empezar otra, porque lo ya creado en Meta no se edita desde aquí.
    if previous.get("campaign_id") and (
        previous.get("objective") != body.objective
        or previous.get("link_url") != body.link_url
        or previous.get("daily_budget") != body.daily_budget
        or sorted(previous.get("countries", [])) != body.countries
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "este lote ya tiene una campaña en Meta con otros ajustes; edítala en Ads Manager",
        )
    job = await services.jobs.enqueue(
        user_id=user.id,
        batch_id=batch_id,
        kind="ad_meta_publish",
        payload=body.model_dump(),
    )
    return JobOut(job_id=UUID(job["id"]))


@router.post(
    "/batches/{batch_id}/meta/sync",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(work_rate_limit)],
)
async def batch_meta_sync(batch_id: UUID, user: User, services: ServicesDep) -> JobOut:
    """Trae de Meta el gasto, impresiones, clics y compras de los últimos 30 días."""
    batch = await owned_batch(services, batch_id, user)
    require_meta(services)
    if not (batch.get("meta") or {}).get("campaign_id"):
        raise HTTPException(status.HTTP_409_CONFLICT, "este lote aún no se subió a Meta")
    for kind in ("ad_meta_publish", "ad_meta_sync"):
        if await services.jobs.active_for_batch(batch_id, kind=kind):
            raise HTTPException(status.HTTP_409_CONFLICT, "ya hay una operación con Meta en curso")
    job = await services.jobs.enqueue(
        user_id=user.id, batch_id=batch_id, kind="ad_meta_sync", payload={}
    )
    return JobOut(job_id=UUID(job["id"]))
