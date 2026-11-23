"""Portada de un producto: arte generativo de un estilo o una imagen propia del usuario.

`products.cover` guarda un `CoverSpec`. Un producto anterior a esta función (columna vacía) se
queda sin arte, como se veía antes; los nuevos arrancan en `auto`.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.generators.cover_art import ArtStyle, render_art, resolve_style
from app.generators.cover_image import contrast, hex_rgb, luminance, veil_opacity
from app.templates_engine.model import Palette, Template

ArtChoice = Literal["auto", "topo", "waves", "circles", "bauhaus", "facets", "none"]
# Diseño de la portada: el de la plantilla (texto + libro pequeño) o «editorial», una tapa de
# libro de verdad (papel claro, título grande, foto o arte al centro y frase al pie, con su lomo
# en el mockup del libro). Opcional: los productos sin el campo siguen con el de la plantilla.
CoverDesign = Literal["template", "editorial"]


class CoverSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    art: ArtChoice = "auto"
    # Imagen propia subida por el usuario (reemplaza al arte). Vive en `<user>/covers/<id>.jpg`.
    image_id: UUID | None = None
    design: CoverDesign = "template"


def stored_spec(product: dict) -> CoverSpec:
    """El `cover` guardado; un producto viejo (sin nada) queda sin arte."""
    raw = product.get("cover")
    return CoverSpec.model_validate(raw) if raw else CoverSpec(art="none")


def image_path(user_id: UUID | str, image_id: UUID | str) -> str:
    return f"{user_id}/covers/{image_id}.jpg"


async def image_exists(storage, user_id: UUID | str, image_id: UUID | str) -> bool:
    """Las imágenes viven bajo la carpeta del usuario: la de otro nunca se resuelve."""
    try:
        await storage.download(image_path(user_id, image_id))
    except Exception:
        return False
    return True


def root_id(product: dict) -> str:
    """Las versiones de un producto comparten arte: la semilla sale de la raíz del árbol."""
    return str(product.get("root_product_id") or product["id"])


def art_for_piece(
    spec: CoverSpec, product: dict, template: Template, role: str, order: int
) -> tuple[ArtStyle | None, str]:
    """Estilo de arte del paquete y SVG de esta pieza (mismo estilo, motivo propio)."""
    style = resolve_style(spec.art, root_id(product))
    if style is None:
        return None, ""
    seed = f"{root_id(product)}:{role}:{order}"
    return style, render_art(style, seed, template.palette, template.style.cover)


def veil_for(jpeg: bytes, template: Template) -> float:
    return veil_opacity(jpeg, template.palette)


# ───────────────────────────── diseño editorial ─────────────────────────────

PAPER = "#F7F2EA"  # papel cálido de libro impreso
INK_FALLBACK = "#141B2D"


def _mix(a: str, b: str, t: float) -> str:
    ra, ga, ba = hex_rgb(a)
    rb, gb, bb = hex_rgb(b)
    r, g, b_ = (round(x + (y - x) * t) for x, y in ((ra, rb), (ga, gb), (ba, bb)))
    return f"#{r:02X}{g:02X}{b_:02X}"


def _contrast(a: str, b: str) -> float:
    return contrast(luminance(hex_rgb(a)), luminance(hex_rgb(b)))


def editorial_colors(palette: Palette) -> dict[str, str]:
    """Colores de la tapa editorial a partir de la paleta de la plantilla, siempre legibles:
    tinta (título) con contraste ≥ 7 sobre el papel y dorado (subtítulo, rombos, filetes) ≥ 3."""
    paper = _mix(PAPER, palette.primary, 0.04)
    ink = max((palette.primary, palette.text, palette.secondary), key=lambda c: _contrast(c, paper))
    for _ in range(12):
        if _contrast(ink, paper) >= 7:
            break
        ink = _mix(ink, INK_FALLBACK, 0.35)
    gold = palette.accent
    for _ in range(12):
        if _contrast(gold, paper) >= 3:
            break
        gold = _mix(gold, "#000000", 0.15)
    r, g, b = hex_rgb(paper)
    return {
        "paper": paper,
        "fade": f"rgba({r},{g},{b},0)",
        "ink": ink,
        "gold": gold,
        "glow": _mix(paper, palette.accent, 0.22),
        "spine": _mix(paper, "#000000", 0.07),
    }
