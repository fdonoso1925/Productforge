"""Plantillas visuales como datos (§5).

Cada plantilla es `templates/<id>/template.json` (paleta, tipografías, estilo). Los HTML
base viven en `templates/_base/`; una plantilla puede reemplazar cualquiera poniendo un
archivo con el mismo nombre en su carpeta, y agregar CSS propio en `style.css`.
Agregar una plantilla nueva no requiere tocar código.
"""

import json
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Literal

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup
from pydantic import BaseModel, Field

from app.templates_engine.fonts import font_path

HEX = r"^#[0-9A-Fa-f]{6}$"


class Palette(BaseModel):
    primary: str = Field(pattern=HEX)
    secondary: str = Field(pattern=HEX)
    accent: str = Field(pattern=HEX)
    background: str = Field(pattern=HEX)
    surface: str = Field(pattern=HEX)
    text: str = Field(pattern=HEX)
    muted: str = Field(pattern=HEX)
    on_primary: str = Field(pattern=HEX)
    tip: str = Field(pattern=HEX)
    warning: str = Field(pattern=HEX)
    exercise: str = Field(pattern=HEX)


class FontSpec(BaseModel):
    family: str
    weights: list[int]


class Fonts(BaseModel):
    heading: FontSpec
    body: FontSpec


class Style(BaseModel):
    cover: Literal["centered", "split", "full-bleed", "band", "notebook"]
    callout: Literal["boxed", "left-bar", "pill", "sticky"]
    radius: str = Field(pattern=r"^\d+px$")
    heading_case: Literal["none", "uppercase"]
    paper: Literal["plain", "lined", "dark"]
    decoration: Literal["none", "rule", "block", "blob", "dots", "diagonal"]


class OfficeTheme(BaseModel):
    """Lo único que se aplica en XLSX / DOCX / PPTX: colores y nombres de fuente."""

    primary: str
    secondary: str
    accent: str
    surface: str
    text: str
    muted: str
    on_primary: str
    heading_font: str
    body_font: str


class Template(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str
    description: str
    palette: Palette
    fonts: Fonts
    style: Style
    base_dir: Path = Field(exclude=True)

    @property
    def templates_root(self) -> Path:
        return self.base_dir.parent

    @cached_property
    def _env(self) -> Environment:
        env = Environment(
            loader=ChoiceLoader(
                [FileSystemLoader(self.base_dir), FileSystemLoader(self.templates_root / "_base")]
            ),
            # Todo lo que viene del contenido (IA / usuario) se escapa.
            autoescape=select_autoescape(["html", "j2", "svg"], default_for_string=True),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

        def visual_svg(visual: object, market: str = "es-LATAM") -> Markup:
            # Import tardío: los generadores importan este módulo. El SVG ya sale escapado.
            from app.generators.visuals import render_visual

            return Markup(render_visual(visual, self, market))  # type: ignore[arg-type]  # noqa: S704

        env.globals["visual_svg"] = visual_svg
        return env

    def render_html(self, kind: str, **context: object) -> str:
        return self._env.get_template(f"{kind}.html.j2").render(t=self, **context)

    def font_faces(self) -> list[dict[str, str | int]]:
        """@font-face con rutas absolutas `file://` a las fuentes embebidas."""
        faces = []
        seen: set[tuple[str, int]] = set()
        for spec in (self.fonts.heading, self.fonts.body):
            for weight in spec.weights:
                if (spec.family, weight) in seen:
                    continue
                seen.add((spec.family, weight))
                path = font_path(self.templates_root / "_fonts", spec.family, weight)
                faces.append(
                    {
                        "family": spec.family,
                        "weight": weight,
                        "url": path.as_uri(),
                        "path": str(path),
                    }
                )
        return faces

    @property
    def extra_css(self) -> str:
        css = self.base_dir / "style.css"
        return css.read_text(encoding="utf-8") if css.exists() else ""

    def office_theme(self) -> OfficeTheme:
        p = self.palette
        return OfficeTheme(
            primary=p.primary,
            secondary=p.secondary,
            accent=p.accent,
            surface=p.surface,
            text=p.text,
            muted=p.muted,
            on_primary=p.on_primary,
            heading_font=self.fonts.heading.family,
            body_font=self.fonts.body.family,
        )


@lru_cache(maxsize=64)
def load_template(templates_dir: Path, template_id: str) -> Template:
    base_dir = templates_dir / template_id
    data = json.loads((base_dir / "template.json").read_text(encoding="utf-8"))
    return Template(**data, base_dir=base_dir)


def list_templates(templates_dir: Path) -> list[Template]:
    ids = sorted(p.parent.name for p in templates_dir.glob("*/template.json"))
    return [load_template(templates_dir, i) for i in ids]
