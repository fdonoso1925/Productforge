"""Reglas de negocio del paquete (§7 y D5) que el schema no puede expresar.

Devuelven una lista de errores legibles; el motor se los reenvía a la IA como feedback.
"""

from pydantic import BaseModel

from app.content.schemas import Format, PackageOutline, PackageRequest
from app.content.schemas.common import BONUS_FORMATS
from app.content.schemas.formats import (
    BlueprintContent,
    ChecklistContent,
    ConceptMapContent,
    EditableTemplateContent,
    GuideContent,
    MindMapContent,
    PlannerContent,
    PrintableContent,
    SheetContent,
    Visual,
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
            if not content.chapters:
                return ["chapters no puede estar vacío."]
            return _guide_visual_errors(content)
        case BlueprintContent():
            return _blueprint_visual_errors(content)
        case PrintableContent():
            return _printable_errors(content)
        case ChecklistContent():
            return _visual_errors(content.visual, "visual", required=True)
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
            return _visual_errors(content.roadmap, "roadmap", required=True)
        case EditableTemplateContent():
            if content.output == "docx" and not content.documents:
                return ["output=docx requiere al menos un documento en documents."]
            if content.output == "pptx" and not content.slides:
                return ["output=pptx requiere al menos una diapositiva en slides."]
            return []
        case _:
            return []


# Cuántos elementos admite cada tipo de infografía (si no, el dibujo se corta o se aprieta).
VISUAL_ITEMS = {
    "process": (3, 6),
    "timeline": (3, 7),
    "cycle": (3, 6),
    "pyramid": (3, 5),
    "funnel": (3, 5),
    "cards": (3, 4),
    "checklist": (2, 8),
    "bars": (2, 8),
    "donut": (2, 7),
}


def _visual_errors(visual: Visual | None, where: str, *, required: bool = False) -> list[str]:
    """Una infografía debe poder dibujarse: tipo y cantidad de elementos coherentes."""
    if visual is None:
        return (
            [f"{where}: falta la infografía (todo el producto debe llevar visuales)."]
            if required
            else []
        )
    errors: list[str] = []
    if any(not item.label.strip() for item in visual.items):
        errors.append(f"{where}: cada item necesita un label.")
    kind = visual.kind
    if kind in VISUAL_ITEMS:
        lo, hi = VISUAL_ITEMS[kind]
        if not lo <= len(visual.items) <= hi:
            errors.append(
                f"{where}: {kind} lleva entre {lo} y {hi} items (tiene {len(visual.items)})."
            )
    if kind == "matrix":
        if len(visual.items) != 4:
            errors.append(f"{where}: matrix lleva exactamente 4 items.")
        if not (visual.axis_x.strip() and visual.axis_y.strip()):
            errors.append(f"{where}: matrix necesita axis_x y axis_y.")
    if kind == "comparison":
        if len(visual.items) < 2 or len(visual.right_items) < 2:
            errors.append(f"{where}: comparison necesita al menos 2 items en cada columna.")
        if not (visual.left_title.strip() and visual.right_title.strip()):
            errors.append(f"{where}: comparison necesita left_title y right_title.")
    if kind in ("bars", "donut"):
        values = [i.value for i in visual.items]
        if any(v is None or v < 0 for v in values) or not any(values):
            errors.append(f"{where}: {kind} necesita un value positivo en cada item.")
    return errors


def _guide_visual_errors(content: GuideContent) -> list[str]:
    errors = _visual_errors(content.overview, "overview", required=True)
    for n, chapter in enumerate(content.chapters, start=1):
        visuals = [s.visual for s in chapter.sections if s.visual is not None]
        if not visuals:
            errors.append(f"Capítulo {n}: agrega al menos una infografía (visual) en una sección.")
        for visual in visuals:
            errors += _visual_errors(visual, f"capítulo {n}")
    with_photo = sum(1 for chapter in content.chapters if chapter.photo is not None)
    needed = len(content.chapters) // 3
    if with_photo < needed:
        errors.append(
            f"Faltan fotos: pide `photo` en al menos {needed} capítulos (hay {with_photo}), "
            "los más fotografiables (actividades, espacios, materiales)."
        )
    return errors


def _blueprint_visual_errors(content: BlueprintContent) -> list[str]:
    errors = _visual_errors(content.roadmap, "roadmap", required=True)
    for n, phase in enumerate(content.phases, start=1):
        errors += _visual_errors(phase.flow, f"fase {n} (flow)", required=True)
    errors += _visual_errors(content.success_visual, "success_visual", required=True)
    return errors


PRINTABLE_PAGES = (4, 14)
TRACKER_DAYS = (7, 14, 21, 28, 30, 31)


def _printable_errors(content: PrintableContent) -> list[str]:
    """Cada hoja debe poder imprimirse y completarse: lo que su tipo necesita para dibujarse."""
    from app.generators.printable import MAX_WORD, MIN_WORD, normalize_word, valid_words

    lo, hi = PRINTABLE_PAGES
    errors: list[str] = []
    if not lo <= len(content.pages) <= hi:
        errors.append(f"pages debe tener entre {lo} y {hi} hojas (tiene {len(content.pages)}).")
    if len(content.how_to_use) < 2:
        errors.append("how_to_use necesita al menos 2 puntos.")
    kinds = {p.kind for p in content.pages}
    if len(kinds) < 3 and len(content.pages) >= 3:
        errors.append("Usa al menos 3 tipos de hoja distintos (kind) para que el pack sea variado.")
    for n, page in enumerate(content.pages, start=1):
        where = f"hoja {n} ({page.kind})"
        items = [i for i in page.items if i.text.strip()]
        match page.kind:
            case "worksheet" if len(items) < 3:
                errors.append(f"{where}: lleva al menos 3 items (consignas).")
            case "checklist" if len(items) < 4:
                errors.append(f"{where}: lleva al menos 4 items.")
            case "table":
                if not 2 <= len([c for c in page.columns if c.strip()]) <= 7:
                    errors.append(f"{where}: columns lleva entre 2 y 7 encabezados.")
                if page.rows < 5:
                    errors.append(f"{where}: rows debe ser al menos 5 filas vacías.")
            case "tracker":
                if not 3 <= len([h for h in page.habits if h.strip()]) <= 10:
                    errors.append(f"{where}: habits lleva entre 3 y 10 hábitos.")
                if page.days not in TRACKER_DAYS:
                    errors.append(f"{where}: days debe ser uno de {list(TRACKER_DAYS)}.")
            case "recipe" if len(page.ingredients) < 3 or len(page.steps) < 3:
                errors.append(f"{where}: necesita al menos 3 ingredients y 3 steps.")
            case "word_search":
                words = valid_words([i.text for i in items])
                if len(words) < 5:
                    errors.append(
                        f"{where}: necesita al menos 5 palabras de {MIN_WORD} a {MAX_WORD} letras "
                        "(sin espacios; las tildes se quitan solas)."
                    )
                if len({normalize_word(i.text) for i in items}) != len(items):
                    errors.append(f"{where}: no repitas palabras.")
            case "matching":
                pairs = [i for i in items if i.match.strip()]
                if not 4 <= len(pairs) <= 8:
                    errors.append(f"{where}: lleva entre 4 y 8 pares (text y match).")
            case "tracing":
                if not 3 <= len(items) <= 8:
                    errors.append(f"{where}: lleva entre 3 y 8 palabras para repasar.")
                if any(len(i.text) > 14 for i in items):
                    errors.append(f"{where}: cada palabra de tracing mide hasta 14 caracteres.")
            case "notes" if page.rows and page.rows < 8:
                errors.append(f"{where}: rows debe ser al menos 8 líneas.")
    return errors


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
