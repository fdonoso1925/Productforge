"""Jobs de la Fase 5: remodelar un producto, regenerar una pieza y duplicar a otro mercado.

Regla de oro: el contenido se guarda estructurado, así que cambiar de plantilla (o entre
formatos que comparten schema, como guía PDF ↔ EPUB) NO vuelve a llamar a la IA. Solo se
usa IA para lo que cambia de verdad: tono, público, un formato con otro schema, la pieza
regenerada o el idioma.
"""

import logging
from uuid import UUID

from app.content.rules import MAIN_PAGES, PAGE_FORMATS, SMALL_MAX_PAGES
from app.content.schemas import FORMAT_SCHEMAS, Format, PackageOutline
from app.pipeline.generate import run_generate
from app.pipeline.package import Mode, PackageBuilder, PipelineDeps, Progress, package_request

logger = logging.getLogger("productforge.remodel")


def same_schema(a: Format, b: Format) -> bool:
    return FORMAT_SCHEMAS[a] is FORMAT_SCHEMAS[b]


def plan_remodel(
    rows: list[dict], new_formats: dict[str, Format], content_changed: bool
) -> dict[str, Mode]:
    """Modo de cada pieza: reutilizar el contenido (`rerender`) o pedirlo a la IA (`generate`).

    `content_changed`: tono o público distintos → todo el contenido cambia.
    """
    modes: dict[str, Mode] = {}
    for row in rows:
        new = new_formats.get(row["id"])
        if content_changed or not row.get("content"):
            modes[row["id"]] = "generate"
        elif new is not None and not same_schema(Format(row["format"]), new):
            modes[row["id"]] = "generate"
        else:
            modes[row["id"]] = "rerender"
    return modes


def pages_for(role: str, fmt: Format, pages: int) -> int:
    """Ajusta las páginas estimadas al nuevo formato para respetar las reglas del paquete."""
    if role == "main":
        if fmt in PAGE_FORMATS:
            return min(max(pages, MAIN_PAGES[0]), MAIN_PAGES[1])
        return pages
    return min(pages, SMALL_MAX_PAGES)


def apply_formats(
    outline: PackageOutline, rows: list[dict], formats: dict[str, Format]
) -> PackageOutline:
    """Copia del outline con los formatos cambiados (las filas se asocian por rol y posición)."""
    result = outline.model_copy(deep=True)
    groups = {
        "main": [result.main],
        "order_bump": result.order_bumps,
        "bonus": result.bonuses,
    }
    for row in rows:
        new = formats.get(row["id"])
        if new is None or new.value == row["format"]:
            continue
        item = groups[row["role"]][row["order"]]
        item.format = new
        item.estimated_pages = pages_for(row["role"], new, item.estimated_pages)
    return result


async def run_remodel(job: dict, deps: PipelineDeps) -> None:
    """Maqueta un producto derivado: las piezas ya existen (creadas por la API) y el payload
    dice cuáles reutilizan su contenido y cuáles lo regeneran."""
    product_id, user_id = UUID(job["product_id"]), UUID(job["user_id"])
    product = await deps.products.get(product_id, user_id)
    builder = PackageBuilder(deps, job, product)
    modes: dict[str, Mode] = job["payload"].get("modes", {})

    await builder.drop_files(await deps.files.list_for_product(product_id))
    rows = await deps.items.list_for_product(product_id)
    await builder.start(rows)
    results = await builder.run_items([(row, modes.get(row["id"], "rerender")) for row in rows])
    if not any(results):
        await deps.products.update(product_id, status="error")
        raise RuntimeError("no se pudo generar ninguna pieza")

    await builder.progress.set(stage="commercial")
    await builder.commercial(job["payload"].get("commercial", "copy"))
    await builder.progress.set(stage="zip")
    await builder.rebuild_zip()
    await builder.finish()


async def run_regenerate_item(job: dict, deps: PipelineDeps) -> None:
    """Vuelve a generar UNA pieza con IA. Los archivos anteriores se reemplazan solo cuando
    los nuevos están listos: si algo falla, la pieza conserva lo que tenía."""
    product_id, user_id = UUID(job["product_id"]), UUID(job["user_id"])
    item_id = job["payload"]["item_id"]
    product = await deps.products.get(product_id, user_id)
    builder = PackageBuilder(deps, job, product)
    rows = await deps.items.list_for_product(product_id)
    row = next(r for r in rows if r["id"] == item_id)
    previous_status = row["status"]

    await builder.start([row])
    await deps.items.update(item_id, status="generating")
    await builder.progress.set(item_id, "generating")
    try:
        files = await builder.produce(row, "generate")
        old = [
            f
            for f in await deps.files.list_for_product(product_id)
            if f.get("product_item_id") == item_id
        ]
        await builder.drop_files(old)
        await deps.storage.delete([f["storage_path"] for f in old])
        await builder.store_item_files(row, files)
    except Exception:
        await deps.items.update(item_id, status=previous_status)
        raise
    await deps.items.update(item_id, status="ready")
    await builder.progress.set(item_id, "ready", stage="zip")
    if not product.get("commercial"):
        # La generación original pudo caer antes de la ficha (p. ej. sin créditos de IA): así
        # un paquete a medias se completa regenerando su pieza fallida, sin rehacer todo.
        await builder.commercial("generate")
    await builder.rebuild_zip()
    await builder.finish()


async def run_duplicate(job: dict, deps: PipelineDeps) -> None:
    """Adapta el paquete al otro mercado (nicho, problema y outline) y lo genera nativo."""
    product_id, user_id = UUID(job["product_id"]), UUID(job["user_id"])
    child = await deps.products.get(product_id, user_id)
    parent = await deps.products.get(UUID(child["parent_product_id"]), user_id)

    await Progress(job_id=job["id"], jobs=deps.jobs, stage="adapting").set()
    adapted = await deps.content.adapt_to_market(
        user_id=user_id,
        product_id=product_id,
        source=package_request(parent),
        outline=PackageOutline.model_validate(parent["outline"]),
        target=child["market"],
    )
    await deps.products.update(
        product_id,
        niche=adapted.niche,
        problem=adapted.problem.model_dump(),
        outline=adapted.outline.model_dump(mode="json"),
        title=adapted.outline.product_name,
        commercial=None,
    )
    await run_generate(job, deps)
