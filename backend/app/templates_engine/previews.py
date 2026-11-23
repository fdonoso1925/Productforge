"""Genera la miniatura de cada plantilla (portada + una página interior, lado a lado).

    uv run python -m app.templates_engine.previews [--photo foto.jpg] [id ...]

Escribe `templates/<id>/preview.png`. Correrlo al crear o modificar una plantilla. Con `--photo`,
las plantillas de «Libro editorial» muestran esa foto en la tapa (como la foto del tema).
"""

import argparse
import io
from pathlib import Path

from PIL import Image

from app.config import get_settings
from app.generators.base import RenderContext
from app.generators.pdf import render_pdf
from app.generators.render import pdf_page_to_png
from app.generators.samples import GUIDE
from app.templates_engine.model import Template, list_templates

THUMB_W = 360  # ancho de cada página en la miniatura


def preview_png(template: Template, photo: str = "") -> bytes:
    ctx = RenderContext(
        market="es-LATAM",
        role="main",
        slug="preview",
        product_name="Productos Aurora",
        cover_photo=photo if template.style.cover == "editorial" else "",
    )
    cover = {"title": GUIDE.title, "subtitle": GUIDE.subtitle, "promise": GUIDE.promise}
    pdf = render_pdf(template, "guide", ctx, GUIDE, cover)
    pages = [Image.open(io.BytesIO(pdf_page_to_png(pdf, i, THUMB_W))) for i in (0, 3)]
    gap = 16
    sheet = Image.new("RGB", (THUMB_W * 2 + gap * 3, pages[0].height + gap * 2), "#E5E7EB")
    for i, page in enumerate(pages):
        sheet.paste(page, (gap + i * (THUMB_W + gap), gap))
    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="*", help="solo estas plantillas (por defecto, todas)")
    parser.add_argument("--photo", type=Path, help="foto JPEG para las tapas de libro")
    args = parser.parse_args()
    photo = ""
    if args.photo:
        from app.generators.cover_image import data_uri

        photo = data_uri(args.photo.read_bytes())
    for template in list_templates(get_settings().templates_dir):
        if args.ids and template.id not in args.ids:
            continue
        (template.base_dir / "preview.png").write_bytes(preview_png(template, photo))
        print(f"{template.id}: ok")


if __name__ == "__main__":
    main()
