"""Mockups de la portada (libro, tablet, celular, pack) y su uso en los anuncios."""

import io
from functools import lru_cache
from pathlib import Path

import pytest
from PIL import Image

from app.ads.jobs import MOCKUP_BY_ANGLE, mockup_kind
from app.ads.render import AdRenderer, product_mockup
from app.ads.schemas import ImageCopy
from app.config import Settings
from app.generators.mockups import (
    MOCKUP_KINDS,
    cached_mockup,
    mockup_info,
    render_mockup,
)
from app.templates_engine.model import load_template

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = Settings(_env_file=None)
R = AdRenderer(ROOT / "ad_templates", SETTINGS.templates_dir)
BOLD = load_template(SETTINGS.templates_dir, "bold-moderno")


@lru_cache
def cover() -> bytes:
    return product_mockup(BOLD, "es-LATAM", "Guía de Alimentación Natural", "Menús simples")


def image(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png)).convert("RGBA")


@pytest.mark.parametrize("kind", MOCKUP_KINDS)
def test_every_mockup_is_a_transparent_png_that_shows_the_cover(kind: str) -> None:
    png = render_mockup(kind, cover())
    im = image(png)
    assert png.startswith(b"\x89PNG") and 400 < im.width < 2000 and 400 < im.height < 2000
    # Fondo transparente: las cuatro esquinas no pintan nada.
    corners = [(0, 0), (im.width - 1, 0), (0, im.height - 1), (im.width - 1, im.height - 1)]
    assert all(im.getpixel(c)[3] == 0 for c in corners)
    # Y hay mucho objeto opaco (no es un lienzo vacío).
    opaque = sum(1 for a in im.getchannel("A").get_flattened_data() if a > 200)
    assert opaque > 0.25 * im.width * im.height * (0.5 if kind == "bundle" else 1)
    # La portada se reconoce: el morado de «bold-moderno» aparece en el mockup.
    rgb = [px[:3] for px in im.resize((120, 120)).get_flattened_data() if px[3] > 200]
    assert any(b > 150 and r < 140 and g < 90 for r, g, b in rgb)


def test_an_unknown_mockup_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="desconocido"):
        render_mockup("poster", cover())


def test_mockups_are_cached_and_deterministic() -> None:
    assert cached_mockup("book", cover()) is cached_mockup("book", cover())
    assert render_mockup("book", cover()) == render_mockup("book", cover())


def test_info_tells_a_flat_cover_from_a_transparent_mockup() -> None:
    assert mockup_info(cover())[2] is True  # opaca: portada plana
    width, height, opaque = mockup_info(render_mockup("tablet", cover()))
    assert opaque is False and height > width


def test_the_mockup_that_goes_with_each_angle() -> None:
    assert mockup_kind({"angle": "oferta"}) == "bundle" == mockup_kind({"angle": "urgencia"})
    assert mockup_kind({"angle": "dolor"}) == "tablet"
    assert mockup_kind({"angle": "mecanismo"}) == "book" == mockup_kind({"angle": "lista"})
    assert set(MOCKUP_BY_ANGLE.values()) <= set(MOCKUP_KINDS)


COPY = ImageCopy(
    headline="Cocina natural para tu perro, sin complicarte",
    subheadline="Menús listos para la semana",
    bullets=["Recetas simples", "Lista de compras", "Guía de porciones"],
    cta_text="QUIERO EMPEZAR",
    price_text="$27",
)


@pytest.mark.parametrize("ratio", ["4x5", "9x16", "1x1"])
@pytest.mark.parametrize("kind", ["book", "tablet", "bundle"])
def test_the_ad_uses_the_real_mockup_and_stays_inside_the_safe_zone(kind: str, ratio: str) -> None:
    pdf, report = R.compose(
        template_id="product_mockup",
        copy=COPY,
        ratio=ratio,
        product_template=BOLD,
        market="es-LATAM",
        product_name="Guía",
        mockup_png=cached_mockup(kind, cover()),
    )
    assert report.outside == [] and pdf.startswith(b"%PDF")


def test_a_flat_cover_still_works_as_before() -> None:
    pdf, report = R.compose(
        template_id="product_mockup",
        copy=COPY,
        ratio="4x5",
        product_template=BOLD,
        market="es-LATAM",
        product_name="Guía",
        mockup_png=cover(),
    )
    assert report.outside == [] and pdf.startswith(b"%PDF")
