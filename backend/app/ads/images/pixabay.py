"""Pixabay: fotos de stock gratis. https://pixabay.com/api/docs/

Términos que se respetan: la imagen se DESCARGA a nuestro storage (nada de hotlinking
permanente), las búsquedas se cachean 24 h, límite de 100 peticiones/60 s, `safesearch`, y se
guarda quién la hizo y su licencia. En temas sensibles no se usan fotos con personas.
"""

import time
from typing import ClassVar

import httpx

from app.ads.images.base import (
    ImageRequest,
    ProviderError,
    ProviderImage,
    ProviderQuota,
    ProviderRejected,
)

API = "https://pixabay.com/api/"
SEARCH_TTL = 24 * 3600
RATE_LIMIT = 90  # de 100 por minuto: deja margen
MIN_WIDTH = 1080
MAX_DOWNLOAD = 15 * 1024 * 1024
PEOPLE_TAGS = {
    "people", "person", "man", "woman", "men", "women", "girl", "boy", "child", "children",
    "kid", "baby", "face", "portrait", "couple", "family", "mother", "father", "mom", "dad",
    "student", "doctor", "patient", "model", "selfie", "crowd", "team", "hand", "hands",
}  # fmt: skip
ORIENTATION = {"4:5": "vertical", "9:16": "vertical", "1:1": "all"}


class PixabayProvider:
    name: ClassVar[str] = "pixabay"
    kind: ClassVar[str] = "search"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        self._key = api_key
        self._client = client or httpx.AsyncClient(timeout=20, follow_redirects=False)
        self._searches: dict[tuple, tuple[float, list[dict]]] = {}
        self._calls: list[float] = []

    def enabled(self) -> bool:
        return bool(self._key)

    def unit_cost(self) -> float:
        return 0.0

    def _throttle(self) -> None:
        now = time.monotonic()
        self._calls = [t for t in self._calls if now - t < 60]
        if len(self._calls) >= RATE_LIMIT:
            raise ProviderQuota("límite de Pixabay por minuto")
        self._calls.append(now)

    async def _search(self, request: ImageRequest) -> list[dict]:
        query = " ".join(request.keywords)[:100]
        key = (query, request.aspect)
        cached = self._searches.get(key)
        if cached and time.monotonic() - cached[0] < SEARCH_TTL:
            return cached[1]
        self._throttle()
        response = await self._client.get(
            API,
            params={
                "key": self._key,
                "q": query,
                "image_type": "photo",
                "orientation": ORIENTATION.get(request.aspect, "all"),
                "safesearch": "true",
                "min_width": MIN_WIDTH,
                "order": "popular",
                "per_page": 30,
            },
        )
        if response.status_code == 429:
            raise ProviderQuota("Pixabay 429")
        if response.status_code != 200:
            raise ProviderError(f"Pixabay {response.status_code}")
        hits = response.json().get("hits", [])
        self._searches[key] = (time.monotonic(), hits)
        return hits

    @staticmethod
    def has_people(hit: dict) -> bool:
        words = {w for t in str(hit.get("tags", "")).lower().split(",") for w in t.split()}
        return bool(words & PEOPLE_TAGS)

    async def fetch(self, request: ImageRequest) -> ProviderImage:
        if not request.keywords:
            raise ProviderRejected("sin palabras clave")
        hits = await self._search(request)
        usable = [h for h in hits if h.get("largeImageURL")]
        if request.sensitive:
            usable = [h for h in usable if not self.has_people(h)]
        if not usable:
            raise ProviderRejected("Pixabay no tiene fotos adecuadas")
        hit = usable[0]
        self._throttle()
        async with self._client.stream("GET", hit["largeImageURL"]) as response:
            if response.status_code != 200:
                raise ProviderError(f"descarga de Pixabay {response.status_code}")
            mime = response.headers.get("content-type", "image/jpeg").split(";")[0]
            data = b""
            async for chunk in response.aiter_bytes():
                data += chunk
                if len(data) > MAX_DOWNLOAD:
                    raise ProviderRejected("imagen demasiado grande")
        return ProviderImage(
            data=data,
            mime=mime,
            provider=self.name,
            credit={
                "provider": self.name,
                "id": hit.get("id"),
                "author": hit.get("user"),
                "page_url": hit.get("pageURL"),
                "license": "Pixabay Content License",
            },
        )
