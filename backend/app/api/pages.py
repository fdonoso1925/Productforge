"""Páginas de ventas: crear desde un paquete (o a mano), modelar otra página sin copiarla, editar,
revisar el parecido y exportar el HTML."""

from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote, urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.ads import JobOut, unprocessable
from app.api.content import (
    FetchError,
    PageFetcher,
    ReferencePage,
    ReferenceRequest,
    get_page_fetcher,
    public_url,
)
from app.api.products import owned_product
from app.auth import CurrentUser, get_current_user
from app.content.schemas import Market
from app.db.supabase import NotFound
from app.deps import ServicesDep
from app.pages import lovable, similarity
from app.pages.render import render_page
from app.pages.schemas import (
    Deliverable,
    PageBrief,
    PageContent,
    PageProof,
    PageReference,
    SimilarityReport,
)
from app.pages.strategy import revalidate
from app.security import ai_rate_limit, work_rate_limit
from app.templates_engine.model import load_template
from app.web.extract import clean_pasted_text, extract_text

router = APIRouter(prefix="/pages")
User = Annotated[CurrentUser, Depends(get_current_user)]

MAX_PROOFS = 6


# ───────────────────────────── helpers ─────────────────────────────


async def owned_page(services, page_id: UUID, user: CurrentUser) -> dict:
    try:
        return await services.sales_pages.get(page_id, user.id)
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "página no encontrada") from None


def deliverables_of(outline: dict) -> list[Deliverable]:
    """Las piezas del paquete en el orden de la página: principal, bonus y order bumps."""

    def one(kind: str, item: dict) -> Deliverable:
        return Deliverable(
            kind=kind,  # type: ignore[arg-type]
            title=str(item.get("title", ""))[:300],
            promise=str(item.get("promise", ""))[:500],
            format=str(item.get("format", ""))[:40],
            contents=[str(x)[:200] for x in (item.get("table_of_contents") or [])][:12],
        )

    out: list[Deliverable] = []
    if outline.get("main"):
        out.append(one("main", outline["main"]))
    out += [one("bonus", b) for b in outline.get("bonuses", [])]
    out += [one("bump", b) for b in outline.get("order_bumps", [])]
    return [d for d in out if d.title]


def brief_from_product(product: dict) -> PageBrief:
    """Los hechos del paquete. Precio, garantía y urgencia solo los pone quien los da."""
    from app.content.schemas import Problem

    problem = Problem.model_validate(product["problem"])
    outline = product.get("outline") or {}
    main = outline.get("main") or {}
    return PageBrief(
        market=product["market"],
        niche=product["niche"],
        product_name=outline.get("product_name") or product.get("title") or problem.title,
        problem=problem.title[:500],
        audience=(product.get("audience_override") or problem.audience)[:500],
        pain=problem.pain[:500],
        promise=(main.get("promise") or problem.promised_result)[:500],
        timeframe=problem.timeframe[:200],
        why_pay=problem.why_pay[:500],
        deliverables=deliverables_of(outline),
        tone=(product.get("tone") or "")[:200],
    )


class ManualBrief(BaseModel):
    """Para crear una página sin un paquete hecho en la app."""

    niche: str = Field(min_length=2, max_length=120)
    product_name: str = Field(min_length=1, max_length=300)
    problem: str = Field(min_length=3, max_length=500)
    audience: str = Field(min_length=3, max_length=500)
    promise: str = Field(min_length=3, max_length=500)
    timeframe: str = Field(default="", max_length=200)
    deliverables: list[Deliverable] = Field(default_factory=list, max_length=12)


