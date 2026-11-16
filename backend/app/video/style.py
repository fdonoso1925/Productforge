"""Colores y tipografías del video, sacados de la plantilla visual del producto.

Así el video se ve de la misma marca que el ebook y los anuncios. Cada par texto/fondo se
comprueba con contraste WCAG (mismas funciones que los anuncios) y, si no llega, se cambia por
uno que sí se lea.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from app.ads.render import readable
from app.generators.cover_image import contrast, hex_rgb, luminance
from app.templates_engine.fonts import font_path
from app.templates_engine.model import Template

DANGER, SUCCESS = "#E5484D", "#22A06B"
CARD, INK, INK_SOFT = "#FFFFFF", "#181C3C", "#5B6175"


def mix(a: str, b: str, t: float) -> str:
    """Mezcla dos colores: t=0 → a, t=1 → b."""
    ra, ga, ba = hex_rgb(a)
    rb, gb, bb = hex_rgb(b)
    r, g, b_ = (round(x + (y - x) * t) for x, y in ((ra, rb), (ga, gb), (ba, bb)))
    return f"#{r:02X}{g:02X}{b_:02X}"


@dataclass(frozen=True)
class VideoPalette:
    bg: str
    text: str
    accent: str
    on_accent: str
    sub: str
    deco: str
    card: str = CARD
    ink: str = INK
    ink_soft: str = INK_SOFT
    bad: str = DANGER
    good: str = SUCCESS


def palette_from(template: Template) -> VideoPalette:
    """Fondo = color principal de la marca; texto y acento siempre legibles sobre él."""
    p = template.palette
    bg = p.primary
    text = readable(p.on_primary, bg)
    accent = p.accent
    if contrast(luminance(hex_rgb(accent)), luminance(hex_rgb(bg))) < 2.0:
        accent = text  # el acento se confunde con el fondo: el destacado usa el color del texto
    return VideoPalette(
        bg=bg,
        text=text,
        accent=accent,
        on_accent=readable(bg, accent, INK),
        sub=mix(text, bg, 0.28),
        deco=mix(bg, text, 0.07),
    )


@dataclass(frozen=True)
class VideoFonts:
    heading: Path
    bold: Path
    regular: Path

    def heading_at(self, size: int) -> ImageFont.FreeTypeFont:
        return _font(str(self.heading), size)

    def bold_at(self, size: int) -> ImageFont.FreeTypeFont:
        return _font(str(self.bold), size)

    def regular_at(self, size: int) -> ImageFont.FreeTypeFont:
        return _font(str(self.regular), size)


@lru_cache(maxsize=64)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _existing(fonts_dir: Path, family: str, weights: list[int], prefer: int) -> Path | None:
    """El archivo del peso más cercano a `prefer` que exista para esa familia."""
    for weight in sorted(weights, key=lambda w: abs(w - prefer)):
        path = font_path(fonts_dir, family, weight)
        if path.exists():
            return path
    return None


def fonts_from(template: Template, templates_dir: Path) -> VideoFonts:
    """Títulos con la tipografía de títulos de la plantilla; filas con la del cuerpo. Si a una
    plantilla le falta un peso, se usa Inter (OFL, incluida en el proyecto)."""
    fonts_dir = templates_dir / "_fonts"
    fallback_bold = font_path(fonts_dir, "Inter", 700)
    fallback_regular = font_path(fonts_dir, "Inter", 400)
    h, b = template.fonts.heading, template.fonts.body
    heading = _existing(fonts_dir, h.family, h.weights, max(h.weights)) or fallback_bold
    bold = _existing(fonts_dir, b.family, [*b.weights, 700, 600], 700) or fallback_bold
    regular = _existing(fonts_dir, b.family, [*b.weights, 400], 400) or fallback_regular
    return VideoFonts(heading=heading, bold=bold, regular=regular)
