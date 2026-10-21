"""OneDrive personal vía Microsoft Graph (D11).

Permiso mínimo `Files.ReadWrite.AppFolder`: la app solo ve su propia carpeta
(`Apps/<nombre de la app>` en OneDrive, "Aplicaciones/…" en español). Todas las rutas son
relativas a esa carpeta (`/me/drive/special/approot`).

OAuth 2.0 con código de autorización y secreto de cliente, hablado directamente con el
endpoint de Microsoft (mismo protocolo que MSAL, pero asíncrono y sin dependencias extra).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from urllib.parse import quote, urlencode
from uuid import UUID

import httpx

from app.db.supabase import ConnectionRepo
from app.storage.base import RemoteFile
from app.storage.crypto import TokenCipher

logger = logging.getLogger("productforge.onedrive")

PROVIDER = "onedrive"
GRAPH = "https://graph.microsoft.com/v1.0"
AUTHORITY = "https://login.microsoftonline.com"
SCOPES = "offline_access Files.ReadWrite.AppFolder User.Read"
APPROOT = "/me/drive/special/approot"

STATE_PURPOSE = "onedrive-oauth"
STATE_TTL_SECONDS = 600
REFRESH_MARGIN = timedelta(minutes=2)

SIMPLE_UPLOAD_LIMIT = 4 * 1024 * 1024  # Graph: hasta 4 MB con un solo PUT
CHUNK_SIZE = 16 * 320 * 1024  # 5 MiB; debe ser múltiplo de 320 KiB
MAX_ATTEMPTS = 4
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_WAIT = 30.0


class OneDriveError(Exception):
    """Fallo hablando con Microsoft. Nunca incluye tokens ni cuerpos de respuesta."""


class NotConnected(OneDriveError):
    """El usuario no conectó OneDrive, o Microsoft revocó el acceso."""


@dataclass(frozen=True)
class OneDriveConfig:
    client_id: str
    client_secret: str
    tenant: str
    redirect_uri: str


Sleep = Callable[[float], Awaitable[None]]


def drive_path(path: str) -> str:
    """`/me/drive/special/approot:/<ruta>` con cada segmento escapado."""
    segments = [s for s in path.split("/") if s]
    return f"{APPROOT}:/{'/'.join(quote(s, safe='') for s in segments)}"


class OneDrive:
    name: ClassVar[str] = PROVIDER

    def __init__(
        self,
        config: OneDriveConfig,
        connections: ConnectionRepo,
        cipher: TokenCipher | None,
        client: httpx.AsyncClient | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._config = config
        self._connections = connections
        self._cipher = cipher
        self._http = client or httpx.AsyncClient(timeout=60)
        self._sleep = sleep
        self._locks: dict[UUID, asyncio.Lock] = {}

    # ── configuración y estado ──

    def configured(self) -> bool:
        c = self._config
        return bool(c.client_id and c.client_secret and self._cipher)

    async def is_connected(self, user_id: UUID) -> bool:
        return self.configured() and await self._connections.get(user_id, PROVIDER) is not None

    async def account_label(self, user_id: UUID) -> str | None:
        row = await self._connections.get(user_id, PROVIDER)
        return row["account_label"] if row else None

    async def disconnect(self, user_id: UUID) -> None:
        await self._connections.delete(user_id, PROVIDER)

    # ── OAuth: autorizar ──

    def authorize_url(self, user_id: UUID, locale: str) -> str:
        cipher = self._require_cipher()
        state = cipher.seal(STATE_PURPOSE, {"uid": str(user_id), "locale": locale})
        query = urlencode(
            {
                "client_id": self._config.client_id,
                "response_type": "code",
                "redirect_uri": self._config.redirect_uri,
                "response_mode": "query",
                "scope": SCOPES,
                "state": state,
                "prompt": "select_account",
            }
        )
        return f"{AUTHORITY}/{self._config.tenant}/oauth2/v2.0/authorize?{query}"

    def read_state(self, state: str) -> dict[str, Any] | None:
        return self._require_cipher().unseal(STATE_PURPOSE, state, STATE_TTL_SECONDS)

    async def complete_authorization(self, code: str, state: str) -> tuple[UUID, str]:
        """Canjea el código por tokens y los guarda cifrados. Devuelve (usuario, idioma)."""
        data = self.read_state(state)
        if data is None:
            raise OneDriveError("estado de autorización inválido o vencido")
        user_id = UUID(data["uid"])
        tokens = await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._config.redirect_uri,
                "scope": SCOPES,
            }
        )
        label = await self._account_label(tokens["access_token"])
        await self._save_tokens(user_id, tokens, label)
        return user_id, str(data.get("locale", "es"))

    async def _account_label(self, access_token: str) -> str | None:
        try:
            response = await self._http.get(
                f"{GRAPH}/me?$select=displayName,userPrincipalName",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            me = response.json()
            return me.get("userPrincipalName") or me.get("displayName")
        except (httpx.HTTPError, ValueError):
            return None  # la etiqueta es solo informativa

    # ── tokens ──

    def _require_cipher(self) -> TokenCipher:
        if not self.configured() or self._cipher is None:
            raise OneDriveError("OneDrive no está configurado en el backend")
        return self._cipher

    async def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        response = await self._http.post(
            f"{AUTHORITY}/{self._config.tenant}/oauth2/v2.0/token",
            data={
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                **form,
            },
        )
        if response.status_code == 200:
            return response.json()
        try:
            error = response.json().get("error", "")
        except ValueError:
            error = ""
        logger.warning("Microsoft rechazó la solicitud de token: %s", error or response.status_code)
        if error == "invalid_grant":  # refresh token vencido o permiso revocado
            raise NotConnected("Microsoft revocó el acceso; hay que reconectar")
        raise OneDriveError(f"error del servicio de autorización ({response.status_code})")

    async def _save_tokens(self, user_id: UUID, tokens: dict[str, Any], label: str | None) -> None:
        cipher = self._require_cipher()
        expires_at = datetime.now(UTC) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
        await self._connections.save(
            user_id=user_id,
            provider=PROVIDER,
            account_label=label,
            access_token_enc=cipher.encrypt(tokens["access_token"]),
            # Microsoft rota el refresh token en cada renovación: hay que guardar el nuevo.
            refresh_token_enc=cipher.encrypt(tokens["refresh_token"]),
            expires_at=expires_at.isoformat(),
        )

    async def access_token(self, user_id: UUID, *, force_refresh: bool = False) -> str:
        cipher = self._require_cipher()
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        async with lock:  # dos subidas simultáneas no deben renovar a la vez
            row = await self._connections.get(user_id, PROVIDER)
            if row is None:
                raise NotConnected("OneDrive no está conectado")
            expires = datetime.fromisoformat(row["expires_at"])
            if not force_refresh and expires - REFRESH_MARGIN > datetime.now(UTC):
                return cipher.decrypt(row["access_token_enc"])
            try:
                tokens = await self._token_request(
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": cipher.decrypt(row["refresh_token_enc"]),
                        "scope": SCOPES,
                    }
                )
            except NotConnected:
                await self._connections.delete(user_id, PROVIDER)  # ya no sirve
                raise
            tokens.setdefault("refresh_token", cipher.decrypt(row["refresh_token_enc"]))
            await self._save_tokens(user_id, tokens, row.get("account_label"))
            return str(tokens["access_token"])

    # ── Graph ──

    async def _request(
        self,
        user_id: UUID,
        method: str,
        url: str,
        *,
        ok: tuple[int, ...] = (200, 201),
        **kwargs: Any,
    ) -> httpx.Response:
        extra_headers = kwargs.pop("headers", {})  # una sola vez: se reusan en cada reintento
        refreshed = False
        for attempt in range(MAX_ATTEMPTS):
            token = await self.access_token(user_id, force_refresh=refreshed)
            try:
                response = await self._http.request(
                    method,
                    url if url.startswith("http") else f"{GRAPH}{url}",
                    headers={"Authorization": f"Bearer {token}", **extra_headers},
                    **kwargs,
                )
            except httpx.TransportError as exc:
                if attempt == MAX_ATTEMPTS - 1:
                    raise OneDriveError(
                        f"sin conexión con Microsoft ({type(exc).__name__})"
                    ) from exc
                await self._sleep(min(2.0**attempt, MAX_RETRY_WAIT))
                continue
            if response.status_code in ok:
                return response
            if response.status_code == 401 and not refreshed:
                refreshed = True  # el token pudo vencer antes de lo esperado
                continue
            if response.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS - 1:
                wait = _retry_after(response) or min(2.0**attempt, MAX_RETRY_WAIT)
                await self._sleep(wait)
                continue
            raise OneDriveError(f"Microsoft Graph respondió {response.status_code}")
        raise OneDriveError("se agotaron los reintentos con Microsoft Graph")

    async def upload(self, user_id: UUID, path: str, data: bytes, mime: str) -> RemoteFile:
        if len(data) <= SIMPLE_UPLOAD_LIMIT:
            response = await self._request(
                user_id,
                "PUT",
                f"{drive_path(path)}:/content?@microsoft.graph.conflictBehavior=replace",
                content=data,
                headers={"Content-Type": mime},
            )
            return _remote(response.json())
        return await self._upload_session(user_id, path, data)

    async def _upload_session(self, user_id: UUID, path: str, data: bytes) -> RemoteFile:
        session = await self._request(
            user_id,
            "POST",
            f"{drive_path(path)}:/createUploadSession",
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        )
        upload_url = session.json()["uploadUrl"]
        total = len(data)
        for start in range(0, total, CHUNK_SIZE):
            chunk = data[start : start + CHUNK_SIZE]
            end = start + len(chunk) - 1
            # La URL de la sesión ya viene autenticada: no se le manda el token.
            response = await self._put_chunk(upload_url, chunk, f"bytes {start}-{end}/{total}")
            if response.status_code in (200, 201):
                return _remote(response.json())
        raise OneDriveError("la sesión de subida terminó sin devolver el archivo")

    async def _put_chunk(self, url: str, chunk: bytes, content_range: str) -> httpx.Response:
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = await self._http.put(
                    url, content=chunk, headers={"Content-Range": content_range}
                )
            except httpx.TransportError as exc:
                if attempt == MAX_ATTEMPTS - 1:
                    raise OneDriveError("sin conexión con Microsoft") from exc
                await self._sleep(min(2.0**attempt, MAX_RETRY_WAIT))
                continue
            if response.status_code in (200, 201, 202):
                return response
            if response.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS - 1:
                await self._sleep(_retry_after(response) or min(2.0**attempt, MAX_RETRY_WAIT))
                continue
            raise OneDriveError(f"la subida por partes falló ({response.status_code})")
        raise OneDriveError("se agotaron los reintentos de la subida por partes")

    async def delete(self, user_id: UUID, remote_id: str) -> None:
        # 404: ya no existe (p. ej. el usuario lo borró a mano); no es un error.
        await self._request(
            user_id, "DELETE", f"/me/drive/items/{quote(remote_id, safe='')}", ok=(204, 404)
        )

    async def folder_url(self, user_id: UUID, path: str) -> str | None:
        response = await self._request(
            user_id, "GET", f"{drive_path(path)}?$select=webUrl", ok=(200, 404)
        )
        return response.json().get("webUrl") if response.status_code == 200 else None


def _remote(item: dict[str, Any]) -> RemoteFile:
    return RemoteFile(id=item["id"], url=item.get("webUrl", ""))


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return min(float(response.headers["Retry-After"]), MAX_RETRY_WAIT)
    except (KeyError, ValueError):
        return None
