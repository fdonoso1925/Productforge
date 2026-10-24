"""Subida a Meta (siempre en pausa) y lectura de métricas: cliente HTTP, jobs y endpoints."""

import asyncio
import json
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
import pytest

from app.ads.meta import client as meta_client
from app.ads.meta.client import AdAccount, MetaClient, MetaError, minor_units
from app.ads.meta.jobs import purchase_value, result_row
from app.config import Settings
from app.worker import enqueue_meta_syncs
from tests.test_api_ads import SETTINGS, AdsWorld, plan_responses
from tests.test_auth import ALLOWED, SECRET
from tests.test_pipeline import USER

TOKEN = "EAAB" + "x" * 40  # falso
TINY_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16
BODY = {
    "link_url": "https://tienda.example.com/producto",
    "objective": "traffic",
    "daily_budget": 5,
    "countries": ["mx", "co"],
}


# ───────────────────────────── cliente HTTP ─────────────────────────────


def make_client(handler) -> MetaClient:
    return MetaClient(
        access_token=TOKEN,
        ad_account_id="123",
        page_id="999",
        pixel_id="555",
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def run(coro):
    return asyncio.run(coro)


def test_everything_the_client_creates_is_paused_and_the_token_is_only_in_the_header() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/adimages"):
            return httpx.Response(200, json={"images": {"a.png": {"hash": "H1"}}})
        if request.method == "GET":
            return httpx.Response(
                200, json={"name": "Cuenta", "currency": "USD", "account_status": 1}
            )
        return httpx.Response(200, json={"id": "777"})

    async def flow() -> None:
        c = make_client(handler)
        assert await c.upload_image("a.png", b"png") == "H1"
        campaign = await c.create_campaign("c", "traffic")
        adset = await c.create_adset(
            name="s", campaign_id=campaign, objective="traffic", daily_budget=5, countries=["MX"]
        )
        creative = await c.create_creative(
            name="n",
            image_hash="H1",
            link="https://x.example.com",
            message="m",
            headline="h",
            description="d",
            cta="LEARN_MORE",
        )
        await c.create_ad(name="n", adset_id=adset, creative_id=creative)

    run(flow())
    created = [r for r in seen if r.method == "POST" and not r.url.path.endswith("/adimages")]
    assert len(created) == 4
    statuses = {
        r.url.path.rsplit("/", 1)[-1]: parse_qs(r.content.decode()).get("status") for r in created
    }
    assert statuses["campaigns"] == ["PAUSED"]
    assert statuses["adsets"] == ["PAUSED"]
    assert statuses["ads"] == ["PAUSED"]
    for r in seen:
        assert TOKEN not in str(r.url)
        assert r.headers["authorization"] == f"Bearer {TOKEN}"
    assert not any(b"ACTIVE" in r.content for r in seen)


def test_the_budget_goes_in_the_smallest_currency_unit() -> None:
    assert minor_units(12.5, "USD") == 1250
    assert minor_units(5000, "CLP") == 5000
    assert minor_units(0.01, "MXN") == 1


def test_adset_budget_and_targeting_are_sent_as_meta_expects() -> None:
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"name": "C", "currency": "CLP", "account_status": 1})
        sent.update(parse_qs(request.content.decode()))
        return httpx.Response(200, json={"id": "1"})

    run(
        make_client(handler).create_adset(
            name="s", campaign_id="9", objective="sales", daily_budget=7000, countries=["CL"]
        )
    )
    assert sent["daily_budget"] == ["7000"]
    targeting = json.loads(sent["targeting"][0])
    assert targeting["geo_locations"] == {"countries": ["CL"]}
    assert targeting["targeting_automation"] == {"advantage_audience": 0}
    assert json.loads(sent["promoted_object"][0]) == {
        "pixel_id": "555",
        "custom_event_type": "PURCHASE",
    }


def test_sales_objective_without_a_pixel_is_refused() -> None:
    c = MetaClient(access_token=TOKEN, ad_account_id="1", page_id="2")

    async def go() -> None:
        c._currency = "USD"
        await c.create_adset(
            name="s", campaign_id="9", objective="sales", daily_budget=5, countries=["MX"]
        )

    with pytest.raises(MetaError, match="META_PIXEL_ID"):
        run(go())


def test_meta_errors_become_a_short_message_without_secrets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": {"message": "Invalid parameter", "code": 100, "error_subcode": 33}}
        )

    with pytest.raises(MetaError) as info:
        run(make_client(handler).create_campaign("c", "traffic"))
    assert info.value.code == 100 and info.value.subcode == 33
    assert TOKEN not in str(info.value)


