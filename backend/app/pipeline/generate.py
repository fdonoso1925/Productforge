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


def is_complete(row: dict, files: list[dict]) -> bool:
    """Pieza lista de verdad: marcada «ready» y con sus archivos en Storage."""
    return row.get("status") == "ready" and any(
        f.get("product_item_id") == row["id"] for f in files
    )


async def run_generate(job: dict, deps: PipelineDeps) -> None:
    """Genera el paquete. Si ya hay piezas (una generación anterior que se cayó), **retoma en la
    etapa pendiente**: conserva las piezas completas, rehace solo las que faltan (con el contenido
    ya guardado, sin volver a pagar IA) y completa la ficha comercial y el ZIP si faltaban."""
    product_id, user_id = UUID(job["product_id"]), UUID(job["user_id"])
    product = await deps.products.get(product_id, user_id)
    builder = PackageBuilder(deps, job, product)

    await deps.products.update(product_id, status="generating")
    existing = await deps.items.list_for_product(product_id)
    files = await deps.files.list_for_product(product_id)
    resuming = len(existing) == len(builder.outline.items()) and bool(existing)

    if resuming:
        done = [r for r in existing if is_complete(r, files)]
        todo = [r for r in existing if r not in done]
        await builder.start(existing)
        for row in done:
            await builder.progress.set(row["id"], "ready")
        # Los archivos a medias de las pendientes se descartan; los de las completas se quedan.
        pending_ids = {r["id"] for r in todo}
        await builder.drop_files([f for f in files if f.get("product_item_id") in pending_ids])
        pairs = [(r, "rerender" if r.get("content") else "generate") for r in todo]
        results = await builder.run_items(pairs) if pairs else []
        if pairs and not done and not any(results):
            await deps.products.update(product_id, status="error")
            raise RuntimeError("no se pudo generar ninguna pieza")
        has_sheet = any(f.get("product_item_id") is None and f["file_type"] != "zip" for f in files)
        if not has_sheet:
            await builder.progress.set(stage="commercial")
            await builder.commercial("copy" if product.get("commercial") else "generate")
    else:
        await builder.drop_files(files)
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
