"""Portada de un producto: arte generativo de un estilo o una imagen propia del usuario.

`products.cover` guarda un `CoverSpec`. Un producto anterior a esta función (columna vacía) se
queda sin arte, como se veía antes; los nuevos arrancan en `auto`.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.generators.cover_art import ArtStyle, render_art, resolve_style
from app.generators.cover_image import veil_opacity
from app.templates_engine.model import Template

ArtChoice = Literal["auto", "topo", "waves", "circles", "bauhaus", "facets", "none"]


class CoverSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    art: ArtChoice = "auto"
    # Imagen propia subida por el usuario (reemplaza al arte). Vive en `<user>/covers/<id>.jpg`.
    image_id: UUID | None = None


def stored_spec(product: dict) -> CoverSpec:
    """El `cover` guardado; un producto viejo (sin nada) queda sin arte."""
    raw = product.get("cover")
    return CoverSpec.model_validate(raw) if raw else CoverSpec(art="none")


def image_path(user_id: UUID | str, image_id: UUID | str) -> str:
    return f"{user_id}/covers/{image_id}.jpg"


async def image_exists(storage, user_id: UUID | str, image_id: UUID | str) -> bool:
    """Las imágenes viven bajo la carpeta del usuario: la de otro nunca se resuelve."""
    try:
        await storage.download(image_path(user_id, image_id))
    except Exception:
        return False
    return True


def root_id(product: dict) -> str:
    """Las versiones de un producto comparten arte: la semilla sale de la raíz del árbol."""
    return str(product.get("root_product_id") or product["id"])


def art_for_piece(
    spec: CoverSpec, product: dict, template: Template, role: str, order: int
) -> tuple[ArtStyle | None, str]:
    """Estilo de arte del paquete y SVG de esta pieza (mismo estilo, motivo propio)."""
    style = resolve_style(spec.art, root_id(product))
    if style is None:
        return None, ""
    seed = f"{root_id(product)}:{role}:{order}"
    return style, render_art(style, seed, template.palette, template.style.cover)


def veil_for(jpeg: bytes, template: Template) -> float:
    return veil_opacity(jpeg, template.palette)
