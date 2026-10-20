"""Generación de un paquete completo a partir del outline aprobado.

Por cada pieza: contenido estructurado (IA) → archivos (generadores) → Supabase Storage.
Luego la ficha comercial y un ZIP con todo. Las piezas corren en paralelo (máx.
`ITEM_CONCURRENCY`); si una falla, las demás siguen y la pieza queda en `error` para
regenerarla después.
"""

import asyncio
import hashlib
import io
import json
import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from app.content.engines import ContentService
from app.content.schemas import Format, ItemOutline, PackageOutline, PackageRequest
from app.db.supabase import FileRepo, ItemRepo, JobRepo, ProductRepo
from app.generators import FileArtifact, RenderContext, generate_files
from app.generators.base import slugify
from app.generators.commercial import commercial_files
from app.storage.base import StorageProvider
from app.templates_engine.model import load_template

logger = logging.getLogger("productforge.pipeline")

ITEM_CONCURRENCY = 3
FOLDERS = {"main": "principal", "order_bump": "order-bumps", "bonus": "bonus"}


@dataclass
class PipelineDeps:
    content: ContentService
    products: ProductRepo
    items: ItemRepo
    files: FileRepo
    jobs: JobRepo
    storage: StorageProvider
    templates_dir: Path


@dataclass
class Progress:
    """Estado que el frontend lee por polling (`jobs.progress`)."""

    job_id: str
    jobs: JobRepo
    items: dict[str, str] = field(default_factory=dict)
    stage: str = "items"
    logs: list[str] = field(default_factory=list)

    @property
    def snapshot(self) -> dict[str, Any]:
        done = sum(s in ("ready", "error") for s in self.items.values())
        return {"stage": self.stage, "items": self.items, "done": done, "total": len(self.items)}

    async def set(self, item_id: str | None = None, status: str | None = None, **kw) -> None:
        if item_id and status:
            self.items[item_id] = status
        self.stage = kw.get("stage", self.stage)
        await self.jobs.update(self.job_id, progress=self.snapshot, logs=self.logs[-50:])


def package_request(product: dict) -> PackageRequest:
    return PackageRequest(
        niche=product["niche"],
        problem=product["problem"],
        market=product["market"],
        main_format=product["main_format"],
        tone=product.get("tone"),
        audience_override=product.get("audience_override"),
    )


def content_hash(content: Any) -> str:
    payload = json.dumps(content.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def build_zip(entries: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            z.writestr(name, data)
    return buffer.getvalue()


async def run_generate(job: dict, deps: PipelineDeps) -> None:
    product_id, user_id = UUID(job["product_id"]), UUID(job["user_id"])
    product = await deps.products.get(product_id, user_id)
    request = package_request(product)
    outline = PackageOutline.model_validate(product["outline"])
    template = load_template(deps.templates_dir, product["template_id"])
    base = f"{user_id}/{product_id}"
    progress = Progress(job_id=job["id"], jobs=deps.jobs)

    await deps.products.update(product_id, status="generating")
    await deps.files.delete_for_product(product_id)
    rows = await deps.items.replace_from_outline(product_id, user_id, outline)
    pairs = list(zip(rows, outline.items(), strict=True))
    for row, _ in pairs:
        progress.items[row["id"]] = "pending"
    await progress.set()

    zip_entries: list[tuple[str, bytes]] = []
    semaphore = asyncio.Semaphore(ITEM_CONCURRENCY)

    async def store(item_id: str | None, folder: str, artifact: FileArtifact) -> None:
        relative = f"{folder}/{artifact.filename}" if folder else artifact.filename
        path = await deps.storage.upload(f"{base}/{relative}", artifact.content, artifact.mime)
        await deps.files.add(
            product_id=product_id,
            user_id=user_id,
            item_id=item_id,
            file_type=artifact.file_type,
            storage_path=path,
            size=len(artifact.content),
        )
        zip_entries.append((relative, artifact.content))

    async def one(row: dict, item: ItemOutline) -> bool:
        async with semaphore:
            item_id = row["id"]
            try:
                await deps.items.update(item_id, status="generating")
                await progress.set(item_id, "generating")
                content = await deps.content.generate_item(
                    user_id=user_id,
                    product_id=product_id,
                    request=request,
                    outline=outline,
                    item=item,
                )
                await deps.items.update(
                    item_id,
                    content=content.model_dump(mode="json"),
                    content_hash=content_hash(content),
                )
                ctx = RenderContext(
                    market=request.market,
                    role=item.role,
                    slug=slugify(item.title),
                    product_name=outline.product_name,
                    promise=item.promise,
                )
                files = await asyncio.to_thread(
                    generate_files, Format(item.format), content, template, ctx
                )
                for artifact in files:
                    await store(item_id, FOLDERS[item.role], artifact)
                await deps.items.update(item_id, status="ready")
                await progress.set(item_id, "ready")
                return True
            except Exception as exc:  # una pieza fallida no tumba el paquete
                logger.exception("falló la pieza %s", item_id)
                progress.logs.append(f"{item.title}: {type(exc).__name__}")
                await deps.items.update(item_id, status="error")
                await progress.set(item_id, "error")
                return False

    results = await asyncio.gather(*(one(row, item) for row, item in pairs))
    if not any(results):
        await deps.products.update(product_id, status="error")
        raise RuntimeError("no se pudo generar ninguna pieza")

    await progress.set(stage="commercial")
    sheet = await deps.content.commercial_sheet(
        user_id=user_id, product_id=product_id, request=request, outline=outline
    )
    await deps.products.update(product_id, commercial=sheet.model_dump(mode="json"))
    ctx = RenderContext(
        market=request.market,
        role="main",
        slug="ficha-comercial",
        product_name=outline.product_name,
    )
    for artifact in await asyncio.to_thread(commercial_files, sheet, template, ctx):
        await store(None, "", artifact)

    await progress.set(stage="zip")
    archive = build_zip(sorted(zip_entries))
    zip_name = f"{slugify(outline.product_name)}.zip"
    path = await deps.storage.upload(f"{base}/{zip_name}", archive, "application/zip")
    await deps.files.add(
        product_id=product_id,
        user_id=user_id,
        item_id=None,
        file_type="zip",
        storage_path=path,
        size=len(archive),
    )

    status = "ready" if all(results) else "error"
    await deps.products.update(product_id, status=status)
    await progress.set(stage="done")
