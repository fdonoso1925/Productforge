"""Ventas de Hotmart → tabla `hotmart_sales`. Idempotente: repetir la lectura actualiza el estado
de cada venta (un reembolso posterior cambia APPROVED por REFUNDED) sin duplicar nada. No se
guardan datos del comprador."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.db.supabase import Row, SupabaseRest, eq
from app.hotmart.client import HotmartClient, now_utc

MAX_DAYS = 365
CHUNK = 500


class HotmartRepo:
    def __init__(self, db: SupabaseRest) -> None:
        self._db = db

    async def upsert_sales(self, rows: list[Row]) -> int:
        for i in range(0, len(rows), CHUNK):
            await self._db.upsert(
                "hotmart_sales", rows[i : i + CHUNK], on_conflict="user_id,transaction"
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


async def run_sync(client: HotmartClient, repo: HotmartRepo, user_id: UUID, days: int) -> int:
    """Lee las ventas de los últimos `days` días y las guarda. Devuelve cuántas leyó."""
    days = max(1, min(days, MAX_DAYS))
    until = now_utc()
    try:
        items = await client.sales_history(until - timedelta(days=days), until)
        rows = [r for item in items if (r := sale_row(str(user_id), item))]
        await repo.upsert_sales(rows)
    except Exception as exc:
        await repo.save_sync(user_id, last_error=str(exc)[:300])
        raise
    await repo.save_sync(user_id, synced_at=until.isoformat(), last_error=None, count=len(rows))
    return len(rows)
