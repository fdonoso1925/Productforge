"""Reglas del guion de video: lo que el schema no expresa.

Largos que caben en pantalla, cantidades exactas por escena, nada inventado (ninguna cifra que no
venga del brief) y el mismo semáforo de políticas de Meta que los anuncios estáticos. Si algo
falla, se le devuelve a la IA como feedback concreto (hasta 3 intentos).
"""

import re

from app.ads import rules as ad_rules
from app.ads.schemas import AdBrief, AdProof, PolicyVerdict
from app.video.schemas import VideoScript

DIGITS = re.compile(r"\d+(?:[.,]\d+)?")
# (campo, máximo de palabras)
WORD_LIMITS = (
    ("hook_tag", 4),
    ("problem_title", 8),
    ("solution_title", 5),
    ("solution_big", 3),
    ("solution_caption", 14),
    ("benefits_title", 5),
    ("cta_button", 4),
    ("cta_sub", 8),
)


def words(text: str) -> int:
    return len(text.split())


def script_texts(script: VideoScript) -> list[tuple[str, str]]:
    """Todo el texto que aparece en pantalla, con el nombre de su campo."""
    out = [
        ("hook_tag", script.hook_tag),
        *((f"hook_lines[{i}]", line) for i, line in enumerate(script.hook_lines)),
        ("problem_title", script.problem_title),
        *((f"problems[{i}]", p) for i, p in enumerate(script.problems)),
        ("solution_title", script.solution_title),
        ("solution_big", script.solution_big),
        ("solution_caption", script.solution_caption),
        ("benefits_title", script.benefits_title),
        *((f"benefits[{i}].title", b.title) for i, b in enumerate(script.benefits)),
        *((f"benefits[{i}].detail", b.detail) for i, b in enumerate(script.benefits)),
        ("cta_button", script.cta_button),
        ("cta_sub", script.cta_sub),
    ]
    return out


def allowed_numbers(brief: AdBrief) -> set[str]:
    """Las cifras que SÍ se pueden mostrar: las que el usuario puso en su brief."""
    facts = " ".join(
        [brief.price_text, brief.real_urgency, brief.promise, brief.product_name, *brief.bonuses]
    )
    return {n.replace(",", ".") for n in DIGITS.findall(facts)}


def check_script(script: VideoScript, brief: AdBrief) -> list[str]:
    e: list[str] = []
    lines = [line for line in script.hook_lines if line.strip()]
    if not 2 <= len(lines) <= 3:
        e.append("hook_lines debe tener 2 o 3 líneas.")
    for i, line in enumerate(script.hook_lines):
        if words(line) > 4:
            e.append(f"hook_lines[{i}] supera 4 palabras: el gancho se lee en 2 segundos.")
    if not 0 <= script.hook_highlight < max(1, len(script.hook_lines)):
        e.append("hook_highlight debe ser el índice de una de las líneas de hook_lines.")
    if len(script.problems) != 3:
        e.append("problems debe tener exactamente 3 ítems.")
    for i, p in enumerate(script.problems):
        if words(p) > 7:
            e.append(f"problems[{i}] supera 7 palabras.")
    if len(script.benefits) != 3:
        e.append("benefits debe tener exactamente 3 ítems.")
    for i, b in enumerate(script.benefits):
        if words(b.title) > 4:
            e.append(f"benefits[{i}].title supera 4 palabras.")
        if words(b.detail) > 8:
            e.append(f"benefits[{i}].detail supera 8 palabras.")
    for name, limit in WORD_LIMITS:
        value = getattr(script, name)
        if not value.strip():
            e.append(f"{name} no puede estar vacío.")
        elif words(value) > limit:
            e.append(f"{name} supera {limit} palabras.")
    allowed = allowed_numbers(brief)
    for name, text in script_texts(script):
        if "*" in text:
            e.append(f"{name} no lleva asteriscos ni marcado.")
        invented = [n for n in DIGITS.findall(text) if n.replace(",", ".") not in allowed]
        if invented:
            e.append(
                f"{name} muestra la cifra «{invented[0]}», que no está en el brief: no inventes "
                "números, plazos, precios ni cantidades."
            )
    return e


def script_policy(script: VideoScript, brief: AdBrief, proofs: list[AdProof]) -> PolicyVerdict:
    """El mismo semáforo de políticas de Meta que los anuncios estáticos."""
    text = "\n".join(t for _, t in script_texts(script) if t)
    notes = ad_rules.text_policy_notes(text, brief, proofs, brief.market)
    return PolicyVerdict(status=ad_rules.worst_status(notes), notes=notes)  # type: ignore[arg-type]
