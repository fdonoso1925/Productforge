"""Instrucciones para construir la página en Lovable (https://lovable.dev) con «Build with URL».

Lovable recibe un texto y construye la página con su propia IA. Para que no la cambie, el texto
lleva TODO el contenido ya escrito (el que pasó nuestras reglas y el control de parecido) y pide
usarlo tal cual, y prohíbe inventar pruebas, garantías, urgencia, cifras, logos o imágenes.
Nada de la página modelo viaja aquí: ni su análisis, ni su URL, ni su huella.
"""

from app.pages.render import safe_link
from app.pages.schemas import PageBrief, PageContent, PageProof
from app.templates_engine.model import Template

MAX_CHARS = 50_000  # límite de Lovable para el texto
URL_SAFE_CHARS = 20_000  # el enlace ya codificado se vuelve largo: sobre esto solo se copia

INTRO = {
    "es-LATAM": (
        "Construye una landing page de ventas de UNA sola página, en español, pensada para "
        "convertir visitas en compradores. Diseño mobile-first, limpio y profesional, con una "
        "barra de compra fija abajo en el celular y botones grandes.\n\n"
        "REGLAS (obligatorias):\n"
        "- Usa EXACTAMENTE los textos de abajo, en el mismo orden de secciones. No reescribas, no "
        "resumas, no agregues ni quites frases.\n"
        "- No inventes testimonios, reseñas, cifras, «X personas ya compraron», logos, sellos, "
        "garantías, descuentos, cuentas regresivas ni escasez. Si un dato no está abajo, "
        "no existe.\n"
        "- No uses fotos de personas, logos de marcas ni imágenes de stock. Si necesitas ilustrar, "
        "usa solo formas, íconos simples y los colores indicados.\n"
        "- No agregues secciones, formularios ni pop-ups. Solo esta página.\n"
        "- Todos los botones de compra llevan al mismo enlace.\n"
    ),
    "pt-BR": (
        "Construa uma landing page de vendas de UMA única página, em português do Brasil, pensada "
        "para converter visitas em compradores. Design mobile-first, limpo e profissional, com uma "
        "barra de compra fixa embaixo no celular e botões grandes.\n\n"
        "REGRAS (obrigatórias):\n"
        "- Use EXATAMENTE os textos abaixo, na mesma ordem de seções. Não reescreva, não resuma, "
        "não acrescente nem retire frases.\n"
        "- Não invente depoimentos, avaliações, números, «X pessoas já compraram», logos, selos, "
        "garantias, descontos, contagens regressivas nem escassez. Se um dado não está abaixo, ele "
        "não existe.\n"
        "- Não use fotos de pessoas, logos de marcas nem imagens de banco. Se precisar ilustrar, "
        "use só formas, ícones simples e as cores indicadas.\n"
        "- Não acrescente seções, formulários nem pop-ups. Só esta página.\n"
        "- Todos os botões de compra levam ao mesmo link.\n"
    ),
}

LABELS = {
    "es-LATAM": {
        "design": "DISEÑO",
        "colors": "Colores",
        "fonts": "Tipografías",
        "heading": "títulos",
        "body": "texto",
        "link": "ENLACE DE COMPRA (todos los botones)",
        "nolink": "ENLACE DE COMPRA: aún no hay; deja los botones en la sección de la oferta.",
        "sections": "SECCIONES, EN ORDEN",
        "hero": "1. INICIO (hero)",
        "problem": "2. PROBLEMA",
        "solution": "3. SOLUCIÓN Y ETAPAS",
        "benefits": "4. BENEFICIOS",
        "inside": "5. QUÉ INCLUYE (tarjetas)",
        "fit": "6. PARA QUIÉN ES",
        "for_you": "Es para ti si…",
        "not_for_you": "No es para ti si…",
        "about": "7. QUIÉN LO CREÓ",
        "proof": "8. PRUEBAS (citar textual, sin cambiar nada)",
        "offer": "9. OFERTA",
        "faq": "10. PREGUNTAS FRECUENTES (acordeón)",
        "final": "11. CIERRE",
        "disclaimer": "AVISO (pie de página, texto pequeño)",
        "button": "Botón",
        "price": "Precio",
        "guarantee": "Garantía",
        "urgency": "Urgencia",
        "main": "Principal",
        "bonus": "Bonus",
        "bump": "Opcional",
        "mechanism": "Método",
        "pains": "Dolores (lista con ✕)",
        "agitation": "Cierre de la sección",
        "bullets": "Puntos clave (lista con ✓)",
    },
    "pt-BR": {
        "design": "DESIGN",
        "colors": "Cores",
        "fonts": "Tipografias",
        "heading": "títulos",
        "body": "texto",
        "link": "LINK DE COMPRA (todos os botões)",
        "nolink": "LINK DE COMPRA: ainda não há; deixe os botões apontando para a seção da oferta.",
        "sections": "SEÇÕES, EM ORDEM",
        "hero": "1. INÍCIO (hero)",
        "problem": "2. PROBLEMA",
        "solution": "3. SOLUÇÃO E ETAPAS",
        "benefits": "4. BENEFÍCIOS",
        "inside": "5. O QUE INCLUI (cartões)",
        "fit": "6. PARA QUEM É",
        "for_you": "É para você se…",
        "not_for_you": "Não é para você se…",
        "about": "7. QUEM CRIOU",
        "proof": "8. PROVAS (citar literalmente, sem mudar nada)",
        "offer": "9. OFERTA",
        "faq": "10. PERGUNTAS FREQUENTES (acordeão)",
        "final": "11. FECHAMENTO",
        "disclaimer": "AVISO (rodapé, texto pequeno)",
        "button": "Botão",
        "price": "Preço",
        "guarantee": "Garantia",
        "urgency": "Urgência",
        "main": "Principal",
        "bonus": "Bônus",
        "bump": "Opcional",
        "mechanism": "Método",
        "pains": "Dores (lista com ✕)",
        "agitation": "Fecho da seção",
        "bullets": "Pontos-chave (lista com ✓)",
    },
}


