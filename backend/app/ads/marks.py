"""Palabras destacadas en el titular de una imagen: `Cocina *natural* para tu perro`.

Las 1 a 3 palabras que cargan la emoción van entre asteriscos y la plantilla las dibuja sobre un
bloque del color de acento. Los asteriscos son solo marcado: para contar palabras, revisar
políticas, exportar o agrupar titulares se usa el texto limpio (`strip_marks`).
"""

import re

MARK = re.compile(r"\*([^*\n]+)\*")
MAX_MARKS = 3  # tramos destacados por titular
MAX_MARK_WORDS = 3  # palabras por tramo


def strip_marks(text: str) -> str:
    """El texto sin los asteriscos de marcado."""
    return text.replace("*", "")


def mark_errors(text: str, field: str = "image.headline") -> list[str]:
    """Errores del marcado de un titular (vacío si está bien o no tiene marcas)."""
    if "*" not in text:
        return []
    if text.count("*") % 2 or "**" in text:
        return [f"{field}: cada palabra destacada va entre dos asteriscos, *así*."]
    spans = MARK.findall(text)
    errors = []
    if len(spans) > MAX_MARKS:
        errors.append(f"{field}: destaca como máximo {MAX_MARKS} tramos con asteriscos.")
    if any(len(span.split()) > MAX_MARK_WORDS for span in spans):
        errors.append(f"{field}: cada tramo destacado tiene como máximo {MAX_MARK_WORDS} palabras.")
    return errors
