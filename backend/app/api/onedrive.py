"""Conexión con OneDrive y estado de la copia de cada producto."""

import logging
from typing import Annotated, Literal
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.api.products import owned_product
from app.auth import CurrentUser, get_current_user
from app.deps import ServicesDep
from app.pipeline.onedrive_sync import product_folder
from app.pipeline.uploads import MAX_ATTEMPTS
from app.storage.onedrive import OneDriveError

logger = logging.getLogger("productforge.onedrive")

router = APIRouter(prefix="/storage/onedrive")
product_router = APIRouter(prefix="/products")
User = Annotated[CurrentUser, Depends(get_current_user)]

Locale = Literal["es", "pt"]


class ConnectionStatus(BaseModel):
    configured: bool
    connected: bool
    account: str | None = None


class ConnectRequest(BaseModel):
    locale: Locale = "es"


class ConnectResponse(BaseModel):
    url: str


class SyncResponse(BaseModel):
    products: int


class ProductSync(BaseModel):
    connected: bool
    total: int
    uploaded: int
    pending: int
    failed: int
    syncing: bool
    folder_url: str | None = None


def require_configured(services) -> None:
    if not services.onedrive.configured():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "OneDrive no está configurado en el backend "
            "(MS_CLIENT_ID, MS_CLIENT_SECRET, TOKEN_ENCRYPTION_KEY)",
        )


@router.get("/status")
async def connection_status(user: User, services: ServicesDep) -> ConnectionStatus:
    onedrive = services.onedrive
    connected = await onedrive.is_connected(user.id)
    return ConnectionStatus(
        configured=onedrive.configured(),
        connected=connected,
        account=await onedrive.account_label(user.id) if connected else None,
    )


@router.post("/connect")
async def connect(body: ConnectRequest, user: User, services: ServicesDep) -> ConnectResponse:
    """URL de Microsoft a la que el frontend manda al usuario para autorizar la app."""
    require_configured(services)
    return ConnectResponse(url=services.onedrive.authorize_url(user.id, body.locale))


@router.get("/callback")
async def callback(
    services: ServicesDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Microsoft vuelve aquí con el navegador del usuario (sin JWT): la identidad sale del
    `state` firmado que se emitió en `/connect`. Siempre termina redirigiendo al frontend."""
    locale: Locale = "es"
    outcome = "error"
    try:
        if state and (data := services.onedrive.read_state(state)):
            locale = "pt" if data.get("locale") == "pt" else "es"
        if error:  # el usuario rechazó el permiso o Microsoft devolvió un error
            outcome = "denied"
        elif code and state:
            user_id, _ = await services.onedrive.complete_authorization(code, state)
            await services.upload_queue.enqueue_unsynced(user_id)  # copia lo que ya existía
            outcome = "connected"
    except OneDriveError as exc:
        logger.warning("no se pudo conectar OneDrive: %s", type(exc).__name__)
    except Exception:
        logger.exception("error inesperado conectando OneDrive")
    base = services.settings.frontend_url.rstrip("/")
    return RedirectResponse(
        f"{base}/{locale}/settings?{urlencode({'onedrive': outcome})}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(user: User, services: ServicesDep) -> None:
    """Borra los tokens guardados. Los archivos que ya están en OneDrive se quedan ahí."""
    await services.onedrive.disconnect(user.id)


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_all(user: User, services: ServicesDep) -> SyncResponse:
    require_configured(services)
    if not await services.onedrive.is_connected(user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "primero conecta OneDrive")
    return SyncResponse(products=await services.upload_queue.enqueue_unsynced(user.id))


@product_router.get("/{product_id}/onedrive")
async def product_sync(product_id: UUID, user: User, services: ServicesDep) -> ProductSync:
    product = await owned_product(services, product_id, user)
    files = [
        f for f in await services.files.list_for_product(product_id) if f["file_type"] != "zip"
    ]
    count = lambda state: sum(f.get("onedrive_status") == state for f in files)  # noqa: E731
    syncing = bool(await services.jobs.active_for_product(product_id, kind="upload"))
    connected = await services.onedrive.is_connected(user.id)
    folder_url = None
    if connected and count("uploaded") and not syncing:
        try:
            folder_url = await services.onedrive.folder_url(user.id, product_folder(product))
        except OneDriveError:
            folder_url = None  # el enlace es un extra; no rompe el estado
    return ProductSync(
        connected=connected,
        total=len(files),
        uploaded=count("uploaded"),
        pending=count("pending"),
        failed=count("failed"),
        syncing=syncing,
        folder_url=folder_url,
    )


@product_router.post("/{product_id}/onedrive/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_product(product_id: UUID, user: User, services: ServicesDep) -> SyncResponse:
    """Sube lo pendiente de un producto y reintenta lo fallido (reinicia sus intentos)."""
    require_configured(services)
    await owned_product(services, product_id, user)
    if not await services.onedrive.is_connected(user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "primero conecta OneDrive")
    for f in await services.files.list_for_product(product_id):
        if f.get("onedrive_status") == "failed" and f.get("upload_attempts", 0) >= MAX_ATTEMPTS:
            await services.files.update(f["id"], upload_attempts=0)
    queued = await services.upload_queue.enqueue(user.id, product_id)
    return SyncResponse(products=int(queued))
