"""Ebook EPUB (ebooklib) con la paleta y las tipografías de la plantilla."""

import io
import uuid
from pathlib import Path
from typing import ClassVar

from ebooklib import epub

from app.content.schemas import Format
from app.content.schemas.formats import GuideContent
from app.generators.base import FileArtifact, RenderContext, artifact, fit_cover_text, register
from app.generators.pdf import without_chapter_numbers
from app.generators.render import html_to_pdf, pdf_page_to_png
from app.templates_engine.model import Template

LANG = {"pt-BR": "pt-BR", "es-LATAM": "es"}


def cover_png(template: Template, ctx: RenderContext, cover: dict, width: int = 1400) -> bytes:
    cover = {
        "product_name": ctx.product_name,
        "subtitle": "",
        "promise": ctx.promise,
        **ctx.cover_extra,
        **cover,
    }
    html = template.render_html("cover_page", c=None, ctx=ctx, cover=fit_cover_text(cover))
    return pdf_page_to_png(html_to_pdf(html, template.base_dir), width=width)


def book_css(template: Template, font_files: list[tuple[str, int, str]]) -> str:
    p = template.palette
    faces = "".join(
        f"@font-face {{ font-family: '{family}'; font-weight: {weight}; src: url('../{path}'); }}\n"
        for family, weight, path in font_files
    )
    return (
        faces
        + f"""
body {{ font-family: '{template.fonts.body.family}', serif; line-height: 1.5; color: {p.text}; }}
h1, h2, h3 {{ font-family: '{template.fonts.heading.family}', sans-serif; color: {p.primary}; }}
h3 {{ color: {p.secondary}; }}
.chapter-label {{ color: {p.accent}; font-weight: bold; text-transform: uppercase;
  font-size: 0.8em; }}
.summary {{ color: {p.muted}; font-style: italic; }}
.callout {{ border-left: 4px solid {p.accent}; padding: 0.4em 0.8em; margin: 1em 0;
  background: {p.surface}; }}
.callout-tip {{ border-color: {p.tip}; }} .callout-warning {{ border-color: {p.warning}; }}
.callout-exercise {{ border-color: {p.exercise}; }}
.callout-title {{ font-weight: bold; }}
.example {{ background: {p.surface}; padding: 0.4em 0.8em; }}
.example-label {{ font-weight: bold; font-size: 0.8em; color: {p.secondary}; }}
"""
    )


def build_epub(content: GuideContent, template: Template, ctx: RenderContext) -> bytes:
    content = without_chapter_numbers(content)
    labels = ctx.labels
    book = epub.EpubBook()
    book.set_identifier(f"urn:uuid:{uuid.uuid4()}")
    book.set_title(content.title)
    book.set_language(LANG[ctx.market])
    book.add_author(ctx.product_name or content.title)
    book.add_metadata("DC", "description", content.subtitle)

    cover = {"title": content.title, "subtitle": content.subtitle, "promise": content.promise}
    book.set_cover("cover.png", cover_png(template, ctx, cover))

    font_files = []
    for face in template.font_faces():
        source = Path(str(face["path"]))
        path = f"fonts/{source.parent.name}-{face['weight']}.ttf"
        book.add_item(
            epub.EpubItem(
                uid=path, file_name=path, media_type="font/ttf", content=source.read_bytes()
            )
        )
        font_files.append((str(face["family"]), int(face["weight"]), path))
    css = epub.EpubItem(
        uid="style",
        file_name="style/book.css",
        media_type="text/css",
        content=book_css(template, font_files).encode(),
    )
    book.add_item(css)

    def page(name: str, heading: str, **context) -> epub.EpubHtml:
        defaults = {"label": "", "chapter": None, "texts": [], "next_steps": []}
        html = template.render_html(
            "epub_chapter", ctx=ctx, heading=heading, **{**defaults, **context}
        )
        item = epub.EpubHtml(title=heading, file_name=f"{name}.xhtml", lang=LANG[ctx.market])
        item.content = html
        item.add_item(css)
        book.add_item(item)
        return item

    chapters = [page("intro", labels["introduction"], texts=content.introduction)]
    for i, chapter in enumerate(content.chapters, start=1):
        chapters.append(
            page(f"ch-{i}", chapter.title, chapter=chapter, label=f"{labels['chapter']} {i}")
        )
    chapters.append(
        page("end", labels["conclusion"], texts=content.conclusion, next_steps=content.next_steps)
    )

    book.toc = chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *chapters]
    buffer = io.BytesIO()
    epub.write_epub(buffer, book)
    return buffer.getvalue()


@register
class EpubGenerator:
    format: ClassVar[Format] = Format.EPUB
    outputs: ClassVar[tuple[str, ...]] = ("epub",)

    def generate(
        self, content: GuideContent, template: Template, ctx: RenderContext
    ) -> list[FileArtifact]:
        return [artifact(ctx, "epub", build_epub(content, template, ctx))]
