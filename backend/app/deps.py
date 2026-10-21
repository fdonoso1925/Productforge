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
from app.db.supabase import (
    ConnectionRepo,
    FileRepo,
    ItemRepo,
    JobRepo,
    ProductRepo,
    SupabaseRest,
    UsageRepo,
)
from app.pipeline.generate import PipelineDeps
from app.pipeline.uploads import UploadQueue
from app.storage.crypto import TokenCipher
from app.storage.onedrive import OneDrive, OneDriveConfig
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
    onedrive: OneDrive
    upload_queue: UploadQueue

    def pipeline(self) -> PipelineDeps:
        return PipelineDeps(
            content=self.content,
            products=self.products,
            items=self.items,
            files=self.files,
            jobs=self.jobs,
            storage=self.storage,
            templates_dir=self.settings.templates_dir,
            sync_target=self.onedrive,
            uploads=self.upload_queue,
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
    files, jobs = FileRepo(db), JobRepo(db)
    onedrive = OneDrive(
        OneDriveConfig(
            client_id=settings.ms_client_id,
            client_secret=settings.ms_client_secret,
            tenant=settings.ms_tenant,
            redirect_uri=settings.ms_redirect_uri,
        ),
        ConnectionRepo(db),
        TokenCipher(settings.token_encryption_key) if settings.token_encryption_key else None,
    )
    return Services(
        settings=settings,
        prompts=prompts,
        content=content,
        products=ProductRepo(db),
        items=ItemRepo(db),
        files=files,
        jobs=jobs,
        storage=SupabaseStorage(settings.supabase_url, settings.supabase_service_role_key),
        onedrive=onedrive,
        upload_queue=UploadQueue(onedrive, jobs, files),
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
