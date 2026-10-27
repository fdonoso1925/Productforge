# ruff: noqa: E501  (las cadenas de SVG son largas por naturaleza)
"""Infografías y gráficos como SVG, dibujados por código a partir de datos estructurados.

La IA no dibuja nada: elige un tipo de visual y llena sus textos (`Visual`); este módulo los
maqueta con la paleta y las tipografías de la plantilla del producto. Así son nítidos en cualquier
tamaño, no cuestan imágenes, quedan coherentes con la marca y todo el texto va escapado (lo que
escribe la IA o el usuario nunca llega al SVG sin escapar).

El texto se mide con las fuentes reales de la plantilla (Pillow) para partirlo en líneas y que
quepa dentro de cada pieza; lo que no cabe se corta con «…» en vez de salirse del dibujo.
"""

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

from PIL import ImageFont

from app.content.schemas.formats import Visual, VisualItem

if TYPE_CHECKING:
    from app.templates_engine.model import Template

W = 680  # ancho del lienzo; el SVG se escala al ancho de la página
PAD = 14
ELLIPSIS = "…"
ICONS = (
    "check",
    "x",
    "star",
    "flag",
    "clock",
    "target",
    "bulb",
    "warning",
    "arrow",
    "user",
    "book",
    "chart",
    "heart",
)


def esc(text: object) -> str:
    return escape(str(text), {'"': "&quot;"})


