"""Reglas de honestidad y estructura de la página de ventas.

Lo que el schema no puede expresar: que no se invente garantía, urgencia, cifras ni pruebas, y que
la página tenga las secciones y los largos que convierten. Los errores vuelven a la IA como
feedback; el texto que edita el usuario pasa por las mismas reglas. Precio, garantía y urgencia
no los escribe la IA: `finalize` los pone con las palabras del usuario.
"""

import re

from app.pages.schemas import PageBrief, PageContent, PageProof

RANGES = {
    "pains": (3, 6),
    "benefits": (4, 6),
    "journey": (3, 5),
    "for_you": (3, 6),
    "not_for_you": (2, 4),
    "faq": (5, 8),
}
HEADLINE_MAX = 110
SEO_TITLE_MAX, SEO_DESCRIPTION_MAX = 60, 160

_GUARANTEE = re.compile(
    r"garant[ií]|devoluci|devolu[cç]|reembols|sin riesgo|sem risco|satisfecho o|"
    r"satisfeito ou",
    re.I,
)
_NO_GUARANTEE = re.compile(
    r"\b(no|nunca|n[aã]o)\s+(se\s+|te\s+|lo\s+)?(garantiz|garant)\w*|"
    r"\bsin\s+garant[ií]as?\b|\bsem\s+garantias?\b",
    re.I,
)
_URGENCY = re.compile(
    r"solo hoy|s[oó] hoje|[uú]ltim[oa]s? (plazas|cupos|unidades|horas|vagas)|cupos? limitados?|"
    r"vagas? limitadas?|oferta (termina|expira|acaba)|por tiempo limitado|por tempo limitado|"
    r"hoy mismo|hoje mesmo|se acaba|est[aá] acabando|antes de que (suba|se acabe)|"
    r"antes que (suba|acabe)",
    re.I,
)
_SOCIAL_PROOF = re.compile(
    r"\b\d[\d.,]*\s*\+?\s*(personas|alumnos|clientes|estudiantes|compradores|miembros|lectores|"
    r"usuarios|pessoas|alunos|membros|leitores|usu[aá]rios|ventas|vendas|descargas|downloads)\b|"
    r"\b(miles|cientos|centenas|milhares) de (personas|alumnos|clientes|pessoas|alunos)\b",
    re.I,
)
_PROMISES = re.compile(
    r"100\s?%\s*(garantizad|seguro|efectiv|garantid)|resultados? (garantizad|asegurad|garantid)|"
    r"hazte rico|dinero f[aá]cil|dinheiro f[aá]cil|fique rico|sin esfuerzo|sem esfor[cç]o|"
    r"ingresos pasivos garantizados|renda passiva garantida",
    re.I,
)
_NUMBER_UNIT = re.compile(
    r"(\d[\d.,]*)\s*(%|por ciento|por cento|d[ií]as|dias|semanas|horas|minutos|meses|meses)", re.I
)


def _numbers(text: str) -> set[str]:
    return {n.strip(".,") for n in re.findall(r"\d[\d.,]*", text)}


def allowed_corpus(brief: PageBrief, proofs: list[PageProof]) -> str:
    """Todo lo que el usuario dio: de ahí pueden salir las cifras de la página."""
    return " ".join([brief.model_dump_json(), *[f"{p.text} {p.author or ''}" for p in proofs]])


def _count(errors: list[str], name: str, items: list, label: str) -> None:
    lo, hi = RANGES[name]
    if not lo <= len(items) <= hi:
        errors.append(f"«{label}» debe tener entre {lo} y {hi} elementos (tiene {len(items)}).")


def visible_text(content: PageContent) -> str:
    from app.pages.similarity import flatten

    return "\n".join(
        text for path, text in flatten(content.model_dump()) if not path.startswith("seo")
    )


def check_content(content: PageContent, brief: PageBrief, proofs: list[PageProof]) -> list[str]:
    errors: list[str] = []
    _count(errors, "pains", content.problem.pains, "problema.dolores")
    _count(errors, "benefits", content.benefits, "beneficios")
    _count(errors, "journey", content.journey, "etapas")
    _count(errors, "for_you", content.for_you, "es para ti")
    _count(errors, "not_for_you", content.not_for_you, "no es para ti")
    _count(errors, "faq", content.faq, "preguntas frecuentes")
    if len(content.hero.bullets) != 3:
        errors.append("El hero debe tener exactamente 3 bullets.")
    if len(content.hero.headline) > HEADLINE_MAX:
        errors.append(f"El título principal no puede pasar de {HEADLINE_MAX} caracteres.")
    if len(content.deliverable_blurbs) != len(brief.deliverables):
        errors.append(
            f"`deliverable_blurbs` debe tener {len(brief.deliverables)} frases, una por pieza, "
            "en el mismo orden."
        )
    known = {p.id for p in proofs}
    unknown = [i for i in content.proof.proof_ids if i not in known]
    if unknown:
        errors.append("`proof.proof_ids` solo puede usar ids de `proofs`; no inventes pruebas.")
    if not brief.about_author.strip() and content.about.strip():
        errors.append(
            "`about` debe quedar vacío: el usuario no dio datos de quién creó el producto."
        )
    for field in ("price_text", "guarantee", "urgency"):
        if getattr(content.offer, field).strip():
            errors.append(f"`offer.{field}` debe quedar vacío: lo completa el sistema.")

    text = visible_text(content)
    # «No garantizamos resultados» es el aviso honesto que sí queremos: no cuenta como garantía.
    unpromised = _NO_GUARANTEE.sub("", text)
    if not brief.guarantee_text.strip() and (m := _GUARANTEE.search(unpromised)):
        errors.append(
            f"No menciones garantía ni devoluciones («{m.group(0)}»): el usuario no ofrece ninguna."
        )
    if not brief.real_urgency.strip() and (m := _URGENCY.search(text)):
        errors.append(f"No inventes urgencia o escasez («{m.group(0)}»): no hay una urgencia real.")
    if m := _PROMISES.search(text):
        errors.append(f"Quita la promesa exagerada o garantizada («{m.group(0)}»).")
    corpus = allowed_corpus(brief, proofs)
    allowed = _numbers(corpus)
    if (m := _SOCIAL_PROOF.search(text)) and not (_numbers(m.group(0)) & allowed):
        errors.append(
            f"No inventes cifras de clientes o ventas («{m.group(0)}»): solo pruebas reales dadas."
        )
    for number, unit in _NUMBER_UNIT.findall(text):
        if number.strip(".,") not in allowed:
            errors.append(f"La cifra «{number} {unit}» no viene de los datos del usuario: quítala.")
            break
    return errors


def finalize(content: PageContent, brief: PageBrief, proofs: list[PageProof]) -> PageContent:
    """Pone precio, garantía y urgencia con las palabras del usuario y recorta lo accesorio."""
    known = {p.id for p in proofs}
    offer = content.offer.model_copy(
        update={
            "price_text": brief.price_text.strip(),
            "guarantee": brief.guarantee_text.strip(),
            "urgency": brief.real_urgency.strip(),
        }
    )
    return content.model_copy(
        update={
            "offer": offer,
            "seo_title": content.seo_title.strip()[:SEO_TITLE_MAX],
            "seo_description": content.seo_description.strip()[:SEO_DESCRIPTION_MAX],
            "proof": content.proof.model_copy(
                update={"proof_ids": [i for i in content.proof.proof_ids if i in known]}
            ),
        }
    )
