"""Ajustes: credenciales de Meta y Hotmart guardadas cifradas, con respaldo en el entorno."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from cryptography.fernet import Fernet

from app.config import Settings
from app.integrations.credentials import (
    CredentialStore,
    InvalidCredentials,
    resolve_hotmart,
    resolve_meta,
)
from app.storage.crypto import TokenCipher
from tests.test_api_ads import AdsWorld
from tests.test_pipeline import USER

TOKEN = "EAAB-fake-token-1234567890"
HOTMART_SECRET = "hotmart-secret-abcdef-9999"
META = {"access_token": TOKEN, "ad_account_id": "act_123456", "page_id": "99887766"}
HOTMART = {"client_id": "client-id-1", "client_secret": HOTMART_SECRET}


class MemoryRepo:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], bytes] = {}

    async def get(self, user_id, provider):
        return self.rows.get((str(user_id), provider))

    async def save(self, user_id, provider, data_enc) -> None:
        self.rows[(str(user_id), provider)] = data_enc

    async def delete(self, user_id, provider) -> None:
        self.rows.pop((str(user_id), provider), None)


def make_store(settings: Settings | None = None, key: str | None = None):
    repo = MemoryRepo()
    cipher = TokenCipher(key or Fernet.generate_key().decode())
    return CredentialStore(repo, cipher, settings or Settings()), repo


def run(coro):
    return asyncio.run(coro)


def test_credentials_are_stored_encrypted_and_never_in_plain_text() -> None:
    store, repo = make_store()
    run(store.save(USER, "meta", META))
    blob = next(iter(repo.rows.values()))
    assert TOKEN.encode() not in blob and b"99887766" not in blob
    assert run(store.saved(USER, "meta")) == META


def test_status_never_returns_a_secret_only_its_last_four_characters() -> None:
    store, _ = make_store()
    run(store.save(USER, "meta", META))
    status = run(store.status(USER, "meta"))
    assert status["connected"] and status["has_saved"] and status["missing"] == []
    token = next(f for f in status["fields"] if f["key"] == "access_token")
    assert token["hint"] == "••••7890" and TOKEN not in str(status)
    assert token["source"] == "saved" and token["set"]
    page = next(f for f in status["fields"] if f["key"] == "page_id")
    assert page["hint"] == "99887766"  # los datos no secretos sí se muestran


def test_not_connected_until_the_required_fields_are_there() -> None:
    store, _ = make_store()
    run(store.save(USER, "meta", {"access_token": TOKEN}))
    status = run(store.status(USER, "meta"))
    assert not status["connected"]
    assert status["missing"] == ["ad_account_id", "page_id"]


def test_saving_again_keeps_what_was_not_sent() -> None:
    store, _ = make_store()
    run(store.save(USER, "meta", META))
    run(store.save(USER, "meta", {"access_token": "", "pixel_id": "5551234"}))
    saved = run(store.saved(USER, "meta"))
    assert saved["access_token"] == TOKEN and saved["pixel_id"] == "5551234"


def test_bad_values_are_rejected() -> None:
    store, _ = make_store()
    for provider, values in [
        ("meta", {"ad_account_id": "no es un número"}),
        ("meta", {"access_token": "con espacios y símbolos <script>"}),
        ("meta", {"pixel_id": "12"}),
        ("meta", {"desconocido": "x"}),
        ("hotmart", {"client_secret": "corto"}),
    ]:
        try:
            run(store.save(USER, provider, values))
        except InvalidCredentials:
            continue
        raise AssertionError((provider, values))


def test_without_an_encryption_key_nothing_can_be_saved() -> None:
    store = CredentialStore(MemoryRepo(), None, Settings())
    assert not store.can_save
    try:
        run(store.save(USER, "meta", META))
    except InvalidCredentials as exc:
        assert "TOKEN_ENCRYPTION_KEY" in str(exc)
    else:
        raise AssertionError


def test_the_environment_still_works_and_saved_values_win_field_by_field() -> None:
    env = Settings(
        meta_access_token="ENVTOKEN-1234567", meta_ad_account_id="777777", meta_page_id="888888"
    )
    store, _ = make_store(env)
    status = run(store.status(USER, "meta"))
    assert status["connected"] and not status["has_saved"]
    assert {f["source"] for f in status["fields"] if f["set"]} == {"env"}
    run(store.save(USER, "meta", {"page_id": "123456789"}))
    merged = run(store.effective(USER, "meta"))
    assert merged["page_id"] == "123456789" and merged["ad_account_id"] == "777777"


def test_a_changed_encryption_key_reads_as_not_saved_instead_of_crashing() -> None:
    store, repo = make_store()
    run(store.save(USER, "meta", META))
    other = CredentialStore(repo, TokenCipher(Fernet.generate_key().decode()), Settings())
    assert run(other.saved(USER, "meta")) == {}


def test_clients_use_saved_credentials_and_fall_back_to_the_environment() -> None:
    store, _ = make_store()
    env_meta = object()
    deps = SimpleNamespace(credentials=store, meta=env_meta, hotmart=None)
    assert run(resolve_meta(deps, USER)) is env_meta  # nada guardado → entorno
    run(store.save(USER, "meta", META))
    saved = run(resolve_meta(deps, USER))
    assert saved is not env_meta and saved.configured()
    assert run(resolve_meta(deps, USER)) is saved  # mismo cliente mientras no cambie
    other_user = uuid4()
    assert run(resolve_meta(deps, other_user)) is env_meta  # cada usuario ve lo suyo
    run(store.save(USER, "hotmart", HOTMART))
    assert run(resolve_hotmart(deps, USER)).configured()
    run(store.delete(USER, "meta"))
    assert run(resolve_meta(deps, USER)) is env_meta


# ───────────────────────────── API ─────────────────────────────


def world():
    w = AdsWorld()
    w.store, w.repo = make_store()
    w.services.credentials = w.store
    return w


def test_the_settings_endpoints_save_report_and_disconnect() -> None:
    w = world()
    empty = w.client.get("/integrations").json()
    assert not empty["meta"]["connected"] and not empty["hotmart"]["connected"]
    assert empty["meta"]["can_save"]

    saved = w.client.put("/integrations/meta", json=META).json()
    assert saved["connected"] and saved["has_saved"]
    assert TOKEN not in w.client.get("/integrations").text  # el valor nunca vuelve

    assert w.client.put("/integrations/hotmart", json=HOTMART).json()["connected"]
    assert HOTMART_SECRET not in w.client.get("/integrations").text

    assert w.client.delete("/integrations/meta").status_code == 204
    after = w.client.get("/integrations").json()
    assert not after["meta"]["connected"] and after["hotmart"]["connected"]


def test_the_settings_endpoints_validate_and_require_a_session() -> None:
    w = world()
    bad = w.client.put("/integrations/meta", json={"ad_account_id": "abc"})
    assert bad.status_code == 422
    assert w.client.put("/integrations/meta", json={"otro": "x"}).status_code == 422
    assert w.client.put("/integrations/tiktok", json={}).status_code == 405  # no existe
    assert w.client.delete("/integrations/tiktok").status_code == 422
    w.client.headers.pop("Authorization")
    assert w.client.get("/integrations").status_code in (401, 403)
    assert w.client.put("/integrations/meta", json=META).status_code in (401, 403)
    assert w.client.delete("/integrations/meta").status_code in (401, 403)


def test_saving_without_an_encryption_key_explains_what_is_missing() -> None:
    w = AdsWorld()
    w.services.credentials = CredentialStore(MemoryRepo(), None, Settings())
    resp = w.client.put("/integrations/meta", json=META)
    assert resp.status_code == 503 and "TOKEN_ENCRYPTION_KEY" in resp.text
    assert not w.client.get("/integrations").json()["meta"]["can_save"]


def test_saved_hotmart_credentials_make_the_hotmart_status_connected() -> None:
    w = world()
    w.services.hotmart = None
    w.services.hotmart_repo = SimpleNamespace(get_sync=lambda user_id: _none())
    assert w.client.get("/hotmart/status").json()["configured"] is False
    w.client.put("/integrations/hotmart", json=HOTMART)
    assert w.client.get("/hotmart/status").json()["configured"] is True


async def _none():
    return None


def test_the_connection_test_reports_missing_data_without_calling_anyone() -> None:
    w = world()
    assert w.client.post("/integrations/meta/test").json() == {
        "ok": False,
        "detail": "faltan datos",
    }
    assert w.client.post("/integrations/hotmart/test").json()["ok"] is False


class NoTableDb:
    """Supabase sin la migración: PostgREST responde 404 a la tabla que no existe."""

    def _error(self):
        import httpx

        request = httpx.Request("GET", "https://x.supabase.co/rest/v1/integration_credentials")
        return httpx.HTTPStatusError(
            "404", request=request, response=httpx.Response(404, request=request)
        )

    async def select(self, *a, **k):
        raise self._error()

    async def upsert(self, *a, **k):
        raise self._error()

    async def delete(self, *a, **k):
        raise self._error()


def test_without_the_migration_settings_still_load_and_saving_says_why() -> None:
    from app.integrations.credentials import CredentialRepo, MigrationMissing

    store = CredentialStore(
        CredentialRepo(NoTableDb()), TokenCipher(Fernet.generate_key().decode()), Settings()
    )
    status = run(store.status(USER, "meta"))
    assert status["connected"] is False and status["has_saved"] is False
    assert run(store.meta_client(USER)) is None
    try:
        run(store.save(USER, "meta", META))
    except MigrationMissing:
        pass
    else:
        raise AssertionError
    run(store.delete(USER, "meta"))  # no revienta
