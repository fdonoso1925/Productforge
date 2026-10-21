import asyncio
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.deps import get_services
from app.main import create_app
from app.pipeline.uploads import MAX_ATTEMPTS, UploadQueue
from app.storage.onedrive import OneDrive, OneDriveConfig
from tests.fake_microsoft import FakeMicrosoft, make_onedrive
from tests.memory import MemoryFiles, MemoryJobs, MemoryProducts
from tests.test_auth import ALLOWED, SECRET, make_token

USER = str(uuid4())
TOKENS = {"access_token": "ACCESS-1", "refresh_token": "REFRESH-1", "expires_in": 3600}
SETTINGS = Settings(
    _env_file=None,
    supabase_jwt_secret=SECRET,
    allowed_emails=[ALLOWED],
    frontend_url="http://localhost:3000/",
)


def run(coro):
    return asyncio.run(coro)


class Ctx:
    def __init__(self, *, configured: bool = True) -> None:
        self.ms = FakeMicrosoft()
        if configured:
            self.onedrive, _, self.connections = make_onedrive(self.ms)
        else:
            from tests.memory import MemoryConnections

            self.connections = MemoryConnections()
            self.onedrive = OneDrive(
                OneDriveConfig("", "", "consumers", "x"), self.connections, None
            )
        self.products, self.files, self.jobs = MemoryProducts(), MemoryFiles(), MemoryJobs()
        self.services = SimpleNamespace(
            products=self.products,
            files=self.files,
            jobs=self.jobs,
            onedrive=self.onedrive,
            upload_queue=UploadQueue(self.onedrive, self.jobs, self.files),
            settings=SETTINGS,
        )
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: SETTINGS
        app.dependency_overrides[get_services] = lambda: self.services
        self.client = TestClient(app, follow_redirects=False)
        self.auth = {"Authorization": f"Bearer {make_token(sub=USER)}"}
        self.product = self.products.add(
            user_id=USER,
            niche="Finanças",
            market="pt-BR",
            title="Kit",
            created_at="2026-10-21T10:00:00+00:00",
            prompt_version="t",
        )

    def get(self, path, **kw):
        return self.client.get(path, headers=self.auth, **kw)

    def post(self, path, **kw):
        return self.client.post(path, headers=self.auth, **kw)

    def add_file(self, status="pending", attempts=0, file_type="pdf") -> dict:
        return run(
            self.files.add(
                product_id=self.product["id"],
                user_id=USER,
                item_id=None,
                file_type=file_type,
                storage_path=f"{USER}/{self.product['id']}/principal/{uuid4().hex[:6]}.{file_type}",
                size=1,
                onedrive_status=status,
                upload_attempts=attempts,
            )
        )

    def connect_user(self) -> None:
        self.ms.token.append((200, TOKENS))
        state = parse_qs(urlparse(self.onedrive.authorize_url(UUID(USER), "es")).query)["state"][0]
        run(self.onedrive.complete_authorization("code", state))

    def state(self, locale="es") -> str:
        return parse_qs(urlparse(self.onedrive.authorize_url(UUID(USER), locale)).query)["state"][0]


@pytest.fixture
def ctx() -> Ctx:
    return Ctx()


# ─────────────────────────── estado y conexión ───────────────────────────


def test_status_when_not_configured_or_not_connected(ctx: Ctx) -> None:
    assert ctx.get("/storage/onedrive/status").json() == {
        "configured": True,
        "connected": False,
        "account": None,
    }
    unconfigured = Ctx(configured=False)
    assert unconfigured.get("/storage/onedrive/status").json()["configured"] is False


def test_endpoints_require_a_session(ctx: Ctx) -> None:
    for method, path in [
        ("get", "/storage/onedrive/status"),
        ("post", "/storage/onedrive/connect"),
        ("delete", "/storage/onedrive"),
        ("post", "/storage/onedrive/sync"),
        ("get", f"/products/{ctx.product['id']}/onedrive"),
    ]:
        assert getattr(ctx.client, method)(path).status_code == 401, path


def test_connect_returns_the_microsoft_authorization_url(ctx: Ctx) -> None:
    url = ctx.post("/storage/onedrive/connect", json={"locale": "pt"}).json()["url"]
    assert url.startswith("https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?")
    assert ctx.onedrive.read_state(parse_qs(urlparse(url).query)["state"][0])["locale"] == "pt"


def test_connect_without_backend_credentials_explains_what_is_missing() -> None:
    response = Ctx(configured=False).post("/storage/onedrive/connect", json={})
    assert response.status_code == 503 and "MS_CLIENT_ID" in response.json()["detail"]


def test_connect_rejects_unknown_locale(ctx: Ctx) -> None:
    assert ctx.post("/storage/onedrive/connect", json={"locale": "xx"}).status_code == 422


# ─────────────────────────── callback de Microsoft ───────────────────────────


def callback(ctx: Ctx, **params):
    return ctx.client.get(
        "/storage/onedrive/callback", params=params
    )  # sin JWT: viene del navegador


def test_callback_connects_stores_tokens_and_syncs_existing_files(ctx: Ctx) -> None:
    ctx.add_file()
    ctx.ms.token.append((200, TOKENS))
    response = callback(ctx, code="abc", state=ctx.state("pt"))

    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:3000/pt/settings?onedrive=connected"
    assert run(ctx.onedrive.is_connected(UUID(USER))) is True
    assert [j["kind"] for j in ctx.jobs.rows.values()] == ["upload"]  # copia lo que ya existía
    status = ctx.get("/storage/onedrive/status").json()
    assert status["connected"] is True and status["account"] == "ana@outlook.com"


