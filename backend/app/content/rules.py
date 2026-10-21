"""Reglas de negocio del paquete (§7 y D5) que el schema no puede expresar.

Devuelven una lista de errores legibles; el motor se los reenvía a la IA como feedback.
"""

from pydantic import BaseModel

from app.content.schemas import Format, PackageOutline, PackageRequest
from app.content.schemas.common import BONUS_FORMATS
from app.content.schemas.formats import (
    ConceptMapContent,
    EditableTemplateContent,
    GuideContent,
    MindMapContent,
    PlannerContent,
    SheetContent,
)

MIN_ORDER_BUMPS = 3
MIN_BONUSES = 2
PAGE_FORMATS = frozenset({Format.PDF_GUIDE, Format.EPUB})
MAIN_PAGES = (25, 40)
SMALL_MAX_PAGES = 15


def check_package_rules(outline: PackageOutline, request: PackageRequest) -> list[str]:
    errors: list[str] = []
    main = outline.main

    if main.role != "main":
        errors.append("main.role debe ser 'main'.")
    if main.format != request.main_format:
        errors.append(f"main.format debe ser '{request.main_format.value}' (lo eligió el usuario).")
    if main.format in PAGE_FORMATS and not MAIN_PAGES[0] <= main.estimated_pages <= MAIN_PAGES[1]:
        errors.append(f"main.estimated_pages debe estar entre {MAIN_PAGES[0]} y {MAIN_PAGES[1]}.")

    if len(outline.order_bumps) < MIN_ORDER_BUMPS:
        errors.append(f"Se necesitan al menos {MIN_ORDER_BUMPS} order_bumps.")
    if len(outline.bonuses) < MIN_BONUSES:
        errors.append(f"Se necesitan al menos {MIN_BONUSES} bonuses.")

    bump_formats = [item.format for item in outline.order_bumps]
    if len(set(bump_formats)) != len(bump_formats):
        errors.append("Cada order_bump debe usar un formato distinto a los demás order_bumps.")
    if main.format in bump_formats:
        errors.append("Ningún order_bump puede usar el mismo formato que el producto principal.")

    for i, item in enumerate(outline.order_bumps):
        if item.role != "order_bump":
            errors.append(f"order_bumps[{i}].role debe ser 'order_bump'.")
    for i, item in enumerate(outline.bonuses):
        if item.role != "bonus":
            errors.append(f"bonuses[{i}].role debe ser 'bonus'.")
        if item.format not in BONUS_FORMATS:
            allowed = ", ".join(sorted(f.value for f in BONUS_FORMATS))
            errors.append(f"bonuses[{i}].format debe ser un formato liviano: {allowed}.")
        if not item.objection_addressed:
            errors.append(f"bonuses[{i}].objection_addressed es obligatorio.")

    for item in [*outline.order_bumps, *outline.bonuses]:
        if item.estimated_pages > SMALL_MAX_PAGES:
            errors.append(f"'{item.title}': estimated_pages no puede superar {SMALL_MAX_PAGES}.")
        if not item.table_of_contents:
            errors.append(f"'{item.title}': table_of_contents no puede estar vacío.")

    if len({item.format for item in outline.items()}) < 3:
        errors.append("El paquete debe usar al menos 3 formatos distintos.")
    return errors


def check_content_rules(content: BaseModel) -> list[str]:
    """Coherencia interna del contenido que los generadores de archivos necesitan."""
    match content:
        case GuideContent():
            return [] if content.chapters else ["chapters no puede estar vacío."]
        case MindMapContent():
            return [] if 3 <= len(content.branches) <= 9 else ["Usa entre 3 y 9 ramas principales."]
        case ConceptMapContent():
            return _concept_map_errors(content)
        case SheetContent():
            return _sheet_errors(content)
        case PlannerContent():
            days = [d.day for d in content.days]
            if days != list(range(1, content.duration_days + 1)):
                return [f"days debe tener los días 1..{content.duration_days} en orden."]
            return []
        case EditableTemplateContent():
            if content.output == "docx" and not content.documents:
                return ["output=docx requiere al menos un documento en documents."]
            if content.output == "pptx" and not content.slides:
                return ["output=pptx requiere al menos una diapositiva en slides."]
            return []
        case _:
            return []


def _concept_map_errors(content: ConceptMapContent) -> list[str]:
    ids = [c.id for c in content.concepts]
    errors = [] if len(set(ids)) == len(ids) else ["Los id de concepts deben ser únicos."]
    known = set(ids)
    for r in content.relations:
        missing = {r.source, r.target} - known
        if missing:
            errors.append(f"La relación '{r.label}' usa ids inexistentes: {sorted(missing)}.")
    return errors


def _sheet_errors(content: SheetContent) -> list[str]:
    errors: list[str] = []
    for tab in content.tabs:
        headers = [c.header for c in tab.columns]
        if len(set(headers)) != len(headers):
            errors.append(f"Pestaña '{tab.name}': los encabezados deben ser únicos.")
        for col in tab.columns:
            if col.type == "choice" and not col.choices:
                errors.append(f"Pestaña '{tab.name}', columna '{col.header}': faltan choices.")
            if col.computed:
                unknown = [op for op in col.computed.operands if op not in headers]
                if unknown or col.header in col.computed.operands:
                    errors.append(
                        f"Pestaña '{tab.name}', columna '{col.header}': operands deben ser "
                        f"otras columnas existentes (desconocidas: {unknown})."
                    )
                if len(col.computed.operands) < 2 and col.computed.op != "sum":
                    errors.append(
                        f"Pestaña '{tab.name}', columna '{col.header}': '{col.computed.op}' "
                        "necesita al menos 2 operands."
                    )
        for i, row in enumerate(tab.sample_rows):
            if len(row) != len(headers):
                errors.append(
                    f"Pestaña '{tab.name}': sample_rows[{i}] debe tener {len(headers)} valores."
                )
    return errors


def check_adaptation(source: PackageOutline, adapted: PackageOutline) -> list[str]:
    """La adaptación conserva la estructura: mismos formatos en el mismo orden."""
    errors: list[str] = []
    for name, src, new in (
        ("main", [source.main], [adapted.main]),
        ("order_bumps", source.order_bumps, adapted.order_bumps),
        ("bonuses", source.bonuses, adapted.bonuses),
    ):
        if len(src) != len(new):
            errors.append(f"{name} debe tener exactamente {len(src)} pieza(s), como el original.")
            continue
        for i, (a, b) in enumerate(zip(src, new, strict=True)):
            if a.format != b.format:
                errors.append(
                    f"{name}[{i}].format debe seguir siendo '{a.format.value}' (como el original)."
                )
    return errors
