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
