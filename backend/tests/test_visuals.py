"""Infografías: SVG válido y escapado, el texto cabe, van en PDF/EPUB; fotos de capítulo."""

import asyncio
import base64
import io
import re
import zipfile
from uuid import uuid4
from xml.etree import ElementTree

import pytest

from app.config import Settings
from app.content.schemas import Format
from app.content.schemas.formats import PhotoSpec, Visual, VisualItem
from app.generators import generate_files
from app.generators.base import RenderContext
from app.generators.epub import photo_bytes
from app.generators.samples_visuals import (
    ALL,
    rich_blueprint,
    rich_checklist,
    rich_guide,
    rich_planner,
)
from app.generators.visuals import ICONS, Meter, W, render_visual
from app.templates_engine.model import list_templates, load_template

SETTINGS = Settings(_env_file=None)
TEMPLATE = load_template(SETTINGS.templates_dir, "bold-moderno")
CTX = RenderContext(market="es-LATAM", role="main", slug="demo", product_name="Demo")


def svg_of(visual: Visual, template=TEMPLATE) -> str:
    return render_visual(visual, template, "es-LATAM")


@pytest.mark.parametrize("name", sorted(ALL))
def test_every_kind_renders_valid_svg_with_an_accessible_title(name: str) -> None:
    svg = svg_of(ALL[name])
    root = ElementTree.fromstring(svg)  # XML bien formado
    assert root.tag.endswith("svg") and root.attrib["role"] == "img"
    assert root.attrib["aria-label"] == ALL[name].title
    width, height = (float(x) for x in root.attrib["viewBox"].split()[2:])
    assert width == W and 40 < height < 1200


@pytest.mark.parametrize("template", [t.id for t in list_templates(SETTINGS.templates_dir)])
def test_visuals_render_with_every_visual_template(template: str) -> None:
    tpl = load_template(SETTINGS.templates_dir, template)
    for visual in ALL.values():
        assert svg_of(visual, tpl).startswith("<svg")


def test_text_from_the_ai_is_escaped_and_cannot_inject_markup() -> None:
    evil = Visual.model_validate(
        {
            "kind": "process",
            "title": '"><script>alert(1)</script>',
            "items": [
                {"label": "<img src=x onerror=alert(1)>", "detail": "</text><script>x</script>"},
                {"label": "A & B", "detail": "'quotes' \"double\""},
                {"label": "Tercero"},
            ],
        }
    )
    svg = svg_of(evil)
    root = ElementTree.fromstring(svg)  # sigue siendo XML válido
    drawn = {el.tag.split("}")[-1] for el in root.iter()}
    assert drawn <= {
        "svg",
        "title",
        "text",
        "rect",
        "circle",
        "polygon",
        "line",
        "g",
        "polyline",
        "path",
    }
    text = "".join(root.itertext())
    assert "<script>" in text and "A & B" in text  # el texto llegó como texto, no como etiqueta
    assert "<script" not in svg and "<img" not in svg


def test_unknown_icons_are_ignored_and_every_declared_icon_draws() -> None:
    for icon in ICONS:
        v = Visual(kind="cards", title="t", items=[VisualItem(label="uno", icon=icon)] * 3)
        assert "<g transform" in svg_of(v)
    with pytest.raises(ValueError):
        VisualItem(label="x", icon="inventado")


def test_long_text_is_cut_with_an_ellipsis_instead_of_overflowing() -> None:
    meter = Meter(TEMPLATE)
    lines = meter.wrap("palabra " * 80, 12, 150, "body", 3)
    assert len(lines) == 3 and lines[-1].endswith("…")
    assert all(meter.width(line, 12, "body") <= 150 + 1 for line in lines)
    assert meter.wrap("Supercalifragilisticoespialidoso" * 3, 12, 100, "body", 4)  # palabra enorme
    assert meter.wrap("", 12, 100) == [""]


