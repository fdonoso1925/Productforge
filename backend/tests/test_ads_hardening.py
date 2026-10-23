"""Creativos, fase 7: endurecimiento (límites, claves, descargas de terceros y logs)."""

import asyncio
import logging
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.ads.images.base import ImageRequest, ProviderRejected
from app.ads.images.gemini import MAX_INLINE_B64, GeminiImageProvider
from app.ads.images.pixabay import PixabayProvider, trusted_image_url
from app.ads.schemas import AvatarProposals
from app.config import Settings, get_settings
from app.security import RedactingFormatter, configure_logging, limiter, redact_secrets
from tests.test_ads_images import HIT, jpeg
from tests.test_ads_strategy import avatar
from tests.test_api_ads import SETTINGS, AdsWorld, plan_responses

ROOT = Path(__file__).resolve().parents[2]


# ───────────────────────────── claves fuera de los logs ─────────────────────────────

PIXABAY_KEY = "00000000-fake0fake0fake0fake0fake0fake"
GOOGLE_KEY = "AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKE0000"
ANTHROPIC_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        (f"GET https://pixabay.com/api/?key={PIXABAY_KEY}&q=desk 200", PIXABAY_KEY),
        (f"GET https://pixabay.com/api/?q=desk&key={PIXABAY_KEY}", PIXABAY_KEY),
        (f"headers {{'x-goog-api-key': '{GOOGLE_KEY}'}}", GOOGLE_KEY),
        (f"x-goog-api-key: {GOOGLE_KEY}", GOOGLE_KEY),
        (f"Authorization: Bearer {JWT}", JWT),
        (f"fallo con {ANTHROPIC_KEY} en el cliente", ANTHROPIC_KEY),
        (f"clave suelta {GOOGLE_KEY} en un mensaje", GOOGLE_KEY),
        (
            "token AQ.FakeFakeFakeFakeFakeFakeFakeFakeFake0000",
            "FakeFakeFakeFakeFakeFakeFakeFakeFake0000",
        ),
    ],
)
def test_secrets_are_masked_in_any_log_message(text: str, secret: str) -> None:
    out = redact_secrets(text)
    assert secret not in out and "***" in out


def test_harmless_text_is_left_alone() -> None:
    text = "llamada claude-sonnet-5-5: 5.8s, entrada=4458, salida=650 (Pixabay 500)"
    assert redact_secrets(text) == text


def test_the_app_log_formatter_also_masks_secrets_inside_tracebacks() -> None:
    try:
        raise httpx.ConnectError(f"no se pudo abrir https://pixabay.com/api/?key={PIXABAY_KEY}&q=x")
    except httpx.ConnectError:
        import sys

        record = logging.LogRecord(
            "productforge.ads.images", logging.ERROR, __file__, 1,
            "proveedor falló %s", (f"key={PIXABAY_KEY}",), sys.exc_info(),
        )  # fmt: skip
    rendered = RedactingFormatter("%(levelname)s %(message)s").format(record)
    assert (
        PIXABAY_KEY not in rendered and "ConnectError" in rendered
    )  # el error se conserva, la clave no


def test_configure_logging_installs_the_masking_formatter() -> None:
    logger = logging.getLogger("productforge")
    saved = (list(logger.handlers), logger.level, logger.propagate)
    logger.handlers.clear()
    try:
        configure_logging()
        assert any(isinstance(h.formatter, RedactingFormatter) for h in logger.handlers)
    finally:
        logger.handlers[:] = saved[0]
        logger.setLevel(saved[1])
        logger.propagate = saved[2]


# ───────────────────────────── descargas de terceros ─────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://pixabay.com/get/desk-77.jpg",
        "https://cdn.pixabay.com/photo/2018/01/01/desk.jpg",
        "https://PIXABAY.com/get/x.jpg",
    ],
)
def test_only_https_pixabay_hosts_are_trusted(url: str) -> None:
    assert trusted_image_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://pixabay.com/get/x.jpg",  # sin https
        "https://pixabay.com.evil.example/x.jpg",  # el nombre solo empieza igual
        "https://evil.example/pixabay.com/x.jpg",
        "https://evilpixabay.com/x.jpg",
        "https://user:pw@pixabay.com/x.jpg",  # credenciales embebidas
        "https://pixabay.com:8443/x.jpg",  # puerto raro
        "https://127.0.0.1/x.jpg",
        "https://169.254.169.254/latest/meta-data/",  # metadatos de la nube
        "file:///etc/passwd",
        "javascript:alert(1)",
        "//pixabay.com/x.jpg",
        "",
        None,
        42,
    ],
)
def test_other_hosts_schemes_and_ports_are_never_downloaded(url) -> None:
    assert not trusted_image_url(url)


