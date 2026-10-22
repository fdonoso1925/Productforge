"""Arte generativo para las portadas: SVG a 210x297 mm, único por pieza y repetible.

Cada estilo recibe una semilla (producto + pieza) y la paleta de la plantilla, y devuelve un SVG
armado solo con números y colores de la paleta (hex validados): nada del contenido de la IA ni del
usuario entra al SVG. El mismo estilo en todo el paquete da una "familia"; la semilla de cada pieza
cambia el motivo.

Para que el título siempre se lea, sobre el arte va una "zona protegida": un degradado del color de
fondo de la portada en el área donde cae el texto de cada diseño.
"""

import hashlib
import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.templates_engine.model import Palette

W, H = 210, 297

ArtStyle = Literal["topo", "waves", "circles", "bauhaus", "facets"]
STYLE_ORDER: tuple[ArtStyle, ...] = ("topo", "waves", "circles", "bauhaus", "facets")


def _rng(seed: str) -> random.Random:
    # Solo decorativo (no es criptografía): la semilla hace el arte repetible.
    return random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:12], 16))  # noqa: S311


def _svg(body: str, opacity: float = 1.0) -> str:
    return f'<g opacity="{opacity}">{body}</g>'


def _closed_curve(points: list[tuple[float, float]]) -> str:
    """Curva cerrada suave (Catmull-Rom → Bézier) por los puntos dados."""
    n = len(points)
    d = ""
    for i in range(n):
        p0, p1, p2, p3 = points[i - 1], points[i], points[(i + 1) % n], points[(i + 2) % n]
        if i == 0:
            d += f"M{p1[0]:.2f},{p1[1]:.2f}"
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f"C{c1[0]:.2f},{c1[1]:.2f} {c2[0]:.2f},{c2[1]:.2f} {p2[0]:.2f},{p2[1]:.2f}"
    return d + "Z"


def topo(rng: random.Random, p: Palette) -> str:
    out = []
    centers = [
        (rng.uniform(120, 230), rng.uniform(-10, 90)),
        (rng.uniform(-30, 70), rng.uniform(200, 320)),
    ]
    for cx, cy in centers:
        phase = [rng.uniform(0, 6.28) for _ in range(3)]
        amp = [rng.uniform(0.10, 0.20), rng.uniform(0.05, 0.12), rng.uniform(0.03, 0.07)]
        for i in range(1, 17):
            r0 = 7 + i * 7.2
            pts = []
            for k in range(36):
                a = k / 36 * 2 * math.pi
                rad = r0 * (
                    1
                    + amp[0] * math.sin(3 * a + phase[0] + i * 0.12)
                    + amp[1] * math.sin(5 * a + phase[1])
                    + amp[2] * math.sin(8 * a + phase[2])
                )
                pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
            strong = i % 4 == 0
            color = p.secondary if strong else p.accent
            out.append(
                f'<path d="{_closed_curve(pts)}" fill="none" stroke="{color}" '
                f'stroke-width="{0.9 if strong else 0.5}"/>'
            )
    return _svg("".join(out), 0.55)


def waves(rng: random.Random, p: Palette) -> str:
    out = []
    colors = [p.accent, p.secondary, p.primary, p.accent, p.secondary]
    for i in range(6):
        base = 175 + i * 22
        amp = rng.uniform(6, 16)
        freq = rng.uniform(0.7, 1.6)
        phase = rng.uniform(0, 6.28)
        pts = [f"M0,{H}"]
        for x in range(0, W + 6, 6):
            y = base + amp * math.sin(x / W * 2 * math.pi * freq + phase)
            pts.append(f"L{x},{y:.2f}")
        pts.append(f"L{W},{H}Z")
        out.append(
            f'<path d="{" ".join(pts)}" fill="{colors[i % len(colors)]}" '
            f'fill-opacity="{0.16 + i * 0.05:.2f}"/>'
        )
    return _svg("".join(out))


def circles(rng: random.Random, p: Palette) -> str:
    out = []
    colors = [p.accent, p.secondary, p.on_primary, p.accent]
    for _ in range(13):
        cx, cy, radius = rng.uniform(-10, 220), rng.uniform(-10, 300), rng.uniform(14, 70)
        color = rng.choice(colors)
        if rng.random() < 0.35:
            out.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" fill="none" '
                f'stroke="{color}" stroke-width="0.8" stroke-opacity="0.6"/>'
            )
        else:
            out.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" fill="{color}" '
                f'fill-opacity="{rng.uniform(0.10, 0.28):.2f}"/>'
            )
    return _svg("".join(out))


