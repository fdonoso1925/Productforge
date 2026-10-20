"""Worker de jobs: toma jobs de la tabla `jobs` (claim_job, FOR UPDATE SKIP LOCKED) y los
ejecuta. Sobrevive reinicios: un job a medias se retoma tras `stale_after`.

    uv run python -m app.worker          # proceso aparte (producción)
    WORKER_INLINE=true                   # o dentro del proceso de la API (desarrollo)
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.config import get_settings
from app.deps import Services, build_services
from app.pipeline.generate import PipelineDeps, run_generate

logger = logging.getLogger("productforge.worker")

HANDLERS: dict[str, Callable[[dict, PipelineDeps], Awaitable[None]]] = {
    "generate": run_generate,
}
POLL_SECONDS = 2.0


async def run_one(services: Services) -> bool:
    """Ejecuta un job si hay alguno en cola. Devuelve True si procesó uno."""
    job = await services.jobs.claim()
    if job is None:
        return False
    handler = HANDLERS.get(job["kind"])
    try:
        if handler is None:
            raise ValueError(f"tipo de job desconocido: {job['kind']}")
        await handler(job, services.pipeline())
    except Exception as exc:
        logger.exception("job %s falló", job["id"])
        # Mensaje genérico: nada de prompts, tokens ni datos del usuario en el error.
        await services.jobs.update(job["id"], status="error", error=type(exc).__name__)
    else:
        await services.jobs.update(job["id"], status="done")
    return True


async def worker_loop(services: Services, stop: asyncio.Event) -> None:
    logger.info("worker iniciado")
    while not stop.is_set():
        try:
            busy = await run_one(services)
        except Exception:
            logger.exception("error tomando jobs; reintento")
            busy = False
        if not busy:
            try:
                await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
            except TimeoutError:
                pass


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(worker_loop(build_services(get_settings()), asyncio.Event()))


if __name__ == "__main__":
    main()
