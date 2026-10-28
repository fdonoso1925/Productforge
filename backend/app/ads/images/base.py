"""Contrato de los proveedores de imagen: agregar uno es una clase y una variable de entorno."""

import hashlib
from dataclasses import dataclass, field
from typing import ClassVar, Protocol

Aspect = str  # "4:5" | "9:16" | "1:1"

NEGATIVE_PROMPT = (
    "text, letters, words, watermark, logo, brand names, trademarks, user interface, "
    "recognizable faces, celebrities"
)


class ProviderError(Exception):
    """Un proveedor no pudo atender la petición; el router prueba el siguiente."""


class ProviderQuota(ProviderError):
    """Cuota o límite agotado: el proveedor queda fuera por hoy."""


class ProviderRejected(ProviderError):
    """El proveedor rechazó este prompt o no tiene nada adecuado (se puede probar con otro)."""


@dataclass(frozen=True)
class ImageRequest:
    prompt: str  # escena en inglés para los generadores
    keywords: tuple[str, ...]  # 2-3 palabras clave en inglés para los buscadores de stock
    aspect: Aspect
    sensitive: bool = False  # salud, deudas, maternidad…: sin rostros reconocibles
    style: str | None = None
    curate: bool = False  # un modelo elige entre las candidatas la que muestra la escena
    context: str = ""  # dónde se usa la foto (para el curador)
    negative_prompt: str = NEGATIVE_PROMPT

    def scene_hash(self, user_id: object) -> str:
        """Clave de caché: la misma escena del mismo usuario no se vuelve a pedir."""
        raw = "|".join(
            [
                str(user_id),
                self.prompt.strip().lower(),
                ",".join(k.strip().lower() for k in self.keywords),
                self.aspect,
                str(self.sensitive),
                self.style or "",
            ]
            + (["curated"] if self.curate else [])
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:40]


@dataclass
class ProviderImage:
    data: bytes
    mime: str
    provider: str
    cost_usd: float = 0.0
    credit: dict = field(default_factory=dict)  # id, autor, URL de la página y licencia


class ImageProvider(Protocol):
    name: ClassVar[str]
    kind: ClassVar[str]  # "generate" (de pago) | "search" (stock gratis)

    def enabled(self) -> bool: ...

    def unit_cost(self) -> float:
        """Costo estimado de una petición, para comprobar el tope diario antes de llamar."""
        ...

    async def fetch(self, request: ImageRequest) -> ProviderImage: ...
