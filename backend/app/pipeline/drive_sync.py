"""Job `upload`: copia a Google Drive los archivos de un producto.

Supabase Storage es el respaldo y la fuente de verdad: este job solo LEE de ahí. Si
Drive falla, el archivo queda `failed` con su contador de intentos y se reintenta (por
el reintento automático del worker o con el botón "reintentar"); nunca se pierde nada.
"""

import asyncio
import logging
from datetime import date
from uuid import UUID

from app.generators.base import MIME, slugify
from app.pipeline.package import PipelineDeps
from app.pipeline.uploads import MAX_ATTEMPTS
from app.storage.google_drive import NotConnected

logger = logging.getLogger("productforge.drive_sync")

UPLOAD_CONCURRENCY = 3
DEFAULT_MIME = "application/octet-stream"


class UploadIncomplete(Exception):
    """Quedaron archivos sin subir; el job se marca `error` y el reintento los retoma."""


def product_folder(product: dict) -> str:
    """Carpeta del producto dentro de la carpeta `ProductForge` de Drive:

        <mercado>/<nicho>/<YYYY-MM-DD>_<slug-producto>

    Las versiones derivadas (remodeladas o duplicadas) llevan además un sufijo corto del id:
    comparten título y día con el original y, sin él, se pisarían los archivos.
    """
    day = (product.get("created_at") or "")[:10] or date.today().isoformat()
    name = slugify(product.get("title") or product["niche"])
    suffix = f"-{product['id'][:6]}" if product.get("parent_product_id") else ""
    return f"{product['market']}/{slugify(product['niche'])}/{day}_{name}{suffix}"


async def run_upload(job: dict, deps: PipelineDeps) -> None:
    target = deps.sync_target
    if target is None:
        raise RuntimeError("no hay destino de sincronización configurado")
    product_id, user_id = UUID(job["product_id"]), UUID(job["user_id"])
    product = await deps.products.get(product_id, user_id)
    folder = product_folder(product)
    prefix = f"{user_id}/{product_id}/"

    # Archivos reemplazados (p. ej. al regenerar una pieza): van a la papelera de Drive.
    for remote_id in job["payload"].get("delete_item_ids", []):
        try:
            await target.delete(user_id, remote_id)
        except NotConnected:
            raise
        except Exception:
            logger.warning("no se pudo borrar un archivo viejo de Drive; se ignora")

    files = await deps.files.list_for_product(product_id)
    for f in files:
        if f["file_type"] == "zip" and f.get("remote_status") != "skipped":
            await deps.files.update(f["id"], remote_status="skipped")  # el ZIP no se sube
    todo = [
        f
        for f in files
        if f["file_type"] != "zip"
        and f.get("remote_status", "pending") in ("pending", "failed")
        and f.get("upload_attempts", 0) < MAX_ATTEMPTS
    ]

    semaphore = asyncio.Semaphore(UPLOAD_CONCURRENCY)
    failed: list[str] = []

    async def one(f: dict) -> None:
        async with semaphore:
            attempts = f.get("upload_attempts", 0) + 1
            try:
                data = await deps.storage.download(f["storage_path"])
                relative = f["storage_path"].removeprefix(prefix)
                remote = await target.upload(
                    user_id, f"{folder}/{relative}", data, MIME.get(f["file_type"], DEFAULT_MIME)
                )
            except NotConnected:
                raise  # sin acceso no tiene sentido seguir con el resto
            except Exception as exc:
                logger.warning("falló la subida de un archivo: %s", type(exc).__name__)
                failed.append(f["id"])
                await deps.files.update(f["id"], remote_status="failed", upload_attempts=attempts)
                return
            await deps.files.update(
                f["id"],
                remote_status="uploaded",
                remote_id=remote.id,
                remote_url=remote.url,
                upload_attempts=attempts,
            )

    await deps.jobs.update(job["id"], progress={"total": len(todo), "failed": 0})
    await asyncio.gather(*(one(f) for f in todo))
    await deps.jobs.update(
        job["id"], progress={"total": len(todo), "failed": len(failed), "folder": folder}
    )
    if failed:
        raise UploadIncomplete(f"{len(failed)} archivo(s) sin subir")
