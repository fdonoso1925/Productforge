"""Página de ventas → un único archivo HTML autocontenido (CSS en línea, sin JavaScript ni
recursos externos: nada se descarga de ningún tercero y no lleva logos de nadie).

Infografías como SVG en línea (`render_visual`, el mismo dibujante de los PDF: todo su texto se
escapa) y fotos/mockups incrustados como data URI (`pages/media.py`).

Todo el texto se escapa (Jinja con autoescape). Los colores vienen de la paleta validada de la
plantilla visual del producto. El enlace de compra debe ser https o el botón queda en «#oferta».
"""

from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from app.content.schemas.formats import Visual, VisualItem
from app.generators.visuals import render_visual
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
        "journey": "Tu camino, paso a paso",
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
        "journey": "Seu caminho, passo a passo",
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


def _svg(visual: Visual | None, template: Template, market: str) -> Markup | None:
    """SVG en línea de una infografía; None si no hay o no se puede dibujar."""
    if visual is None:
        return None
    try:
        svg = render_visual(visual, template, market)  # type: ignore[arg-type]
    except Exception:
        return None
    return Markup(svg) if svg else None  # noqa: S704 - render_visual ya escapa todo el texto


def journey_visual(content: PageContent, title: str) -> Visual | None:
    """Las etapas del camino como infografía de proceso (la arma el código, no la IA)."""
    steps = content.journey[:5]
    if len(steps) < 3:
        return None
    return Visual(
        kind="process",
        title=title,
        items=[VisualItem(label=s.title, detail=s.text) for s in steps],
    )


def render_page(
    content: PageContent,
    brief: PageBrief,
    proofs: list[PageProof],
    template: Template,
    checkout_url: str | None,
    images: dict[str, str] | None = None,
) -> str:
    """`images`: {hero, problem, bundle, book} → data URI (las que haya)."""
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
        img={k: v for k, v in (images or {}).items() if v.startswith("data:image/")},
        solution_svg=_svg(content.solution_visual, template, brief.market),
        journey_svg=_svg(journey_visual(content, labels["journey"]), template, brief.market),
    )
