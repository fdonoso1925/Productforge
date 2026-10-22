"""Construcción de servicios compartidos (API y worker) e inyección en FastAPI.

En tests se reemplazan con `app.dependency_overrides`.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.ads.images.router import ImageRouter, build_router
from app.ads.jobs import AdDeps
from app.ads.render import AdRenderer
from app.ads.repo import (
    AdBatchRepo,
    AdCreativeRepo,
    AdImageCacheRepo,
    AdProofRepo,
    ProviderUsageRepo,
)
from app.ads.strategy import AdStrategyService
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
from app.storage.google_drive import GoogleConfig, GoogleDrive
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
    drive: GoogleDrive
    upload_queue: UploadQueue
    ad_strategy: AdStrategyService
    ad_renderer: AdRenderer
    ad_batches: AdBatchRepo
    ad_creatives: AdCreativeRepo
    ad_proofs: AdProofRepo
    ad_images: ImageRouter

    def ads(self) -> AdDeps:
        return AdDeps(
            strategy=self.ad_strategy,
            renderer=self.ad_renderer,
            batches=self.ad_batches,
            creatives=self.ad_creatives,
            proofs=self.ad_proofs,
            jobs=self.jobs,
            storage=self.storage,
            templates_dir=self.settings.templates_dir,
            images=self.ad_images,
        )

    def pipeline(self) -> PipelineDeps:
        return PipelineDeps(
            content=self.content,
            products=self.products,
            items=self.items,
            files=self.files,
            jobs=self.jobs,
            storage=self.storage,
            templates_dir=self.settings.templates_dir,
            sync_target=self.drive,
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
    drive = GoogleDrive(
        GoogleConfig(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=settings.google_redirect_uri,
        ),
        ConnectionRepo(db),
        TokenCipher(settings.token_encryption_key) if settings.token_encryption_key else None,
    )
    storage = SupabaseStorage(settings.supabase_url, settings.supabase_service_role_key)
    return Services(
        settings=settings,
        prompts=prompts,
        content=content,
        products=ProductRepo(db),
        items=ItemRepo(db),
        files=files,
        jobs=jobs,
        storage=storage,
        drive=drive,
        upload_queue=UploadQueue(drive, jobs, files),
        ad_strategy=AdStrategyService(content),
        ad_renderer=AdRenderer(settings.ad_templates_dir, settings.templates_dir),
        ad_batches=AdBatchRepo(db),
        ad_creatives=AdCreativeRepo(db),
        ad_proofs=AdProofRepo(db),
        ad_images=build_router(settings, AdImageCacheRepo(db), ProviderUsageRepo(db), storage),
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
