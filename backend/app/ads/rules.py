"""Reglas determinísticas del módulo de creativos: largos, ángulos disponibles y políticas de Meta.

Dos capas con propósitos distintos:
- `check_*` devuelven errores DUROS (largo excedido, plantilla inexistente…) que se le devuelven a
  la IA como feedback para que corrija, igual que `app.content.rules`.
- `policy_verdict` es el semáforo 🟢🟡🔴 que no necesita IA: detecta con expresiones regulares lo
  evidente (atributos personales, garantías, prueba social inventada, urgencia falsa, marcas…).
  Se combina con el veredicto de la IA tomando el PEOR de los dos: la IA puede agregar riesgos,
  nunca quitar los que ya detectó una regla. Es una ayuda, no una garantía de aprobación.
"""

import re
from collections.abc import Iterable

from app.ads.schemas import (
    TEMPLATE_IDS,
    AdBrief,
    AdProof,
    AngleProposals,
    CreativeDraft,
    PolicyNote,
    PolicyVerdict,
)
from app.content.schemas import Market

# Largos de Meta / legibilidad. Se verifican en Ads Manager antes de publicar.
PRIMARY_SHORT_MAX = 125
PRIMARY_LONG_MIN, PRIMARY_LONG_MAX = 200, 700
HEADLINE_MAX = 40
DESCRIPTION_MAX = 30
IMAGE_HEADLINE_WORDS = 10
IMAGE_SUB_WORDS = 14
KICKER_WORDS = 4
CTA_WORDS = 4
BULLET_WORDS = 7
BULLETS = (3, 5)
NOTE_MAX = 220
LIST_TEMPLATES = {"checklist", "product_mockup", "offer_stack", "before_after", "comparison"}
PAIRED_TEMPLATES = {"before_after", "comparison"}  # mitad «antes» y mitad «después»
ANGLES_RANGE = (5, 6)
AVATARS_RANGE = (2, 3)

SENSITIVE_NICHE = re.compile(
    r"salud|saúde|nutric|fitness|peso|dieta|adelgaz|emagrec|materni|crianza|beb[eé]|gesta|gr[aá]vid"
    r"|finanz|finan[cç]|deud|d[ií]vid|dinero|dinheiro|invers|belleza|beleza|est[eé]tic|relacion"
    r"|ansied|ansiedad|depres|terapia|medic",
    re.IGNORECASE,
)


def is_sensitive(niche: str) -> bool:
    return bool(SENSITIVE_NICHE.search(niche))


def words(text: str) -> int:
    return len(text.split())


# ───────────────────────────── ángulos disponibles ─────────────────────────────


def available_angles(
    library: dict[str, dict], *, has_proofs: bool, has_price: bool, real_urgency: bool
) -> dict[str, dict]:
    """Los ángulos que se pueden ofrecer: los que exigen una prueba, un precio o una urgencia
    REAL solo aparecen si existen. Así el sistema nunca sugiere inventarlas."""
    gates = {"proof": has_proofs, "price": has_price, "real_urgency": real_urgency}
    return {
        angle_id: angle
        for angle_id, angle in library.items()
        if angle.get("needs") is None or gates.get(angle["needs"], False)
    }


def check_angles(
    result: AngleProposals, available: Iterable[str], avatar_names: Iterable[str]
) -> list[str]:
    errors: list[str] = []
    ids, names = set(available), set(avatar_names)
    lo, hi = ANGLES_RANGE
    if not lo <= len(result.angles) <= hi:
        errors.append(f"Devuelve entre {lo} y {hi} ángulos (devolviste {len(result.angles)}).")
    pairs: set[tuple[str, str]] = set()
    for i, a in enumerate(result.angles):
        if a.angle_id not in ids:
            errors.append(f"angles[{i}].angle_id «{a.angle_id}» no está en available_angles.")
        if a.avatar not in names:
            errors.append(f"angles[{i}].avatar «{a.avatar}» no coincide con ningún avatar.")
        if (a.angle_id, a.avatar) in pairs:
            errors.append(f"angles[{i}] repite el par ángulo + avatar.")
        pairs.add((a.angle_id, a.avatar))
    if len({a.angle_id for a in result.angles}) < 3:
        errors.append("Usa al menos 3 ángulos distintos entre sí.")
    return errors


