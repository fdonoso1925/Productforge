import asyncio
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest

from app.storage.crypto import from_bytea, to_bytea
from app.storage.onedrive import (
    CHUNK_SIZE,
    NotConnected,
    OneDrive,
    OneDriveError,
    drive_path,
)
from tests.fake_microsoft import CONFIG, UPLOAD_HOST, FakeMicrosoft, make_onedrive, new_cipher
from tests.memory import MemoryConnections

USER = uuid4()
TOKENS = {"access_token": "ACCESS-1", "refresh_token": "REFRESH-1", "expires_in": 3600}


def run(coro):
    return asyncio.run(coro)


def connect(od: OneDrive, ms: FakeMicrosoft, tokens: dict | None = None) -> None:
    """Completa el flujo de autorización con Microsoft simulado."""
    ms.token.append((200, tokens or TOKENS))
    url = od.authorize_url(USER, "pt")
    state = parse_qs(urlparse(url).query)["state"][0]
    run(od.complete_authorization("auth-code", state))


# ─────────────────────────── cifrado y estado ───────────────────────────


def test_cipher_roundtrip_and_wrong_key_fails() -> None:
    cipher = new_cipher()
    token = cipher.encrypt("secreto")
    assert b"secreto" not in token and cipher.decrypt(token) == "secreto"
    with pytest.raises(Exception):  # noqa: B017, PT011 - InvalidToken
        new_cipher().decrypt(token)


def test_bytea_hex_roundtrip() -> None:
    assert from_bytea(to_bytea(b"\x00\xffabc")) == b"\x00\xffabc"


def test_state_expires_tampering_and_other_purposes_are_rejected() -> None:
    cipher = new_cipher()
    state = cipher.seal("onedrive-oauth", {"uid": "1"})
    assert cipher.unseal("onedrive-oauth", state, 600) == {"purpose": "onedrive-oauth", "uid": "1"}
    assert cipher.unseal("onedrive-oauth", state, -1) is None  # vencido
    assert cipher.unseal("otro", state, 600) is None  # otro propósito
    assert cipher.unseal("onedrive-oauth", state[:-4] + "AAAA", 600) is None  # alterado
    assert cipher.unseal("onedrive-oauth", "basura", 600) is None
    assert new_cipher().unseal("onedrive-oauth", state, 600) is None  # otra clave


# ─────────────────────────── autorización ───────────────────────────


def test_authorize_url_asks_only_for_app_folder_scope() -> None:
    od, _, _ = make_onedrive()
    url = urlparse(od.authorize_url(USER, "es"))
    query = parse_qs(url.query)
    assert url.netloc == "login.microsoftonline.com"
    assert url.path == "/consumers/oauth2/v2.0/authorize"
    assert query["client_id"] == [CONFIG.client_id]
    assert query["redirect_uri"] == [CONFIG.redirect_uri]
    scopes = query["scope"][0].split()
    assert "Files.ReadWrite.AppFolder" in scopes and "offline_access" in scopes
    assert "Files.ReadWrite" not in scopes and "Files.ReadWrite.All" not in scopes
    assert query["response_type"] == ["code"]
    assert od.read_state(query["state"][0])["uid"] == str(USER)


def test_unconfigured_onedrive_refuses_to_authorize() -> None:
    od = OneDrive(CONFIG.__class__("", "", "consumers", "x"), MemoryConnections(), None)
    assert od.configured() is False
    with pytest.raises(OneDriveError):
        od.authorize_url(USER, "es")


def test_authorization_stores_tokens_encrypted_and_labels_the_account() -> None:
    od, ms, connections = make_onedrive()
    connect(od, ms)

    row = connections.rows[(str(USER), "onedrive")]
    assert row["account_label"] == "ana@outlook.com"
    for blob in (row["access_token_enc"], row["refresh_token_enc"]):
        assert isinstance(blob, bytes) and b"ACCESS-1" not in blob and b"REFRESH-1" not in blob
    form = ms.token_requests()[0]
    assert form["grant_type"] == "authorization_code" and form["code"] == "auth-code"
    assert form["client_secret"] == CONFIG.client_secret
    assert run(od.is_connected(USER)) is True
    assert run(od.access_token(USER)) == "ACCESS-1"  # sin renovar: no vence todavía
    assert len(ms.token_requests()) == 1


def test_authorization_with_bad_state_is_rejected_without_calling_microsoft() -> None:
    od, ms, connections = make_onedrive()
    with pytest.raises(OneDriveError):
        run(od.complete_authorization("code", "estado-falso"))
    assert ms.requests == [] and connections.rows == {}


