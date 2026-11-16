"""Motor de motion graphics: 5 escenas animadas cuadro a cuadro con Pillow.

Cada escena es una lista de elementos (sprites ya dibujados) con su posición, el momento en que
entra y cómo entra (sube con fade, aparece con rebote, se revela de izquierda a derecha). Los
sprites se dibujan UNA vez fuera del bucle; cada cuadro solo los compone. La misma lista da la
línea de tiempo de efectos de sonido (pop, golpe, ding, whoosh) para que el audio quede en sync.

Reglas de la skill: el gancho está completo antes de los 2 s, entradas escalonadas de 0,3–0,4 s,
fade-out de 0,22 s al final de cada escena, botón que late, fondo vivo con formas que flotan,
todo dentro de la zona segura de Meta (la misma de los anuncios: `ad_templates/specs.json`).
"""

import math
import random
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.generators.cover_image import hex_rgb
from app.video.schemas import VideoRatio, VideoScript
from app.video.style import VideoFonts, VideoPalette

FPS = 30
FADE_OUT = 0.22
# Duraciones alineadas a pulsos de 0,5 s (120 bpm): la música y los cortes coinciden.
SCENES: tuple[tuple[str, float], ...] = (
    ("hook", 3.0),
    ("problem", 4.0),
    ("solution", 3.5),
    ("benefits", 3.5),
    ("cta", 3.5),
)
DURATION = sum(d for _, d in SCENES)
SIZES: dict[str, tuple[int, int]] = {"9x16": (1080, 1920), "4x5": (1080, 1350)}
# Zona segura (fracción del alto arriba/abajo): la de Meta para Reels y un margen prudente en Feed.
SAFE: dict[str, tuple[float, float]] = {"9x16": (0.14, 0.35), "4x5": (0.06, 0.06)}
SIDE = 90
VISIBLE_ALPHA = 48  # por debajo de esta opacidad (sombra tenue) no tapa nada
ARROW_ROOM = 120  # margen derecho del botón del CTA, donde se mueve la flecha

Anim = Literal["up", "pop", "fade", "reveal"]
Sound = Literal["pop", "thud", "ding", "whoosh"]


# ───────────────────────────── utilidades de animación ─────────────────────────────


def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return max(a, min(b, x))


def prog(t: float, start: float, dur: float) -> float:
    return clamp((t - start) / dur)


def ease_out(p: float) -> float:
    return 1 - (1 - p) ** 3


def ease_back(p: float, s: float = 1.7) -> float:
    p -= 1
    return 1 + (s + 1) * p**3 + s * p**2


def rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    return (*hex_rgb(hex_color), alpha)


def put(frame: Image.Image, sprite: Image.Image, cx: float, cy: float, scale=1.0, alpha=1.0):
    """Compone `sprite` centrado en (cx, cy) con escala y opacidad."""
    if alpha <= 0.01 or scale <= 0.01:
        return
    s = sprite
    if abs(scale - 1) > 0.005:
        size = (max(1, int(sprite.width * scale)), max(1, int(sprite.height * scale)))
        s = sprite.resize(size, Image.Resampling.BICUBIC)
    if alpha < 0.999:
        s = s.copy()
        s.putalpha(s.getchannel("A").point(lambda v: int(v * alpha)))
    x, y = int(cx - s.width / 2), int(cy - s.height / 2)
    frame.alpha_composite(s, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))


# ───────────────────────────── sprites ─────────────────────────────


def visible_box(im: Image.Image, threshold: int = VISIBLE_ALPHA) -> tuple[int, int, int, int]:
    """Recuadro de lo que se ve de un sprite: sin el margen transparente ni la cola casi
    invisible de la sombra difuminada."""
    mask = im.getchannel("A").point(lambda v: 255 if v > threshold else 0)
    return mask.getbbox() or (0, 0, im.width, im.height)


def wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if font.getlength(trial) <= max_w or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fit_font(make, text: str, size: int, max_w: int, max_lines: int, minimum: int = 26):
    """La fuente más grande (desde `size`) en la que el texto entra en `max_lines` líneas y
    ninguna palabra sola se pasa del ancho."""
    while True:
        font = make(size)
        lines = wrap(text, font, max_w)
        widest = max((font.getlength(w) for w in text.split()), default=0)
        if (len(lines) <= max_lines and widest <= max_w) or size <= minimum:
            return font, lines
        size = max(minimum, int(size * 0.92))


def text_sprite(
    lines: list[str], font: ImageFont.FreeTypeFont, color: str, align: str = "center"
) -> Image.Image:
    """Texto en un lienzo transparente ajustado, línea por línea."""
    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * 1.08)
    widths = [int(font.getlength(line)) for line in lines] or [1]
    w, h = max(widths) + 8, line_h * max(1, len(lines)) + 8
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, line in enumerate(lines):
        x = 4 if align == "left" else (w - widths[i]) // 2
        d.text((x, 4 + i * line_h), line, font=font, fill=rgba(color))
    return im


def hi(size: tuple[int, int], draw_fn) -> Image.Image:
    """Dibuja al doble de tamaño y reduce: bordes limpios en formas."""
    w, h = size
    im = Image.new("RGBA", (w * 2, h * 2), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(im), 2)
    return im.resize((w, h), Image.Resampling.LANCZOS)


def icon(kind: Literal["cross", "check"], color: str, size: int = 76) -> Image.Image:
    """Círculo con ✕ o ✓ dibujados como formas (sin depender de glifos de la fuente)."""

    def draw(d: ImageDraw.ImageDraw, k: int) -> None:
        s = size * k
        d.ellipse((0, 0, s - 1, s - 1), fill=rgba(color))
        width = max(3, round(s * 0.11))
        white = (255, 255, 255, 255)
        if kind == "cross":
            a, b = s * 0.32, s * 0.68
            d.line([(a, a), (b, b)], fill=white, width=width)
            d.line([(a, b), (b, a)], fill=white, width=width)
        else:
            d.line([(s * 0.27, s * 0.52), (s * 0.44, s * 0.68), (s * 0.74, s * 0.34)],
                   fill=white, width=width, joint="curve")  # fmt: skip

    return hi((size, size), draw)


def with_shadow(
    sprite: Image.Image, blur: int = 18, opacity: int = 70, dy: int = 12
) -> Image.Image:
    """El sprite con sombra suave, con margen suficiente para que la sombra no se corte."""
    margin = blur * 3
    w, h = sprite.width + 2 * margin, sprite.height + 2 * margin
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    alpha = Image.new("L", (w, h), 0)
    alpha.paste(sprite.getchannel("A"), (margin, margin + dy))
    alpha = alpha.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: v * opacity // 255)
    shadow.putalpha(alpha)
    shadow.alpha_composite(sprite, (margin, margin))
    return shadow