# ───────────────────────────── errores duros del copy ─────────────────────────────


def _plain(text: str) -> str:
    """Texto sin comillas ni espacios de más, para comparar citas."""
    return " ".join(re.sub(r"[«»“”\"']", "", text).split()).lower()


def check_testimonial(draft: CreativeDraft, proofs: list[AdProof]) -> list[str]:
    """Un testimonio solo puede ser una cita textual de una prueba REAL del usuario."""
    proof = next((p for p in proofs if p.id == draft.proof_id), None)
    if proof is None:
        return ["La plantilla testimonial exige proof_id con una prueba real de proofs."]
    errors = []
    quote = _plain(draft.image.note)
    if not quote or quote not in _plain(proof.text):
        errors.append(
            "image.note debe ser una cita textual (o un fragmento) del texto de la prueba."
        )
    author = draft.image.subheadline.strip()
    if author and author != (proof.author or "").strip():
        errors.append("image.subheadline solo puede ser el autor de la prueba, tal cual (o vacío).")
    return errors


def check_draft(
    draft: CreativeDraft,
    *,
    allowed_templates: Iterable[str],
    brief: AdBrief,
    proofs: list[AdProof],
    needs_proof: bool = False,
) -> list[str]:
    e: list[str] = []
    img, ad = draft.image, draft.ad
    if draft.template_id not in set(allowed_templates):
        e.append(f"template_id «{draft.template_id}» no está en allowed_templates.")
    if draft.template_id not in TEMPLATE_IDS:
        e.append(f"template_id «{draft.template_id}» no existe.")
    if not img.headline.strip():
        e.append("image.headline no puede estar vacío.")
    if words(img.headline) > IMAGE_HEADLINE_WORDS:
        e.append(
            f"image.headline tiene {words(img.headline)} palabras (máximo {IMAGE_HEADLINE_WORDS})."
        )
    if words(img.subheadline) > IMAGE_SUB_WORDS:
        e.append(f"image.subheadline supera {IMAGE_SUB_WORDS} palabras.")
    if words(img.kicker) > KICKER_WORDS:
        e.append(f"image.kicker supera {KICKER_WORDS} palabras.")
    if words(img.cta_text) > CTA_WORDS:
        e.append(f"image.cta_text supera {CTA_WORDS} palabras.")
    for i, bullet in enumerate(img.bullets):
        if words(bullet) > BULLET_WORDS:
            e.append(f"image.bullets[{i}] supera {BULLET_WORDS} palabras.")
    lo, hi = BULLETS
    if draft.template_id in ("checklist", "offer_stack") and not lo <= len(img.bullets) <= hi:
        e.append(f"La plantilla {draft.template_id} necesita entre {lo} y {hi} bullets.")
    if draft.template_id in PAIRED_TEMPLATES and len(img.bullets) not in (2, 4):
        e.append(
            f"La plantilla {draft.template_id} necesita 2 o 4 bullets: la primera mitad es "
            "«antes / lo de siempre» y la segunda «después / con el método»."
        )
    if draft.template_id == "offer_stack" and not brief.price_text.strip():
        e.append("La plantilla offer_stack exige un precio real en el brief; usa otra plantilla.")
    if draft.template_id == "photo_headline" and (
        not draft.scene.strip() or not 2 <= len(draft.stock_keywords) <= 3
    ):
        e.append("photo_headline necesita scene y 2 o 3 stock_keywords en inglés.")
    if draft.template_id == "testimonial":
        e += check_testimonial(draft, proofs)
    if draft.template_id != "checklist" and len(img.bullets) > hi:
        e.append(f"image.bullets no puede pasar de {hi} ítems.")
    if draft.template_id == "note" and not img.note.strip():
        e.append("La plantilla note necesita image.note.")
    if len(img.note) > NOTE_MAX:
        e.append(f"image.note supera {NOTE_MAX} caracteres.")
    if img.price_text.strip() and img.price_text.strip() != brief.price_text.strip():
        e.append("image.price_text solo puede ser brief.price_text, tal cual (o vacío).")
    if len(ad.primary_short) > PRIMARY_SHORT_MAX:
        e.append(
            f"ad.primary_short tiene {len(ad.primary_short)} caracteres (máximo {PRIMARY_SHORT_MAX})."
        )
    if not PRIMARY_LONG_MIN <= len(ad.primary_long) <= PRIMARY_LONG_MAX:
        e.append(
            f"ad.primary_long tiene {len(ad.primary_long)} caracteres "
            f"(entre {PRIMARY_LONG_MIN} y {PRIMARY_LONG_MAX})."
        )
    if len(ad.headline) > HEADLINE_MAX:
        e.append(f"ad.headline tiene {len(ad.headline)} caracteres (máximo {HEADLINE_MAX}).")
    if len(ad.description) > DESCRIPTION_MAX:
        e.append(
            f"ad.description tiene {len(ad.description)} caracteres (máximo {DESCRIPTION_MAX})."
        )
    known = {p.id for p in proofs}
    if draft.proof_id is not None and draft.proof_id not in known:
        e.append(f"proof_id «{draft.proof_id}» no existe en proofs: no inventes pruebas.")
    if needs_proof and draft.proof_id is None:
        e.append("Este ángulo exige una prueba real: indica proof_id con una de proofs.")
    return e


