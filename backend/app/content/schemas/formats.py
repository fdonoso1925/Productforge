"""Contenido estructurado por formato (§4).

La IA llena estos schemas; los generadores de archivos (Fase 3) los convierten en
PDF, XLSX, DOCX, etc. Nunca se le pide a la IA HTML ni código de archivos: hasta las
fórmulas de planillas se describen como operaciones sobre columnas.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.content.schemas.common import Format

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
    example: str | None = Field(default=None, description="Ejemplo concreto y local")
    callouts: list[Callout] = Field(default_factory=list)


class Chapter(BaseModel):
    title: str
    summary: str
    sections: list[Section]


class GuideContent(BaseModel):
    title: str
    subtitle: str
    promise: str
    introduction: list[str]
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


class BlueprintContent(BaseModel):
    title: str
    overview: str
    phases: list[Phase]
    success_metrics: list[str]


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
}
