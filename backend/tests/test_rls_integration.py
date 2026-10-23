"""Test de acceso cruzado RLS entre dos usuarios (criterio de aceptación §13).

Corre contra Supabase local:
    npx supabase start
    cd backend && uv run pytest -m integration

Lee SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY y SUPABASE_ANON_KEY del entorno;
si faltan o Supabase no responde, el test se salta.
"""

import os
import secrets
from collections.abc import Iterator

import httpx
import pytest

pytestmark = pytest.mark.integration

URL = os.environ.get("SUPABASE_URL", "http://127.0.0.1:54321").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


def _headers(key: str, token: str | None = None) -> dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {token or key}"}


@pytest.fixture(scope="module")
def http() -> Iterator[httpx.Client]:
    if not SERVICE_KEY or not ANON_KEY:
        pytest.skip("faltan SUPABASE_SERVICE_ROLE_KEY / SUPABASE_ANON_KEY")
    with httpx.Client(base_url=URL, timeout=10) as client:
        try:
            client.get("/rest/v1/", headers=_headers(ANON_KEY))
        except httpx.HTTPError:
            pytest.skip("Supabase local no responde")
        yield client


def _admin(http: httpx.Client) -> dict[str, str]:
    return _headers(SERVICE_KEY)


def _create_user(http: httpx.Client, email: str, password: str) -> httpx.Response:
    return http.post(
        "/auth/v1/admin/users",
        headers=_admin(http),
        json={"email": email, "password": password, "email_confirm": True},
    )


@pytest.fixture(scope="module")
def users(http: httpx.Client) -> Iterator[dict[str, dict[str, str]]]:
    created: dict[str, dict[str, str]] = {}
    emails = []
    for name in ("a", "b"):
        email = f"rls-{name}-{secrets.token_hex(4)}@example.test"
        password = secrets.token_urlsafe(16)
        emails.append(email)
        http.post(
            "/rest/v1/app_allowed_emails", headers=_admin(http), json={"email": email}
        ).raise_for_status()
        response = _create_user(http, email, password)
        response.raise_for_status()
        login = http.post(
            "/auth/v1/token",
            params={"grant_type": "password"},
            headers={"apikey": ANON_KEY},
            json={"email": email, "password": password},
        )
        login.raise_for_status()
        created[name] = {"id": response.json()["id"], "token": login.json()["access_token"]}
    yield created
    for user in created.values():
        http.delete(f"/auth/v1/admin/users/{user['id']}", headers=_admin(http))
    for email in emails:
        http.delete(
            "/rest/v1/app_allowed_emails", headers=_admin(http), params={"email": f"eq.{email}"}
        )


@pytest.fixture(scope="module")
def product_of_a(http: httpx.Client, users: dict[str, dict[str, str]]) -> str:
    response = http.post(
        "/rest/v1/products",
        headers={**_admin(http), "Prefer": "return=representation"},
        json={
            "user_id": users["a"]["id"],
            "niche": "finanzas",
            "problem": {"title": "Salir del sobregiro en 60 días"},
            "market": "es-LATAM",
            "main_format": "pdf_guide",
            "template_id": "minimal-clean",
            "prompt_version": "test",
        },
    )
    response.raise_for_status()
    return response.json()[0]["id"]


def _select_product(http: httpx.Client, product_id: str, token: str | None) -> list:
    response = http.get(
        "/rest/v1/products",
        headers=_headers(ANON_KEY, token),
        params={"id": f"eq.{product_id}", "select": "id"},
    )
    response.raise_for_status()
    return response.json()


def test_owner_sees_own_product(http, users, product_of_a) -> None:
    assert len(_select_product(http, product_of_a, users["a"]["token"])) == 1


def test_other_user_cannot_see_product(http, users, product_of_a) -> None:
    assert _select_product(http, product_of_a, users["b"]["token"]) == []


def test_anon_cannot_see_product(http, product_of_a) -> None:
    assert _select_product(http, product_of_a, None) == []


def test_user_cannot_write_directly(http, users) -> None:
    response = http.post(
        "/rest/v1/products",
        headers=_headers(ANON_KEY, users["b"]["token"]),
        json={
            "user_id": users["b"]["id"],
            "niche": "x",
            "problem": {},
            "main_format": "pdf_guide",
            "template_id": "minimal-clean",
            "prompt_version": "test",
        },
    )
    assert response.status_code in (401, 403)


def test_user_cannot_read_allowlist_or_tokens(http, users) -> None:
    for table in ("app_allowed_emails", "storage_connections"):
        response = http.get(f"/rest/v1/{table}", headers=_headers(ANON_KEY, users["a"]["token"]))
        assert response.status_code == 200
        assert response.json() == []


def test_catalog_visible_to_authenticated(http, users) -> None:
    response = http.get(
        "/rest/v1/templates",
        headers=_headers(ANON_KEY, users["a"]["token"]),
        params={"select": "id"},
    )
    assert len(response.json()) >= 10


def test_email_not_in_allowlist_cannot_sign_up(http) -> None:
    response = _create_user(http, f"intruso-{secrets.token_hex(4)}@example.test", "x" * 16)
    assert response.status_code >= 400


# ───────────────────── Creativos para Meta Ads: tablas ad_* ─────────────────────

AD_TABLES = ("ad_batches", "ad_creatives", "ad_results", "ad_proofs")


