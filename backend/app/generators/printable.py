"""Hojas imprimibles (PDF A4): la persona las imprime y las completa a mano.

La IA describe cada hoja (`PrintablePage`: ejercicios, tabla, seguimiento de hábitos, calendario,
receta, sopa de letras, unir con líneas, repasar palabras, checklist, hojas rayadas) y este módulo
las dibuja. Lo que requiere cálculo se hace aquí, no en la IA: la sopa de letras se arma por código
(posiciones y letras de relleno, siempre con solución posible), el orden del lado derecho de «unir»
se baraja de forma determinista y los calendarios son cuadrículas en blanco.

El papel es blanco y casi sin tinta: nada de fondos de color aunque la plantilla visual sea oscura.
"""

import random
import re
import unicodedata
import zlib
from typing import ClassVar

from app.content.schemas import Format
from app.content.schemas.formats import PrintableContent, PrintablePage
from app.generators.base import FileArtifact, RenderContext, artifact, register
from app.generators.render import html_to_pdf
from app.templates_engine.model import Template

LABELS = {
    "es-LATAM": {
        "name": "Nombre",
        "date": "Fecha",
        "how_to_use": "Cómo usar estas hojas",
        "ingredients": "Ingredientes",
        "steps": "Preparación",
        "servings": "Porciones",
        "time": "Tiempo",
        "notes": "Notas",
        "month": "Mes",
        "week_of": "Semana del",
        "priorities": "Prioridades de la semana",
        "habit": "Hábito o meta",
        "words": "Palabras para encontrar",
        "trace": "Repasa y luego escribe tú",
        "weekdays": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"],
        "short": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
    },
    "pt-BR": {
        "name": "Nome",
        "date": "Data",
        "how_to_use": "Como usar estas folhas",
        "ingredients": "Ingredientes",
        "steps": "Modo de preparo",
        "servings": "Porções",
        "time": "Tempo",
        "notes": "Anotações",
        "month": "Mês",
        "week_of": "Semana de",
        "priorities": "Prioridades da semana",
        "habit": "Hábito ou meta",
        "words": "Palavras para encontrar",
        "trace": "Repasse e depois escreva você",
        "weekdays": ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"],
        "short": ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"],
    },
}

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIRECTIONS = [(0, 1), (1, 0), (1, 1)]  # → ↓ ↘: las más fáciles de seguir con la vista
MIN_WORD, MAX_WORD, MAX_WORDS = 3, 12, 12
MIN_ROWS = 5


def normalize_word(text: str) -> str:
    """MAYÚSCULAS sin tildes ni espacios (la sopa de letras usa solo A-Z)."""
    folded = unicodedata.normalize("NFKD", text.upper())
    return re.sub(r"[^A-Z]", "", "".join(c for c in folded if not unicodedata.combining(c)))


def valid_words(items: list[str]) -> list[str]:
    seen: list[str] = []
    for text in items:
        word = normalize_word(text)
        if MIN_WORD <= len(word) <= MAX_WORD and word not in seen:
            seen.append(word)
    return seen[:MAX_WORDS]


def seed_of(*parts: str) -> int:
    return zlib.crc32("|".join(parts).encode())


def build_word_search(words: list[str], seed: int) -> tuple[list[list[str]], list[str]]:
    """Sopa de letras: (cuadrícula, palabras colocadas). Cada palabra va en una línea recta
    (derecha, abajo o diagonal) y el resto se rellena con letras al azar, siempre igual para el
    mismo contenido."""
    clean = sorted(valid_words(words), key=len, reverse=True)
    if not clean:
        return [], []
    size = max(10, len(clean[0]), min(14, 8 + len(clean) // 2))
    rng = random.Random(seed)  # noqa: S311  (azar determinista para maquetar, no criptografía)
    grid = [["" for _ in range(size)] for _ in range(size)]
    placed: list[str] = []
    for word in clean:
        for _ in range(300):
            dr, dc = rng.choice(DIRECTIONS)
            r, c = rng.randrange(size), rng.randrange(size)
            end_r, end_c = r + dr * (len(word) - 1), c + dc * (len(word) - 1)
            if end_r >= size or end_c >= size:
                continue
            cells = [(r + dr * i, c + dc * i) for i in range(len(word))]
            if all(grid[y][x] in ("", word[i]) for i, (y, x) in enumerate(cells)):
                for i, (y, x) in enumerate(cells):
                    grid[y][x] = word[i]
                placed.append(word)
                break
    for row in grid:
        for x, letter in enumerate(row):
            if not letter:
                row[x] = rng.choice(ALPHABET)
    return grid, placed


def shuffled(values: list[str], seed: int) -> list[str]:
    """Orden barajado pero estable; si por azar queda igual al original, se rota una posición."""
    out = list(values)
    random.Random(seed).shuffle(out)  # noqa: S311
    if out == values and len(out) > 1:
        out = out[1:] + out[:1]
    return out


def prepare(page: PrintablePage, labels: dict, seed: int) -> dict:
    """Todo lo que la hoja necesita ya calculado, para que la plantilla solo dibuje."""
    view: dict = {"p": page, "kind": page.kind}
    if page.kind == "word_search":
        grid, placed = build_word_search([i.text for i in page.items], seed)
        view.update(grid=grid, placed=placed)
    elif page.kind == "matching":
        pairs = [i for i in page.items if i.text.strip() and i.match.strip()]
        view.update(left=[i.text for i in pairs], right=shuffled([i.match for i in pairs], seed))
    elif page.kind == "tracker":
        days = max(1, min(page.days, 31))
        view.update(
            day_numbers=list(range(1, days + 1)), dot=round(max(2.2, min(4.0, 118 / days - 1.4)), 1)
        )
    elif page.kind == "table":
        view.update(blank_rows=range(max(page.rows, MIN_ROWS)))
    elif page.kind == "notes":
        view.update(blank_rows=range(max(page.rows, 12)))
    elif page.kind == "worksheet":
        view.update(
            work=[(item, range(item.lines or 1)) for item in page.items if item.text.strip()]
        )
    elif page.kind == "calendar":
        view.update(weeks=range(6) if page.calendar_kind == "month" else range(7))
    return view


def render_html(content: PrintableContent, template: Template, ctx: RenderContext) -> str:
    labels = LABELS[ctx.market]
    pages = [
        prepare(page, labels, seed_of(content.title, str(n), page.title))
        for n, page in enumerate(content.pages, start=1)
    ]
    return template.render_html("printable", c=content, ctx=ctx, P=labels, pages=pages)


@register
class PrintablePdf:
    format: ClassVar[Format] = Format.PRINTABLE
    outputs: ClassVar[tuple[str, ...]] = ("pdf",)

    def generate(
        self, content: PrintableContent, template: Template, ctx: RenderContext
    ) -> list[FileArtifact]:
        pdf = html_to_pdf(render_html(content, template, ctx), template.base_dir)
        return [artifact(ctx, "pdf", pdf)]
