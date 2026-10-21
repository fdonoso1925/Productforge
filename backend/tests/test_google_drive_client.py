import asyncio
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest

from app.storage.crypto import from_bytea, to_bytea
from app.storage.google_drive import (
    CHUNK_SIZE,
    DRIVE_SCOPE,
    MULTIPART_LIMIT,
    DriveError,
    GoogleConfig,
    GoogleDrive,
    NotConnected,
    escape_query,
)
from tests.fake_google import CONFIG, FakeGoogle, make_drive, new_cipher, state_of, tokens
from tests.memory import MemoryConnections

USER = uuid4()


def run(coro):
    return asyncio.run(coro)


def connect(drive: GoogleDrive, google: FakeGoogle, body: dict | None = None) -> None:
    google.token.append((200, body or tokens()))
    run(drive.complete_authorization("auth-code", state_of(drive.authorize_url(USER, "pt"))))


def expire(connections: MemoryConnections) -> None:
    connections.rows[(str(USER), "google_drive")]["expires_at"] = (
        datetime.now(UTC) - timedelta(minutes=5)
    ).isoformat()


def upload(drive, path="a/b.pdf", data=b"x", mime="application/pdf"):
    return run(drive.upload(USER, path, data, mime))


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
    state = cipher.seal("drive-oauth", {"uid": "1"})
    assert cipher.unseal("drive-oauth", state, 600) == {"purpose": "drive-oauth", "uid": "1"}
    assert cipher.unseal("drive-oauth", state, -1) is None  # vencido
    assert cipher.unseal("otro", state, 600) is None  # otro propósito
    assert cipher.unseal("drive-oauth", state[:-4] + "AAAA", 600) is None  # alterado
    assert cipher.unseal("drive-oauth", "basura", 600) is None
    assert new_cipher().unseal("drive-oauth", state, 600) is None  # otra clave


def test_query_literals_are_escaped() -> None:
    assert escape_query("it's a \\ test") == "it\\'s a \\\\ test"


# ─────────────────────────── autorización ───────────────────────────


def test_authorize_url_asks_for_the_minimal_scope_and_offline_access() -> None:
    drive, _, _ = make_drive()
    url = urlparse(drive.authorize_url(USER, "es"))
    query = parse_qs(url.query)
    assert (url.netloc, url.path) == ("accounts.google.com", "/o/oauth2/v2/auth")
    assert query["client_id"] == [CONFIG.client_id]
    assert query["redirect_uri"] == [CONFIG.redirect_uri]
    scopes = query["scope"][0].split()
    assert DRIVE_SCOPE in scopes
    assert "https://www.googleapis.com/auth/drive" not in scopes  # nunca el Drive completo
    assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]
    assert drive.read_state(query["state"][0])["uid"] == str(USER)


def test_unconfigured_drive_refuses_to_authorize() -> None:
    drive = GoogleDrive(GoogleConfig("", "", "x"), MemoryConnections(), None)
    assert drive.configured() is False
    with pytest.raises(DriveError):
        drive.authorize_url(USER, "es")


def test_authorization_stores_tokens_encrypted_and_labels_the_account() -> None:
    drive, google, connections = make_drive()
    connect(drive, google)

    row = connections.rows[(str(USER), "google_drive")]
    assert row["account_label"] == "ana@gmail.com"
    for blob in (row["access_token_enc"], row["refresh_token_enc"]):
        assert isinstance(blob, bytes) and b"ACCESS-1" not in blob and b"REFRESH-1" not in blob
    form = google.token_requests()[0]
    assert form["grant_type"] == "authorization_code" and form["code"] == "auth-code"
    assert (
        form["client_secret"] == CONFIG.client_secret
        and form["redirect_uri"] == CONFIG.redirect_uri
    )
    assert run(drive.is_connected(USER)) is True
    assert run(drive.access_token(USER)) == "ACCESS-1"  # sin renovar: aún no vence
    assert len(google.token_requests()) == 1


def test_authorization_without_the_drive_permission_is_rejected() -> None:
    """Google deja desmarcar permisos en la pantalla de consentimiento."""
    drive, google, connections = make_drive()
    google.token.append((200, tokens(scope="openid email")))
    with pytest.raises(DriveError):
        run(drive.complete_authorization("code", state_of(drive.authorize_url(USER, "es"))))
    assert connections.rows == {}


