"""Reportes de campañas de Meta: de las filas de `insights` a métricas listas para mostrar.

Como en el resto de la app, solo se suman totales (gasto, impresiones, clics, compras, valor) y
las métricas derivadas (CTR, CPC, CPM, CPA, ROAS) se calculan de esos totales: promediar
porcentajes de filas distintas daría números falsos. El alcance no se suma (una persona puede
verse en varios días o campañas): solo se muestra por campaña y para todo el período.
"""

from datetime import date, timedelta
from typing import Any

from app.ads.meta.client import ZERO_DECIMAL

PRESETS = {"last_7d": 7, "last_30d": 30, "last_90d": 90}
MAX_RANGE_DAYS = 37 * 31  # Meta guarda unos 37 meses de métricas
# Tipos de acción de Meta, del más completo al más específico (sin contar dos veces lo mismo).
PURCHASES = ("omni_purchase", "purchase", "offsite_conversion.fb_pixel_purchase")
CHECKOUTS = (
    "omni_initiated_checkout",
    "initiate_checkout",
    "offsite_conversion.fb_pixel_initiate_checkout",
)
LANDINGS = ("omni_landing_page_view", "landing_page_view")


def period_params(preset: str | None, since: date | None, until: date | None, today: date) -> dict:
    """El período para la Graph API. Lanza ValueError si no tiene sentido."""
    if since or until:
        if not (since and until):
            raise ValueError("indica las dos fechas (desde y hasta)")
        if until < since:
            raise ValueError("la fecha final es anterior a la inicial")
        if since > today:
            raise ValueError("la fecha inicial está en el futuro")
        if (until - since).days >= MAX_RANGE_DAYS:
            raise ValueError("Meta solo guarda unos 37 meses de métricas")
        return {"time_range": {"since": since.isoformat(), "until": min(until, today).isoformat()}}
    preset = preset or "last_30d"
    if preset == "maximum":
        return {"date_preset": "maximum"}
    if preset not in PRESETS:
        raise ValueError(f"período desconocido: {preset}")
    # Rango explícito (incluye hoy) en vez del preset de Meta, que deja hoy fuera.
    first = today - timedelta(days=PRESETS[preset] - 1)
    return {"time_range": {"since": first.isoformat(), "until": today.isoformat()}}


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def first_action(rows: list[dict] | None, kinds: tuple[str, ...]) -> float:
    """Valor del primer tipo de acción presente (en orden de preferencia)."""
    by_type = {r.get("action_type"): r.get("value") for r in rows or []}
    for kind in kinds:
        if kind in by_type:
            return _number(by_type[kind])
    return 0.0


def totals_of(row: dict) -> dict[str, float]:
    """Los totales sumables de una fila de insights."""
    return {
        "spend": _number(row.get("spend")),
        "impressions": _number(row.get("impressions")),
        "clicks": _number(row.get("inline_link_clicks")),
        "landing_views": first_action(row.get("actions"), LANDINGS),
        "checkouts": first_action(row.get("actions"), CHECKOUTS),
        "purchases": first_action(row.get("actions"), PURCHASES),
        "revenue": first_action(row.get("action_values"), PURCHASES),
    }