def test_failed_code_exchange_stores_nothing() -> None:
    od, ms, connections = make_onedrive()
    ms.token.append((400, {"error": "invalid_request", "error_description": "secreto?"}))
    state = parse_qs(urlparse(od.authorize_url(USER, "es")).query)["state"][0]
    with pytest.raises(OneDriveError) as exc:
        run(od.complete_authorization("code", state))
    assert "secreto" not in str(exc.value) and connections.rows == {}


# ─────────────────────────── renovación de tokens ───────────────────────────


def expire(connections: MemoryConnections) -> None:
    row = connections.rows[(str(USER), "onedrive")]
    row["expires_at"] = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()


def test_expired_token_is_refreshed_and_refresh_token_rotates() -> None:
    cipher = new_cipher()
    od, ms, connections = make_onedrive(cipher=cipher)
    connect(od, ms)
    expire(connections)
    ms.token.append(
        (200, {"access_token": "ACCESS-2", "refresh_token": "REFRESH-2", "expires_in": 3600})
    )

    assert run(od.access_token(USER)) == "ACCESS-2"
    refresh_form = ms.token_requests()[-1]
    assert refresh_form["grant_type"] == "refresh_token"
    assert refresh_form["refresh_token"] == "REFRESH-1"
    row = connections.rows[(str(USER), "onedrive")]
    assert cipher.decrypt(row["refresh_token_enc"]) == "REFRESH-2"  # el nuevo reemplaza al viejo
    assert run(od.access_token(USER)) == "ACCESS-2"  # ya no vuelve a renovar
    assert len(ms.token_requests()) == 2


def test_concurrent_requests_refresh_only_once() -> None:
    od, ms, connections = make_onedrive()
    connect(od, ms)
    expire(connections)
    ms.token.append(
        (200, {"access_token": "ACCESS-2", "refresh_token": "REFRESH-2", "expires_in": 3600})
    )

    async def both():
        return await asyncio.gather(od.access_token(USER), od.access_token(USER))

    assert run(both()) == ["ACCESS-2", "ACCESS-2"]
    assert len(ms.token_requests()) == 2  # canje inicial + una sola renovación


def test_revoked_access_disconnects_and_asks_to_reconnect() -> None:
    od, ms, connections = make_onedrive()
    connect(od, ms)
    expire(connections)
    ms.token.append((400, {"error": "invalid_grant"}))
    with pytest.raises(NotConnected):
        run(od.access_token(USER))
    assert connections.rows == {} and run(od.is_connected(USER)) is False


def test_not_connected_user_cannot_upload() -> None:
    od, _, _ = make_onedrive()
    with pytest.raises(NotConnected):
        run(od.upload(USER, "a/b.pdf", b"x", "application/pdf"))


# ─────────────────────────── subidas ───────────────────────────


def test_drive_path_escapes_each_segment() -> None:
    assert drive_path("pt-BR/finanças pessoais/a b.pdf") == (
        "/me/drive/special/approot:/pt-BR/finan%C3%A7as%20pessoais/a%20b.pdf"
    )
    # Caracteres que cambiarían el significado de la URL quedan escapados dentro del segmento.
    assert drive_path("a/b?c#d") == "/me/drive/special/approot:/a/b%3Fc%23d"


def test_small_file_uses_a_single_put_that_replaces_existing() -> None:
    od, ms, _ = make_onedrive()
    connect(od, ms)
    ms.graph.append((201, {"id": "abc", "webUrl": "https://1drv.ms/abc"}))

    remote = run(
        od.upload(
            USER, "pt-BR/nicho/2026-10-21_x/principal/guia final.pdf", b"PDF", "application/pdf"
        )
    )

    assert (remote.id, remote.url) == ("abc", "https://1drv.ms/abc")
    [req] = ms.graph_requests()
    assert req.method == "PUT"
    assert "/approot:/pt-BR/nicho/2026-10-21_x/principal/guia%20final.pdf:/content" in str(req.url)
    assert "conflictBehavior=replace" in str(req.url)
    assert req.headers["Authorization"] == "Bearer ACCESS-1"
    assert req.headers["Content-Type"] == "application/pdf" and req.content == b"PDF"


