"""Portadas: arte generativo, imagen propia (validación y velo) y su uso al armar el paquete."""

import asyncio
import io
import re
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from uuid import uuid4

import pypdfium2
import pytest
from PIL import Image

from app.config import Settings
from app.generators.base import RenderContext
from app.generators.cover import CoverSpec, art_for_piece, image_path, root_id, stored_spec
from app.generators.cover_art import STYLE_ORDER, render_art, resolve_style, text_zone
from app.generators.cover_image import (
    MAX_BYTES,
    MAX_VEIL,
    MIN_CONTRAST,
    InvalidCoverImage,
    contrast,
    hex_rgb,
    luminance,
    process_upload,
    veil_opacity,
)
from app.generators.pdf import render_pdf
from app.generators.samples import GUIDE
from app.pipeline.generate import run_generate
from app.pipeline.package import PackageBuilder
from app.templates_engine.model import list_templates, load_template
from tests.fakes import make_outline
from tests.test_engines import commercial
from tests.test_pipeline import item_responses, setup

SETTINGS = Settings(_env_file=None)
TEMPLATES = list_templates(SETTINGS.templates_dir)
TPL = load_template(SETTINGS.templates_dir, "bold-moderno")


def jpeg_bytes(size=(1000, 1400), color="#336699", exif=False) -> bytes:
    image = Image.new("RGB", size, color)
    out = io.BytesIO()
    if exif:
        data = Image.Exif()
        data[0x010F] = "CamaraSecreta"  # Make
        data[0x8825] = {1: "S", 2: (33.0, 26.0, 0.0)}  # GPS
        image.save(out, format="JPEG", exif=data)
    else:
        image.save(out, format="JPEG")
    return out.getvalue()


# ───────────────────────────── arte generativo ─────────────────────────────


@pytest.mark.parametrize("style", STYLE_ORDER)
def test_art_is_valid_deterministic_and_unique_per_seed(style) -> None:
    first = render_art(style, "producto:main:0", TPL.palette, "centered")
    again = render_art(style, "producto:main:0", TPL.palette, "centered")
    other = render_art(style, "producto:bonus:1", TPL.palette, "centered")
    assert first == again  # repetible: regenerar no cambia la portada
    assert first != other  # cada pieza tiene su motivo
    ET.fromstring(first)  # XML válido


@pytest.mark.parametrize("style", STYLE_ORDER)
def test_art_only_uses_palette_colors_and_nothing_external(style) -> None:
    svg = render_art(style, "x", TPL.palette, "split")
    allowed = {c.lower() for c in TPL.palette.model_dump().values()}
    assert {c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}", svg)} <= allowed
    for forbidden in ("<script", "href", "http://www.w3.org/1999/xlink", "javascript:", "<image"):
        assert forbidden not in svg


def test_art_family_is_the_same_style_across_the_package() -> None:
    product = {"id": str(uuid4())}
    spec = CoverSpec(art="auto")
    styles = {
        art_for_piece(spec, product, TPL, role, order)[0]
        for role, order in [("main", 0), ("order_bump", 0), ("order_bump", 1), ("bonus", 0)]
    }
    assert len(styles) == 1  # mismo estilo en todo el paquete…
    svgs = {
        art_for_piece(spec, product, TPL, role, order)[1]
        for role, order in [("main", 0), ("order_bump", 0), ("order_bump", 1), ("bonus", 0)]
    }
    assert len(svgs) == 4  # …y un motivo distinto en cada pieza


def test_versions_share_art_with_their_root_and_none_means_no_art() -> None:
    root = {"id": str(uuid4())}
    child = {"id": str(uuid4()), "root_product_id": root["id"]}
    assert root_id(child) == root["id"]
    spec = CoverSpec(art="auto")
    assert art_for_piece(spec, root, TPL, "main", 0) == art_for_piece(spec, child, TPL, "main", 0)
    assert art_for_piece(CoverSpec(art="none"), root, TPL, "main", 0) == (None, "")


def test_auto_style_is_stable_and_uses_every_style() -> None:
    assert resolve_style("auto", "abc") == resolve_style("auto", "abc")
    seen = {resolve_style("auto", str(uuid4())) for _ in range(80)}
    assert seen == set(STYLE_ORDER)
    assert resolve_style("waves", "abc") == "waves"
    assert resolve_style("none", "abc") is None


def test_legacy_products_keep_their_old_look() -> None:
    assert stored_spec({"id": "x"}).art == "none"
    assert stored_spec({"id": "x", "cover": {}}).art == "none"
    assert stored_spec({"id": "x", "cover": {"art": "topo", "image_id": None}}).art == "topo"


def test_text_zone_matches_every_cover_layout() -> None:
    for layout in ("centered", "band", "split", "full-bleed", "notebook"):
        zone = text_zone(layout, TPL.palette)
        assert 0 <= zone.x0 < zone.x1 <= 210 and 0 <= zone.y0 < zone.y1 <= 297


