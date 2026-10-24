"""Jobs de Meta: subir un lote como anuncios EN PAUSA y traer sus métricas.

`ad_meta_publish` es reanudable: lo ya creado (campaña, conjunto, imagen, creativo, anuncio) queda
guardado en `ad_batches.meta` / `ad_creatives.meta`, así que repetirlo tras un fallo completa lo
que falta sin duplicar nada. `ad_meta_sync` copia el rendimiento diario de cada anuncio a
`ad_results` (`source = 'meta'`); las métricas derivadas se siguen calculando de los totales.
"""

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from app.ads.meta.client import MetaClient, MetaError

logger = logging.getLogger("productforge.meta")

PUBLISH_CONCURRENCY = 2
PURCHASE_TYPES = ("omni_purchase", "purchase")
SYNC_DAYS_BACK = 30
# Un lote publicado se vuelve a leer cada tanto desde el worker.
PUBLISHED_STATUSES = {"done", "partial"}


def purchase_value(rows: list[dict] | None) -> float:
    """Valor de la acción de compra (prefiere la omnicanal, que no duplica la de web)."""
    by_type = {r.get("action_type"): r.get("value") for r in rows or []}
    for kind in PURCHASE_TYPES:
        if kind in by_type:
            try:
                return float(by_type[kind])
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def result_row(creative: dict, user_id: str, raw: dict) -> dict:
    """Una fila de `ad_results` a partir de una fila diaria de insights."""
    return {
        "user_id": user_id,
        "creative_id": creative["id"],
        "day": raw["date_start"],
        "spend": round(float(raw.get("spend") or 0), 2),
        "impressions": int(float(raw.get("impressions") or 0)),
        "clicks": int(float(raw.get("inline_link_clicks") or 0)),
        "purchases": int(purchase_value(raw.get("actions"))),
        "revenue": round(purchase_value(raw.get("action_values")), 2),
        "source": "meta",
    }


def ad_text(creative: dict) -> dict[str, str]:
    ad = (creative.get("copy") or {}).get("ad") or {}
    return {
        "message": ad.get("primary_long") or ad.get("primary_short") or "",
        "headline": ad.get("headline", ""),
        "description": ad.get("description", ""),
        "cta": ad.get("cta") or "LEARN_MORE",
    }


def publishable(creative: dict) -> bool:
    """Rojo del semáforo de políticas = no se sube; sin imagen compuesta tampoco."""
    return (
        creative.get("status") == "rendered"
        and bool(creative.get("storage_path"))
        and creative.get("policy_status") != "red"
    )


async def run_ad_meta_publish(job: dict, deps: Any) -> None:
    meta: MetaClient | None = deps.meta
    if meta is None or not meta.configured():
        raise MetaError("Meta no está configurado")
    payload = job["payload"]
    user_id = UUID(job["user_id"])
    batch = await deps.batches.get(job["batch_id"], user_id)
    state: dict = {**(batch.get("meta") or {}), **{k: payload[k] for k in payload}}
    creatives = [c for c in await deps.creatives.list_for_batch(batch["id"]) if publishable(c)]
    skipped = len(await deps.creatives.list_for_batch(batch["id"])) - len(creatives)
    state.update(status="publishing", total=len(creatives), skipped=skipped, uploaded=0, failed=0)
    state.pop("error", None)
    await deps.batches.update(batch["id"], meta=state)

    brief_name = (batch.get("brief") or {}).get("product_name", "")
    today = datetime.now(UTC).date().isoformat()
    try:
        if not state.get("campaign_id"):
            state["campaign_id"] = await meta.create_campaign(
                f"ProductForge · {brief_name} · {today}", state["objective"]
            )
            await deps.batches.update(batch["id"], meta=state)
        if not state.get("adset_id"):
            state["adset_id"] = await meta.create_adset(
                name=f"{brief_name} · {state['objective']}",
                campaign_id=state["campaign_id"],
                objective=state["objective"],
                daily_budget=float(state["daily_budget"]),
                countries=list(state["countries"]),
            )
            await deps.batches.update(batch["id"], meta=state)
    except MetaError as exc:
        await deps.batches.update(batch["id"], meta={**state, "status": "error", "error": str(exc)})
        raise

    semaphore = asyncio.Semaphore(PUBLISH_CONCURRENCY)
    errors: list[str] = []

    async def one(c: dict) -> None:
        ids: dict = dict(c.get("meta") or {})
        if ids.get("ad_id"):
            state["uploaded"] += 1
            return
        async with semaphore:
            try:
                if not ids.get("image_hash"):
                    data = await deps.storage.download(c["storage_path"])
                    ids["image_hash"] = await meta.upload_image(c["filename"], data)
                    await deps.creatives.update(c["id"], meta=ids)
                text = ad_text(c)
                name = c["filename"].removesuffix(".png")  # mismo nombre que usa la importación CSV
                if not ids.get("creative_id"):
                    ids["creative_id"] = await meta.create_creative(
                        name=name,
                        image_hash=ids["image_hash"],
                        link=state["link_url"],
                        **text,
                    )
                    await deps.creatives.update(c["id"], meta=ids)
                ids["ad_id"] = await meta.create_ad(
                    name=name, adset_id=state["adset_id"], creative_id=ids["creative_id"]
                )
                await deps.creatives.update(c["id"], meta=ids)
                state["uploaded"] += 1
            except MetaError as exc:
                logger.warning("falló un anuncio en Meta (código %s)", exc.code)
                errors.append(str(exc))
                state["failed"] += 1

    await asyncio.gather(*(one(c) for c in creatives))
    status = "done" if not state["failed"] else ("partial" if state["uploaded"] else "error")
    final = {**state, "status": status, "published_at": datetime.now(UTC).isoformat()}
    if errors:
        final["error"] = errors[0]
    await deps.batches.update(batch["id"], meta=final)
    if state["failed"]:
        raise MetaError(f"{state['failed']} anuncio(s) sin subir: {errors[0]}")


async def run_ad_meta_sync(job: dict, deps: Any) -> None:
    meta: MetaClient | None = deps.meta
    if meta is None or not meta.configured():
        raise MetaError("Meta no está configurado")
    user_id = UUID(job["user_id"])
    batch = await deps.batches.get(job["batch_id"], user_id)
    creatives = [
        c
        for c in await deps.creatives.list_for_batch(batch["id"])
        if (c.get("meta") or {}).get("ad_id")
    ]
    if not creatives:
        return
    by_ad = {c["meta"]["ad_id"]: c for c in creatives}
    until = date.today()
    since = until - timedelta(days=SYNC_DAYS_BACK)
    rows = await meta.insights(list(by_ad), since.isoformat(), until.isoformat())
    results = [
        result_row(by_ad[r["ad_id"]], job["user_id"], r)
        for r in rows
        if r.get("ad_id") in by_ad and r.get("date_start")
    ]
    await deps.results.upsert_many(results)
    statuses = await meta.ad_statuses(list(by_ad))
    state = {
        **(batch.get("meta") or {}),
        "statuses": statuses,
        "synced_at": datetime.now(UTC).isoformat(),
    }
    await deps.batches.update(batch["id"], meta=state)
