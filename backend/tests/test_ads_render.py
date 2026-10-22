"""Módulo Creativos, fase 3: composición de anuncios con WeasyPrint (tamaños, márgenes, texto)."""

import io
from functools import lru_cache
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image

from app.ads import render as ads_render
from app.ads.render import (
    SHRINKS,
    AdRenderer,
    content_outside_safe_zone,
    font_sizes,
    product_mockup,
    readable,
    scheme_colors,
)
from app.ads.schemas import TEMPLATE_IDS, ImageCopy
from app.config import Settings
from app.generators.cover_image import contrast, hex_rgb, luminance
from app.templates_engine.model import list_templates, load_template

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = Settings(_env_file=None)
R = AdRenderer(ROOT / "ad_templates", SETTINGS.templates_dir)
PRODUCT_TEMPLATES = list_templates(SETTINGS.templates_dir)
BOLD = load_template(SETTINGS.templates_dir, "bold-moderno")
SIZES = {"4x5": (1080, 1350), "9x16": (1080, 1920), "1x1": (1080, 1080)}
TEMPLATES = ["headline_bold", "product_mockup", "checklist", "note"]


def copy(**over) -> ImageCopy:
    data = {
        "headline": "Pedidos ordenados en una sola lista",
        "subheadline": "Un método simple para no perder fechas",
        "kicker": "Método en 7 días",
        "bullets": ["Un solo lugar para todo", "Responsable y fecha", "Revisión semanal"],
        "cta_text": "Quiero ordenarme",
        "price_text": "USD 12",
        "note": "Anoté mis pedidos en un solo lugar y por fin sé qué entrego primero",
    }
    return ImageCopy(**{**data, **over})


@lru_cache
def mockup() -> bytes:
    return product_mockup(BOLD, "es-LATAM", "Bandeja Única", "Un método simple")


def compose(template="headline_bold", ratio="4x5", product=BOLD, **over):
    return R.compose(
        template_id=template,
        copy=over.pop("copy", copy()),
        ratio=ratio,
        product_template=product,
        market="es-LATAM",
        product_name="Bandeja Única",
        mockup_png=mockup() if template == "product_mockup" else None,
        **over,
    )


def pdf_text(pdf: bytes) -> str:
    document = pdfium.PdfDocument(pdf)
    try:
        return document[0].get_textpage().get_text_range()
    finally:
        document.close()


# ───────────────────────────── specs de Meta ─────────────────────────────


def test_specs_are_read_from_a_config_file() -> None:
    assert {k: (r.width, r.height) for k, r in R.ratios.items()} == SIZES
    assert R.specs["max_file_mb"] == 30 and R.specs["hires_scale"] == pytest.approx(1.3333)
    assert R.ratios["9x16"].pad["top"] == round(1920 * 0.14)
    assert R.ratios["9x16"].pad["bottom"] == round(1920 * 0.35)  # Stories y Reels tapan abajo
    assert R.ratios["4x5"].folder == "feed-4x5" and R.ratios["9x16"].folder == "stories-9x16"
    assert "Ads Guide oficial" in R.specs["_nota"]  # verificados contra la guía de Meta


def test_the_twelve_templates_exist_and_only_the_photo_one_needs_an_image() -> None:
    assert set(R.available_ids()) == set(TEMPLATE_IDS) and len(R.templates) == 12
    assert {t.id for t in R.templates.values() if t.uses_image} == {"photo_headline"}
    assert R.templates["product_mockup"].uses_mockup


# ───────────────────────────── tamaños y márgenes seguros ─────────────────────────────


@pytest.mark.parametrize("ratio", SIZES)
@pytest.mark.parametrize("template", TEMPLATES)
def test_every_template_renders_at_the_exact_meta_size_within_the_safe_zone(
    template: str, ratio: str
) -> None:
    png, report = R.render_with_report(
        template_id=template,
        copy=copy(),
        ratio=ratio,
        product_template=BOLD,
        market="es-LATAM",
        product_name="Bandeja Única",
        mockup_png=mockup() if template == "product_mockup" else None,
    )
    image = Image.open(io.BytesIO(png))
    assert image.size == SIZES[ratio] and image.format == "PNG"
    assert report.outside == []  # ningún texto ni imagen invade el margen seguro
    assert len(png) < R.specs["max_file_mb"] * 1024 * 1024


@pytest.mark.parametrize("ratio", SIZES)
def test_hires_export_scales_the_size(ratio: str) -> None:
    png, _ = R.render_with_report(
        template_id="headline_bold",
        copy=copy(),
        ratio=ratio,
        product_template=BOLD,
        market="es-LATAM",
        hires=True,
    )
    w, h = SIZES[ratio]
    assert Image.open(io.BytesIO(png)).size == (1440, round(h * 1440 / w))


