"""Google (OAuth + Drive API v3 + subida reanudable) simulado con httpx.MockTransport.

Incluye un Drive en memoria (carpetas, archivos, papelera) para probar comportamientos
reales: no duplicar carpetas, reemplazar archivos, retomar subidas cortadas.
"""

import json
import re
from collections.abc import Callable
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet

from app.storage.base import RemoteFile
from app.storage.crypto import TokenCipher
from app.storage.google_drive import FOLDER_MIME, GoogleConfig, GoogleDrive
from tests.memory import MemoryConnections

CONFIG = GoogleConfig(
    client_id="client-id.apps.googleusercontent.com",
    client_secret="client-secret",
    redirect_uri="http://localhost:8000/storage/drive/callback",
)
UPLOAD_HOST = "https://upload.test"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"


def new_cipher() -> TokenCipher:
    return TokenCipher(Fernet.generate_key().decode())


def tokens(access="ACCESS-1", refresh: str | None = "REFRESH-1", scope: str | None = None) -> dict:
    body = {
        "access_token": access,
        "expires_in": 3599,
        "scope": scope or f"openid https://www.googleapis.com/auth/userinfo.email {DRIVE_SCOPE}",
        "token_type": "Bearer",
    }
    if refresh:
        body["refresh_token"] = refresh
    return body


class Fault:
    def __init__(
        self,
        when: Callable[[httpx.Request], bool],
        status: int,
        body=None,
        headers=None,
        effect: Callable[[httpx.Request], None] | None = None,
    ) -> None:
        self.when, self.status, self.body, self.headers, self.effect = (
            when,
            status,
            body,
            headers,
            effect,
        )


