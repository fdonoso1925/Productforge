"""Creativos, fase 6: resultados de Ads Manager, aprendizaje, iteraciones y lotes en otro idioma."""

from collections import defaultdict
from datetime import date
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator

from app.ads import jobs as ad_jobs
from app.ads import results_import, rules
from app.ads.insights import load_insights
from app.ads.schemas import Avatar, Ratio
from app.api.ads import (
    BatchOut,
    JobOut,
    owned_batch,
    owned_creative,
    require_no_active_job,
    unprocessable,
    user_proofs,
)
from app.auth import CurrentUser, get_current_user
from app.content.schemas import Market
from app.db.supabase import NotFound
from app.deps import ServicesDep
from app.security import ai_rate_limit

router = APIRouter(prefix="/ads")
User = Annotated[CurrentUser, Depends(get_current_user)]

MAX_ITERATIONS = 3


# ───────────────────────────── resultados ─────────────────────────────


class ResultIn(BaseModel):
    day: date
    spend: float = Field(default=0, ge=0, le=10_000_000)
    impressions: int = Field(default=0, ge=0, le=2_000_000_000)
    clicks: int = Field(default=0, ge=0, le=2_000_000_000)
    purchases: int = Field(default=0, ge=0, le=10_000_000)
    revenue: float = Field(default=0, ge=0, le=100_000_000)

    @model_validator(mode="after")
    def coherent(self) -> "ResultIn":
        if self.day > date.today():
            raise ValueError("la fecha no puede ser futura")
        if self.clicks > self.impressions:
            raise ValueError("los clics no pueden superar a las impresiones")
        if self.purchases and not self.clicks:
            raise ValueError("no puede haber compras sin clics")
        return self


def result_row(user_id: UUID, creative_id: str, body: ResultIn, source: str) -> dict:
    return {
        "user_id": str(user_id),
        "creative_id": creative_id,
        "day": body.day.isoformat(),
        "spend": body.spend,
        "impressions": body.impressions,
        "clicks": body.clicks,
        "purchases": body.purchases,
        "revenue": body.revenue,
        "source": source,
    }


@router.put("/creatives/{creative_id}/results")
async def save_result(creative_id: UUID, body: ResultIn, user: User, services: ServicesDep) -> dict:
    """Carga a mano las métricas de un día de un creativo (reemplaza lo de ese día)."""
    creative = await owned_creative(services, creative_id, user)
    await services.ad_results.upsert_many([result_row(user.id, creative["id"], body, "manual")])
    return {"saved": True}


@router.get("/creatives/{creative_id}/results")
async def list_results(creative_id: UUID, user: User, services: ServicesDep) -> list[dict]:
    await owned_creative(services, creative_id, user)
    return await services.ad_results.list_for_creative(creative_id, user.id)


@router.delete("/results/{result_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_result(result_id: UUID, user: User, services: ServicesDep) -> None:
    try:
        await services.ad_results.get(result_id, user.id)
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "resultado no encontrado") from None
    await services.ad_results.delete(result_id, user.id)


async def read_limited(request: Request, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "el archivo es demasiado grande")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/results/import")
async def import_results(request: Request, user: User, services: ServicesDep) -> dict[str, Any]:
    """Importa el CSV de Ads Manager (el body ES el archivo) y lo empareja por nombre de archivo."""
    data = await read_limited(request, results_import.MAX_BYTES)
    try:
        report = results_import.parse_report(data)
    except results_import.ReportError as exc:
        raise unprocessable(str(exc)) from None
    creatives = await services.ad_creatives.list_for_user(user.id)
    match = results_import.match_creatives(report.rows, creatives)

    # Un mismo anuncio puede salir en varias filas del mismo día (conjuntos de anuncios): se suman.
    merged: dict[tuple[str, date], dict] = defaultdict(
        lambda: {"spend": 0.0, "impressions": 0, "clicks": 0, "purchases": 0, "revenue": 0.0}
    )
    for row, creative in match.matched:
        total = merged[(creative["id"], row.day)]
        total["spend"] += row.spend
        total["impressions"] += row.impressions
        total["clicks"] += row.clicks
        total["purchases"] += row.purchases
        total["revenue"] += row.revenue
    rows = [
        {
            "user_id": str(user.id),
            "creative_id": creative_id,
            "day": day.isoformat(),
            **{k: round(v, 2) if isinstance(v, float) else v for k, v in total.items()},
            "source": "csv",
        }
        for (creative_id, day), total in merged.items()
    ]
    imported = await services.ad_results.upsert_many(rows)
    return {
        "rows": len(report.rows),
        "matched": len(match.matched),
        "imported": imported,
        "unmatched": match.unmatched[:50],
        "ambiguous": match.ambiguous[:50],
        "invalid": report.invalid,
        "columns": report.columns,
    }


