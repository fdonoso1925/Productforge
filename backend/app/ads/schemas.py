"""Schemas del módulo Creativos para Meta Ads.

Lo que devuelve la IA se valida aquí; las restricciones de negocio que el schema no expresa
(largos del copy, plantillas permitidas, ángulos disponibles) viven en `app.ads.rules` y se le
devuelven a la IA como feedback concreto, igual que en el motor de contenido.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.content.schemas import Market, SalesReference

# Plantillas de anuncio (las 12 del plan; la fase 3 implementa 4). `ad_templates/<id>/`.
TEMPLATE_IDS = (
    "headline_bold",
    "photo_headline",
    "product_mockup",
    "note",
    "text_post",
    "notification",
    "checklist",
    "before_after",
    "comparison",
    "question",
    "testimonial",
    "offer_stack",
)
Ratio = Literal["4x5", "9x16", "1x1"]
MetaCta = Literal["LEARN_MORE", "SHOP_NOW", "GET_OFFER", "DOWNLOAD", "SIGN_UP"]
PolicyStatus = Literal["green", "yellow", "red"]


class AdProof(BaseModel):
    """Prueba REAL cargada por el usuario (testimonio, cifra o experiencia). Nunca inventada."""

    id: str
    kind: Literal["testimonial", "stat", "authority"]
    text: str = Field(max_length=500)
    author: str | None = Field(default=None, max_length=80)


class AdBrief(BaseModel):
    """Los hechos del producto sobre los que se escriben los anuncios (copia del momento)."""

    market: Market
    niche: str = Field(min_length=2, max_length=120)
    product_name: str = Field(min_length=1, max_length=300)
    problem: str = Field(max_length=500)
    audience: str = Field(max_length=500)
    promise: str = Field(max_length=500)
    price_text: str = Field(default="", max_length=60)  # solo precio REAL; vacío = sin precio
    bonuses: list[str] = Field(default_factory=list, max_length=8)
    real_urgency: str = Field(
        default="", max_length=200
    )  # solo una urgencia REAL (fecha, lanzamiento)
    reference: SalesReference | None = None


class Avatar(BaseModel):
    name: str = Field(description="Etiqueta corta del avatar")
    situation: str = Field(description="Contexto y lo que ya intentó")
    pain: str = Field(description="Dolor principal, como lo diría esa persona")
    desire: str = Field(description="Lo que quiere lograr")
    objections: list[str] = Field(description="2 a 4 razones para dudar de comprar")
    language: list[str] = Field(description="3 a 6 expresiones que usaría")


class AvatarProposals(BaseModel):
    avatars: list[Avatar]


class AdaptedBrief(BaseModel):
    """El brief y los avatares reescritos (no traducidos) para otro mercado."""

    niche: str = Field(max_length=120)
    product_name: str = Field(max_length=300)
    problem: str = Field(max_length=500)
    audience: str = Field(max_length=500)
    promise: str = Field(max_length=500)
    bonuses: list[str] = Field(default_factory=list, max_length=8)
    avatars: list[Avatar]


class AngleSuggestion(BaseModel):
    angle_id: str
    avatar: str = Field(description="Nombre exacto de uno de los avatares")
    why: str = Field(description="Por qué funcionaría, en una frase")


class AngleProposals(BaseModel):
    angles: list[AngleSuggestion]


class ImageCopy(BaseModel):
    """Texto que va DENTRO de la imagen. Lo renderiza HTML, nunca la IA de imágenes."""

    headline: str
    subheadline: str = ""
    kicker: str = ""
    bullets: list[str] = Field(default_factory=list)
    cta_text: str = ""
    price_text: str = ""
    note: str = ""
    mark: Literal["check", "cross"] = "check"


class AdCopy(BaseModel):
    """Texto del anuncio en Ads Manager."""

    primary_short: str
    primary_long: str
    headline: str
    description: str
    cta: MetaCta = "LEARN_MORE"


class CreativeDraft(BaseModel):
    template_id: str
    variant_note: str = ""
    image: ImageCopy
    ad: AdCopy
    scene: str = ""
    stock_keywords: list[str] = Field(default_factory=list)
    proof_id: str | None = None


class CreativeDrafts(BaseModel):
    creatives: list[CreativeDraft]


class PolicyNote(BaseModel):
    rule: str
    text: str
    severity: Literal["yellow", "red"] = "yellow"


class PolicyVerdict(BaseModel):
    status: PolicyStatus
    notes: list[PolicyNote] = Field(default_factory=list)
    rewrite: str = ""


class PreScore(BaseModel):
    score: int = Field(ge=1, le=10)
    hook_clarity: int = Field(ge=1, le=10)
    specificity: int = Field(ge=1, le=10)
    avatar_relevance: int = Field(ge=1, le=10)
    visual_contrast: int = Field(ge=1, le=10)
    mobile_legibility: int = Field(ge=1, le=10)
    policy_risk: int = Field(ge=1, le=10)
    explanation: str
    improvement: str


class CreativeReview(BaseModel):
    index: int
    policy: PolicyVerdict
    score: PreScore


class CreativeReviews(BaseModel):
    reviews: list[CreativeReview]