def test_a_visual_with_nothing_to_draw_is_empty_not_broken() -> None:
    empty = Visual(kind="process", title="vacío", items=[VisualItem(label="  ")])
    assert svg_of(empty) == ""
    assert svg_of(Visual(kind="bars", title="sin datos", items=[VisualItem(label="x")])) in (
        "",
        svg_of(Visual(kind="bars", title="sin datos", items=[])),
    )


def test_charts_are_marked_as_illustrative_unless_the_data_is_real() -> None:
    assert "Ejemplo ilustrativo" in svg_of(ALL["bars"]) and "Ejemplo ilustrativo" in svg_of(
        ALL["donut"]
    )
    real = ALL["bars"].model_copy(update={"illustrative": False})
    assert "Ejemplo ilustrativo" not in svg_of(real)
    pt = render_visual(ALL["bars"], TEMPLATE, "pt-BR")
    assert "Exemplo ilustrativo" in pt


def test_item_counts_are_capped_so_the_layout_never_breaks() -> None:
    many = Visual(
        kind="process", title="muchos", items=[VisualItem(label=f"Paso {i}") for i in range(30)]
    )
    root = ElementTree.fromstring(svg_of(many))
    assert float(root.attrib["viewBox"].split()[3]) < 800
    assert svg_of(many).count(">1<") >= 1 and ">7<" not in svg_of(many)


def test_donut_percent_unit_is_not_repeated() -> None:
    assert "60 % · 60 %" not in svg_of(ALL["donut"])


# ───────────────────────────── dentro de los archivos ─────────────────────────────


def pdf_text(pdf: bytes) -> str:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf)
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


def test_the_rich_guide_pdf_carries_its_infographics() -> None:
    [pdf] = generate_files(Format.PDF_GUIDE, rich_guide(), TEMPLATE, CTX)
    text = pdf_text(pdf.content)
    for visual_title in ("Tu ruta de salida en 4 pasos", "Las 4 ideas que sostienen el método"):
        assert visual_title in text
    assert "Mide tu deuda" in text and "Pagar el mínimo" in text


def test_the_rich_blueprint_is_visual_first() -> None:
    [pdf] = generate_files(Format.BLUEPRINT, rich_blueprint(), TEMPLATE, CTX)
    text = pdf_text(pdf.content)
    assert "Línea de tiempo de los 60 días" in text and "El ciclo semanal del dinero" in text
    assert "Las 4 ideas que sostienen el método" in text  # success_visual


def test_checklist_and_planner_get_their_visual() -> None:
    [check] = generate_files(Format.CHECKLIST, rich_checklist(), TEMPLATE, CTX)
    [plan] = generate_files(Format.PLANNER, rich_planner(), TEMPLATE, CTX)
    assert "Tu ruta de salida en 4 pasos" in pdf_text(check.content)
    assert "Línea de tiempo de los 60 días" in pdf_text(plan.content)


def test_content_without_visuals_still_renders_as_before() -> None:
    from app.generators.samples import BLUEPRINT, GUIDE

    for fmt, content in ((Format.PDF_GUIDE, GUIDE), (Format.BLUEPRINT, BLUEPRINT)):
        [pdf] = generate_files(fmt, content, TEMPLATE, CTX)
        assert pdf.content.startswith(b"%PDF")


def test_a_chapter_photo_goes_into_the_pdf_and_the_epub() -> None:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (1080, 607), "#336699").save(buffer, "JPEG")
    uri = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
    ctx = RenderContext(
        market="es-LATAM", role="main", slug="demo", product_name="Demo", photos={"ch1": uri}
    )

    [pdf] = generate_files(Format.PDF_GUIDE, rich_guide(), TEMPLATE, ctx)
    assert "Empieza por los números" in pdf_text(pdf.content)

    [epub] = generate_files(Format.EPUB, rich_guide(), TEMPLATE, ctx)
    archive = zipfile.ZipFile(io.BytesIO(epub.content))
    assert "EPUB/images/ch1.jpg" in archive.namelist()
    chapter = archive.read("EPUB/ch-1.xhtml").decode()
    assert "images/ch1.jpg" in chapter and "<svg" in chapter and "Tu ruta de salida" in chapter
    ElementTree.fromstring(chapter.split("?>", 1)[-1])  # XHTML bien formado con el SVG dentro