# ───────────────────────────── aprendizaje ─────────────────────────────


@router.get("/insights")
async def insights(
    user: User, services: ServicesDep, market: Market | None = None, niche: str | None = None
) -> dict:
    """Qué ángulos, plantillas y hooks rinden mejor (por mercado y nicho)."""
    return await load_insights(
        batches=services.ad_batches,
        creatives=services.ad_creatives,
        results=services.ad_results,
        user_id=user.id,
        market=market,
        niche=niche,
    )


# ───────────────────────────── iterar y variantes ─────────────────────────────


class IterateIn(BaseModel):
    count: int = Field(default=2, ge=1, le=MAX_ITERATIONS)


@router.post(
    "/creatives/{creative_id}/iterate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(ai_rate_limit)],
)
async def iterate(creative_id: UUID, body: IterateIn, user: User, services: ServicesDep) -> JobOut:
    """Hooks nuevos para un creativo ya probado (mismo ángulo y avatar). Usa IA."""
    creative = await owned_creative(services, creative_id, user)
    if creative["status"] == "discarded":
        raise HTTPException(status.HTTP_409_CONFLICT, "el creativo está descartado")
    batch = await owned_batch(services, UUID(creative["batch_id"]), user)
    await require_no_active_job(services, batch)
    brief = ad_jobs.batch_brief(batch)
    product_id = UUID(batch["product_id"]) if batch.get("product_id") else None
    available = services.ad_strategy.available(brief, await user_proofs(services, user, product_id))
    if creative["angle"] not in available:
        raise unprocessable(
            "el ángulo de este creativo ya no está disponible (falta una prueba o dato)"
        )
    await services.ad_batches.update(batch["id"], status="planning")
    job = await services.jobs.enqueue(
        user_id=user.id,
        batch_id=UUID(batch["id"]),
        kind="ad_iterate",
        payload={"creative_id": creative["id"], "count": body.count},
    )
    return JobOut(job_id=UUID(job["id"]))


class VariantIn(BaseModel):
    template_id: str | None = Field(default=None, max_length=40, pattern=r"^[a-z_]+$")
    ratio: Ratio | None = None
    stock_keywords: list[str] | None = Field(default=None, max_length=3)

    @model_validator(mode="after")
    def something(self) -> "VariantIn":
        if self.template_id is None and self.ratio is None and self.stock_keywords is None:
            raise ValueError("indica una plantilla, un formato o palabras clave")
        return self


