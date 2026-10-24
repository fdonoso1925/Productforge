"""Pixabay: fotos de stock gratis. https://pixabay.com/api/docs/

Términos que se respetan: la imagen se DESCARGA a nuestro storage (nada de hotlinking
permanente), las búsquedas se cachean 24 h, límite de 100 peticiones/60 s, `safesearch`, y se
guarda quién la hizo y su licencia. En temas sensibles no se usan fotos con personas.
"""

import time
from typing import ClassVar
from urllib.parse import urlparse

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
TRUSTED_HOST = "pixabay.com"
LARGE_SIDE = 1280  # `largeImageURL` mide como mucho esto en su lado largo
MIN_CROP_WIDTH = 720  # igual que el recorte del router: menos se ve pixelado a 1080 px
VARIETY = 5  # se elige entre las N mejores: dos anuncios con la misma búsqueda no repiten foto
RATIO = {"4:5": (4, 5), "9:16": (9, 16), "1:1": (1, 1)}


def fits_aspect(hit: dict, aspect: str) -> bool:
    """¿Alcanza la foto (en su versión grande) para recortarla a este formato sin pixelarse?"""
    try:
        width, height = int(hit["imageWidth"]), int(hit["imageHeight"])
    except (KeyError, TypeError, ValueError):
        return True  # sin medidas no se puede saber: el router igual valida al recortar
    if width <= 0 or height <= 0 or aspect not in RATIO:
        return False
    scale = min(1.0, LARGE_SIDE / max(width, height))
    w, h = RATIO[aspect]
    return min(width * scale, height * scale * w / h) >= MIN_CROP_WIDTH


def trusted_image_url(url: object) -> bool:
    """Solo se descarga de pixabay.com por https: la URL viene en la respuesta de la API y no se
    debe poder usar para que el servidor llame a otro lado (SSRF)."""
    if not isinstance(url, str):
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and parsed.port in (None, 443)
        and not parsed.username
        and (host == TRUSTED_HOST or host.endswith("." + TRUSTED_HOST))
    )


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
        usable = [h for h in hits if trusted_image_url(h.get("largeImageURL"))]
        if request.sensitive:
            usable = [h for h in usable if not self.has_people(h)]
        usable = [h for h in usable if fits_aspect(h, request.aspect)]
        if not usable:
            raise ProviderRejected("Pixabay no tiene fotos adecuadas")
        # Determinista (misma escena → misma foto, así se puede cachear) pero variado entre escenas.
        hit = usable[int(request.scene_hash("photo")[:8], 16) % min(len(usable), VARIETY)]
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