class PageIn(BaseModel):
    market: Market
    product_id: UUID | None = None
    manual: ManualBrief | None = None
    template_id: str | None = Field(default=None, max_length=60)
    checkout_url: str | None = Field(default=None, max_length=500)
    # Lo que el usuario pone: si lo deja vacío, la página no lo menciona.
    price_text: str = Field(default="", max_length=60)
    guarantee_text: str = Field(default="", max_length=300)
    real_urgency: str = Field(default="", max_length=200)
    about_author: str = Field(default="", max_length=600)
    tone: str = Field(default="", max_length=200)
    proof_ids: list[UUID] = Field(default_factory=list, max_length=MAX_PROOFS)
    # La página que se toma de modelo (análisis + huella de `POST /pages/reference`).
    reference: PageReference | None = None
    fingerprint: str | None = Field(default=None, max_length=70_000)

    @model_validator(mode="after")
    def one_source(self) -> "PageIn":
        if (self.product_id is None) == (self.manual is None):
            raise ValueError("indica un paquete (product_id) o los datos a mano (manual), no ambos")
        return self

    @field_validator("checkout_url")
    @classmethod
    def https_url(cls, value: str | None) -> str | None:
        return check_checkout(value)


def check_checkout(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    parts = urlsplit(value.strip())
    if parts.scheme != "https" or not parts.hostname or "." not in parts.hostname:
        raise ValueError("el enlace de compra debe ser una URL https:// completa")
    if parts.username or parts.password:
        raise ValueError("el enlace no puede llevar usuario ni clave")
    return value.strip()


class PageCreated(BaseModel):
    page_id: UUID
    job_id: UUID


async def proofs_for(services, user: CurrentUser, ids: list[UUID], product_id: UUID | None):
    if not ids:
        return []
    rows = await services.ad_proofs.list(user.id, product_id)
    by_id = {str(r["id"]): r for r in rows}
    missing = [str(i) for i in ids if str(i) not in by_id]
    if missing:
        raise unprocessable("una de las pruebas elegidas no existe")
    return [
        PageProof(
            id=str(i),
            kind=by_id[str(i)]["kind"],
            text=by_id[str(i)]["text"],
            author=by_id[str(i)].get("author"),
        )
        for i in ids
    ]


def known_template(services, template_id: str) -> str:
    try:
        load_template(Path(services.settings.templates_dir), template_id)
    except (OSError, ValueError):
        raise unprocessable("la plantilla visual no existe") from None
    return template_id


# ───────────────────────────── analizar otra página ─────────────────────────────


class TeardownResponse(BaseModel):
    reference: PageReference
    fingerprint: str
    page: ReferencePage
    looks_like_sales_page: bool


@router.post("/reference", dependencies=[Depends(ai_rate_limit)])
async def analyze_reference(
    body: ReferenceRequest,
    user: User,
    services: ServicesDep,
    fetch: Annotated[PageFetcher, Depends(get_page_fetcher)],
) -> TeardownResponse:
    """Lee la página modelo (se guarda un análisis y una huella, nunca su texto)."""
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
    reference, is_sales = await services.page_service.teardown(
        user_id=user.id, market=body.market, page=payload, source_url=source_url
    )
    return TeardownResponse(
        reference=reference,
        fingerprint=similarity.pack(similarity.fingerprint(f"{page.title} {page.text}")),
        page=ReferencePage(
            title=page.title,
            chars=len(page.text),
            truncated=page.truncated,
            source=source,  # type: ignore[arg-type]
        ),
        looks_like_sales_page=is_sales,
    )


# ───────────────────────────── crear ─────────────────────────────


class BriefPreview(BaseModel):
    brief: PageBrief
    template_id: str
    proofs: list[PageProof]


@router.get("/brief")
async def brief_preview(product_id: UUID, user: User, services: ServicesDep) -> BriefPreview:
    """Los datos del paquete, para que el asistente los muestre y el usuario complete lo suyo."""
    product = await owned_product(services, product_id, user)
    brief = brief_from_product(product)
    rows = await services.ad_proofs.list(user.id, product_id)
    proofs = [
        PageProof(id=str(r["id"]), kind=r["kind"], text=r["text"], author=r.get("author"))
        for r in rows[:MAX_PROOFS]
    ]
    return BriefPreview(brief=brief, template_id=product["template_id"], proofs=proofs)


@router.post("", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(ai_rate_limit)])
async def create_page(body: PageIn, user: User, services: ServicesDep) -> PageCreated:
    product: dict | None = None
    if body.product_id is not None:
        product = await owned_product(services, body.product_id, user)
        if product.get("status") not in ("ready", "error", "generating", "outline_ready"):
            raise unprocessable("el paquete aún no está listo")
        base = brief_from_product(product)
        if base.market != body.market:
            raise unprocessable("el mercado de la página debe ser el del paquete")
        template_id = body.template_id or product["template_id"]
    else:
        assert body.manual is not None
        base = PageBrief(market=body.market, **body.manual.model_dump())
        template_id = body.template_id or "bold-moderno"
    known_template(services, template_id)
    brief = base.model_copy(
        update={
            "price_text": body.price_text.strip(),
            "guarantee_text": body.guarantee_text.strip(),
            "real_urgency": body.real_urgency.strip(),
            "about_author": body.about_author.strip(),
            "tone": body.tone.strip() or base.tone,
        }
    )
    proofs = await proofs_for(services, user, body.proof_ids, body.product_id)
    fingerprint: list[int] | None = None
    if body.reference is not None:
        if not body.fingerprint:
            raise unprocessable("falta la huella de la página modelo: vuelve a analizarla")
        try:
            fingerprint = similarity.unpack(body.fingerprint)
        except ValueError as exc:
            raise unprocessable(str(exc)) from exc
    page = await services.sales_pages.create(
        {
            "user_id": str(user.id),
            "product_id": str(body.product_id) if body.product_id else None,
            "market": body.market,
            "template_id": template_id,
            "title": brief.product_name[:200],
            "brief": brief.model_dump(),
            "reference": body.reference.model_dump() if body.reference else None,
            "reference_fingerprint": fingerprint,
            "proofs": [p.model_dump() for p in proofs],
            "checkout_url": body.checkout_url,
            "prompt_version": services.prompts.version,
        }
    )
    job = await services.jobs.enqueue(
        user_id=user.id, page_id=UUID(page["id"]), kind="page_generate", payload={}
    )
    return PageCreated(page_id=UUID(page["id"]), job_id=UUID(job["id"]))