@router.post("/creatives/{creative_id}/variant", status_code=status.HTTP_201_CREATED)
async def variant(creative_id: UUID, body: VariantIn, user: User, services: ServicesDep) -> dict:
    """Mismo texto en otra plantilla, formato o foto. NO usa IA ni toca el original."""
    source = await owned_creative(services, creative_id, user)
    if source["status"] == "discarded":
        raise HTTPException(status.HTTP_409_CONFLICT, "el creativo está descartado")
    batch = await owned_batch(services, UUID(source["batch_id"]), user)
    brief = ad_jobs.batch_brief(batch)
    product_id = UUID(batch["product_id"]) if batch.get("product_id") else None
    proofs = await user_proofs(services, user, product_id)
    deps = services.ads()
    allowed = ad_jobs.available_templates(deps, brief, proofs)

    template_id = body.template_id or source["template_id"]
    ratio = body.ratio or source["ratio"]
    if template_id not in allowed:
        raise unprocessable(f"la plantilla «{template_id}» no está disponible para este lote")
    if ratio not in services.ad_renderer.ratios:
        raise unprocessable(f"formato «{ratio}» desconocido")

    draft = ad_jobs.draft_of(source).model_copy(update={"template_id": template_id})
    if body.stock_keywords is not None:
        keywords = [k.strip() for k in body.stock_keywords if k.strip()]
        draft = draft.model_copy(update={"stock_keywords": keywords})
    angle = services.prompts.angle_library(brief.market).get(source["angle"], {})
    errors = rules.check_draft(
        draft,
        allowed_templates=[template_id],
        brief=brief,
        proofs=proofs,
        needs_proof=angle.get("needs") == "proof",
    )
    if errors:
        raise unprocessable(*errors)

    siblings = [
        c
        for c in await services.ad_creatives.list_for_batch(batch["id"])
        if c["status"] != "discarded"
    ]
    same_group = template_id == source["template_id"] and body.stock_keywords is None
    if same_group and any(
        c["group_id"] == source["group_id"] and c["ratio"] == ratio for c in siblings
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "ese formato ya existe en este borrador")

    taken = {c["filename"] for c in await services.ad_creatives.list_for_batch(batch["id"])}
    filename, version = ad_jobs.next_filename(
        taken,
        product_name=brief.product_name,
        market=batch["market"],
        angle=source["angle"],
        template_id=template_id,
        ratio=ratio,
    )
    verdict = rules.policy_verdict(draft, brief, proofs)
    [row] = await services.ad_creatives.insert_many(
        [
            {
                "batch_id": batch["id"],
                "user_id": str(user.id),
                # Otro formato del mismo texto sigue en su grupo; otra plantilla es otro borrador.
                "group_id": source["group_id"] if same_group else str(uuid4()),
                "angle": source["angle"],
                "avatar": source["avatar"],
                "template_id": template_id,
                "ratio": ratio,
                "copy": draft.model_dump(mode="json"),
                "policy_status": verdict.status,
                "policy_notes": verdict.model_dump(mode="json", exclude={"status"}),
                "pre_score": source.get("pre_score"),
                "score_notes": source.get("score_notes"),
                "version": version,
                "filename": filename,
                "parent_creative_id": source["id"],
            }
        ]
    )
    if batch["status"] in ("ready", "error"):
        await services.ad_batches.update(batch["id"], status="review")
    return row


# ───────────────────────────── duplicar a otro idioma ─────────────────────────────


class DuplicateIn(BaseModel):
    market: Market


@router.post(
    "/batches/{batch_id}/duplicate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(ai_rate_limit)],
)
async def duplicate_batch(
    batch_id: UUID, body: DuplicateIn, user: User, services: ServicesDep
) -> BatchOut:
    """Adapta (no traduce) el brief y los avatares al otro mercado y planifica un lote nuevo con
    los mismos ángulos, formatos y plantilla. El precio y la urgencia se copian tal cual."""
    batch = await owned_batch(services, batch_id, user)
    if body.market == batch["market"]:
        raise unprocessable("elige el otro mercado")
    brief = ad_jobs.batch_brief(batch)
    avatars = ad_jobs.batch_avatars(batch)
    adapted, new_avatars = await services.ad_strategy.adapt_brief(
        user_id=user.id, brief=brief, avatars=avatars, target=body.market
    )
    new_avatars = _distinct(new_avatars)
    names = {old.name: new.name for old, new in zip(avatars, new_avatars, strict=True)}
    picks = [{**p, "avatar": names.get(p["avatar"], new_avatars[0].name)} for p in batch["picks"]]
    created = await services.ad_batches.create(
        {
            "user_id": str(user.id),
            "product_id": None,  # el producto es del otro mercado: el lote queda con brief propio
            "parent_batch_id": batch["id"],
            "niche": adapted.niche,
            "market": body.market,
            "template_id": batch["template_id"],
            "brief": adapted.model_dump(mode="json"),
            "avatars": [a.model_dump() for a in new_avatars],
            "picks": picks,
            "ratios": batch["ratios"],
            "status": "planning",
            "prompt_version": services.prompts.version,
        }
    )
    job = await services.jobs.enqueue(
        user_id=user.id, batch_id=UUID(created["id"]), kind="ad_plan", payload={}
    )
    return BatchOut(batch_id=UUID(created["id"]), job_id=UUID(job["id"]))


def _distinct(avatars: list[Avatar]) -> list[Avatar]:
    """Nombres únicos (el lote los exige distintos): si la IA repitió uno, se numera."""
    seen: dict[str, int] = {}
    out = []
    for a in avatars:
        n = seen.get(a.name, 0) + 1
        seen[a.name] = n
        out.append(a if n == 1 else a.model_copy(update={"name": f"{a.name} ({n})"}))
    return out
