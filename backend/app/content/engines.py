"""Motores de contenido: problemas, outline del paquete, piezas y ficha comercial.

Flujo de cada llamada: prompt versionado del mercado + datos del usuario delimitados →
salida estructurada validada con Pydantic → reglas de negocio. Si las reglas fallan,
se reintenta con los errores como feedback (máximo `max_attempts`).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel, ValidationError

from app.content import rules
from app.content.claude_client import CallUsage, LLMInvalidOutput, StructuredLLM
from app.content.prompts import PromptLibrary, wrap_user_data
from app.content.schemas import (
    FORMAT_SCHEMAS,
    AdaptedPackage,
    CommercialSheet,
    Format,
    ItemOutline,
    Market,
    PackageOutline,
    PackageRequest,
    Problem,
    ProblemProposals,
    SalesPageAnalysis,
    SalesReference,
    to_reference,
)
from app.content.schemas.common import BONUS_FORMATS, CURRENCY

T = TypeVar("T", bound=BaseModel)

FEEDBACK_INTRO: dict[str, str] = {
    "pt-BR": "Sua resposta anterior não cumpriu estas regras. Gere novamente corrigindo-as:",
    "es-LATAM": "Tu respuesta anterior no cumplió estas reglas. Genérala de nuevo corrigiéndolas:",
}


class UsageSink(Protocol):
    async def record(self, user_id: UUID, product_id: UUID | None, usage: CallUsage) -> None: ...


class ContentRejected(Exception):
    """La IA no cumplió las reglas tras todos los intentos."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class EngineConfig:
    model_outline: str
    model_content: str
    effort: str = "high"
    max_attempts: int = 3


