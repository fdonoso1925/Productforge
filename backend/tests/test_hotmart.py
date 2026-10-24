"""Hotmart: cliente de solo lectura, lectura de ventas y vínculo de productos."""

import asyncio
import base64
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.config import Settings
from app.hotmart import client as hm
from app.hotmart.client import HotmartClient, HotmartError
from app.hotmart.sync import sale_row
from app.security import RedactingFormatter, hotmart_problems
from tests.test_api_ads import AdsWorld
from tests.test_pipeline import USER

SECRET = "s3cr3t-hotmart-fake"


def make_client(handler, **kw) -> HotmartClient:
    return HotmartClient(
        client_id="cid",
        client_secret=SECRET,
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        **kw,
    )


def run(coro):
    return asyncio.run(coro)


def item(transaction="HP1", status="APPROVED", price=47.0, product=7, fee=4.0):
    return {
        "product": {"id": product, "name": "Guía de Notion"},
        "buyer": {"name": "Ana", "email": "ana@example.com"},
        "purchase": {
            "transaction": transaction,
            "order_date": 1_760_000_000_000,
            "approved_date": 1_760_000_100_000,
            "status": status,
            "price": {"value": price, "currency_code": "usd"},
            "hotmart_fee": {"total": fee},
            "payment": {"type": "CREDIT_CARD"},
            "tracking": {"source": "meta", "source_sck": "lote-1"},
            "commission_as": "PRODUCER",
            "is_subscription": False,
        },
    }


# ───────────────────────────── cliente ─────────────────────────────


def test_token_uses_basic_credentials_once_and_sales_are_read_only() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "api-sec-vlc.hotmart.com":
            return httpx.Response(200, json={"access_token": "TOK", "expires_in": 3600})
        return httpx.Response(200, json={"items": [item()], "page_info": {}})

    c = make_client(handler)

    async def go():
        until = datetime(2026, 10, 1, tzinfo=UTC)
        await c.sales_history(datetime(2026, 9, 25, tzinfo=UTC), until)
        await c.sales_history(datetime(2026, 9, 25, tzinfo=UTC), until)

    run(go())
    auth = [r for r in calls if r.url.host == "api-sec-vlc.hotmart.com"]
    assert len(auth) == 1  # el token se reutiliza
    expected = "Basic " + base64.b64encode(f"cid:{SECRET}".encode()).decode()
    assert auth[0].headers["authorization"] == expected
    assert all(r.method in ("GET", "POST") for r in calls)
    sales = [r for r in calls if r.url.host != "api-sec-vlc.hotmart.com"]
    assert all(r.method == "GET" and r.url.path.endswith("/sales/history") for r in sales)
    assert all(r.headers["authorization"] == "Bearer TOK" for r in sales)


def test_a_given_basic_value_is_used_as_is() -> None:
    c = HotmartClient(client_id="a", client_secret="b", basic="Basic ZmFrZTpmYWtl")
    assert c._basic_header() == "Basic ZmFrZTpmYWtl"
    assert HotmartClient(
        client_id="a", client_secret="b", basic="ZmFrZTpmYWtl"
    )._basic_header() == ("Basic ZmFrZTpmYWtl")


def test_history_is_read_in_30_day_windows_and_follows_page_tokens() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api-sec-vlc.hotmart.com":
            return httpx.Response(200, json={"access_token": "T", "expires_in": 3600})
        params = dict(request.url.params)
        seen.append(params)
        if params.get("page_token") == "P2":
            return httpx.Response(200, json={"items": [item("HP3")], "page_info": {}})
        if "page_token" not in params and len(seen) == 1:
            return httpx.Response(
                200,
                json={"items": [item("HP1"), item("HP2")], "page_info": {"next_page_token": "P2"}},
            )
        return httpx.Response(200, json={"items": [], "page_info": {}})

    items = run(
        make_client(handler).sales_history(
            datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 9, 14, tzinfo=UTC)
        )
    )
    assert [i["purchase"]["transaction"] for i in items] == ["HP1", "HP2", "HP3"]
    windows = {(p["start_date"], p["end_date"]) for p in seen}
    assert len(windows) == 3  # 75 días = 30 + 30 + 15
    assert all(int(p["end_date"]) - int(p["start_date"]) <= 30 * 86_400_000 for p in seen)


