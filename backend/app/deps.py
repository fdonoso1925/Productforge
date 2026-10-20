"""Dependencias compartidas (inyectables y reemplazables en tests)."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.content.claude_client import ClaudeClient
from app.content.engines import ContentService, EngineConfig
from app.content.prompts import PromptLibrary
from app.db.supabase import ProductRepo, SupabaseRest, UsageRepo


@lru_cache
def _db(url: str, key: str) -> SupabaseRest:
    return SupabaseRest(url, key)


@lru_cache
def _claude(api_key: str) -> ClaudeClient:
    return ClaudeClient(api_key)


def get_db(settings: Annotated[Settings, Depends(get_settings)]) -> SupabaseRest:
    return _db(settings.supabase_url, settings.supabase_service_role_key)


def get_prompts(settings: Annotated[Settings, Depends(get_settings)]) -> PromptLibrary:
    return PromptLibrary(settings.prompts_dir)


def get_product_repo(db: Annotated[SupabaseRest, Depends(get_db)]) -> ProductRepo:
    return ProductRepo(db)


def get_content_service(
    settings: Annotated[Settings, Depends(get_settings)],
    prompts: Annotated[PromptLibrary, Depends(get_prompts)],
    db: Annotated[SupabaseRest, Depends(get_db)],
) -> ContentService:
    return ContentService(
        llm=_claude(settings.anthropic_api_key),
        prompts=prompts,
        usage=UsageRepo(db),
        config=EngineConfig(
            model_outline=settings.claude_model_outline,
            model_content=settings.claude_model_content,
            effort=settings.claude_effort,
        ),
    )
