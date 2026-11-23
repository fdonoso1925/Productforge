"""Foto del tema en la tapa del libro de la portada: opcional, la propone la IA en el outline."""

import asyncio
from uuid import uuid4

from app.config import Settings
from app.content import rules
from app.content.schemas.formats import PhotoSpec
from app.generators.base import RenderContext, fit_cover_text
from app.pipeline.package import cover_photo_uri
from app.templates_engine.model import load_template
from tests.fakes import make_outline, make_request
from tests.test_visuals import FakeRouter, builder_with

SETTINGS = Settings(_env_file=None)
PHOTO = PhotoSpec(scene="homemade dog food in a bowl", keywords=["dog food", "bowl"])
JPEG_URI = "data:image/jpeg;base64,/9g="


def with_photo(item, photo=PHOTO):
    return item.model_copy(update={"cover_photo": photo})


# ───────────────────────────── reglas del outline ─────────────────────────────


def test_the_cover_photo_is_optional_and_checked_when_present() -> None:
    outline = make_outline()
    request = make_request()
    assert rules.check_package_rules(outline, request) == []  # sin foto: válido
    good = outline.model_copy(update={"main": with_photo(outline.main)})
    assert rules.check_package_rules(good, request) == []
    bad_photo = PhotoSpec(scene="dog", keywords=["dog"])
    bad = outline.model_copy(update={"main": with_photo(outline.main, bad_photo)})
    errors = rules.check_package_rules(bad, request)
    assert any("main.cover_photo" in e and "2 o 3" in e for e in errors)


# ───────────────────────────── búsqueda de la foto ─────────────────────────────


def test_the_photo_is_searched_wide_curated_and_with_the_piece_as_context() -> None:
    router = FakeRouter()
    item = with_photo(make_outline().main)
    uri = asyncio.run(cover_photo_uri(router, uuid4(), item, "mascotas"))
    assert uri.startswith("data:image/jpeg;base64,")
    [request] = router.requests
    assert request.aspect == "16:9" and request.curate is True
    assert request.keywords == ("dog food", "bowl") and item.title in request.context


def test_no_photo_means_the_usual_cover_and_nothing_breaks() -> None:
    item = make_outline().main
    assert asyncio.run(cover_photo_uri(FakeRouter(), uuid4(), item, "x")) == ""  # no la pidió
    asked = with_photo(item)
    assert asyncio.run(cover_photo_uri(None, uuid4(), asked, "x")) == ""  # sin proveedor
    assert asyncio.run(cover_photo_uri(FakeRouter(active=False), uuid4(), asked, "x")) == ""
    failing = FakeRouter(fail={"dog food"})
    assert asyncio.run(cover_photo_uri(failing, uuid4(), asked, "x")) == ""  # sin cuota


def test_sensitive_niches_ask_for_photos_without_recognizable_people() -> None:
    router = FakeRouter()
    asyncio.run(cover_photo_uri(router, uuid4(), with_photo(make_outline().main), "maternidad"))
    assert router.requests[0].sensitive is True


def test_the_package_builder_passes_the_photo_to_the_cover() -> None:
    builder = builder_with(FakeRouter())
    builder.outline = builder.outline.model_copy(update={"main": with_photo(builder.outline.main)})
    fields = asyncio.run(builder.cover_fields({"role": "main", "order": 0}))
    assert fields["cover_photo"].startswith("data:image/jpeg;base64,")
    bump = asyncio.run(builder.cover_fields({"role": "order_bump", "order": 0}))
    assert "cover_photo" not in bump  # la pieza que no la pidió sale como siempre


# ───────────────────────────── dibujo en la portada ─────────────────────────────


def cover_html(photo: str, template_id: str = "editorial-premium") -> str:
    template = load_template(SETTINGS.templates_dir, template_id)
    ctx = RenderContext(
        market="es-LATAM", role="main", slug="x", product_name="P", cover_photo=photo
    )
    cover = fit_cover_text(
        {"title": "Guía", "subtitle": "s", "product_name": "P", "promise": "", **ctx.cover_extra}
    )
    return template.render_html("cover_page", c=None, ctx=ctx, cover=cover)


def test_with_a_photo_the_book_shows_it_on_top_and_without_it_keeps_its_design() -> None:
    html = cover_html(JPEG_URI)
    assert 'class="mk-photo"' in html and JPEG_URI in html and "with-photo" in html
    plain = cover_html("")
    assert 'class="mk-photo"' not in plain and 'class="mk-shape"' in plain


def test_every_cover_style_can_show_the_photo() -> None:
    for template_id in ("bold-moderno", "corporativo-pro", "minimal-clean", "notebook-cuaderno"):
        assert JPEG_URI in cover_html(JPEG_URI, template_id), template_id
