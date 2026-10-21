"""Schemas del paquete: problema, outline y ficha comercial.

Las restricciones de negocio que cruzan piezas (formatos distintos, cantidades) se
verifican en `app.content.rules`, no aquí: así el schema que ve la IA queda simple y
el error se le devuelve como feedback concreto.
"""

from pydantic import BaseModel, Field

from app.content.schemas.common import Format, Market, Role


class Problem(BaseModel):
    title: str = Field(description="Problema puntual y específico, no un tema amplio")
    audience: str = Field(description="Público exacto")
    pain: str = Field(description="Dolor principal")
    promised_result: str = Field(description="Resultado prometido, concreto y medible")
    timeframe: str = Field(description="Plazo para lograr el resultado")
    why_pay: str = Field(description="Por qué alguien pagaría por esto")
    urgency: int = Field(ge=1, le=5, description="Nivel de urgencia de 1 a 5")


class ProblemProposals(BaseModel):
    problems: list[Problem]


class PackageRequest(BaseModel):
    """Lo que el usuario eligió en el wizard. Campos libres con límite de longitud."""

    niche: str = Field(min_length=2, max_length=120)
    problem: Problem
    market: Market = "pt-BR"
    main_format: Format
    tone: str | None = Field(default=None, max_length=200)
    audience_override: str | None = Field(default=None, max_length=300)


class ItemOutline(BaseModel):
    role: Role
    format: Format
    title: str
    promise: str = Field(
        description="Qué problema concreto resuelve y en cuánto tiempo, en una frase"
    )
    objection_addressed: str | None = Field(
        default=None, description="Solo bonus: la objeción que elimina"
    )
    table_of_contents: list[str] = Field(description="Índice: secciones o bloques en orden")
    estimated_pages: int = Field(ge=1, le=60)
    related_items: list[str] = Field(
        default_factory=list, description="Títulos de otras piezas del paquete que esta cita"
    )


class PackageOutline(BaseModel):
    product_name: str
    main: ItemOutline
    order_bumps: list[ItemOutline]
    bonuses: list[ItemOutline]

    def items(self) -> list[ItemOutline]:
        return [self.main, *self.order_bumps, *self.bonuses]


class PriceRange(BaseModel):
    min: float
    max: float


class BumpOffer(BaseModel):
    title: str
    price: float
    checkout_text: str = Field(description="Texto del order bump en el checkout")


class BonusValue(BaseModel):
    title: str
    perceived_value: float


class CommercialSheet(BaseModel):
    product_name: str
    alternative_names: list[str] = Field(description="Exactamente 3 alternativas")
    headline: str
    subheadline: str
    currency: str
    main_price: PriceRange
    order_bumps: list[BumpOffer]
    bonuses: list[BonusValue]
    short_description: str = Field(description="Descripción corta para Hotmart / Kiwify")
    benefit_bullets: list[str]
    ad_hooks: list[str] = Field(description="Exactamente 3 hooks para anuncios")


class AdaptedPackage(BaseModel):
    """Paquete adaptado (no traducido) a otro mercado: nicho, problema y outline."""

    niche: str = Field(description="Nombre del nicho en el idioma del mercado destino")
    problem: Problem
    outline: PackageOutline