def test_a_search_hit_pointing_somewhere_else_is_ignored_and_never_requested() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/":
            hits = [
                {**HIT, "id": 1, "largeImageURL": "http://169.254.169.254/latest/meta-data/"},
                {**HIT, "id": 2, "largeImageURL": "https://evil.example/x.jpg"},
                {**HIT, "id": 3, "largeImageURL": "https://pixabay.com/get/ok.jpg"},
            ]
            return httpx.Response(200, json={"hits": hits})
        return httpx.Response(200, content=jpeg(), headers={"content-type": "image/jpeg"})

    provider = PixabayProvider("k", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    image = asyncio.run(provider.fetch(ImageRequest("x", ("desk",), "4:5")))
    assert image.credit["id"] == 3
    assert {r.url.host for r in seen} == {"pixabay.com"}  # nunca se tocó otro host


def test_if_no_hit_is_trusted_nothing_is_downloaded() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        hits = [{**HIT, "largeImageURL": "https://evil.example/x.jpg"}]
        return httpx.Response(200, json={"hits": hits})

    provider = PixabayProvider("k", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderRejected):
        asyncio.run(provider.fetch(ImageRequest("x", ("desk",), "4:5")))
    assert seen == ["pixabay.com"]


def test_an_absurdly_large_gemini_image_is_refused() -> None:
    big = {
        "candidates": [
            {"content": {"parts": [{"inlineData": {"data": "A" * (MAX_INLINE_B64 + 1)}}]}}
        ]
    }
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=big))
    )
    provider = GeminiImageProvider("k", "m", 0.03, 1.0, client)
    with pytest.raises(ProviderRejected):
        asyncio.run(provider.fetch(ImageRequest("x", (), "4:5")))


# ───────────────────────────── límites de uso ─────────────────────────────

LOW = Settings(
    _env_file=None,
    supabase_jwt_secret=SETTINGS.supabase_jwt_secret,
    allowed_emails=SETTINGS.allowed_emails,
    rate_limit_per_minute=1,
    rate_limit_per_hour=50,
)


def limited_world(extra=()):
    w = AdsWorld([*plan_responses(), *extra])
    batch_id = w.client.post("/ads/batches", json=w.batch_body()).json()["batch_id"]
    w.run_worker()
    creatives = w.client.get(f"/ads/batches/{batch_id}").json()["creatives"]
    limiter.reset()
    w.client.app.dependency_overrides[get_settings] = lambda: LOW
    return w, batch_id, creatives


def heavy_calls(w, batch_id, creatives):
    cid = creatives[0]["id"]
    return {
        "editar": lambda: w.client.put(f"/ads/creatives/{cid}", json={}),
        "componer uno": lambda: w.client.post(f"/ads/creatives/{cid}/render"),
        "componer lote": lambda: w.client.post(f"/ads/batches/{batch_id}/render", json={}),
        "exportar": lambda: w.client.post(f"/ads/batches/{batch_id}/export"),
        "drive": lambda: w.client.post(f"/ads/batches/{batch_id}/drive"),
        "importar": lambda: w.client.post("/ads/results/import", content=b"Ad name,Impressions\n"),
        "resultado": lambda: w.client.put(f"/ads/creatives/{cid}/results", json={}),
        "variante": lambda: w.client.post(f"/ads/creatives/{cid}/variant", json={"ratio": "9x16"}),
        "prueba": lambda: w.client.post("/ads/proofs", json={"kind": "stat", "text": "dato real"}),
    }


def test_every_heavy_endpoint_is_rate_limited_with_retry_after() -> None:
    w, batch_id, creatives = limited_world()
    for name, call in heavy_calls(w, batch_id, creatives).items():
        limiter.reset()
        first = call()
        assert first.status_code != 429, name
        second = call()
        assert second.status_code == 429, name
        assert int(second.headers["retry-after"]) >= 1, name


