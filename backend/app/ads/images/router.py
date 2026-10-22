"""Router de proveedores de imagen: caché por escena, tope diario y reserva automática.

Orden de decisión para una escena:
1. Caché (misma escena del mismo usuario): no se llama a nadie ni se gasta nada.
2. Cada proveedor activo en el orden configurado. Uno de pago se salta si hoy ya llegó a su tope
   en USD; un 429 o de cuota lo deja fuera por el resto del día. Si falla, se prueba el siguiente.
3. Si ninguno puede, devuelve None y el anuncio se compone con una plantilla sin imagen: el lote
   nunca se cae por falta de imágenes.
"""

import io
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from PIL import Image, ImageOps

from app.ads.images.base import (
    ImageProvider,
    ImageRequest,
    ProviderError,
    ProviderImage,
    ProviderQuota,
)
from app.ads.images.gemini import GeminiImageProvider
from app.ads.images.pixabay import PixabayProvider
from app.config import Settings

logger = logging.getLogger("productforge.ads.images")

OUT_WIDTH = 1080
MIN_CROP_WIDTH = 720  # menos que esto se ve pixelado al subirlo a 1080
MAX_PIXELS = 40_000_000
ALLOWED = {"JPEG", "PNG", "WEBP"}
ASPECTS = {"4:5": (4, 5), "9:16": (9, 16), "1:1": (1, 1)}


class UnusableImage(ProviderError):
    """La imagen no sirve (formato raro, demasiado chica): se prueba otro proveedor."""


def fit_image(data: bytes, aspect: str) -> bytes:
    """Recorta la imagen a la proporción del anuncio, a 1080 px de ancho, como JPEG sin EXIF."""
    if aspect not in ASPECTS:
        raise UnusableImage(f"formato desconocido {aspect}")
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise UnusableImage("no es una imagen válida") from exc
    if image.format not in ALLOWED or image.width * image.height > MAX_PIXELS:
        raise UnusableImage("formato o tamaño no permitido")
    w, h = ASPECTS[aspect]
    # El recorte más grande con esa proporción: si es muy chico, la foto no alcanza.
    crop_w = min(image.width, image.height * w // h)
    if crop_w < MIN_CROP_WIDTH:
        raise UnusableImage("resolución insuficiente")
    out = ImageOps.fit(
        ImageOps.exif_transpose(image).convert("RGB"),
        (OUT_WIDTH, OUT_WIDTH * h // w),
        Image.Resampling.LANCZOS,
    )
    buffer = io.BytesIO()
    out.save(buffer, format="JPEG", quality=88, optimize=True)
    return buffer.getvalue()


@dataclass
class RoutedImage:
    jpeg: bytes
    provider: str
    credit: dict
    storage_path: str
    cost_usd: float = 0.0
    from_cache: bool = False


class ImageRouter:
    def __init__(
        self, providers: list[ImageProvider], cache: Any, usage: Any, storage: Any
    ) -> None:
        self.providers = providers
        self._cache, self._usage, self._storage = cache, usage, storage

    @staticmethod
    def today() -> date:
        return datetime.now(UTC).date()

    def active(self) -> list[str]:
        return [p.name for p in self.providers if p.enabled()]

    async def _within_budget(self, provider: ImageProvider, day: date) -> bool:
        cost = provider.unit_cost()
        if cost <= 0:
            row = await self._usage.get(provider.name, day)
            return not (row and row.get("exhausted"))
        row = await self._usage.get(provider.name, day) or {}
        if row.get("exhausted"):
            return False
        cap = getattr(provider, "daily_cap", 0.0)
        return float(row.get("cost_usd") or 0) + cost <= cap

    async def get(self, *, user_id: UUID, request: ImageRequest) -> RoutedImage | None:
        key = request.scene_hash(user_id)
        cached = await self._cache.get(key)
        if cached:
            try:
                jpeg = await self._storage.download(cached["storage_path"])
                return RoutedImage(
                    jpeg, cached["provider"], cached.get("credit") or {}, cached["storage_path"],
                    from_cache=True,
                )  # fmt: skip
            except Exception:
                logger.warning("imagen en caché ilegible; se vuelve a pedir")
        day = self.today()
        for provider in self.providers:
            if not provider.enabled() or not await self._within_budget(provider, day):
                continue
            try:
                raw: ProviderImage = await provider.fetch(request)
                jpeg = fit_image(raw.data, request.aspect)
            except ProviderQuota:
                logger.warning("%s sin cuota por hoy; sigo con el siguiente", provider.name)
                await self._usage.mark_exhausted(provider.name, day)
                continue
            except ProviderError as exc:
                logger.warning("%s no pudo: %s", provider.name, exc)
                continue
            except Exception:
                logger.exception("%s falló de forma inesperada", provider.name)
                continue
            await self._usage.add(provider.name, day, requests=1, cost_usd=raw.cost_usd)
            path = f"{user_id}/ads/_images/{key}.jpg"
            await self._storage.upload(path, jpeg, "image/jpeg")
            await self._cache.put(
                {
                    "scene_hash": key,
                    "provider": raw.provider,
                    "storage_path": path,
                    "credit": raw.credit,
                }
            )
            return RoutedImage(jpeg, raw.provider, raw.credit, path, raw.cost_usd)
        return None


def build_router(settings: Settings, cache: Any, usage: Any, storage: Any) -> ImageRouter:
    """Arma los proveedores en el orden de `IMAGE_PROVIDERS`; los desconocidos se ignoran."""
    available: dict[str, ImageProvider] = {
        "pixabay": PixabayProvider(settings.pixabay_api_key),
        "gemini": GeminiImageProvider(
            settings.gemini_api_key,
            settings.gemini_image_model,
            settings.gemini_image_price_usd,
            settings.gemini_daily_usd_cap,
        ),
    }
    ordered = [available[n] for n in settings.image_providers if n in available]
    return ImageRouter(ordered, cache, usage, storage)
