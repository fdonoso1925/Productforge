"""Job `page_generate`: escribe la página de ventas con IA y la deja lista para revisar."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from app.pages.media import resolve_assets
from app.pages.repo import SalesPageRepo
from app.pages.schemas import PageBrief, PageProof, PageReference
from app.pages.strategy import PageService

logger = logging.getLogger("productforge.pages")


@dataclass
class PageDeps:
    service: PageService
    pages: SalesPageRepo
    # Imágenes de la página (opcionales): fotos de stock y mockups del producto.
    images: Any = None
    storage: Any = None
    products: Any = None
    templates_dir: Path | None = None


def proofs_of(page: dict) -> list[PageProof]:
    return [PageProof.model_validate(p) for p in page.get("proofs") or []]


async def run_page_generate(job: dict, deps: PageDeps) -> None:
    user_id = UUID(job["user_id"])
    page = await deps.pages.get(job["page_id"], user_id)
    brief = PageBrief.model_validate(page["brief"])
    reference = PageReference.model_validate(page["reference"]) if page.get("reference") else None
    content, report = await deps.service.write(
        user_id=user_id,
        brief=brief,
        proofs=proofs_of(page),
        reference=reference,
        known=page.get("reference_fingerprint"),
    )
    assets = await resolve_assets(
        page,
        content,
        brief,
        user_id=user_id,
        images=deps.images,
        storage=deps.storage,
        products=deps.products,
        templates_dir=deps.templates_dir,
    )
    values: dict = {
        "content": content.model_dump(),
        "similarity": report.model_dump(),
        "status": "ready",
        "error": None,
    }
    if assets:  # la columna solo se toca cuando hay imágenes
        values["assets"] = assets
    await deps.pages.update(page["id"], **values)