def cover_ctx(**extra) -> RenderContext:
    return RenderContext(market="es-LATAM", role="main", slug="x", product_name="Pack", **extra)


def first_page_text(pdf: bytes) -> str:
    document = pypdfium2.PdfDocument(pdf)
    try:
        return document[0].get_textpage().get_text_range()
    finally:
        document.close()


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.id)
def test_every_template_renders_a_readable_cover_with_art(template) -> None:
    style = STYLE_ORDER[hash(template.id) % len(STYLE_ORDER)]
    art = render_art(style, "seed", template.palette, template.style.cover)
    cover = {"title": GUIDE.title, "subtitle": GUIDE.subtitle, "promise": GUIDE.promise}
    pdf = render_pdf(template, "guide", cover_ctx(cover_art=art), GUIDE, cover)
    assert GUIDE.title in first_page_text(pdf)  # el título sigue ahí, como texto real


def test_art_changes_the_pdf_and_without_it_nothing_changes() -> None:
    cover = {"title": GUIDE.title, "subtitle": GUIDE.subtitle, "promise": GUIDE.promise}
    plain = render_pdf(TPL, "guide", cover_ctx(), GUIDE, cover)
    art = render_art("topo", "s", TPL.palette, TPL.style.cover)
    with_art = render_pdf(TPL, "guide", cover_ctx(cover_art=art), GUIDE, cover)
    other = render_pdf(
        TPL,
        "guide",
        cover_ctx(cover_art=render_art("topo", "otra", TPL.palette, TPL.style.cover)),
        GUIDE,
        cover,
    )
    assert len({plain, with_art, other}) == 3


# ───────────────────────────── imagen propia ─────────────────────────────


def test_valid_images_become_clean_jpegs() -> None:
    for fmt in ("JPEG", "PNG", "WEBP"):
        out = io.BytesIO()
        Image.new("RGB", (900, 1200), "#aa5522").save(out, format=fmt)
        result = process_upload(out.getvalue())
        assert Image.open(io.BytesIO(result.jpeg)).format == "JPEG"
        assert (result.width, result.height) == (900, 1200)


def test_exif_and_gps_are_stripped_and_orientation_is_applied() -> None:
    raw = jpeg_bytes(exif=True)
    assert Image.open(io.BytesIO(raw)).getexif().get(0x010F) == "CamaraSecreta"
    cleaned = Image.open(io.BytesIO(process_upload(raw).jpeg))
    assert not dict(cleaned.getexif())
    assert b"CamaraSecreta" not in process_upload(raw).jpeg


def test_large_images_are_downscaled() -> None:
    result = process_upload(jpeg_bytes(size=(3000, 4200)))
    assert max(result.width, result.height) == 1800


def test_transparent_png_is_flattened_on_white() -> None:
    out = io.BytesIO()
    Image.new("RGBA", (900, 900), (0, 0, 0, 0)).save(out, format="PNG")
    pixel = Image.open(io.BytesIO(process_upload(out.getvalue()).jpeg)).getpixel((10, 10))
    assert min(pixel) > 240


