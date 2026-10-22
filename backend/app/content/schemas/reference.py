"""Referencia de una página de ventas: lo que la IA entendió de ella, no la página.

La página es texto de un tercero (no confiable y con derechos de autor). De ella solo se guarda un
resumen estructurado —público, dolores, promesa, tono, ángulo de venta— que sirve de INSPIRACIÓN:
el contenido que se genera es original. Los límites de `SalesReference` son duros porque el
cliente puede devolverla (al pedir problemas o crear el paquete) y entra a los prompts.
"""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=250)]
Medium = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class SalesPageAnalysis(BaseModel):
    """Lo que devuelve la IA al leer el texto de una página. Sin límites duros: se recortan."""

    is_sales_page: bool = Field(
        description="false si el texto no es una página que promocione una oferta o un tema"
    )
    niche_hint: str = Field(description="El nicho en pocas palabras (p. ej. «finanzas personales»)")
    product_name: str = Field(description="Nombre del producto o programa que promocionan")
    audience: str = Field(description="A quién le hablan: quién es y en qué situación está")
    main_pain: str = Field(description="El dolor o problema principal que prometen resolver")
    pains: list[str] = Field(description="Dolores y frustraciones que menciona, con sus palabras")
    promise: str = Field(description="El resultado que prometen y en cuánto tiempo")
    benefits: list[str] = Field(description="Beneficios o resultados concretos que enumeran")
    objections: list[str] = Field(description="Objeciones que la página intenta eliminar")
    price_text: str = Field(description="Precio u oferta que declara; vacío si no lo dice")
    guarantee: str = Field(description="Garantía que ofrece; vacío si no hay")
    bonuses: list[str] = Field(description="Bonus o extras que incluye, si los hay")
    tone: str = Field(description="Tono y estilo: formal, cercano, urgente, técnico…")
    angle: str = Field(description="El enfoque o gancho de venta, en una frase")
    key_terms: list[str] = Field(description="Palabras y expresiones propias del público")


class SalesReference(BaseModel):
    source_url: str | None = Field(default=None, max_length=2000)
    niche_hint: Short = ""
    product_name: Short = ""
    audience: Medium = ""
    main_pain: Medium = ""
    pains: list[Short] = Field(default_factory=list, max_length=8)
    promise: Medium = ""
    benefits: list[Short] = Field(default_factory=list, max_length=8)
    objections: list[Short] = Field(default_factory=list, max_length=6)
    price_text: Short = ""
    guarantee: Short = ""
    bonuses: list[Short] = Field(default_factory=list, max_length=6)
    tone: Short = ""
    angle: Medium = ""
    key_terms: list[Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]] = (
        Field(default_factory=list, max_length=12)
    )


def _text(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _items(values: object, count: int, limit: int) -> list[str]:
    out = [_text(v, limit) for v in (values if isinstance(values, list) else [])]
    return [v for v in out if v][:count]


def to_reference(analysis: SalesPageAnalysis, source_url: str | None) -> SalesReference:
    """Recorta lo que devolvió la IA a los límites duros (nunca falla por largo)."""
    return SalesReference(
        source_url=source_url,
        niche_hint=_text(analysis.niche_hint, 250),
        product_name=_text(analysis.product_name, 250),
        audience=_text(analysis.audience, 500),
        main_pain=_text(analysis.main_pain, 500),
        pains=_items(analysis.pains, 8, 250),
        promise=_text(analysis.promise, 500),
        benefits=_items(analysis.benefits, 8, 250),
        objections=_items(analysis.objections, 6, 250),
        price_text=_text(analysis.price_text, 250),
        guarantee=_text(analysis.guarantee, 250),
        bonuses=_items(analysis.bonuses, 6, 250),
        tone=_text(analysis.tone, 250),
        angle=_text(analysis.angle, 500),
        key_terms=_items(analysis.key_terms, 12, 60),
    )