def test_large_file_uses_an_upload_session_in_aligned_chunks() -> None:
    od, ms, _ = make_onedrive()
    connect(od, ms)
    size = CHUNK_SIZE * 2 + 1000
    assert CHUNK_SIZE % (320 * 1024) == 0  # Graph exige múltiplos de 320 KiB
    ms.graph.append((200, {"uploadUrl": f"{UPLOAD_HOST}/session/1"}))
    ms.chunks += [(202, {}), (202, {}), (201, {"id": "big", "webUrl": "https://1drv.ms/big"})]

    remote = run(od.upload(USER, "a/big.zip", b"x" * size, "application/zip"))

    assert remote.id == "big"
    session, *_ = ms.graph_requests()
    assert session.method == "POST" and str(session.url).endswith(":/createUploadSession")
    puts = [r for r in ms.requests if r.url.host == "upload.test"]
    assert [r.headers["Content-Range"] for r in puts] == [
        f"bytes 0-{CHUNK_SIZE - 1}/{size}",
        f"bytes {CHUNK_SIZE}-{CHUNK_SIZE * 2 - 1}/{size}",
        f"bytes {CHUNK_SIZE * 2}-{size - 1}/{size}",
    ]
    assert all("Authorization" not in r.headers for r in puts)  # la URL ya viene autenticada
    assert sum(len(r.content) for r in puts) == size


def test_throttling_honors_retry_after_and_keeps_headers_on_retry() -> None:
    sleeps: list[float] = []
    od, ms, _ = make_onedrive(sleeps=sleeps)
    connect(od, ms)
    ms.graph += [(429, {}, {"Retry-After": "7"}), (503, {}), (201, {"id": "ok", "webUrl": "u"})]

    remote = run(od.upload(USER, "a/b.pdf", b"x", "application/pdf"))

    assert remote.id == "ok"
    assert sleeps == [7.0, 2.0]  # Retry-After del servidor; luego backoff 2**intento
    assert all(r.headers["Content-Type"] == "application/pdf" for r in ms.graph_requests())


def test_gives_up_after_max_attempts_without_leaking_details() -> None:
    od, ms, _ = make_onedrive()
    connect(od, ms)
    ms.graph += [(503, {"error": "detalle interno"})] * 4
    with pytest.raises(OneDriveError) as exc:
        run(od.upload(USER, "a/b.pdf", b"x", "application/pdf"))
    assert "503" in str(exc.value) and "detalle" not in str(exc.value)
    assert len(ms.graph_requests()) == 4


def test_client_errors_are_not_retried() -> None:
    od, ms, _ = make_onedrive()
    connect(od, ms)
    ms.graph.append((403, {}))
    with pytest.raises(OneDriveError):
        run(od.upload(USER, "a/b.pdf", b"x", "application/pdf"))
    assert len(ms.graph_requests()) == 1


def test_401_refreshes_the_token_once_and_retries() -> None:
    od, ms, _ = make_onedrive()
    connect(od, ms)
    ms.graph += [(401, {}), (201, {"id": "ok", "webUrl": "u"})]
    ms.token.append(
        (200, {"access_token": "ACCESS-2", "refresh_token": "REFRESH-2", "expires_in": 3600})
    )

    assert run(od.upload(USER, "a/b.pdf", b"x", "application/pdf")).id == "ok"
    first, second = ms.graph_requests()
    assert first.headers["Authorization"] == "Bearer ACCESS-1"
    assert second.headers["Authorization"] == "Bearer ACCESS-2"


def test_persistent_401_fails_instead_of_looping() -> None:
    od, ms, _ = make_onedrive()
    connect(od, ms)
    ms.graph += [(401, {}), (401, {})]
    ms.token.append(
        (200, {"access_token": "ACCESS-2", "refresh_token": "REFRESH-2", "expires_in": 3600})
    )
    with pytest.raises(OneDriveError):
        run(od.upload(USER, "a/b.pdf", b"x", "application/pdf"))


def test_delete_treats_missing_item_as_success() -> None:
    od, ms, _ = make_onedrive()
    connect(od, ms)
    ms.graph += [(204, {}), (404, {})]
    run(od.delete(USER, "item-1"))
    run(od.delete(USER, "item-2"))
    assert [r.method for r in ms.graph_requests()] == ["DELETE", "DELETE"]


def test_folder_url_returns_none_when_missing() -> None:
    od, ms, _ = make_onedrive()
    connect(od, ms)
    ms.graph += [(200, {"webUrl": "https://1drv.ms/folder"}), (404, {})]
    assert run(od.folder_url(USER, "pt-BR/x")) == "https://1drv.ms/folder"
    assert run(od.folder_url(USER, "pt-BR/y")) is None


def test_disconnect_forgets_tokens() -> None:
    od, ms, connections = make_onedrive()
    connect(od, ms)
    run(od.disconnect(USER))
    assert connections.rows == {} and run(od.is_connected(USER)) is False
