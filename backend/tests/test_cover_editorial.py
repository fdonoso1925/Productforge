"""Tapa «libro editorial» (opcional): papel claro, título grande, foto al centro y lomo."""

import io

from PIL import Image

from app.api.products import book_spine
from app.config import Settings
from app.generators.base import RenderContext, fit_cover_text
from app.generators.cover import CoverSpec, _contrast, editorial_colors, stored_spec
from app.generators.mockups import render_mockup
from app.templates_engine.model import list_templates, load_template

SETTINGS = Settings(_env_file=None)
JPEG_URI = "data:image/jpeg;base64,/9g="


def cover_html(template_id: str = "bold-moderno", **fields) -> str:
    template = load_template(SETTINGS.templates_dir, template_id)
    ctx = RenderContext(market="es-LATAM", role="main", slug="x", product_name="P", **fields)
    cover = fit_cover_text(
        {
            "title": "Guía",
            "subtitle": "sub",
            "product_name": "P",
            "promise": "frase",
            **ctx.cover_extra,
        }
    )
    return template.render_html("cover_page", c=None, ctx=ctx, cover=cover)


def test_the_design_is_optional_and_old_products_keep_the_template_one() -> None:
    assert CoverSpec().design == "template"
    assert stored_spec({"cover": {"art": "topo", "image_id": None}}).design == "template"
    assert stored_spec({"cover": {"art": "auto", "design": "editorial"}}).design == "editorial"


def test_editorial_colors_are_readable_with_every_template() -> None:
    for template in list_templates(SETTINGS.templates_dir):
        colors = editorial_colors(template.palette)
        assert _contrast(colors["ink"], colors["paper"]) >= 7, template.id
        assert _contrast(colors["gold"], colors["paper"]) >= 3, template.id
        assert colors["fade"].startswith("rgba(") and colors["fade"].endswith(",0)")


def test_the_editorial_cover_is_a_book_front_with_the_photo_in_the_middle() -> None:
    html = cover_html(cover_design="editorial", cover_photo=JPEG_URI)
    assert 'class="cover cover-ed"' in html and JPEG_URI in html
    assert 'class="ed-fade"' in html and "built-in method" not in html
    assert 'class="mockup"' not in html  # sin el libro pequeño de la plantilla
    plain = cover_html(cover_design="editorial", cover_art="<svg id='art'></svg>")
    assert 'class="ed-ring"' in plain and "id='art'" not in plain  # sin foto: emblema, no arte
    assert 'class="cover-ed' not in cover_html(cover_photo=JPEG_URI)  # por defecto, la de siempre


def test_the_own_image_wins_over_the_theme_photo() -> None:
    own = "data:image/jpeg;base64,/9j/own="
    html = cover_html(cover_design="editorial", cover_image=own, cover_photo=JPEG_URI)
    assert own in html and JPEG_URI not in html


def test_the_editorial_cover_renders_in_every_template() -> None:
    for template in list_templates(SETTINGS.templates_dir):
        assert 'class="ed-title' in cover_html(template.id, cover_design="editorial"), template.id


def product(design: str, title: str = "Desobedece") -> dict:
    return {
        "id": "x",
        "template_id": "editorial-premium",
        "cover": {"art": "auto", "image_id": None, "design": design},
        "outline": {"product_name": "Paquete " + title, "main": {"title": title}},
    }


def test_only_the_editorial_design_gets_a_spine_with_the_shortest_title() -> None:
    assert book_spine(SETTINGS.templates_dir, product("template")) is None
    spine = book_spine(SETTINGS.templates_dir, product("editorial"))
    assert spine is not None and spine.title == "Desobedece"
    assert spine.font.endswith(".ttf")


def test_the_book_mockup_shows_the_spine() -> None:
    cover = Image.new("RGB", (420, 594), "#F7F2EA")
    raw = io.BytesIO()
    cover.save(raw, "PNG")
    spine = book_spine(SETTINGS.templates_dir, product("editorial", "Un título muy largo " * 6))
    plain = Image.open(io.BytesIO(render_mockup("book", raw.getvalue())))
    with_spine = Image.open(io.BytesIO(render_mockup("book", raw.getvalue(), spine)))
    assert with_spine.width > plain.width
    assert render_mockup("bundle", raw.getvalue(), spine)  # el pack también lo dibuja
    assert render_mockup("tablet", raw.getvalue(), spine)  # el resto lo ignora


# ───────────────────── anuncios y videos usan la portada real del producto ─────────────────────


class FakeProducts:
    def __init__(self, row: dict) -> None:
        self.row = row

    async def get(self, product_id, user_id=None) -> dict:
        return self.row


def test_ads_and_videos_use_the_real_product_cover_with_its_spine() -> None:
    import asyncio
    from types import SimpleNamespace
    from uuid import uuid4

    from app.ads.jobs import batch_cover
    from app.templates_engine.model import load_template

    template = load_template(SETTINGS.templates_dir, "editorial-premium")
    row = {**product("editorial"), "market": "es-LATAM", "niche": "x"}
    row["outline"]["main"]["promise"] = "Una promesa"
    deps = SimpleNamespace(
        products=FakeProducts(row), templates_dir=SETTINGS.templates_dir, storage=None,
        images=None,
    )  # fmt: skip
    batch = {"product_id": str(uuid4()), "user_id": str(uuid4()), "market": "es-LATAM",
             "brief": {}, "template_id": "editorial-premium"}  # fmt: skip
    cover = asyncio.run(batch_cover(deps, batch, template))
    assert cover.png.startswith(b"\x89PNG") and cover.spine is not None
    assert cover.spine.title == "Desobedece"
    # La tapa de la plantilla no lleva lomo.
    deps.products = FakeProducts({**row, "cover": {"art": "auto", "design": "template"}})
    assert asyncio.run(batch_cover(deps, batch, template)).spine is None