@pytest.fixture(scope="module")
def ads_of_a(http: httpx.Client, users: dict[str, dict[str, str]]) -> Iterator[dict[str, str]]:
    """Un lote, un creativo, un resultado, una prueba y un trabajo del usuario A."""
    owner = users["a"]["id"]
    ids: dict[str, str] = {}

    def insert(table: str, row: dict) -> str:
        response = http.post(
            f"/rest/v1/{table}",
            headers={**_admin(http), "Prefer": "return=representation"},
            json=row,
        )
        response.raise_for_status()
        return response.json()[0].get("id", "")

    ids["ad_batches"] = insert(
        "ad_batches",
        {
            "user_id": owner,
            "niche": "productividad",
            "market": "es-LATAM",
            "template_id": "minimal-clean",
            "brief": {"product_name": "Bandeja Única"},
            "prompt_version": "test",
        },
    )
    ids["ad_creatives"] = insert(
        "ad_creatives",
        {
            "batch_id": ids["ad_batches"],
            "user_id": owner,
            "group_id": "00000000-0000-0000-0000-000000000001",
            "angle": "dolor",
            "avatar": "A",
            "template_id": "headline_bold",
            "ratio": "4x5",
            "copy": {},
            "filename": "rls_test_4x5_v1.png",
        },
    )
    ids["ad_results"] = insert(
        "ad_results",
        {"user_id": owner, "creative_id": ids["ad_creatives"], "day": "2026-01-01", "spend": 10},
    )
    ids["ad_proofs"] = insert(
        "ad_proofs", {"user_id": owner, "kind": "stat", "text": "dato real de prueba"}
    )
    ids["jobs"] = insert(
        "jobs", {"user_id": owner, "batch_id": ids["ad_batches"], "kind": "ad_plan", "payload": {}}
    )
    ids["cache"] = "rls-test-" + secrets.token_hex(4)
    insert(
        "ad_image_cache",
        {
            "scene_hash": ids["cache"],
            "provider": "test",
            "storage_path": f"{owner}/ads/_images/x.jpg",
        },
    )
    insert("ad_provider_usage", {"provider": "rls-test", "day": "2026-01-01", "requests": 1})
    yield ids
    http.delete(
        "/rest/v1/ad_image_cache", headers=_admin(http), params={"scene_hash": f"eq.{ids['cache']}"}
    )
    http.delete(
        "/rest/v1/ad_provider_usage", headers=_admin(http), params={"provider": "eq.rls-test"}
    )


def _rows(http: httpx.Client, table: str, token: str | None, **filters: str) -> list:
    response = http.get(
        f"/rest/v1/{table}", headers=_headers(ANON_KEY, token), params={"select": "*", **filters}
    )
    response.raise_for_status()
    return response.json()


@pytest.mark.parametrize("table", [*AD_TABLES, "jobs"])
def test_ad_rows_are_visible_to_their_owner_only(http, users, ads_of_a, table) -> None:
    mine = _rows(http, table, users["a"]["token"], id=f"eq.{ads_of_a[table]}")
    assert len(mine) == 1
    assert _rows(http, table, users["b"]["token"], id=f"eq.{ads_of_a[table]}") == []
    assert _rows(http, table, None, id=f"eq.{ads_of_a[table]}") == []


@pytest.mark.parametrize("table", ["ad_image_cache", "ad_provider_usage"])
def test_backend_only_ad_tables_are_invisible_to_every_user(http, users, ads_of_a, table) -> None:
    """La caché de imágenes y el consumo diario no tienen policies: solo la service role."""
    assert len(_rows(http, table, None)) == 0
    for name in ("a", "b"):
        assert _rows(http, table, users[name]["token"]) == []
    assert len(_rows(http, table, SERVICE_KEY)) >= 1  # la service role sí ve lo que insertó


@pytest.mark.parametrize("table", [*AD_TABLES, "ad_image_cache", "ad_provider_usage"])
def test_users_cannot_write_ad_tables_directly(http, users, ads_of_a, table) -> None:
    rows = {
        "ad_batches": {"user_id": users["b"]["id"], "niche": "x", "market": "es-LATAM", "template_id": "t", "brief": {}, "prompt_version": "t"},
        "ad_creatives": {"batch_id": ads_of_a["ad_batches"], "user_id": users["b"]["id"], "group_id": "00000000-0000-0000-0000-000000000002", "angle": "a", "avatar": "a", "template_id": "t", "ratio": "4x5", "copy": {}, "filename": "x.png"},
        "ad_results": {"user_id": users["b"]["id"], "creative_id": ads_of_a["ad_creatives"], "day": "2026-01-02"},
        "ad_proofs": {"user_id": users["b"]["id"], "kind": "stat", "text": "inventado"},
        "ad_image_cache": {"scene_hash": "x", "provider": "x", "storage_path": "x"},
        "ad_provider_usage": {"provider": "x", "day": "2026-01-02"},
    }  # fmt: skip
    response = http.post(
        f"/rest/v1/{table}", headers=_headers(ANON_KEY, users["b"]["token"]), json=rows[table]
    )
    assert response.status_code in (401, 403), table
    # Ni siquiera A (la dueña) puede modificar sus propias filas: escribe el backend.
    update = http.patch(
        f"/rest/v1/{table}",
        headers={**_headers(ANON_KEY, users["a"]["token"]), "Prefer": "return=representation"},
        params={"user_id": f"eq.{users['a']['id']}"}
        if table in AD_TABLES
        else {"provider": "eq.x"},
        json={"niche": "cambiado"} if table == "ad_batches" else {"text": "cambiado"},
    )
    assert update.status_code in (200, 204, 401, 403)
    if update.status_code == 200:
        assert update.json() == []  # RLS no deja tocar ninguna fila


def test_the_usage_counter_function_is_not_callable_by_users(http, users) -> None:
    response = http.post(
        "/rest/v1/rpc/ad_usage_add",
        headers=_headers(ANON_KEY, users["a"]["token"]),
        json={"p_provider": "x", "p_day": "2026-01-01", "p_requests": 1, "p_cost": 1},
    )
    assert response.status_code in (401, 403, 404)