def test_authorization_without_refresh_token_is_rejected() -> None:
    drive, google, connections = make_drive()
    google.token.append((200, tokens(refresh=None)))
    with pytest.raises(DriveError):
        run(drive.complete_authorization("code", state_of(drive.authorize_url(USER, "es"))))
    assert connections.rows == {}


def test_authorization_with_bad_state_does_not_call_google() -> None:
    drive, google, connections = make_drive()
    with pytest.raises(DriveError):
        run(drive.complete_authorization("code", "estado-falso"))
    assert google.requests == [] and connections.rows == {}


def test_failed_code_exchange_stores_nothing_and_leaks_nothing() -> None:
    drive, google, connections = make_drive()
    google.token.append((400, {"error": "invalid_request", "error_description": "secreto?"}))
    with pytest.raises(DriveError) as exc:
        run(drive.complete_authorization("code", state_of(drive.authorize_url(USER, "es"))))
    assert "secreto" not in str(exc.value) and connections.rows == {}


# ─────────────────────────── renovación de tokens ───────────────────────────


def test_expired_token_is_refreshed_keeping_the_same_refresh_token() -> None:
    cipher = new_cipher()
    drive, google, connections = make_drive(cipher=cipher)
    connect(drive, google)
    expire(connections)
    google.token.append((200, tokens(access="ACCESS-2", refresh=None)))  # Google no rota el refresh

    assert run(drive.access_token(USER)) == "ACCESS-2"
    form = google.token_requests()[-1]
    assert form["grant_type"] == "refresh_token" and form["refresh_token"] == "REFRESH-1"
    row = connections.rows[(str(USER), "google_drive")]
    assert cipher.decrypt(row["refresh_token_enc"]) == "REFRESH-1"  # se conserva
    assert run(drive.access_token(USER)) == "ACCESS-2"
    assert len(google.token_requests()) == 2


def test_concurrent_requests_refresh_only_once() -> None:
    drive, google, connections = make_drive()
    connect(drive, google)
    expire(connections)
    google.token.append((200, tokens(access="ACCESS-2", refresh=None)))

    async def both():
        return await asyncio.gather(drive.access_token(USER), drive.access_token(USER))

    assert run(both()) == ["ACCESS-2", "ACCESS-2"]
    assert len(google.token_requests()) == 2  # canje inicial + una sola renovación


def test_revoked_or_expired_access_disconnects_and_asks_to_reconnect() -> None:
    """En modo Prueba, Google vence el refresh token a los 7 días (`invalid_grant`)."""
    drive, google, connections = make_drive()
    connect(drive, google)
    expire(connections)
    google.token.append((400, {"error": "invalid_grant"}))
    with pytest.raises(NotConnected):
        run(drive.access_token(USER))
    assert connections.rows == {} and run(drive.is_connected(USER)) is False


def test_not_connected_user_cannot_upload() -> None:
    drive, _, _ = make_drive()
    with pytest.raises(NotConnected):
        upload(drive)


def test_disconnect_revokes_at_google_and_forgets_tokens() -> None:
    drive, google, connections = make_drive()
    connect(drive, google)
    run(drive.disconnect(USER))
    assert connections.rows == {} and google.revoked == ["REFRESH-1"]
    assert run(drive.is_connected(USER)) is False


def test_disconnect_forgets_tokens_even_if_google_is_unreachable() -> None:
    drive, google, connections = make_drive()
    connect(drive, google)
    google.__class__.__call__  # noqa: B018 - el simulador sigue accesible
    drive._http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("x")))
    )
    run(drive.disconnect(USER))
    assert connections.rows == {}


# ─────────────────────────── carpetas y subidas ───────────────────────────


def test_creates_the_folder_tree_under_productforge_and_uploads_the_file() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)

    remote = upload(drive, "pt-BR/financas/2026-10-21_kit/principal/guia.pdf", b"PDF!")

    [created] = [f for f in google.files.values() if f["name"] == "guia.pdf"]
    assert (
        google.path_of(created["id"])
        == "ProductForge/pt-BR/financas/2026-10-21_kit/principal/guia.pdf"
    )
    assert created["content"] == b"PDF!" and created["mimeType"] == "application/pdf"
    assert remote.id == created["id"] and remote.url.startswith("https://drive.google.com/")


def test_folders_are_reused_not_duplicated() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)
    upload(drive, "pt-BR/x/principal/a.pdf")
    upload(drive, "pt-BR/x/principal/b.pdf")
    assert [len(google.folders(n)) for n in ("ProductForge", "pt-BR", "x", "principal")] == [
        1,
        1,
        1,
        1,
    ]