def test_stories_text_stays_out_of_the_top_and_bottom_ui_bands() -> None:
    pdf, _ = compose("headline_bold", "9x16")
    document = pdfium.PdfDocument(pdf)
    try:
        page = document[0]
        height_pt = page.get_height()
        textpage = page.get_textpage()
        tops, bottoms = [], []
        for i in range(textpage.count_rects()):
            _, y_min, _, y_max = textpage.get_rect(i)
            tops.append((height_pt - y_max) / 0.75)
            bottoms.append((height_pt - y_min) / 0.75)
    finally:
        document.close()
    assert min(tops) >= 1920 * 0.14 - 1  # nada en el 14 % superior
    assert max(bottoms) <= 1920 * (1 - 0.35) + 1  # ni en el 35 % inferior


def test_long_headlines_shrink_to_fit_instead_of_overflowing() -> None:
    long = copy(
        headline="Un sistema completo para ordenar tus pedidos del mes sin perder fechas",
        subheadline="Un método simple para organizar el trabajo de tu negocio sin complicarte",
    )
    _, report = R.render_with_report(
        template_id="product_mockup",
        copy=long,
        ratio="9x16",
        product_template=BOLD,
        market="es-LATAM",
        mockup_png=mockup(),
    )
    assert report.outside == [] and report.shrink < 1.0  # se redujo hasta que cupo
    _, tight = R.render_with_report(
        template_id="headline_bold",
        copy=copy(),
        ratio="4x5",
        product_template=BOLD,
        market="es-LATAM",
    )
    assert tight.shrink == 1.0  # un texto normal no se toca


def test_the_overflow_check_actually_detects_content_outside_the_zone() -> None:
    pdf, _ = compose("headline_bold", "9x16")
    wider = ads_render.RatioSpec("x", "x", 1080, 1920, 0.45, 0.45, 0.06, "x")  # margen enorme
    assert content_outside_safe_zone(pdf, wider)  # el mismo contenido ya no cabe
    assert content_outside_safe_zone(pdf, R.ratios["9x16"]) == []


def test_font_sizes_follow_the_text_length_and_the_shrink() -> None:
    spec = R.ratios["4x5"]
    short = font_sizes("headline_bold", copy(headline="Corto"), spec)["headline"]
    long = font_sizes("headline_bold", copy(headline="palabra " * 8), spec)["headline"]
    assert short > long > 40
    assert (
        font_sizes("headline_bold", copy(), spec, 0.5)["headline"]
        < font_sizes("headline_bold", copy(), spec)["headline"]
    )
    assert SHRINKS[0] == 1.0 and list(SHRINKS) == sorted(SHRINKS, reverse=True)


# ───────────────────────────── texto: lo pone el HTML, no la IA ─────────────────────────────


@pytest.mark.parametrize("template", TEMPLATES)
def test_accents_and_enes_are_real_text_in_both_markets(template: str) -> None:
    c = copy(
        headline="Revisión mensual: gestión sencilla",
        subheadline="Más claridad, menos caos: ¿por dónde empezar?",
        bullets=["Atención a clientes", "Planificación semanal", "Años de experiencia"],
        note="Mañana empiezo: ¡sin excusas! Ahora sí",
    )
    pdf, _ = compose(template, "4x5", copy=c)
    text = pdf_text(pdf)
    expected = {"note": "Mañana", "checklist": "Atención", "product_mockup": "Revisión"}.get(
        template, "Revisión"
    )
    assert expected in text
    pt = copy(
        headline="Ação rápida: organização já",
        bullets=["Atenção aos prazos", "Gestão simples", "Você decide"],
        note="Começo hoje: sem desculpas, até já",
    )
    pdf, _ = R.compose(
        template_id=template,
        copy=pt,
        ratio="4x5",
        product_template=BOLD,
        market="pt-BR",
        mockup_png=mockup() if template == "product_mockup" else None,
    )
    expected_pt = {"note": "Começo", "checklist": "Atenção"}.get(template, "Ação")
    assert expected_pt in pdf_text(pdf)


def test_untrusted_text_is_escaped_and_never_executed_as_a_template() -> None:
    hostile = copy(
        headline="<script>alert(1)</script> {{ 7*7 }}",
        subheadline="{% for x in y %}",
        kicker="<b>negrita</b>",
    )
    pdf, _ = compose("headline_bold", "4x5", copy=hostile)
    text = pdf_text(pdf)
    assert "<script>" in text and "{{ 7*7 }}" in text and "49" not in text  # literal, no evaluado
    squeezed = text.replace(" ", "").lower()  # el kicker va en mayúsculas y con tracking
    assert "<b>negrita</b>" in squeezed  # las etiquetas se ven como texto, no se interpretan


