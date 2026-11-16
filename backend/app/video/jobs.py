"""Job `ad_video`: guion (IA, una vez) → render (sin IA) → Storage.

El guion se escribe solo si el video aún no lo tiene; volver a componer (otra plantilla, otro
formato, un arreglo del motor) reutiliza el guion guardado y no llama a la IA. El texto del
anuncio para Ads Manager se toma de un creativo ya revisado del mismo ángulo cuando existe.
"""

import asyncio
import logging
from uuid import UUID

from app.ads import rules as ad_rules
from app.ads.jobs import AdDeps, batch_avatars, batch_brief, make_mockup, proofs_from_rows
from app.ads.marks import strip_marks
from app.ads.naming import video_path
from app.ads.schemas import AdBrief, AdCopy, Avatar
from app.templates_engine.model import load_template
from app.video import rules as video_rules
from app.video.render import render_video
from app.video.schemas import VideoScript

logger = logging.getLogger("productforge.video")

MP4, PNG = "video/mp4", "image/png"
# Un video a la vez: el render es CPU pura y no debe frenar al resto de jobs.
_render_lock = asyncio.Lock()


def ad_copy_for(video: dict, creatives: list[dict], script: VideoScript, brief: AdBrief) -> dict:
    """Texto del anuncio en Ads Manager: el de un creativo del mismo ángulo y avatar (ya pasó por
    las reglas y el semáforo); si no hay, uno sobrio armado con el propio guion."""
    for c in creatives:
        if c["angle"] == video["angle"] and c["avatar"] == video["avatar"] and c.get("copy"):
            if c.get("status") != "discarded" and c.get("policy_status") != "red":
                return c["copy"]["ad"]
    hook = " ".join(line.strip() for line in script.hook_lines if line.strip())
    primary = f"{hook} {script.solution_caption}".strip()
    return AdCopy(
        primary_short=primary[: ad_rules.PRIMARY_SHORT_MAX],
        primary_long=primary,
        headline=brief.product_name[: ad_rules.HEADLINE_MAX],
        description=script.benefits_title[: ad_rules.DESCRIPTION_MAX],
        cta="LEARN_MORE",
    ).model_dump(mode="json")


def avatar_named(batch: dict, name: str) -> Avatar:
    for avatar in batch_avatars(batch):
        if avatar.name == name:
            return avatar
    raise ValueError(f"avatar desconocido: {name}")


async def run_ad_video(job: dict, deps: AdDeps) -> None:
    payload = job.get("payload") or {}
    user_id = UUID(job["user_id"])
    video = await deps.videos.get(payload["video_id"], user_id)
    batch = await deps.batches.get(video["batch_id"], user_id)
    brief = batch_brief(batch)
    await deps.videos.update(video["id"], status="rendering", error=None)
    try:
        script = VideoScript.model_validate(video["script"]) if video.get("script") else None
        creatives = await deps.creatives.list_for_batch(batch["id"])
        if script is None:
            product_id = UUID(batch["product_id"]) if batch.get("product_id") else None
            proofs = proofs_from_rows(await deps.proofs.list(user_id, product_id))
            hook_from = ""
            if payload.get("creative_id"):
                source = next((c for c in creatives if c["id"] == payload["creative_id"]), None)
                if source:
                    hook_from = strip_marks(source["copy"]["image"]["headline"])
            await deps.jobs.update(job["id"], progress={"stage": "script"})
            script = await deps.strategy.video_script(
                user_id=user_id,
                brief=brief,
                avatar=avatar_named(batch, video["avatar"]),
                angle_id=video["angle"],
                proofs=proofs,
                hook_from=hook_from,
            )
            verdict = video_rules.script_policy(script, brief, proofs)
            await deps.videos.update(
                video["id"],
                script=script.model_dump(mode="json"),
                ad_copy=ad_copy_for(video, creatives, script, brief),
                policy_status=verdict.status,
                policy_notes=verdict.model_dump(mode="json", exclude={"status"}),
            )
        await deps.jobs.update(job["id"], progress={"stage": "render"})
        template = await asyncio.to_thread(load_template, deps.templates_dir, batch["template_id"])
        cover = await asyncio.to_thread(make_mockup, template, batch, brief)
        async with _render_lock:
            result = await asyncio.to_thread(
                render_video,
                script,
                product_name=brief.product_name,
                template=template,
                templates_dir=deps.templates_dir,
                ratio=video["ratio"],
                cover_png=cover,
                seed=str(video["id"]),
            )
        path = video_path(batch["user_id"], batch["id"], video["filename"])
        thumb = path.removesuffix(".mp4") + ".png"
        await deps.storage.upload(path, result.mp4, MP4)
        await deps.storage.upload(thumb, result.thumbnail, PNG)
        await deps.videos.update(
            video["id"],
            status="ready",
            storage_path=path,
            thumb_path=thumb,
            duration=result.duration,
            error=None,
        )
        await deps.jobs.update(job["id"], progress={"stage": "done"})
    except Exception as exc:
        logger.exception("no se pudo crear el video %s", video["id"])
        # Si ya había un video listo, se conserva: solo se marca el error.
        status = "ready" if video.get("storage_path") else "error"
        await deps.videos.update(video["id"], status=status, error=type(exc).__name__)
        raise
