from typing import ClassVar
from urllib.parse import quote

import httpx


class SupabaseStorage:
    """Bucket privado de Supabase Storage; las descargas son URLs firmadas con expiración."""

    name: ClassVar[str] = "supabase"

    def __init__(self, url: str, service_key: str, bucket: str = "products") -> None:
        self._base = f"{url.rstrip('/')}/storage/v1"
        self._bucket = bucket
        self._client = httpx.AsyncClient(
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            timeout=60,
        )

    async def upload(self, path: str, data: bytes, mime: str) -> str:
        response = await self._client.post(
            f"{self._base}/object/{self._bucket}/{quote(path)}",
            content=data,
            headers={"Content-Type": mime, "x-upsert": "true"},
        )
        response.raise_for_status()
        return path

    async def signed_url(self, path: str, expires_in: int) -> str:
        response = await self._client.post(
            f"{self._base}/object/sign/{self._bucket}/{quote(path)}",
            json={"expiresIn": expires_in},
        )
        response.raise_for_status()
        return f"{self._base}{response.json()['signedURL']}"

    async def download(self, path: str) -> bytes:
        response = await self._client.get(f"{self._base}/object/{self._bucket}/{quote(path)}")
        response.raise_for_status()
        return response.content

    async def delete(self, paths: list[str]) -> None:
        if not paths:
            return
        response = await self._client.request(
            "DELETE", f"{self._base}/object/{self._bucket}", json={"prefixes": paths}
        )
        response.raise_for_status()
