"""Esqueletos documentados: así se agrega otro proveedor sin tocar el router.

1. Una clase con `name`, `kind`, `enabled()`, `unit_cost()` y `async fetch(request)`.
2. Registrarla en `build_router` (`app/ads/images/router.py`).
3. Su clave y su tope en `Settings` y `.env.example`, y su nombre en `IMAGE_PROVIDERS`.
"""

from typing import ClassVar

from app.ads.images.base import ImageRequest, ProviderImage


class PexelsProvider:
    """Pexels pausó la emisión de claves nuevas. Se implementaría igual que `PixabayProvider`."""

    name: ClassVar[str] = "pexels"
    kind: ClassVar[str] = "search"

    def enabled(self) -> bool:
        return False

    def unit_cost(self) -> float:
        return 0.0

    async def fetch(self, request: ImageRequest) -> ProviderImage:
        raise NotImplementedError("PexelsProvider es un esqueleto")


class OpenAIImageProvider:
    """Generación de pago (gpt-image). Mismo patrón que `GeminiImageProvider`."""

    name: ClassVar[str] = "openai"
    kind: ClassVar[str] = "generate"

    def enabled(self) -> bool:
        return False

    def unit_cost(self) -> float:
        return 0.0

    async def fetch(self, request: ImageRequest) -> ProviderImage:
        raise NotImplementedError("OpenAIImageProvider es un esqueleto")
