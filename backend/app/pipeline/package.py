"""Piezas compartidas por todos los jobs que producen archivos de un paquete.

`PackageBuilder` trabaja sobre UN producto: produce el contenido de una pieza (con IA o
reutilizando el guardado), lo maqueta con la plantilla del producto, sube los archivos y
reconstruye el ZIP. Lo usan generar, remodelar, regenerar una pieza y duplicar.
"""

import asyncio
import hashlib
import io
import json
import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import ValidationError

from app.ads import rules as ad_rules
from app.ads.images.base import ImageRequest
from app.content.engines import ContentService
from app.content.schemas import (
    FORMAT_SCHEMAS,
    CommercialSheet,
    Format,
    ItemOutline,
    PackageOutline,
    PackageRequest,
)
from app.db.supabase import FileRepo, ItemRepo, JobRepo, ProductRepo
from app.generators import FileArtifact, RenderContext, generate_files
from app.generators.base import slugify
from app.generators.commercial import commercial_files
from app.generators.cover import art_for_piece, image_path, stored_spec, veil_for
from app.generators.cover_image import data_uri
from app.pipeline.uploads import UploadQueue
from app.storage.base import StorageProvider, SyncTarget
from app.templates_engine.model import load_template

logger = logging.getLogger("productforge.pipeline")

ITEM_CONCURRENCY = 3
FOLDERS = {"main": "principal", "order_bump": "order-bumps", "bonus": "bonus"}

# generate: contenido nuevo con IA · rerender: reutiliza el contenido guardado (sin IA)
Mode = Literal["generate", "rerender"]


@dataclass
class PipelineDeps:
    content: ContentService
    products: ProductRepo
    items: ItemRepo
    files: FileRepo
    jobs: JobRepo
    storage: StorageProvider
    templates_dir: Path
    # Google Drive: destino al que se copian los archivos y cola que encola esas copias.
    sync_target: SyncTarget | None = None
    uploads: UploadQueue | None = None
    # Fotos de stock para abrir capítulos (ImageRouter de los anuncios). None = sin fotos.
    images: Any = None


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
        reference=product.get("reference") or None,
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


