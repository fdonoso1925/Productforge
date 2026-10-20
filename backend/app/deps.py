"""Construcción de servicios compartidos (API y worker) e inyección en FastAPI.

En tests se reemplazan con `app.dependency_overrides`.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.content.claude_client import ClaudeClient
from app.content.engines import ContentService, EngineConfig
from app.content.prompts import PromptLibrary
from app.db.supabase import FileRepo, ItemRepo, JobRepo, ProductRepo, SupabaseRest, UsageRepo
from app.pipeline.generate import PipelineDeps
from app.storage.supabase_storage import SupabaseStorage


@dataclass(frozen=True)
class Services:
    settings: Settings
    prompts: PromptLibrary
    content: ContentService
    products: ProductRepo
    items: ItemRepo
    files: FileRepo
    jobs: JobRepo
    storage: SupabaseStorage

    def pipeline(self) -> PipelineDeps:
        return PipelineDeps(
            content=self.content,
            products=self.products,
            items=self.items,
            files=self.files,
            jobs=self.jobs,
            storage=self.storage,
            templates_dir=self.settings.templates_dir,
        )


def build_services(settings: Settings) -> Services:
    db = SupabaseRest(settings.supabase_url, settings.supabase_service_role_key)
    prompts = PromptLibrary(settings.prompts_dir)
    content = ContentService(
        llm=ClaudeClient(settings.anthropic_api_key),
        prompts=prompts,
        usage=UsageRepo(db),
        config=EngineConfig(
            model_outline=settings.claude_model_outline,
            model_content=settings.claude_model_content,
            effort=settings.claude_effort,
        ),
    )
    return Services(
        settings=settings,
        prompts=prompts,
        content=content,
        products=ProductRepo(db),
        items=ItemRepo(db),
        files=FileRepo(db),
        jobs=JobRepo(db),
        storage=SupabaseStorage(settings.supabase_url, settings.supabase_service_role_key),
    )


@lru_cache
def get_services() -> Services:
    return build_services(get_settings())


ServicesDep = Annotated[Services, Depends(get_services)]


def get_prompts(settings: Annotated[Settings, Depends(get_settings)]) -> PromptLibrary:
    return PromptLibrary(settings.prompts_dir)


def get_content_service(services: ServicesDep) -> ContentService:
    return services.content


def get_product_repo(services: ServicesDep) -> ProductRepo:
    return services.products
