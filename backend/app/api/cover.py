"""Portadas: vista previa del arte, subida de una imagen propia y selección para un producto."""

import re
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.api.products import SIGNED_URL_SECONDS, owned_product, validate_cover
from app.auth import CurrentUser, get_current_user
from app.config import Settings, get_settings
from app.deps import ServicesDep
from app.generators.cover import CoverSpec, image_exists, image_path
from app.generators.cover_art import STYLE_ORDER, render_art
from app.generators.cover_image import MAX_BYTES, InvalidCoverImage, process_upload
from app.templates_engine.model import load_template

router = APIRouter()
User = Annotated[CurrentUser, Depends(get_current_user)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

SEED_RE = re.compile(r"^[\w:.-]{1,64}$")
TEMPLATE_RE = re.compile(r"^[a-z0-9-]{1,64}$")


class CoverImageResponse(BaseModel):
    image_id: UUID
    url: str
    width: int
    height: int


class CoverImageUrl(BaseModel):
    url: str


@router.get("/cover/art/{style}.svg")
def art_preview(
    style: str,
    settings: SettingsDep,
    template: str = "minimal-clean",
    seed: str = "preview",
    background: bool = False,
) -> Response:
    """Muestra de un estilo con la paleta de una plantilla (para el selector; es pública)."""
    if style not in STYLE_ORDER or not SEED_RE.match(seed) or not TEMPLATE_RE.match(template):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "estilo no encontrado")
    try:
        tpl = load_template(settings.templates_dir, template)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "plantilla no encontrada") from None
    svg = render_art(style, seed, tpl.palette, tpl.style.cover, background=background)  # type: ignore[arg-type]
    return Response(
        svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=3600"}
    )


async def read_limited(request: Request, limit: int) -> bytes:
    """Lee el body cortando en `limit` (también cubre subidas sin Content-Length)."""
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "la imagen es demasiado grande")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/cover-images", status_code=status.HTTP_201_CREATED)
async def upload_cover_image(
    request: Request, user: User, services: ServicesDep
) -> CoverImageResponse:
    """Sube una imagen propia (el body es el archivo). Se valida y se guarda como JPEG limpio."""
    raw = await read_limited(request, MAX_BYTES)
    try:
        image = process_upload(raw)
    except InvalidCoverImage as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    image_id = uuid4()
    path = image_path(user.id, image_id)
    await services.storage.upload(path, image.jpeg, "image/jpeg")
    url = await services.storage.signed_url(path, SIGNED_URL_SECONDS)
    return CoverImageResponse(image_id=image_id, url=url, width=image.width, height=image.height)


@router.get("/cover-images/{image_id}/url")
async def cover_image_url(image_id: UUID, user: User, services: ServicesDep) -> CoverImageUrl:
    if not await image_exists(services.storage, user.id, image_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "imagen no encontrada")
    url = await services.storage.signed_url(image_path(user.id, image_id), SIGNED_URL_SECONDS)
    return CoverImageUrl(url=url)


@router.put("/products/{product_id}/cover")
async def set_cover(
    product_id: UUID, cover: CoverSpec, user: User, services: ServicesDep
) -> CoverSpec:
    """Cambia la portada de un paquete que aún no se generó (el asistente).

    Con el paquete ya generado, la portada se cambia al remodelar: crea una versión nueva y
    conserva la original.
    """
    product = await owned_product(services, product_id, user)
    if product["status"] != "outline_ready":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "la portada de un paquete generado se cambia al remodelar"
        )
    await validate_cover(services, user, cover)
    await services.products.update(product_id, cover=cover.model_dump(mode="json"))
    return cover
