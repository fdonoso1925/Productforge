import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app

SECRET = "test-secret-con-al-menos-treinta-y-dos-caracteres"
ALLOWED = "yo@example.com"


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, supabase_jwt_secret=SECRET, allowed_emails=[ALLOWED]
    )
    return TestClient(app)


def make_token(email: str = ALLOWED, *, secret: str = SECRET, **overrides: object) -> str:
    claims = {
        "sub": str(uuid.uuid4()),
        "email": email,
        "aud": "authenticated",
        "exp": int(time.time()) + 300,
        **overrides,
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def get_me(client: TestClient, token: str | None) -> int:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get("/me", headers=headers).status_code


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_me_ok(client: TestClient) -> None:
    token = make_token()
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == ALLOWED


def test_me_email_case_insensitive(client: TestClient) -> None:
    assert get_me(client, make_token("YO@Example.com")) == 200


def test_missing_token(client: TestClient) -> None:
    assert get_me(client, None) == 401


def test_wrong_signature(client: TestClient) -> None:
    assert get_me(client, make_token(secret="otro-secreto-de-mas-de-32-caracteres!!")) == 401


def test_expired(client: TestClient) -> None:
    assert get_me(client, make_token(exp=int(time.time()) - 10)) == 401


def test_wrong_audience(client: TestClient) -> None:
    assert get_me(client, make_token(aud="anon")) == 401


def test_alg_none_rejected(client: TestClient) -> None:
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "email": ALLOWED,
            "aud": "authenticated",
            "exp": int(time.time()) + 300,
        },
        None,
        algorithm="none",
    )
    assert get_me(client, token) == 401


def test_email_not_allowed(client: TestClient) -> None:
    assert get_me(client, make_token("intruso@example.com")) == 403


def test_settings_parse_csv() -> None:
    s = Settings(
        _env_file=None, allowed_emails="A@x.com, b@y.com", cors_origins="http://a,http://b"
    )
    assert s.allowed_emails == ["a@x.com", "b@y.com"]
    assert s.cors_origins == ["http://a", "http://b"]