def test_parallel_uploads_to_a_new_folder_create_it_only_once() -> None:
    """Drive permite carpetas con el mismo nombre: sin serializar, 3 subidas crearían 3."""
    drive, google, _ = make_drive()
    connect(drive, google)

    async def many():
        await asyncio.gather(
            *(
                drive.upload(USER, f"pt-BR/x/bonus/{i}.pdf", b"x", "application/pdf")
                for i in range(3)
            )
        )

    run(many())
    assert len(google.folders("bonus")) == 1 and len(google.folders("ProductForge")) == 1
    assert len([f for f in google.files.values() if f["name"].endswith(".pdf")]) == 3


def test_existing_file_is_replaced_in_place_not_duplicated() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)
    first = upload(drive, "a/b.pdf", b"v1")
    second = upload(drive, "a/b.pdf", b"v2")
    assert first.id == second.id
    assert [f["content"] for f in google.by_name("b.pdf")] == [b"v2"]
    methods = [r.method for r in google.drive_requests() if "/upload/" in str(r.url)]
    assert methods == ["POST", "PATCH"]


def test_a_trashed_copy_does_not_get_reused() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)
    old = upload(drive, "a/b.pdf", b"v1")
    google.files[old.id]["trashed"] = True  # el usuario lo mandó a la papelera
    new = upload(drive, "a/b.pdf", b"v2")
    assert new.id != old.id


def test_names_with_quotes_are_searched_safely() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)
    upload(drive, "a/it's here.pdf", b"x")
    upload(drive, "a/it's here.pdf", b"y")
    assert [f["content"] for f in google.by_name("it's here.pdf")] == [b"y"]


def test_folder_deleted_by_hand_is_recreated() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)
    upload(drive, "pt-BR/x/principal/a.pdf")
    for folder in google.folders():  # el usuario borra todo desde Drive
        del google.files[folder["id"]]
    remote = upload(drive, "pt-BR/x/principal/b.pdf", b"nuevo")
    assert google.path_of(remote.id) == "ProductForge/pt-BR/x/principal/b.pdf"


def test_multipart_is_used_up_to_the_limit_and_resumable_above() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)
    upload(drive, "a/small.bin", b"x" * 1000, "application/octet-stream")
    upload(drive, "a/big.bin", b"y" * (MULTIPART_LIMIT + 1), "application/octet-stream")
    kinds = [
        parse_qs(urlparse(str(r.url)).query)["uploadType"][0]
        for r in google.drive_requests()
        if "/upload/" in str(r.url)
    ]
    assert kinds == ["multipart", "resumable"]
    assert len(google.by_name("big.bin")[0]["content"]) == MULTIPART_LIMIT + 1


def test_large_file_goes_in_aligned_chunks_and_content_arrives_intact() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)
    assert CHUNK_SIZE % (256 * 1024) == 0  # Drive exige múltiplos de 256 KiB
    data = bytes(range(256)) * ((CHUNK_SIZE * 2 + 1000) // 256 + 1)
    data = data[: CHUNK_SIZE * 2 + 1000]

    upload(drive, "a/big.zip", data, "application/zip")

    puts = [r for r in google.requests if r.url.host == "upload.test"]
    assert [r.headers["Content-Range"] for r in puts] == [
        f"bytes 0-{CHUNK_SIZE - 1}/{len(data)}",
        f"bytes {CHUNK_SIZE}-{CHUNK_SIZE * 2 - 1}/{len(data)}",
        f"bytes {CHUNK_SIZE * 2}-{len(data) - 1}/{len(data)}",
    ]
    assert google.by_name("big.zip")[0]["content"] == data


def test_a_cut_chunk_resumes_from_what_google_already_received() -> None:
    """El chunk llegó pero la respuesta se perdió: se consulta el estado y se retoma."""
    sleeps: list[float] = []
    drive, google, _ = make_drive(sleeps=sleeps)
    connect(drive, google)
    data = b"z" * (CHUNK_SIZE * 2 + 5)

    def store_then_lose(request: httpx.Request) -> None:
        google._session_put(request)  # Google lo recibió...

    google.fail(
        503,
        when=lambda r: (
            r.url.host == "upload.test" and r.headers["Content-Range"].startswith("bytes 0-")
        ),
        effect=store_then_lose,
    )  # ...pero el cliente ve un 503

    upload(drive, "a/big.bin", data, "application/octet-stream")

    assert google.by_name("big.bin")[0]["content"] == data
    probes = [
        r for r in google.requests if r.headers.get("Content-Range", "").startswith("bytes */")
    ]
    assert len(probes) == 1 and len(sleeps) == 1


# ─────────────────────────── reintentos ───────────────────────────


def test_rate_limits_retry_with_retry_after_and_keep_the_headers() -> None:
    sleeps: list[float] = []
    drive, google, _ = make_drive(sleeps=sleeps)
    connect(drive, google)
    upload(drive, "a/warmup.pdf")  # crea la carpeta antes de inyectar fallos
    only_upload = lambda r: "/upload/" in str(r.url)  # noqa: E731
    google.fail(429, headers={"Retry-After": "7"}, when=only_upload)
    google.fail(503, when=only_upload)

    remote = upload(drive, "a/b.pdf", b"x")

    assert remote.id
    assert sleeps == [7.0, 2.0]  # Retry-After del servidor; luego backoff 2**intento
    posts = [r for r in google.requests if "/upload/" in str(r.url) and r.method == "POST"][-3:]
    assert all(r.headers["Content-Type"].startswith("multipart/related") for r in posts)


def test_drive_403_rate_limit_is_retried_but_other_403_is_not() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)
    upload(drive, "a/warmup.pdf")
    only_upload = lambda r: "/upload/" in str(r.url)  # noqa: E731
    google.fail(403, {"error": {"errors": [{"reason": "userRateLimitExceeded"}]}}, when=only_upload)
    assert upload(drive, "a/ok.pdf").id  # reintentó y pasó

    google.fail(403, {"error": {"errors": [{"reason": "storageQuotaExceeded"}]}}, when=only_upload)
    with pytest.raises(DriveError) as exc:
        upload(drive, "a/full.pdf")
    assert exc.value.status == 403 and "storageQuota" not in str(exc.value)


