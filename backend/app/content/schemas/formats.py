"""Contenido estructurado por formato (§4).

La IA llena estos schemas; los generadores de archivos (Fase 3) los convierten en
PDF, XLSX, DOCX, etc. Nunca se le pide a la IA HTML ni código de archivos: hasta las
fórmulas de planillas se describen como operaciones sobre columnas.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.content.schemas.common import Format

# ─────────────────────────── Visuales (infografías, gráficos, fotos) ───────────────────────────

VisualKind = Literal[
    "process", "timeline", "cycle", "pyramid", "funnel", "matrix", "comparison", "cards",
    "checklist", "bars", "donut",
]  # fmt: skip
IconName = Literal[
    "check", "x", "star", "flag", "clock", "target", "bulb", "warning", "arrow", "user", "book",
    "chart", "heart",
]  # fmt: skip


class VisualItem(BaseModel):
    label: str = Field(description="Texto corto (2 a 6 palabras)")
    detail: str = Field(default="", description="Una frase breve que lo explica; puede ir vacía")
    value: float | None = Field(default=None, description="Solo para bars y donut")
    icon: IconName | None = Field(default=None, description="Ícono opcional que ilustra la idea")


class Visual(BaseModel):
    """Una infografía o gráfico que el sistema dibuja con la paleta de la plantilla.

    Los textos son breves: el dibujo recorta lo que no cabe. Nunca se inventan datos reales: un
    gráfico de barras o de dona solo muestra proporciones de referencia (`illustrative`)."""

    kind: VisualKind = Field(
        description=(
            "process = pasos en secuencia; timeline = hitos en el tiempo; "
            "cycle = ciclo que se repite; pyramid = niveles de base a cima; "
            "funnel = etapas que se afinan; "
            "matrix = cuadrante 2x2 (items: arriba-izq, arriba-der, abajo-izq, abajo-der); "
            "comparison = dos columnas (items = izquierda, right_items = derecha); "
            "cards = 3 o 4 ideas clave; checklist = lista de verificación; "
            "bars/donut = proporciones con `value`"
        )
    )
    title: str = Field(description="Título descriptivo de la infografía")
    caption: str = Field(default="", description="Pie opcional: qué debe notar la persona")
    items: list[VisualItem]
    right_items: list[VisualItem] = Field(default_factory=list, description="Solo comparison")
    left_title: str = Field(default="", description="Solo comparison: título de la izquierda")
    right_title: str = Field(default="", description="Solo comparison: título de la derecha")
    axis_x: str = Field(default="", description="Solo matrix: nombre del eje horizontal")
    axis_y: str = Field(default="", description="Solo matrix: nombre del eje vertical")
    unit: str = Field(default="", description="Solo bars/donut: unidad (%, h, USD…)")
    illustrative: bool = Field(
        default=True,
        description="true = los valores son un ejemplo o una referencia, no datos medidos",
    )


class PhotoSpec(BaseModel):
    """Una foto de stock que abre un capítulo. Se busca por palabras clave (en inglés)."""

    scene: str = Field(description="Escena en inglés: lugar, objetos o actividad, sin texto")
    keywords: list[str] = Field(description="2 o 3 palabras clave en inglés para buscarla")
    caption: str = Field(default="", description="Pie de foto opcional en el idioma del mercado")


# ─────────────────────────── Guía / ebook (pdf_guide, epub) ───────────────────────────


class Callout(BaseModel):
    kind: Literal["tip", "warning", "exercise"] = Field(
        description="tip = Dica/Consejo, warning = Atenção/Atención, exercise = Exercício/Ejercicio"
    )
    title: str
    text: str


class Section(BaseModel):
    heading: str
    paragraphs: list[str]
    bullets: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list, description="Pasos numerados accionables")
    example: str | None = Field(
        default=None,
        description="Ejemplo concreto del nicho, como situación hipotética («Imagina que…»); "
        "nunca un caso real inventado ni nombres propios",
    )
    callouts: list[Callout] = Field(default_factory=list)
    visual: Visual | None = Field(
        default=None, description="Infografía que ilustra esta sección (va después de su texto)"
    )


class Chapter(BaseModel):
    title: str
    summary: str
    sections: list[Section]
    photo: PhotoSpec | None = Field(
        default=None, description="Foto que abre el capítulo (solo si aporta al tema)"
    )


class GuideContent(BaseModel):
    title: str
    subtitle: str
    promise: str
    introduction: list[str]
    overview: Visual | None = Field(
        default=None,
        description="Mapa visual de toda la guía (ruta o resumen), tras la introducción",
    )
    chapters: list[Chapter]
    conclusion: list[str]
    next_steps: list[str]


# ─────────────────────────── Mapa mental ───────────────────────────


class MindLeaf(BaseModel):
    label: str
    children: list[str] = Field(default_factory=list)


class MindBranch(BaseModel):
    label: str
    note: str | None = None
    children: list[MindLeaf]


class MindMapContent(BaseModel):
    title: str
    central_idea: str
    branches: list[MindBranch]


# ─────────────────────────── Mapa conceptual ───────────────────────────


class Concept(BaseModel):
    id: str = Field(description="Identificador corto en snake_case, único")
    label: str
    description: str


class Relation(BaseModel):
    source: str = Field(description="id del concepto origen")
    target: str = Field(description="id del concepto destino")
    label: str = Field(description="Verbo o frase que etiqueta la relación")


class ConceptMapContent(BaseModel):
    title: str
    focus_question: str
    concepts: list[Concept]
    relations: list[Relation]


# ─────────────────────────── Planilla ───────────────────────────


class Computation(BaseModel):
    """Fórmula descrita como operación; el generador la traduce a Excel."""

    op: Literal["sum", "subtract", "multiply", "divide", "percent_of"]
    operands: list[str] = Field(description="Encabezados de columnas de la misma fila, en orden")


class Column(BaseModel):
    header: str
    type: Literal["text", "number", "currency", "percent", "date", "choice", "checkbox"]
    choices: list[str] = Field(default_factory=list, description="Solo para type=choice")
    computed: Computation | None = Field(default=None, description="Si la columna se calcula")
    total: Literal["sum", "average", "count", "max", "min"] | None = Field(
        default=None, description="Agregado en la fila de totales"
    )


class SheetTab(BaseModel):
    name: str = Field(max_length=31)
    kind: Literal["tracker", "calculator", "planner", "budget"]
    instructions: str
    columns: list[Column]
    sample_rows: list[list[str]] = Field(
        description="Filas de ejemplo; valores como texto, vacío en columnas calculadas"
    )
    empty_rows: int = Field(ge=0, le=500, description="Filas vacías listas para usar")


class SheetContent(BaseModel):
    title: str
    purpose: str
    how_to_use: list[str]
    tabs: list[SheetTab]


# ─────────────────────────── Checklist / workbook ───────────────────────────


class ChecklistItem(BaseModel):
    text: str
    detail: str | None = None


class ChecklistGroup(BaseModel):
    title: str
    items: list[ChecklistItem]


class WritingPrompt(BaseModel):
    question: str
    lines: int = Field(ge=1, le=20, description="Líneas en blanco para escribir a mano")


class ChecklistContent(BaseModel):
    title: str
    introduction: str
    visual: Visual | None = Field(
        default=None, description="Infografía de cómo usarlo o de la ruta"
    )
    groups: list[ChecklistGroup]
    writing_prompts: list[WritingPrompt]


# ─────────────────────────── Blueprint ───────────────────────────


class Phase(BaseModel):
    name: str
    duration: str
    objective: str
    steps: list[str]
    deliverables: list[str]
    common_mistakes: list[str]
    flow: Visual | None = Field(
        default=None, description="Diagrama de la fase (los pasos como proceso, ciclo o matriz)"
    )


class BlueprintContent(BaseModel):
    title: str
    overview: str
    roadmap: Visual | None = Field(
        default=None, description="Mapa de todas las fases (timeline o process)"
    )
    phases: list[Phase]
    success_metrics: list[str]
    success_visual: Visual | None = Field(
        default=None, description="Las métricas de éxito como tarjetas o checklist"
    )


# ─────────────────────────── Plantillas editables (docx / pptx) ───────────────────────────


class TemplateBlock(BaseModel):
    kind: Literal["heading", "paragraph", "placeholder", "bullets"]
    text: str = Field(description="Para placeholder: texto entre [CORCHETES] a reemplazar")
    items: list[str] = Field(default_factory=list, description="Solo para bullets")


class TemplateDocument(BaseModel):
    name: str
    purpose: str
    blocks: list[TemplateBlock]


class Slide(BaseModel):
    title: str
    bullets: list[str]
    speaker_notes: str | None = None


class EditableTemplateContent(BaseModel):
    title: str
    instructions: list[str]
    output: Literal["docx", "pptx"]
    documents: list[TemplateDocument] = Field(default_factory=list, description="Si output=docx")
    slides: list[Slide] = Field(default_factory=list, description="Si output=pptx")


# ─────────────────────────── Planner ───────────────────────────


class PlannerDay(BaseModel):
    day: int = Field(ge=1)
    focus: str
    tasks: list[str]
    tip: str
    reflection_question: str


class PlannerContent(BaseModel):
    title: str
    duration_days: Literal[7, 21, 30]
    introduction: str
    roadmap: Visual | None = Field(default=None, description="Ruta visual de las etapas del plan")
    days: list[PlannerDay]
    weekly_review_questions: list[str] = Field(default_factory=list)


# ─────────────────────────── Swipe file ───────────────────────────


class SwipeEntry(BaseModel):
    label: str
    text: str = Field(description="Texto listo para copiar")
    notes: str | None = Field(default=None, description="Cuándo y cómo adaptarlo")


class SwipeCategory(BaseModel):
    name: str
    when_to_use: str
    entries: list[SwipeEntry]


class SwipeFileContent(BaseModel):
    title: str
    introduction: str
    categories: list[SwipeCategory]


# ─────────────────────────── Hojas imprimibles ───────────────────────────

PrintableKind = Literal[
    "worksheet", "table", "tracker", "calendar", "recipe", "word_search", "matching", "tracing",
    "checklist", "notes",
]  # fmt: skip


def _all_required(schema: dict) -> None:
    # La API de salida estructurada rechaza ("Schema is too complex") los esquemas con muchos
    # campos opcionales: se le declaran todos obligatorios (vacío = no aplica). Al leer la
    # respuesta, los valores por defecto siguen valiendo.
    for prop in schema.get("properties", {}).values():
        prop.pop("default", None)
    schema["required"] = list(schema.get("properties", {}))


class PrintableItem(BaseModel):
    model_config = ConfigDict(json_schema_extra=_all_required)

    text: str = Field(
        description="Consigna o pregunta (worksheet), tarea (checklist), palabra (word_search y "
        "tracing) o el lado izquierdo (matching)"
    )
    match: str = Field(
        default="", description="Solo matching: lo que corresponde al lado izquierdo"
    )
    lines: int = Field(default=0, ge=0, le=8, description="Solo worksheet: líneas para responder")
    hint: str = Field(default="", description="Pista opcional, corta")


class PrintablePage(BaseModel):
    """Una hoja para imprimir (A4). El sistema la dibuja; la persona la completa a mano."""

    model_config = ConfigDict(json_schema_extra=_all_required)

    kind: PrintableKind = Field(
        description="worksheet = ejercicios con espacio para responder; table = tabla con filas "
        "vacías (presupuesto, registro de entrenamiento, lista de compras…); tracker = "
        "seguimiento de hábitos por día; calendar = calendario mensual o semanal en blanco; "
        "recipe = ficha de receta; word_search = sopa de letras (items = palabras); matching = "
        "unir con líneas (items = pares text/match); tracing = repasar palabras (items = "
        "palabras cortas); checklist = lista para tachar; notes = hoja rayada para anotar"
    )
    title: str
    instructions: str = Field(default="", description="Una o dos frases que dicen qué hacer")
    items: list[PrintableItem] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list, description="Solo table: encabezados (2 a 7)")
    rows: int = Field(default=0, ge=0, le=40, description="table: filas vacías · notes: líneas")
    habits: list[str] = Field(default_factory=list, description="Solo tracker: hábitos o metas")
    days: int = Field(default=7, description="Solo tracker: columnas (7, 14, 21, 28 o 30)")
    calendar_kind: Literal["month", "week"] = "month"
    ingredients: list[str] = Field(default_factory=list, description="Solo recipe")
    steps: list[str] = Field(default_factory=list, description="Solo recipe")
    servings: str = Field(default="", description="Solo recipe: porciones")
    time: str = Field(default="", description="Solo recipe: tiempo total")
    footer: str = Field(default="", description="Frase corta de ánimo o consejo al pie; opcional")


class PrintableContent(BaseModel):
    model_config = ConfigDict(json_schema_extra=_all_required)

    title: str
    how_to_use: list[str] = Field(description="Cómo imprimir y usar las hojas (3 a 5 puntos)")
    audience_note: str = Field(default="", description="Para quién es (p. ej. edad de los niños)")
    pages: list[PrintablePage]


ProductContent = (
    GuideContent
    | MindMapContent
    | ConceptMapContent
    | SheetContent
    | ChecklistContent
    | BlueprintContent
    | EditableTemplateContent
    | PlannerContent
    | SwipeFileContent
    | PrintableContent
)

FORMAT_SCHEMAS: dict[Format, type[BaseModel]] = {
    Format.PDF_GUIDE: GuideContent,
    Format.EPUB: GuideContent,
    Format.MIND_MAP: MindMapContent,
    Format.CONCEPT_MAP: ConceptMapContent,
    Format.SHEET: SheetContent,
    Format.CHECKLIST: ChecklistContent,
    Format.BLUEPRINT: BlueprintContent,
    Format.EDITABLE_TEMPLATE: EditableTemplateContent,
    Format.PLANNER: PlannerContent,
    Format.SWIPE_FILE: SwipeFileContent,
    Format.PRINTABLE: PrintableContent,
}
