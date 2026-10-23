"""API del módulo Creativos para Meta Ads (fases 2 y 3: estrategia + composición sin IA de imagen).

Flujo: brief (de un producto o manual) → avatares → ángulos → lote (job `ad_plan`: copy,
semáforo de políticas y pre-score) → revisión/edición del texto → composición (job `ad_render`).
Editar un texto y volver a componer no usa IA.
"""

import asyncio
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from app.ads import jobs as ad_jobs
from app.ads.insights import winner_angles
from app.ads.schemas import (
    AdBrief,
    AdCopy,
    AdProof,
    Avatar,
    CreativeDraft,
    ImageCopy,
    Ratio,
)
from app.api.products import SIGNED_URL_SECONDS, owned_product
from app.auth import CurrentUser, get_current_user
from app.content.schemas import Market, Problem
from app.db.supabase import NotFound
from app.deps import ServicesDep
from app.security import ai_rate_limit, work_rate_limit
from app.templates_engine.model import list_templates

router = APIRouter(prefix="/ads")
User = Annotated[CurrentUser, Depends(get_current_user)]

MAX_PICKS = 8
MAX_CREATIVES_PER_BATCH = 20
DEFAULT_TEMPLATE = "minimal-clean"
ACTIVE_BATCH_STATUSES = ("planning", "rendering")


# ───────────────────────────── modelos ─────────────────────────────


class BriefIn(BaseModel):
    """O un producto existente (con precio y urgencia reales opcionales) o un brief manual."""

    product_id: UUID | None = None
    brief: AdBrief | None = None
    price_text: str | None = Field(default=None, max_length=60)
    real_urgency: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def exactly_one(self) -> "BriefIn":
        if (self.product_id is None) == (self.brief is None):
            raise ValueError("indica un producto (product_id) o un brief manual, no ambos")
        return self


class Pick(BaseModel):
    angle_id: str = Field(max_length=40)
    avatar: str = Field(max_length=120)
    count: int = Field(default=2, ge=1, le=5)


class BatchIn(BriefIn):
    avatars: list[Avatar] = Field(min_length=1, max_length=5)
    picks: list[Pick] = Field(min_length=1, max_length=MAX_PICKS)
    ratios: list[Ratio] = Field(default_factory=lambda: ["4x5"], min_length=1, max_length=3)
    template_id: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9-]+$")


class AvatarsOut(BaseModel):
    brief: AdBrief
    avatars: list[Avatar]


class AnglesIn(BriefIn):
    avatars: list[Avatar] = Field(min_length=1, max_length=5)
    count: int = Field(default=6, ge=3, le=10)


class AngleInfo(BaseModel):
    id: str
    name: str
    description: str
    needs: str | None = None


class AnglesOut(BaseModel):
    available: list[AngleInfo]
    suggestions: list[dict[str, Any]]
    winners: list[str] = []  # ángulos que ya rindieron bien con tus resultados


class JobOut(BaseModel):
    job_id: UUID


class BatchOut(BaseModel):
    batch_id: UUID
    job_id: UUID


class RenderIn(BaseModel):
    creative_ids: list[UUID] = Field(default_factory=list, max_length=200)


class EditIn(BaseModel):
    image: ImageCopy | None = None
    ad: AdCopy | None = None


class ProofIn(BaseModel):
    kind: str = Field(pattern=r"^(testimonial|stat|authority)$")
    text: str = Field(min_length=3, max_length=500)
    author: str | None = Field(default=None, max_length=80)
    product_id: UUID | None = None


# ───────────────────────────── helpers ─────────────────────────────


def unprocessable(*errors: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"errors": list(errors)})


def brief_from_product(product: dict, *, price: str = "", urgency: str = "") -> AdBrief:
    """Los hechos del producto. El precio y la urgencia solo entran si el usuario los da: la
    ficha comercial sugiere un rango, que no es un precio real."""
    problem = Problem.model_validate(product["problem"])
    outline = product.get("outline") or {}
    main = outline.get("main") or {}
    return AdBrief(
        market=product["market"],
        niche=product["niche"],
        product_name=outline.get("product_name") or product.get("title") or problem.title,
        problem=problem.title[:500],
        audience=(product.get("audience_override") or problem.audience)[:500],
        promise=(main.get("promise") or problem.promised_result)[:500],
        price_text=price,
        bonuses=[b["title"] for b in outline.get("bonuses", []) if b.get("title")][:8],
        real_urgency=urgency,
        reference=product.get("reference") or None,
    )


