"""Acceso a Postgres vía PostgREST con la service role.

Es el ÚNICO lugar del backend que escribe en la base. La service role salta RLS, así
que cada consulta que nace de un request filtra o fija `user_id` explícitamente con el
usuario del JWT.
"""

from typing import Any
from uuid import UUID

import httpx

from app.content.claude_client import CallUsage
from app.content.schemas import PackageOutline, PackageRequest

Row = dict[str, Any]


class NotFound(Exception):
    pass


class SupabaseRest:
    def __init__(self, url: str, service_key: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"{url.rstrip('/')}/rest/v1",
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            timeout=15,
        )

    async def insert(self, table: str, row: Row | list[Row]) -> list[Row]:
        response = await self._client.post(
            f"/{table}", json=row, headers={"Prefer": "return=representation"}
        )
        response.raise_for_status()
        return response.json()

    async def select(self, table: str, **filters: str) -> list[Row]:
        response = await self._client.get(f"/{table}", params={"select": "*", **filters})
        response.raise_for_status()
        return response.json()

    async def update(self, table: str, values: Row, **filters: str) -> list[Row]:
        response = await self._client.patch(
            f"/{table}", json=values, params=filters, headers={"Prefer": "return=representation"}
        )
        response.raise_for_status()
        return response.json()

    async def delete(self, table: str, **filters: str) -> None:
        (await self._client.delete(f"/{table}", params=filters)).raise_for_status()

    async def rpc(self, function: str, args: Row | None = None) -> Any:
        response = await self._client.post(f"/rpc/{function}", json=args or {})
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()


def eq(value: object) -> str:
    return f"eq.{value}"


class ProductRepo:
    def __init__(self, db: SupabaseRest) -> None:
        self._db = db

    async def create_with_outline(
        self,
        *,
        user_id: UUID,
        request: PackageRequest,
        template_id: str,
        outline: PackageOutline,
        prompt_version: str,
    ) -> UUID:
        [row] = await self._db.insert(
            "products",
            {
                "user_id": str(user_id),
                "title": outline.product_name,
                "niche": request.niche,
                "problem": request.problem.model_dump(),
                "market": request.market,
                "main_format": request.main_format.value,
                "template_id": template_id,
                "tone": request.tone,
                "audience_override": request.audience_override,
                "outline": outline.model_dump(mode="json"),
                "prompt_version": prompt_version,
                "status": "outline_ready",
            },
        )
        return UUID(row["id"])

    async def get(self, product_id: UUID, user_id: UUID | None = None) -> Row:
        filters = {"id": eq(product_id)}
        if user_id:
            filters["user_id"] = eq(user_id)
        rows = await self._db.select("products", **filters)
        if not rows:
            raise NotFound(f"producto {product_id}")
        return rows[0]

    async def update(self, product_id: UUID, **values: Any) -> None:
        await self._db.update("products", values, id=eq(product_id))


class ItemRepo:
    def __init__(self, db: SupabaseRest) -> None:
        self._db = db

    async def replace_from_outline(
        self, product_id: UUID, user_id: UUID, outline: PackageOutline
    ) -> list[Row]:
        """Crea una fila por pieza del outline (borra las anteriores del producto)."""
        await self._db.delete("product_items", product_id=eq(product_id))
        rows = []
        for role, items in (
            ("main", [outline.main]),
            ("order_bump", outline.order_bumps),
            ("bonus", outline.bonuses),
        ):
            for order, item in enumerate(items):
                rows.append(
                    {
                        "product_id": str(product_id),
                        "user_id": str(user_id),
                        "role": role,
                        "format": item.format.value,
                        "title": item.title,
                        "outline": item.model_dump(mode="json"),
                        "order": order,
                    }
                )
        return await self._db.insert("product_items", rows)

    async def update(self, item_id: UUID | str, **values: Any) -> None:
        await self._db.update("product_items", values, id=eq(item_id))


class FileRepo:
    def __init__(self, db: SupabaseRest) -> None:
        self._db = db

    async def add(
        self,
        *,
        product_id: UUID,
        user_id: UUID,
        item_id: str | None,
        file_type: str,
        storage_path: str,
        size: int,
    ) -> Row:
        [row] = await self._db.insert(
            "files",
            {
                "product_id": str(product_id),
                "user_id": str(user_id),
                "product_item_id": item_id,
                "file_type": file_type,
                "storage_path": storage_path,
                "size": size,
            },
        )
        return row

    async def delete_for_product(self, product_id: UUID) -> None:
        await self._db.delete("files", product_id=eq(product_id))

    async def get(self, file_id: UUID, user_id: UUID) -> Row:
        rows = await self._db.select("files", id=eq(file_id), user_id=eq(user_id))
        if not rows:
            raise NotFound(f"archivo {file_id}")
        return rows[0]


class JobRepo:
    def __init__(self, db: SupabaseRest) -> None:
        self._db = db

    async def enqueue(self, *, product_id: UUID, user_id: UUID, kind: str, payload: Row) -> Row:
        [row] = await self._db.insert(
            "jobs",
            {
                "product_id": str(product_id),
                "user_id": str(user_id),
                "kind": kind,
                "payload": payload,
            },
        )
        return row

    async def claim(self) -> Row | None:
        rows = await self._db.rpc("claim_job")
        return rows[0] if rows else None

    async def update(self, job_id: UUID | str, **values: Any) -> None:
        await self._db.update("jobs", values, id=eq(job_id))

    async def active_for_product(self, product_id: UUID) -> list[Row]:
        return await self._db.select(
            "jobs", product_id=eq(product_id), status="in.(queued,running)"
        )


class UsageRepo:
    def __init__(self, db: SupabaseRest) -> None:
        self._db = db

    async def record(self, user_id: UUID, product_id: UUID | None, usage: CallUsage) -> None:
        await self._db.insert(
            "ai_usage",
            {
                "user_id": str(user_id),
                "product_id": str(product_id) if product_id else None,
                "model": usage.model,
                "input_tokens": usage.input_tokens
                + usage.cache_read_tokens
                + usage.cache_write_tokens,
                "output_tokens": usage.output_tokens,
                "cost_usd": round(usage.cost_usd, 5),
            },
        )
