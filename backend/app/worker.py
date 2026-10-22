"""Worker de jobs: toma jobs de la tabla `jobs` (claim_job, FOR UPDATE SKIP LOCKED) y los
ejecuta. Sobrevive reinicios: un job a medias se retoma tras `stale_after`.

    uv run python -m app.worker          # proceso aparte (producción)
    WORKER_INLINE=true                   # o dentro del proceso de la API (desarrollo)
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from uuid import UUID

from app.ads.jobs import AdDeps, run_ad_plan, run_ad_render
from app.config import get_settings
from app.deps import Services, build_services
from app.pipeline.drive_sync import run_upload
from app.pipeline.generate import PipelineDeps, run_generate
from app.pipeline.remodel import run_duplicate, run_regenerate_item, run_remodel
from app.security import configure_logging, ensure_production_ready

logger = logging.getLogger("productforge.worker")

HANDLERS: dict[str, Callable[[dict, PipelineDeps], Awaitable[None]]] = {
    "generate": run_generate,
    "remodel": run_remodel,
    "regenerate_item": run_regenerate_item,
    "duplicate_market": run_duplicate,
    "upload": run_upload,
}
# Los jobs de anuncios cuelgan de un lote y reciben sus propios servicios.
AD_HANDLERS: dict[str, Callable[[dict, AdDeps], Awaitable[None]]] = {
    "ad_plan": run_ad_plan,
    "ad_render": run_ad_render,
}
POLL_SECONDS = 2.0
# Cada tanto se reencolan las subidas a Google Drive que quedaron pendientes o fallidas.
UPLOAD_RETRY_SECONDS = 600.0


async def release_product(services: Services, job: dict) -> None:
    """Un job que cae a medias (p. ej. sin créditos de IA al armar la ficha) no puede dejar el
    producto en «generando» para siempre: pasa a «error» y queda abierto a regenerar piezas."""
    if job["kind"] == "upload" or not job.get("product_id"):
        return
    try:
        product = await services.products.get(UUID(job["product_id"]), UUID(job["user_id"]))
        if product["status"] == "generating":
            await services.products.update(product["id"], status="error")
    except Exception:
        logger.exception("no se pudo liberar el producto del job %s", job["id"])


async def fail_batch(services: Services, job: dict) -> None:
    """Un lote cuyo job cayó no puede quedar en «planificando» o «componiendo» para siempre."""
    try:
        batch = await services.ad_batches.get(job["batch_id"])
        if batch["status"] in ("planning", "rendering"):
            # Con creativos ya planificados vuelve a revisión; sin ellos, a error.
            has_copy = bool(await services.ad_creatives.list_for_batch(batch["id"]))
            await services.ad_batches.update(batch["id"], status="review" if has_copy else "error")
    except Exception:
        logger.exception("no se pudo liberar el lote del job %s", job["id"])


async def run_one(services: Services) -> bool:
    """Ejecuta un job si hay alguno en cola. Devuelve True si procesó uno."""
    job = await services.jobs.claim()
    if job is None:
        return False
    handler = HANDLERS.get(job["kind"])
    ad_handler = AD_HANDLERS.get(job["kind"])
    try:
        if ad_handler is not None:
            await ad_handler(job, services.ads())
        elif handler is None:
            raise ValueError(f"tipo de job desconocido: {job['kind']}")
        else:
            await handler(job, services.pipeline())
    except Exception as exc:
        logger.exception("job %s falló", job["id"])
        # Mensaje genérico: nada de prompts, tokens ni datos del usuario en el error.
        await services.jobs.update(job["id"], status="error", error=type(exc).__name__)
        await release_product(services, job)
        if job.get("batch_id"):
            await fail_batch(services, job)
    else:
        await services.jobs.update(job["id"], status="done")
    return True


async def worker_loop(services: Services, stop: asyncio.Event) -> None:
    logger.info("worker iniciado")
    next_retry = time.monotonic() + UPLOAD_RETRY_SECONDS
    while not stop.is_set():
        try:
            busy = await run_one(services)
        except Exception:
            logger.exception("error tomando jobs; reintento")
            busy = False
        if time.monotonic() >= next_retry:
            next_retry = time.monotonic() + UPLOAD_RETRY_SECONDS
            try:
                await services.upload_queue.enqueue_unsynced()
            except Exception:
                logger.exception("no se pudo reencolar las subidas pendientes")
        if not busy:
            try:
                await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
            except TimeoutError:
                pass


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    configure_logging()
    settings = get_settings()
    ensure_production_ready(settings)
    asyncio.run(worker_loop(build_services(settings), asyncio.Event()))


if __name__ == "__main__":
    main()
