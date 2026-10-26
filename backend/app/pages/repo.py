"""Repositorio de páginas de ventas (tabla `sales_pages`). Solo el backend escribe, con la service
role: cada consulta que nace de un request filtra por `user_id`."""

from typing import Any
from uuid import UUID

from app.db.supabase import NotFound, Row, SupabaseRest, eq


class SalesPageRepo:
    def __init__(self, db: SupabaseRest) -> None:
        self._db = db

    async def create(self, row: Row) -> Row:
        [created] = await self._db.insert("sales_pages", row)
        return created

    async def get(self, page_id: UUID | str, user_id: UUID | None = None) -> Row:
        filters = {"id": eq(page_id)}
        if user_id:
            filters["user_id"] = eq(user_id)
        rows = await self._db.select("sales_pages", **filters)
        if not rows:
            raise NotFound(f"página {page_id}")
        return rows[0]

    async def update(self, page_id: UUID | str, **values: Any) -> None:
        await self._db.update("sales_pages", values, id=eq(page_id))

    async def list_for_user(self, user_id: UUID, limit: int = 100) -> list[Row]:
        return await self._db.select(
            "sales_pages", user_id=eq(user_id), order="created_at.desc", limit=str(limit)
        )

    async def delete(self, page_id: UUID, user_id: UUID) -> None:
        await self._db.delete("sales_pages", id=eq(page_id), user_id=eq(user_id))
