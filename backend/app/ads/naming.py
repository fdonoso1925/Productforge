"""Nombres y rutas de los creativos: `<producto>_<mercado>_<angulo>_<plantilla>_<ratio>_v<n>`."""

from uuid import UUID

from app.generators.base import slugify

MARKET_SLUG = {"pt-BR": "pt-br", "es-LATAM": "es-latam"}


def creative_filename(
    *, product_name: str, market: str, angle: str, template_id: str, ratio: str, version: int
) -> str:
    parts = [
        slugify(product_name, 40),
        MARKET_SLUG.get(market, slugify(market, 12)),
        slugify(angle, 30),
        slugify(template_id, 30).replace("-", ""),  # `headline_bold` → `headlinebold`
        ratio,
        f"v{version}",
    ]
    return "_".join(parts) + ".png"


def storage_path(
    user_id: UUID | str, batch_id: UUID | str, ratio_folder: str, filename: str
) -> str:
    """Misma convención que el resto de archivos: la carpeta raíz es el usuario."""
    return f"{user_id}/ads/{batch_id}/{ratio_folder}/{filename}"