async def resolve_brief(services, user: CurrentUser, body: BriefIn) -> tuple[AdBrief, dict | None]:
    if body.brief is not None:
        return body.brief, None
    assert body.product_id is not None
    product = await owned_product(services, body.product_id, user)
    brief = brief_from_product(
        product, price=body.price_text or "", urgency=body.real_urgency or ""
    )
    return brief, product


async def owned_batch(services, batch_id: UUID, user: CurrentUser) -> dict:
    try:
        return await services.ad_batches.get(batch_id, user.id)
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lote no encontrado") from None


async def owned_creative(services, creative_id: UUID, user: CurrentUser) -> dict:
    try:
        return await services.ad_creatives.get(creative_id, user.id)
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "creativo no encontrado") from None


async def user_proofs(services, user: CurrentUser, product_id: UUID | None) -> list[AdProof]:
    return ad_jobs.proofs_from_rows(await services.ad_proofs.list(user.id, product_id))


async def require_no_active_job(services, batch: dict) -> None:
    if await services.jobs.active_for_batch(UUID(batch["id"])):
        raise HTTPException(status.HTTP_409_CONFLICT, "el lote ya tiene un trabajo en curso")


# ───────────────────────────── catálogo y brief ─────────────────────────────


@router.get("/templates")
def ad_templates(services: ServicesDep) -> dict[str, Any]:
    """Plantillas de anuncio disponibles y formatos con sus zonas seguras (para el asistente)."""
    renderer = services.ad_renderer
    return {
        "templates": [t.model_dump() for t in renderer.templates.values()],
        "ratios": [
            {"id": r.id, "width": r.width, "height": r.height, "label": r.label}
            for r in renderer.ratios.values()
        ],
    }


@router.post("/brief")
async def brief(body: BriefIn, user: User, services: ServicesDep) -> AdBrief:
    """El brief resuelto (sin IA): sirve para que el usuario revise y complete precio y urgencia."""
    return (await resolve_brief(services, user, body))[0]


# ───────────────────────────── estrategia (IA) ─────────────────────────────


@router.post("/avatars", dependencies=[Depends(ai_rate_limit)])
async def avatars(body: BriefIn, user: User, services: ServicesDep) -> AvatarsOut:
    brief_, _ = await resolve_brief(services, user, body)
    proposals = await services.ad_strategy.avatars(user_id=user.id, brief=brief_)
    return AvatarsOut(brief=brief_, avatars=proposals)


@router.post("/angles", dependencies=[Depends(ai_rate_limit)])
async def angles(body: AnglesIn, user: User, services: ServicesDep) -> AnglesOut:
    brief_, product = await resolve_brief(services, user, body)
    proofs = await user_proofs(services, user, UUID(product["id"]) if product else None)
    available = services.ad_strategy.available(brief_, proofs)
    winners = [
        w
        for w in await winner_angles(
            batches=services.ad_batches,
            creatives=services.ad_creatives,
            results=services.ad_results,
            user_id=user.id,
            market=brief_.market,
            niche=brief_.niche,
        )
        if w in available
    ]
    suggestions = await services.ad_strategy.angles(
        user_id=user.id,
        brief=brief_,
        avatars=body.avatars,
        proofs=proofs,
        winners=winners,
        count=body.count,
    )
    return AnglesOut(
        available=[
            AngleInfo(
                id=k,
                name=v["name"],
                description=v["description"],
                needs=v.get("needs"),
            )
            for k, v in available.items()
        ],
        suggestions=[s.model_dump() for s in suggestions],
        winners=winners,
    )


