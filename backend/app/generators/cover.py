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


DARK_PAPER = "#0E1018"
LIGHT_INK = "#F7F2EA"


def _towards(color: str, target: str, over: str, minimum: float) -> str:
    """Acerca `color` a `target` hasta llegar al contraste `minimum` sobre `over`."""
    for _ in range(14):
        if _contrast(color, over) >= minimum:
            break
        color = _mix(color, target, 0.15)
    return color


def editorial_colors(palette: Palette, variant: str = "classic") -> dict[str, str]:
    """Colores de la tapa editorial a partir de la paleta de la plantilla, siempre legibles:
    tinta (título) con contraste ≥ 7 sobre el papel y dorado (subtítulo, rombos, filetes) ≥ 3
    (≥ 4,5 en los diseños oscuros, donde el dorado también lleva texto).
    `variant`: classic (papel crema), night y photo (papel oscuro), minimal (papel blanco)."""
    dark = variant in ("night", "photo")
    if dark:
        paper = _mix(DARK_PAPER, palette.primary, 0.35)
        if _contrast(LIGHT_INK, paper) < 7:
            paper = _mix(paper, "#000000", 0.5)
        ink = LIGHT_INK
        gold = _towards(palette.accent, "#FFFFFF", paper, 4.5)
    else:
        paper = "#FFFFFF" if variant == "minimal" else _mix(PAPER, palette.primary, 0.04)
        ink = max(
            (palette.primary, palette.text, palette.secondary), key=lambda c: _contrast(c, paper)
        )
        ink = _towards(ink, INK_FALLBACK, paper, 7)
        gold = _towards(palette.accent, "#000000", paper, 3)
    r, g, b = hex_rgb(paper)
    return {
        "paper": paper,
        "fade": f"rgba({r},{g},{b},0)",
        "shade": f"rgba({r},{g},{b},0.55)",
        "ink": ink,
        "gold": gold,
        "glow": _mix(paper, palette.accent, 0.22),
        "spine": _mix(paper, "#FFFFFF" if dark else "#000000", 0.07),
    }


def is_editorial(template: Template, spec: "CoverSpec") -> bool:
    """¿La tapa es un libro editorial? (plantilla de libro o la opción vieja del producto)."""
    return template.style.cover == "editorial" or spec.design == "editorial"


def editorial_variant(template: Template) -> str:
    return template.style.book if template.style.cover == "editorial" else "classic"
