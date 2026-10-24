"""Cliente de solo lectura de la API de Hotmart (ventas).

OAuth 2.0 con credenciales de cliente: el token se pide con la cabecera `Authorization: Basic …`
y se reutiliza hasta poco antes de vencer. Solo se llama a `GET /sales/history`; esta app nunca
crea, reembolsa ni modifica nada en Hotmart.
"""

import asyncio
import base64
import logging
import time
from datetime import UTC, datetime, timedelta

import httpx

logger = logging.getLogger("productforge.hotmart")

AUTH_URL = "https://api-sec-vlc.hotmart.com/security/oauth/token"
API = "https://developers.hotmart.com/payments/api/v1"
TIMEOUT = httpx.Timeout(60.0, connect=10.0)
MAX_ATTEMPTS = 4
WINDOW_DAYS = 30
PAGE_SIZE = 500
TOKEN_MARGIN = 300  # se renueva 5 min antes de vencer


class HotmartError(Exception):
    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


def millis(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


class HotmartClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        basic: str = "",
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._id = client_id.strip()
        self._secret = client_secret.strip()
        self._basic = basic.strip()
        self._http = http
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    def configured(self) -> bool:
        return bool(self._id and self._secret)

    def _basic_header(self) -> str:
        if self._basic:
            return (
                self._basic if self._basic.lower().startswith("basic ") else f"Basic {self._basic}"
            )
        raw = base64.b64encode(f"{self._id}:{self._secret}".encode()).decode()
        return f"Basic {raw}"

    async def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        owns = self._http is None
        client = self._http or httpx.AsyncClient(timeout=TIMEOUT, trust_env=False)
        try:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    response = await client.request(method, url, **kwargs)
                except httpx.TransportError as exc:
                    if attempt == MAX_ATTEMPTS:
                        raise HotmartError(
                            f"sin conexión con Hotmart ({type(exc).__name__})"
                        ) from exc
                    await asyncio.sleep(2**attempt)
                    continue
                if response.status_code in (429, 500, 502, 503, 504) and attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(2**attempt)
                    continue
                return response
        finally:
            if owns:
                await client.aclose()
        raise HotmartError("Hotmart no respondió")  # pragma: no cover

    async def token(self) -> str:
        if not self.configured():
            raise HotmartError("Hotmart no está configurado")
        async with self._lock:
            if self._token and time.time() < self._expires_at - TOKEN_MARGIN:
                return self._token
            response = await self._send(
                "POST",
                AUTH_URL,
                headers={"Authorization": self._basic_header()},
                params={
                    "grant_type": "client_credentials",
                    "client_id": self._id,
                    "client_secret": self._secret,
                },
            )
            if response.status_code != 200:
                raise HotmartError(
                    "Hotmart rechazó las credenciales (revisa HOTMART_CLIENT_ID, "
                    "HOTMART_CLIENT_SECRET y HOTMART_BASIC)",
                    status=response.status_code,
                )
            data = response.json()
            self._token = data["access_token"]
            self._expires_at = time.time() + float(data.get("expires_in", 3600))
            return self._token

    async def _get(self, path: str, params: dict) -> dict:
        for attempt in (1, 2):
            token = await self.token()
            response = await self._send(
                "GET", f"{API}{path}", params=params, headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code == 401 and attempt == 1:
                self._token = None  # venció antes de lo previsto: se pide otro y se reintenta
                continue
            if response.status_code != 200:
                raise HotmartError(
                    f"Hotmart respondió HTTP {response.status_code}", status=response.status_code
                )
            return response.json() if response.content else {}
        raise HotmartError("Hotmart rechazó el token")  # pragma: no cover

    async def sales_history(self, since: datetime, until: datetime) -> list[dict]:
        """Todas las ventas entre dos fechas, en ventanas de 30 días y con paginación."""
        items: list[dict] = []
        start = since
        while start < until:
            end = min(start + timedelta(days=WINDOW_DAYS), until)
            token: str | None = None
            while True:
                params = {
                    "start_date": millis(start),
                    "end_date": millis(end),
                    "max_results": PAGE_SIZE,
                }
                if token:
                    params["page_token"] = token
                page = await self._get("/sales/history", params)
                items.extend(page.get("items") or [])
                token = (page.get("page_info") or {}).get("next_page_token")
                if not token:
                    break
            start = end
        return items


def now_utc() -> datetime:
    return datetime.now(UTC)
