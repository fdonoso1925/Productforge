"""Generadores enchufables (§4): un módulo por formato, todos con la misma interfaz.

Agregar un formato = crear un módulo con una clase decorada con `@register`, e
importarlo en `app/generators/__init__.py`. Nada más cambia.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import ClassVar, Protocol

from pydantic import BaseModel

from app.content.schemas import Format, Market, Role
from app.templates_engine.model import Template


@dataclass(frozen=True)
class FileArtifact:
    filename: str
    file_type: str
    content: bytes
    mime: str


@dataclass(frozen=True)
class RenderContext:
    market: Market
    role: Role
    slug: str  # base del nombre de archivo, p. ej. "guia-adeus-cheque-especial"
    product_name: str = ""
    promise: str = ""  # promesa de la pieza (outline), para la portada

    @property
    def labels(self) -> dict[str, str]:
        return LABELS[self.market]

    @property
    def currency(self) -> str:
        return "BRL" if self.market == "pt-BR" else "USD"


class FileGenerator(Protocol):
    format: ClassVar[Format]
    outputs: ClassVar[tuple[str, ...]]

    def generate(
        self, content: BaseModel, template: Template, ctx: RenderContext
    ) -> list[FileArtifact]: ...


REGISTRY: dict[Format, FileGenerator] = {}


def register(cls: type) -> type:
    REGISTRY[cls.format] = cls()
    return cls


def generate_files(
    fmt: Format, content: BaseModel, template: Template, ctx: RenderContext
) -> list[FileArtifact]:
    return REGISTRY[fmt].generate(content, template, ctx)


MIME = {
    "pdf": "application/pdf",
    "epub": "application/epub+zip",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "svg": "image/svg+xml",
    "png": "image/png",
    "md": "text/markdown",
    "mmd": "text/plain",
    "opml": "text/x-opml",
    "mm": "application/x-freemind",
    "xmind": "application/vnd.xmind.workbook",
    "drawio": "application/vnd.jgraph.mxfile",
}


def artifact(ctx: RenderContext, ext: str, content: bytes, suffix: str = "") -> FileArtifact:
    name = f"{ctx.slug}{('-' + suffix) if suffix else ''}.{ext}"
    return FileArtifact(filename=name, file_type=ext, content=content, mime=MIME[ext])


def slugify(text: str, max_length: int = 60) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_length].rstrip("-") or "producto"


LABELS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "tip": "Dica",
        "warning": "Atenção",
        "exercise": "Exercício",
        "toc": "Sumário",
        "introduction": "Introdução",
        "conclusion": "Conclusão",
        "next_steps": "Próximos passos",
        "chapter": "Capítulo",
        "page": "Página",
        "example": "Exemplo",
        "steps": "Passo a passo",
        "day": "Dia",
        "focus": "Foco",
        "tasks": "Tarefas",
        "reflection": "Reflexão",
        "weekly_review": "Revisão semanal",
        "phase": "Fase",
        "duration": "Duração",
        "objective": "Objetivo",
        "deliverables": "Entregáveis",
        "mistakes": "Erros comuns",
        "success_metrics": "Como saber que deu certo",
        "when_to_use": "Quando usar",
        "notes": "Como adaptar",
        "how_to_use": "Como usar",
        "instructions": "Instruções",
        "total": "Total",
        "yes": "Sim",
        "no": "Não",
        "focus_question": "Pergunta central",
        "concepts": "Conceitos",
    },
    "es-LATAM": {
        "tip": "Consejo",
        "warning": "Atención",
        "exercise": "Ejercicio",
        "toc": "Índice",
        "introduction": "Introducción",
        "conclusion": "Conclusión",
        "next_steps": "Próximos pasos",
        "chapter": "Capítulo",
        "page": "Página",
        "example": "Ejemplo",
        "steps": "Paso a paso",
        "day": "Día",
        "focus": "Foco",
        "tasks": "Tareas",
        "reflection": "Reflexión",
        "weekly_review": "Revisión semanal",
        "phase": "Fase",
        "duration": "Duración",
        "objective": "Objetivo",
        "deliverables": "Entregables",
        "mistakes": "Errores comunes",
        "success_metrics": "Cómo saber que funcionó",
        "when_to_use": "Cuándo usarlo",
        "notes": "Cómo adaptarlo",
        "how_to_use": "Cómo usar",
        "instructions": "Instrucciones",
        "total": "Total",
        "yes": "Sí",
        "no": "No",
        "focus_question": "Pregunta central",
        "concepts": "Conceptos",
    },
}