def test_the_note_falls_back_to_the_headline_and_the_check_cross_mark_changes_color() -> None:
    pdf, _ = compose("note", "4x5", copy=copy(note="", headline="Mi idea en una nota"))
    assert "Mi idea en una nota" in pdf_text(pdf)
    check, _ = R.render_with_report(
        template_id="checklist",
        copy=copy(mark="check"),
        ratio="4x5",
        product_template=BOLD,
        market="es-LATAM",
    )
    cross, _ = R.render_with_report(
        template_id="checklist",
        copy=copy(mark="cross"),
        ratio="4x5",
        product_template=BOLD,
        market="es-LATAM",
    )
    assert check != cross


def test_the_mockup_template_works_with_the_product_cover_or_a_text_fallback() -> None:
    with_cover, _ = compose("product_mockup", "4x5")
    pdf_without, _ = R.compose(
        template_id="product_mockup",
        copy=copy(),
        ratio="4x5",
        product_template=BOLD,
        market="es-LATAM",
        product_name="Bandeja Única",
        mockup_png=None,
    )
    assert "Bandeja Única" in pdf_text(pdf_without)  # sin portada, muestra el nombre del producto
    assert pdf_text(with_cover) != pdf_text(pdf_without)
    assert Image.open(io.BytesIO(mockup())).format == "PNG"


def test_unknown_templates_and_ratios_are_rejected() -> None:
    with pytest.raises(KeyError):
        compose("no_existe")
    with pytest.raises(KeyError):
        compose("headline_bold", "16x9")


# ───────────────────────────── colores y contraste ─────────────────────────────


@pytest.mark.parametrize("product", PRODUCT_TEMPLATES, ids=lambda t: t.id)
@pytest.mark.parametrize("scheme", ["bold", "light"])
def test_colors_always_have_readable_text_and_visible_buttons(product, scheme: str) -> None:
    c = scheme_colors(product, scheme)
    lum = lambda hex_: luminance(hex_rgb(hex_))  # noqa: E731
    assert contrast(lum(c["fg"]), lum(c["bg"])) >= 4.5  # texto sobre el fondo
    assert contrast(lum(c["accent_fg"]), lum(c["accent"])) >= 4.5  # texto del botón
    assert contrast(lum(c["accent"]), lum(c["bg"])) >= 2.0  # el botón se distingue del fondo
    assert contrast(lum(c["accent_text"]), lum(c["bg"])) >= 3.0  # kicker y precio


def test_readable_picks_a_legible_color() -> None:
    assert readable("#FFFFFF", "#FFFFFF") == "#111827"
    assert readable("#111827", "#FFFFFF") == "#111827"
    assert readable("#777777", "#000000") == "#777777"  # ya contrasta (4,7:1): se respeta
    assert readable("#444444", "#000000") != "#444444"  # no contrasta: se reemplaza


@pytest.mark.parametrize("product", PRODUCT_TEMPLATES, ids=lambda t: t.id)
def test_every_product_template_gives_a_valid_ad_within_the_safe_zone(product) -> None:
    for template in ("headline_bold", "checklist"):
        _, report = R.render_with_report(
            template_id=template,
            copy=copy(),
            ratio="9x16",
            product_template=product,
            market="es-LATAM",
        )
        assert report.outside == [], (product.id, template)


# ───────────────────────────── textos que no se pisan ─────────────────────────────


def text_boxes(pdf: bytes) -> list[tuple[float, float, float, float]]:
    """Cajas (x0, y0, x1, y1) en px de cada línea de texto de la página."""
    document = pdfium.PdfDocument(pdf)
    try:
        page = document[0]
        height = page.get_height()
        textpage = page.get_textpage()
        boxes = []
        for i in range(textpage.count_rects()):
            x0, y0, x1, y1 = textpage.get_rect(i)
            boxes.append((x0 / 0.75, (height - y1) / 0.75, x1 / 0.75, (height - y0) / 0.75))
        return boxes
    finally:
        document.close()


def overlapping(boxes) -> list[tuple]:
    """Pares de líneas que se montan una sobre otra (más de 8 px en vertical y en horizontal)."""
    bad = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            dx = min(a[2], b[2]) - max(a[0], b[0])
            dy = min(a[3], b[3]) - max(a[1], b[1])
            if dx > 8 and dy > 8:
                bad.append((a, b))
    return bad


HEADLINES = [
    "Corto",
    "Pedidos ordenados en una sola lista",
    "Capturas, notas y chats: el pedido nunca aparece",
    "Un sistema completo para ordenar tus pedidos del mes sin perder fechas",
]


@pytest.mark.parametrize("ratio", SIZES)
@pytest.mark.parametrize("template", TEMPLATES)
@pytest.mark.parametrize("headline", HEADLINES)
def test_lines_of_text_never_overlap_whatever_the_wrapping(
    template: str, ratio: str, headline: str
) -> None:
    c = copy(headline=headline, note=headline, subheadline="Registra cada pedido sin otra app")
    pdf, _ = compose(template, ratio, copy=c)
    assert overlapping(text_boxes(pdf)) == [], (template, ratio, headline)
