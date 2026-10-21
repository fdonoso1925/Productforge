"""Google Drive personal vía la API v3 de Drive.

Permiso mínimo `drive.file`: la app solo ve los archivos y carpetas que ella misma crea, nunca
el resto del Drive del usuario. Todo vive bajo una carpeta `ProductForge/` en "Mi unidad".

OAuth 2.0 con código de autorización y secreto de cliente (cliente tipo "Aplicación web").
Drive no direcciona por ruta: cada carpeta se busca o crea por nombre dentro de su padre, y
los ids se guardan en memoria. Como Drive permite carpetas duplicadas con el mismo nombre,
la creación se serializa con un candado por usuario.
"""

import asyncio
import json
import logging
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from urllib.parse import urlencode
from uuid import UUID

import httpx

from app.db.supabase import ConnectionRepo
from app.storage.base import RemoteFile
from app.storage.crypto import TokenCipher

logger = logging.getLogger("productforge.drive")

PROVIDER = "google_drive"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - es una URL, no una contraseña
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
SCOPES = f"{DRIVE_SCOPE} openid email"

ROOT_FOLDER = "ProductForge"
FOLDER_MIME = "application/vnd.google-apps.folder"
FILE_FIELDS = "id,webViewLink"

STATE_PURPOSE = "drive-oauth"
STATE_TTL_SECONDS = 600
REFRESH_MARGIN = timedelta(minutes=2)

MULTIPART_LIMIT = 5 * 1024 * 1024  # hasta aquí, un solo request; más, subida reanudable
CHUNK_SIZE = 32 * 256 * 1024  # 8 MiB; Drive exige múltiplos de 256 KiB
MAX_ATTEMPTS = 4
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
RATE_LIMIT_REASONS = frozenset({"rateLimitExceeded", "userRateLimitExceeded"})
MAX_RETRY_WAIT = 30.0


class DriveError(Exception):
    """Fallo hablando con Google. Nunca incluye tokens ni cuerpos de respuesta."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class NotConnected(DriveError):
    """El usuario no conectó Drive, o Google revocó o venció el acceso."""


@dataclass(frozen=True)
class GoogleConfig:
    client_id: str
    client_secret: str
    redirect_uri: str


Sleep = Callable[[float], Awaitable[None]]


def escape_query(value: str) -> str:
    """Escapa un literal para el parámetro `q` de Drive (comillas simples y barras)."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


