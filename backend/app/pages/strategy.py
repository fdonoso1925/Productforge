"""Motor de la página de ventas: analiza una página modelo y escribe la nuestra.

Reutiliza `ContentService._call` (salida validada con Pydantic, reintento con los errores como
feedback, costo en `ai_usage`) con el system prompt propio de `prompts/<mercado>/pages/`. El texto
de la página ajena y los datos del usuario viajan como dato delimitado, nunca como instrucción.
"""

from dataclasses import dataclass
from uuid import UUID

from app.ads import rules as ad_rules
from app.content.engines import ContentService
from app.content.schemas import Market
from app.pages import rules, similarity
from app.pages.schemas import (
    PageBrief,
    PageContent,
    PageProof,
    PageReference,
    PageTeardownAnalysis,
    SimilarityReport,
    to_reference,
)

MAX_TOKENS = 16_000
# En el último intento el parecido deja de ser motivo de rechazo: el informe llega al usuario.
SIMILARITY_ATTEMPTS = 2


def brief_data(brief: PageBrief) -> dict:
    data = brief.model_dump(exclude={"market"})
    return {k: v for k, v in data.items() if v not in ("", [], None)}


def revalidate(
    content: PageContent,
    brief: PageBrief,
    proofs: list[PageProof],
    known: list[int] | None,
    brands: list[str],
) -> tuple[list[str], SimilarityReport]:
    """Reglas de honestidad y parecido con la página modelo, sin IA (generación y edición)."""
    blank = content.offer.model_copy(update={"price_text": "", "guarantee": "", "urgency": ""})
    errors = rules.check_content(content.model_copy(update={"offer": blank}), brief, proofs)
    report = similarity.check(
        content, known or [], brands, own_text=f"{brief.product_name} {brief.niche}"
    )
    return errors, report


def similarity_errors(report: SimilarityReport) -> list[str]:
    if report.level != "block":
        return []
    where = ", ".join(f.path for f in report.fields[:5]) or "varias secciones"
    out = [
        f"El texto se parece demasiado a la página modelo ({where}). Reescríbelo desde cero con "
        "otras palabras y otra estructura de frases; no sigas sus frases."
    ]
    if report.brands:
        out.append(f"No uses estos nombres de la página modelo: {', '.join(report.brands)}.")
    return out


@dataclass
class PageService:
    content: ContentService

    async def teardown(
        self, *, user_id: UUID, market: Market, page: dict, source_url: str | None
    ) -> tuple[PageReference, bool]:
        analysis = await self.content._call(
            user_id=user_id,
            product_id=None,
            market=market,
            task=self.content.prompts.render(market, "pages/teardown"),
            data={"page": page},
            schema=PageTeardownAnalysis,
            model=self.content.config.model_outline,
            max_tokens=6_000,
            check=lambda _: [],
            system=self.content.prompts.pages_system(market),
        )
        return to_reference(analysis, source_url), analysis.is_sales_page

    def angles(self, brief: PageBrief, proofs: list[PageProof]) -> dict[str, dict]:
        library = self.content.prompts.angle_library(brief.market)
        available = ad_rules.available_angles(
            library,
            has_proofs=bool(proofs),
            has_price=bool(brief.price_text.strip()),
            real_urgency=bool(brief.real_urgency.strip()),
        )
        keep = ("name", "description", "when")
        return {i: {k: v for k, v in a.items() if k in keep} for i, a in available.items()}

    async def write(
        self,
        *,
        user_id: UUID,
        brief: PageBrief,
        proofs: list[PageProof],
        reference: PageReference | None = None,
        known: list[int] | None = None,
    ) -> tuple[PageContent, SimilarityReport]:
        brands = reference.brand_terms if reference else []
        attempts = 0

        def check(result: PageContent) -> list[str]:
            nonlocal attempts
            attempts += 1
            errors, report = revalidate(result, brief, proofs, known, brands)
            if attempts <= SIMILARITY_ATTEMPTS:
                errors += similarity_errors(report)
            return errors

        data: dict = {
            "brief": brief_data(brief),
            "angles": self.angles(brief, proofs),
            "proofs": [p.model_dump(exclude_none=True) for p in proofs],
        }
        if reference is not None:
            data["reference_teardown"] = reference.model_dump(exclude={"source_url"})
        written = await self.content._call(
            user_id=user_id,
            product_id=None,
            market=brief.market,
            task=self.content.prompts.render(brief.market, "pages/page"),
            data=data,
            schema=PageContent,
            model=self.content.config.model_content,
            max_tokens=MAX_TOKENS,
            check=check,
            system=self.content.prompts.pages_system(brief.market),
        )
        final = rules.finalize(written, brief, proofs)
        _, report = revalidate(final, brief, proofs, known, brands)
        return final, report
