import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.deps import get_services
from app.main import create_app
from app.security import (
    RateLimiter,
    RedactQueryFilter,
    ensure_production_ready,
    production_problems,
)
from tests.fakes import make_outline, make_request
from tests.memory import MemoryJobs, MemoryProducts
from tests.test_auth import ALLOWED, SECRET, make_token


def prod_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "supabase_url": "https://abc.supabase.co",
        "supabase_service_role_key": "sb_secret_x",
        "anthropic_api_key": "sk-ant-x",
        "allowed_emails": ["yo@example.com"],
        "cors_origins": ["https://app.example.com"],
        "frontend_url": "https://app.example.com",
        **overrides,
    }
    return Settings(_env_file=None, **values)


class TestRateLimiter:
    def test_allows_up_to_the_limit_then_reports_wait(self) -> None:
        rl = RateLimiter()
        limits = [(3, 60.0)]
        assert [rl.check("u", limits, now=t) for t in (0, 1, 2)] == [0, 0, 0]
        assert rl.check("u", limits, now=3) == 57  # el primero sale de la ventana en t=60

    def test_window_slides(self) -> None:
        rl = RateLimiter()
        limits = [(2, 10.0)]
        rl.check("u", limits, now=0)
        rl.check("u", limits, now=1)
        assert rl.check("u", limits, now=5) > 0
        assert rl.check("u", limits, now=10.5) == 0  # ya salió el de t=0

    def test_rejected_attempts_do_not_extend_the_block(self) -> None:
        rl = RateLimiter()
        limits = [(1, 10.0)]
        rl.check("u", limits, now=0)
        for t in (1, 2, 3, 4):
            assert rl.check("u", limits, now=t) > 0
        assert rl.check("u", limits, now=10.1) == 0

    def test_keys_are_independent(self) -> None:
        rl = RateLimiter()
        assert rl.check("a", [(1, 60.0)], now=0) == 0
        assert rl.check("b", [(1, 60.0)], now=0) == 0

    def test_the_stricter_of_two_windows_wins(self) -> None:
        rl = RateLimiter()
        limits = [(5, 60.0), (2, 3600.0)]
        rl.check("u", limits, now=0)
        rl.check("u", limits, now=1)
        assert rl.check("u", limits, now=2) > 60  # frena la ventana de la hora


@pytest.fixture
def ctx(monkeypatch):
    settings = Settings(
        _env_file=None,
        supabase_jwt_secret=SECRET,
        allowed_emails=[ALLOWED],
        rate_limit_per_minute=2,
        max_body_bytes=2000,
    )
    user = str(uuid4())
    services = SimpleNamespace(products=MemoryProducts(), jobs=MemoryJobs())
    request = make_request()
    product = services.products.add(
        user_id=user,
        niche=request.niche,
        problem=request.problem.model_dump(),
        market="pt-BR",
        main_format="pdf_guide",
        template_id="minimal-clean",
        outline=None,
    )
    monkeypatch.setattr("app.main.get_settings", lambda: settings)  # middlewares: se leen al crear
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_services] = lambda: services
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {make_token(sub=user)}"
    return client, product


def test_ai_endpoints_return_429_with_retry_after(ctx) -> None:
    client, product = ctx
    url = f"/products/{product['id']}/generate"
    # Sin outline responde 409, pero igual cuenta como intento.
    assert [client.post(url).status_code for _ in range(2)] == [409, 409]
    blocked = client.post(url)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1


def test_rate_limit_is_per_user(ctx) -> None:
    client, product = ctx
    url = f"/products/{product['id']}/generate"
    for _ in range(3):
        client.post(url)
    client.headers["Authorization"] = f"Bearer {make_token(sub=str(uuid4()))}"
    assert client.post(url).status_code != 429


def test_non_ai_endpoints_are_not_limited(ctx) -> None:
    client, _ = ctx
    assert all(client.get("/me").status_code == 200 for _ in range(10))


def test_security_headers_on_every_response(ctx) -> None:
    client, _ = ctx
    for response in (client.get("/health"), client.get("/me"), client.get("/nope")):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert "max-age=" in response.headers["strict-transport-security"]


def test_oversized_body_is_rejected_before_parsing(ctx) -> None:
    client, product = ctx
    big = client.put(f"/products/{product['id']}/outline", content=b"x" * 5000)
    assert big.status_code == 413
    assert big.headers["x-content-type-options"] == "nosniff"


def test_docs_are_open_in_development_and_closed_in_production(monkeypatch) -> None:
    assert TestClient(create_app()).get("/openapi.json").status_code == 200
    monkeypatch.setattr("app.main.get_settings", lambda: prod_settings())
    closed = TestClient(create_app())
    assert closed.get("/openapi.json").status_code == 404
    assert closed.get("/docs").status_code == 404
    assert closed.get("/health").status_code == 200


class TestProductionConfig:
    def test_valid_config_has_no_problems(self) -> None:
        assert production_problems(prod_settings()) == []
        ensure_production_ready(prod_settings())

    def test_development_never_blocks(self) -> None:
        ensure_production_ready(Settings(_env_file=None))

    @pytest.mark.parametrize(
        ("override", "fragment"),
        [
            ({"supabase_url": "http://127.0.0.1:54321"}, "SUPABASE_URL"),
            ({"supabase_service_role_key": ""}, "SERVICE_ROLE"),
            ({"anthropic_api_key": ""}, "ANTHROPIC_API_KEY"),
            ({"allowed_emails": []}, "ALLOWED_EMAILS"),
            ({"cors_origins": ["http://localhost:3000"]}, "CORS_ORIGINS"),
            ({"cors_origins": ["*"]}, "CORS_ORIGINS"),
            ({"frontend_url": "http://localhost:3000"}, "FRONTEND_URL"),
            ({"token_encryption_key": "no-es-fernet"}, "TOKEN_ENCRYPTION_KEY"),
            ({"google_client_id": "id"}, "van juntos"),
            ({"google_client_id": "id", "google_client_secret": "s"}, "GOOGLE_REDIRECT_URI"),
        ],
    )
    def test_each_problem_is_reported(self, override: dict, fragment: str) -> None:
        with pytest.raises(RuntimeError, match=fragment):
            ensure_production_ready(prod_settings(**override))

    def test_google_needs_an_encryption_key_and_public_redirect(self) -> None:
        google = {
            "google_client_id": "id",
            "google_client_secret": "s",
            "google_redirect_uri": "https://api.example.com/storage/drive/callback",
        }
        assert any(
            "TOKEN_ENCRYPTION_KEY" in p for p in production_problems(prod_settings(**google))
        )
        key = Fernet.generate_key().decode()
        assert production_problems(prod_settings(token_encryption_key=key, **google)) == []

    def test_startup_fails_fast_in_production(self, monkeypatch) -> None:
        monkeypatch.setattr("app.main.get_settings", lambda: prod_settings(anthropic_api_key=""))
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"), TestClient(create_app()):
            pass


def test_access_log_drops_the_query_string() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "GET", "/storage/drive/callback?code=SECRETO&state=OTRO", "1.1", 303),
        None,
    )
    assert RedactQueryFilter().filter(record)
    assert "SECRETO" not in record.getMessage()
    assert "/storage/drive/callback" in record.getMessage()


def test_outline_helpers_still_available() -> None:
    # Guardia: el fixture usa las mismas fábricas que el resto de la suite.
    assert make_outline().main is not None