class GoogleDrive:
    name: ClassVar[str] = PROVIDER

    def __init__(
        self,
        config: GoogleConfig,
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
        self._token_locks: dict[UUID, asyncio.Lock] = {}
        self._folder_locks: dict[UUID, asyncio.Lock] = {}
        self._folders: dict[tuple[UUID, tuple[str, ...]], str] = {}

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
        """Olvida los tokens y pide a Google que revoque el acceso (si falla, igual se olvidan)."""
        row = await self._connections.get(user_id, PROVIDER)
        await self._connections.delete(user_id, PROVIDER)
        self._forget_folders(user_id)
        if row is not None and self._cipher is not None:
            try:
                token = self._cipher.decrypt(row["refresh_token_enc"])
                await self._http.post(REVOKE_URL, data={"token": token})
            except Exception:
                logger.info(
                    "no se pudo revocar el acceso en Google; se borraron los tokens locales"
                )

    # ── OAuth: autorizar ──

    def authorize_url(self, user_id: UUID, locale: str) -> str:
        cipher = self._require_cipher()
        state = cipher.seal(STATE_PURPOSE, {"uid": str(user_id), "locale": locale})
        query = urlencode(
            {
                "client_id": self._config.client_id,
                "redirect_uri": self._config.redirect_uri,
                "response_type": "code",
                "scope": SCOPES,
                "access_type": "offline",  # sin esto Google no entrega refresh token
                "prompt": "consent",  # ni lo repite si el usuario ya había autorizado antes
                "state": state,
            }
        )
        return f"{AUTH_URL}?{query}"

    def read_state(self, state: str) -> dict[str, Any] | None:
        return self._require_cipher().unseal(STATE_PURPOSE, state, STATE_TTL_SECONDS)

    async def complete_authorization(self, code: str, state: str) -> tuple[UUID, str]:
        """Canjea el código por tokens y los guarda cifrados. Devuelve (usuario, idioma)."""
        data = self.read_state(state)
        if data is None:
            raise DriveError("estado de autorización inválido o vencido")
        user_id = UUID(data["uid"])
        tokens = await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._config.redirect_uri,
            }
        )
        # Google deja desmarcar permisos al autorizar: sin drive.file no hay nada que hacer.
        if DRIVE_SCOPE not in str(tokens.get("scope", "")).split():
            raise DriveError("faltó el permiso de Drive en la autorización")
        if not tokens.get("refresh_token"):
            raise DriveError("Google no entregó un refresh token")
        label = await self._account_label(tokens["access_token"])
        await self._save_tokens(user_id, tokens, label)
        return user_id, str(data.get("locale", "es"))

    async def _account_label(self, access_token: str) -> str | None:
        try:
            response = await self._http.get(
                USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            return response.json().get("email")
        except (httpx.HTTPError, ValueError):
            return None  # la etiqueta es solo informativa

    # ── tokens ──

    def _require_cipher(self) -> TokenCipher:
        if not self.configured() or self._cipher is None:
            raise DriveError("Google Drive no está configurado en el backend")
        return self._cipher

    async def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        response = await self._http.post(
            TOKEN_URL,
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
        logger.warning("Google rechazó la solicitud de token: %s", error or response.status_code)
        if error == "invalid_grant":  # refresh token vencido (modo Prueba: 7 días) o revocado
            raise NotConnected("Google revocó o venció el acceso; hay que reconectar")
        raise DriveError(f"error del servicio de autorización ({response.status_code})")

    async def _save_tokens(self, user_id: UUID, tokens: dict[str, Any], label: str | None) -> None:
        cipher = self._require_cipher()
        expires_at = datetime.now(UTC) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
        await self._connections.save(
            user_id=user_id,
            provider=PROVIDER,
            account_label=label,
            access_token_enc=cipher.encrypt(tokens["access_token"]),
            refresh_token_enc=cipher.encrypt(tokens["refresh_token"]),
            expires_at=expires_at.isoformat(),
        )

    async def access_token(self, user_id: UUID, *, force_refresh: bool = False) -> str:
        cipher = self._require_cipher()
        lock = self._token_locks.setdefault(user_id, asyncio.Lock())
        async with lock:  # dos subidas simultáneas no deben renovar a la vez
            row = await self._connections.get(user_id, PROVIDER)
            if row is None:
                raise NotConnected("Google Drive no está conectado")
            expires = datetime.fromisoformat(row["expires_at"])
            if not force_refresh and expires - REFRESH_MARGIN > datetime.now(UTC):
                return cipher.decrypt(row["access_token_enc"])
            refresh_token = cipher.decrypt(row["refresh_token_enc"])
            try:
                tokens = await self._token_request(
                    {"grant_type": "refresh_token", "refresh_token": refresh_token}
                )
            except NotConnected:
                await self._connections.delete(user_id, PROVIDER)  # ya no sirve
                self._forget_folders(user_id)
                raise
            # Google NO rota el refresh token: la respuesta trae solo el access token nuevo.
            tokens.setdefault("refresh_token", refresh_token)
            await self._save_tokens(user_id, tokens, row.get("account_label"))
            return str(tokens["access_token"])

    # ── llamadas a la API ──

    async def _send(
        self,
        user_id: UUID,
        method: str,
        url: str,
        *,
        ok: tuple[int, ...] = (200,),
        **kwargs: Any,
    ) -> httpx.Response:
        extra_headers = kwargs.pop("headers", {})  # una sola vez: se reusan en cada reintento
        refreshed = False
        for attempt in range(MAX_ATTEMPTS):
            token = await self.access_token(user_id, force_refresh=refreshed)
            try:
                response = await self._http.request(
                    method,
                    url,
                    headers={"Authorization": f"Bearer {token}", **extra_headers},
                    **kwargs,
                )
            except httpx.TransportError as exc:
                if attempt == MAX_ATTEMPTS - 1:
                    raise DriveError(f"sin conexión con Google ({type(exc).__name__})") from exc
                await self._sleep(min(2.0**attempt, MAX_RETRY_WAIT))
                continue
            if response.status_code in ok:
                return response
            if response.status_code == 401 and not refreshed:
                refreshed = True  # el token pudo vencer antes de lo esperado
                continue
            if _retryable(response) and attempt < MAX_ATTEMPTS - 1:
                await self._sleep(_retry_after(response) or min(2.0**attempt, MAX_RETRY_WAIT))
                continue
            raise DriveError(f"Google Drive respondió {response.status_code}", response.status_code)
        raise DriveError("se agotaron los reintentos con Google Drive")

    # ── carpetas ──

    def _forget_folders(self, user_id: UUID) -> None:
        for key in [k for k in self._folders if k[0] == user_id]:
            del self._folders[key]

    async def _find_child(
        self, user_id: UUID, parent: str, name: str, *, folder: bool
    ) -> dict[str, Any] | None:
        kind = "=" if folder else "!="
        query = (
            f"name = '{escape_query(name)}' and '{parent}' in parents and trashed = false"
            f" and mimeType {kind} '{FOLDER_MIME}'"
        )
        response = await self._send(
            user_id,
            "GET",
            f"{API}/files",
            params={
                "q": query,
                "spaces": "drive",
                "fields": f"files({FILE_FIELDS})",
                "orderBy": "createdTime",  # si hay duplicados, siempre el más antiguo
                "pageSize": 1,
            },
        )
        files = response.json().get("files", [])
        return files[0] if files else None

    async def _ensure_folder(self, user_id: UUID, parts: list[str], *, create: bool) -> str | None:
        """Id de la carpeta `parts` (desde "Mi unidad"); la crea si falta y `create` es True."""
        lock = self._folder_locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            parent = "root"
            for i in range(len(parts)):
                key = (user_id, tuple(parts[: i + 1]))
                if key in self._folders:
                    parent = self._folders[key]
                    continue
                found = await self._find_child(user_id, parent, parts[i], folder=True)
                if found is None:
                    if not create:
                        return None
                    created = await self._send(
                        user_id,
                        "POST",
                        f"{API}/files",
                        params={"fields": "id"},
                        json={"name": parts[i], "mimeType": FOLDER_MIME, "parents": [parent]},
                    )
                    found = created.json()
                self._folders[key] = parent = found["id"]
            return parent

    # ── subidas ──

    async def upload(self, user_id: UUID, path: str, data: bytes, mime: str) -> RemoteFile:
        segments = [s for s in path.split("/") if s]
        *dirs, filename = segments
        for attempt in range(2):
            parent = await self._ensure_folder(user_id, [ROOT_FOLDER, *dirs], create=True)
            assert parent is not None
            try:
                return await self._upload_file(user_id, parent, filename, data, mime)
            except DriveError as exc:
                # Carpeta borrada a mano desde que se guardó su id: se olvida y se recrea.
                if exc.status == 404 and attempt == 0:
                    self._forget_folders(user_id)
                    continue
                raise
        raise DriveError("no se pudo subir el archivo")

    async def _upload_file(
        self, user_id: UUID, parent: str, name: str, data: bytes, mime: str
    ) -> RemoteFile:
        existing = await self._find_child(user_id, parent, name, folder=False)
        metadata: dict[str, Any] = {"name": name, "mimeType": mime}
        if existing is None:
            metadata["parents"] = [parent]
            method, base = "POST", f"{UPLOAD_API}/files"
        else:  # reemplaza el contenido del archivo existente: la subida es idempotente
            method, base = "PATCH", f"{UPLOAD_API}/files/{existing['id']}"
        if len(data) <= MULTIPART_LIMIT:
            boundary = secrets.token_hex(16)
            body = _multipart(boundary, metadata, data, mime)
            response = await self._send(
                user_id,
                method,
                f"{base}?uploadType=multipart&fields={FILE_FIELDS}",
                content=body,
                headers={"Content-Type": f"multipart/related; boundary={boundary}"},
            )
            return _remote(response.json())
        return await self._upload_resumable(user_id, method, base, metadata, data, mime)

    async def _upload_resumable(
        self,
        user_id: UUID,
        method: str,
        base: str,
        metadata: dict[str, Any],
        data: bytes,
        mime: str,
    ) -> RemoteFile:
        session = await self._send(
            user_id,
            method,
            f"{base}?uploadType=resumable&fields={FILE_FIELDS}",
            json=metadata,
            headers={
                "X-Upload-Content-Type": mime,
                "X-Upload-Content-Length": str(len(data)),
            },
        )
        upload_url = session.headers.get("Location")
        if not upload_url:
            raise DriveError("Google no devolvió la URL de subida reanudable")
        total, offset, failures = len(data), 0, 0
        while True:
            chunk = data[offset : offset + CHUNK_SIZE]
            end = offset + len(chunk) - 1
            response = await self._put_chunk(
                user_id, upload_url, chunk, f"bytes {offset}-{end}/{total}"
            )
            if response is not None and response.status_code in (200, 201):
                return _remote(response.json())
            if response is not None and response.status_code == 308:
                offset, failures = _next_offset(response, default=end + 1), 0
                continue
            failures += 1  # error transitorio: se consulta cuánto recibió Google y se retoma
            if failures >= MAX_ATTEMPTS or (response is not None and not _retryable(response)):
                status = response.status_code if response is not None else None
                raise DriveError(f"la subida reanudable falló ({status})", status)
            await self._sleep(
                (_retry_after(response) if response is not None else None)
                or min(2.0**failures, MAX_RETRY_WAIT)
            )
            probe = await self._put_chunk(user_id, upload_url, b"", f"bytes */{total}")
            if probe is not None and probe.status_code in (200, 201):
                return _remote(probe.json())
            if probe is not None and probe.status_code == 308:
                offset = _next_offset(probe, default=0)

    async def _put_chunk(
        self, user_id: UUID, url: str, chunk: bytes, content_range: str
    ) -> httpx.Response | None:
        token = await self.access_token(user_id)
        try:
            return await self._http.put(
                url,
                content=chunk,
                headers={"Authorization": f"Bearer {token}", "Content-Range": content_range},
            )
        except httpx.TransportError:
            return None

    # ── borrar y enlazar ──

    async def delete(self, user_id: UUID, remote_id: str) -> None:
        """Manda el archivo a la papelera (recuperable). 404: ya no existe, no es un error."""
        await self._send(
            user_id,
            "PATCH",
            f"{API}/files/{remote_id}",
            ok=(200, 404),
            params={"fields": "id"},
            json={"trashed": True},
        )

    async def folder_url(self, user_id: UUID, path: str) -> str | None:
        parts = [ROOT_FOLDER, *[s for s in path.split("/") if s]]
        folder_id = await self._ensure_folder(user_id, parts, create=False)
        return f"https://drive.google.com/drive/folders/{folder_id}" if folder_id else None


def _multipart(boundary: str, metadata: dict[str, Any], data: bytes, mime: str) -> bytes:
    head = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n"
    )
    return head.encode() + data + f"\r\n--{boundary}--".encode()


def _remote(item: dict[str, Any]) -> RemoteFile:
    return RemoteFile(id=item["id"], url=item.get("webViewLink", ""))


def _retryable(response: httpx.Response) -> bool:
    if response.status_code in RETRY_STATUSES:
        return True
    if response.status_code == 403:  # Drive usa 403 para el límite de velocidad
        try:
            return response.json()["error"]["errors"][0]["reason"] in RATE_LIMIT_REASONS
        except (ValueError, KeyError, IndexError, TypeError):
            return False
    return False


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return min(float(response.headers["Retry-After"]), MAX_RETRY_WAIT)
    except (KeyError, ValueError):
        return None


def _next_offset(response: httpx.Response, default: int) -> int:
    """Siguiente byte a enviar según la cabecera `Range: bytes=0-N` de una respuesta 308."""
    try:
        return int(response.headers["Range"].rsplit("-", 1)[1]) + 1
    except (KeyError, ValueError, IndexError):
        return default
