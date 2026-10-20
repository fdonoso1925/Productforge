"""Ficha comercial del paquete (§7) en Markdown y DOCX."""

from app.content.schemas import CommercialSheet
from app.generators.base import FileArtifact, RenderContext, artifact
from app.generators.office import new_document, to_bytes
from app.templates_engine.model import Template

TEXT = {
    "pt-BR": {
        "title": "Ficha comercial",
        "names": "Nomes alternativos",
        "headline": "Headline",
        "subheadline": "Subheadline",
        "price": "Preço sugerido",
        "bumps": "Order bumps",
        "checkout": "Texto do checkout",
        "bonuses": "Bônus e valor percebido",
        "description": "Descrição curta (Hotmart / Kiwify)",
        "benefits": "Benefícios",
        "hooks": "Ganchos para anúncios",
    },
    "es-LATAM": {
        "title": "Ficha comercial",
        "names": "Nombres alternativos",
        "headline": "Headline",
        "subheadline": "Subheadline",
        "price": "Precio sugerido",
        "bumps": "Order bumps",
        "checkout": "Texto del checkout",
        "bonuses": "Bonus y valor percibido",
        "description": "Descripción corta (Hotmart / Kiwify)",
        "benefits": "Beneficios",
        "hooks": "Hooks para anuncios",
    },
}
SYMBOL = {"BRL": "R$", "USD": "US$"}


def money(value: float, currency: str) -> str:
    return f"{SYMBOL.get(currency, currency)} {value:,.2f}"


def commercial_markdown(sheet: CommercialSheet, market: str) -> str:
    t, cur = TEXT[market], sheet.currency
    price = f"{money(sheet.main_price.min, cur)} – {money(sheet.main_price.max, cur)}"
    out = [
        f"# {t['title']}: {sheet.product_name}",
        "",
        f"**{t['names']}:** " + " · ".join(sheet.alternative_names),
        "",
        f"## {t['headline']}",
        sheet.headline,
        "",
        f"## {t['subheadline']}",
        sheet.subheadline,
        "",
        f"## {t['price']}",
        price,
        "",
        f"## {t['bumps']}",
    ]
    for bump in sheet.order_bumps:
        out += [
            f"- **{bump.title}** — {money(bump.price, cur)}",
            f"  - {t['checkout']}: {bump.checkout_text}",
        ]
    out += ["", f"## {t['bonuses']}"]
    out += [f"- **{b.title}** — {money(b.perceived_value, cur)}" for b in sheet.bonuses]
    out += ["", f"## {t['description']}", sheet.short_description, "", f"## {t['benefits']}"]
    out += [f"- {b}" for b in sheet.benefit_bullets]
    out += ["", f"## {t['hooks']}"]
    out += [f"{i}. {h}" for i, h in enumerate(sheet.ad_hooks, start=1)]
    return "\n".join(out) + "\n"


def commercial_docx(sheet: CommercialSheet, template: Template, market: str) -> bytes:
    t, cur = TEXT[market], sheet.currency
    doc = new_document(template.office_theme())
    doc.add_paragraph(f"{t['title']}: {sheet.product_name}", style="Title")
    names = doc.add_paragraph()
    names.add_run(f"{t['names']}: ").bold = True
    names.add_run(" · ".join(sheet.alternative_names))

    def section(heading: str, *paragraphs: str) -> None:
        doc.add_paragraph(heading, style="Heading 2")
        for text in paragraphs:
            doc.add_paragraph(text)

    section(t["headline"], sheet.headline)
    section(t["subheadline"], sheet.subheadline)
    section(t["price"], f"{money(sheet.main_price.min, cur)} – {money(sheet.main_price.max, cur)}")
    doc.add_paragraph(t["bumps"], style="Heading 2")
    for bump in sheet.order_bumps:
        line = doc.add_paragraph(style="List Bullet")
        line.add_run(f"{bump.title} — {money(bump.price, cur)}").bold = True
        doc.add_paragraph(f"{t['checkout']}: {bump.checkout_text}")
    doc.add_paragraph(t["bonuses"], style="Heading 2")
    for bonus in sheet.bonuses:
        doc.add_paragraph(
            f"{bonus.title} — {money(bonus.perceived_value, cur)}", style="List Bullet"
        )
    section(t["description"], sheet.short_description)
    doc.add_paragraph(t["benefits"], style="Heading 2")
    for benefit in sheet.benefit_bullets:
        doc.add_paragraph(benefit, style="List Bullet")
    doc.add_paragraph(t["hooks"], style="Heading 2")
    for hook in sheet.ad_hooks:
        doc.add_paragraph(hook, style="List Number")
    return to_bytes(doc)


def commercial_files(
    sheet: CommercialSheet, template: Template, ctx: RenderContext
) -> list[FileArtifact]:
    return [
        artifact(ctx, "md", commercial_markdown(sheet, ctx.market).encode()),
        artifact(ctx, "docx", commercial_docx(sheet, template, ctx.market)),
    ]
