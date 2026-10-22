"""Composición de anuncios: HTML/CSS (Jinja2) → PDF (WeasyPrint) → PNG (pdfium).

El texto de la imagen lo pone el HTML, no la IA de imágenes: tildes y ortografía siempre
correctas, y cambiar un texto y volver a renderizar tarda ~1 s y no cuesta nada. Las plantillas
viven en `ad_templates/<id>/` (datos + HTML); las medidas y zonas seguras de Meta, en
`ad_templates/specs.json`. Los colores y tipografías salen de la plantilla del producto, para
que el anuncio sea coherente con el ebook.
"""

import base64
import io
import json
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel

from app.ads.schemas import ImageCopy, Ratio
from app.content.schemas import Market
from app.generators.cover_image import contrast, hex_rgb, luminance
from app.generators.render import html_to_pdf, pdf_page_to_png
from app.templates_engine.fonts import font_path
from app.templates_engine.model import Template

LANG = {"pt-BR": "pt-BR", "es-LATAM": "es"}
SUCCESS, DANGER = "#16A34A", "#DC2626"
MIN_TEXT_CONTRAST = 4.5
LARGE_TEXT_CONTRAST = 3.0
MIN_ACCENT_CONTRAST = 2.0  # botones y marcas de color deben distinguirse del fondo
A4_RATIO = 210 / 297
SHRINKS = (1.0, 0.92, 0.84, 0.76, 0.68, 0.6)  # reintentos si el contenido no cabe en la zona segura
SAFE_TOLERANCE_PX = 6
PT_PER_PX = 0.75  # el PDF mide en puntos: 1 px CSS = 0,75 pt


@dataclass(frozen=True)
class RatioSpec:
    id: str
    label: str
    width: int
    height: int
    safe_top: float
    safe_bottom: float
    safe_sides: float
    folder: str

    @property
    def pad(self) -> dict[str, int]:
        return {
            "top": round(self.height * self.safe_top),
            "bottom": round(self.height * self.safe_bottom),
            "side": round(self.width * self.safe_sides),
        }


@dataclass(frozen=True)
class RenderReport:
    shrink: float  # 1.0 = a tamaño completo
    outside: list[
        str
    ]  # qué quedó fuera de la zona segura aun después de reducir (idealmente vacío)


class AdTemplate(BaseModel):
    id: str
    name: str
    description: str
    uses_image: bool
    uses_mockup: bool
    scheme: str


def load_specs(root: Path) -> tuple[dict[str, RatioSpec], dict]:
    raw = json.loads((root / "specs.json").read_text(encoding="utf-8"))
    ratios = {
        rid: RatioSpec(
            id=rid,
            label=r["label"],
            width=r["width"],
            height=r["height"],
            safe_top=r["safe"]["top"],
            safe_bottom=r["safe"]["bottom"],
            safe_sides=r["safe"]["sides"],
            folder=r["folder"],
        )
        for rid, r in raw["ratios"].items()
    }
    return ratios, raw