def test_gives_up_after_max_attempts_without_leaking_details() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)
    upload(drive, "a/warmup.pdf")
    for _ in range(4):
        google.fail(503, {"error": "detalle interno"}, when=lambda r: "/upload/" in str(r.url))
    with pytest.raises(DriveError) as exc:
        upload(drive, "a/b.pdf")
    assert "503" in str(exc.value) and "detalle" not in str(exc.value)


def test_client_errors_are_not_retried() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)
    upload(drive, "a/warmup.pdf")
    before = len(google.requests)
    google.fail(400, when=lambda r: "/upload/" in str(r.url))
    with pytest.raises(DriveError):
        upload(drive, "a/b.pdf")
    assert len([r for r in google.requests[before:] if "/upload/" in str(r.url)]) == 1


def test_401_refreshes_the_token_once_and_retries() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)
    google.fail(401, when=lambda r: r.url.path == "/drive/v3/files" and r.method == "GET")
    google.token.append((200, tokens(access="ACCESS-2", refresh=None)))

    assert upload(drive).id
    auth = [r.headers["Authorization"] for r in google.drive_requests()]
    assert auth[0] == "Bearer ACCESS-1" and auth[1] == "Bearer ACCESS-2"


def test_persistent_401_fails_instead_of_looping() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)
    google.fail(401)
    google.fail(401)
    google.token.append((200, tokens(access="ACCESS-2", refresh=None)))
    with pytest.raises(DriveError):
        upload(drive)


def test_network_errors_are_retried_then_reported() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("sin red")

    drive._http = httpx.AsyncClient(transport=httpx.MockTransport(flaky))
    with pytest.raises(DriveError, match="sin conexión"):
        upload(drive)
    assert calls["n"] == 4


# ─────────────────────────── borrar y enlazar ───────────────────────────


def test_delete_sends_to_trash_and_missing_files_are_fine() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)
    remote = upload(drive)
    run(drive.delete(USER, remote.id))
    assert google.files[remote.id]["trashed"] is True  # recuperable desde la papelera
    run(drive.delete(USER, "no-existe"))  # 404: no es un error


def test_folder_url_points_to_the_product_folder_without_creating_anything() -> None:
    drive, google, _ = make_drive()
    connect(drive, google)
    upload(drive, "pt-BR/x/2026-10-21_kit/principal/a.pdf")
    folder = google.folders("2026-10-21_kit")[0]
    assert run(drive.folder_url(USER, "pt-BR/x/2026-10-21_kit")) == (
        f"https://drive.google.com/drive/folders/{folder['id']}"
    )
    count = len(google.files)
    assert run(drive.folder_url(USER, "pt-BR/otro/2000-01-01_nada")) is None
    assert len(google.files) == count