class FakeGoogle:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.token: list[tuple[int, dict]] = []
        self.faults: list[Fault] = []
        self.files: dict[str, dict] = {}
        self._ids = 0
        self.sessions: dict[str, dict] = {}
        self.revoked: list[str] = []

    # ── el Drive en memoria ──

    def _new_id(self) -> str:
        self._ids += 1
        return f"id{self._ids}"

    def add(self, name: str, parent: str, mime: str = "text/plain", content: bytes = b"") -> str:
        file_id = self._new_id()
        self.files[file_id] = {
            "id": file_id,
            "name": name,
            "parents": [parent],
            "mimeType": mime,
            "trashed": False,
            "content": content,
            "order": self._ids,
        }
        return file_id

    def folders(self, name: str | None = None) -> list[dict]:
        return [
            f
            for f in self.files.values()
            if f["mimeType"] == FOLDER_MIME and (name is None or f["name"] == name)
        ]

    def children(self, parent: str, *, trashed: bool = False) -> list[dict]:
        return [
            f for f in self.files.values() if parent in f["parents"] and f["trashed"] is trashed
        ]

    def by_name(self, name: str) -> list[dict]:
        return [f for f in self.files.values() if f["name"] == name]

    def path_of(self, file_id: str) -> str:
        names, current = [], self.files[file_id]
        while True:
            names.append(current["name"])
            parent = current["parents"][0]
            if parent == "root":
                return "/".join(reversed(names))
            current = self.files[parent]

    # ── transporte ──

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url, host, path = str(request.url), request.url.host, request.url.path
        if url.startswith("https://oauth2.googleapis.com/token"):
            status, body = self.token.pop(0)
            return httpx.Response(status, json=body)
        if url.startswith("https://oauth2.googleapis.com/revoke"):
            self.revoked.append(self.form(request).get("token", ""))
            return httpx.Response(200, json={})
        if host == "openidconnect.googleapis.com":
            return httpx.Response(200, json={"email": "ana@gmail.com"})
        for fault in self.faults:
            if fault.when(request):
                self.faults.remove(fault)
                if fault.effect:
                    fault.effect(request)
                return httpx.Response(fault.status, json=fault.body or {}, headers=fault.headers)
        if host == "upload.test":
            return self._session_put(request)
        if host == "www.googleapis.com" and path.startswith("/upload/drive/v3/files"):
            return self._upload(request)
        if host == "www.googleapis.com" and path.startswith("/drive/v3/files"):
            return self._api(request)
        return httpx.Response(404, json={})

    def form(self, request: httpx.Request) -> dict[str, str]:
        return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}

    def token_requests(self) -> list[dict[str, str]]:
        return [
            self.form(r)
            for r in self.requests
            if str(r.url).startswith("https://oauth2.googleapis.com/token")
        ]

    def drive_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host in ("www.googleapis.com", "upload.test")]

    def _api(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/drive/v3/files":
            q = request.url.params["q"]
            name = (
                re.search(r"name = '((?:[^'\\]|\\.)*)'", q)
                .group(1)
                .replace("\\'", "'")
                .replace("\\\\", "\\")
            )
            parent = re.search(r"'([^']+)' in parents", q).group(1)
            is_folder = "mimeType =" in q
            found = [
                f
                for f in self.children(parent)
                if f["name"] == name and (f["mimeType"] == FOLDER_MIME) is is_folder
            ]
            found.sort(key=lambda f: f["order"])
            found = found[: int(request.url.params.get("pageSize", 100))]
            return httpx.Response(200, json={"files": [self._view(f) for f in found]})
        if request.method == "POST" and path == "/drive/v3/files":
            meta = json.loads(request.content)
            if meta["parents"][0] != "root" and meta["parents"][0] not in self.files:
                return httpx.Response(404, json={"error": {"message": "File not found"}})
            file_id = self.add(meta["name"], meta["parents"][0], meta.get("mimeType", ""))
            return httpx.Response(200, json=self._view(self.files[file_id]))
        if request.method == "PATCH" and path.startswith("/drive/v3/files/"):
            file_id = path.rsplit("/", 1)[1]
            if file_id not in self.files:
                return httpx.Response(404, json={})
            body = json.loads(request.content)
            if "trashed" in body:
                self.files[file_id]["trashed"] = body["trashed"]
            return httpx.Response(200, json={"id": file_id})
        return httpx.Response(404, json={})

    @staticmethod
    def _view(f: dict) -> dict:
        return {"id": f["id"], "webViewLink": f"https://drive.google.com/file/d/{f['id']}/view"}

    def _upload(self, request: httpx.Request) -> httpx.Response:
        kind = request.url.params.get("uploadType")
        update_id = request.url.path.rsplit("/", 1)[1] if request.method == "PATCH" else None
        if update_id and update_id not in self.files:
            return httpx.Response(404, json={})
        if kind == "multipart":
            meta, content = self._parse_multipart(request)
            if self._missing_parent(meta):
                return httpx.Response(404, json={"error": {"message": "File not found"}})
            return httpx.Response(200, json=self._save(meta, content, update_id))
        if kind == "resumable":
            meta = json.loads(request.content)
            if self._missing_parent(meta):
                return httpx.Response(404, json={"error": {"message": "File not found"}})
            session = f"{UPLOAD_HOST}/session/{uuid4().hex[:8]}"
            self.sessions[session] = {
                "meta": meta,
                "update_id": update_id,
                "data": b"",
                "total": int(request.headers["X-Upload-Content-Length"]),
            }
            return httpx.Response(200, headers={"Location": session})
        return httpx.Response(400, json={})

    def _missing_parent(self, meta: dict) -> bool:
        parents = meta.get("parents", [])
        return bool(parents) and parents[0] != "root" and parents[0] not in self.files

    def _save(self, meta: dict, content: bytes, update_id: str | None) -> dict:
        parents = meta.get("parents", [])
        if update_id:
            self.files[update_id]["content"] = content
            return self._view(self.files[update_id])
        file_id = self.add(meta["name"], parents[0], meta.get("mimeType", ""), content)
        return self._view(self.files[file_id])

    @staticmethod
    def _parse_multipart(request: httpx.Request) -> tuple[dict, bytes]:
        boundary = request.headers["Content-Type"].split("boundary=")[1].encode()
        parts = [p for p in request.content.split(b"--" + boundary) if p.strip(b"-\r\n")]
        meta_part, media_part = parts[0], parts[1]
        meta = json.loads(meta_part.split(b"\r\n\r\n", 1)[1].strip())
        media = media_part.split(b"\r\n\r\n", 1)[1]
        return meta, media.removesuffix(b"\r\n")

    def _session_put(self, request: httpx.Request) -> httpx.Response:
        session = self.sessions[str(request.url)]
        content_range = request.headers["Content-Range"]
        if content_range.startswith("bytes */"):  # consulta de estado
            received = len(session["data"])
            if received >= session["total"]:
                return httpx.Response(200, json=self._finish(session))
            return httpx.Response(
                308, headers={"Range": f"bytes=0-{received - 1}"} if received else {}
            )
        start = int(re.match(r"bytes (\d+)-", content_range).group(1))
        if start != len(session["data"]):
            return httpx.Response(400, json={"error": "desalineado"})
        session["data"] += request.content
        if len(session["data"]) >= session["total"]:
            return httpx.Response(200, json=self._finish(session))
        return httpx.Response(308, headers={"Range": f"bytes=0-{len(session['data']) - 1}"})

    def _finish(self, session: dict) -> dict:
        return self._save(session["meta"], session["data"], session["update_id"])

    # ── fallos ──

    def fail(self, status: int, body=None, headers=None, *, when=None, effect=None) -> None:
        self.faults.append(
            Fault(
                when or (lambda r: r.url.host in ("www.googleapis.com", "upload.test")),
                status,
                body,
                headers,
                effect,
            )
        )


def make_drive(
    google: FakeGoogle | None = None,
    connections: MemoryConnections | None = None,
    *,
    cipher: TokenCipher | None = None,
    sleeps: list[float] | None = None,
) -> tuple[GoogleDrive, FakeGoogle, MemoryConnections]:
    google = google or FakeGoogle()
    connections = connections if connections is not None else MemoryConnections()

    async def no_sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    client = httpx.AsyncClient(transport=httpx.MockTransport(google))
    drive = GoogleDrive(CONFIG, connections, cipher or new_cipher(), client=client, sleep=no_sleep)
    return drive, google, connections


def state_of(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


class FakeTarget:
    """SyncTarget en memoria para probar el job de subida sin tocar Google."""

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
        from app.storage.google_drive import NotConnected

        self.attempted.append(path)
        if self.raise_not_connected:
            raise NotConnected("revocado")
        if any(path.endswith(f) for f in self.fail):
            raise RuntimeError("boom")
        self.uploads.append((str(user_id), path, len(data), mime))
        return RemoteFile(id=f"remote-{uuid4().hex[:6]}", url=f"https://drive.test/{path}")

    async def delete(self, user_id, remote_id) -> None:
        self.deleted.append(remote_id)
        if self.fail_delete:
            raise RuntimeError("boom")

    async def folder_url(self, user_id, path) -> str | None:
        return f"https://drive.test/folder/{path}"