def test_an_expired_token_is_renewed_once() -> None:
    state = {"tokens": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api-sec-vlc.hotmart.com":
            state["tokens"] += 1
            return httpx.Response(
                200, json={"access_token": f"T{state['tokens']}", "expires_in": 3600}
            )
        if request.headers["authorization"] == "Bearer T1":
            return httpx.Response(401, json={})
        return httpx.Response(200, json={"items": [], "page_info": {}})

    run(
        make_client(handler).sales_history(
            datetime(2026, 9, 25, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)
        )
    )
    assert state["tokens"] == 2


def test_rejected_credentials_give_a_clear_error_without_the_secret(monkeypatch) -> None:
    async def no_sleep(_):
        return None

    monkeypatch.setattr(hm.asyncio, "sleep", no_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client"})

    with pytest.raises(HotmartError) as info:
        run(make_client(handler).token())
    assert "credenciales" in str(info.value) and SECRET not in str(info.value)


def test_unconfigured_client_never_calls_hotmart() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no debe llamar a Hotmart")

    c = HotmartClient(
        client_id="",
        client_secret="",
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert not c.configured()
    with pytest.raises(HotmartError):
        run(c.token())


# ───────────────────────────── mapeo ─────────────────────────────


def test_a_sale_becomes_a_row_without_buyer_data() -> None:
    row = sale_row("u1", item())
    assert row["transaction"] == "HP1" and row["product_id"] == 7
    assert (row["price"], row["fee"], row["currency"]) == (47.0, 4.0, "USD")
    assert row["status"] == "APPROVED" and row["payment_type"] == "CREDIT_CARD"
    assert row["order_date"].startswith("2025-") and row["approved_date"]
    assert (row["src"], row["sck"]) == ("meta", "lote-1")
    assert "ana" not in str(row).lower() and "buyer" not in row


def test_sales_without_a_transaction_code_are_skipped() -> None:
    assert sale_row("u1", {"purchase": {"status": "APPROVED"}}) is None
    assert sale_row("u1", {}) is None
    assert (
        sale_row("u1", {"purchase": {"transaction": "X", "price": {"value": "n/a"}}})["price"] == 0
    )


# ───────────────────────────── API ─────────────────────────────


class MemoryHotmart:
    def __init__(self) -> None:
        self.sales: dict[tuple[str, str], dict] = {}
        self.sync: dict[str, dict] = {}
        self.links: dict[tuple[str, int], str] = {}

    async def upsert_sales(self, rows) -> int:
        for r in rows:
            self.sales[(r["user_id"], r["transaction"])] = r
        return len(rows)

    async def get_sync(self, user_id):
        return self.sync.get(str(user_id))

    async def save_sync(self, user_id, **values) -> None:
        self.sync.setdefault(str(user_id), {}).update(values)

    async def link(self, user_id, hotmart_product_id, product_id) -> None:
        key = (str(user_id), hotmart_product_id)
        if product_id is None:
            self.links.pop(key, None)
        else:
            self.links[key] = str(product_id)


class FakeHotmart:
    def __init__(self, items=None, error=None) -> None:
        self.items = items if items is not None else [item("HP1"), item("HP2", price=20.0)]
        self.error = error
        self.windows: list[tuple[datetime, datetime]] = []

    def configured(self) -> bool:
        return True

    async def sales_history(self, since, until):
        self.windows.append((since, until))
        if self.error:
            raise self.error
        return self.items


def hotmart_world(fake: FakeHotmart | None = None, configured=True):
    w = AdsWorld()
    w.repo = MemoryHotmart()
    w.fake = fake or FakeHotmart()
    w.services.hotmart = w.fake if configured else None
    w.services.hotmart_repo = w.repo
    return w


def test_status_reports_unconfigured_and_never_calls_hotmart() -> None:
    w = hotmart_world(configured=False)
    assert w.client.get("/hotmart/status").json() == {
        "configured": False,
        "synced_at": None,
        "last_error": None,
        "count": 0,
    }
    assert w.client.post("/hotmart/sync").status_code == 503


def test_sync_stores_sales_and_a_later_refund_updates_the_same_row() -> None:
    w = hotmart_world()
    assert w.client.post("/hotmart/sync", json={"days": 30}).json() == {"sales": 2}
    assert len(w.repo.sales) == 2
    since, until = w.fake.windows[0]
    assert (until - since).days == 30

    w.fake.items = [item("HP1", status="REFUNDED"), item("HP2", price=20.0)]
    w.client.post("/hotmart/sync")
    assert len(w.repo.sales) == 2  # nada se duplica
    assert w.repo.sales[(USER, "HP1")]["status"] == "REFUNDED"
    status = w.client.get("/hotmart/status").json()
    assert status["configured"] and status["synced_at"] and status["count"] == 2


def test_sync_validates_the_period_and_reports_hotmart_failures() -> None:
    w = hotmart_world()
    assert w.client.post("/hotmart/sync", json={"days": 0}).status_code == 422
    assert w.client.post("/hotmart/sync", json={"days": 4000}).status_code == 422

    w2 = hotmart_world(FakeHotmart(error=HotmartError("Hotmart respondió HTTP 500", status=500)))
    response = w2.client.post("/hotmart/sync")
    assert response.status_code == 502 and "HTTP 500" in response.json()["detail"]
    assert w2.client.get("/hotmart/status").json()["last_error"] == "Hotmart respondió HTTP 500"
    # y el candado se libera: se puede reintentar
    assert w2.client.post("/hotmart/sync").status_code == 502


def test_the_hotmart_endpoints_require_a_session() -> None:
    w = hotmart_world()
    w.client.headers.pop("Authorization")
    assert w.client.get("/hotmart/status").status_code in (401, 403)
    assert w.client.post("/hotmart/sync").status_code in (401, 403)


def test_a_hotmart_product_can_be_linked_to_your_own_product_only() -> None:
    w = hotmart_world()
    mine = w.product["id"]
    assert w.client.put("/hotmart/products/7/link", json={"product_id": mine}).status_code == 204
    assert w.repo.links[(USER, 7)] == mine
    assert w.client.put("/hotmart/products/7/link", json={"product_id": None}).status_code == 204
    assert (USER, 7) not in w.repo.links
    stranger = str(uuid4())
    assert (
        w.client.put("/hotmart/products/7/link", json={"product_id": stranger}).status_code == 404
    )
    assert w.repo.links == {}


# ───────────────────────────── seguridad ─────────────────────────────


def test_hotmart_credentials_are_masked_in_logs() -> None:
    basic = "Basic " + base64.b64encode(f"cid:{SECRET}".encode()).decode()
    record = logging.LogRecord("x", logging.ERROR, __file__, 1, f"fallo con {basic}", None, None)
    assert basic not in RedactingFormatter().format(record)


def test_id_and_secret_go_together() -> None:
    assert hotmart_problems(Settings(_env_file=None, hotmart_client_id="a")) != []
    assert hotmart_problems(Settings(_env_file=None, hotmart_client_secret="b")) != []
    assert (
        hotmart_problems(Settings(_env_file=None, hotmart_client_id="a", hotmart_client_secret="b"))
        == []
    )
    assert hotmart_problems(Settings(_env_file=None)) == []


def test_no_hotmart_secret_reaches_the_frontend() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    assert "HOTMART_CLIENT_SECRET" in (root / ".env.example").read_text(encoding="utf-8")
    for path in (root / "frontend").rglob("*.ts*"):
        if "node_modules" in path.parts or ".next" in path.parts:
            continue
        assert "HOTMART_CLIENT" not in path.read_text(encoding="utf-8", errors="ignore"), path
    assert SimpleNamespace  # (import usado por otros tests de este archivo)