def test_rate_limits_are_retried_and_other_errors_are_not(monkeypatch) -> None:
    async def no_sleep(_):  # no esperar de verdad
        return None

    monkeypatch.setattr(meta_client.asyncio, "sleep", no_sleep)
    calls = {"n": 0}

    def limited(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(400, json={"error": {"message": "limit", "code": 17}})
        return httpx.Response(200, json={"id": "5"})

    assert run(make_client(limited).create_campaign("c", "traffic")) == "5"
    assert calls["n"] == 3

    calls["n"] = 0

    def invalid(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"message": "no", "code": 100}})

    with pytest.raises(MetaError):
        run(make_client(invalid).create_campaign("c", "traffic"))
    assert calls["n"] == 1


def test_insights_follow_the_pagination() -> None:
    pages = {
        None: {"data": [{"ad_id": "1"}], "paging": {"cursors": {"after": "A"}, "next": "x"}},
        "A": {"data": [{"ad_id": "2"}], "paging": {"cursors": {"after": "B"}}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[request.url.params.get("after")])

    rows = run(make_client(handler).insights(["1", "2"], "2026-01-01", "2026-01-31"))
    assert [r["ad_id"] for r in rows] == ["1", "2"]


def test_unconfigured_client_never_calls_meta() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no debe llamar a Meta")

    c = MetaClient(
        access_token="",
        ad_account_id="",
        page_id="",
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert not c.configured()
    with pytest.raises(MetaError):
        run(c.create_campaign("c", "traffic"))


# ───────────────────────────── métricas ─────────────────────────────


def test_purchases_prefer_the_omnichannel_action() -> None:
    rows = [
        {"action_type": "purchase", "value": "2"},
        {"action_type": "omni_purchase", "value": "3"},
    ]
    assert purchase_value(rows) == 3
    assert purchase_value([{"action_type": "purchase", "value": "2"}]) == 2
    assert purchase_value(None) == 0
    assert purchase_value([{"action_type": "omni_purchase", "value": "x"}]) == 0


def test_an_insight_row_becomes_an_ads_result() -> None:
    row = result_row(
        {"id": "c1"},
        "u1",
        {
            "date_start": "2026-10-20",
            "spend": "12.345",
            "impressions": "1500",
            "inline_link_clicks": "30",
            "actions": [{"action_type": "omni_purchase", "value": "2"}],
            "action_values": [{"action_type": "omni_purchase", "value": "58.0"}],
        },
    )
    assert row == {
        "user_id": "u1",
        "creative_id": "c1",
        "day": "2026-10-20",
        "spend": 12.35,
        "impressions": 1500,
        "clicks": 30,
        "purchases": 2,
        "revenue": 58.0,
        "source": "meta",
    }


# ───────────────────────────── jobs y endpoints ─────────────────────────────


class FakeMeta:
    """Doble en memoria de MetaClient: registra lo que se crea."""

    def __init__(self, *, configured=True, fail_ads=0) -> None:
        self._configured = configured
        self.fail_ads = fail_ads
        self.created: list[tuple[str, dict]] = []
        self.n = 0
        self.insight_rows: list[dict] = []
        self.ad_status = "PAUSED"

    def configured(self) -> bool:
        return self._configured

    def _id(self, kind: str, **info) -> str:
        self.n += 1
        self.created.append((kind, info))
        return f"{kind}-{self.n}"

    async def currency(self) -> str:
        return "USD"

    async def account_info(self) -> AdAccount:
        return AdAccount(id="act_1", name="Mi cuenta", currency="USD", status=1)

    async def upload_image(self, filename, data) -> str:
        assert data[:4] == b"\x89PNG"
        return self._id("hash", filename=filename)

    async def create_campaign(self, name, objective) -> str:
        return self._id("campaign", name=name, objective=objective)

    async def create_adset(self, **info) -> str:
        return self._id("adset", **info)

    async def create_creative(self, **info) -> str:
        return self._id("creative", **info)

    async def create_ad(self, **info) -> str:
        if self.fail_ads:
            self.fail_ads -= 1
            raise MetaError("anuncio rechazado", code=100)
        return self._id("ad", **info)

    async def insights(self, ad_ids, since, until) -> list[dict]:
        return [r for r in self.insight_rows if r["ad_id"] in ad_ids]

    async def ad_statuses(self, ad_ids) -> dict[str, str]:
        return {a: self.ad_status for a in ad_ids}

    def kinds(self, kind: str) -> list[dict]:
        return [info for k, info in self.created if k == kind]


def meta_world(meta: FakeMeta | None = None, **kw) -> tuple[AdsWorld, str, FakeMeta]:
    meta = meta or FakeMeta(**kw)
    w = AdsWorld(plan_responses(), meta=meta)
    w.services.settings = Settings(
        _env_file=None,
        supabase_jwt_secret=SECRET,
        allowed_emails=[ALLOWED],
        meta_access_token=TOKEN,
        meta_ad_account_id="1",
        meta_page_id="2",
        meta_pixel_id="3",
    )
    response = w.client.post("/ads/batches", json=w.batch_body())
    w.run_worker()
    batch_id = response.json()["batch_id"]
    # Sin componer de verdad (WeasyPrint/pdfium son lentos y esto no los necesita): cada creativo
    # queda «compuesto» con un PNG mínimo en Storage.
    for c in w.creatives.rows.values():
        path = f"{USER}/ads/{batch_id}/{c['filename']}"
        w.storage.objects[path] = TINY_PNG
        c.update(status="rendered", storage_path=path)
    return w, batch_id, meta


def publish(w: AdsWorld, batch_id: str, **over):
    return w.client.post(f"/ads/batches/{batch_id}/meta", json={**BODY, **over})


def test_publishing_creates_campaign_adset_and_one_paused_ad_per_creative() -> None:
    w, batch_id, meta = meta_world()
    response = publish(w, batch_id)
    assert response.status_code == 202, response.text
    w.run_worker()

    state = w.client.get(f"/ads/batches/{batch_id}/meta").json()
    creatives = list(w.creatives.rows.values())
    assert state["status"] == "done"
    assert state["uploaded"] == state["total"] == len(creatives) == 4
    assert state["failed"] == 0 and state["active_ads"] == 0
    assert len(meta.kinds("campaign")) == 1 and len(meta.kinds("adset")) == 1
    assert meta.kinds("adset")[0]["countries"] == ["CO", "MX"]
    assert len(meta.kinds("ad")) == 4
    for c in creatives:
        assert c["meta"]["ad_id"].startswith("ad-")
    # El anuncio se llama como el archivo: así lo empareja también la importación CSV.
    names = {i["name"] for i in meta.kinds("creative")}
    assert names == {c["filename"].removesuffix(".png") for c in creatives}
    # Y no se llamó a la IA para subir.
    assert len(w.llm.calls) == 2


def test_a_failed_ad_leaves_the_batch_partial_and_retrying_only_completes_the_rest() -> None:
    meta = FakeMeta(fail_ads=1)
    w, batch_id, meta = meta_world(meta)
    publish(w, batch_id)
    w.run_worker()
    state = w.client.get(f"/ads/batches/{batch_id}/meta").json()
    assert state["status"] == "partial" and state["uploaded"] == 3 and state["failed"] == 1
    assert "rechazado" in state["error"]

    publish(w, batch_id)
    w.run_worker()
    state = w.client.get(f"/ads/batches/{batch_id}/meta").json()
    assert state["status"] == "done" and state["uploaded"] == 4
    assert len(meta.kinds("campaign")) == 1 and len(meta.kinds("adset")) == 1  # nada se duplica
    assert len(meta.kinds("ad")) == 4 and len(meta.kinds("hash")) == 4


def test_red_policy_creatives_are_never_uploaded() -> None:
    w, batch_id, meta = meta_world()
    first = next(iter(w.creatives.rows.values()))
    first["policy_status"] = "red"
    publish(w, batch_id)
    w.run_worker()
    state = w.client.get(f"/ads/batches/{batch_id}/meta").json()
    assert state["skipped"] == 1 and state["uploaded"] == 3
    assert "ad_id" not in (first.get("meta") or {})


def test_publish_validates_the_link_budget_countries_and_objective() -> None:
    w, batch_id, _ = meta_world()
    for over in (
        {"link_url": "http://tienda.example.com/x"},
        {"link_url": "https://user:pw@tienda.example.com/x"},
        {"link_url": "https://localhost/x"},
        {"daily_budget": 0},
        {"daily_budget": 100000},
        {"countries": []},
        {"countries": ["MEX"]},
        {"objective": "reach"},
    ):
        assert publish(w, batch_id, **over).status_code == 422, over


def test_sales_objective_needs_a_pixel() -> None:
    w, batch_id, _ = meta_world()
    w.services.settings = Settings(
        _env_file=None,
        supabase_jwt_secret=SECRET,
        allowed_emails=[ALLOWED],
        meta_access_token=TOKEN,
        meta_ad_account_id="1",
        meta_page_id="2",
    )
    assert publish(w, batch_id, objective="sales").status_code == 422


def test_publishing_requires_meta_composed_images_and_ownership() -> None:
    w, batch_id, _ = meta_world(configured=False)
    assert publish(w, batch_id).status_code == 503

    w2 = AdsWorld(plan_responses(), meta=FakeMeta())
    created = w2.client.post("/ads/batches", json=w2.batch_body())
    w2.run_worker()
    assert publish(w2, created.json()["batch_id"]).status_code == 409  # aún sin imágenes

    w3, batch3, _ = meta_world()
    other = {"Authorization": w3.as_user("00000000-0000-0000-0000-000000000099")["Authorization"]}
    assert (
        w3.client.post(f"/ads/batches/{batch3}/meta", json=BODY, headers=other).status_code == 404
    )
    assert w3.client.get(f"/ads/batches/{batch3}/meta", headers=other).status_code == 404


def test_one_meta_operation_at_a_time_and_no_silent_changes_to_an_existing_campaign() -> None:
    w, batch_id, _ = meta_world()
    assert publish(w, batch_id).status_code == 202
    assert publish(w, batch_id).status_code == 409  # ya hay una en curso
    assert w.client.post(f"/ads/batches/{batch_id}/meta/sync").status_code == 409
    w.run_worker()
    assert publish(w, batch_id, daily_budget=50).status_code == 409  # otra configuración
    assert publish(w, batch_id, countries=["co", "mx"]).status_code == 202  # la misma: completa


def test_sync_needs_a_published_batch() -> None:
    w, batch_id, _ = meta_world()
    assert w.client.post(f"/ads/batches/{batch_id}/meta/sync").status_code == 409


def test_sync_stores_daily_results_and_warns_when_someone_activates_an_ad() -> None:
    w, batch_id, meta = meta_world()
    publish(w, batch_id)
    w.run_worker()
    creative = next(iter(w.creatives.rows.values()))
    meta.insight_rows = [
        {
            "ad_id": creative["meta"]["ad_id"],
            "date_start": "2026-10-20",
            "spend": "10.00",
            "impressions": "2000",
            "inline_link_clicks": "40",
            "actions": [{"action_type": "omni_purchase", "value": "1"}],
            "action_values": [{"action_type": "omni_purchase", "value": "19"}],
        },
        {"ad_id": "ajeno", "date_start": "2026-10-20", "spend": "99"},
    ]
    meta.ad_status = "ACTIVE"
    assert w.client.post(f"/ads/batches/{batch_id}/meta/sync").status_code == 202
    w.run_worker()

    [result] = list(w.results.rows.values())
    assert result["creative_id"] == creative["id"] and result["source"] == "meta"
    assert (result["spend"], result["impressions"], result["clicks"]) == (10.0, 2000, 40)
    assert (result["purchases"], result["revenue"]) == (1, 19.0)
    state = w.client.get(f"/ads/batches/{batch_id}/meta").json()
    assert state["active_ads"] == 4 and state["synced_at"]
    assert state["status"] == "done"  # leer métricas no cambia el estado de la subida


def test_a_crashed_publish_does_not_stay_publishing_forever() -> None:
    class Broken(FakeMeta):
        async def upload_image(self, filename, data):
            raise RuntimeError("boom")

    w, batch_id, _ = meta_world(Broken())
    publish(w, batch_id)
    w.run_worker()
    # el worker real marca el job como error; el lote no queda «publicando»
    state = w.client.get(f"/ads/batches/{batch_id}/meta").json()
    assert state["status"] != "publishing"


def test_status_endpoint_reports_what_is_missing_without_exposing_secrets() -> None:
    w, _, _ = meta_world()
    w.services.settings = SETTINGS
    body = w.client.get("/ads/meta/status").json()
    assert body["configured"] is False
    assert body["missing"] == ["META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID", "META_PAGE_ID"]

    w.services.settings = Settings(
        _env_file=None,
        supabase_jwt_secret=SECRET,
        allowed_emails=[ALLOWED],
        meta_access_token=TOKEN,
        meta_ad_account_id="1",
        meta_page_id="2",
        meta_pixel_id="3",
    )
    ok = w.client.get("/ads/meta/status")
    assert ok.json()["configured"] is True and ok.json()["account_name"] == "Mi cuenta"
    assert ok.json()["sales_available"] is True
    assert TOKEN not in ok.text


def test_the_worker_queues_a_sync_for_published_batches_only_once() -> None:
    w, batch_id, _ = meta_world()
    services = SimpleNamespace(meta=w.services.meta, ad_batches=w.batches, jobs=w.jobs)
    assert asyncio.run(enqueue_meta_syncs(services)) == 0  # aún sin publicar
    publish(w, batch_id)
    w.run_worker()
    assert asyncio.run(enqueue_meta_syncs(services)) == 1
    assert asyncio.run(enqueue_meta_syncs(services)) == 0  # ya hay uno en cola
    assert USER  # el lote es del usuario de las pruebas


def test_meta_variables_are_documented_and_only_the_backend_knows_them() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    example = (root / ".env.example").read_text(encoding="utf-8")
    for name in ("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID", "META_PAGE_ID", "META_PIXEL_ID"):
        assert name in example
    for path in (root / "frontend").rglob("*.ts*"):
        if "node_modules" in path.parts or ".next" in path.parts:
            continue
        assert "META_ACCESS_TOKEN" not in path.read_text(encoding="utf-8", errors="ignore"), path