def test_the_work_limit_does_not_use_up_the_ai_budget_nor_other_users() -> None:
    w, batch_id, creatives = limited_world([AvatarProposals(avatars=[avatar("A"), avatar("B")])])
    calls = heavy_calls(w, batch_id, creatives)
    calls["exportar"]()
    assert calls["exportar"]().status_code == 429  # el cupo de componer/exportar se agotó
    ai = w.client.post("/ads/avatars", json={"product_id": w.product["id"]})
    assert ai.status_code == 200, ai.text  # …pero la IA tiene su propio cupo
    again = w.client.post("/ads/avatars", json={"product_id": w.product["id"]})
    assert again.status_code == 429  # y también está limitada
    stranger = w.as_user(str(uuid4()))
    assert w.client.get("/ads/templates", headers=stranger).status_code == 200
    other = w.client.post(f"/ads/batches/{batch_id}/export", headers=stranger)
    assert other.status_code == 404  # llegó al endpoint (no fue 429): su cupo es suyo


def test_reads_are_not_rate_limited() -> None:
    w, batch_id, _ = limited_world()
    for _ in range(5):
        assert w.client.get(f"/ads/batches/{batch_id}").status_code == 200
        assert w.client.get("/ads/insights").status_code == 200


# ───────────────────────────── las claves no salen del backend ─────────────────────────────


def test_no_api_response_ever_contains_a_configured_key() -> None:
    keys = Settings(
        _env_file=None,
        supabase_jwt_secret=SETTINGS.supabase_jwt_secret,
        allowed_emails=SETTINGS.allowed_emails,
        gemini_api_key=GOOGLE_KEY,
        pixabay_api_key=PIXABAY_KEY,
        anthropic_api_key=ANTHROPIC_KEY,
        image_providers="gemini,pixabay",
        gemini_daily_usd_cap=1,
    )
    w, batch_id, creatives = limited_world()
    w.client.app.dependency_overrides[get_settings] = lambda: keys
    cid = creatives[0]["id"]
    for method, url, body in [
        ("get", "/ads/images/status", None),
        ("get", "/ads/templates", None),
        ("get", "/ads/batches", None),
        ("get", f"/ads/batches/{batch_id}", None),
        ("get", "/ads/insights", None),
        ("get", f"/ads/batches/{batch_id}/drive", None),
        ("post", "/ads/brief", {"product_id": w.product["id"]}),
        ("put", f"/ads/creatives/{cid}", {}),
        ("get", f"/ads/creatives/{cid}/url", None),
    ]:
        kwargs = {"json": body} if body is not None else {}
        response = getattr(w.client, method)(url, **kwargs)
        for secret in (GOOGLE_KEY, PIXABAY_KEY, ANTHROPIC_KEY):
            assert secret not in response.text, (url, secret[:6])


def test_the_frontend_never_mentions_image_provider_keys() -> None:
    """Las claves de Gemini y Pixabay viven solo en el backend: ni el código ni las variables
    públicas del frontend las nombran."""
    frontend = ROOT / "frontend"
    if not frontend.exists():
        pytest.skip("el frontend no está en este checkout")
    banned = (
        "GEMINI_API_KEY",
        "PIXABAY_API_KEY",
        "pixabay.com/api",
        "generativelanguage.googleapis",
    )
    skip = {"node_modules", ".next", "tsconfig.tsbuildinfo"}
    offenders = []
    for path in frontend.rglob("*"):
        if (
            not path.is_file()
            or skip & set(path.parts)
            or path.suffix not in {".ts", ".tsx", ".json", ".mjs", ".js", ".env", ".example"}
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        offenders += [f"{path.relative_to(ROOT)}: {word}" for word in banned if word in text]
    assert offenders == []
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    public = [line.split("=")[0] for line in env.splitlines() if line.startswith("NEXT_PUBLIC_")]
    assert public and not any(
        "GEMINI" in v or "PIXABAY" in v or "KEY" in v.replace("ANON_KEY", "") for v in public
    )


def test_env_example_documents_every_image_setting() -> None:
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    for variable in (
        "GEMINI_API_KEY", "PIXABAY_API_KEY", "IMAGE_PROVIDERS", "GEMINI_IMAGE_MODEL",
        "GEMINI_IMAGE_PRICE_USD", "GEMINI_DAILY_USD_CAP",
    ):  # fmt: skip
        assert f"{variable}=" in env, variable
    # Claves en blanco y Gemini apagado por defecto: copiar el ejemplo nunca gasta dinero.
    for secret in ("GEMINI_API_KEY", "PIXABAY_API_KEY"):
        assert f"\n{secret}=\n" in env
    assert "\nGEMINI_DAILY_USD_CAP=0\n" in env
