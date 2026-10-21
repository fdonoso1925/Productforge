"""Microsoft (login + Graph + URL de subida por partes) simulado con httpx.MockTransport."""

from urllib.parse import parse_qs
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet

from app.storage.base import RemoteFile
from app.storage.crypto import TokenCipher
from app.storage.onedrive import OneDrive, OneDriveConfig
from tests.memory import MemoryConnections

CONFIG = OneDriveConfig(
    client_id="client-id",
    client_secret="client-secret",
    tenant="consumers",
    redirect_uri="http://localhost:8000/storage/onedrive/callback",
)
UPLOAD_HOST = "https://upload.test"


def new_cipher() -> TokenCipher:
    return TokenCipher(Fernet.generate_key().decode())


class FakeMicrosoft:
    """Respuestas en cola por tipo de llamada; registra cada request para poder inspeccionarlo."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.token: list[tuple[int, dict]] = []
        self.graph: list[tuple] = []  # (status, body[, headers])
        self.chunks: list[tuple[int, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url.endswith("/oauth2/v2.0/token"):
            status, body = self.token.pop(0)
            return httpx.Response(status, json=body)
        if url.startswith(UPLOAD_HOST):
            status, body = self.chunks.pop(0)
            return httpx.Response(status, json=body)
        if request.url.path == "/v1.0/me":
            return httpx.Response(200, json={"userPrincipalName": "ana@outlook.com"})
        if self.graph:
            status, body, *rest = self.graph.pop(0)
            return httpx.Response(status, json=body, headers=rest[0] if rest else None)
        return httpx.Response(200, json={"id": "item-1", "webUrl": "https://onedrive.test/item-1"})

    # ── helpers de inspección ──

    def form(self, request: httpx.Request) -> dict[str, str]:
        return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}

    def token_requests(self) -> list[dict[str, str]]:
        return [self.form(r) for r in self.requests if str(r.url).endswith("/token")]

    def graph_requests(self) -> list[httpx.Request]:
        return [
            r
            for r in self.requests
            if r.url.host == "graph.microsoft.com" and r.url.path != "/v1.0/me"
        ]


def make_onedrive(
    microsoft: FakeMicrosoft | None = None,
    connections: MemoryConnections | None = None,
    *,
    cipher: TokenCipher | None = None,
    sleeps: list[float] | None = None,
) -> tuple[OneDrive, FakeMicrosoft, MemoryConnections]:
    microsoft = microsoft or FakeMicrosoft()
    connections = connections if connections is not None else MemoryConnections()

    async def no_sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    client = httpx.AsyncClient(transport=httpx.MockTransport(microsoft))
    onedrive = OneDrive(CONFIG, connections, cipher or new_cipher(), client=client, sleep=no_sleep)
    return onedrive, microsoft, connections


class FakeTarget:
    """SyncTarget en memoria para probar el job de subida sin tocar Microsoft."""

    name = "fake"

    def __init__(
        self,
        *,
        connected=True,
        configured=True,
        fail=(),
        fail_delete=False,
        raise_not_connected=False,
    ) -> None:
        self.connected, self._configured = connected, configured
        self.fail, self.fail_delete = tuple(fail), fail_delete
        self.raise_not_connected = raise_not_connected
        self.uploads: list[tuple[str, str, int, str]] = []
        self.deleted: list[str] = []
        self.attempted: list[str] = []

    def configured(self) -> bool:
        return self._configured

    async def is_connected(self, user_id) -> bool:
        return self.connected

    async def upload(self, user_id, path, data, mime) -> RemoteFile:
        from app.storage.onedrive import NotConnected

        self.attempted.append(path)
        if self.raise_not_connected:
            raise NotConnected("revocado")
        if any(path.endswith(f) for f in self.fail):
            raise RuntimeError("boom")
        self.uploads.append((str(user_id), path, len(data), mime))
        return RemoteFile(id=f"remote-{uuid4().hex[:6]}", url=f"https://onedrive.test/{path}")

    async def delete(self, user_id, remote_id) -> None:
        self.deleted.append(remote_id)
        if self.fail_delete:
            raise RuntimeError("boom")

    async def folder_url(self, user_id, path) -> str | None:
        return f"https://onedrive.test/folder/{path}"