def add(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    return {k: a.get(k, 0.0) + b.get(k, 0.0) for k in set(a) | set(b)}


def empty() -> dict[str, float]:
    return totals_of({})


def ratio(num: float, den: float, scale: float = 1.0) -> float | None:
    return round(num / den * scale, 4) if den else None


def metrics(t: dict[str, float], reach: float | None = None) -> dict[str, Any]:
    """Totales redondeados y derivadas calculadas de ellos (None = no se puede calcular)."""
    out: dict[str, Any] = {
        "spend": round(t["spend"], 2),
        "impressions": int(t["impressions"]),
        "clicks": int(t["clicks"]),
        "landing_views": int(t["landing_views"]),
        "checkouts": int(t["checkouts"]),
        "purchases": int(t["purchases"]),
        "revenue": round(t["revenue"], 2),
        "ctr": ratio(t["clicks"], t["impressions"], 100),
        "cpc": ratio(t["spend"], t["clicks"]),
        "cpm": ratio(t["spend"], t["impressions"], 1000),
        "cpa": ratio(t["spend"], t["purchases"]),
        "roas": ratio(t["revenue"], t["spend"]) if t["revenue"] else None,
        "reach": None,
        "frequency": None,
    }
    if reach:
        out["reach"] = int(reach)
        out["frequency"] = ratio(t["impressions"], reach)
    return out


def budget(campaign: dict, currency: str) -> dict[str, Any] | None:
    """Presupuesto de la campaña en la moneda de la cuenta (Meta lo da en centavos). Nulo si el
    presupuesto está en los conjuntos de anuncios."""
    for kind in ("daily_budget", "lifetime_budget"):
        raw = campaign.get(kind)
        if raw:
            amount = _number(raw) if currency.upper() in ZERO_DECIMAL else _number(raw) / 100
            return {"kind": "daily" if kind == "daily_budget" else "lifetime", "amount": amount}
    return None


def campaign_report(
    campaigns: list[dict], rows: list[dict], currency: str, app_campaign_ids: set[str]
) -> dict[str, Any]:
    """Una fila por campaña (también las que no gastaron en el período) y los totales."""
    by_id: dict[str, dict] = {}
    for row in rows:
        cid = str(row.get("campaign_id") or "")
        if not cid:
            continue
        entry = by_id.setdefault(cid, {"totals": empty(), "reach": 0.0, "name": ""})
        entry["totals"] = add(entry["totals"], totals_of(row))
        entry["reach"] += _number(row.get("reach"))  # una fila por campaña en el período
        entry["name"] = row.get("campaign_name") or entry["name"]
    known = {str(c["id"]): c for c in campaigns}
    out = []
    total = empty()
    for cid in {*known, *by_id}:
        c = known.get(cid, {})
        data = by_id.get(cid, {"totals": empty(), "reach": 0.0, "name": ""})
        total = add(total, data["totals"])
        out.append(
            {
                "id": cid,
                "name": c.get("name") or data["name"] or cid,
                "status": c.get("effective_status") or c.get("status") or "DELETED",
                "objective": c.get("objective"),
                "created_time": c.get("created_time"),
                "budget": budget(c, currency) if c else None,
                "from_app": cid in app_campaign_ids,
                "metrics": metrics(data["totals"], data["reach"] or None),
            }
        )
    out.sort(key=lambda r: (-r["metrics"]["spend"], r["name"].lower()))
    return {"campaigns": out, "totals": metrics(total)}


def daily_series(rows: list[dict]) -> list[dict[str, Any]]:
    days: dict[str, dict[str, float]] = {}
    for row in rows:
        day = row.get("date_start")
        if day:
            days[day] = add(days.get(day, empty()), totals_of(row))
    return [{"day": d, **metrics(t)} for d, t in sorted(days.items())]


def ad_rows(rows: list[dict]) -> list[dict[str, Any]]:
    """Una fila por anuncio de la campaña, el que más gastó primero."""
    ads: dict[str, dict] = {}
    for row in rows:
        aid = str(row.get("ad_id") or "")
        if not aid:
            continue
        entry = ads.setdefault(
            aid,
            {"name": row.get("ad_name") or aid, "adset": row.get("adset_name") or "",
             "totals": empty(), "reach": 0.0},
        )  # fmt: skip
        entry["totals"] = add(entry["totals"], totals_of(row))
        entry["reach"] += _number(row.get("reach"))
    out = [
        {"id": aid, "name": e["name"], "adset": e["adset"],
         "metrics": metrics(e["totals"], e["reach"] or None)}
        for aid, e in ads.items()
    ]  # fmt: skip
    return sorted(out, key=lambda r: -r["metrics"]["spend"])
