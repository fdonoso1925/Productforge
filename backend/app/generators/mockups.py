"""Mockups realistas de la portada de un producto: libro, tablet, celular y pack.

Todo se dibuja con Pillow a partir de la portada real del producto (la que ya genera la
plantilla), sin fotos ni recursos externos: PNG con fondo transparente, listo para ponerlo
sobre un anuncio, una página de ventas o una vitrina. Se dibuja al doble de tamaño y se reduce
para que los bordes salgan limpios.

No inventa nada: ni sellos de «best seller», ni estrellas, ni autor. Solo la portada.
"""

import io
from collections.abc import Callable
from functools import lru_cache
from typing import Literal

from PIL import Image, ImageChops, ImageDraw, ImageFilter

MockupKind = Literal["book", "tablet", "phone", "bundle"]
MOCKUP_KINDS: tuple[str, ...] = ("book", "tablet", "phone", "bundle")

SS = 2  # supersampling: se dibuja a SS veces y se reduce
BOOK_RATIO = 1.414  # alto / ancho de una portada A4
PAD = 36  # aire alrededor del recorte final


# ───────────────────────────── utilidades ─────────────────────────────


def _open(cover_png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(cover_png)).convert("RGBA")


def _to_png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


def _perspective_coeffs(
    dst: list[tuple[float, float]], src: list[tuple[float, float]]
) -> list[float]:
    """Coeficientes para `Image.transform(..., PERSPECTIVE)`: lleva el cuadrilátero `dst` del lienzo
    de salida al rectángulo `src` de la imagen de origen (resuelve el sistema 8x8 por Gauss)."""
    rows: list[list[float]] = []
    for (x, y), (u, v) in zip(dst, src, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y, u])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y, v])
    n = 8
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(rows[r][col]))
        rows[col], rows[pivot] = rows[pivot], rows[col]
        div = rows[col][col] or 1e-12
        rows[col] = [value / div for value in rows[col]]
        for r in range(n):
            if r != col:
                factor = rows[r][col]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[col], strict=True)]
    return [rows[i][n] for i in range(n)]


def _warp(
    image: Image.Image, quad: list[tuple[float, float]], size: tuple[int, int]
) -> Image.Image:
    """Pega `image` deformada en el cuadrilátero `quad` (TL, TR, BR, BL) sobre un lienzo vacío."""
    w, h = image.size
    coeffs = _perspective_coeffs(quad, [(0, 0), (w, 0), (w, h), (0, h)])
    return image.transform(size, Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC)


