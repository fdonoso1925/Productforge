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


def video_filename(*, product_name: str, market: str, angle: str, ratio: str, version: int) -> str:
    """`<producto>_<mercado>_<angulo>_video_<ratio>_v<n>.mp4`: el mismo nombre del anuncio en Meta
    (así lo empareja también el CSV de resultados)."""
    return (
        creative_filename(
            product_name=product_name,
            market=market,
            angle=angle,
            template_id="video",
            ratio=ratio,
            version=version,
        ).removesuffix(".png")
        + ".mp4"
    )


def video_path(user_id: UUID | str, batch_id: UUID | str, filename: str) -> str:
    return f"{user_id}/ads/{batch_id}/videos/{filename}"


def storage_path(
    user_id: UUID | str, batch_id: UUID | str, ratio_folder: str, filename: str
) -> str:
    """Misma convención que el resto de archivos: la carpeta raíz es el usuario."""
    return f"{user_id}/ads/{batch_id}/{ratio_folder}/{filename}"
