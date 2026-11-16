"""Videos de motion graphics de un lote de anuncios (texto e íconos animados con música).

`POST /ads/batches/{id}/videos` crea el video de un ángulo y avatar y encola el job `ad_video`
(la IA escribe el guion una sola vez; el render no usa IA). Editar el guion y volver a componer
no usa IA. Los videos se suben a Meta junto con el lote (siempre en pausa).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.ads import jobs as ad_jobs
from app.ads.naming import video_filename
from app.api.ads import owned_batch, user_proofs
from app.api.products import SIGNED_URL_SECONDS
from app.auth import CurrentUser, get_current_user
from app.db.supabase import NotFound
from app.deps import ServicesDep
from app.security import ai_rate_limit, work_rate_limit
from app.video import rules as video_rules
from app.video.schemas import VideoRatio, VideoScript

router = APIRouter(prefix="/ads")
User = Annotated[CurrentUser, Depends(get_current_user)]

MAX_VIDEOS_PER_BATCH = 12


class VideoIn(BaseModel):
    angle: str = Field(min_length=1, max_length=40)
    avatar: str = Field(min_length=1, max_length=120)
    ratio: VideoRatio = "9x16"
    # Un creativo del lote que ya funcionó: su titular inspira el gancho del video.
    creative_id: UUID | None = None


class VideoJobOut(BaseModel):
    video_id: UUID
    job_id: UUID


async def owned_video(services, video_id: UUID, user: CurrentUser) -> dict:
    try:
        return await services.ad_videos.get(video_id, user.id)
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "video no encontrado") from None


def unprocessable(*errors: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"errors": list(errors)})


@router.post(
    "/batches/{batch_id}/videos",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(ai_rate_limit)],
)
async def create_video(
    batch_id: UUID, body: VideoIn, user: User, services: ServicesDep
) -> VideoJobOut:
    batch = await owned_batch(services, batch_id, user)
    brief = ad_jobs.batch_brief(batch)
    product_id = UUID(batch["product_id"]) if batch.get("product_id") else None
    proofs = await user_proofs(services, user, product_id)
    if body.angle not in services.ad_strategy.available(brief, proofs):
        raise unprocessable(f"el ángulo «{body.angle}» no está disponible para este lote")
    if body.avatar not in {a.name for a in ad_jobs.batch_avatars(batch)}:
        raise unprocessable(f"el avatar «{body.avatar}» no es de este lote")
    existing = await services.ad_videos.list_for_batch(batch["id"])
    if len(existing) >= MAX_VIDEOS_PER_BATCH:
        raise unprocessable(f"un lote tiene como máximo {MAX_VIDEOS_PER_BATCH} videos")
    taken = {v["filename"] for v in existing}
    version = 1
    while (
        name := video_filename(
            product_name=brief.product_name,
            market=batch["market"],
            angle=body.angle,
            ratio=body.ratio,
            version=version,
        )
    ) in taken:
        version += 1
    video = await services.ad_videos.insert(
        {
            "batch_id": batch["id"],
            "user_id": str(user.id),
            "angle": body.angle,
            "avatar": body.avatar,
            "ratio": body.ratio,
            "filename": name,
        }
    )
    payload = {"video_id": video["id"]}
    if body.creative_id:
        payload["creative_id"] = str(body.creative_id)
    job = await services.jobs.enqueue(
        user_id=user.id, kind="ad_video", payload=payload, batch_id=UUID(batch["id"])
    )
    return VideoJobOut(video_id=video["id"], job_id=job["id"])


@router.put("/videos/{video_id}/script", dependencies=[Depends(work_rate_limit)])
async def edit_script(
    video_id: UUID, script: VideoScript, user: User, services: ServicesDep
) -> dict:
    """Cambia los textos del video sin IA: mismas reglas y mismo semáforo que el de la IA."""
    video = await owned_video(services, video_id, user)
    batch = await owned_batch(services, UUID(video["batch_id"]), user)
    brief = ad_jobs.batch_brief(batch)
    errors = video_rules.check_script(script, brief)
    if errors:
        raise unprocessable(*errors)
    product_id = UUID(batch["product_id"]) if batch.get("product_id") else None
    verdict = video_rules.script_policy(
        script, brief, await user_proofs(services, user, product_id)
    )
    await services.ad_videos.update(
        video["id"],
        script=script.model_dump(mode="json"),
        policy_status=verdict.status,
        policy_notes=verdict.model_dump(mode="json", exclude={"status"}),
    )
    return await services.ad_videos.get(video_id, user.id)


@router.post(
    "/videos/{video_id}/render",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(work_rate_limit)],
)
async def rerender_video(video_id: UUID, user: User, services: ServicesDep) -> VideoJobOut:
    """Vuelve a componer el video con el guion guardado (sin IA)."""
    video = await owned_video(services, video_id, user)
    if not video.get("script"):
        raise HTTPException(status.HTTP_409_CONFLICT, "el video todavía no tiene guion")
    if video["status"] == "rendering":
        raise HTTPException(status.HTTP_409_CONFLICT, "el video ya se está componiendo")
    job = await services.jobs.enqueue(
        user_id=user.id,
        kind="ad_video",
        payload={"video_id": video["id"]},
        batch_id=UUID(video["batch_id"]),
    )
    return VideoJobOut(video_id=video["id"], job_id=job["id"])


@router.get("/videos/{video_id}/url")
async def video_url(video_id: UUID, user: User, services: ServicesDep) -> dict:
    video = await owned_video(services, video_id, user)
    if not video.get("storage_path"):
        raise HTTPException(status.HTTP_409_CONFLICT, "el video todavía no está listo")
    return {
        "url": await services.storage.signed_url(video["storage_path"], SIGNED_URL_SECONDS),
        "thumb_url": await services.storage.signed_url(video["thumb_path"], SIGNED_URL_SECONDS)
        if video.get("thumb_path")
        else None,
    }


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(video_id: UUID, user: User, services: ServicesDep) -> None:
    video = await owned_video(services, video_id, user)
    if video["status"] == "rendering":
        raise HTTPException(status.HTTP_409_CONFLICT, "el video se está componiendo")
    if (video.get("meta") or {}).get("ad_id"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "el video ya está en Meta: bórralo desde Ads Manager"
        )
    paths = [p for p in (video.get("storage_path"), video.get("thumb_path")) if p]
    if paths:
        await services.storage.delete(paths)
    await services.ad_videos.delete(video_id, user.id)
