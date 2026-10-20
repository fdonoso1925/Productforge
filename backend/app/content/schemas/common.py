from enum import StrEnum
from typing import Literal

Market = Literal["pt-BR", "es-LATAM"]
Role = Literal["main", "order_bump", "bonus"]

CURRENCY: dict[str, str] = {"pt-BR": "BRL", "es-LATAM": "USD"}  # D4: LATAM en USD


class Format(StrEnum):
    """Formatos de pieza. Los valores coinciden con el enum `format_t` de Postgres."""

    PDF_GUIDE = "pdf_guide"
    EPUB = "epub"
    MIND_MAP = "mind_map"
    CONCEPT_MAP = "concept_map"
    SHEET = "sheet"
    CHECKLIST = "checklist"
    BLUEPRINT = "blueprint"
    EDITABLE_TEMPLATE = "editable_template"
    PLANNER = "planner"
    SWIPE_FILE = "swipe_file"


# Formatos livianos aptos para bonus (§7).
BONUS_FORMATS = frozenset(
    {
        Format.MIND_MAP,
        Format.CONCEPT_MAP,
        Format.SWIPE_FILE,
        Format.PLANNER,
        Format.PDF_GUIDE,
        Format.CHECKLIST,
    }
)