# ───────────────────────────── leer, editar y exportar ─────────────────────────────


class PageState(BaseModel):
    working: bool


@router.get("/{page_id}/state")
async def page_state(page_id: UUID, user: User, services: ServicesDep) -> PageState:
    await owned_page(services, page_id, user)
    return PageState(working=bool(await services.jobs.active_for_page(page_id)))


class HtmlOut(BaseModel):
    html: str
    filename: str


def page_parts(page: dict) -> tuple[PageContent, PageBrief, list[PageProof]]:
    if not page.get("content"):
        raise HTTPException(status.HTTP_409_CONFLICT, "la página aún no tiene contenido")
    return (
        PageContent.model_validate(page["content"]),
        PageBrief.model_validate(page["brief"]),
        [PageProof.model_validate(p) for p in page.get("proofs") or []],
    )


def filename_of(page: dict) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in page["title"].lower()).strip("-")[:50]
    return f"pagina-{slug or 'ventas'}.html"


def html_of(services, page: dict) -> str:
    content, brief, proofs = page_parts(page)
    template = load_template(Path(services.settings.templates_dir), page["template_id"])
    return render_page(content, brief, proofs, template, page.get("checkout_url"))


@router.get("/{page_id}/html")
async def preview_html(page_id: UUID, user: User, services: ServicesDep) -> HtmlOut:
    """La página renderizada para la vista previa (se ve aunque no se pueda exportar)."""
    page = await owned_page(services, page_id, user)
    return HtmlOut(html=html_of(services, page), filename=filename_of(page))


