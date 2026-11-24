"""Imágenes de la página de ventas: fotos de stock del tema y mockups del producto.

Se resuelven UNA vez, en el job que escribe la página (las fotos tienen caché y tope diario), se
guardan en Storage (`<user>/pages/<página>/<clave>.<ext>`) y la columna `sales_pages.assets` guarda
las rutas. Al mostrar o exportar, cada imagen se incrusta como data URI: la página sigue siendo
un único HTML sin recursos externos.

- `hero` / `problem`: foto de stock (Pixabay, licencia libre) con la escena que propuso la IA.
- `bundle` / `book`: mockups de la portada REAL del producto (con su lomo si la tapa es editorial),
  solo si la página viene de un paquete.

Nada de esto es obligatorio: sin proveedor, sin cuota, sin paquete o si algo falla, la página sale
igual (con sus infografías).
"""

import asyncio
import base64
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from app.ads import rules as ad_rules
from app.ads.images.base import ImageRequest
from app.content.schemas.formats import PhotoSpec
from app.generators.mockups import render_mockup
from app.pages.schemas import PageBrief, PageContent

logger = logging.getLogger("productforge.pages")

PHOTO_KEYS = ("hero", "problem")
MOCKUP_KEYS = ("bundle", "book")
MIME = {"jpg": "image/jpeg", "png": "image/png"}


def asset_path(user_id: UUID | str, page_id: str, key: str) -> str:
    ext = "png" if key in MOCKUP_KEYS else "jpg"
    return f"{user_id}/pages/{page_id}/{key}.{ext}"


async def _photo(images: Any, user_id: UUID, spec: PhotoSpec, brief: PageBrief) -> bytes | None:
    try:
        routed = await images.get(
            user_id=user_id,
            request=ImageRequest(
                prompt=spec.scene,
                keywords=tuple(k for k in spec.keywords if k.strip())[:3],
                aspect="16:9",
                sensitive=ad_rules.is_sensitive(brief.niche),
                curate=True,
                context=f"sales page of «{brief.product_name}»: {brief.promise}",
            ),
        )
    except Exception:
        logger.warning("página: no se pudo traer la foto «%s»", spec.scene[:60])
        return None
    return routed.jpeg if routed is not None else None


async def resolve_assets(
    page: dict,
    content: PageContent,
    brief: PageBrief,
    *,
    user_id: UUID,
    images: Any = None,
    storage: Any = None,
    products: Any = None,
    templates_dir: Path | None = None,
) -> dict[str, str]:
    """Busca, guarda y devuelve {clave: ruta en Storage} de las imágenes de la página."""
    if storage is None:
        return {}
    found: dict[str, tuple[bytes, str]] = {}
    if images is not None and images.active():
        for key, spec in (("hero", content.hero_photo), ("problem", content.problem_photo)):
            if spec is not None:
                jpeg = await _photo(images, user_id, spec, brief)
                if jpeg:
                    found[key] = (jpeg, MIME["jpg"])
    if page.get("product_id") and products is not None and templates_dir is not None:
        from app.pipeline.product_cover import book_spine, product_cover_png

        try:
            product = await products.get(UUID(page["product_id"]), user_id)
            if product.get("outline"):
                cover = await product_cover_png(
                    product, user_id, templates_dir=templates_dir, storage=storage, images=images
                )
                spine = await asyncio.to_thread(book_spine, templates_dir, product)
                for key in MOCKUP_KEYS:
                    png = await asyncio.to_thread(render_mockup, key, cover, spine)
                    found[key] = (png, MIME["png"])
        except Exception:
            logger.warning("página: no se pudieron armar los mockups del producto")
    assets: dict[str, str] = {}
    for key, (data, mime) in found.items():
        path = asset_path(user_id, page["id"], key)
        try:
            await storage.upload(path, data, mime)
        except Exception:
            logger.warning("página: no se pudo guardar la imagen %s", key)
            continue
        assets[key] = path
    return assets


async def asset_uris(storage: Any, assets: dict | None) -> dict[str, str]:
    """{clave: data URI} de las imágenes guardadas; la que falte, simplemente no aparece."""
    out: dict[str, str] = {}
    for key, path in (assets or {}).items():
        if key not in (*PHOTO_KEYS, *MOCKUP_KEYS) or not isinstance(path, str):
            continue
        try:
            data = await storage.download(path)
        except Exception:
            logger.warning("página: falta la imagen %s en Storage", key)
            continue
        mime = MIME["png"] if path.endswith(".png") else MIME["jpg"]
        out[key] = f"data:{mime};base64,{base64.b64encode(data).decode()}"
    return out