@router.post(
    "/batches", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(ai_rate_limit)]
)
async def create_batch(body: BatchIn, user: User, services: ServicesDep) -> BatchOut:
    brief_, product = await resolve_brief(services, user, body)
    product_id = UUID(product["id"]) if product else None
    proofs = await user_proofs(services, user, product_id)
    available = services.ad_strategy.available(brief_, proofs)

    errors = []
    names = {a.name for a in body.avatars}
    for i, pick in enumerate(body.picks):
        if pick.angle_id not in available:
            errors.append(f"picks[{i}]: el ángulo «{pick.angle_id}» no está disponible")
        if pick.avatar not in names:
            errors.append(f"picks[{i}]: el avatar «{pick.avatar}» no existe")
    if sum(p.count for p in body.picks) > MAX_CREATIVES_PER_BATCH:
        errors.append(f"máximo {MAX_CREATIVES_PER_BATCH} creativos por lote")
    if len(set(body.ratios)) != len(body.ratios):
        errors.append("formatos repetidos")
    if len(names) != len(body.avatars):
        errors.append("los avatares deben tener nombres distintos")
    template_id = body.template_id or (product["template_id"] if product else DEFAULT_TEMPLATE)
    if template_id not in {t.id for t in list_templates(services.settings.templates_dir)}:
        errors.append(f"plantilla «{template_id}» desconocida")
    if errors:
        raise unprocessable(*errors)

    batch = await services.ad_batches.create(
        {
            "user_id": str(user.id),
            "product_id": str(product_id) if product_id else None,
            "niche": brief_.niche,
            "market": brief_.market,
            "template_id": template_id,
            "brief": brief_.model_dump(mode="json"),
            "avatars": [a.model_dump() for a in body.avatars],
            "picks": [p.model_dump() for p in body.picks],
            "ratios": list(body.ratios),
            "status": "planning",
            "prompt_version": services.prompts.version,
        }
    )
    job = await services.jobs.enqueue(
        user_id=user.id, batch_id=UUID(batch["id"]), kind="ad_plan", payload={}
    )
    return BatchOut(batch_id=UUID(batch["id"]), job_id=UUID(job["id"]))


# ───────────────────────────── lotes y creativos ─────────────────────────────


@router.get("/batches")
async def list_batches(user: User, services: ServicesDep) -> list[dict]:
    return await services.ad_batches.list_for_user(user.id)


@router.get("/batches/{batch_id}")
async def get_batch(batch_id: UUID, user: User, services: ServicesDep) -> dict:
    batch = await owned_batch(services, batch_id, user)
    active = await services.jobs.active_for_batch(batch_id)
    return {
        "batch": batch,
        "creatives": await services.ad_creatives.list_for_batch(batch_id),
        "job": active[0] if active else None,
    }


@router.post(
    "/batches/{batch_id}/render",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(work_rate_limit)],
)
async def render_batch(batch_id: UUID, body: RenderIn, user: User, services: ServicesDep) -> JobOut:
    """Compone las imágenes pendientes (todas o las indicadas). No usa IA."""
    batch = await owned_batch(services, batch_id, user)
    if batch["status"] == "planning":
        raise HTTPException(status.HTTP_409_CONFLICT, "el lote aún se está planificando")
    await require_no_active_job(services, batch)
    job = await services.jobs.enqueue(
        user_id=user.id,
        batch_id=batch_id,
        kind="ad_render",
        payload={"creative_ids": [str(i) for i in body.creative_ids]},
    )
    return JobOut(job_id=UUID(job["id"]))


async def batch_and_context(services, creative: dict, user: CurrentUser):
    batch = await services.ad_batches.get(creative["batch_id"], user.id)
    product_id = UUID(batch["product_id"]) if batch.get("product_id") else None
    return batch, ad_jobs.batch_brief(batch), await user_proofs(services, user, product_id)


@router.put("/creatives/{creative_id}", dependencies=[Depends(work_rate_limit)])
async def edit_creative(creative_id: UUID, body: EditIn, user: User, services: ServicesDep) -> dict:
    """Edita el texto de un creativo (y de sus otros formatos) y recompone lo ya renderizado.

    Pasa por las mismas reglas y el mismo semáforo que el texto de la IA, pero sin IA."""
    creative = await owned_creative(services, creative_id, user)
    if body.image is None and body.ad is None:
        raise unprocessable("no hay nada que cambiar")
    batch, brief_, proofs = await batch_and_context(services, creative, user)
    old = ad_jobs.draft_of(creative)
    draft = CreativeDraft(
        **{
            **old.model_dump(),
            **{k: v for k, v in (("image", body.image), ("ad", body.ad)) if v is not None},
        }
    )
    angle = services.prompts.angle_library(brief_.market).get(creative["angle"], {})
    errors, verdict = ad_jobs.recheck(
        creative, draft, brief_, proofs, angle.get("needs") == "proof"
    )
    if errors:
        raise unprocessable(*errors)

    siblings = [
        c
        for c in await services.ad_creatives.list_for_batch(batch["id"])
        if c["group_id"] == creative["group_id"] and c["status"] != "discarded"
    ]
    for sibling in siblings:
        await services.ad_creatives.update(
            sibling["id"],
            copy=draft.model_dump(mode="json"),
            policy_status=verdict.status,
            policy_notes=verdict.model_dump(mode="json", exclude={"status"}),
        )
        sibling["copy"] = draft.model_dump(mode="json")
    redo = [c for c in siblings if c["status"] == "rendered" or c["id"] == creative["id"]]
    deps = services.ads()
    template = await asyncio.to_thread(
        ad_jobs.load_template, services.settings.templates_dir, batch["template_id"]
    )
    mockup = (
        await asyncio.to_thread(ad_jobs.make_mockup, template, batch, brief_)
        if ad_jobs.needs_mockup(deps, redo)
        else None
    )
    for c in redo:
        try:
            await ad_jobs.render_creative(deps, batch, c, template=template, mockup=mockup)
        except Exception:
            await services.ad_creatives.update(c["id"], status="error")
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, "no se pudo componer"
            ) from None
    return await services.ad_creatives.get(creative_id, user.id)


