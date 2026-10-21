"""Generación de un paquete completo a partir del outline aprobado.

Por cada pieza: contenido estructurado (IA) → archivos (generadores) → Supabase Storage.
Luego la ficha comercial y un ZIP con todo. Las piezas corren en paralelo (máx.
`ITEM_CONCURRENCY`); si una falla, las demás siguen y la pieza queda en `error` para
regenerarla después. La mecánica vive en `PackageBuilder` (`package.py`).
"""

from uuid import UUID

from app.pipeline.package import (
    ITEM_CONCURRENCY,
    PackageBuilder,
    PipelineDeps,
    Progress,
    build_zip,
    content_hash,
    package_request,
)

__all__ = [
    "ITEM_CONCURRENCY",
    "PipelineDeps",
    "Progress",
    "build_zip",
    "content_hash",
    "package_request",
    "run_generate",
]


async def run_generate(job: dict, deps: PipelineDeps) -> None:
    product_id, user_id = UUID(job["product_id"]), UUID(job["user_id"])
    product = await deps.products.get(product_id, user_id)
    builder = PackageBuilder(deps, job, product)

    await deps.products.update(product_id, status="generating")
    await builder.drop_files(await deps.files.list_for_product(product_id))
    rows = await deps.items.replace_from_outline(product_id, user_id, builder.outline)
    await builder.start(rows)

    results = await builder.run_items([(row, "generate") for row in rows])
    if not any(results):
        await deps.products.update(product_id, status="error")
        raise RuntimeError("no se pudo generar ninguna pieza")

    await builder.progress.set(stage="commercial")
    await builder.commercial("generate")
    await builder.progress.set(stage="zip")
    await builder.rebuild_zip()
    await builder.finish()
