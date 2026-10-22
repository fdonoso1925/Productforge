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


def proofs_from_rows(rows: list[dict]) -> list[AdProof]:
    return [
        AdProof(id=str(r["id"]), kind=r["kind"], text=r["text"], author=r.get("author"))
        for r in rows
    ]


def batch_brief(batch: dict) -> AdBrief:
    return AdBrief.model_validate(batch["brief"])


def batch_avatars(batch: dict) -> list[Avatar]:
    return [Avatar.model_validate(a) for a in batch["avatars"]]


def creative_rows(batch: dict, planned: list, renderer_ratios: list[str]) -> list[dict]:
    """Una fila por borrador y formato; los borradores de un mismo borrador comparten `group_id`.

    Dos variaciones del mismo ángulo y plantilla se distinguen por el número de versión del
    nombre de archivo (`…_v1.png`, `…_v2.png`)."""
    brief = batch_brief(batch)
    seen: dict[str, int] = {}
    rows = []
    for item in planned:
        group = str(uuid4())
        for ratio in renderer_ratios:
            base = dict(
                product_name=brief.product_name,
                market=batch["market"],
                angle=item.angle_id,
                template_id=item.draft.template_id,
                ratio=ratio,
            )
            seen[f"{item.angle_id}|{item.draft.template_id}|{ratio}"] = (
                seen.get(f"{item.angle_id}|{item.draft.template_id}|{ratio}", 0) + 1
            )
            version = seen[f"{item.angle_id}|{item.draft.template_id}|{ratio}"]
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
                    "filename": creative_filename(**base, version=version),
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
        templates=deps.renderer.available_ids(),
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
        hires=hires,
    )


def creative_path(renderer: AdRenderer, creative: dict, user_id: str, batch_id: str) -> str:
    return storage_path(
        user_id, batch_id, renderer.ratios[creative["ratio"]].folder, creative["filename"]
    )


async def render_creative(
    deps: AdDeps,
    batch: dict,
    creative: dict,
    *,
    template: Template,
    mockup: bytes | None,
) -> str:
    """Compone, sube y marca el creativo como renderizado. Devuelve la ruta en Storage."""
    brief = batch_brief(batch)
    png = await asyncio.to_thread(
        compose_png,
        deps.renderer,
        creative,
        template=template,
        brief=brief,
        market=batch["market"],
        mockup=mockup,
    )
    path = creative_path(deps.renderer, creative, batch["user_id"], batch["id"])
    await deps.storage.upload(path, png, PNG)
    await deps.creatives.update(creative["id"], status="rendered", storage_path=path)
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
