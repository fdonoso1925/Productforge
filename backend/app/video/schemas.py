"""Guion de un video de motion graphics: lo que la IA escribe y el motor anima.

Estructura fija de 5 escenas (gancho → problema → solución → qué recibes → CTA), como en la
skill de motion graphics. Todos los campos son obligatorios a propósito: un schema con muchos
opcionales es «demasiado complejo» para la salida estructurada.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VideoRatio = Literal["9x16", "4x5"]


class VideoBenefit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="Lo que recibe, en 2 a 4 palabras")
    detail: str = Field(description="Para qué le sirve, en 3 a 8 palabras")


class VideoScript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook_tag: str = Field(description="Etiqueta corta sobre el gancho (2 a 4 palabras)")
    hook_lines: list[str] = Field(description="El gancho en 2 o 3 líneas de 1 a 4 palabras")
    hook_highlight: int = Field(description="Índice (desde 0) de la línea que va destacada")
    problem_title: str = Field(description="Título de la escena de problemas (3 a 8 palabras)")
    problems: list[str] = Field(description="Exactamente 3 problemas o frustraciones reales")
    solution_title: str = Field(description="Frase que abre la solución (2 a 5 palabras)")
    solution_big: str = Field(description="Palabra o expresión clave grande (1 a 3 palabras)")
    solution_caption: str = Field(description="Lo que logra el producto (6 a 14 palabras)")
    benefits_title: str = Field(description="Título de lo que recibe (2 a 5 palabras)")
    benefits: list[VideoBenefit] = Field(description="Exactamente 3 entregables reales")
    cta_button: str = Field(description="Botón en imperativo y 1.ª persona (2 a 4 palabras)")
    cta_sub: str = Field(description="Línea de confianza verdadera bajo el botón (2 a 8 palabras)")
