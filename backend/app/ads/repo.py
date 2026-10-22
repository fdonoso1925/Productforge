"""Repositorios del módulo Creativos (tablas `ad_*`). Solo el backend escribe, con la service role,
así que cada consulta que nace de un request filtra por `user_id`."""

from datetime import date
from typing import Any
from uuid import UUID

from app.db.supabase import NotFound, Row, SupabaseRest, eq


class AdBatchRepo:
    def __init__(self, db: SupabaseRest) -> None:
        self._db = db

    async def create(self, row: Row) -> Row:
        [created] = await self._db.insert("ad_batches", row)
        return created

    async def get(self, batch_id: UUID | str, user_id: UUID | None = None) -> Row:
        filters = {"id": eq(batch_id)}
        if user_id:
            filters["user_id"] = eq(user_id)
        rows = await self._db.select("ad_batches", **filters)
        if not rows:
            raise NotFound(f"lote {batch_id}")
        return rows[0]

    async def update(self, batch_id: UUID | str, **values: Any) -> None:
        await self._db.update("ad_batches", values, id=eq(batch_id))

    async def list_for_user(self, user_id: UUID, limit: int = 50) -> list[Row]:
        return await self._db.select(
            "ad_batches", user_id=eq(user_id), order="created_at.desc", limit=str(limit)
        )


class AdCreativeRepo:
    def __init__(self, db: SupabaseRest) -> None:
        self._db = db

    async def insert_many(self, rows: list[Row]) -> list[Row]:
        return await self._db.insert("ad_creatives", rows) if rows else []

    async def list_for_batch(self, batch_id: UUID | str) -> list[Row]:
        return await self._db.select("ad_creatives", batch_id=eq(batch_id), order="created_at.asc")

    async def get(self, creative_id: UUID | str, user_id: UUID) -> Row:
        rows = await self._db.select("ad_creatives", id=eq(creative_id), user_id=eq(user_id))
        if not rows:
            raise NotFound(f"creativo {creative_id}")
        return rows[0]

    async def update(self, creative_id: UUID | str, **values: Any) -> None:
        await self._db.update("ad_creatives", values, id=eq(creative_id))

    async def delete_for_batch(self, batch_id: UUID | str) -> None:
        await self._db.delete("ad_creatives", batch_id=eq(batch_id))


class AdProofRepo:
    def __init__(self, db: SupabaseRest) -> None:
        self._db = db

    async def list(self, user_id: UUID, product_id: UUID | None = None) -> list[Row]:
        """Pruebas del producto y las generales (sin producto) del usuario."""
        filters = {"user_id": eq(user_id), "order": "created_at.asc"}
        if product_id:
            filters["or"] = f"(product_id.is.null,product_id.eq.{product_id})"
        else:
            filters["product_id"] = "is.null"
        return await self._db.select("ad_proofs", **filters)

    async def add(self, row: Row) -> Row:
        [created] = await self._db.insert("ad_proofs", row)
        return created

    async def delete(self, proof_id: UUID, user_id: UUID) -> None:
        await self._db.delete("ad_proofs", id=eq(proof_id), user_id=eq(user_id))


class AdImageCacheRepo:
    """Caché de imágenes base por escena (tabla `ad_image_cache`, solo backend)."""

    def __init__(self, db: SupabaseRest) -> None:
        self._db = db

    async def get(self, scene_hash: str) -> Row | None:
        rows = await self._db.select("ad_image_cache", scene_hash=eq(scene_hash))
        return rows[0] if rows else None

    async def put(self, row: Row) -> None:
        await self._db.upsert("ad_image_cache", row, on_conflict="scene_hash")


class ProviderUsageRepo:
    """Consumo diario por proveedor (tabla `ad_provider_usage`)."""

    def __init__(self, db: SupabaseRest) -> None:
        self._db = db

    async def get(self, provider: str, day: date) -> Row | None:
        rows = await self._db.select("ad_provider_usage", provider=eq(provider), day=eq(day))
        return rows[0] if rows else None

    async def add(self, provider: str, day: date, *, requests: int, cost_usd: float) -> None:
        await self._db.rpc(
            "ad_usage_add",
            {"p_provider": provider, "p_day": str(day), "p_requests": requests, "p_cost": cost_usd},
        )

    async def mark_exhausted(self, provider: str, day: date) -> None:
        await self._db.upsert(
            "ad_provider_usage",
            {"provider": provider, "day": str(day), "exhausted": True},
            on_conflict="provider,day",
        )
