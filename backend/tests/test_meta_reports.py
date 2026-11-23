"""Campañas de Meta con métricas (solo lectura): período, cálculos y endpoints."""

from datetime import date

import pytest

from app.ads.meta import reports
from app.ads.meta.client import AdAccount, MetaError
from app.api import meta_reports
from tests.test_api_ads import AdsWorld

TODAY = date(2026, 11, 23)


def row(cid="1", name="Camp", spend="10", impressions="1000", clicks="20", reach="800", **extra):
    return {
        "campaign_id": cid,
        "campaign_name": name,
        "spend": spend,
        "impressions": impressions,
        "inline_link_clicks": clicks,
        "reach": reach,
        **extra,
    }


# ───────────────────────────── período ─────────────────────────────


def test_presets_include_today_and_custom_ranges_are_validated() -> None:
    assert reports.period_params("last_7d", None, None, TODAY) == {
        "time_range": {"since": "2026-11-17", "until": "2026-11-23"}
    }
    assert reports.period_params(None, None, None, TODAY)["time_range"]["since"] == "2026-10-25"
    assert reports.period_params("maximum", None, None, TODAY) == {"date_preset": "maximum"}
    custom = reports.period_params(None, date(2026, 1, 1), date(2026, 12, 31), TODAY)
    assert custom == {"time_range": {"since": "2026-01-01", "until": "2026-11-23"}}  # sin futuro
    for bad in [
        ("x", None, None),
        (None, date(2026, 3, 1), None),
        (None, date(2026, 3, 1), date(2026, 2, 1)),
        (None, date(2027, 1, 1), date(2027, 1, 2)),
        (None, date(2020, 1, 1), date(2026, 1, 1)),
    ]:
        with pytest.raises(ValueError):
            reports.period_params(*bad, TODAY)


# ───────────────────────────── cálculos ─────────────────────────────


def test_purchases_are_counted_once_and_derived_metrics_come_from_totals() -> None:
    actions = [
        {"action_type": "omni_purchase", "value": "2"},
        {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "2"},  # la misma compra
        {"action_type": "omni_initiated_checkout", "value": "5"},
    ]
    values = [{"action_type": "omni_purchase", "value": "54"}]
    t = reports.totals_of(row(actions=actions, action_values=values))
    assert t["purchases"] == 2 and t["checkouts"] == 5 and t["revenue"] == 54
    m = reports.metrics(t, reach=800)
    assert m["ctr"] == 2.0 and m["cpc"] == 0.5 and m["cpm"] == 10.0
    assert m["cpa"] == 5.0 and m["roas"] == 5.4 and m["frequency"] == 1.25


def test_without_clicks_or_sales_the_ratios_are_unknown_not_zero() -> None:
    m = reports.metrics(reports.totals_of(row(clicks="0")))
    assert m["cpc"] is None and m["cpa"] is None and m["roas"] is None and m["reach"] is None


def test_budgets_come_in_cents_except_zero_decimal_currencies() -> None:
    assert reports.budget({"daily_budget": "800"}, "USD") == {"kind": "daily", "amount": 8.0}
    assert reports.budget({"lifetime_budget": "5000"}, "CLP") == {
        "kind": "lifetime",
        "amount": 5000.0,
    }
    assert reports.budget({}, "USD") is None  # presupuesto en los conjuntos


def test_the_report_lists_every_campaign_even_without_spend_and_marks_app_ones() -> None:
    campaigns = [
        {"id": "1", "name": "Ventas", "effective_status": "PAUSED", "daily_budget": "500"},
        {"id": "2", "name": "Sin gasto", "effective_status": "ACTIVE"},
    ]
    rows = [row("1", spend="10"), row("9", name="Borrada", spend="30")]
    rep = reports.campaign_report(campaigns, rows, "USD", {"2"})
    names = [c["name"] for c in rep["campaigns"]]
    assert names == ["Borrada", "Ventas", "Sin gasto"]  # el que más gastó primero
    deleted, sales, idle = rep["campaigns"]
    assert deleted["status"] == "DELETED" and idle["metrics"]["spend"] == 0
    assert idle["from_app"] and not sales["from_app"]
    assert rep["totals"]["spend"] == 40 and rep["totals"]["reach"] is None  # el alcance no se suma


