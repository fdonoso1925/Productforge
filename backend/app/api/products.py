from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import CurrentUser, get_current_user
from app.content import rules
from app.content.schemas import PackageOutline
from app.db.supabase import NotFound
from app.deps import ServicesDep
from app.pipeline.generate import package_request

router = APIRouter(prefix="/products")
User = Annotated[CurrentUser, Depends(get_current_user)]

SIGNED_URL_SECONDS = 600


class JobResponse(BaseModel):
    job_id: UUID


class DownloadResponse(BaseModel):
    url: str


async def owned_product(services, product_id: UUID, user: CurrentUser) -> dict:
    try:
        return await services.products.get(product_id, user.id)
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "producto no encontrado") from None


@router.put("/{product_id}/outline")
async def save_outline(
    product_id: UUID, outline: PackageOutline, user: User, services: ServicesDep
) -> PackageOutline:
    """Guarda el outline editado por el usuario, aplicando las mismas reglas que a la IA."""
    product = await owned_product(services, product_id, user)
    errors = rules.check_package_rules(outline, package_request(product))
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"errors": errors})
    await services.products.update(
        product_id, outline=outline.model_dump(mode="json"), title=outline.product_name
    )
    return outline


@router.post("/{product_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate(product_id: UUID, user: User, services: ServicesDep) -> JobResponse:
    product = await owned_product(services, product_id, user)
    if not product.get("outline"):
        raise HTTPException(status.HTTP_409_CONFLICT, "el producto no tiene outline")
    if await services.jobs.active_for_product(product_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "ya hay una generación en curso")
    job = await services.jobs.enqueue(
        product_id=product_id, user_id=user.id, kind="generate", payload={}
    )
    await services.products.update(product_id, status="generating")
    return JobResponse(job_id=job["id"])


files_router = APIRouter(prefix="/files")


@files_router.get("/{file_id}/download")
async def download(file_id: UUID, user: User, services: ServicesDep) -> DownloadResponse:
    try:
        row = await services.files.get(file_id, user.id)
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "archivo no encontrado") from None
    url = await services.storage.signed_url(row["storage_path"], SIGNED_URL_SECONDS)
    return DownloadResponse(url=url)