def _lines(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items)


def build_prompt(
    content: PageContent,
    brief: PageBrief,
    proofs: list[PageProof],
    template: Template,
    checkout_url: str | None,
) -> str:
    """El texto completo para pegar (o abrir) en Lovable."""
    L = LABELS[brief.market]  # noqa: N806
    c = content
    palette = template.palette
    chosen = {p.id: p for p in proofs}
    quotes = [chosen[i] for i in c.proof.proof_ids if i in chosen]
    link = safe_link(checkout_url)
    blurbs = c.deliverable_blurbs
    pieces = [
        f"- [{L[d.kind]}] {d.title}: {blurbs[i] if i < len(blurbs) else d.promise}"
        for i, d in enumerate(brief.deliverables)
    ]

    parts = [
        INTRO[brief.market],
        f"{L['design']}\n"
        f"- {L['colors']}: principal {palette.primary}, secundario {palette.secondary}, acento "
        f"{palette.accent}, fondo {palette.background}, superficie {palette.surface}, texto "
        f"{palette.text}.\n"
        f"- {L['fonts']}: {template.fonts.heading.family} ({L['heading']}), "
        f"{template.fonts.body.family} ({L['body']}).\n"
        f"- Bordes redondeados de {template.style.radius}.",
        f"{L['link']}: {link}" if link != "#oferta" else L["nolink"],
        L["sections"],
        f"{L['hero']}\n{c.hero.eyebrow}\n# {c.hero.headline}\n{c.hero.subheadline}\n"
        f"{L['bullets']}:\n{_lines(c.hero.bullets)}\n{L['button']}: {c.hero.cta_text}"
        + (f"\n{c.hero.microcopy}" if c.hero.microcopy else ""),
        f"{L['problem']}\n## {c.problem.title}\n{c.problem.intro}\n{L['pains']}:\n"
        f"{_lines(c.problem.pains)}\n{L['agitation']}: {c.problem.agitation}",
        f"{L['solution']}\n## {c.solution.title}\n{c.solution.intro}\n{L['mechanism']}: "
        f"{c.solution.mechanism_name}. {c.solution.mechanism}\n"
        + "\n".join(f"{n}. {s.title}: {s.text}" for n, s in enumerate(c.journey, 1)),
        f"{L['benefits']}\n" + "\n".join(f"- {b.title}: {b.text}" for b in c.benefits),
        f"{L['inside']}\n" + "\n".join(pieces),
        f"{L['fit']}\n{L['for_you']}\n{_lines(c.for_you)}\n{L['not_for_you']}\n{_lines(c.not_for_you)}",
    ]
    if c.about.strip():
        parts.append(f"{L['about']}\n{c.about}")
    if quotes:
        body = "\n".join(f"- «{q.text}»" + (f" — {q.author}" if q.author else "") for q in quotes)
        parts.append(f"{L['proof']}\n{c.proof.intro}\n{body}".rstrip())
    offer = [f"{L['offer']}\n## {c.offer.title}\n{c.offer.intro}"]
    if c.offer.price_text:
        offer.append(f"{L['price']}: {c.offer.price_text}")
    if c.offer.urgency:
        offer.append(f"{L['urgency']}: {c.offer.urgency}")
    if c.offer.guarantee:
        offer.append(f"{L['guarantee']}: {c.offer.guarantee}")
    offer.append(f"{L['button']}: {c.offer.cta_text}")
    parts.append("\n".join(offer))
    parts.append(f"{L['faq']}\n" + "\n".join(f"- {f.q}\n  {f.a}" for f in c.faq))
    parts.append(
        f"{L['final']}\n## {c.final_cta.headline}\n{c.final_cta.text}\n"
        f"{L['button']}: {c.final_cta.cta_text}"
    )
    parts.append(f"{L['disclaimer']}\n{c.disclaimer}")
    return "\n\n".join(parts)[:MAX_CHARS]
