"""Acceso a Postgres vía PostgREST con la service role.

Es el ÚNICO lugar del backend que escribe en la base. La service role salta RLS, así
que cada repositorio filtra o fija `user_id` explícitamente con el usuario del JWT.
"""

from typing import Any
from uuid import UUID

import httpx

from app.content.claude_client import CallUsage
from app.content.schemas import PackageOutline, PackageRequest


class SupabaseRest:
    def __init__(self, url: str, service_key: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"{url.rstrip('/')}/rest/v1",
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            timeout=15,
        )

    async def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(
            f"/{table}", json=row, headers={"Prefer": "return=representation"}
        )
        response.raise_for_status()
        return response.json()[0]

    async def aclose(self) -> None:
        await self._client.aclose()


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
        row = await self._db.insert(
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