def num(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


# ───────────────────────────── medición de texto ─────────────────────────────


@lru_cache(maxsize=64)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont | None:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return None


class Meter:
    """Mide y parte texto con las fuentes de la plantilla (aproxima si faltara el archivo)."""

    def __init__(self, template: "Template") -> None:
        root = template.templates_root / "_fonts"
        from app.templates_engine.fonts import font_path

        def pick(spec, bold: bool) -> str:
            weights = sorted(spec.weights)
            weight = weights[-1] if bold else weights[0]
            return str(font_path(root, spec.family, weight))

        self.paths = {
            "heading": pick(template.fonts.heading, True),
            "bold": pick(template.fonts.body, True),
            "body": pick(template.fonts.body, False),
        }

    def width(self, text: str, size: int, face: str = "body") -> float:
        font = _font(self.paths[face], size)
        if font is None:
            return len(text) * size * 0.58
        return font.getlength(text)

    def wrap(
        self, text: str, size: int, max_w: float, face: str = "body", max_lines: int = 3
    ) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if self.width(candidate, size, face) <= max_w:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word
            while self.width(current, size, face) > max_w and len(current) > 1:  # palabra enorme
                cut = len(current) - 1
                while cut > 1 and self.width(current[:cut], size, face) > max_w:
                    cut -= 1
                lines.append(current[:cut])
                current = current[cut:]
        if current:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            last = lines[-1]
            while last and self.width(last + ELLIPSIS, size, face) > max_w:
                last = last[:-1].rstrip()
            lines[-1] = last + ELLIPSIS
        return lines or [""]


# ───────────────────────────── colores y primitivas ─────────────────────────────


def _lum(hex_color: str) -> float:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def on(background: str) -> str:
    """Negro o blanco, el que dé más contraste sobre ese fondo."""
    lum = _lum(background)
    return "#0B0B0D" if (lum + 0.05) / 0.05 >= 1.05 / (lum + 0.05) else "#FFFFFF"


@dataclass
class Canvas:
    meter: Meter
    palette: object
    heading: str
    body: str
    parts: list[str]

    def add(self, markup: str) -> None:
        self.parts.append(markup)

    @property
    def c(self):
        return self.palette

    def text(
        self,
        x: float,
        y: float,
        lines: list[str],
        size: int,
        fill: str,
        *,
        face: str = "body",
        anchor: str = "start",
        leading: float = 1.28,
    ) -> float:
        """Escribe varias líneas desde `y` (línea base de la primera); devuelve la `y` siguiente."""
        family = self.heading if face == "heading" else self.body
        weight = {"heading": 800, "bold": 700, "body": 400}[face]
        for line in lines:
            self.add(
                f'<text x="{num(x)}" y="{num(y)}" font-family="{esc(family)}" font-size="{size}" '
                f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{esc(line)}</text>'
            )
            y += size * leading
        return y

    def rect(self, x, y, w, h, fill, *, r=12, stroke="none", sw=1.5) -> None:
        self.add(
            f'<rect x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{num(h)}" rx="{r}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
        )

    def circle(self, cx, cy, r, fill, stroke="none", sw=1.5) -> None:
        self.add(
            f'<circle cx="{num(cx)}" cy="{num(cy)}" r="{num(r)}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw}"/>'
        )

    def badge(self, cx, cy, n: int, r=15, fill=None) -> None:
        fill = fill or self.c.primary
        self.circle(cx, cy, r, fill)
        self.add(
            f'<text x="{num(cx)}" y="{num(cy + 5)}" font-family="{esc(self.heading)}" font-size="{int(r * 1.05)}" '
            f'font-weight="800" fill="{on(fill)}" text-anchor="middle">{n}</text>'
        )

    def icon(self, name: str | None, cx: float, cy: float, size: float, color: str) -> None:
        if name not in ICONS:
            return
        s = size / 24
        body = _ICON_PATHS[name]
        self.add(
            f'<g transform="translate({num(cx - size / 2)} {num(cy - size / 2)}) scale({num(s)})" '
            f'fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" '
            f'stroke-linejoin="round">{body}</g>'
        )


_ICON_PATHS = {
    "check": '<polyline points="4,13 10,19 20,6"/>',
    "x": '<line x1="5" y1="5" x2="19" y2="19"/><line x1="19" y1="5" x2="5" y2="19"/>',
    "star": '<polygon points="12,2.5 14.8,9 21.5,9.5 16.4,14 18,21 12,17.3 6,21 7.6,14 2.5,9.5 9.2,9"/>',
    "flag": '<line x1="6" y1="3" x2="6" y2="21"/><polygon points="6,4 19,4 15.5,8.5 19,13 6,13"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><polyline points="12,7 12,12 16,14"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.3"/>',
    "bulb": '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"/>',
    "warning": '<polygon points="12,3 22,20 2,20"/><line x1="12" y1="9" x2="12" y2="14"/><line x1="12" y1="17" x2="12" y2="17.2"/>',
    "arrow": '<line x1="4" y1="12" x2="20" y2="12"/><polyline points="13,5 20,12 13,19"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "book": '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><line x1="8" y1="8" x2="15" y2="8"/>',
    "chart": '<polyline points="3,18 9,11 13,15 21,6"/><line x1="3" y1="21" x2="21" y2="21"/>',
    "heart": '<path d="M12 20s-8-5.2-8-11a4.5 4.5 0 0 1 8-2.6A4.5 4.5 0 0 1 20 9c0 5.8-8 11-8 11z"/>',
}


def _chunks(items: list[VisualItem], limit: int) -> list[VisualItem]:
    return [i for i in items if i.label.strip()][:limit]


# ───────────────────────────── tipos de visual ─────────────────────────────


def process(cv: Canvas, v: Visual) -> float:
    items = _chunks(v.items, 6)
    n = len(items)
    cols = n if n <= 4 else 3
    rows = math.ceil(n / cols)
    gap = 26
    card_w = (W - gap * (cols - 1)) / cols
    inner = card_w - 2 * PAD
    layout = []
    for it in items:
        label = cv.meter.wrap(it.label, 15, inner, "bold", 2)
        detail = cv.meter.wrap(it.detail, 12, inner, "body", 4) if it.detail else []
        layout.append((label, detail))
    row_h = max(60 + len(lb) * 19 + len(dt) * 16 for lb, dt in layout) + 6
    for i, (it, (label, detail)) in enumerate(zip(items, layout, strict=True)):
        r, c = divmod(i, cols)
        x, y = c * (card_w + gap), r * (row_h + 22)
        cv.rect(x, y, card_w, row_h, cv.c.surface, stroke=cv.c.primary, sw=1.2)
        cv.badge(x + PAD + 14, y + PAD + 14, i + 1)
        cv.icon(it.icon, x + card_w - PAD - 14, y + PAD + 14, 24, cv.c.secondary)
        ty = cv.text(x + PAD, y + 60, label, 15, cv.c.text, face="bold")
        cv.text(x + PAD, ty + 2, detail, 12, cv.c.muted)
        if c < cols - 1 and i < n - 1:  # flecha hacia la siguiente tarjeta
            ax, ay = x + card_w + gap / 2, y + row_h / 2
            cv.add(
                f'<polygon points="{num(ax - 7)},{num(ay - 9)} {num(ax + 7)},{num(ay)} {num(ax - 7)},{num(ay + 9)}" fill="{cv.c.accent}"/>'
            )
    return rows * row_h + (rows - 1) * 22


def timeline(cv: Canvas, v: Visual) -> float:
    items = _chunks(v.items, 7)
    n = len(items)
    left, right = 50, W - 50
    step = (right - left) / max(n - 1, 1)
    block_w = min(max(step * 1.8, 130), 200)
    blocks = []
    for it in items:
        label = cv.meter.wrap(it.label, 14, block_w, "bold", 2)
        detail = cv.meter.wrap(it.detail, 12, block_w, "body", 3) if it.detail else []
        blocks.append((label, detail, len(label) * 18 + len(detail) * 15))
    above = max((h for i, (_, _, h) in enumerate(blocks) if i % 2 == 0), default=0) + 14
    below = max((h for i, (_, _, h) in enumerate(blocks) if i % 2 == 1), default=0) + 14
    mid = above + 36
    cv.add(
        f'<line x1="{left - 24}" y1="{mid}" x2="{right + 24}" y2="{mid}" stroke="{cv.c.primary}" stroke-width="4" stroke-linecap="round"/>'
    )
    for i, (_it, (label, detail, h)) in enumerate(zip(items, blocks, strict=True)):
        x = left + i * step if n > 1 else W / 2
        cv.badge(x, mid, i + 1, r=14, fill=cv.c.secondary if i % 2 else cv.c.primary)
        top = i % 2 == 0
        cv.add(
            f'<line x1="{num(x)}" y1="{mid + (-14 if top else 14)}" x2="{num(x)}" y2="{mid + (-30 if top else 30)}" stroke="{cv.c.muted}" stroke-width="1.5"/>'
        )
        y0 = (mid - 36 - h + 14) if top else (mid + 36 + 14)
        anchor, tx = "middle", x
        if x - block_w / 2 < 0:
            anchor, tx = "start", 0
        elif x + block_w / 2 > W:
            anchor, tx = "end", W
        ty = cv.text(tx, y0, label, 14, cv.c.text, face="bold", anchor=anchor, leading=1.3)
        cv.text(tx, ty, detail, 12, cv.c.muted, anchor=anchor)
    return mid + 36 + below + 6


def cycle(cv: Canvas, v: Visual) -> float:
    items = _chunks(v.items, 6)
    n = len(items)
    radius, node_r, label_w = 105, 22, 170
    cx = W / 2
    texts = []
    for it in items:
        label = cv.meter.wrap(it.label, 14, label_w, "bold", 2)
        detail = cv.meter.wrap(it.detail, 12, label_w, "body", 3) if it.detail else []
        texts.append((label, detail))
    tallest = max(len(a) * 18 + len(b) * 15 for a, b in texts)
    cy = radius + node_r + tallest + 26
    cv.circle(cx, cy, radius, "none", stroke=cv.c.primary, sw=2.5)
    for i in range(n):  # flechas en el arco, entre un nodo y el siguiente
        mid = -math.pi / 2 + (i + 0.5) * 2 * math.pi / n
        ax, ay = cx + radius * math.cos(mid), cy + radius * math.sin(mid)
        tx, ty_ = -math.sin(mid), math.cos(mid)  # tangente
        p1 = (ax + tx * 9, ay + ty_ * 9)
        p2 = (ax - tx * 7 + ty_ * 8, ay - ty_ * 7 - tx * 8)
        p3 = (ax - tx * 7 - ty_ * 8, ay - ty_ * 7 + tx * 8)
        cv.add(
            f'<polygon points="{num(p1[0])},{num(p1[1])} {num(p2[0])},{num(p2[1])} {num(p3[0])},{num(p3[1])}" fill="{cv.c.accent}"/>'
        )
    for i, (_it, (label, detail)) in enumerate(zip(items, texts, strict=True)):
        ang = -math.pi / 2 + i * 2 * math.pi / n
        nx, ny = cx + radius * math.cos(ang), cy + radius * math.sin(ang)
        cv.badge(nx, ny, i + 1, r=node_r)
        side = math.cos(ang)
        if abs(side) < 0.25:
            anchor, lx = "middle", nx
        elif side > 0:
            anchor, lx = "start", nx + node_r + 12
        else:
            anchor, lx = "end", nx - node_r - 12
        h = len(label) * 18 + len(detail) * 15
        if abs(side) < 0.25:
            ly = ny - node_r - 10 - h + 14 if math.sin(ang) < 0 else ny + node_r + 22
        else:
            ly = ny - h / 2 + 14
        end = cv.text(lx, ly, label, 14, cv.c.text, face="bold", anchor=anchor, leading=1.3)
        cv.text(lx, end, detail, 12, cv.c.muted, anchor=anchor)
    return cy + radius + node_r + tallest + 30


def _tiered(cv: Canvas, v: Visual, *, inverted: bool) -> float:
    items = _chunks(v.items, 6)
    n = len(items)
    shape_w, layer_h, gap = 280, 62, 6
    text_x, text_w = shape_w + 34, W - shape_w - 34
    fills = [cv.c.primary, cv.c.secondary, cv.c.accent, cv.c.tip, cv.c.exercise, cv.c.muted]
    for i, it in enumerate(items):
        y = i * (layer_h + gap)
        f0, f1 = (i / n, (i + 1) / n) if not inverted else (1 - i / n, 1 - (i + 1) / n)
        w0, w1 = 50 + f0 * (shape_w - 50), 50 + f1 * (shape_w - 50)
        cx = shape_w / 2
        fill = fills[i % len(fills)]
        cv.add(
            f'<polygon points="{num(cx - w0 / 2)},{num(y)} {num(cx + w0 / 2)},{num(y)} '
            f'{num(cx + w1 / 2)},{num(y + layer_h)} {num(cx - w1 / 2)},{num(y + layer_h)}" fill="{fill}"/>'
        )
        cv.add(
            f'<text x="{num(cx)}" y="{num(y + layer_h / 2 + 6)}" font-family="{esc(cv.heading)}" font-size="20" '
            f'font-weight="800" fill="{on(fill)}" text-anchor="middle">{i + 1}</text>'
        )
        label = cv.meter.wrap(it.label, 15, text_w, "bold", 2)
        detail = cv.meter.wrap(it.detail, 12, text_w, "body", 2) if it.detail else []
        h = len(label) * 19 + len(detail) * 15
        ty = cv.text(text_x, y + (layer_h - h) / 2 + 14, label, 15, cv.c.text, face="bold")
        cv.text(text_x, ty, detail, 12, cv.c.muted)
    return n * (layer_h + gap) - gap


def pyramid(cv: Canvas, v: Visual) -> float:
    return _tiered(cv, v, inverted=False)


def funnel(cv: Canvas, v: Visual) -> float:
    return _tiered(cv, v, inverted=True)


def matrix(cv: Canvas, v: Visual) -> float:
    items = _chunks(v.items, 4)
    left, gap = 34, 14
    cell_w = (W - left - gap) / 2
    inner = cell_w - 2 * PAD
    texts = [
        (
            cv.meter.wrap(it.label, 15, inner, "bold", 2),
            cv.meter.wrap(it.detail, 12, inner, "body", 3) if it.detail else [],
        )
        for it in items
    ]
    cell_h = max((len(a) * 19 + len(b) * 15 for a, b in texts), default=40) + 2 * PAD + 6
    fills = [cv.c.surface, cv.c.surface, cv.c.surface, cv.c.surface]
    for i, (label, detail) in enumerate(texts):
        r, c = divmod(i, 2)
        x, y = left + c * (cell_w + gap), r * (cell_h + gap)
        cv.rect(
            x, y, cell_w, cell_h, fills[i], stroke=cv.c.primary if i == 1 else cv.c.muted, sw=1.4
        )
        cv.badge(
            x + PAD + 4, y + PAD + 6, i + 1, r=11, fill=cv.c.primary if i == 1 else cv.c.secondary
        )
        ty = cv.text(x + PAD + 24, y + PAD + 11, label, 15, cv.c.text, face="bold")
        cv.text(x + PAD + 24, ty, detail, 12, cv.c.muted)
    total = 2 * cell_h + gap
    # Ejes: vertical (izquierda, de abajo hacia arriba) y horizontal (abajo, hacia la derecha).
    cv.add(
        f'<line x1="14" y1="{num(total)}" x2="14" y2="6" stroke="{cv.c.muted}" stroke-width="2"/>'
    )
    cv.add(f'<polygon points="8,12 14,0 20,12" fill="{cv.c.muted}"/>')
    cv.add(
        f'<text x="26" y="{num(total / 2)}" font-family="{esc(cv.body)}" font-size="12" fill="{cv.c.muted}" '
        f'text-anchor="middle" transform="rotate(-90 26 {num(total / 2)})" dy="-14">{esc(v.axis_y)}</text>'
    )
    cv.add(
        f'<line x1="{left}" y1="{num(total + 14)}" x2="{W - 6}" y2="{num(total + 14)}" stroke="{cv.c.muted}" stroke-width="2"/>'
    )
    cv.add(
        f'<polygon points="{W - 12},{num(total + 8)} {W},{num(total + 14)} {W - 12},{num(total + 20)}" fill="{cv.c.muted}"/>'
    )
    cv.text(W / 2, total + 34, [v.axis_x], 12, cv.c.muted, anchor="middle")
    return total + 42


def comparison(cv: Canvas, v: Visual) -> float:
    left_items, right_items = _chunks(v.items, 6), _chunks(v.right_items, 6)
    n = max(len(left_items), len(right_items))
    gap = 18
    col_w = (W - gap) / 2
    inner = col_w - 2 * PAD - 30
    head_h = 38
    rows = []
    for i in range(n):
        pair = []
        for items in (left_items, right_items):
            it = items[i] if i < len(items) else None
            pair.append(cv.meter.wrap(it.label, 14, inner, "body", 3) if it else [])
        rows.append(pair)
    row_h = max((len(c) * 18 for pair in rows for c in pair), default=18) + 2 * PAD
    for col, (title, fill, icon, color) in enumerate(
        [
            (v.left_title, cv.c.warning, "x", cv.c.warning),
            (v.right_title, cv.c.tip, "check", cv.c.tip),
        ]
    ):
        x = col * (col_w + gap)
        cv.rect(x, 0, col_w, head_h, fill, r=19)
        head = cv.meter.wrap(title, 15, col_w - 2 * PAD, "bold", 1)
        cv.text(x + col_w / 2, 25, head, 15, on(fill), face="bold", anchor="middle")
        for i, pair in enumerate(rows):
            y = head_h + 10 + i * (row_h + 8)
            cv.rect(x, y, col_w, row_h, cv.c.surface, r=10)
            if pair[col]:
                cv.icon(icon, x + PAD + 10, y + row_h / 2, 18, color)
                cv.text(
                    x + PAD + 30,
                    y + row_h / 2 - (len(pair[col]) - 1) * 9 + 5,
                    pair[col],
                    14,
                    cv.c.text,
                    leading=1.28,
                )
    return head_h + 10 + n * (row_h + 8) - 8


def cards(cv: Canvas, v: Visual) -> float:
    items = _chunks(v.items, 4)
    n = len(items)
    cols = 2 if n == 4 else max(n, 1)
    gap = 16
    card_w = (W - gap * (cols - 1)) / cols
    inner = card_w - 2 * PAD - 4
    layout = [
        (
            cv.meter.wrap(it.label, 15, inner, "bold", 2),
            cv.meter.wrap(it.detail, 12, inner, "body", 5) if it.detail else [],
        )
        for it in items
    ]
    h = max((len(a) * 19 + len(b) * 15 for a, b in layout), default=30) + 74
    rows = math.ceil(n / cols)
    fills = [cv.c.primary, cv.c.secondary, cv.c.accent, cv.c.tip]
    for i, (it, (label, detail)) in enumerate(zip(items, layout, strict=True)):
        r, c = divmod(i, cols)
        x, y = c * (card_w + gap), r * (h + gap)
        cv.rect(x, y, card_w, h, cv.c.surface, stroke=fills[i % 4], sw=1.6, r=14)
        cv.circle(x + PAD + 20, y + PAD + 20, 22, fills[i % 4])
        if it.icon in ICONS:
            cv.icon(it.icon, x + PAD + 20, y + PAD + 20, 24, on(fills[i % 4]))
        else:
            cv.add(
                f'<text x="{num(x + PAD + 20)}" y="{num(y + PAD + 27)}" font-family="{esc(cv.heading)}" font-size="20" '
                f'font-weight="800" fill="{on(fills[i % 4])}" text-anchor="middle">{i + 1}</text>'
            )
        ty = cv.text(x + PAD + 2, y + 76, label, 15, cv.c.text, face="bold")
        cv.text(x + PAD + 2, ty + 2, detail, 12, cv.c.muted)
    return rows * h + (rows - 1) * gap


def checklist(cv: Canvas, v: Visual) -> float:
    items = _chunks(v.items, 8)
    inner = W - 2 * PAD - 44
    rows = [
        (
            cv.meter.wrap(it.label, 15, inner, "bold", 2),
            cv.meter.wrap(it.detail, 12, inner, "body", 2) if it.detail else [],
        )
        for it in items
    ]
    heights = [len(a) * 19 + len(b) * 15 + 18 for a, b in rows]
    total = sum(heights) + 2 * PAD
    cv.rect(0, 0, W, total, cv.c.surface, stroke=cv.c.primary, sw=1.4, r=14)
    y = PAD
    for (label, detail), h in zip(rows, heights, strict=True):
        cv.rect(PAD + 2, y + 6, 22, 22, cv.c.primary, r=6)
        cv.icon("check", PAD + 13, y + 17, 14, on(cv.c.primary))
        ty = cv.text(PAD + 36, y + 22, label, 15, cv.c.text, face="bold")
        cv.text(PAD + 36, ty, detail, 12, cv.c.muted)
        y += h
    return total


def _bar_rows(v: Visual) -> list[VisualItem]:
    return [i for i in _chunks(v.items, 8) if i.value is not None and i.value >= 0]


def _note(cv: Canvas, v: Visual, y: float, labels: dict[str, str]) -> float:
    if not v.illustrative:
        return y
    cv.text(
        W, y + 12, [labels.get("illustrative", "Ejemplo ilustrativo")], 11, cv.c.muted, anchor="end"
    )
    return y + 22


def bars(cv: Canvas, v: Visual, labels: dict[str, str]) -> float:
    items = _bar_rows(v)
    label_w, value_w = 190, 80
    track_w = W - label_w - value_w - 20
    peak = max((i.value for i in items), default=1) or 1
    y = 0.0
    colors = [cv.c.primary, cv.c.secondary, cv.c.accent, cv.c.tip, cv.c.exercise, cv.c.warning]
    for i, it in enumerate(items):
        lines = cv.meter.wrap(it.label, 14, label_w - 10, "bold", 2)
        h = max(len(lines) * 18, 20) + 18
        cv.text(0, y + h / 2 - (len(lines) - 1) * 9 + 4, lines, 14, cv.c.text, face="bold")
        cv.rect(label_w, y + h / 2 - 11, track_w, 22, cv.c.surface, r=11)
        cv.rect(
            label_w,
            y + h / 2 - 11,
            max(track_w * (it.value or 0) / peak, 8),
            22,
            colors[i % len(colors)],
            r=11,
        )
        cv.text(
            label_w + track_w + 14,
            y + h / 2 + 5,
            [f"{num(it.value or 0)}{v.unit}"],
            14,
            cv.c.text,
            face="bold",
        )
        y += h
    return _note(cv, v, y, labels)


def donut(cv: Canvas, v: Visual, labels: dict[str, str]) -> float:
    items = [i for i in _bar_rows(v) if (i.value or 0) > 0][:7]
    total = sum(i.value or 0 for i in items) or 1
    cx, cy, ro, ri = 150, 150, 120, 66
    colors = [
        cv.c.primary,
        cv.c.secondary,
        cv.c.accent,
        cv.c.tip,
        cv.c.exercise,
        cv.c.warning,
        cv.c.muted,
    ]
    start = -math.pi / 2
    for i, it in enumerate(items):
        sweep = 2 * math.pi * (it.value or 0) / total
        end = start + sweep - (0.02 if len(items) > 1 else 0)
        large = 1 if sweep > math.pi else 0
        p = lambda r, a: (cx + r * math.cos(a), cy + r * math.sin(a))  # noqa: E731
        (x1, y1), (x2, y2), (x3, y3), (x4, y4) = p(ro, start), p(ro, end), p(ri, end), p(ri, start)
        if len(items) == 1:
            cv.circle(cx, cy, (ro + ri) / 2, "none", stroke=colors[0], sw=ro - ri)
        else:
            cv.add(
                f'<path d="M{num(x1)} {num(y1)} A{ro} {ro} 0 {large} 1 {num(x2)} {num(y2)} L{num(x3)} {num(y3)} '
                f'A{ri} {ri} 0 {large} 0 {num(x4)} {num(y4)} Z" fill="{colors[i % len(colors)]}"/>'
            )
        start += sweep
    ly = max(30, cy - len(items) * 20)
    for i, it in enumerate(items):
        cv.circle(320, ly + 4, 8, colors[i % len(colors)])
        lines = cv.meter.wrap(it.label, 14, 270, "bold", 2)
        end = cv.text(340, ly + 9, lines, 14, cv.c.text, face="bold")
        share = f"{num(100 * (it.value or 0) / total)} %"
        if v.unit.strip() == "%" or not v.unit:
            detail_line = share
        else:
            detail_line = f"{num(it.value or 0)}{v.unit} · {share}"
        cv.text(340, end - 4, [detail_line], 12, cv.c.muted)
        ly += max(len(lines) * 18 + 22, 42)
    return _note(cv, v, max(cy + ro + 10, ly), labels)


RENDERERS = {
    "process": process,
    "timeline": timeline,
    "cycle": cycle,
    "pyramid": pyramid,
    "funnel": funnel,
    "matrix": matrix,
    "comparison": comparison,
    "cards": cards,
    "checklist": checklist,
}
WITH_LABELS = {"bars": bars, "donut": donut}

ILLUSTRATIVE = {"es-LATAM": "Ejemplo ilustrativo", "pt-BR": "Exemplo ilustrativo"}


def render_visual(v: Visual, template: "Template", market: str = "es-LATAM") -> str:
    """El SVG completo de un visual; cadena vacía si no hay nada que dibujar."""
    drawable = (
        _bar_rows(v)
        if v.kind in WITH_LABELS
        else _chunks(v.items, 1) or (_chunks(v.right_items, 1) if v.kind == "comparison" else [])
    )
    if not drawable:
        return ""  # nada que dibujar: mejor sin visual que un dibujo roto
    cv = Canvas(
        meter=Meter(template),
        palette=template.palette,
        heading=template.fonts.heading.family,
        body=template.fonts.body.family,
        parts=[],
    )
    if v.kind in RENDERERS:
        height = RENDERERS[v.kind](cv, v)
    elif v.kind in WITH_LABELS:
        height = WITH_LABELS[v.kind](
            cv, v, {"illustrative": ILLUSTRATIVE.get(market, "Ejemplo ilustrativo")}
        )
    else:  # pragma: no cover - el schema ya lo impide
        return ""
    if not cv.parts:
        return ""
    height = max(height, 40) + 4
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {num(height)}" width="{W}" '
        f'height="{num(height)}" role="img" aria-label="{esc(v.title)}" class="visual-svg">'
        f"<title>{esc(v.title)}</title>{''.join(cv.parts)}</svg>"
    )


__all__ = ["ICONS", "render_visual"]