@router.post("/{page_id}/export", dependencies=[Depends(work_rate_limit)])
async def export_html(page_id: UUID, user: User, services: ServicesDep) -> HtmlOut:
    """El HTML listo para publicar. Se niega si el texto se parece demasiado a la página modelo."""
    page = await owned_page(services, page_id, user)
    report = SimilarityReport.model_validate(page.get("similarity") or {})
    if report.level == "block":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "el texto se parece demasiado a la página modelo: edítalo o vuelve a generarlo",
        )
    return HtmlOut(html=html_of(services, page), filename=filename_of(page))


class LovableOut(BaseModel):
    prompt: str
    chars: int
    # El enlace de Lovable lleva el texto en la URL: pasado este largo conviene copiar y pegar.
    link_ok: bool


@router.get("/{page_id}/lovable", dependencies=[Depends(work_rate_limit)])
async def lovable_prompt(page_id: UUID, user: User, services: ServicesDep) -> LovableOut:
    """Las instrucciones para construir esta página en Lovable (texto ya revisado, sin IA)."""
    page = await owned_page(services, page_id, user)
    report = SimilarityReport.model_validate(page.get("similarity") or {})
    if report.level == "block":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "el texto se parece demasiado a la página modelo: edítalo o vuelve a generarlo",
        )
    content, brief, proofs = page_parts(page)
    template = load_template(Path(services.settings.templates_dir), page["template_id"])
    prompt = lovable.build_prompt(content, brief, proofs, template, page.get("checkout_url"))
    return LovableOut(
        prompt=prompt,
        chars=len(prompt),
        link_ok=len(quote(prompt, safe="")) <= lovable.URL_SAFE_CHARS,
    )


class EditIn(BaseModel):
    content: PageContent | None = None
    checkout_url: str | None = Field(default=None, max_length=500)
    template_id: str | None = Field(default=None, max_length=60)

    @field_validator("checkout_url")
    @classmethod
    def https_url(cls, value: str | None) -> str | None:
        return check_checkout(value)


class EditOut(BaseModel):
    similarity: SimilarityReport
    warnings: list[str] = []


@router.put("/{page_id}", dependencies=[Depends(work_rate_limit)])
async def edit_page(page_id: UUID, body: EditIn, user: User, services: ServicesDep) -> EditOut:
    """Guarda el texto editado a mano: mismas reglas de honestidad que la IA y el parecido se
    vuelve a medir. No usa IA."""
    page = await owned_page(services, page_id, user)
    if await services.jobs.active_for_page(page_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "la página se está generando")
    changes: dict[str, Any] = {}
    if body.template_id:
        changes["template_id"] = known_template(services, body.template_id)
    if body.checkout_url is not None:
        changes["checkout_url"] = body.checkout_url or None
    report = SimilarityReport.model_validate(page.get("similarity") or {})
    if body.content is not None:
        _, brief, proofs = page_parts({**page, "content": body.content.model_dump()})
        from app.pages import rules

        errors, report = revalidate(
            body.content,
            brief,
            proofs,
            page.get("reference_fingerprint"),
            (page.get("reference") or {}).get("brand_terms", []),
        )
        if errors:
            raise unprocessable(*errors)
        changes["content"] = rules.finalize(body.content, brief, proofs).model_dump()
        changes["similarity"] = report.model_dump()
    if changes:
        await services.sales_pages.update(page["id"], **changes)
    return EditOut(similarity=report)


@router.post(
    "/{page_id}/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(ai_rate_limit)],
)
async def regenerate_page(page_id: UUID, user: User, services: ServicesDep) -> JobOut:
    """Vuelve a escribir la página completa con IA (descarta las ediciones a mano)."""
    page = await owned_page(services, page_id, user)
    if await services.jobs.active_for_page(page_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "la página ya se está generando")
    await services.sales_pages.update(page["id"], status="planning", error=None)
    job = await services.jobs.enqueue(
        user_id=user.id, page_id=page_id, kind="page_generate", payload={}
    )
    return JobOut(job_id=UUID(job["id"]))


@router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(page_id: UUID, user: User, services: ServicesDep) -> None:
    await owned_page(services, page_id, user)
    await services.sales_pages.delete(page_id, user.id)
