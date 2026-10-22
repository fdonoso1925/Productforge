"""Formatos que se maquetan como PDF con la plantilla visual (HTML/Jinja2 → WeasyPrint)."""

from typing import ClassVar

from app.content.schemas import Format
from app.content.schemas.formats import (
    BlueprintContent,
    ChecklistContent,
    GuideContent,
    PlannerContent,
    SwipeFileContent,
)
from app.generators.base import (
    FileArtifact,
    RenderContext,
    artifact,
    fit_cover_text,
    register,
    strip_chapter_number,
)
from app.generators.render import html_to_pdf
from app.templates_engine.model import Template


def without_chapter_numbers(content: GuideContent) -> GuideContent:
    """La IA a veces numera los títulos ("Capítulo 3 – ..."); la plantilla ya lo hace."""
    chapters = [
        ch.model_copy(update={"title": strip_chapter_number(ch.title)}) for ch in content.chapters
    ]
    return content.model_copy(update={"chapters": chapters})


def render_pdf(template: Template, kind: str, ctx: RenderContext, content, cover: dict) -> bytes:
    cover = {
        "product_name": ctx.product_name,
        "subtitle": "",
        "promise": ctx.promise,
        **ctx.cover_extra,
        **cover,
    }
    html = template.render_html(kind, c=content, ctx=ctx, cover=fit_cover_text(cover))
    return html_to_pdf(html, template.base_dir)


@register
class GuidePdf:
    format: ClassVar[Format] = Format.PDF_GUIDE
    outputs: ClassVar[tuple[str, ...]] = ("pdf",)

    def generate(
        self, content: GuideContent, template: Template, ctx: RenderContext
    ) -> list[FileArtifact]:
        cover = {"title": content.title, "subtitle": content.subtitle, "promise": content.promise}
        pdf = render_pdf(template, "guide", ctx, without_chapter_numbers(content), cover)
        return [artifact(ctx, "pdf", pdf)]


@register
class ChecklistPdf:
    format: ClassVar[Format] = Format.CHECKLIST
    outputs: ClassVar[tuple[str, ...]] = ("pdf",)

    def generate(
        self, content: ChecklistContent, template: Template, ctx: RenderContext
    ) -> list[FileArtifact]:
        pdf = render_pdf(template, "checklist", ctx, content, {"title": content.title})
        return [artifact(ctx, "pdf", pdf)]


@register
class BlueprintPdf:
    format: ClassVar[Format] = Format.BLUEPRINT
    outputs: ClassVar[tuple[str, ...]] = ("pdf",)

    def generate(
        self, content: BlueprintContent, template: Template, ctx: RenderContext
    ) -> list[FileArtifact]:
        cover = {"title": content.title, "subtitle": content.overview}
        return [artifact(ctx, "pdf", render_pdf(template, "blueprint", ctx, content, cover))]


@register
class PlannerPdf:
    format: ClassVar[Format] = Format.PLANNER
    outputs: ClassVar[tuple[str, ...]] = ("pdf",)

    def generate(
        self, content: PlannerContent, template: Template, ctx: RenderContext
    ) -> list[FileArtifact]:
        cover = {
            "title": content.title,
            "subtitle": f"{content.duration_days} {ctx.labels['day']}s",
        }
        return [artifact(ctx, "pdf", render_pdf(template, "planner", ctx, content, cover))]


@register
class SwipeFile:
    """PDF para leer + DOCX para copiar y editar los textos."""

    format: ClassVar[Format] = Format.SWIPE_FILE
    outputs: ClassVar[tuple[str, ...]] = ("pdf", "docx")

    def generate(
        self, content: SwipeFileContent, template: Template, ctx: RenderContext
    ) -> list[FileArtifact]:
        from app.generators.office import swipe_file_docx

        pdf = render_pdf(template, "swipe_file", ctx, content, {"title": content.title})
        return [
            artifact(ctx, "pdf", pdf),
            artifact(ctx, "docx", swipe_file_docx(content, template.office_theme(), ctx)),
        ]
