from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import CurrentUser, get_current_user
from app.content import rules
from app.content.schemas import Format, Market, PackageOutline, PackageRequest
from app.db.supabase import NotFound
from app.deps import ServicesDep
from app.pipeline.generate import package_request
from app.pipeline.remodel import apply_formats, plan_remodel
from app.templates_engine.model import list_templates

router = APIRouter(prefix="/products")
User = Annotated[CurrentUser, Depends(get_current_user)]

SIGNED_URL_SECONDS = 600


class JobResponse(BaseModel):
    job_id: UUID


class DownloadResponse(BaseModel):
    url: str


class RemodelRequest(BaseModel):
    """Solo lo que viene en el body cambia: `tone: null` borra el tono, omitirlo lo conserva."""

    template_id: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9-]+$")
    tone: str | None = Field(default=None, max_length=200)
    audience_override: str | None = Field(default=None, max_length=300)
    formats: dict[UUID, Format] = Field(default_factory=dict, max_length=20)


class RemodelResponse(BaseModel):
    product_id: UUID
    job_id: UUID
    plan: dict[str, int]  # piezas que usan IA ("generate") y piezas que no ("rerender")


class DuplicateRequest(BaseModel):
    market: Market


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
        raise HTTPException(
            status.HTTP_409_CONFLICT, "hay un trabajo en curso (generación o subida a OneDrive)"
        )
    job = await services.jobs.enqueue(
        product_id=product_id, user_id=user.id, kind="generate", payload={}
    )
    await services.products.update(product_id, status="generating")
    return JobResponse(job_id=job["id"])


def require_settled(product: dict) -> None:
    """Remodelar, regenerar y duplicar parten de un paquete ya generado."""
    if product["status"] not in ("ready", "error") or not product.get("outline"):
        raise HTTPException(status.HTTP_409_CONFLICT, "primero hay que generar el paquete")


async def require_idle(services, product_id: UUID) -> None:
    if await services.jobs.active_for_product(product_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "hay un trabajo en curso (generación o subida a OneDrive)"
        )


def unprocessable(*errors: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"errors": list(errors)})


@router.post("/{product_id}/items/{item_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_item(
    product_id: UUID, item_id: UUID, user: User, services: ServicesDep
) -> JobResponse:
    """Regenera una sola pieza con IA, sin rehacer el resto del paquete."""
    product = await owned_product(services, product_id, user)
    require_settled(product)
    await require_idle(services, product_id)
    items = await services.items.list_for_product(product_id)
    if not any(i["id"] == str(item_id) for i in items):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pieza no encontrada")
    job = await services.jobs.enqueue(
        product_id=product_id,
        user_id=user.id,
        kind="regenerate_item",
        payload={"item_id": str(item_id)},
    )
    return JobResponse(job_id=job["id"])


@router.post("/{product_id}/remodel", status_code=status.HTTP_202_ACCEPTED)
async def remodel(
    product_id: UUID, body: RemodelRequest, user: User, services: ServicesDep
) -> RemodelResponse:
    """Crea una versión nueva (hija del producto) con otra plantilla, formato, tono o público.

    Solo usa IA para lo que cambia de verdad; el resto reutiliza el contenido guardado.
    """
    parent = await owned_product(services, product_id, user)
    require_settled(parent)
    await require_idle(services, product_id)
    rows = await services.items.list_for_product(product_id)
    current_format = {r["id"]: r["format"] for r in rows}

    requested = {str(k): v for k, v in body.formats.items()}
    if unknown := sorted(set(requested) - set(current_format)):
        raise unprocessable(f"pieza desconocida: {unknown}")
    new_formats = {k: v for k, v in requested.items() if v.value != current_format[k]}

    fields = body.model_fields_set
    template_id = body.template_id if body.template_id else parent["template_id"]
    if template_id not in {t.id for t in list_templates(services.settings.templates_dir)}:
        raise unprocessable("plantilla desconocida")
    tone = (body.tone if "tone" in fields else parent.get("tone")) or None
    audience = (
        body.audience_override if "audience_override" in fields else parent.get("audience_override")
    ) or None
    content_changed = tone != (parent.get("tone") or None) or audience != (
        parent.get("audience_override") or None
    )
    if not (new_formats or content_changed or template_id != parent["template_id"]):
        raise unprocessable("no hay cambios que aplicar")

    outline = apply_formats(PackageOutline.model_validate(parent["outline"]), rows, new_formats)
    request = PackageRequest.model_validate(
        {**package_request(parent).model_dump(), "main_format": outline.main.format}
    )
    if errors := rules.check_package_rules(outline, request):
        raise unprocessable(*errors)

    parent_modes = plan_remodel(rows, new_formats, content_changed)
    uses_ai = "generate" in parent_modes.values()
    child = await services.products.create_child(
        parent,
        template_id=template_id,
        tone=tone,
        audience_override=audience,
        main_format=outline.main.format.value,
        outline=outline.model_dump(mode="json"),
        prompt_version=services.prompts.version if uses_ai else parent["prompt_version"],
    )
    groups = {"main": [outline.main], "order_bump": outline.order_bumps, "bonus": outline.bonuses}
    new_rows = []
    for row in rows:
        item = groups[row["role"]][row["order"]]
        reuse = parent_modes[row["id"]] == "rerender"
        new_rows.append(
            {
                "product_id": child["id"],
                "user_id": str(user.id),
                "role": row["role"],
                "order": row["order"],
                "format": item.format.value,
                "title": row["title"],
                "outline": item.model_dump(mode="json"),
                "content": row.get("content") if reuse else None,
                "content_hash": row.get("content_hash") if reuse else None,
            }
        )
    created = await services.items.insert_many(new_rows)
    new_id = {(r["role"], r["order"]): r["id"] for r in created}
    modes = {new_id[(r["role"], r["order"])]: parent_modes[r["id"]] for r in rows}
    job = await services.jobs.enqueue(
        product_id=UUID(child["id"]),
        user_id=user.id,
        kind="remodel",
        payload={"modes": modes, "commercial": "copy"},
    )
    values = list(modes.values())
    plan = {"generate": values.count("generate"), "rerender": values.count("rerender")}
    return RemodelResponse(product_id=child["id"], job_id=job["id"], plan=plan)


@router.post("/{product_id}/duplicate", status_code=status.HTTP_202_ACCEPTED)
async def duplicate_to_market(
    product_id: UUID, body: DuplicateRequest, user: User, services: ServicesDep
) -> RemodelResponse:
    """Versión adaptada (no traducida) al otro mercado, vinculada al original."""
    parent = await owned_product(services, product_id, user)
    require_settled(parent)
    await require_idle(services, product_id)
    if body.market == parent["market"]:
        raise unprocessable("elige el otro mercado")
    child = await services.products.create_child(
        parent, market=body.market, commercial=None, prompt_version=services.prompts.version
    )
    job = await services.jobs.enqueue(
        product_id=UUID(child["id"]), user_id=user.id, kind="duplicate_market", payload={}
    )
    plan = {"generate": 1, "rerender": 0}
    return RemodelResponse(product_id=child["id"], job_id=job["id"], plan=plan)


files_router = APIRouter(prefix="/files")


@files_router.get("/{file_id}/download")
async def download(file_id: UUID, user: User, services: ServicesDep) -> DownloadResponse:
    try:
        row = await services.files.get(file_id, user.id)
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "archivo no encontrado") from None
    url = await services.storage.signed_url(row["storage_path"], SIGNED_URL_SECONDS)
    return DownloadResponse(url=url)