@pytest.mark.parametrize(
    ("raw", "fragment"),
    ids=["vacio", "texto", "svg", "pdf", "muy-pesada"],
    argvalues=[
        (b"", "vacío"),
        (b"no soy una imagen" * 100, "no se pudo leer"),
        (b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>", "no se pudo leer"),
        (b"%PDF-1.7 ..." * 50, "no se pudo leer"),
        (b"x" * (MAX_BYTES + 1), "pesa más"),
    ],
)
def test_invalid_uploads_are_rejected(raw: bytes, fragment: str) -> None:
    with pytest.raises(InvalidCoverImage, match=fragment):
        process_upload(raw)


def test_gif_too_small_and_pixel_bombs_are_rejected() -> None:
    gif = io.BytesIO()
    Image.new("P", (900, 900)).save(gif, format="GIF")
    with pytest.raises(InvalidCoverImage, match="JPG, PNG o WebP"):
        process_upload(gif.getvalue())
    with pytest.raises(InvalidCoverImage, match="muy chica"):
        process_upload(jpeg_bytes(size=(400, 600)))
    bomb = io.BytesIO()
    Image.new("1", (7000, 7000)).save(bomb, format="PNG")  # ~49 Mpx en pocos KB
    assert len(bomb.getvalue()) < MAX_BYTES
    with pytest.raises(InvalidCoverImage, match="demasiados píxeles"):
        process_upload(bomb.getvalue())


def blended_contrast(jpeg: bytes, alpha: float) -> float:
    """Contraste del texto claro contra el 90 % más claro de la zona del título, con velo."""
    page = Image.open(io.BytesIO(jpeg)).convert("RGB").resize((84, 119))
    zone = page.crop((0, 0, 84, 59))
    veil = hex_rgb(TPL.palette.primary)
    lums = sorted(
        luminance(tuple(round((1 - alpha) * c + alpha * v) for c, v in zip(px, veil, strict=True)))
        for px in zone.get_flattened_data()
    )
    return contrast(luminance(hex_rgb(TPL.palette.on_primary)), lums[int(len(lums) * 0.9)])


@pytest.mark.parametrize("color", ["#FFFFFF", "#F2E2A0", "#7A7A7A", "#102030", "#000000"])
def test_veil_always_makes_the_title_readable(color: str) -> None:
    jpeg = process_upload(jpeg_bytes(color=color)).jpeg
    alpha = veil_opacity(jpeg, TPL.palette)
    assert alpha <= MAX_VEIL
    assert alpha == MAX_VEIL or blended_contrast(jpeg, alpha) >= MIN_CONTRAST


def test_brighter_images_get_a_stronger_veil() -> None:
    bright = veil_opacity(process_upload(jpeg_bytes(color="#FFFFFF")).jpeg, TPL.palette)
    dark = veil_opacity(process_upload(jpeg_bytes(color="#101820")).jpeg, TPL.palette)
    assert bright > dark


def test_a_light_patch_behind_the_title_is_not_averaged_away() -> None:
    image = Image.new("RGB", (1000, 1400), "#101820")
    image.paste("#FFFFFF", (0, 0, 1000, 420))  # franja clara justo donde va el título
    out = io.BytesIO()
    image.save(out, format="JPEG")
    jpeg = process_upload(out.getvalue()).jpeg
    assert veil_opacity(jpeg, TPL.palette) > veil_opacity(
        process_upload(jpeg_bytes(color="#101820")).jpeg, TPL.palette
    )


# ───────────────────── uso al armar el paquete (PackageBuilder) ─────────────────────


def builder_with(cover: dict | None, *, image: bytes | None = None):
    deps, product, job, outline = setup([*item_responses(make_outline()), commercial("BRL")])
    product["cover"] = cover
    if image is not None:
        asyncio.run(
            deps.storage.upload(
                image_path(product["user_id"], cover["image_id"]), image, "image/jpeg"
            )
        )
    return deps, product, job, PackageBuilder(deps, job, product)


def row(role: str, order: int) -> dict:
    return {"role": role, "order": order}


def test_builder_gives_each_piece_its_own_art_in_one_style() -> None:
    _, _, _, builder = builder_with({"art": "bauhaus", "image_id": None})
    arts = [
        asyncio.run(builder.cover_fields(row(r, o)))["cover_art"]
        for r, o in [("main", 0), ("order_bump", 0), ("order_bump", 1), ("bonus", 0)]
    ]
    assert len(set(arts)) == 4 and all(a.startswith("<svg") for a in arts)


def test_builder_without_art_adds_nothing() -> None:
    _, _, _, builder = builder_with(None)  # producto anterior a la función
    assert asyncio.run(builder.cover_fields(row("main", 0))) == {"cover_art": ""}


def test_builder_uses_the_uploaded_image_with_its_veil() -> None:
    image_id = str(uuid4())
    jpeg = process_upload(jpeg_bytes(color="#F2E2A0")).jpeg
    _, _, _, builder = builder_with({"art": "topo", "image_id": image_id}, image=jpeg)
    fields = asyncio.run(builder.cover_fields(row("main", 0)))
    assert fields["cover_image"].startswith("data:image/jpeg;base64,")
    assert 0.35 <= fields["cover_veil"] <= 0.9
    assert "cover_art" not in fields  # la imagen reemplaza al arte


def test_builder_falls_back_to_art_if_the_image_is_gone() -> None:
    _, _, _, builder = builder_with({"art": "waves", "image_id": str(uuid4())})
    fields = asyncio.run(builder.cover_fields(row("main", 0)))
    assert fields["cover_art"].startswith("<svg") and "cover_image" not in fields


def test_a_generated_package_carries_the_cover_into_its_pdfs() -> None:
    def main_pdf(cover):
        deps, product, job, _ = builder_with(cover)
        asyncio.run(run_generate(job, deps))
        f = next(
            f
            for f in deps.files.rows.values()
            if f["file_type"] == "pdf" and "/principal/" in f["storage_path"]
        )
        return deps.storage.objects[f["storage_path"]]

    art, plain = main_pdf({"art": "topo", "image_id": None}), main_pdf({"art": "none"})
    assert art != plain
    assert len(pypdfium2.PdfDocument(art)) >= 1


def test_cover_spec_rejects_unknown_fields_and_styles() -> None:
    with pytest.raises(ValueError):
        CoverSpec.model_validate({"art": "grafiti"})
    with pytest.raises(ValueError):
        CoverSpec.model_validate({"art": "topo", "url": "http://x"})
    assert SimpleNamespace  # evita que el import quede huérfano si se limpia el archivo
