"""Catálogo de plantillas visuales (público: no contiene datos de usuario)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.content.schemas import Format
from app.templates_engine.model import Palette, list_templates

router = APIRouter()
SettingsDep = Annotated[Settings, Depends(get_settings)]


class TemplateInfo(BaseModel):
    id: str
    name: str
    description: str
    palette: Palette
    heading_font: str
    body_font: str


@router.get("/templates")
def templates(settings: SettingsDep) -> list[TemplateInfo]:
    return [
        TemplateInfo(
            id=t.id,
            name=t.name,
            description=t.description,
            palette=t.palette,
            heading_font=t.fonts.heading.family,
            body_font=t.fonts.body.family,
        )
        for t in list_templates(settings.templates_dir)
    ]


@router.get("/templates/{template_id}/preview.png")
def preview(template_id: str, settings: SettingsDep) -> FileResponse:
    ids = {t.id for t in list_templates(settings.templates_dir)}
    if template_id not in ids:  # evita path traversal: solo ids conocidos
        raise HTTPException(404, "plantilla no encontrada")
    path = settings.templates_dir / template_id / "preview.png"
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "max-age=3600"})


@router.get("/formats")
def formats() -> list[str]:
    return [f.value for f in Format]
