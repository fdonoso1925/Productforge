"""Jobs del módulo Creativos: planificar un lote (IA) y componer sus imágenes (sin IA).

`ad_plan` escribe el copy, el semáforo de políticas y el pre-score de cada creativo; no
renderiza nada, para que el usuario revise y edite el texto antes de gastar tiempo. `ad_render`
compone los PNG con WeasyPrint y los guarda en Storage. Volver a componer un texto editado no
llama a la IA.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from app.ads import rules
from app.ads.images.base import ImageRequest
from app.ads.images.router import ImageRouter, RoutedImage
from app.ads.naming import creative_filename, storage_path
from app.ads.render import AdRenderer, product_mockup
from app.ads.repo import AdBatchRepo, AdCreativeRepo, AdProofRepo
from app.ads.schemas import AdBrief, AdProof, Avatar, CreativeDraft, ImageCopy
from app.ads.strategy import AdStrategyService
from app.db.supabase import JobRepo
from app.storage.base import StorageProvider
from app.templates_engine.model import Template, load_template

logger = logging.getLogger("productforge.ads")

PNG = "image/png"
RENDER_CONCURRENCY = 2
FALLBACK_TEMPLATE = "headline_bold"  # sin imagen disponible, el anuncio sale solo con texto


@dataclass
class AdDeps:
    strategy: AdStrategyService
    renderer: AdRenderer
    batches: AdBatchRepo
    creatives: AdCreativeRepo
    proofs: AdProofRepo
    jobs: JobRepo
    storage: StorageProvider
    templates_dir: Any  # Path
    prompt_version: str = ""
    images: ImageRouter | None = None
    sync_target: Any = None  # destino externo (Google Drive); None = sin copia
    results: Any = None  # AdResultRepo: resultados de Ads Manager (aprendizaje)


def available_templates(deps: "AdDeps", brief: AdBrief, proofs: list[AdProof]) -> list[str]:
    """Plantillas que este lote puede usar hoy: las que necesitan foto, solo con un proveedor de
    imagen activo; la de oferta, solo con precio real; la de testimonio, solo con pruebas."""
    has_images = bool(deps.images and deps.images.active())
    out = []
    for template_id, template in deps.renderer.templates.items():
        if template.uses_image and not has_images:
            continue
        if template_id == "offer_stack" and not brief.price_text.strip():
            continue
        if template_id == "testimonial" and not proofs:
            continue
        out.append(template_id)
    return out


def proofs_from_rows(rows: list[dict]) -> list[AdProof]:
    return [
        AdProof(id=str(r["id"]), kind=r["kind"], text=r["text"], author=r.get("author"))
        for r in rows
    ]


def batch_brief(batch: dict) -> AdBrief:
    return AdBrief.model_validate(batch["brief"])


def batch_avatars(batch: dict) -> list[Avatar]:
    return [Avatar.model_validate(a) for a in batch["avatars"]]


def next_filename(taken: set[str], **parts) -> tuple[str, int]:
    """Primer nombre libre `…_v<n>.png`: el número de versión distingue variaciones del mismo
    ángulo, plantilla y formato. Reserva el nombre en `taken`."""
    version = 1
    while (name := creative_filename(**parts, version=version)) in taken:
        version += 1
    taken.add(name)
    return name, version


def creative_rows(
    batch: dict,
    planned: list,
    renderer_ratios: list[str],
    taken: set[str] | None = None,
    parent_id: str | None = None,
) -> list[dict]:
    """Una fila por borrador y formato; los formatos de un mismo borrador comparten `group_id`.

    `taken` son los nombres que el lote ya usa (al iterar); `parent_id`, el creativo mejorado."""
    brief = batch_brief(batch)
    taken = set(taken or ())
    rows = []
    for item in planned:
        group = str(uuid4())
        for ratio in renderer_ratios:
            filename, version = next_filename(
                taken,
                product_name=brief.product_name,
                market=batch["market"],
                angle=item.angle_id,
                template_id=item.draft.template_id,
                ratio=ratio,
            )
            rows.append(
                {
                    "batch_id": batch["id"],
                    "user_id": batch["user_id"],
                    "group_id": group,
                    "angle": item.angle_id,
                    "avatar": item.avatar,
                    "template_id": item.draft.template_id,
                    "ratio": ratio,
                    "copy": item.draft.model_dump(mode="json"),
                    "policy_status": item.policy.status,
                    "policy_notes": item.policy.model_dump(mode="json", exclude={"status"}),
                    "pre_score": item.score.score,
                    "score_notes": item.score.model_dump(mode="json", exclude={"score"}),
                    "version": version,
                    "filename": filename,
                    **({"parent_creative_id": parent_id} if parent_id else {}),
                }
            )
    return rows


async def run_ad_plan(job: dict, deps: AdDeps) -> None:
    batch = await deps.batches.get(job["batch_id"], UUID(job["user_id"]))
    brief = batch_brief(batch)
    product_id = UUID(batch["product_id"]) if batch.get("product_id") else None
    proofs = proofs_from_rows(await deps.proofs.list(UUID(batch["user_id"]), product_id))
    picks = [(p["angle_id"], p["avatar"], int(p["count"])) for p in batch["picks"]]

    async def progress(done: int, total: int) -> None:
        await deps.jobs.update(job["id"], progress={"stage": "copy", "done": done, "total": total})

    await deps.batches.update(batch["id"], status="planning")
    planned = await deps.strategy.plan(
        user_id=UUID(batch["user_id"]),
        brief=brief,
        avatars=batch_avatars(batch),
        picks=picks,
        proofs=proofs,
        templates=available_templates(deps, brief, proofs),
        on_progress=progress,
    )
    await deps.creatives.delete_for_batch(batch["id"])
    await deps.creatives.insert_many(creative_rows(batch, planned, list(batch["ratios"])))
    await deps.batches.update(batch["id"], status="review")
    await deps.jobs.update(
        job["id"],
        progress={
            "stage": "done",
            "creatives": len(planned),
            "angles_failed": len(picks) - len({(p.angle_id, p.avatar) for p in planned}),
        },
    )


# ───────────────────────── composición ─────────────────────────


def draft_of(creative: dict) -> CreativeDraft:
    return CreativeDraft.model_validate(creative["copy"])


def make_mockup(template: Template, batch: dict, brief: AdBrief) -> bytes:
    return product_mockup(template, batch["market"], brief.product_name, brief.promise[:120])


def compose_png(
    renderer: AdRenderer,
    creative: dict,
    *,
    template: Template,
    brief: AdBrief,
    market: str,
    mockup: bytes | None,
    bg_jpeg: bytes | None = None,
    hires: bool = False,
) -> bytes:
    """PNG del creativo. Es CPU (WeasyPrint + pdfium): se llama desde un hilo."""
    draft = draft_of(creative)
    image: ImageCopy = draft.image
    return renderer.render(
        template_id=creative["template_id"],
        copy=image,
        ratio=creative["ratio"],
        product_template=template,
        market=market,
        product_name=brief.product_name,
        mockup_png=mockup if renderer.templates[creative["template_id"]].uses_mockup else None,
        bg_jpeg=bg_jpeg,
        hires=hires,
    )


def creative_path(renderer: AdRenderer, creative: dict, user_id: str, batch_id: str) -> str:
    return storage_path(
        user_id, batch_id, renderer.ratios[creative["ratio"]].folder, creative["filename"]
    )


def image_request(creative: dict, draft: CreativeDraft, niche: str) -> ImageRequest:
    return ImageRequest(
        prompt=draft.scene,
        keywords=tuple(draft.stock_keywords),
        aspect=creative["ratio"].replace("x", ":"),
        sensitive=rules.is_sensitive(niche),
    )


async def switch_to_fallback(deps: AdDeps, batch: dict, creative: dict) -> None:
    """Sin foto disponible el creativo pasa a la plantilla de solo texto (y cambia de nombre)."""
    brief = batch_brief(batch)
    taken = {c["filename"] for c in await deps.creatives.list_for_batch(batch["id"])}
    filename, version = next_filename(
        taken,
        product_name=brief.product_name,
        market=batch["market"],
        angle=creative["angle"],
        template_id=FALLBACK_TEMPLATE,
        ratio=creative["ratio"],
    )
    draft = draft_of(creative).model_copy(update={"template_id": FALLBACK_TEMPLATE})
    values = {
        "template_id": FALLBACK_TEMPLATE,
        "filename": filename,
        "version": version,
        "copy": draft.model_dump(mode="json"),
    }
    await deps.creatives.update(creative["id"], **values)
    creative.update(values)


async def render_creative(
    deps: AdDeps,
    batch: dict,
    creative: dict,
    *,
    template: Template,
    mockup: bytes | None,
) -> str:
    """Compone, sube y marca el creativo como renderizado. Devuelve la ruta en Storage.

    Una plantilla con foto pide la imagen al router (caché → proveedores → tope diario). Si
    ninguno puede, el creativo pasa a la plantilla de solo texto: el lote nunca se cae."""
    brief = batch_brief(batch)
    user_id = UUID(batch["user_id"])
    routed: RoutedImage | None = None
    if deps.renderer.templates[creative["template_id"]].uses_image:
        routed = (
            await deps.images.get(
                user_id=user_id, request=image_request(creative, draft_of(creative), batch["niche"])
            )
            if deps.images
            else None
        )
        if routed is None:
            await switch_to_fallback(deps, batch, creative)
    png = await asyncio.to_thread(
        compose_png,
        deps.renderer,
        creative,
        template=template,
        brief=brief,
        market=batch["market"],
        mockup=mockup,
        bg_jpeg=routed.jpeg if routed else None,
    )
    path = creative_path(deps.renderer, creative, batch["user_id"], batch["id"])
    await deps.storage.upload(path, png, PNG)
    await deps.creatives.update(
        creative["id"],
        status="rendered",
        storage_path=path,
        image_provider=routed.provider if routed else None,
        image_credit=routed.credit if routed else None,
        base_image_path=routed.storage_path if routed else None,
        image_cost_usd=0 if routed is None or routed.from_cache else routed.cost_usd,
    )
    return path


def needs_mockup(deps: AdDeps, creatives: list[dict]) -> bool:
    return any(deps.renderer.templates[c["template_id"]].uses_mockup for c in creatives)


async def run_ad_render(job: dict, deps: AdDeps) -> None:
    batch = await deps.batches.get(job["batch_id"], UUID(job["user_id"]))
    wanted = set(job.get("payload", {}).get("creative_ids") or [])
    everything = await deps.creatives.list_for_batch(batch["id"])
    todo = [
        c
        for c in everything
        if c["status"] in ("planned", "error") and (not wanted or c["id"] in wanted)
    ]
    template = await asyncio.to_thread(load_template, deps.templates_dir, batch["template_id"])
    mockup = (
        await asyncio.to_thread(make_mockup, template, batch, batch_brief(batch))
        if needs_mockup(deps, todo)
        else None
    )
    await deps.batches.update(batch["id"], status="rendering")
    semaphore = asyncio.Semaphore(RENDER_CONCURRENCY)
    done = failed = 0

    async def one(creative: dict) -> None:
        nonlocal done, failed
        async with semaphore:
            try:
                await render_creative(deps, batch, creative, template=template, mockup=mockup)
            except Exception:
                logger.exception("no se pudo componer el creativo %s", creative["id"])
                await deps.creatives.update(creative["id"], status="error")
                failed += 1
            else:
                done += 1
            await deps.jobs.update(
                job["id"],
                progress={
                    "stage": "render",
                    "done": done + failed,
                    "total": len(todo),
                    "failed": failed,
                },
            )

    await asyncio.gather(*(one(c) for c in todo))
    rendered_any = done or any(c["status"] == "rendered" for c in everything)
    await deps.batches.update(batch["id"], status="ready" if rendered_any else "error")
    if todo and not done:
        raise RuntimeError("no se pudo componer ningún creativo")


def recheck(
    creative: dict, draft: CreativeDraft, brief: AdBrief, proofs: list[AdProof], needs_proof: bool
) -> tuple[list[str], Any]:
    """Reglas de largo/contenido y semáforo (sin IA) para un copy editado a mano."""
    errors = rules.check_draft(
        draft,
        allowed_templates=[creative["template_id"]],
        brief=brief,
        proofs=proofs,
        needs_proof=needs_proof,
    )
    return errors, rules.policy_verdict(draft, brief, proofs)


# ───────────────────────── copia a Google Drive ─────────────────────────

DRIVE_CONCURRENCY = 3


async def run_ad_drive(job: dict, deps: AdDeps) -> None:
    """Copia a Drive las imágenes compuestas del lote y su CSV. Storage sigue siendo la fuente."""
    from app.ads.export import build_csv, drive_folder
    from app.storage.google_drive import NotConnected

    target = deps.sync_target
    if target is None:
        raise RuntimeError("no hay destino de sincronización configurado")
    user_id = UUID(job["user_id"])
    batch = await deps.batches.get(job["batch_id"], user_id)
    brief = batch_brief(batch)
    folder = drive_folder(batch, brief.product_name)
    creatives = [
        c
        for c in await deps.creatives.list_for_batch(batch["id"])
        if c["status"] == "rendered" and c.get("storage_path")
    ]
    state = {"status": "uploading", "total": len(creatives) + 1, "uploaded": 0, "failed": 0}
    await deps.batches.update(batch["id"], drive={**state, "folder": folder})
    semaphore = asyncio.Semaphore(DRIVE_CONCURRENCY)

    async def one(c: dict) -> None:
        async with semaphore:
            try:
                data = await deps.storage.download(c["storage_path"])
                relative = f"{deps.renderer.ratios[c['ratio']].folder}/{c['filename']}"
                remote = await target.upload(user_id, f"{folder}/{relative}", data, PNG)
            except NotConnected:
                raise
            except Exception as exc:
                logger.warning("falló la subida de un creativo: %s", type(exc).__name__)
                state["failed"] += 1
                return
            await deps.creatives.update(c["id"], remote_id=remote.id, remote_url=remote.url)
            state["uploaded"] += 1

    try:
        await asyncio.gather(*(one(c) for c in creatives))
        try:
            csv = build_csv(batch["market"], creatives)
            await target.upload(user_id, f"{folder}/copys.csv", csv, "text/csv")
            state["uploaded"] += 1
        except NotConnected:
            raise
        except Exception as exc:
            logger.warning("falló la subida del CSV: %s", type(exc).__name__)
            state["failed"] += 1
    except Exception:
        await deps.batches.update(batch["id"], drive={**state, "status": "error", "folder": folder})
        raise
    status = "error" if state["failed"] else "done"
    await deps.batches.update(batch["id"], drive={**state, "status": status, "folder": folder})
    if state["failed"]:
        raise RuntimeError(f"{state['failed']} archivo(s) sin subir")


# ───────────────────────── iterar un creativo ─────────────────────────


def metrics_hint(results: list[dict]) -> dict | None:
    """Métricas del creativo que se itera, para que la IA sepa qué conservar y qué cambiar."""
    from app.ads.learning import Metrics

    if not results:
        return None
    total = Metrics()
    for r in results:
        total.add(r)
    keys = ("spend", "impressions", "clicks", "purchases", "ctr", "cpc", "cpa", "roas")
    return {k: v for k, v in total.as_dict().items() if k in keys and v is not None}


async def run_ad_iterate(job: dict, deps: AdDeps) -> None:
    """Hooks nuevos para un creativo ya probado: mismo ángulo y avatar, textos distintos.

    Los borradores nuevos entran al mismo lote (apuntando al original con `parent_creative_id`),
    con su semáforo y pre-score, y quedan listos para revisar y componer."""
    from app.ads.strategy import PlannedCreative

    user_id = UUID(job["user_id"])
    batch = await deps.batches.get(job["batch_id"], user_id)
    source = await deps.creatives.get(job["payload"]["creative_id"], user_id)
    count = int(job["payload"].get("count", 2))
    brief = batch_brief(batch)
    product_id = UUID(batch["product_id"]) if batch.get("product_id") else None
    proofs = proofs_from_rows(await deps.proofs.list(user_id, product_id))
    avatar = next(a for a in batch_avatars(batch) if a.name == source["avatar"])

    everything = await deps.creatives.list_for_batch(batch["id"])
    group = [c for c in everything if c["group_id"] == source["group_id"]]
    order = list(deps.renderer.ratios)
    ratios = sorted({c["ratio"] for c in group}, key=order.index)
    results: list[dict] = []
    if deps.results is not None:
        for c in group:
            results += await deps.results.list_for_creative(c["id"], user_id)
    draft = draft_of(source)
    hint = metrics_hint(results)
    iterate_from = {
        "angle": source["angle"],
        "image": draft.image.model_dump(mode="json"),
        "ad": draft.ad.model_dump(mode="json"),
        **({"metrics": hint} if hint else {}),
    }

    await deps.jobs.update(job["id"], progress={"stage": "copy", "done": 0, "total": 1})
    drafts = await deps.strategy.creatives(
        user_id=user_id,
        brief=brief,
        angle_id=source["angle"],
        avatar=avatar,
        count=count,
        proofs=proofs,
        templates=available_templates(deps, brief, proofs),
        iterate_from=iterate_from,
    )
    reviews = await deps.strategy.review(
        user_id=user_id, brief=brief, avatar=avatar, drafts=drafts, proofs=proofs
    )
    planned = [
        PlannedCreative(angle_id=source["angle"], avatar=avatar.name, draft=d, policy=p, score=s)
        for d, (p, s) in zip(drafts, reviews, strict=True)
    ]
    rows = creative_rows(
        batch, planned, ratios, taken={c["filename"] for c in everything}, parent_id=source["id"]
    )
    await deps.creatives.insert_many(rows)
    await deps.batches.update(batch["id"], status="review")
    await deps.jobs.update(job["id"], progress={"stage": "done", "creatives": len(planned)})
