"""Plantillas por ángulo (cómo X sin Y, mito vs. verdad, objeción) y palabras destacadas."""

from pathlib import Path

import pypdfium2 as pdfium
import pytest

from app.ads import rules
from app.ads.export import build_csv
from app.ads.marks import mark_errors, strip_marks
from app.ads.render import AdRenderer, highlight
from app.ads.schemas import TEMPLATE_IDS, ImageCopy
from app.config import Settings
from app.templates_engine.model import load_template
from tests.test_ads_strategy import brief, draft

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = Settings(_env_file=None)
R = AdRenderer(ROOT / "ad_templates", SETTINGS.templates_dir)
BOLD = load_template(SETTINGS.templates_dir, "bold-moderno")
ALL = list(TEMPLATE_IDS)


def check(d) -> list[str]:
    return rules.check_draft(d, allowed_templates=ALL, brief=brief(), proofs=[])


def pdf_text(pdf: bytes) -> str:
    document = pdfium.PdfDocument(pdf)
    try:
        return document[0].get_textpage().get_text_range()
    finally:
        document.close()


# ───────────────────────────── palabras destacadas ─────────────────────────────


def test_marks_are_markup_only() -> None:
    assert strip_marks("Cocina *natural* para tu *perro*") == "Cocina natural para tu perro"
    assert mark_errors("Sin marcas") == []
    assert mark_errors("Cocina *natural* hoy") == []


@pytest.mark.parametrize(
    "bad",
    [
        "Cocina *natural hoy",
        "Cocina **natural** hoy",
        "*a* *b* *c* *d*",
        "*cuatro palabras muy largas* x",
    ],
)
def test_broken_or_excessive_marks_are_rejected(bad: str) -> None:
    assert mark_errors(bad)


def test_highlight_escapes_html_and_marks_the_words() -> None:
    html = str(highlight("<b>Hola</b> *natural* & más"))
    assert "<b>" not in html and "&lt;b&gt;" in html and "&amp;" in html
    assert "<mark>natural</mark>" in html


def test_marks_do_not_count_as_words_or_reach_the_policy_or_exports() -> None:
    d = draft(headline="Pedidos *ordenados* en una sola lista")
    assert check(d) == []
    assert "*" not in rules.visible_text(d)
    row = {
        "filename": "x.png", "ratio": "4x5", "template_id": "headline_bold", "angle": "dolor",
        "avatar": "a", "copy": d.model_dump(mode="json"),
    }  # fmt: skip
    assert b"*" not in build_csv("es-LATAM", [row])


def test_only_the_image_headline_can_carry_asterisks() -> None:
    errors = check(draft(subheadline="Un método *simple*"))
    assert any("no lleva asteriscos" in e for e in errors)
    assert any("no lleva asteriscos" in e for e in check(draft(ad_headline="Ordena *ya*")))


def test_the_marked_word_is_drawn_and_the_asterisks_are_not() -> None:
    pdf, _ = R.compose(
        template_id="headline_bold",
        copy=ImageCopy(headline="Tu perro merece comida *de verdad*"),
        ratio="4x5",
        product_template=BOLD,
        market="es-LATAM",
    )
    text = pdf_text(pdf)
    assert "de verdad" in text and "*" not in text


# ───────────────────────────── plantillas por ángulo ─────────────────────────────


@pytest.mark.parametrize(
    ("template", "bullets", "ok"),
    [
        ("myth", ["Cocinar en casa es arriesgado", "Con porciones correctas es simple"], True),
        ("myth", ["Solo uno"], False),
        ("objection", ["¿Y si no tengo tiempo?", "Cocinas una vez por semana"], True),
        ("objection", ["a", "b", "c"], False),
        ("how", ["Elige la receta", "Compra con la lista", "Porciona"], True),
        ("how", ["Uno", "Dos"], False),
    ],
)
def test_each_angle_template_needs_its_bullets(template: str, bullets: list[str], ok: bool) -> None:
    errors = check(draft(template, bullets=bullets))
    assert (errors == []) is ok, errors


CASES = {
    "how": ImageCopy(
        kicker="Sin horas en la cocina",
        headline="Cómo cocinar *natural* sin complicarte",
        bullets=["Elige la receta de la semana", "Compra con la lista", "Porciona según su tamaño"],
        cta_text="QUIERO EMPEZAR",
    ),
    "myth": ImageCopy(
        headline="¿La comida casera es *peligrosa*?",
        bullets=["Cocinar en casa siempre es arriesgado", "Con porciones correctas es simple"],
        cta_text="VER LA GUÍA",
    ),
    "objection": ImageCopy(
        headline="«No tengo *tiempo* para cocinar»",
        bullets=["¿Y si no tengo tiempo cada día?", "Cocinas una vez y congelas porciones"],
        cta_text="QUIERO LA GUÍA",
    ),
}


@pytest.mark.parametrize("ratio", ["4x5", "9x16", "1x1"])
@pytest.mark.parametrize("template", list(CASES))
def test_angle_templates_fit_the_safe_zone_at_full_size(template: str, ratio: str) -> None:
    pdf, report = R.compose(
        template_id=template,
        copy=CASES[template],
        ratio=ratio,
        product_template=BOLD,
        market="es-LATAM",
    )
    assert report.outside == [] and report.shrink == 1.0


@pytest.mark.parametrize(
    ("template", "market", "labels"),
    [
        ("myth", "es-LATAM", ("Mito", "Verdad")),
        ("myth", "pt-BR", ("Mito", "Verdade")),
        ("objection", "es-LATAM", ("La duda", "La respuesta")),
        ("objection", "pt-BR", ("A dúvida", "A resposta")),
    ],
)
def test_angle_templates_label_each_card_in_the_market_language(
    template: str, market: str, labels: tuple[str, str]
) -> None:
    pdf, _ = R.compose(
        template_id=template,
        copy=CASES[template],
        ratio="4x5",
        product_template=BOLD,
        market=market,
    )
    # Las etiquetas llevan letter-spacing: al extraer el texto salen con espacios entre letras.
    text = "".join(pdf_text(pdf).lower().split())
    assert all("".join(label.lower().split()) in text for label in labels)


def test_angles_point_to_the_new_templates() -> None:
    import json

    for market in ("es-LATAM", "pt-BR"):
        library = json.loads((ROOT / "prompts" / market / "ads" / "angles.json").read_text("utf-8"))
        assert "myth" in library["mito"]["templates"]
        assert "objection" in library["objecion"]["templates"]
        assert "how" in library["mecanismo"]["templates"]
        assert all(t in TEMPLATE_IDS for a in library.values() for t in a["templates"])
