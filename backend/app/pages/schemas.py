"""Esquemas de la página de ventas.

Tres grupos:
- `PageBrief`: los hechos que el usuario controla (producto, público, precio, garantía, urgencia).
  Precio, garantía y urgencia solo existen si el usuario las da: la IA no las inventa y el
  código las pone en la oferta con sus palabras, no con las de la IA.
- `PageTeardown` / `PageReference`: lo que la IA entendió de OTRA página (estructura, qué hace bien,
  dónde pierde ventas). Nunca el texto de esa página.
- `PageContent`: los textos de cada sección que devuelve la IA y que el usuario puede editar.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.content.schemas import Market

Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=250)]
Medium = Annotated[str, StringConstraints(strip_whitespace=True, max_length=600)]

# ───────────────────────────── brief ─────────────────────────────


class Deliverable(BaseModel):
    """Una pieza del paquete que la página presenta (el principal, un bonus o un order bump)."""

    kind: Literal["main", "bonus", "bump"]
    title: str = Field(max_length=300)
    promise: str = Field(default="", max_length=500)
    format: str = Field(default="", max_length=40)
    contents: list[Annotated[str, Field(max_length=200)]] = Field(
        default_factory=list, max_length=12
    )


class PageProof(BaseModel):
    id: str
    kind: Literal["testimonial", "stat", "authority"]
    text: str
    author: str | None = None


class PageBrief(BaseModel):
    market: Market
    niche: str = Field(min_length=2, max_length=120)
    product_name: str = Field(min_length=1, max_length=300)
    problem: str = Field(max_length=500)
    audience: str = Field(max_length=500)
    pain: str = Field(default="", max_length=500)
    promise: str = Field(max_length=500)
    timeframe: str = Field(default="", max_length=200)
    why_pay: str = Field(default="", max_length=500)
    deliverables: list[Deliverable] = Field(default_factory=list, max_length=12)
    # Solo lo que el usuario da; vacío = la página no lo menciona.
    price_text: str = Field(default="", max_length=60)
    guarantee_text: str = Field(default="", max_length=300)
    real_urgency: str = Field(default="", max_length=200)
    about_author: str = Field(default="", max_length=600)
    tone: str = Field(default="", max_length=200)


# ───────────────────────────── análisis de otra página ─────────────────────────────


class SectionObservation(BaseModel):
    kind: str = Field(
        description="Tipo: hero, problema, solución, beneficios, prueba, oferta, faq…"
    )
    purpose: str = Field(description="Qué intenta lograr esa sección, en una frase")


class PageTeardownAnalysis(BaseModel):
    """Lo que devuelve la IA. Sin límites duros: se recortan en `to_reference`."""

    is_sales_page: bool
    brand_terms: list[str] = Field(
        description="Nombres propios de la marca, del producto y de las personas de esa página"
    )
    audience: str
    main_pain: str
    promise: str
    structure: list[SectionObservation] = Field(description="Secciones en el orden en que aparecen")
    offer_summary: str = Field(description="Cómo arma la oferta (qué incluye, precio, garantía)")
    proof_types: list[str] = Field(description="Tipos de prueba que usa (testimonios, cifras…)")
    persuasion: list[str] = Field(description="Técnicas de persuasión que usa")
    tone: str
    angle: str = Field(description="El gancho de venta principal en una frase")
    strengths: list[str] = Field(description="Lo que hace bien y conviene igualar")
    weaknesses: list[str] = Field(description="Dónde pierde ventas: vacíos, confusión, exageración")
    missing: list[str] = Field(description="Lo que no tiene y una página que convierte sí tendría")
    key_terms: list[str] = Field(description="Palabras propias del público (no de la marca)")


class PageReference(BaseModel):
    """El análisis recortado a límites duros; viaja de ida y vuelta por el cliente."""

    source_url: str | None = Field(default=None, max_length=2000)
    brand_terms: list[Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)]] = (
        Field(default_factory=list, max_length=20)
    )
    audience: Medium = ""
    main_pain: Medium = ""
    promise: Medium = ""
    structure: list[SectionObservation] = Field(default_factory=list, max_length=20)
    offer_summary: Medium = ""
    proof_types: list[Short] = Field(default_factory=list, max_length=8)
    persuasion: list[Short] = Field(default_factory=list, max_length=10)
    tone: Short = ""
    angle: Medium = ""
    strengths: list[Short] = Field(default_factory=list, max_length=8)
    weaknesses: list[Short] = Field(default_factory=list, max_length=10)
    missing: list[Short] = Field(default_factory=list, max_length=10)
    key_terms: list[Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]] = (
        Field(default_factory=list, max_length=12)
    )


def _text(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _items(values: object, count: int, limit: int) -> list[str]:
    out = [_text(v, limit) for v in (values if isinstance(values, list) else [])]
    return [v for v in out if v][:count]


def to_reference(analysis: PageTeardownAnalysis, source_url: str | None) -> PageReference:
    return PageReference(
        source_url=source_url,
        brand_terms=_items(analysis.brand_terms, 20, 80),
        audience=_text(analysis.audience, 600),
        main_pain=_text(analysis.main_pain, 600),
        promise=_text(analysis.promise, 600),
        structure=[
            SectionObservation(kind=_text(s.kind, 60), purpose=_text(s.purpose, 250))
            for s in analysis.structure[:20]
        ],
        offer_summary=_text(analysis.offer_summary, 600),
        proof_types=_items(analysis.proof_types, 8, 250),
        persuasion=_items(analysis.persuasion, 10, 250),
        tone=_text(analysis.tone, 250),
        angle=_text(analysis.angle, 600),
        strengths=_items(analysis.strengths, 8, 250),
        weaknesses=_items(analysis.weaknesses, 10, 250),
        missing=_items(analysis.missing, 10, 250),
        key_terms=_items(analysis.key_terms, 12, 60),
    )


# ───────────────────────────── contenido de la página ─────────────────────────────


class Hero(BaseModel):
    eyebrow: str = Field(description="Línea corta sobre el título: para quién es")
    headline: str = Field(description="Promesa principal, concreta y creíble")
    subheadline: str = Field(description="Cómo se logra y en cuánto tiempo, sin exagerar")
    bullets: list[str] = Field(description="3 beneficios clave, en una línea cada uno")
    cta_text: str = Field(description="Texto del botón principal")
    microcopy: str = Field(default="", description="Línea bajo el botón, solo con hechos reales")


class Problem(BaseModel):
    title: str
    intro: str = Field(description="Describe la situación del público con sus palabras")
    pains: list[str] = Field(description="3 a 6 dolores concretos, como los diría el público")
    agitation: str = Field(description="Qué pasa si sigue igual; honesto, sin dramatizar")


class Solution(BaseModel):
    title: str
    intro: str
    mechanism_name: str = Field(description="Nombre corto del método o enfoque")
    mechanism: str = Field(description="Cómo funciona y por qué es distinto a lo que ya intentó")


class Benefit(BaseModel):
    title: str
    text: str


class Step(BaseModel):
    title: str
    text: str


class Faq(BaseModel):
    q: str
    a: str


class ProofBlock(BaseModel):
    """Solo ids de pruebas reales del usuario: el texto sale de ellas, nunca de la IA."""

    intro: str = ""
    proof_ids: list[str] = Field(default_factory=list)


class OfferBlock(BaseModel):
    title: str
    intro: str
    cta_text: str
    # Los rellena el código con lo que dio el usuario (la IA los deja vacíos).
    price_text: str = ""
    guarantee: str = ""
    urgency: str = ""


class FinalCta(BaseModel):
    headline: str
    text: str
    cta_text: str


class PageContent(BaseModel):
    seo_title: str = Field(description="Título para buscadores, hasta 60 caracteres")
    seo_description: str = Field(description="Descripción, hasta 160 caracteres")
    hero: Hero
    problem: Problem
    solution: Solution
    journey: list[Step] = Field(
        description="3 a 5 etapas del camino de la situación actual al resultado"
    )
    benefits: list[Benefit] = Field(description="4 a 6 beneficios con su porqué")
    deliverable_blurbs: list[str] = Field(
        description="Una frase de valor por cada pieza de `deliverables`, en el mismo orden"
    )
    for_you: list[str] = Field(description="3 a 6 señales de que es para esta persona")
    not_for_you: list[str] = Field(description="2 a 4 casos en que NO es para ella")
    about: str = Field(
        default="", description="Sobre quien creó el producto; vacío si no hay datos"
    )
    proof: ProofBlock = Field(default_factory=ProofBlock)
    offer: OfferBlock
    faq: list[Faq] = Field(description="5 a 8 preguntas que eliminan objeciones reales")
    final_cta: FinalCta
    disclaimer: str = Field(description="Aviso honesto: los resultados dependen de la aplicación")


# ───────────────────────────── informe de parecido ─────────────────────────────

Level = Literal["ok", "warn", "block"]


class SimilarityField(BaseModel):
    path: str
    ratio: float
    run_words: int


class SimilarityReport(BaseModel):
    level: Level = "ok"
    ratio: float = 0.0
    longest_run_words: int = 0
    fields: list[SimilarityField] = Field(default_factory=list)
    brands: list[str] = Field(default_factory=list)