def test_daily_series_and_ads_are_aggregated_and_sorted() -> None:
    daily = reports.daily_series([row(date_start="2026-03-02"), row(date_start="2026-03-01")])
    assert [d["day"] for d in daily] == ["2026-03-01", "2026-03-02"]
    ads = reports.ad_rows(
        [
            {**row(spend="3"), "ad_id": "a", "ad_name": "A", "adset_name": "S"},
            {**row(spend="7"), "ad_id": "b", "ad_name": "B", "adset_name": "S"},
        ]
    )
    assert [a["name"] for a in ads] == ["B", "A"] and ads[0]["adset"] == "S"


# ───────────────────────────── endpoints ─────────────────────────────


class ReportMeta:
    def __init__(self, error: MetaError | None = None) -> None:
        self.error = error
        self.calls: list[dict] = []

    def configured(self) -> bool:
        return True

    async def account_info(self) -> AdAccount:
        if self.error:
            raise self.error
        return AdAccount(id="act_1", name="Mi cuenta", currency="USD", status=1)

    async def campaigns(self) -> list[dict]:
        return [{"id": "11", "name": "Ventas", "effective_status": "PAUSED"}]

    async def report(self, **kwargs) -> list[dict]:
        self.calls.append(kwargs)
        if kwargs["level"] == "ad":
            return [{**row("11"), "ad_id": "a1", "ad_name": "Anuncio"}]
        if kwargs.get("daily"):
            return [row("11", date_start="2026-03-01")]
        return [row("11")]


@pytest.fixture(autouse=True)
def clean_cache():
    meta_reports._cache.clear()
    yield
    meta_reports._cache.clear()


def test_campaigns_endpoint_reads_the_account_and_caches_the_answer() -> None:
    meta = ReportMeta()
    w = AdsWorld(meta=meta)
    data = w.client.get("/ads/meta/campaigns?preset=last_90d").json()
    assert data["account"] == {"id": "act_1", "name": "Mi cuenta", "currency": "USD"}
    assert data["campaigns"][0]["metrics"]["spend"] == 10 and data["totals"]["clicks"] == 20
    assert len(meta.calls) == 1
    w.client.get("/ads/meta/campaigns?preset=last_90d")
    assert len(meta.calls) == 1  # de la caché: no se vuelve a consultar a Meta
    w.client.get("/ads/meta/campaigns?preset=last_90d&refresh=true")
    assert len(meta.calls) == 2


def test_campaign_detail_filters_inside_the_account() -> None:
    meta = ReportMeta()
    w = AdsWorld(meta=meta)
    data = w.client.get("/ads/meta/campaigns/11?preset=maximum").json()
    assert data["daily"][0]["day"] == "2026-03-01" and data["ads"][0]["name"] == "Anuncio"
    assert all(c["campaign_id"] == "11" for c in meta.calls)
    assert w.client.get("/ads/meta/campaigns/abc").status_code == 422  # solo ids numéricos


def test_campaigns_need_meta_valid_periods_and_a_session() -> None:
    assert AdsWorld(meta=None).client.get("/ads/meta/campaigns").status_code == 503
    w = AdsWorld(meta=ReportMeta())
    assert w.client.get("/ads/meta/campaigns?preset=raro").status_code == 422
    assert w.client.get("/ads/meta/campaigns?since=2026-03-01").status_code == 422
    failing = AdsWorld(meta=ReportMeta(error=MetaError("token vencido", code=190)))
    response = failing.client.get("/ads/meta/campaigns")
    assert response.status_code == 502 and "token vencido" in response.json()["detail"]
    w.client.headers.pop("Authorization")
    assert w.client.get("/ads/meta/campaigns").status_code in (401, 403)