@dataclass
class ContentService:
    llm: StructuredLLM
    prompts: PromptLibrary
    usage: UsageSink
    config: EngineConfig

    async def analyze_reference(
        self, *, user_id: UUID, market: Market, page: dict, source_url: str | None
    ) -> tuple[SalesReference, bool]:
        """Resume una página de ventas (texto de un tercero) en un `SalesReference`.

        El texto va como dato delimitado, nunca como instrucción; la salida se recorta a los
        límites duros del schema.
        """
        analysis = await self._call(
            user_id=user_id,
            product_id=None,
            market=market,
            task=self.prompts.render(market, "reference"),
            data={"page": page},
            schema=SalesPageAnalysis,
            model=self.config.model_outline,
            max_tokens=4_000,
            check=lambda _: [],
        )
        return to_reference(analysis, source_url), analysis.is_sales_page

    async def propose_problems(
        self,
        *,
        user_id: UUID,
        niche: str,
        market: Market,
        reference: SalesReference | None = None,
    ) -> list[Problem]:
        result = await self._call(
            user_id=user_id,
            product_id=None,
            market=market,
            task=self.prompts.render(market, "problems"),
            data={"niche": niche, **_reference_data(reference)},
            schema=ProblemProposals,
            model=self.config.model_outline,
            max_tokens=8_000,
            check=lambda r: [] if len(r.problems) == 5 else ["Devuelve exactamente 5 problemas."],
        )
        return result.problems

    async def build_outline(self, *, user_id: UUID, request: PackageRequest) -> PackageOutline:
        task = self.prompts.render(
            request.market,
            "outline",
            main_format=request.main_format.value,
            main_min_pages=rules.MAIN_PAGES[0],
            main_max_pages=rules.MAIN_PAGES[1],
            min_bumps=rules.MIN_ORDER_BUMPS,
            min_bonuses=rules.MIN_BONUSES,
            small_max_pages=rules.SMALL_MAX_PAGES,
            bonus_formats=", ".join(sorted(f.value for f in BONUS_FORMATS)),
            formats=", ".join(f.value for f in Format),
        )
        return await self._call(
            user_id=user_id,
            product_id=None,
            market=request.market,
            task=task,
            data=_request_data(request),
            schema=PackageOutline,
            model=self.config.model_outline,
            max_tokens=16_000,
            check=lambda outline: rules.check_package_rules(outline, request),
        )

    async def adapt_to_market(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
        source: PackageRequest,
        outline: PackageOutline,
        target: Market,
    ) -> AdaptedPackage:
        """Reescribe nicho, problema y outline para otro mercado (no es una traducción literal).

        El contenido de cada pieza se genera después, nativo, con el outline adaptado.
        """
        task = self.prompts.render(
            target,
            "adapt_market",
            main_min_pages=rules.MAIN_PAGES[0],
            main_max_pages=rules.MAIN_PAGES[1],
            small_max_pages=rules.SMALL_MAX_PAGES,
        )
        data = {
            "source_market": source.market,
            **_request_data(source),
            "outline": outline.model_dump(mode="json"),
        }

        def check(adapted: AdaptedPackage) -> list[str]:
            try:
                request = PackageRequest(
                    niche=adapted.niche,
                    problem=adapted.problem,
                    market=target,
                    main_format=source.main_format,
                )
            except ValidationError as exc:
                return [f"niche o problem inválidos: {exc.errors()[0]['msg']}"]
            return rules.check_package_rules(adapted.outline, request) + rules.check_adaptation(
                outline, adapted.outline
            )

        return await self._call(
            user_id=user_id,
            product_id=product_id,
            market=target,
            task=task,
            data=data,
            schema=AdaptedPackage,
            model=self.config.model_outline,
            max_tokens=16_000,
            check=check,
        )

    async def generate_item(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
        request: PackageRequest,
        outline: PackageOutline,
        item: ItemOutline,
    ) -> BaseModel:
        task = self.prompts.render(
            request.market,
            "item",
            target_pages=item.estimated_pages,
            format_guide=self.prompts.format_guide(request.market, item.format),
        )
        data = {
            **_request_data(request),
            "product_name": outline.product_name,
            "item": item.model_dump(mode="json"),
            "other_items": [
                {"title": o.title, "role": o.role, "format": o.format.value, "promise": o.promise}
                for o in outline.items()
                if o is not item
            ],
        }
        return await self._call(
            user_id=user_id,
            product_id=product_id,
            market=request.market,
            task=task,
            data=data,
            schema=FORMAT_SCHEMAS[item.format],
            model=self.config.model_content,
            max_tokens=64_000 if item.role == "main" else 32_000,
            check=rules.check_content_rules,
        )

    async def commercial_sheet(
        self, *, user_id: UUID, product_id: UUID, request: PackageRequest, outline: PackageOutline
    ) -> CommercialSheet:
        currency = CURRENCY[request.market]

        def check(sheet: CommercialSheet) -> list[str]:
            errors = []
            if sheet.currency != currency:
                errors.append(f"currency debe ser {currency}.")
            if len(sheet.alternative_names) != 3:
                errors.append("alternative_names debe tener exactamente 3 nombres.")
            if len(sheet.ad_hooks) != 3:
                errors.append("ad_hooks debe tener exactamente 3 hooks.")
            if len(sheet.order_bumps) != len(outline.order_bumps):
                errors.append(f"order_bumps debe tener {len(outline.order_bumps)} entradas.")
            if len(sheet.bonuses) != len(outline.bonuses):
                errors.append(f"bonuses debe tener {len(outline.bonuses)} entradas.")
            if sheet.main_price.min > sheet.main_price.max:
                errors.append("main_price.min no puede ser mayor que main_price.max.")
            return errors

        return await self._call(
            user_id=user_id,
            product_id=product_id,
            market=request.market,
            task=self.prompts.render(request.market, "commercial", currency=currency),
            data={**_request_data(request), "outline": outline.model_dump(mode="json")},
            schema=CommercialSheet,
            model=self.config.model_outline,
            max_tokens=8_000,
            check=check,
        )

    async def _call(
        self,
        *,
        user_id: UUID,
        product_id: UUID | None,
        market: Market,
        task: str,
        data: dict,
        schema: type[T],
        model: str,
        max_tokens: int,
        check: Callable[[T], list[str]],
        system: str | None = None,
    ) -> T:
        base_user = f"{task}\n\n{wrap_user_data(market, data)}"
        user = base_user
        errors: list[str] = []
        for _ in range(self.config.max_attempts):
            try:
                result, usage = await self.llm.structured(
                    system=system or self.prompts.system(market),
                    user=user,
                    schema=schema,
                    model=model,
                    max_tokens=max_tokens,
                    effort=self.config.effort,
                )
            except LLMInvalidOutput as exc:
                errors = [f"La salida no cumplió el schema: {exc}"]
            else:
                await self.usage.record(user_id, product_id, usage)
                errors = check(result)
                if not errors:
                    return result
            feedback = "\n".join(f"- {e}" for e in errors)
            user = f"{base_user}\n\n{FEEDBACK_INTRO[market]}\n{feedback}"
        raise ContentRejected(errors)


def _reference_data(reference: SalesReference | None) -> dict:
    """La referencia viaja dentro de los datos delimitados; la URL no le sirve a la IA."""
    if reference is None:
        return {}
    return {"sales_page_reference": reference.model_dump(exclude={"source_url"})}


def _request_data(request: PackageRequest) -> dict:
    return {
        "niche": request.niche,
        "problem": request.problem.model_dump(),
        "tone": request.tone,
        "audience_override": request.audience_override,
        **_reference_data(request.reference),
    }