def test_the_epub_has_no_photo_when_none_was_found() -> None:
    [epub] = generate_files(Format.EPUB, rich_guide(), TEMPLATE, CTX)
    assert not [n for n in zipfile.ZipFile(io.BytesIO(epub.content)).namelist() if "images/" in n]


def test_photo_bytes_only_accepts_a_real_jpeg_data_uri() -> None:
    assert photo_bytes("") == b"" and photo_bytes("data:image/png;base64,AAAA") == b""
    assert photo_bytes("data:image/jpeg;base64,@@@") == b""
    assert photo_bytes("data:image/jpeg;base64," + base64.b64encode(b"x").decode()) == b"x"


# ───────────────────────────── fotos en el pipeline ─────────────────────────────


class FakeRouter:
    def __init__(self, active=True, fail=()):
        self._active, self.fail, self.requests = active, set(fail), []

    def active(self):
        return ["pixabay"] if self._active else []

    async def get(self, *, user_id, request):
        from types import SimpleNamespace

        self.requests.append(request)
        if request.keywords[0] in self.fail:
            raise RuntimeError("sin cuota")
        return SimpleNamespace(jpeg=b"\xff\xd8jpeg")


def builder_with(router):
    from app.pipeline.package import PackageBuilder
    from tests.test_pipeline import setup

    deps, product, job, _ = setup([])
    deps.images = router
    return PackageBuilder(deps, job, product)


def test_chapter_photos_are_requested_wide_and_skip_failures() -> None:
    router = FakeRouter(fail={"broken"})
    chapters = [
        {
            "title": "a",
            "summary": "s",
            "sections": [],
            "photo": {"scene": "desk", "keywords": ["desk", "notes"]},
        },
        {"title": "b", "summary": "s", "sections": []},
        {
            "title": "c",
            "summary": "s",
            "sections": [],
            "photo": {"scene": "x", "keywords": ["broken"]},
        },
    ]
    from app.content.schemas.formats import GuideContent

    guide = rich_guide().model_copy(
        update={
            "chapters": [
                rich_guide()
                .chapters[0]
                .model_copy(update={"photo": PhotoSpec(**chapters[0]["photo"])}),
                rich_guide().chapters[0].model_copy(update={"photo": None}),
                rich_guide()
                .chapters[0]
                .model_copy(update={"photo": PhotoSpec(**chapters[2]["photo"])}),
            ]
        }
    )
    assert isinstance(guide, GuideContent)
    found = asyncio.run(builder_with(router).chapter_photos(guide))
    assert list(found) == ["ch1"] and found["ch1"].startswith("data:image/jpeg;base64,")
    assert all(r.aspect == "16:9" for r in router.requests) and len(router.requests) == 2


def test_no_photos_without_an_active_provider_and_nothing_breaks() -> None:
    assert asyncio.run(builder_with(FakeRouter(active=False)).chapter_photos(rich_guide())) == {}
    assert asyncio.run(builder_with(None).chapter_photos(rich_guide())) == {}
    from app.generators.samples import BLUEPRINT

    assert (
        asyncio.run(builder_with(FakeRouter()).chapter_photos(BLUEPRINT)) == {}
    )  # no tiene capítulos


def test_the_wide_format_is_known_to_the_image_router_and_pixabay() -> None:
    from PIL import Image

    from app.ads.images.pixabay import ORIENTATION, RATIO
    from app.ads.images.router import ASPECTS, fit_image

    assert (
        ASPECTS["16:9"] == (16, 9)
        and RATIO["16:9"] == (16, 9)
        and ORIENTATION["16:9"] == "horizontal"
    )
    buffer = io.BytesIO()
    Image.new("RGB", (2400, 1600), "#223344").save(buffer, "JPEG")
    out = Image.open(io.BytesIO(fit_image(buffer.getvalue(), "16:9")))
    assert out.size == (1080, 607)


