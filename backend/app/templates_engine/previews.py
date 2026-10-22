"""Genera la miniatura de cada plantilla (portada + una página interior, lado a lado).

    uv run python -m app.templates_engine.previews

Escribe `templates/<id>/preview.png`. Correrlo al crear o modificar una plantilla.
"""

import io

from PIL import Image

from app.config import get_settings
from app.generators.base import RenderContext
from app.generators.pdf import render_pdf
from app.generators.render import pdf_page_to_png
from app.generators.samples import GUIDE
from app.templates_engine.model import Template, list_templates

THUMB_W = 360  # ancho de cada página en la miniatura


def preview_png(template: Template) -> bytes:
    ctx = RenderContext(
        market="es-LATAM", role="main", slug="preview", product_name="Productos Aurora"
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
    for template in list_templates(get_settings().templates_dir):
        (template.base_dir / "preview.png").write_bytes(preview_png(template))
        print(f"{template.id}: ok")


if __name__ == "__main__":
    main()
