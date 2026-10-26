"""Página de ventas → un único archivo HTML autocontenido (CSS en línea, sin JavaScript, sin
imágenes ni recursos externos: nada se descarga de ningún tercero y no lleva logos de nadie).

Todo el texto se escapa (Jinja con autoescape). Los colores vienen de la paleta validada de la
plantilla visual del producto. El enlace de compra debe ser https o el botón queda en «#oferta».
"""

from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.pages.schemas import PageBrief, PageContent, PageProof
from app.templates_engine.model import Template

LABELS = {
    "es-LATAM": {
        "lang": "es",
        "benefits": "Lo que vas a lograr",
        "inside": "Todo lo que incluye",
        "main": "Producto principal",
        "bonus": "Bonus",
        "bump": "Opcional",
        "for_you": "Es para ti si…",
        "not_for_you": "No es para ti si…",
        "about": "Quién está detrás",
        "guarantee": "Garantía",
        "faq": "Preguntas frecuentes",
    },
    "pt-BR": {
        "lang": "pt-BR",
        "benefits": "O que você vai conquistar",
        "inside": "Tudo o que está incluído",
        "main": "Produto principal",
        "bonus": "Bônus",
        "bump": "Opcional",
        "for_you": "É para você se…",
        "not_for_you": "Não é para você se…",
        "about": "Quem está por trás",
        "guarantee": "Garantia",
        "faq": "Perguntas frequentes",
    },
}

_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    autoescape=select_autoescape(["html", "j2"], default=True),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def readable_on(background: str) -> str:
    """Negro o blanco, el que dé más contraste sobre ese fondo."""
    lum = _luminance(background)
    return "#0B0B0D" if (lum + 0.05) / 0.05 >= 1.05 / (lum + 0.05) else "#FFFFFF"


def safe_link(url: str | None) -> str:
    """Solo https con dominio; cualquier otra cosa (javascript:, data:, http…) se descarta."""
    parts = urlsplit((url or "").strip())
    if parts.scheme != "https" or not parts.hostname or "." not in parts.hostname:
        return "#oferta"
    if parts.username or parts.password:
        return "#oferta"
    return (url or "").strip()


def font_stack(family: str) -> str:
    clean = "".join(ch for ch in family if ch.isalnum() or ch in " -")
    return f'"{clean}", system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'


def items_of(content: PageContent, brief: PageBrief) -> list[dict]:
    blurbs = content.deliverable_blurbs
    return [
        {"kind": d.kind, "title": d.title, "blurb": blurbs[i] if i < len(blurbs) else d.promise}
        for i, d in enumerate(brief.deliverables)
    ]


def render_page(
    content: PageContent,
    brief: PageBrief,
    proofs: list[PageProof],
    template: Template,
    checkout_url: str | None,
) -> str:
    labels = LABELS[brief.market]
    chosen = {p.id: p for p in proofs}
    picked = [chosen[i] for i in content.proof.proof_ids if i in chosen]
    palette = template.palette
    return _ENV.get_template("page.html.j2").render(
        c=content,
        lang=labels["lang"],
        L=labels,
        p=palette,
        on_accent=readable_on(palette.accent),
        radius=template.style.radius,
        heading_font=font_stack(template.fonts.heading.family),
        body_font=font_stack(template.fonts.body.family),
        items=items_of(content, brief),
        proofs=picked,
        cta=safe_link(checkout_url),
    )