def test_the_prompts_teach_the_visual_types_in_both_markets() -> None:
    from app.content.prompts import PromptLibrary

    library = PromptLibrary(SETTINGS.prompts_dir)
    for market in ("es-LATAM", "pt-BR"):
        for fmt in (
            Format.PDF_GUIDE,
            Format.EPUB,
            Format.BLUEPRINT,
            Format.CHECKLIST,
            Format.PLANNER,
        ):
            guide = library.format_guide(market, fmt)
            for kind in ("process", "timeline", "comparison", "matrix", "illustrative"):
                assert kind in guide, (market, fmt, kind)
        assert "roadmap" in library.format_guide(market, Format.BLUEPRINT)
        assert "flow" in library.format_guide(market, Format.BLUEPRINT)
    assert re.search(r"nunca inventes", library.format_guide("es-LATAM", Format.PDF_GUIDE), re.I)
    assert uuid4()  # (import usado)


# ───────────────────────────── reglas: todo producto lleva visuales ─────────────────────────────


def rules_for(content):
    from app.content.rules import check_content_rules

    return check_content_rules(content)


def test_content_without_infographics_is_sent_back_to_the_ai() -> None:
    from app.generators.samples import BLUEPRINT, CHECKLIST, GUIDE, PLANNER

    guide_errors = " ".join(rules_for(GUIDE))
    assert "overview" in guide_errors and "Capítulo 1" in guide_errors
    blueprint_errors = " ".join(rules_for(BLUEPRINT))
    assert (
        "roadmap" in blueprint_errors
        and "fase 1" in blueprint_errors
        and "success_visual" in blueprint_errors
    )
    assert "visual" in " ".join(rules_for(CHECKLIST))
    assert "roadmap" in " ".join(rules_for(PLANNER))


def test_rich_content_passes_the_rules() -> None:
    for content in (rich_guide(), rich_blueprint(), rich_checklist(), rich_planner()):
        assert rules_for(content) == []


def bad(kind: str, n: int, **extra) -> Visual:
    return Visual(
        kind=kind, title="t", items=[VisualItem(label=f"i{i}", value=1) for i in range(n)], **extra
    )


def test_each_visual_kind_is_validated_for_what_it_needs_to_draw() -> None:
    from app.content.rules import _visual_errors

    assert _visual_errors(bad("process", 2), "x") and not _visual_errors(bad("process", 4), "x")
    assert _visual_errors(bad("process", 9), "x")
    assert _visual_errors(bad("matrix", 4), "x")  # sin ejes
    assert not _visual_errors(bad("matrix", 4, axis_x="a", axis_y="b"), "x")
    assert _visual_errors(bad("matrix", 3, axis_x="a", axis_y="b"), "x")
    assert _visual_errors(bad("comparison", 3), "x")  # sin columna derecha ni títulos
    assert _visual_errors(
        bad("bars", 3).model_copy(update={"items": [VisualItem(label="a")] * 3}), "x"
    )
    assert not _visual_errors(bad("donut", 3), "x")
    assert _visual_errors(Visual(kind="cards", title="t", items=[VisualItem(label=" ")] * 3), "x")


def test_the_engine_retries_with_the_visual_errors_as_feedback() -> None:
    from app.generators.samples import GUIDE
    from tests.fakes import FakeLLM, make_outline, make_request
    from tests.test_engines import USER, run, service

    outline = make_outline()
    llm = FakeLLM([GUIDE, rich_guide()])
    result = run(
        service(llm).generate_item(
            user_id=USER,
            product_id=uuid4(),
            request=make_request(),
            outline=outline,
            item=outline.main,
        )
    )
    assert result.overview is not None and len(llm.calls) == 2
    assert "infografía" in llm.calls[1].user and "overview" in llm.calls[1].user
