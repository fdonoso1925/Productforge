"""La portada real del producto principal (tal como sale en el paquete) y el lomo de su libro.

Una sola fuente para todo lo que muestra el producto fuera del PDF: los mockups del paquete, las
imágenes de los anuncios y los videos (motion graphics y Lemo). Así todos llevan el mismo diseño
que eligió el usuario: tapa «Libro editorial» o la de la plantilla, foto del tema, imagen propia
o arte, y el lomo con el título cuando la tapa es editorial.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.content.schemas import ItemOutline
from app.generators.base import RenderContext
from app.generators.cover import (
    art_for_piece,
    editorial_colors,
    editorial_variant,
    image_path,
    is_editorial,
    stored_spec,
    veil_for,
)
from app.generators.cover_image import data_uri
from app.generators.epub import cover_png
from app.generators.mockups import Spine
from app.pipeline.package import cover_photo_uri
from app.templates_engine.model import load_template
from app.video.style import fonts_from

logger = logging.getLogger("productforge.cover")


def book_spine(templates_dir: Path, product: dict) -> Spine | None:
    """Con la portada editorial, el libro del mockup muestra su lomo con el título (el más corto
    entre el nombre del paquete y el de la pieza principal, para que quepa)."""
    template = load_template(templates_dir, product["template_id"])
    if not is_editorial(template, stored_spec(product)):
        return None
    outline = product.get("outline") or {}
    names = [
        n for n in ((outline.get("main") or {}).get("title"), outline.get("product_name")) if n
    ]
    colors = editorial_colors(template.palette, editorial_variant(template))
    return Spine(
        title=min(names, key=len) if names else (product.get("title") or ""),
        paper=colors["spine"],
        ink=colors["ink"],
        gold=colors["gold"],
        font=str(fonts_from(template, templates_dir).heading),
    )


async def product_cover_png(
    product: dict,
    user_id: UUID,
    *,
    templates_dir: Path,
    storage: Any,
    images: Any = None,
    width: int = 900,
) -> bytes:
    """PNG de la portada del producto principal con su diseño (arte, imagen propia, foto del
    tema, tapa editorial). `images` = ImageRouter para la foto del tema (None = sin foto)."""
    template = await asyncio.to_thread(load_template, templates_dir, product["template_id"])
    spec = stored_spec(product)
    outline = product.get("outline") or {}
    main = outline.get("main") or {}
    title = main.get("title") or product.get("title") or outline.get("product_name") or "Producto"
    promise = main.get("promise") or ""
    fields: dict = {}
    if spec.image_id is not None:
        try:
            raw = await storage.download(image_path(user_id, spec.image_id))
            fields = {
                "cover_image": data_uri(raw),
                "cover_veil": await asyncio.to_thread(veil_for, raw, template),
            }
        except Exception:
            logger.warning("portada: no se pudo cargar la imagen propia; se usa el arte")
    if not fields:
        _, art = art_for_piece(spec, product, template, "main", 0)
        fields = {"cover_art": art}
    if main.get("cover_photo"):
        # La misma foto del tema que lleva la portada del paquete (si el outline la pidió).
        try:
            item = ItemOutline.model_validate(main)
        except ValidationError:
            item = None
        photo = (
            await cover_photo_uri(images, user_id, item, product.get("niche") or "") if item else ""
        )
        if photo:
            fields["cover_photo"] = photo
    if spec.design == "editorial":
        fields["cover_design"] = "editorial"
    ctx = RenderContext(
        market=product["market"],
        role="main",
        slug="mockup",
        product_name=outline.get("product_name") or title,
        promise=promise,
        **fields,
    )
    cover = {"title": title, "subtitle": promise[:140]}
    return await asyncio.to_thread(cover_png, template, ctx, cover, width)