def list_ad_templates(root: Path) -> list[AdTemplate]:
    return [
        AdTemplate(**json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(root.glob("*/template.json"))
    ]


# ───────────────────────────── colores ─────────────────────────────


def readable(fg: str, bg: str, *candidates: str, minimum: float = MIN_TEXT_CONTRAST) -> str:
    """`fg` si se lee sobre `bg`; si no, el primer candidato (o blanco/casi negro) que sí."""
    options = [fg, *candidates, "#FFFFFF", "#111827"]
    bg_l = luminance(hex_rgb(bg))
    for option in options:
        if contrast(luminance(hex_rgb(option)), bg_l) >= minimum:
            return option
    return max(options, key=lambda o: contrast(luminance(hex_rgb(o)), bg_l))


def scheme_colors(template: Template, scheme: str) -> dict[str, str]:
    """Paleta del anuncio a partir de la plantilla del producto, con el contraste garantizado."""
    p = template.palette
    if scheme == "bold":
        bg, fg = p.primary, p.on_primary
    else:
        bg, fg = p.background, p.text
    fg = readable(fg, bg)
    accent = p.accent
    if contrast(luminance(hex_rgb(accent)), luminance(hex_rgb(bg))) < MIN_ACCENT_CONTRAST:
        accent = (
            fg  # el acento se confunde con el fondo (p. ej. dorado sobre dorado): botones visibles
        )
    return {
        "bg": bg,
        "fg": fg,
        "accent": accent,
        "accent_fg": readable(bg, accent, fg),  # texto sobre botones y marcas de color
        "accent_text": readable(accent, bg, fg, minimum=LARGE_TEXT_CONTRAST),  # kicker y precio
        "border": p.muted
        if contrast(luminance(hex_rgb(p.muted)), luminance(hex_rgb(bg))) >= 1.5
        else fg,
    }


# ───────────────────────────── tamaños de texto ─────────────────────────────


def _fit(length: int, steps: list[tuple[int, float]]) -> float:
    for limit, factor in steps:
        if length <= limit:
            return factor
    return steps[-1][1]


def font_sizes(
    template_id: str, copy: ImageCopy, spec: RatioSpec, shrink: float = 1.0
) -> dict[str, int]:
    """Tamaños que escalan con el largo del texto para que nunca se desborde la zona segura."""
    w = spec.width
    wide = spec.id == "1x1"
    steps = [(16, 1.0), (26, 0.86), (40, 0.72), (56, 0.60), (80, 0.52), (999, 0.46)]
    base = {"headline_bold": 0.118, "product_mockup": 0.078, "checklist": 0.084, "note": 0.1}[
        template_id
    ]
    if wide:
        base *= 0.9
    if template_id == "product_mockup" and wide:
        base *= 0.78
    headline = round(w * base * _fit(len(copy.headline), steps))
    note_len = len(copy.note or copy.headline)
    note = round(w * 0.092 * _fit(note_len, [(40, 1.0), (80, 0.84), (130, 0.7), (999, 0.58)]))
    if wide:
        note = round(note * 0.85)
    longest = max([len(b) for b in copy.bullets] or [0])
    sizes = {
        "headline": max(headline, 44),
        "sub": round(w * 0.036),
        "kicker": round(w * 0.03),
        "cta": round(w * 0.034),
        "price": round(w * 0.052),
        "bullet": round(w * (0.034 if wide else 0.038) * _fit(longest, [(30, 1.0), (999, 0.88)])),
        "item": round(w * 0.05 * _fit(longest, [(26, 1.0), (40, 0.86), (999, 0.74)])),
        "note": max(note, 44),
        "sign": round(w * 0.04),
    }
    return {k: max(round(v * shrink), 22) for k, v in sizes.items()}


def mock_size(spec: RatioSpec, shrink: float = 1.0) -> dict[str, int]:
    img_w = round({"4x5": 280, "9x16": 250, "1x1": 330}[spec.id] * shrink)
    return {"w": img_w + 28, "h": round(img_w / A4_RATIO) + 28}


# ───────────────────────────── medición ─────────────────────────────


def content_outside_safe_zone(pdf: bytes, spec: RatioSpec) -> list[str]:
    """Textos e imágenes que caen fuera de la zona segura (medido en el PDF, no estimado)."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    pad = spec.pad
    left, right = pad["side"] - SAFE_TOLERANCE_PX, spec.width - pad["side"] + SAFE_TOLERANCE_PX
    top, bottom = pad["top"] - SAFE_TOLERANCE_PX, spec.height - pad["bottom"] + SAFE_TOLERANCE_PX
    document = pdfium.PdfDocument(pdf)
    try:
        page = document[0]
        height_pt = page.get_height()
        boxes: list[tuple[str, tuple[float, float, float, float]]] = []
        textpage = page.get_textpage()
        for i in range(textpage.count_rects()):
            boxes.append(("texto", textpage.get_rect(i)))
        for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE]):
            boxes.append(("imagen", obj.get_bounds()))
        out = []
        for kind, (x_min, y_min, x_max, y_max) in boxes:
            x0, x1 = x_min / PT_PER_PX, x_max / PT_PER_PX
            y0, y1 = (height_pt - y_max) / PT_PER_PX, (height_pt - y_min) / PT_PER_PX
            if x0 < left or x1 > right or y0 < top or y1 > bottom:
                out.append(f"{kind} ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})")
        return out
    finally:
        document.close()


# ───────────────────────────── compositor ─────────────────────────────


class AdRenderer:
    def __init__(self, ad_templates_dir: Path, templates_dir: Path) -> None:
        self.root = ad_templates_dir
        self.templates_dir = templates_dir
        self.ratios, self.specs = load_specs(ad_templates_dir)
        self.templates = {t.id: t for t in list_ad_templates(ad_templates_dir)}
        self._env = Environment(
            loader=FileSystemLoader([str(ad_templates_dir), str(ad_templates_dir / "_base")]),
            autoescape=select_autoescape(["html", "j2"], default_for_string=True),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def available_ids(self) -> list[str]:
        return list(self.templates)

    def render(self, **kwargs) -> bytes:
        return self.render_with_report(**kwargs)[0]

    def render_with_report(self, *, hires: bool = False, **kwargs) -> tuple[bytes, RenderReport]:
        pdf, report = self.compose(**kwargs)
        spec = self.ratios[kwargs["ratio"]]
        scale = self.specs["hires_scale"] if hires else 1.0
        return pdf_page_to_png(pdf, 0, round(spec.width * scale)), report

    def compose(
        self,
        *,
        template_id: str,
        copy: ImageCopy,
        ratio: Ratio | str,
        product_template: Template,
        market: Market,
        product_name: str = "",
        mockup_png: bytes | None = None,
    ) -> tuple[bytes, RenderReport]:
        """PDF de una página del anuncio y un informe.

        Si algo se sale de la zona segura del formato (un titular
        largo, un mockup grande), se reduce el contenido y se reintenta hasta que quepa."""
        if template_id not in self.templates:
            raise KeyError(f"plantilla de anuncio desconocida: {template_id}")
        spec = self.ratios[ratio]
        tpl = self.templates[template_id]
        c = scheme_colors(product_template, tpl.scheme)
        c["mk"] = DANGER if copy.mark == "cross" else SUCCESS
        faces = product_template.font_faces()
        caveat = font_path(self.templates_dir / "_fonts", "Caveat", 700)
        faces.append({"family": "Caveat", "weight": 700, "url": caveat.as_uri()})
        fonts = product_template.fonts
        mockup_uri = (
            "data:image/png;base64," + base64.b64encode(mockup_png).decode() if mockup_png else None
        )
        page = self._env.get_template("page.html.j2")
        pdf = b""
        outside: list[str] = []
        shrink = SHRINKS[0]
        for shrink in SHRINKS:
            mock = mock_size(spec, shrink)
            html = page.render(
                W=spec.width,
                H=spec.height,
                pad=spec.pad,
                c=c,
                mk_color=c["mk"],
                f={
                    "body": fonts.body.family,
                    "heading": fonts.heading.family,
                    "heading_weight": fonts.heading.weights[0],
                },
                fs=font_sizes(template_id, copy, spec, shrink),
                faces=faces,
                copy=copy,
                ratio=spec.id,
                template_id=template_id,
                mockup_uri=mockup_uri,
                mock=mock,
                col_w=spec.width - 2 * spec.pad["side"] - mock["w"] - 40,
                product_name=product_name,
                lang=LANG[market],
            )
            pdf = html_to_pdf(html, self.root)
            outside = content_outside_safe_zone(pdf, spec)
            if not outside:
                break
        return pdf, RenderReport(shrink=shrink, outside=outside)


def product_mockup(
    product_template: Template, market: Market, title: str, subtitle: str = "", name: str = ""
) -> bytes:
    """La portada del producto como imagen (para la plantilla de mockup), con su plantilla."""
    from app.generators.base import RenderContext
    from app.generators.epub import cover_png

    ctx = RenderContext(market=market, role="main", slug="mockup", product_name=name or title)
    return cover_png(product_template, ctx, {"title": title, "subtitle": subtitle}, width=600)


def png_info(png: bytes) -> tuple[int, int]:
    from PIL import Image

    with Image.open(io.BytesIO(png)) as image:
        return image.size