# ───────────────────────────── semáforo de políticas ─────────────────────────────

# (regla, severidad, patrón por mercado, mensaje por mercado)
_RULES: list[tuple[str, str, dict[str, str], dict[str, str]]] = [
    (
        "atributos_personales",
        "red",
        {
            "es-LATAM": r"\b(est[aá]s|eres|tienes|sufres|padeces|te sientes)\b[^.!?\n]{0,30}\b("
            r"endeudad\w*|gord\w*|obes\w*|deprimid\w*|ansios\w*|embarazad\w*|enferm\w*|quebrad\w*"
            r"|arruinad\w*|calv\w*|diab[eé]tic\w*|adict\w*|ansiedad|depresi[oó]n|obesidad|diabetes"
            r"|sobrepeso)",
            "pt-BR": r"\b(voc[eê]\s+(est[aá]|[eé]|tem|sofre|se sente)|est[aá]s?)\b[^.!?\n]{0,30}\b("
            r"endividad\w*|gord\w*|obes\w*|deprimid\w*|ansios\w*|gr[aá]vid\w*|doente\w*|falid\w*"
            r"|careca|diab[eé]tic\w*|viciad\w*|ansiedade|depress[aã]o|obesidade|diabetes|sobrepeso)",
        },
        {
            "es-LATAM": "Afirma una característica personal del espectador (salud, peso, deudas…).",
            "pt-BR": "Afirma uma característica pessoal de quem vê (saúde, peso, dívidas…).",
        },
    ),
    (
        "atributos_personales",
        "yellow",
        {
            "es-LATAM": r"\btus?\s+(deudas?|sobrepeso|peso|ansiedad|depresi[oó]n|panza|barriga|grasa)\b",
            "pt-BR": r"\b(sua|suas|seu)\s+(d[ií]vidas?|sobrepeso|peso|ansiedade|depress[aã]o|barriga|gordura)\b",
        },
        {
            "es-LATAM": "«Tu deuda / tu peso…» insinúa un atributo personal; habla de la situación en general.",
            "pt-BR": "«Sua dívida / seu peso…» insinua um atributo pessoal; fale da situação em geral.",
        },
    ),
    (
        "garantias",
        "red",
        {
            "es-LATAM": r"\bgarantiz\w+|100\s?%\s?(seguro|efectivo|garantizado)|sin riesgo|riesgo cero"
            r"|resultados? asegurados?|hazte rico|ingresos? asegurad\w+|dinero (f[aá]cil|r[aá]pido)"
            r"|gana dinero (r[aá]pido|f[aá]cil)",
            "pt-BR": r"\bgarantid\w+|\bgarantimos|100\s?%\s?(seguro|eficaz|garantido)|sem risco|risco zero"
            r"|resultados? assegurad\w+|fique rico|renda garantida|dinheiro (f[aá]cil|r[aá]pido)"
            r"|ganhe dinheiro (r[aá]pido|f[aá]cil)",
        },
        {
            "es-LATAM": "Promete resultados garantizados o dinero fácil.",
            "pt-BR": "Promete resultados garantidos ou dinheiro fácil.",
        },
    ),
    (
        "prueba_social",
        "red",
        {
            "es-LATAM": r"\b\d[\d.,]*\s*(mil|k)?\s*\+?\s*(personas|clientes|alumnos|estudiantes|mujeres"
            r"|hombres|familias|compradores|usuarios|seguidores)\b|ya (lo )?compraron|ya lo usan|\bmiles de\b"
            r"|\bcientos de\b|[★⭐]|\bestrellas\b|\brese[ñn]as\b",
            "pt-BR": r"\b\d[\d.,]*\s*(mil|k)?\s*\+?\s*(pessoas|clientes|alunos|estudantes|mulheres"
            r"|homens|fam[ií]lias|compradores|usu[aá]rios|seguidores)\b|j[aá] compraram|j[aá] usam"
            r"|\bmilhares de\b|\bcentenas de\b|[★⭐]|\bestrelas\b|\bavalia[cç][õo]es\b",
        },
        {
            "es-LATAM": "Cifra, reseña o «X personas ya…» que no aparece en tus pruebas reales.",
            "pt-BR": "Número, avaliação ou «X pessoas já…» que não aparece nas suas provas reais.",
        },
    ),
    (
        "marcas",
        "yellow",
        {
            "es-LATAM": r"\b(instagram|facebook|whatsapp|tiktok|youtube|netflix|iphone|android|messenger"
            r"|twitter|linkedin|google|amazon|paypal|uber|apple)\b",
            "pt-BR": r"\b(instagram|facebook|whatsapp|tiktok|youtube|netflix|iphone|android|messenger"
            r"|twitter|linkedin|google|amazon|paypal|uber|apple)\b",
        },
        {
            "es-LATAM": "Menciona una marca o plataforma real: evita logos, interfaces y marcas.",
            "pt-BR": "Menciona uma marca ou plataforma real: evite logos, interfaces e marcas.",
        },
    ),
    (
        "urgencia",
        "red",
        {
            "es-LATAM": r"[uú]ltim[oa]s? (unidades|cupos|plazas|horas)|solo hoy|s[oó]lo hoy|ahora o nunca"
            r"|termina hoy|se acaba (hoy|pronto)|oferta (limitada|expira)|cupos limitados|[uú]ltimo d[ií]a"
            r"|cuenta regresiva",
            "pt-BR": r"[uú]ltim[oa]s? (unidades|vagas|horas)|s[oó] hoje|agora ou nunca|termina hoje"
            r"|acaba (hoje|logo)|oferta (limitada|expira)|vagas limitadas|[uú]ltimo dia|contagem regressiva",
        },
        {
            "es-LATAM": "Urgencia sin respaldo real (no hay una urgencia verificable en el brief).",
            "pt-BR": "Urgência sem respaldo real (não há urgência verificável no brief).",
        },
    ),
    (
        "salud",
        "red",
        {
            "es-LATAM": r"\b(cura|curar|curamos|sana(r|mos)?)\b|elimina (la |el )?(diabetes|ansiedad"
            r"|depresi[oó]n|c[aá]ncer)|antes y despu[eé]s|antes/despu[eé]s",
            "pt-BR": r"\b(cura|curar|curamos|sarar|sanar)\b|elimina (a |o )?(diabetes|ansiedade"
            r"|depress[aã]o|c[aá]ncer)|antes e depois|antes/depois",
        },
        {
            "es-LATAM": "Promesa de cura o antes/después de cuerpos (no permitido en salud y estética).",
            "pt-BR": "Promessa de cura ou antes/depois de corpos (não permitido em saúde e estética).",
        },
    ),
]
_COMPILED = [
    (rule, sev, {m: re.compile(p, re.IGNORECASE) for m, p in patterns.items()}, msgs)
    for rule, sev, patterns, msgs in _RULES
]
_WEIGHT = {
    "es-LATAM": re.compile(
        r"\b\d+\s?(kilos?|kg|libras?|lb)\b|bajar de peso|perder peso|adelgaz\w+|quemar grasa", re.I
    ),
    "pt-BR": re.compile(
        r"\b\d+\s?(quilos?|kg)\b|emagrec\w+|perder peso|queimar gordura|barriga", re.I
    ),
}
_WEIGHT_MSG = {
    "es-LATAM": "Promesa de peso o estética en un nicho sensible: Meta la restringe mucho.",
    "pt-BR": "Promessa de peso ou estética em um nicho sensível: a Meta a restringe muito.",
}