def _shade(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    """Oscurece (<1) o aclara (>1) un color."""
    if factor <= 1:
        return tuple(round(c * factor) for c in color)  # type: ignore[return-value]
    return tuple(round(c + (255 - c) * (factor - 1)) for c in color)  # type: ignore[return-value]


def _edge_color(cover: Image.Image) -> tuple[int, int, int]:
    """Color medio del borde izquierdo de la portada: el del lomo del libro."""
    strip = (
        cover.convert("RGB").crop((0, 0, max(2, cover.width // 40), cover.height)).resize((1, 1))
    )
    return strip.getpixel((0, 0))  # type: ignore[return-value]


def _gradient(size: tuple[int, int], left: int, right: int, vertical: bool = False) -> Image.Image:
    """Degradado de gris (máscara) entre dos valores 0-255."""
    w, h = size
    line = Image.linear_gradient("L")  # 256x256: negro arriba → blanco abajo
    if not vertical:
        line = line.rotate(90, expand=True)  # el arriba pasa a la izquierda: negro → blanco
    line = line.resize((w, h))
    span = right - left
    return line.point(lambda v: round(left + span * v / 255))


def _shadow(shape: Image.Image, blur: int, opacity: float, offset: tuple[int, int]) -> Image.Image:
    """Sombra suave de la silueta (canal alfa) de `shape`, en un lienzo del mismo tamaño."""
    alpha = shape.getchannel("A").filter(ImageFilter.GaussianBlur(blur))
    alpha = alpha.point(lambda v: round(v * opacity))
    layer = Image.new("RGBA", shape.size, (0, 0, 0, 0))
    layer.putalpha(ImageChops.offset(alpha, *offset))
    return layer


def _round_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=255)
    return mask


def _cover_fit(cover: Image.Image, size: tuple[int, int], *, top: bool = False) -> Image.Image:
    """La portada llenando `size` sin deformarla (recorta lo que sobre)."""
    w, h = size
    scale = max(w / cover.width, h / cover.height)
    resized = cover.resize(
        (max(1, round(cover.width * scale)), max(1, round(cover.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = (resized.width - w) // 2
    upper = 0 if top else (resized.height - h) // 2
    return resized.crop((left, upper, left + w, upper + h))


def _trim(image: Image.Image, pad: int = PAD) -> Image.Image:
    """Recorta el transparente sobrante y deja `pad` px de aire."""
    box = image.getbbox()
    if box is None:
        return image
    cropped = image.crop(box)
    out = Image.new("RGBA", (cropped.width + 2 * pad, cropped.height + 2 * pad), (0, 0, 0, 0))
    out.alpha_composite(cropped, (pad, pad))
    return out


def _down(image: Image.Image) -> Image.Image:
    return image.resize((image.width // SS, image.height // SS), Image.Resampling.LANCZOS)


# ───────────────────────────── libro ─────────────────────────────


def _book(cover: Image.Image, width: int = 760) -> Image.Image:
    """Libro de tapa dura girado unos grados: portada en perspectiva, lomo, hojas y sombra."""
    W = width * SS
    H = round(W * BOOK_RATIO) + 160 * SS
    canvas_size = (W + 120 * SS, H)
    front_w = round(W * 0.78)
    front_h = round(front_w * BOOK_RATIO)
    x0, y0 = 60 * SS, 40 * SS
    depth = round(front_w * 0.075)  # grosor de las hojas hacia la derecha
    drop = round(front_h * 0.028)  # cuánto «se aleja» el borde derecho (perspectiva)

    face = _cover_fit(cover, (front_w, front_h))
    # Lomo: el borde izquierdo oscurecido y un brillo fino donde dobla la tapa.
    spine = _edge_color(cover)
    band = Image.new("L", face.size, 0)
    band.paste(_gradient((round(front_w * 0.09), front_h), 150, 0), (0, 0))
    face = Image.alpha_composite(
        face, Image.merge("RGBA", (*Image.new("RGB", face.size, _shade(spine, 0.35)).split(), band))
    )
    hinge = Image.new("RGBA", face.size, (0, 0, 0, 0))
    ImageDraw.Draw(hinge).rectangle(
        (round(front_w * 0.085), 0, round(front_w * 0.095), front_h), fill=(255, 255, 255, 70)
    )
    face = Image.alpha_composite(face, hinge)
    # Brillo suave en diagonal.
    gloss = Image.new("RGBA", face.size, (255, 255, 255, 0))
    gloss.putalpha(_gradient(face.size, 70, 0).point(lambda v: min(v, 55)))
    face = Image.alpha_composite(face, gloss)

    tl = (x0, y0)
    tr = (x0 + front_w, y0 + drop)
    br = (x0 + front_w, y0 + front_h - drop)
    bl = (x0, y0 + front_h)
    body = Image.new("RGBA", canvas_size, (0, 0, 0, 0))

    # Hojas (cara derecha): parallelogram con líneas finas, detrás de la portada.
    pages = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    pd = ImageDraw.Draw(pages)
    quad = [tr, (tr[0] + depth, tr[1] + drop * 0.35), (br[0] + depth, br[1] - drop * 0.35), br]
    pd.polygon(quad, fill=(246, 243, 236, 255))
    for i in range(1, 9):
        t = i / 9
        a = (tr[0] + depth * t, tr[1] + (drop * 0.35) * t)
        b = (br[0] + depth * t, br[1] - (drop * 0.35) * t)
        pd.line([a, b], fill=(214, 209, 198, 255), width=SS)
    pd.polygon(quad, outline=(190, 184, 172, 255))
    # Tapa trasera asomando por abajo.
    pd.polygon(
        [
            bl,
            br,
            (br[0] + depth, br[1] - drop * 0.35 + SS * 3),
            (bl[0] + depth * 0.2, bl[1] + SS * 3),
        ],
        fill=_shade(spine, 0.5) + (255,),
    )
    body = Image.alpha_composite(body, pages)
    body = Image.alpha_composite(body, _warp(face, [tl, tr, br, bl], canvas_size))
    # Borde fino de luz arriba y a la izquierda: da volumen a la tapa.
    rim = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(rim)
    rd.line([tl, tr], fill=(255, 255, 255, 90), width=SS * 2)
    rd.line([tr, br], fill=(0, 0, 0, 50), width=SS * 2)
    body = Image.alpha_composite(body, rim)

    shadow = _shadow(body, blur=26 * SS, opacity=0.5, offset=(20 * SS, 34 * SS))
    floor = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    ImageDraw.Draw(floor).ellipse(
        (
            x0 + 20 * SS,
            y0 + front_h - 4 * SS,
            x0 + front_w + depth + 10 * SS,
            y0 + front_h + 38 * SS,
        ),
        fill=(0, 0, 0, 120),
    )
    floor = floor.filter(ImageFilter.GaussianBlur(14 * SS))
    return _trim(_down(Image.alpha_composite(Image.alpha_composite(floor, shadow), body)))


# ───────────────────────────── tablet ─────────────────────────────


def _device(
    cover: Image.Image,
    screen: tuple[int, int],
    bezel: int,
    radius: int,
    *,
    island: Literal["none", "camera", "pill"] = "none",
    body_color: tuple[int, int, int] = (22, 24, 30),
) -> Image.Image:
    """Marco con pantalla: la portada ocupa la pantalla, con reflejo y sombra."""
    sw, sh = screen
    W, H = sw + 2 * bezel, sh + 2 * bezel
    pad = 70 * SS
    canvas = Image.new("RGBA", (W + 2 * pad, H + 2 * pad), (0, 0, 0, 0))
    body = Image.new("RGBA", (W, H), body_color + (255,))
    body.putalpha(_round_mask((W, H), radius))
    # Reborde metálico fino.
    edge = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(edge).rounded_rectangle(
        (0, 0, W - 1, H - 1), radius, outline=(120, 124, 135, 255), width=SS * 2
    )
    body = Image.alpha_composite(body, edge)

    # Pantalla: la portada a lo ancho, anclada arriba; lo que sobra se rellena con su color.
    shot = (
        _cover_fit(cover, (sw, sh), top=True)
        if abs(sw / sh - cover.width / cover.height) < 0.12
        else _screen_fill(cover, (sw, sh))
    )
    screen_mask = _round_mask((sw, sh), max(2, radius - bezel))
    body.paste(shot, (bezel, bezel), screen_mask)
    # Reflejo suave arriba de la pantalla: se compone con su propio alfa, recortado a la pantalla.
    glare = Image.new("RGBA", (sw, sh), (255, 255, 255, 0))
    fade = _gradient((sw, sh), 60, 0, vertical=True).point(lambda v: min(v, 38))
    glare.putalpha(ImageChops.multiply(fade, screen_mask))
    body.alpha_composite(glare, (bezel, bezel))

    draw = ImageDraw.Draw(body)
    if island == "camera":
        r = max(3, bezel // 5)
        draw.ellipse(
            (W // 2 - r, bezel // 2 - r, W // 2 + r, bezel // 2 + r), fill=(48, 52, 62, 255)
        )
    elif island == "pill":
        pw, ph = round(sw * 0.3), round(bezel * 0.78)
        draw.rounded_rectangle(
            (W // 2 - pw // 2, bezel + ph // 2, W // 2 + pw // 2, bezel + ph // 2 + ph),
            ph // 2,
            fill=(8, 9, 12, 255),
        )

    canvas.alpha_composite(body, (pad, pad))
    shadow = _shadow(canvas, blur=30 * SS, opacity=0.45, offset=(14 * SS, 30 * SS))
    return _trim(_down(Image.alpha_composite(shadow, canvas)))


def _screen_fill(cover: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Pantalla más alta que la portada (celular): portada a lo ancho arriba y, debajo, su color."""
    w, h = size
    scaled = cover.resize((w, round(cover.height * w / cover.width)), Image.Resampling.LANCZOS)
    base = (
        scaled.convert("RGB")
        .crop((0, scaled.height - 4, w, scaled.height))
        .resize((1, 1))
        .getpixel((0, 0))
    )
    canvas = Image.new("RGBA", size, base + (255,))
    canvas.alpha_composite(scaled, (0, min(round(h * 0.07), max(0, h - scaled.height))))
    return canvas


def _tablet(cover: Image.Image) -> Image.Image:
    screen = (640 * SS, round(640 * SS * 1.34))
    return _device(cover, screen, bezel=34 * SS, radius=44 * SS, island="camera")


def _phone(cover: Image.Image) -> Image.Image:
    screen = (430 * SS, round(430 * SS * 2.05))
    return _device(cover, screen, bezel=22 * SS, radius=70 * SS, island="pill")


# ───────────────────────────── pack ─────────────────────────────


def _bundle(cover: Image.Image) -> Image.Image:
    """Libro al frente con la tablet detrás a la derecha y el celular delante: el «pack digital»."""
    book, tablet, phone = _book(cover, 700), _tablet(cover), _phone(cover)
    tablet = tablet.resize(
        (round(tablet.width * 0.78), round(tablet.height * 0.78)), Image.Resampling.LANCZOS
    )
    phone = phone.resize(
        (round(phone.width * 0.5), round(phone.height * 0.5)), Image.Resampling.LANCZOS
    )
    book = book.resize(
        (round(book.width * 0.95), round(book.height * 0.95)), Image.Resampling.LANCZOS
    )
    W = book.width + tablet.width // 2 + phone.width // 3
    H = max(book.height, tablet.height) + 20
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.alpha_composite(tablet, (W - tablet.width, 0))
    canvas.alpha_composite(book, (0, H - book.height))
    canvas.alpha_composite(phone, (round(book.width * 0.78), H - phone.height))
    return _trim(canvas, PAD // 2)


_BUILDERS: dict[str, Callable[[Image.Image], Image.Image]] = {
    "book": _book,
    "tablet": _tablet,
    "phone": _phone,
    "bundle": _bundle,
}


def render_mockup(kind: str, cover_png: bytes) -> bytes:
    """PNG transparente del mockup `kind` con la portada dada. `ValueError` si el tipo no existe."""
    if kind not in _BUILDERS:
        raise ValueError(f"mockup desconocido: {kind}")
    return _to_png(_BUILDERS[kind](_open(cover_png)))


@lru_cache(maxsize=12)
def cached_mockup(kind: str, cover_png: bytes) -> bytes:
    """Lo mismo que `render_mockup`, recordando los últimos: un lote de anuncios pide el mismo
    mockup (mismo tipo y misma portada) decenas de veces."""
    return render_mockup(kind, cover_png)


def mockup_info(png: bytes) -> tuple[int, int, bool]:
    """Ancho, alto y si la imagen es opaca (una portada plana) o trae transparencia (un mockup)."""
    with Image.open(io.BytesIO(png)) as image:
        rgba = image.convert("RGBA")
        return rgba.width, rgba.height, rgba.getchannel("A").getextrema()[0] == 255
