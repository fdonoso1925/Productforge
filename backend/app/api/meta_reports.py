"""Campañas de Meta con sus métricas, leídas en vivo de la cuenta del usuario (solo lectura).

A diferencia de `/ads/dashboard` (solo lo que se subió desde la app), aquí aparecen TODAS las
campañas de la cuenta publicitaria, también las creadas a mano en Ads Manager. Nada se modifica:
solo `GET` a la Graph API. Una caché corta por usuario y período evita gastar el límite de
velocidad de Meta al ir y volver entre pantallas.
"""

import time
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.ads.meta import reports
from app.ads.meta.client import MetaError
from app.auth import CurrentUser, get_current_user
from app.deps import ServicesDep
from app.integrations.credentials import resolve_meta
from app.security import work_rate_limit

router = APIRouter(prefix="/ads/meta")
User = Annotated[CurrentUser, Depends(get_current_user)]

CACHE_SECONDS = 300.0
_cache: dict[tuple[str, str], tuple[float, dict]] = {}


def _cached(user_id: str, key: str) -> dict | None:
    hit = _cache.get((user_id, key))
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    return None


def _remember(user_id: str, key: str, value: dict) -> dict:
    _cache[(user_id, key)] = (time.monotonic(), value)
    return value


async def _client(services, user: CurrentUser):
    meta = await resolve_meta(services, user.id)
    if meta is None or not meta.configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Meta no está conectado")
    return meta


def _period(preset: str | None, since: date | None, until: date | None) -> dict:
    try:
        return reports.period_params(preset, since, until, datetime.now(UTC).date())
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


def _meta_failure(exc: MetaError) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, f"Meta respondió: {exc}")


@router.get("/campaigns", dependencies=[Depends(work_rate_limit)])
async def list_campaigns(
    user: User,
    services: ServicesDep,
    preset: str | None = None,
    since: date | None = None,
    until: date | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Todas las campañas de la cuenta con sus métricas del período y los totales."""
    period = _period(preset, since, until)
    key = f"list:{period}"
    if not refresh and (hit := _cached(str(user.id), key)):
        return hit
    meta = await _client(services, user)
    try:
        account = await meta.account_info()
        campaigns = await meta.campaigns()
        rows = await meta.report(level="campaign", period=period)
    except MetaError as exc:
        raise _meta_failure(exc) from exc
    batches = await services.ad_batches.list_for_user(user.id, limit=500)
    from_app = {
        str((b.get("meta") or {}).get("campaign_id"))
        for b in batches
        if (b.get("meta") or {}).get("campaign_id")
    }
    report = reports.campaign_report(campaigns, rows, account.currency, from_app)
    return _remember(
        str(user.id),
        key,
        {
            "account": {"id": account.id, "name": account.name, "currency": account.currency},
            "period": period,
            "fetched_at": datetime.now(UTC).isoformat(),
            **report,
        },
    )


@router.get("/campaigns/{campaign_id}", dependencies=[Depends(work_rate_limit)])
async def campaign_detail(
    user: User,
    services: ServicesDep,
    campaign_id: Annotated[str, Path(pattern=r"^\d{1,30}$")],
    preset: str | None = None,
    since: date | None = None,
    until: date | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Una campaña: su serie diaria y sus anuncios con métricas. El filtro va dentro de la
    cuenta del usuario, así que una campaña ajena simplemente no devuelve nada."""
    period = _period(preset, since, until)
    key = f"detail:{campaign_id}:{period}"
    if not refresh and (hit := _cached(str(user.id), key)):
        return hit
    meta = await _client(services, user)
    try:
        daily = await meta.report(
            level="campaign", period=period, daily=True, campaign_id=campaign_id
        )
        ads = await meta.report(level="ad", period=period, campaign_id=campaign_id)
    except MetaError as exc:
        raise _meta_failure(exc) from exc
    return _remember(
        str(user.id),
        key,
        {
            "id": campaign_id,
            "period": period,
            "daily": reports.daily_series(daily),
            "ads": reports.ad_rows(ads),
        },
    )
