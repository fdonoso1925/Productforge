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
from app.storage.crypto import from_bytea, to_bytea

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

    async def upsert(self, table: str, row: Row, on_conflict: str) -> list[Row]:
        response = await self._client.post(
            f"/{table}",
            json=row,
            params={"on_conflict": on_conflict},
            headers={"Prefer": "return=representation,resolution=merge-duplicates"},
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


def child_row(parent: Row, **overrides: Any) -> Row:
    """Fila de un producto derivado (versión remodelada o duplicado a otro mercado).

    Apunta al original (`parent_product_id`) y a la raíz del árbol (`root_product_id`).
    """
    row: Row = {
        "user_id": parent["user_id"],
        "parent_product_id": parent["id"],
        "root_product_id": parent.get("root_product_id") or parent["id"],
        "title": parent.get("title"),
        "slug": parent.get("slug"),
        "niche": parent["niche"],
        "problem": parent["problem"],
        "market": parent["market"],
        "main_format": parent["main_format"],
        "template_id": parent["template_id"],
        "tone": parent.get("tone"),
        "audience_override": parent.get("audience_override"),
        "outline": parent.get("outline"),
        "commercial": parent.get("commercial"),
        "prompt_version": parent["prompt_version"],
        "status": "generating",
    }
    row.update(overrides)
    return row


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

    async def create_child(self, parent: Row, **overrides: Any) -> Row:
        [row] = await self._db.insert("products", child_row(parent, **overrides))
        return row


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

    async def list_for_product(self, product_id: UUID) -> list[Row]:
        return await self._db.select(
            "product_items", product_id=eq(product_id), order="role.asc,order.asc"
        )

    async def insert_many(self, rows: list[Row]) -> list[Row]:
        return await self._db.insert("product_items", rows) if rows else []

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
        onedrive_status: str = "pending",
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
                "onedrive_status": onedrive_status,
            },
        )
        return row

    async def update(self, file_id: UUID | str, **values: Any) -> None:
        await self._db.update("files", values, id=eq(file_id))

    async def unsynced(self, max_attempts: int, user_id: UUID | None = None) -> list[Row]:
        """Archivos pendientes o fallidos que aún admiten reintentos (para el reintento
        automático y para "sincronizar todo")."""
        filters = {
            "onedrive_status": "in.(pending,failed)",
            "upload_attempts": f"lt.{max_attempts}",
            "file_type": "neq.zip",
            "select": "product_id,user_id",
            "limit": "1000",
        }
        if user_id:
            filters["user_id"] = eq(user_id)
        return await self._db.select("files", **filters)

    async def delete_for_product(self, product_id: UUID) -> None:
        await self._db.delete("files", product_id=eq(product_id))

    async def list_for_product(self, product_id: UUID) -> list[Row]:
        return await self._db.select("files", product_id=eq(product_id))

    async def delete_ids(self, ids: list[str]) -> None:
        if ids:
            await self._db.delete("files", id=f"in.({','.join(ids)})")

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

    async def active_for_product(self, product_id: UUID, kind: str | None = None) -> list[Row]:
        filters = {"product_id": eq(product_id), "status": "in.(queued,running)"}
        if kind:
            filters["kind"] = eq(kind)
        return await self._db.select("jobs", **filters)


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


class ConnectionRepo:
    """Tokens OAuth cifrados de cada usuario (tabla `storage_connections`, sin policies:
    solo la service role la ve)."""

    def __init__(self, db: SupabaseRest) -> None:
        self._db = db

    async def get(self, user_id: UUID, provider: str) -> Row | None:
        rows = await self._db.select(
            "storage_connections", user_id=eq(user_id), provider=eq(provider)
        )
        if not rows:
            return None
        row = rows[0]
        return {
            **row,
            "access_token_enc": from_bytea(row["access_token_enc"]),
            "refresh_token_enc": from_bytea(row["refresh_token_enc"]),
        }

    async def save(
        self,
        *,
        user_id: UUID,
        provider: str,
        account_label: str | None,
        access_token_enc: bytes,
        refresh_token_enc: bytes,
        expires_at: str,
    ) -> None:
        await self._db.upsert(
            "storage_connections",
            {
                "user_id": str(user_id),
                "provider": provider,
                "account_label": account_label,
                "access_token_enc": to_bytea(access_token_enc),
                "refresh_token_enc": to_bytea(refresh_token_enc),
                "expires_at": expires_at,
            },
            on_conflict="user_id,provider",
        )

    async def delete(self, user_id: UUID, provider: str) -> None:
        await self._db.delete("storage_connections", user_id=eq(user_id), provider=eq(provider))