def bauhaus(rng: random.Random, p: Palette) -> str:
    out = []
    t = 35
    colors = [p.accent, p.secondary, p.primary, p.on_primary]
    for row in range(5, 9):
        for col in range(6):
            x, y = col * t, row * t
            kind = rng.choice(["quarter", "quarter", "half", "square", "circle", "empty"])
            color = rng.choice(colors)
            opacity = rng.uniform(0.25, 0.6)
            if kind == "quarter":
                corner = rng.choice([0, 1, 2, 3])
                ox = x + (t if corner in (1, 2) else 0)
                oy = y + (t if corner in (2, 3) else 0)
                sx = -1 if corner in (1, 2) else 1
                sy = -1 if corner in (2, 3) else 1
                sweep = 1 if sx * sy > 0 else 0
                out.append(
                    f'<path d="M{ox},{oy} L{ox + sx * t},{oy} A{t},{t} 0 0 {sweep} '
                    f'{ox},{oy + sy * t}Z" fill="{color}" fill-opacity="{opacity:.2f}"/>'
                )
            elif kind == "half":
                out.append(
                    f'<path d="M{x},{y + t} A{t / 2},{t / 2} 0 0 1 {x + t},{y + t}Z" '
                    f'fill="{color}" fill-opacity="{opacity:.2f}"/>'
                )
            elif kind == "square":
                out.append(
                    f'<rect x="{x}" y="{y}" width="{t}" height="{t}" fill="{color}" '
                    f'fill-opacity="{opacity * 0.6:.2f}"/>'
                )
            elif kind == "circle":
                out.append(
                    f'<circle cx="{x + t / 2}" cy="{y + t / 2}" r="{t / 2 - 3}" fill="none" '
                    f'stroke="{color}" stroke-width="1" '
                    f'stroke-opacity="{min(opacity + 0.2, 1):.2f}"/>'
                )
    return _svg("".join(out))


def facets(rng: random.Random, p: Palette) -> str:
    cols_n, rows_n = 7, 10
    dx, dy = W / (cols_n - 1), H / (rows_n - 1)
    grid = [
        [
            (
                c * dx + rng.uniform(-dx * 0.35, dx * 0.35),
                r * dy + rng.uniform(-dy * 0.35, dy * 0.35),
            )
            for c in range(cols_n)
        ]
        for r in range(rows_n)
    ]
    out = []
    colors = [p.accent, p.secondary, p.on_primary, p.primary]
    for r in range(rows_n - 1):
        for c in range(cols_n - 1):
            a, b, c2, d = grid[r][c], grid[r][c + 1], grid[r + 1][c + 1], grid[r + 1][c]
            for tri in ((a, b, c2), (a, c2, d)):
                path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in tri) + "Z"
                out.append(
                    f'<path d="{path}" fill="{rng.choice(colors)}" '
                    f'fill-opacity="{rng.uniform(0.0, 0.22):.2f}" stroke="{p.on_primary}" '
                    f'stroke-opacity="0.08" stroke-width="0.3"/>'
                )
    return _svg("".join(out))


_DRAW: dict[str, Callable[[random.Random, Palette], str]] = {
    "topo": topo,
    "waves": waves,
    "circles": circles,
    "bauhaus": bauhaus,
    "facets": facets,
}


@dataclass(frozen=True)
class TextZone:
    """Rectángulo (mm) donde cae el texto de la portada y color de fondo que hay debajo."""

    x0: float
    y0: float
    x1: float
    y1: float
    background: str


def text_zone(layout: str, p: Palette) -> TextZone:
    """Dónde pone el texto cada diseño de portada (ver templates/_base/cover.html.j2)."""
    if layout == "band":
        return TextZone(10, 22, 200, 112, p.primary)
    if layout == "split":
        return TextZone(88, 58, 205, 160, p.background)
    if layout == "notebook":
        return TextZone(28, 52, 205, 135, p.background)
    if layout == "full-bleed":
        return TextZone(10, 38, 200, 132, p.primary)
    return TextZone(10, 38, 200, 132, p.surface)  # centered


def _protect(zone: TextZone) -> str:
    """Degradado del color de fondo sobre el arte: lo atenúa solo donde va el texto."""
    cx, cy = (zone.x0 + zone.x1) / 2, (zone.y0 + zone.y1) / 2
    rx, ry = (zone.x1 - zone.x0) / 2 * 1.25, (zone.y1 - zone.y0) / 2 * 1.35
    return (
        f'<defs><radialGradient id="protect" gradientUnits="userSpaceOnUse" cx="{cx}" cy="{cy}" '
        f'r="{rx}" gradientTransform="translate({cx} {cy}) scale(1 {ry / rx:.4f}) '
        f'translate({-cx} {-cy})">'
        f'<stop offset="0" stop-color="{zone.background}" stop-opacity="0.94"/>'
        f'<stop offset="0.62" stop-color="{zone.background}" stop-opacity="0.9"/>'
        f'<stop offset="1" stop-color="{zone.background}" stop-opacity="0"/>'
        f"</radialGradient></defs>"
        f'<rect x="{zone.x0 - rx}" y="{zone.y0 - ry}" width="{zone.x1 - zone.x0 + 2 * rx}" '
        f'height="{zone.y1 - zone.y0 + 2 * ry}" fill="url(#protect)"/>'
    )


def resolve_style(style: str, root_id: str) -> ArtStyle | None:
    """`auto` elige un estilo por producto (estable entre versiones); `none` = sin arte."""
    if style == "none":
        return None
    if style in _DRAW:
        return style  # type: ignore[return-value]
    index = int(hashlib.sha256(root_id.encode()).hexdigest()[:8], 16) % len(STYLE_ORDER)
    return STYLE_ORDER[index]


def render_art(
    style: ArtStyle, seed: str, palette: Palette, layout: str, *, background: bool = False
) -> str:
    """SVG completo (viewBox 0 0 210 297) del arte para una pieza.

    `background` agrega el color de fondo de la portada: para las vistas previas del selector.
    """
    body = _DRAW[style](_rng(f"{style}:{seed}"), palette)
    if background:
        zone = text_zone(layout, palette)
        body = f'<rect width="{W}" height="{H}" fill="{zone.background}"/>' + body
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" '
        f'viewBox="0 0 {W} {H}">{body}{_protect(text_zone(layout, palette))}</svg>'
    )
