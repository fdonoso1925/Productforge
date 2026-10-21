from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth import CurrentUser, get_current_user
from app.content.engines import ContentService
from app.content.prompts import PromptLibrary
from app.content.schemas import Market, PackageOutline, PackageRequest, Problem
from app.db.supabase import ProductRepo
from app.deps import get_content_service, get_product_repo, get_prompts
from app.security import ai_rate_limit

router = APIRouter()

User = Annotated[CurrentUser, Depends(get_current_user)]
Service = Annotated[ContentService, Depends(get_content_service)]


class ProblemsRequest(BaseModel):
    niche: str = Field(min_length=2, max_length=120)
    market: Market = "pt-BR"


class ProblemsResponse(BaseModel):
    problems: list[Problem]


class OutlineRequest(PackageRequest):
    template_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")


class OutlineResponse(BaseModel):
    product_id: UUID
    outline: PackageOutline


@router.post("/problems", dependencies=[Depends(ai_rate_limit)])
async def propose_problems(body: ProblemsRequest, user: User, service: Service) -> ProblemsResponse:
    problems = await service.propose_problems(user_id=user.id, niche=body.niche, market=body.market)
    return ProblemsResponse(problems=problems)


@router.post("/outline", dependencies=[Depends(ai_rate_limit)])
async def build_outline(
    body: OutlineRequest,
    user: User,
    service: Service,
    products: Annotated[ProductRepo, Depends(get_product_repo)],
    prompts: Annotated[PromptLibrary, Depends(get_prompts)],
) -> OutlineResponse:
    request = PackageRequest.model_validate(body.model_dump(exclude={"template_id"}))
    outline = await service.build_outline(user_id=user.id, request=request)
    product_id = await products.create_with_outline(
        user_id=user.id,
        request=request,
        template_id=body.template_id,
        outline=outline,
        prompt_version=prompts.version,
    )
    return OutlineResponse(product_id=product_id, outline=outline)
