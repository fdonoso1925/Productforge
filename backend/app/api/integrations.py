"""Ajustes: conectar Meta Ads y Hotmart pegando sus credenciales (se guardan cifradas).

El navegador nunca recibe los valores guardados: solo si cada campo está puesto, de dónde viene
(guardado o variable de entorno) y los últimos 4 caracteres de los secretos.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.ads.meta.client import MetaError
from app.auth import CurrentUser, get_current_user
from app.deps import ServicesDep
from app.hotmart.client import HotmartError
from app.integrations.credentials import (
    InvalidCredentials,
    MigrationMissing,
    resolve_hotmart,
    resolve_meta,
)
from app.security import work_rate_limit

router = APIRouter(prefix="/integrations")
User = Annotated[CurrentUser, Depends(get_current_user)]
Provider = Literal["meta", "hotmart"]

Secret = Annotated[str, Field(default="", max_length=1000)]


class MetaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_token: Secret
    ad_account_id: Secret
    page_id: Secret
    instagram_user_id: Secret
    pixel_id: Secret


class HotmartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: Secret
    client_secret: Secret
    basic: Secret


class StatusOut(BaseModel):
    provider: Provider
    connected: bool
    can_save: bool
    has_saved: bool
    fields: list[dict]
    missing: list[str]


class AllOut(BaseModel):
    meta: StatusOut
    hotmart: StatusOut


class TestOut(BaseModel):
    ok: bool
    detail: str = ""


def store(services):
    if services.credentials is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "credenciales no disponibles")
    return services.credentials


@router.get("")
async def integrations(user: User, services: ServicesDep) -> AllOut:
    s = store(services)
    return AllOut(
        meta=StatusOut(**await s.status(user.id, "meta")),
        hotmart=StatusOut(**await s.status(user.id, "hotmart")),
    )


async def save(provider: str, body: BaseModel, user: CurrentUser, services) -> StatusOut:
    s = store(services)
    try:
        await s.save(user.id, provider, body.model_dump())
    except InvalidCredentials as exc:
        code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if "TOKEN_ENCRYPTION_KEY" in str(exc)
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        raise HTTPException(code, str(exc)) from exc
    except MigrationMissing as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return StatusOut(**await s.status(user.id, provider))


@router.put("/meta", dependencies=[Depends(work_rate_limit)])
async def save_meta(body: MetaIn, user: User, services: ServicesDep) -> StatusOut:
    return await save("meta", body, user, services)


@router.put("/hotmart", dependencies=[Depends(work_rate_limit)])
async def save_hotmart(body: HotmartIn, user: User, services: ServicesDep) -> StatusOut:
    return await save("hotmart", body, user, services)


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(provider: Provider, user: User, services: ServicesDep) -> None:
    """Borra lo guardado. Si las variables de entorno siguen puestas, se usan esas."""
    await store(services).delete(user.id, provider)


@router.post("/{provider}/test", dependencies=[Depends(work_rate_limit)])
async def test_connection(provider: Provider, user: User, services: ServicesDep) -> TestOut:
    """Prueba de verdad las credenciales contra Meta u Hotmart (solo lectura)."""
    if provider == "meta":
        meta = await resolve_meta(services, user.id)
        if meta is None or not meta.configured():
            return TestOut(ok=False, detail="faltan datos")
        try:
            account = await meta.account_info()
        except MetaError as exc:
            return TestOut(ok=False, detail=str(exc))
        return TestOut(ok=True, detail=f"{account.name} · {account.currency}")
    client = await resolve_hotmart(services, user.id)
    if client is None or not client.configured():
        return TestOut(ok=False, detail="faltan datos")
    try:
        await client.token()
    except HotmartError as exc:
        return TestOut(ok=False, detail=str(exc))
    return TestOut(ok=True)