@router.post("/creatives/{creative_id}/render", dependencies=[Depends(work_rate_limit)])
async def render_one(creative_id: UUID, user: User, services: ServicesDep) -> dict:
    creative = await owned_creative(services, creative_id, user)
    if creative["status"] == "discarded":
        raise HTTPException(status.HTTP_409_CONFLICT, "el creativo está descartado")
    batch, brief_, _ = await batch_and_context(services, creative, user)
    deps = services.ads()
    template = await asyncio.to_thread(
        ad_jobs.load_template, services.settings.templates_dir, batch["template_id"]
    )
    mockup = (
        await asyncio.to_thread(ad_jobs.make_mockup, template, batch, brief_)
        if ad_jobs.needs_mockup(deps, [creative])
        else None
    )
    try:
        await ad_jobs.render_creative(deps, batch, creative, template=template, mockup=mockup)
    except Exception:
        await services.ad_creatives.update(creative_id, status="error")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "no se pudo componer") from None
    return await services.ad_creatives.get(creative_id, user.id)


@router.post("/creatives/{creative_id}/discard")
async def discard(creative_id: UUID, user: User, services: ServicesDep) -> dict:
    creative = await owned_creative(services, creative_id, user)
    await services.ad_creatives.update(creative_id, status="discarded")
    return {**creative, "status": "discarded"}


@router.get("/creatives/{creative_id}/url")
async def creative_url(creative_id: UUID, user: User, services: ServicesDep) -> dict[str, str]:
    creative = await owned_creative(services, creative_id, user)
    if not creative.get("storage_path"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "el creativo aún no tiene imagen")
    return {"url": await services.storage.signed_url(creative["storage_path"], SIGNED_URL_SECONDS)}


# ───────────────────────────── pruebas reales ─────────────────────────────


@router.get("/proofs")
async def list_proofs(
    user: User, services: ServicesDep, product_id: UUID | None = None
) -> list[dict]:
    return await services.ad_proofs.list(user.id, product_id)


@router.post(
    "/proofs", status_code=status.HTTP_201_CREATED, dependencies=[Depends(work_rate_limit)]
)
async def add_proof(body: ProofIn, user: User, services: ServicesDep) -> dict:
    """Un testimonio o dato REAL. Es lo único que los anuncios pueden citar como prueba social."""
    if body.product_id:
        await owned_product(services, body.product_id, user)
    return await services.ad_proofs.add(
        {
            "user_id": str(user.id),
            "product_id": str(body.product_id) if body.product_id else None,
            "kind": body.kind,
            "text": body.text.strip(),
            "author": body.author,
        }
    )


