"""Imagen propia para la portada: validación, normalización y velo para que el texto se lea.

La imagen la sube el usuario, así que se trata como entrada no confiable: se limita el tamaño y
los píxeles (bombas de descompresión), solo se aceptan JPEG/PNG/WebP reales (se mira el contenido,
no la extensión) y se reencodea siempre a JPEG, lo que descarta metadatos (EXIF/GPS) y cualquier
dato extra pegado al archivo.
"""

import base64
import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from app.templates_engine.model import Palette

MAX_BYTES = 5 * 1024 * 1024  # lo que se acepta subir
MAX_PIXELS = 40_000_000  # alto x ancho; evita bombas de descompresión
MIN_SIDE = 800  # menos que esto se ve pixelado en una portada A4
OUT_MAX_SIDE = 1800  # lado largo de la imagen guardada
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

# Contraste mínimo (WCAG AA texto normal) entre el texto de la portada y el fondo con el velo.
MIN_CONTRAST = 4.5
MIN_VEIL, MAX_VEIL = 0.35, 0.9

Image.MAX_IMAGE_PIXELS = MAX_PIXELS * 2  # Pillow avisa al superarlo y falla al doble


class InvalidCoverImage(ValueError):
    """La imagen no sirve; el mensaje es apto para mostrarlo al usuario."""


@dataclass(frozen=True)
class ProcessedImage:
    jpeg: bytes
    width: int
    height: int


def process_upload(raw: bytes) -> ProcessedImage:
    if not raw:
        raise InvalidCoverImage("el archivo está vacío")
    if len(raw) > MAX_BYTES:
        raise InvalidCoverImage(f"la imagen pesa más de {MAX_BYTES // (1024 * 1024)} MB")
    try:
        image = Image.open(io.BytesIO(raw))
        if image.format not in ALLOWED_FORMATS:
            raise InvalidCoverImage("usa una imagen JPG, PNG o WebP")
        width, height = image.size  # solo lee el encabezado; aún no decodifica
        if width * height > MAX_PIXELS:
            raise InvalidCoverImage("la imagen tiene demasiados píxeles")
        if min(width, height) < MIN_SIDE:
            raise InvalidCoverImage(f"la imagen es muy chica (mínimo {MIN_SIDE} px de lado)")
        image = ImageOps.exif_transpose(image)  # respeta la orientación de la cámara
        if image.mode in ("RGBA", "LA", "P"):
            rgba = image.convert("RGBA")
            flat = Image.new("RGB", rgba.size, "white")
            flat.paste(rgba, mask=rgba.getchannel("A"))
            image = flat
        else:
            image = image.convert("RGB")
    except InvalidCoverImage:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as exc:
        raise InvalidCoverImage("no se pudo leer la imagen") from exc

    image.thumbnail((OUT_MAX_SIDE, OUT_MAX_SIDE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=86, optimize=True)  # sin exif ni metadatos
    return ProcessedImage(jpeg=out.getvalue(), width=image.width, height=image.height)


def _channel(value: int) -> float:
    s = value / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(l1: float, l2: float) -> float:
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def hex_rgb(value: str) -> tuple[int, int, int]:
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)


def veil_opacity(jpeg: bytes, palette: Palette) -> float:
    """Opacidad mínima del velo (color primario) para que el texto claro de la portada se lea.

    Se mira la zona superior de la imagen recortada como A4 (donde va el título) y se exige el
    contraste con el 90 % de sus píxeles más claros, no con el promedio: una mancha clara detrás
    de una palabra la vuelve ilegible aunque el resto de la imagen sea oscura.
    """
    image = Image.open(io.BytesIO(jpeg)).convert("RGB")
    page = ImageOps.fit(image, (84, 119), Image.Resampling.BILINEAR)  # proporción A4
    zone = page.crop((0, 0, 84, int(119 * 0.5)))
    pixels = list(zone.get_flattened_data())
    text_l = luminance(hex_rgb(palette.on_primary))
    veil = hex_rgb(palette.primary)

    def worst_contrast(alpha: float) -> float:
        lums = sorted(
            luminance(
                tuple(round((1 - alpha) * c + alpha * v) for c, v in zip(px, veil, strict=True))
            )
            for px in pixels
        )
        # El 90 % más claro (o más oscuro, si el texto es oscuro) es lo que decide la lectura.
        probe = lums[int(len(lums) * 0.9)] if text_l > 0.5 else lums[int(len(lums) * 0.1)]
        return contrast(text_l, probe)

    alpha = MIN_VEIL
    while alpha < MAX_VEIL and worst_contrast(alpha) < MIN_CONTRAST:
        alpha = round(alpha + 0.05, 2)
    return min(alpha, MAX_VEIL)


def data_uri(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