def card(
    width: int, rows: list[tuple[Image.Image, int]], pal: VideoPalette, icon_im=None
) -> Image.Image:
    """Tarjeta blanca redondeada: ícono a la izquierda y filas de texto apiladas."""
    pad_x, pad_y, gap = 34, 24, 4
    text_x = pad_x + (icon_im.width + 26 if icon_im else 0)
    text_h = sum(im.height for im, _ in rows) + gap * (len(rows) - 1)
    h = max(text_h, icon_im.height if icon_im else 0) + 2 * pad_y

    def draw(d: ImageDraw.ImageDraw, k: int) -> None:
        d.rounded_rectangle((0, 0, width * k - 1, h * k - 1), 30 * k, fill=rgba(pal.card))

    im = hi((width, h), draw)
    if icon_im:
        im.alpha_composite(icon_im, (pad_x, (h - icon_im.height) // 2))
    y = (h - text_h) // 2
    for row, _ in rows:
        im.alpha_composite(row, (text_x - 4, y))
        y += row.height + gap
    return with_shadow(im)


def pill(
    text_im: Image.Image, color: str, pad_x: int = 30, pad_y: int = 14, pad_right: int | None = None
) -> Image.Image:
    """Píldora de color con el texto; `pad_right` deja sitio a la flecha del botón."""
    right = pad_x if pad_right is None else pad_right
    w, h = text_im.width + pad_x + right, text_im.height + 2 * pad_y

    def draw(d: ImageDraw.ImageDraw, k: int) -> None:
        d.rounded_rectangle((0, 0, w * k - 1, h * k - 1), h * k // 2, fill=rgba(color))

    im = hi((w, h), draw)
    im.alpha_composite(text_im, (pad_x, pad_y))
    return im


def block(w: int, h: int, color: str) -> Image.Image:
    def draw(d: ImageDraw.ImageDraw, k: int) -> None:
        d.rounded_rectangle((0, 0, w * k - 1, h * k - 1), 14 * k, fill=rgba(color))

    return hi((w, h), draw)


def arrow(color: str, size: int = 40) -> Image.Image:
    def draw(d: ImageDraw.ImageDraw, k: int) -> None:
        s = size * k
        d.polygon([(s * 0.1, s * 0.42), (s * 0.55, s * 0.42), (s * 0.55, s * 0.18),
                   (s * 0.95, s * 0.5), (s * 0.55, s * 0.82), (s * 0.55, s * 0.58),
                   (s * 0.1, s * 0.58)], fill=rgba(color))  # fmt: skip

    return hi((size, size), draw)


# ───────────────────────────── escenas ─────────────────────────────


@dataclass
class Element:
    sprite: Image.Image
    cx: float
    cy: float
    start: float
    anim: Anim = "up"
    sound: Sound | None = "pop"
    pulse: bool = False  # el botón del CTA late después de entrar
    extra: Image.Image | None = None  # la flecha que se mueve dentro del botón


@dataclass
class Scene:
    name: str
    dur: float
    elements: list[Element] = field(default_factory=list)


@dataclass
class Layout:
    W: int
    H: int
    top: int
    bottom: int

    @property
    def content_w(self) -> int:
        return self.W - 2 * SIDE

    @property
    def room(self) -> int:
        """Alto útil de la zona segura."""
        return self.bottom - self.top

    def stack(self, items: list[tuple[Image.Image, bool]], gaps: list[int]) -> list[float]:
        """Centros verticales de una pila de sprites centrada en la zona segura.

        `(sprite, trim)`: con `trim` (tarjetas y mockups, que traen margen para la sombra) se
        apila por lo VISIBLE del sprite, así los espacios son reales y nada visible cae fuera; el
        texto se apila con su caja completa (el interlineado es parte del diseño). Si no cabe, se
        aprietan los espacios (los sprites ya se dibujaron para caber)."""
        boxes = []
        for im, trim in items:
            _, top, _, bottom = visible_box(im) if trim else (0, 0, im.width, im.height)
            boxes.append((top, bottom, im.height))
        visible = [bottom - top for top, bottom, _ in boxes]
        gaps = [max(0, g) for g in gaps]
        total = sum(visible) + sum(gaps)
        if total > self.room and sum(gaps):
            shrink = max(0.0, 1 - (total - self.room) / sum(gaps))
            gaps = [round(g * shrink) for g in gaps]
            total = sum(visible) + sum(gaps)
        y = self.top + max(0, (self.room - total) / 2)
        centers = []
        for i, (top, bottom, height) in enumerate(boxes):
            centers.append(y - top + height / 2)  # el borde visible de arriba cae en `y`
            y += bottom - top + (gaps[i] if i < len(gaps) else 0)
        return centers


def build_scenes(
    script: VideoScript,
    *,
    product_name: str,
    pal: VideoPalette,
    fonts: VideoFonts,
    ratio: VideoRatio = "9x16",
    mockup_book: Image.Image | None = None,
    mockup_bundle: Image.Image | None = None,
) -> tuple[Layout, list[Scene]]:
    W, H = SIZES[ratio]
    top_f, bottom_f = SAFE[ratio]
    lay = Layout(W, H, round(H * top_f), round(H * (1 - bottom_f)))
    cw = lay.content_w
    tall = ratio == "9x16"
    k = 1.0 if tall else 0.92  # el 4:5 tiene un poco menos de alto útil por escena
    cx = W / 2
    scenes: list[Scene] = []

    def title(text: str, size: int, color: str, lines: int = 2) -> Image.Image:
        font, wrapped = fit_font(fonts.heading_at, text, round(size * k), cw, lines)
        return text_sprite(wrapped, font, color)

    # 1. Gancho: etiqueta + 2-3 líneas; la destacada sobre un bloque de acento que crece.
    hook = Scene("hook", SCENES[0][1])
    tag_font, tag_lines = fit_font(
        fonts.bold_at, script.hook_tag.upper(), round(38 * k), cw - 60, 1
    )
    tag = pill(text_sprite(tag_lines, tag_font, pal.on_accent), pal.accent)
    lines = [ln for ln in script.hook_lines if ln.strip()][:3]
    highlight = script.hook_highlight if 0 <= script.hook_highlight < len(lines) else -1
    line_sprites = []
    for i, line in enumerate(lines):
        size = 128 if i == highlight else 92
        color = pal.on_accent if i == highlight else pal.text
        font, wrapped = fit_font(fonts.heading_at, line, round(size * k), cw - 60, 1)
        line_sprites.append(text_sprite(wrapped, font, color))
    padded = [line_sprites[i] if i != highlight else _padded(line_sprites[i], 26, 14)
              for i in range(len(line_sprites))]  # fmt: skip
    ys = lay.stack([(tag, False), *[(s, False) for s in padded]], [44, *[18] * (len(padded) - 1)])
    hook.elements.append(Element(tag, cx, ys[0], 0.1, "pop"))
    for i, sprite in enumerate(line_sprites):
        start = 0.35 + 0.35 * i
        if i == highlight:
            back = block(padded[i].width, padded[i].height, pal.accent)
            hook.elements.append(Element(back, cx, ys[i + 1], start, "reveal", None))
            hook.elements.append(Element(sprite, cx, ys[i + 1], start + 0.12, "pop"))
        else:
            hook.elements.append(Element(sprite, cx, ys[i + 1], start, "up"))
    scenes.append(hook)

    # 2. Problema: título + 3 tarjetas con ✕.
    problem = Scene("problem", SCENES[1][1])
    head = title(script.problem_title, 82, pal.text)
    cross = icon("cross", pal.bad)
    cards = []
    for item in script.problems[:3]:
        font, wrapped = fit_font(fonts.bold_at, item, round(50 * k), cw - 190, 2)
        cards.append(card(cw, [(text_sprite(wrapped, font, pal.ink, "left"), 0)], pal, cross))
    ys = lay.stack([(head, False), *[(c, True) for c in cards]], [34, *[22] * (len(cards) - 1)])
    problem.elements.append(Element(head, cx, ys[0], 0.15, "up"))
    for i, c in enumerate(cards):
        problem.elements.append(Element(c, cx, ys[i + 1], 0.8 + 0.4 * i, "pop", "thud"))
    scenes.append(problem)

    # 3. Solución: frase + palabra clave grande + mockup de la portada + qué logra.
    solution = Scene("solution", SCENES[2][1])
    open_line = title(script.solution_title, 80, pal.text, 1)
    big = title(script.solution_big, 140, pal.accent, 2)
    caption_font, caption_lines = fit_font(
        fonts.regular_at, script.solution_caption, round(44 * k), cw - 40, 3
    )
    caption = text_sprite(caption_lines, caption_font, pal.sub)
    stack: list[tuple[Image.Image, bool]] = [(open_line, False), (big, False)]
    visual = None
    if mockup_book is not None:
        # El mockup ocupa lo que dejan los textos (nunca empuja nada fuera de la zona segura).
        room = lay.room - open_line.height - big.height - caption.height - 58
        visual = fit_height(mockup_book, min(round((480 if tall else 360) * k), room))
        stack.append((visual, True))
    stack.append((caption, False))
    ys = lay.stack(stack, [10, *([24] if visual else []), 24])
    solution.elements.append(Element(open_line, cx, ys[0], 0.15, "up"))
    solution.elements.append(Element(big, cx, ys[1], 0.6, "pop"))
    if visual is not None:
        solution.elements.append(Element(visual, cx, ys[2], 0.9, "pop"))
    solution.elements.append(Element(caption, cx, ys[-1], 1.4, "fade", None))
    scenes.append(solution)

    # 4. Qué recibes: título + 3 tarjetas con ✓ (título y para qué sirve).
    benefits = Scene("benefits", SCENES[3][1])
    head = title(script.benefits_title, 82, pal.text)
    check = icon("check", pal.good)
    cards = []
    for b in script.benefits[:3]:
        tfont, tlines = fit_font(fonts.bold_at, b.title, round(50 * k), cw - 190, 1)
        dfont, dlines = fit_font(fonts.regular_at, b.detail, round(38 * k), cw - 190, 2)
        rows = [(text_sprite(tlines, tfont, pal.ink, "left"), 0),
                (text_sprite(dlines, dfont, pal.ink_soft, "left"), 0)]  # fmt: skip
        cards.append(card(cw, rows, pal, check))
    ys = lay.stack([(head, False), *[(c, True) for c in cards]], [34, *[20] * (len(cards) - 1)])
    benefits.elements.append(Element(head, cx, ys[0], 0.15, "up"))
    for i, c in enumerate(cards):
        benefits.elements.append(Element(c, cx, ys[i + 1], 0.6 + 0.4 * i, "pop", "ding"))
    scenes.append(benefits)

    # 5. CTA: pack del producto + nombre + botón que late con flecha + línea de confianza.
    cta = Scene("cta", SCENES[4][1])
    name = title(product_name, 84, pal.text, 3)
    bfont, blines = fit_font(fonts.bold_at, script.cta_button.upper(), round(52 * k), cw - 200, 1)
    btn_text = text_sprite(blines, bfont, pal.on_accent)
    button = pill(btn_text, pal.accent, pad_x=64, pad_y=30, pad_right=ARROW_ROOM)
    sub_font, sub_lines = fit_font(fonts.regular_at, script.cta_sub, round(40 * k), cw, 2)
    sub = text_sprite(sub_lines, sub_font, pal.sub)
    stack: list[tuple[Image.Image, bool]] = []
    pack = None
    if mockup_bundle is not None:
        room = lay.room - name.height - button.height - sub.height - 90
        pack = fit_height(mockup_bundle, min(round((380 if tall else 280) * k), room))
        stack.append((pack, True))
    stack += [(name, False), (button, False), (sub, False)]
    gaps = [*([24] if pack else []), 40, 26]
    ys = lay.stack(stack, gaps)
    i = 0
    if pack is not None:
        cta.elements.append(Element(pack, cx, ys[0], 0.1, "pop"))
        i = 1
    cta.elements.append(Element(name, cx, ys[i], 0.35, "up"))
    cta.elements.append(
        Element(button, cx, ys[i + 1], 1.0, "pop", "ding", pulse=True, extra=arrow(pal.on_accent))
    )
    cta.elements.append(Element(sub, cx, ys[i + 2], 1.4, "fade", None))
    scenes.append(cta)
    return lay, scenes


def fit_height(image: Image.Image, height: int) -> Image.Image:
    """La imagen escalada a `height` px de alto (mínimo 80, para que siga reconociéndose)."""
    height = max(80, height)
    width = max(1, round(image.width * height / image.height))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _padded(sprite: Image.Image, px: int, py: int) -> Image.Image:
    out = Image.new("RGBA", (sprite.width + 2 * px, sprite.height + 2 * py), (0, 0, 0, 0))
    out.alpha_composite(sprite, (px, py))
    return out


# ───────────────────────────── fondo vivo ─────────────────────────────


def background(lay: Layout, pal: VideoPalette, seed: str) -> tuple[Image.Image, list]:
    """Fondo de color y formas decorativas (anillos, puntos, cruces) que flotan suave."""
    base = Image.new("RGBA", (lay.W, lay.H), rgba(pal.bg))
    rnd = random.Random(seed)  # noqa: S311 — decoración, no seguridad
    shapes = []
    for i in range(6):
        size = rnd.randint(70, 150)
        kind = ("ring", "dot", "plus")[i % 3]

        def draw(d: ImageDraw.ImageDraw, k: int, kind=kind, size=size) -> None:
            s = size * k
            color = rgba(pal.deco)
            if kind == "ring":
                d.ellipse((0, 0, s - 1, s - 1), outline=color, width=max(4, s // 9))
            elif kind == "dot":
                d.ellipse((s * 0.2, s * 0.2, s * 0.8, s * 0.8), fill=color)
            else:
                w = max(6, s // 6)
                d.rounded_rectangle((s / 2 - w / 2, 0, s / 2 + w / 2, s), w // 2, fill=color)
                d.rounded_rectangle((0, s / 2 - w / 2, s, s / 2 + w / 2), w // 2, fill=color)

        sprite = hi((size, size), draw)
        x = rnd.choice([rnd.uniform(0.03, 0.2), rnd.uniform(0.8, 0.97)]) * lay.W
        y = rnd.uniform(0.06, 0.94) * lay.H
        shapes.append((sprite, x, y, rnd.uniform(0, math.tau), rnd.uniform(0.6, 1.1)))
    return base, shapes


# ───────────────────────────── cuadros y sonido ─────────────────────────────


def frame_at(
    lay: Layout, scene: Scene, t: float, base: Image.Image, shapes: list, global_t: float
) -> Image.Image:
    frame = base.copy()
    for sprite, x, y, phase, speed in shapes:
        put(frame, sprite, x, y + 18 * math.sin(global_t * speed + phase))
    fade = clamp((scene.dur - t) / FADE_OUT)
    for el in scene.elements:
        p = prog(t, el.start, 0.42)
        if p <= 0:
            continue
        if el.anim == "up":
            e = ease_out(p)
            put(frame, el.sprite, el.cx, el.cy + 60 * (1 - e), 1.0, e * fade)
        elif el.anim == "pop":
            scale = 0.55 + 0.45 * ease_back(p)
            if el.pulse and p >= 1:
                scale = 1 + 0.045 * math.sin(6 * (t - el.start))
            put(frame, el.sprite, el.cx, el.cy, scale, clamp(p * 2) * fade)
            if el.extra is not None and p >= 1:
                dx = 10 * math.sin(7 * t)
                ax = el.cx + el.sprite.width * scale / 2 - ARROW_ROOM / 2 + dx
                put(frame, el.extra, ax, el.cy, scale, fade)
        elif el.anim == "fade":
            put(frame, el.sprite, el.cx, el.cy, 1.0, ease_out(p) * fade)
        elif el.anim == "reveal":
            e = ease_out(prog(t, el.start, 0.35))
            width = max(1, int(el.sprite.width * e))
            part = el.sprite.crop((0, 0, width, el.sprite.height))
            left = el.cx - el.sprite.width / 2
            put(frame, part, left + width / 2, el.cy, 1.0, fade)
    return frame


def timeline(scenes: list[Scene]) -> list[tuple[float, Sound]]:
    """Efectos de sonido en el segundo exacto en que entra cada elemento; whoosh 0,1 s antes de
    cada cambio de escena."""
    events: list[tuple[float, Sound]] = []
    offset = 0.0
    for i, scene in enumerate(scenes):
        if i > 0:
            events.append((max(0.0, offset - 0.1), "whoosh"))
        for el in scene.elements:
            if el.sound:
                events.append((offset + el.start, el.sound))
        offset += scene.dur
    return sorted(events)


def render_frames(
    lay: Layout, scenes: list[Scene], pal: VideoPalette, seed: str
) -> Iterator[Image.Image]:
    """Todos los cuadros del video, en orden (RGBA)."""
    base, shapes = background(lay, pal, seed)
    offset = 0.0
    for scene in scenes:
        for f in range(round(scene.dur * FPS)):
            t = f / FPS
            yield frame_at(lay, scene, t, base, shapes, offset + t)
        offset += scene.dur