@pytest.mark.parametrize(
    "params",
    [
        {"code": "abc", "state": "estado-falso"},
        {"code": "abc"},
        {"state": "x"},
        {},
    ],
)
def test_callback_with_missing_or_forged_state_connects_nothing(ctx: Ctx, params) -> None:
    response = callback(ctx, **params)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/es/settings?onedrive=error")
    assert ctx.connections.rows == {} and ctx.ms.requests == []


def test_callback_when_the_user_denies_access(ctx: Ctx) -> None:
    response = callback(ctx, error="access_denied", state=ctx.state("pt"))
    assert response.headers["location"] == "http://localhost:3000/pt/settings?onedrive=denied"
    assert ctx.connections.rows == {}


def test_callback_when_microsoft_rejects_the_code(ctx: Ctx) -> None:
    ctx.ms.token.append((400, {"error": "invalid_grant"}))
    response = callback(ctx, code="vencido", state=ctx.state())
    assert response.headers["location"].endswith("?onedrive=error") and ctx.connections.rows == {}


def test_callback_never_redirects_outside_the_configured_frontend(ctx: Ctx) -> None:
    for params in ({"code": "a", "state": "b", "next": "https://evil.test"}, {"error": "x"}):
        location = callback(ctx, **params).headers["location"]
        assert location.startswith("http://localhost:3000/")


def test_disconnect_forgets_tokens_but_requires_no_extra_confirmation(ctx: Ctx) -> None:
    ctx.connect_user()
    assert ctx.client.delete("/storage/onedrive", headers=ctx.auth).status_code == 204
    assert ctx.get("/storage/onedrive/status").json()["connected"] is False


# ─────────────────────────── sincronizar ───────────────────────────


def test_sync_all_needs_a_connection_then_queues_products_with_pending_files(ctx: Ctx) -> None:
    ctx.add_file()
    assert ctx.post("/storage/onedrive/sync").status_code == 409
    ctx.connect_user()
    response = ctx.post("/storage/onedrive/sync")
    assert response.status_code == 202 and response.json() == {"products": 1}
    assert ctx.post("/storage/onedrive/sync").json() == {"products": 0}  # ya hay una pendiente


def test_product_status_counts_files_and_ignores_the_zip(ctx: Ctx) -> None:
    ctx.connect_user()
    for status in ("uploaded", "uploaded", "pending", "failed"):
        ctx.add_file(status)
    ctx.add_file("skipped", file_type="zip")
    ctx.ms.graph.append((200, {"webUrl": "https://1drv.ms/carpeta"}))

    body = ctx.get(f"/products/{ctx.product['id']}/onedrive").json()

    assert body == {
        "connected": True,
        "total": 4,
        "uploaded": 2,
        "pending": 1,
        "failed": 1,
        "syncing": False,
        "folder_url": "https://1drv.ms/carpeta",
    }
    folder_request = ctx.ms.graph_requests()[-1]
    assert "pt-BR/financas/2026-10-21_kit" in str(folder_request.url)


def test_product_status_does_not_call_graph_while_syncing(ctx: Ctx) -> None:
    ctx.connect_user()
    ctx.add_file("uploaded")
    run(ctx.jobs.enqueue(product_id=ctx.product["id"], user_id=USER, kind="upload", payload={}))
    body = ctx.get(f"/products/{ctx.product['id']}/onedrive").json()
    assert body["syncing"] is True and body["folder_url"] is None
    assert ctx.ms.graph_requests() == []


def test_product_status_survives_a_graph_failure(ctx: Ctx) -> None:
    ctx.connect_user()
    ctx.add_file("uploaded")
    ctx.ms.graph += [(503, {})] * 4
    body = ctx.get(f"/products/{ctx.product['id']}/onedrive")
    assert body.status_code == 200 and body.json()["folder_url"] is None


def test_product_status_when_not_connected(ctx: Ctx) -> None:
    ctx.add_file()
    body = ctx.get(f"/products/{ctx.product['id']}/onedrive").json()
    assert body["connected"] is False and body["pending"] == 1 and body["folder_url"] is None


def test_manual_product_sync_resets_exhausted_attempts_and_queues_once(ctx: Ctx) -> None:
    ctx.connect_user()
    stuck = ctx.add_file("failed", attempts=MAX_ATTEMPTS)
    path = f"/products/{ctx.product['id']}/onedrive/sync"

    assert ctx.post(path).json() == {"products": 1}
    assert ctx.files.rows[stuck["id"]]["upload_attempts"] == 0
    assert ctx.post(path).json() == {"products": 0}
    assert len([j for j in ctx.jobs.rows.values() if j["kind"] == "upload"]) == 1


def test_product_sync_requires_connection(ctx: Ctx) -> None:
    ctx.add_file()
    assert ctx.post(f"/products/{ctx.product['id']}/onedrive/sync").status_code == 409


def test_other_users_product_is_not_visible(ctx: Ctx) -> None:
    ctx.connect_user()
    other = {"Authorization": f"Bearer {make_token(sub=str(uuid4()))}"}
    assert (
        ctx.client.get(f"/products/{ctx.product['id']}/onedrive", headers=other).status_code == 404
    )
    assert (
        ctx.client.post(f"/products/{ctx.product['id']}/onedrive/sync", headers=other).status_code
        == 404
    )