class PackageBuilder:
    def __init__(self, deps: PipelineDeps, job: dict, product: dict) -> None:
        self.deps = deps
        self.job = job
        self.product = product
        self.user_id = UUID(job["user_id"])
        self.product_id = UUID(product["id"])
        self.request = package_request(product)
        self.outline = PackageOutline.model_validate(product["outline"])
        self.template = load_template(deps.templates_dir, product["template_id"])
        self.progress = Progress(job_id=job["id"], jobs=deps.jobs)
        self.base = f"{self.user_id}/{self.product_id}"
        self.cover = stored_spec(product)
        self._cover_image: tuple[str, float] | None = None
        self._cover_lock = asyncio.Lock()
        # Copias en Google Drive que quedaron huérfanos al reemplazar los de Supabase.
        self.orphaned_remote_ids: list[str] = []

    # ── piezas ──

    def slot(self, role: str, order: int) -> ItemOutline:
        """La pieza del outline que corresponde a una fila de `product_items`."""
        group = {
            "main": [self.outline.main],
            "order_bump": self.outline.order_bumps,
            "bonus": self.outline.bonuses,
        }[role]
        return group[order]

    async def drop_files(self, rows: list[dict]) -> None:
        """Borra filas de `files` y recuerda sus copias externas para limpiarlas después."""
        self.orphaned_remote_ids += [r["remote_id"] for r in rows if r.get("remote_id")]
        await self.deps.files.delete_ids([r["id"] for r in rows])

    async def start(self, rows: list[dict]) -> None:
        for row in rows:
            self.progress.items[row["id"]] = "pending"
        await self.progress.set()

    async def cover_image(self) -> tuple[str, float] | None:
        """Imagen propia de la portada (data URI) y su velo; se baja una sola vez por job."""
        if self.cover.image_id is None:
            return None
        async with self._cover_lock:
            if self._cover_image is None:
                try:
                    raw = await self.deps.storage.download(
                        image_path(self.user_id, self.cover.image_id)
                    )
                    self._cover_image = (
                        data_uri(raw),
                        await asyncio.to_thread(veil_for, raw, self.template),
                    )
                except Exception:
                    # Sin la imagen la pieza igual se genera, con el arte de la portada.
                    logger.exception("no se pudo cargar la imagen de portada")
                    return None
        return self._cover_image

    async def cover_fields(self, row: dict) -> dict[str, Any]:
        """Campos de `RenderContext` con la portada de esta pieza (imagen propia o arte)."""
        image = await self.cover_image()
        if image:
            return {"cover_image": image[0], "cover_veil": image[1]}
        _, art = art_for_piece(self.cover, self.product, self.template, row["role"], row["order"])
        return {"cover_art": art}

    async def chapter_photos(self, content: Any) -> dict[str, str]:
        """Fotos de stock de los capítulos que las piden: {"ch3": data URI}. Una foto que no se
        consigue (sin proveedor, sin cuota, sin resultados) simplemente no sale: el capítulo se
        maqueta igual, con sus infografías."""
        router = getattr(self.deps, "images", None)
        chapters = getattr(content, "chapters", None)
        if router is None or not chapters or not router.active():
            return {}
        sensitive = ad_rules.is_sensitive(self.request.niche)
        found: dict[str, str] = {}
        semaphore = asyncio.Semaphore(3)

        async def one(index: int, title: str, spec: Any) -> None:
            async with semaphore:
                try:
                    image = await router.get(
                        user_id=self.user_id,
                        request=ImageRequest(
                            prompt=spec.scene,
                            keywords=tuple(k for k in spec.keywords if k.strip())[:3],
                            aspect="16:9",
                            sensitive=sensitive,
                            curate=True,
                            context=f"{spec.caption} (chapter: {title})",
                        ),
                    )
                except Exception:
                    logger.warning("no se pudo traer la foto del capítulo %s", index)
                    return
                if image is not None:
                    found[f"ch{index}"] = data_uri(image.jpeg)

        await asyncio.gather(
            *(
                one(i, ch.title, ch.photo)
                for i, ch in enumerate(chapters, start=1)
                if getattr(ch, "photo", None)
            )
        )
        return found

    async def produce(self, row: dict, mode: Mode) -> list[FileArtifact]:
        """Contenido de la pieza (IA o guardado) → archivos. No sube nada."""
        item = self.slot(row["role"], row["order"])
        content = None
        if mode == "rerender" and row.get("content"):
            try:
                content = FORMAT_SCHEMAS[Format(item.format)].model_validate(row["content"])
            except ValidationError:
                content = None  # el contenido guardado no sirve para este formato
        if content is None:
            content = await self.deps.content.generate_item(
                user_id=self.user_id,
                product_id=self.product_id,
                request=self.request,
                outline=self.outline,
                item=item,
            )
            await self.deps.items.update(
                row["id"],
                content=content.model_dump(mode="json"),
                content_hash=content_hash(content),
            )
        ctx = RenderContext(
            market=self.request.market,
            role=item.role,
            slug=slugify(item.title),
            product_name=self.outline.product_name,
            promise=item.promise,
            photos=await self.chapter_photos(content),
            **await self.cover_fields(row),
        )
        return await asyncio.to_thread(
            generate_files, Format(item.format), content, self.template, ctx
        )

    async def store(self, item_id: str | None, folder: str, artifact: FileArtifact) -> None:
        relative = f"{folder}/{artifact.filename}" if folder else artifact.filename
        path = await self.deps.storage.upload(
            f"{self.base}/{relative}", artifact.content, artifact.mime
        )
        await self.deps.files.add(
            product_id=self.product_id,
            user_id=self.user_id,
            item_id=item_id,
            file_type=artifact.file_type,
            storage_path=path,
            size=len(artifact.content),
        )

    async def store_item_files(self, row: dict, files: list[FileArtifact]) -> None:
        for artifact in files:
            await self.store(row["id"], FOLDERS[row["role"]], artifact)

    async def run_items(self, pairs: list[tuple[dict, Mode]]) -> list[bool]:
        """Procesa las piezas en paralelo; una que falla queda en `error` y no frena el resto."""
        semaphore = asyncio.Semaphore(ITEM_CONCURRENCY)

        async def one(row: dict, mode: Mode) -> bool:
            async with semaphore:
                item_id = row["id"]
                try:
                    await self.deps.items.update(item_id, status="generating")
                    await self.progress.set(item_id, "generating")
                    files = await self.produce(row, mode)
                    await self.store_item_files(row, files)
                    await self.deps.items.update(item_id, status="ready")
                    await self.progress.set(item_id, "ready")
                    return True
                except Exception as exc:  # una pieza fallida no tumba el paquete
                    logger.exception("falló la pieza %s", item_id)
                    self.progress.logs.append(f"{row.get('title', item_id)}: {type(exc).__name__}")
                    await self.deps.items.update(item_id, status="error")
                    await self.progress.set(item_id, "error")
                    return False

        return list(await asyncio.gather(*(one(row, mode) for row, mode in pairs)))

    # ── ficha comercial, ZIP y cierre ──

    async def commercial(self, mode: Literal["generate", "copy"]) -> None:
        """`copy` re-maqueta la ficha ya guardada con la plantilla actual (sin IA)."""
        stored = self.product.get("commercial")
        if mode == "copy" and stored:
            sheet = CommercialSheet.model_validate(stored)
        else:
            sheet = await self.deps.content.commercial_sheet(
                user_id=self.user_id,
                product_id=self.product_id,
                request=self.request,
                outline=self.outline,
            )
            await self.deps.products.update(
                self.product_id, commercial=sheet.model_dump(mode="json")
            )
        ctx = RenderContext(
            market=self.request.market,
            role="main",
            slug="ficha-comercial",
            product_name=self.outline.product_name,
        )
        for artifact in await asyncio.to_thread(commercial_files, sheet, self.template, ctx):
            await self.store(None, "", artifact)

    async def rebuild_zip(self) -> None:
        """ZIP con todos los archivos vigentes del producto (descargados de Storage)."""
        rows = await self.deps.files.list_for_product(self.product_id)
        old_zips = [r for r in rows if r["file_type"] == "zip"]
        current = sorted(
            (r for r in rows if r["file_type"] != "zip"), key=lambda r: r["storage_path"]
        )
        blobs = await asyncio.gather(
            *(self.deps.storage.download(r["storage_path"]) for r in current)
        )
        prefix = f"{self.base}/"
        archive = build_zip(
            [
                (r["storage_path"].removeprefix(prefix), data)
                for r, data in zip(current, blobs, strict=True)
            ]
        )
        name = f"{slugify(self.outline.product_name)}.zip"
        path = await self.deps.storage.upload(f"{self.base}/{name}", archive, "application/zip")
        await self.deps.files.delete_ids([r["id"] for r in old_zips])
        await self.deps.storage.delete(
            [r["storage_path"] for r in old_zips if r["storage_path"] != path]
        )
        await self.deps.files.add(
            product_id=self.product_id,
            user_id=self.user_id,
            item_id=None,
            file_type="zip",
            storage_path=path,
            size=len(archive),
            remote_status="skipped",  # el ZIP es para descargar, no se copia a Drive
        )

    async def finish(self) -> None:
        items = await self.deps.items.list_for_product(self.product_id)
        ok = bool(items) and all(i["status"] == "ready" for i in items)
        await self.deps.products.update(self.product_id, status="ready" if ok else "error")
        await self.progress.set(stage="done")
        await self._queue_uploads()

    async def _queue_uploads(self) -> None:
        """Encola la copia al destino externo. Un fallo aquí nunca debe tumbar la generación."""
        if self.deps.uploads is None:
            return
        try:
            await self.deps.uploads.enqueue(self.user_id, self.product_id, self.orphaned_remote_ids)
        except Exception:
            logger.exception("no se pudo encolar la subida a Google Drive")