def visible_text(draft: CreativeDraft) -> str:
    """Todo lo que ve la persona: texto de la imagen y del anuncio."""
    img, ad = draft.image, draft.ad
    parts = [
        img.headline, img.subheadline, img.kicker, img.cta_text, img.price_text, img.note,
        *img.bullets, ad.primary_short, ad.primary_long, ad.headline, ad.description,
    ]  # fmt: skip
    return "\n".join(p for p in parts if p)


def _allowed_by_proofs(fragment: str, proofs: list[AdProof], brief: AdBrief) -> bool:
    haystack = " ".join([p.text for p in proofs] + [brief.price_text]).lower()
    return fragment.lower().strip() in haystack


def policy_verdict(
    draft: CreativeDraft,
    brief: AdBrief,
    proofs: list[AdProof],
    market: Market | None = None,
) -> PolicyVerdict:
    market = market or brief.market
    text = visible_text(draft)
    notes: list[PolicyNote] = []
    for rule, severity, patterns, messages in _COMPILED:
        found = patterns[market].search(text)
        if not found:
            continue
        if rule == "prueba_social" and _allowed_by_proofs(found.group(0), proofs, brief):
            continue
        sev = severity
        if rule == "urgencia" and brief.real_urgency.strip():
            sev = "yellow"  # hay una urgencia real: se pide revisar que el texto la refleje
        notes.append(PolicyNote(rule=rule, text=messages[market], severity=sev))  # type: ignore[arg-type]
    if is_sensitive(brief.niche) and _WEIGHT[market].search(text):
        notes.append(PolicyNote(rule="salud", text=_WEIGHT_MSG[market], severity="red"))
    if draft.template_id == "testimonial" and draft.proof_id is None:
        msg = {
            "es-LATAM": "Testimonio sin una prueba real cargada.",
            "pt-BR": "Depoimento sem uma prova real cadastrada.",
        }
        notes.append(PolicyNote(rule="prueba_social", text=msg[market], severity="red"))
    ad_text = f"{draft.ad.primary_short} {draft.ad.primary_long}"
    if _shouting(draft.ad.primary_short) or _shouting(draft.ad.primary_long) or "!!" in ad_text:
        msg = {
            "es-LATAM": "Mayúsculas gritadas o exceso de exclamaciones.",
            "pt-BR": "MAIÚSCULAS gritadas ou excesso de exclamações.",
        }
        notes.append(PolicyNote(rule="lenguaje", text=msg[market], severity="yellow"))
    return PolicyVerdict(status=_worst([n.severity for n in notes]), notes=notes)


def _shouting(text: str) -> bool:
    """MAYÚSCULAS gritadas: más del 40 % de las letras, en un texto de largo razonable."""
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 12 and sum(c.isupper() for c in letters) / len(letters) > 0.4


def _worst(severities: Iterable[str]) -> str:
    s = set(severities)
    return "red" if "red" in s else "yellow" if "yellow" in s else "green"


def merge_verdicts(rules: PolicyVerdict, ai: PolicyVerdict) -> PolicyVerdict:
    """Lo peor de los dos: la IA suma riesgos y la reescritura, pero no puede quitar un 🔴 de una regla."""
    return PolicyVerdict(
        status=_worst([rules.status, ai.status]),  # type: ignore[arg-type]
        notes=[*rules.notes, *ai.notes],
        rewrite=ai.rewrite,
    )
