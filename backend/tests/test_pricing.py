"""Precio de venta + precio normal («de R$ 97 por R$ 47») en anuncios y páginas de ventas."""

import pypdfium2 as pdfium
import pytest

from app.ads import jobs as ad_jobs
from app.pages import rules as page_rules
from app.pages.render import render_page
from app.pricing import amount, price_errors, savings_percent
from tests.test_ads_strategy import avatar, brief, draft
from tests.test_api_ads import planned_world
from tests.test_pages import brief as page_brief
from tests.test_pages import content, proofs
from tests.test_pages_media import TEMPLATE


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("R$ 47", 47.0),
        ("R$ 47,90", 47.9),
        ("US$ 1,299.00", 1299.0),
        ("R$ 1.299,90", 1299.9),
        ("USD 12", 12.0),
        ("R$ 1.000", 1000.0),
        ("sin cifra", None),
    ],
)
def test_amount_reads_brazilian_and_us_formats(text, value) -> None:
    assert amount(text) == value


def test_savings_only_from_two_real_prices() -> None:
    assert savings_percent("R$ 97", "R$ 47") == 52
    assert savings_percent("US$ 49.90", "US$ 19.90") == 60
    assert savings_percent("", "R$ 47") is None
    assert savings_percent("R$ 47", "R$ 97") is None  # el normal no es mayor: no se afirma ahorro
    assert price_errors("R$ 47", "R$ 97") == []
    assert price_errors("", "R$ 97") == ["el precio normal necesita también el precio de venta"]
    assert "mayor" in price_errors("R$ 97", "R$ 47")[0]
    assert price_errors("R$ 47", "") == []


# ───────────────────────────── página de ventas ─────────────────────────────


def test_the_page_shows_the_struck_base_price_and_the_savings() -> None:
    b = page_brief(price_text="R$ 47", base_price_text="R$ 97")
    final = page_rules.finalize(content(), b, proofs())
    assert final.offer.base_price == "R$ 97" and final.offer.price_text == "R$ 47"
    html = render_page(final, b, proofs(), TEMPLATE, None)
    assert "<s>R$ 97</s>" in html and "Ahorras 52 %" in html
    assert '<s class="was-s">R$ 97</s>' in html  # también en la barra de compra


def test_without_a_price_the_base_price_never_shows() -> None:
    b = page_brief(price_text="", base_price_text="R$ 97")
    final = page_rules.finalize(content(), b, proofs())
    assert final.offer.base_price == ""
    assert "R$ 97" not in render_page(final, b, proofs(), TEMPLATE, None).split("</style>")[1]


def test_the_ai_cannot_write_the_base_price_itself() -> None:
    written = content()
    written = written.model_copy(
        update={"offer": written.offer.model_copy(update={"base_price": "R$ 500"})}
    )
    errors = page_rules.check_content(written, page_brief(), proofs())
    assert any("offer.base_price" in e for e in errors)


def test_the_page_api_rejects_a_base_price_lower_than_the_price() -> None:
    w, _ = planned_world()
    body = {
        "market": "es-LATAM",
        "manual": {
            "niche": "orden",
            "product_name": "Orden Digital",
            "problem": "Desorden",
            "audience": "Freelancers",
            "promise": "Orden",
        },
        "price_text": "US$ 97",
        "base_price_text": "US$ 47",
    }
    response = w.client.post("/pages", json=body)
    assert response.status_code == 422 and "mayor" in response.text


# ───────────────────────────── anuncios ─────────────────────────────


def pdf_text(pdf: bytes) -> str:
    doc = pdfium.PdfDocument(pdf)
    try:
        return doc[0].get_textpage().get_text_range()
    finally:
        doc.close()


def test_ads_with_a_price_show_the_base_price_struck_through() -> None:
    from tests.test_ads_render import BOLD, R, mockup

    b = brief(price_text="USD 19", base_price_text="USD 49")
    d = draft(
        "offer_stack",
        image={
            "headline": "Todo lo que incluye",
            "bullets": ["Guía completa", "Plantillas", "Checklist"],
            "price_text": "USD 19",
            "cta_text": "Quiero empezar",
        },
    )
    creative = {"template_id": "offer_stack", "ratio": "4x5", "copy": d.model_dump()}
    png = ad_jobs.compose_png(
        R, creative, template=BOLD, brief=b, market="es-LATAM", mockup=mockup()
    )
    assert png.startswith(b"\x89PNG")
    pdf, _ = R.compose(
        template_id="offer_stack",
        copy=d.image.model_copy(update={"base_price_text": b.base_price_text}),
        ratio="4x5",
        product_template=BOLD,
        market="es-LATAM",
    )
    text = pdf_text(pdf)
    assert "USD 49" in text and "USD 19" in text


def test_the_ad_brief_api_validates_the_base_price() -> None:
    w, _ = planned_world()
    manual = brief().model_dump(mode="json")
    bad = {"brief": {**manual, "price_text": "", "base_price_text": "USD 49"}}
    assert w.client.post("/ads/avatars", json=bad).status_code == 422
    assert avatar()  # el ayudante existe (el resto del flujo lo cubren los tests de anuncios)
