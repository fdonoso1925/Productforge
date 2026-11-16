"""Ventas de Hotmart → tabla `hotmart_sales`. Idempotente: repetir la lectura actualiza el estado
de cada venta (un reembolso posterior cambia APPROVED por REFUNDED) sin duplicar nada. No se
guardan datos del comprador."""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from app.db.supabase import Row, SupabaseRest, eq
from app.hotmart.client import HotmartClient, HotmartError, now_utc

logger = logging.getLogger("productforge.hotmart")

MAX_DAYS = 365
CHUNK = 500


class HotmartRepo:
    def __init__(self, db: SupabaseRest) -> None:
        self._db = db

    async def upsert_sales(self, rows: list[Row]) -> int:
        # PostgREST exige las mismas claves en todo el lote: las ventas con neto real van aparte
        # de las que no lo tienen (así una lectura sin comisiones nunca borra un neto ya guardado).
        groups: dict[frozenset[str], list[Row]] = {}
        for row in rows:
            groups.setdefault(frozenset(row), []).append(row)
        for group in groups.values():
            for i in range(0, len(group), CHUNK):
                await self._db.upsert(
                    "hotmart_sales", group[i : i + CHUNK], on_conflict="user_id,transaction"
                )
        return len(rows)

    async def get_sync(self, user_id: UUID) -> Row | None:
        rows = await self._db.select("hotmart_sync", user_id=eq(user_id))
        return rows[0] if rows else None

    async def save_sync(self, user_id: UUID, **values: Any) -> None:
        await self._db.upsert(
            "hotmart_sync", {"user_id": str(user_id), **values}, on_conflict="user_id"
        )

    async def link(self, user_id: UUID, hotmart_product_id: int, product_id: UUID | None) -> None:
        if product_id is None:
            await self._db.delete(
                "hotmart_product_links",
                user_id=eq(user_id),
                hotmart_product_id=eq(hotmart_product_id),
            )
            return
        await self._db.upsert(
            "hotmart_product_links",
            {
                "user_id": str(user_id),
                "hotmart_product_id": hotmart_product_id,
                "product_id": str(product_id),
            },
            on_conflict="user_id,hotmart_product_id",
        )


def iso(ms: Any) -> str | None:
    if not isinstance(ms, int | float) or ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat()


def number(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def sale_row(user_id: str, item: dict) -> Row | None:
    """Una fila por venta; sin código de transacción no hay forma de identificarla."""
    purchase = item.get("purchase") or {}
    transaction = purchase.get("transaction")
    if not transaction:
        return None
    price = purchase.get("price") or {}
    tracking = purchase.get("tracking") or {}
    product = item.get("product") or {}
    return {
        "user_id": user_id,
        "transaction": str(transaction),
        "product_id": product.get("id"),
        "product_name": (product.get("name") or "")[:300] or None,
        "status": str(purchase.get("status") or "UNKNOWN"),
        "order_date": iso(purchase.get("order_date")),
        "approved_date": iso(purchase.get("approved_date")),
        "price": number(price.get("value")),
        "currency": str(price.get("currency_code") or "BRL").upper()[:3],
        "fee": number((purchase.get("hotmart_fee") or {}).get("total")),
        "commission_as": purchase.get("commission_as"),
        "payment_type": (purchase.get("payment") or {}).get("type"),
        "is_subscription": bool(purchase.get("is_subscription")),
        "src": (tracking.get("source") or None),
        "sck": (tracking.get("source_sck") or None),
        "updated_at": now_utc().isoformat(),
    }


def period_bounds(
    days: int | None, start: date | None, end: date | None, now: datetime
) -> tuple[datetime, datetime]:
    """Período a leer: un rango de fechas (días UTC completos, `end` incluido) o los últimos días.

    Lanza ValueError si el rango no tiene sentido (fin antes del inicio, futuro o más de un año).
    """
    if start is None and end is None:
        return now - timedelta(days=max(1, min(days or 90, MAX_DAYS))), now
    first = start or (end - timedelta(days=MAX_DAYS - 1))  # type: ignore[operator]
    last = end or now.date()
    if last < first:
        raise ValueError("la fecha final es anterior a la inicial")
    if first > now.date():
        raise ValueError("la fecha inicial está en el futuro")
    since = datetime(first.year, first.month, first.day, tzinfo=UTC)
    until = min(datetime(last.year, last.month, last.day, tzinfo=UTC) + timedelta(days=1), now)
    if (until - since).days >= MAX_DAYS + 1:
        raise ValueError(f"el rango no puede superar {MAX_DAYS} días")
    return since, until


def real_net(commission_item: dict, role: str | None) -> tuple[float, float | None] | None:
    """Facturación neta real de una venta: la comisión del propio usuario (según su rol en la
    venta) en USD y el tipo de cambio que aplicó Hotmart (USD por unidad de la moneda de venta).

    Nulo si no se puede saber con certeza: sin rol, ninguna o varias comisiones de ese rol (no
    hay forma de distinguir a dos coproductores) o una moneda de pago que no sea USD.
    """
    mine = [c for c in commission_item.get("commissions") or [] if c.get("source") == role]
    if not role or len(mine) != 1:
        return None
    commission = mine[0].get("commission") or {}
    value = commission.get("value")
    if str(commission.get("currency_code") or "").upper() != "USD" or not isinstance(
        value, int | float
    ):
        return None
    rate = commission_item.get("exchange_rate_currency_payout")
    ok = isinstance(rate, int | float) and rate > 0
    return round(float(value), 2), (round(float(rate), 8) if ok else None)


def with_real_net(rows: list[Row], commissions: list[dict]) -> None:
    """Agrega `net_usd` y `payout_rate` a las ventas que tienen comisión (sin tocar las demás)."""
    by_transaction = {c.get("transaction"): c for c in commissions if c.get("transaction")}
    for row in rows:
        found = by_transaction.get(row["transaction"])
        net = real_net(found, row.get("commission_as")) if found else None
        if net is not None:
            row["net_usd"], row["payout_rate"] = net


async def run_sync(
    client: HotmartClient,
    repo: HotmartRepo,
    user_id: UUID,
    days: int | None = 90,
    start: date | None = None,
    end: date | None = None,
) -> int:
    """Lee las ventas del período (últimos `days` días o un rango de fechas) y las guarda.
    Devuelve cuántas leyó."""
    since, until = period_bounds(days, start, end, now_utc())
    try:
        items = await client.sales_history(since, until)
        rows = [r for item in items if (r := sale_row(str(user_id), item))]
        try:
            with_real_net(rows, await client.sales_commissions(since, until))
        except HotmartError as exc:
            # Las ventas se guardan igual: el dashboard marca las que no tienen dato real.
            logger.warning("hotmart: no se pudieron leer las comisiones (%s)", exc)
        await repo.upsert_sales(rows)
    except Exception as exc:
        await repo.save_sync(user_id, last_error=str(exc)[:300])
        raise
    await repo.save_sync(user_id, synced_at=now_utc().isoformat(), last_error=None, count=len(rows))
    return len(rows)
