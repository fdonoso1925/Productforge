"""Cola de subidas a destinos externos (Google Drive). Solo decide a quién encolarle un job."""

import logging
from collections.abc import Iterable
from uuid import UUID

from app.db.supabase import FileRepo, JobRepo
from app.storage.base import SyncTarget

logger = logging.getLogger("productforge.uploads")

MAX_ATTEMPTS = 5  # intentos por archivo antes de dejarlo en `failed` definitivamente


class UploadQueue:
    def __init__(self, target: SyncTarget, jobs: JobRepo, files: FileRepo) -> None:
        self.target = target
        self.jobs = jobs
        self.files = files

    async def enqueue(
        self, user_id: UUID, product_id: UUID, delete_item_ids: Iterable[str] = ()
    ) -> bool:
        """Encola la copia de un producto. No hace nada si el usuario no conectó Google Drive."""
        if not self.target.configured() or not await self.target.is_connected(user_id):
            return False
        delete = list(delete_item_ids)
        # Un job de subida pendiente ya cubrirá estos archivos; los borrados sí van aparte.
        if not delete and await self.jobs.active_for_product(product_id, kind="upload"):
            return False
        await self.jobs.enqueue(
            product_id=product_id,
            user_id=user_id,
            kind="upload",
            payload={"delete_item_ids": delete},
        )
        return True

    async def enqueue_unsynced(self, user_id: UUID | None = None) -> int:
        """Encola los productos con archivos pendientes o fallidos (de un usuario o de todos).

        Lo usan "sincronizar todo", el callback de conexión y el reintento automático.
        """
        pairs = {
            (r["user_id"], r["product_id"])
            for r in await self.files.unsynced(MAX_ATTEMPTS, user_id)
        }
        queued = 0
        for uid, pid in sorted(pairs):
            if await self.enqueue(UUID(uid), UUID(pid)):
                queued += 1
        return queued
