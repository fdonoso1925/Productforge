from collections.abc import Awaitable, Callable
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from app.auth import CurrentUser, get_current_user
from app.content.engines import ContentService
from app.content.prompts import PromptLibrary
from app.content.schemas import Market, PackageOutline, PackageRequest, Problem, SalesReference
from app.db.supabase import ProductRepo
from app.deps import get_content_service, get_product_repo, get_prompts
from app.generators.cover import ArtChoice
from app.security import ai_rate_limit
from app.web.extract import clean_pasted_text, extract_text
from app.web.safe_fetch import FetchedPage, FetchError, fetch_page

router = APIRouter()

User = Annotated[CurrentUser, Depends(get_current_user)]
Service = Annotated[ContentService, Depends(get_content_service)]


class ProblemsRequest(BaseModel):
    niche: str = Field(min_length=2, max_length=120)
    market: Market = "pt-BR"
    reference: SalesReference | None = None


class ProblemsResponse(BaseModel):
    problems: list[Problem]


class OutlineRequest(PackageRequest):
    template_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")
    # Estilo de arte de la portada; la imagen propia se agrega después, sobre el producto creado.
    cover_art: ArtChoice = "auto"


class OutlineResponse(BaseModel):
    product_id: UUID
    outline: PackageOutline


@router.post("/problems", dependencies=[Depends(ai_rate_limit)])
async def propose_problems(body: ProblemsRequest, user: User, service: Service) -> ProblemsResponse:
    problems = await service.propose_problems(
        user_id=user.id, niche=body.niche, market=body.market, reference=body.reference
    )
    return ProblemsResponse(problems=problems)


@router.post("/outline", dependencies=[Depends(ai_rate_limit)])
async def build_outline(
    body: OutlineRequest,
    user: User,
    service: Service,
    products: Annotated[ProductRepo, Depends(get_product_repo)],
    prompts: Annotated[PromptLibrary, Depends(get_prompts)],
) -> OutlineResponse:
    request = PackageRequest.model_validate(body.model_dump(exclude={"template_id", "cover_art"}))
    outline = await service.build_outline(user_id=user.id, request=request)
    product_id = await products.create_with_outline(
        user_id=user.id,
        request=request,
        template_id=body.template_id,
        outline=outline,
        prompt_version=prompts.version,
        cover={"art": body.cover_art, "image_id": None},
    )
    return OutlineResponse(product_id=product_id, outline=outline)


# ───────────────────────── página de ventas de referencia ─────────────────────────

PageFetcher = Callable[[str], Awaitable[FetchedPage]]


def get_page_fetcher() -> PageFetcher:
    return fetch_page


class ReferenceRequest(BaseModel):
    """Una URL (se lee desde el servidor) o el texto pegado a mano, uno de los dos."""

    market: Market = "pt-BR"
    url: str | None = Field(default=None, max_length=2000)
    text: str | None = Field(default=None, max_length=30_000)

    @model_validator(mode="after")
    def _one_source(self) -> "ReferenceRequest":
        if bool(self.url and self.url.strip()) == bool(self.text and self.text.strip()):
            raise ValueError("indica la URL o pega el texto de la página, no ambos")
        return self


class ReferencePage(BaseModel):
    title: str
    chars: int
    truncated: bool
    source: Literal["url", "text"]


class ReferenceResponse(BaseModel):
    reference: SalesReference
    page: ReferencePage
    # false: la IA no vio una oferta o un tema concreto en el texto (conviene avisar al usuario).
    looks_like_sales_page: bool


def public_url(url: str) -> str:
    """Solo origen y ruta: la query y el fragmento pueden traer tokens y no aportan."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"[:2000]


@router.post("/reference", dependencies=[Depends(ai_rate_limit)])
async def analyze_reference(
    body: ReferenceRequest,
    user: User,
    service: Service,
    fetch: Annotated[PageFetcher, Depends(get_page_fetcher)],
) -> ReferenceResponse:
    """Lee una página de ventas y la resume como inspiración (lo generado es original)."""
    if body.url:
        try:
            fetched = await fetch(body.url)
        except FetchError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        page = extract_text(fetched.html, truncated=fetched.truncated)
        source_url, source = public_url(fetched.url), "url"
        if page.is_thin:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "la página casi no tiene texto legible (es probable que se arme con JavaScript): "
                "copia y pega su texto",
            )
    else:
        page = clean_pasted_text(body.text or "")
        source_url, source = None, "text"
        if page.is_thin:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "el texto es muy corto para analizarlo"
            )
    payload = {
        "title": page.title,
        "description": page.description,
        "offers": page.offers,
        "text": page.text,
    }
    reference, is_sales = await service.analyze_reference(
        user_id=user.id, market=body.market, page=payload, source_url=source_url
    )
    return ReferenceResponse(
        reference=reference,
        page=ReferencePage(
            title=page.title,
            chars=len(page.text),
            truncated=page.truncated,
            source=source,  # type: ignore[arg-type]
        ),
        looks_like_sales_page=is_sales,
    )