@router.delete("/proofs/{proof_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proof(proof_id: UUID, user: User, services: ServicesDep) -> None:
    await services.ad_proofs.delete(proof_id, user.id)


__all__ = ["Market", "router"]


@router.get("/images/status")
async def image_status(services: ServicesDep) -> dict[str, Any]:
    """Qué proveedores de imagen están activos hoy y cuánto se usó (sin claves)."""
    return {
        "providers": await services.ad_images.status(),
        "photo_templates": any(t.uses_image for t in services.ad_renderer.templates.values())
        and bool(services.ad_images.active()),
    }


# ───────────────────────────── entrega: URLs, ZIP/CSV y Drive ─────────────────────────────


async def rendered_creatives(services, batch_id: UUID) -> list[dict]:
    return [
        c
        for c in await services.ad_creatives.list_for_batch(batch_id)
        if c["status"] == "rendered" and c.get("storage_path")
    ]


@router.post("/batches/{batch_id}/urls")
async def creative_urls(batch_id: UUID, user: User, services: ServicesDep) -> dict[str, str]:
    """URLs firmadas (10 min) de todas las imágenes compuestas del lote, para la galería."""
    await owned_batch(services, batch_id, user)
    creatives = await rendered_creatives(services, batch_id)
    urls = await asyncio.gather(
        *(services.storage.signed_url(c["storage_path"], SIGNED_URL_SECONDS) for c in creatives)
    )
    return {c["id"]: url for c, url in zip(creatives, urls, strict=True)}


class ExportOut(BaseModel):
    zip_url: str
    csv_url: str
    zip_name: str
    images: int


@router.post("/batches/{batch_id}/export", dependencies=[Depends(work_rate_limit)])
async def export_batch(batch_id: UUID, user: User, services: ServicesDep) -> ExportOut:
    """ZIP con las imágenes por formato + CSV de copys para Ads Manager (y créditos de fotos)."""
    from app.ads import export

    batch = await owned_batch(services, batch_id, user)
    creatives = await rendered_creatives(services, batch_id)
    if not creatives:
        raise HTTPException(status.HTTP_409_CONFLICT, "aún no hay imágenes compuestas")
    brief_ = ad_jobs.batch_brief(batch)
    blobs = await asyncio.gather(*(services.storage.download(c["storage_path"]) for c in creatives))
    folders = {r.id: r.folder for r in services.ad_renderer.ratios.values()}
    try:
        data = export.build_zip(
            batch["market"],
            creatives,
            {c["id"]: b for c, b in zip(creatives, blobs, strict=True)},
            folders,
        )
    except export.ExportTooLarge:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "el lote pesa demasiado") from None
    name = export.batch_slug(batch, brief_.product_name)
    base = f"{user.id}/ads/{batch_id}/export/{name}"
    await services.storage.upload(f"{base}.zip", data, "application/zip")
    await services.storage.upload(
        f"{base}.csv", export.build_csv(batch["market"], creatives), "text/csv"
    )
    return ExportOut(
        zip_url=await services.storage.signed_url(f"{base}.zip", SIGNED_URL_SECONDS),
        csv_url=await services.storage.signed_url(f"{base}.csv", SIGNED_URL_SECONDS),
        zip_name=f"{name}.zip",
        images=len(creatives),
    )


class DriveOut(BaseModel):
    connected: bool
    status: str  # none | uploading | done | error
    total: int = 0
    uploaded: int = 0
    failed: int = 0
    folder_url: str | None = None


@router.get("/batches/{batch_id}/drive")
async def batch_drive(batch_id: UUID, user: User, services: ServicesDep) -> DriveOut:
    batch = await owned_batch(services, batch_id, user)
    state = batch.get("drive") or {}
    connected = await services.drive.is_connected(user.id)
    syncing = bool(await services.jobs.active_for_batch(batch_id, kind="ad_drive"))
    status_ = "uploading" if syncing else state.get("status", "none")
    folder_url = None
    if connected and status_ == "done" and state.get("folder"):
        try:
            folder_url = await services.drive.folder_url(user.id, state["folder"])
        except Exception:
            folder_url = None  # el enlace es un extra; no rompe el estado
    return DriveOut(
        connected=connected,
        status=status_,
        total=state.get("total", 0),
        uploaded=state.get("uploaded", 0),
        failed=state.get("failed", 0),
        folder_url=folder_url,
    )


@router.post(
    "/batches/{batch_id}/drive",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(work_rate_limit)],
)
async def batch_to_drive(batch_id: UUID, user: User, services: ServicesDep) -> JobOut:
    """Copia el lote a Google Drive (Storage sigue siendo el respaldo)."""
    batch = await owned_batch(services, batch_id, user)
    if not services.drive.configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google Drive no está configurado")
    if not await services.drive.is_connected(user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "conecta Google Drive en Ajustes")
    if not await rendered_creatives(services, batch_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "aún no hay imágenes compuestas")
    if await services.jobs.active_for_batch(UUID(batch["id"]), kind="ad_drive"):
        raise HTTPException(status.HTTP_409_CONFLICT, "ya se está copiando a Drive")
    job = await services.jobs.enqueue(
        user_id=user.id, batch_id=batch_id, kind="ad_drive", payload={}
    )
    return JobOut(job_id=UUID(job["id"]))
