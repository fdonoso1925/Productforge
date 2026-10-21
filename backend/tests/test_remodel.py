"""Fase 5: remodelar, regenerar una pieza y duplicar a otro mercado (repos en memoria)."""

import asyncio
import io
import zipfile
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.content.claude_client import LLMRefusal
from app.content.rules import check_adaptation, check_package_rules
from app.content.schemas import AdaptedPackage, Format
from app.content.schemas.formats import MindMapContent
from app.deps import get_services
from app.main import create_app
from app.pipeline.generate import run_generate
from app.pipeline.remodel import apply_formats, pages_for, plan_remodel, same_schema
from app.worker import run_one
from tests.fakes import make_item, make_outline, make_problem, make_request
from tests.test_auth import ALLOWED, SECRET, make_token
from tests.test_engines import commercial
from tests.test_pipeline import USER, item_responses, setup

SETTINGS = Settings(_env_file=None, supabase_jwt_secret=SECRET, allowed_emails=[ALLOWED])


# ─────────────────────────── lógica pura ───────────────────────────


def rows(*specs):
    return [
        {"id": f"i{n}", "role": role, "order": order, "format": fmt, "content": {"x": 1}}
        for n, (role, order, fmt) in enumerate(specs)
    ]


def test_same_schema_groups_guide_and_epub() -> None:
    assert same_schema(Format.PDF_GUIDE, Format.EPUB)
    assert not same_schema(Format.PDF_GUIDE, Format.CHECKLIST)


def test_plan_template_only_uses_no_ai() -> None:
    r = rows(("main", 0, "pdf_guide"), ("bonus", 0, "mind_map"))
    assert plan_remodel(r, {}, content_changed=False) == {"i0": "rerender", "i1": "rerender"}


def test_plan_tone_or_audience_regenerates_everything() -> None:
    r = rows(("main", 0, "pdf_guide"), ("bonus", 0, "mind_map"))
    assert set(plan_remodel(r, {}, content_changed=True).values()) == {"generate"}


def test_plan_format_change_depends_on_schema() -> None:
    r = rows(("main", 0, "pdf_guide"), ("bonus", 0, "mind_map"))
    modes = plan_remodel(r, {"i0": Format.EPUB, "i1": Format.SWIPE_FILE}, content_changed=False)
    assert modes == {"i0": "rerender", "i1": "generate"}


def test_plan_item_without_content_is_generated() -> None:
    r = rows(("main", 0, "pdf_guide"))
    r[0]["content"] = None
    assert plan_remodel(r, {}, content_changed=False) == {"i0": "generate"}


def test_pages_follow_new_format() -> None:
    assert pages_for("main", Format.PDF_GUIDE, 3) == 25
    assert pages_for("main", Format.EPUB, 80) == 40
    assert pages_for("main", Format.MIND_MAP, 3) == 3
    assert pages_for("order_bump", Format.CHECKLIST, 30) == 15


def test_apply_formats_does_not_mutate_original() -> None:
    outline = make_outline()
    r = [{"id": "b0", "role": "order_bump", "order": 0, "format": "sheet"}]
    changed = apply_formats(outline, r, {"b0": Format.SWIPE_FILE})
    assert changed.order_bumps[0].format == Format.SWIPE_FILE
    assert outline.order_bumps[0].format == Format.SHEET


def test_adaptation_must_keep_formats_and_counts() -> None:
    source = make_outline()
    same = source.model_copy(deep=True)
    assert check_adaptation(source, same) == []
    other = source.model_copy(deep=True)
    other.order_bumps[0] = make_item("order_bump", Format.SWIPE_FILE, "Otro")
    other.bonuses.pop()
    errors = check_adaptation(source, other)
    assert any("order_bumps[0].format" in e for e in errors)
    assert any("bonuses debe tener exactamente 2" in e for e in errors)


# ─────────────────────────── flujo completo ───────────────────────────


class World:
    """API + worker + repos en memoria compartiendo el mismo estado."""

    def __init__(self, extra_responses=()) -> None:
        self.outline = make_outline()
        self.deps, self.product, job, _ = setup(
            [*item_responses(self.outline), commercial("BRL"), *extra_responses]
        )
        self.llm = self.deps.content.llm
        self.services = SimpleNamespace(
            products=self.deps.products,
            items=self.deps.items,
            files=self.deps.files,
            jobs=self.deps.jobs,
            storage=self.deps.storage,
            prompts=self.deps.content.prompts,
            settings=SETTINGS,
            pipeline=lambda: self.deps,
        )
        asyncio.run(run_generate(job, self.deps))
        self.deps.jobs.rows[job["id"]]["status"] = "done"
        self.calls_after_generate = len(self.llm.calls)

        app = create_app()
        app.dependency_overrides[get_settings] = lambda: SETTINGS
        app.dependency_overrides[get_services] = lambda: self.services
        self.client = TestClient(app)
        self.client.headers["Authorization"] = f"Bearer {make_token(sub=USER)}"

    def run_worker(self) -> None:
        assert asyncio.run(run_one(self.services)) is True

    @property
    def new_calls(self) -> int:
        return len(self.llm.calls) - self.calls_after_generate

    def files_of(self, product_id: str) -> list[dict]:
        return [f for f in self.deps.files.rows.values() if f["product_id"] == product_id]

    def zip_names(self, product_id: str) -> list[str]:
        z = next(f for f in self.files_of(product_id) if f["file_type"] == "zip")
        return zipfile.ZipFile(io.BytesIO(self.deps.storage.objects[z["storage_path"]])).namelist()


def test_template_remodel_creates_linked_version_without_ai() -> None:
    w = World()
    parent_id = w.product["id"]
    response = w.client.post(
        f"/products/{parent_id}/remodel", json={"template_id": "dark-elegante"}
    )
    assert response.status_code == 202
    assert response.json()["plan"] == {"generate": 0, "rerender": 6}
    child_id = response.json()["product_id"]
    w.run_worker()

    assert w.new_calls == 0  # cambiar de plantilla no llama a la IA
    child = w.deps.products.rows[child_id]
    assert child["status"] == "ready"
    assert child["template_id"] == "dark-elegante"
    assert child["parent_product_id"] == parent_id
    assert child["root_product_id"] == parent_id
    assert child["commercial"] == w.product["commercial"]
    assert w.deps.products.rows[parent_id]["template_id"] == "minimal-clean"  # el original intacto

    # Los archivos nuevos se maquetaron con la otra plantilla, el ZIP trae todo.
    def main_pdf(pid):
        f = next(
            f
            for f in w.files_of(pid)
            if f["file_type"] == "pdf" and "/principal/" in f["storage_path"]
        )
        return w.deps.storage.objects[f["storage_path"]]

    assert main_pdf(child_id) != main_pdf(parent_id)
    names = w.zip_names(child_id)
    assert any(n.startswith("principal/") for n in names) and "ficha-comercial.md" in names
    assert all(
        p.startswith(f"{USER}/{child_id}/")
        for p in (f["storage_path"] for f in w.files_of(child_id))
    )


def test_version_tree_keeps_the_root_across_generations() -> None:
    w = World()
    first = w.client.post(
        f"/products/{w.product['id']}/remodel", json={"template_id": "soft-pastel"}
    )
    w.run_worker()
    second = w.client.post(
        f"/products/{first.json()['product_id']}/remodel", json={"template_id": "bold-moderno"}
    )
    assert second.status_code == 202
    grandchild = w.deps.products.rows[second.json()["product_id"]]
    assert grandchild["parent_product_id"] == first.json()["product_id"]
    assert grandchild["root_product_id"] == w.product["id"]


def test_tone_change_regenerates_all_pieces_with_ai() -> None:
    w = World(extra_responses=item_responses(make_outline()))
    response = w.client.post(
        f"/products/{w.product['id']}/remodel", json={"tone": "más informal y cercano"}
    )
    assert response.json()["plan"] == {"generate": 6, "rerender": 0}
    w.run_worker()
    assert w.new_calls == 6  # las 6 piezas; la ficha comercial se reutiliza
    assert "más informal" in w.llm.calls[-1].user
    assert w.deps.products.rows[response.json()["product_id"]]["tone"] == "más informal y cercano"


def test_format_change_with_same_schema_is_free_and_other_schema_uses_ai() -> None:
    w = World(extra_responses=[SAMPLES_SWIPE()])
    rows_ = asyncio.run(w.deps.items.list_for_product(w.product["id"]))
    main = next(r for r in rows_ if r["role"] == "main")
    bump = next(r for r in rows_ if r["role"] == "order_bump" and r["format"] == "sheet")
    response = w.client.post(
        f"/products/{w.product['id']}/remodel",
        json={"formats": {main["id"]: "epub", bump["id"]: "swipe_file"}},
    )
    assert response.status_code == 202
    assert response.json()["plan"] == {"generate": 1, "rerender": 5}
    w.run_worker()
    assert w.new_calls == 1
    child = w.deps.products.rows[response.json()["product_id"]]
    assert child["main_format"] == "epub" and child["status"] == "ready"
    assert any(f["file_type"] == "epub" for f in w.files_of(child["id"]))


def SAMPLES_SWIPE():
    from app.generators.samples import SAMPLES

    return SAMPLES[Format.SWIPE_FILE]


def test_invalid_remodels_are_rejected() -> None:
    w = World()
    pid = w.product["id"]
    rows_ = asyncio.run(w.deps.items.list_for_product(pid))
    bumps = [r for r in rows_ if r["role"] == "order_bump"]
    post = lambda body, product=pid: w.client.post(f"/products/{product}/remodel", json=body)  # noqa: E731

    assert post({}).status_code == 422  # sin cambios
    assert post({"template_id": "no-existe"}).status_code == 422
    # dos order bumps con el mismo formato rompe las reglas del paquete
    dup = post({"formats": {bumps[0]["id"]: bumps[1]["format"]}})
    assert dup.status_code == 422 and dup.json()["detail"]["errors"]
    assert post({"formats": {"00000000-0000-0000-0000-000000000000": "epub"}}).status_code == 422
    assert post({"tone": "x" * 201}).status_code == 422
    assert len(w.deps.products.rows) == 1  # nada se creó


def test_remodel_requires_a_generated_idle_package() -> None:
    w = World()
    w.deps.products.rows[w.product["id"]]["status"] = "outline_ready"
    body = {"template_id": "soft-pastel"}
    assert w.client.post(f"/products/{w.product['id']}/remodel", json=body).status_code == 409
    w.deps.products.rows[w.product["id"]]["status"] = "ready"
    w.client.post(f"/products/{w.product['id']}/duplicate", json={"market": "es-LATAM"})
    # hay un job en cola sobre el hijo, no sobre el original: el original sigue libre
    assert w.client.post(f"/products/{w.product['id']}/remodel", json=body).status_code == 202


def test_other_users_product_cannot_be_remodeled() -> None:
    w = World()
    from uuid import uuid4

    w.client.headers["Authorization"] = f"Bearer {make_token(sub=str(uuid4()))}"
    assert (
        w.client.post(
            f"/products/{w.product['id']}/remodel", json={"template_id": "soft-pastel"}
        ).status_code
        == 404
    )


# ─────────────────────────── regenerar una pieza ───────────────────────────


def bonus_mind_map(w: World) -> dict:
    rows_ = asyncio.run(w.deps.items.list_for_product(w.product["id"]))
    return next(r for r in rows_ if r["format"] == "mind_map")


def new_mind_map() -> MindMapContent:
    return MindMapContent.model_validate(
        {
            "title": "Mapa REGENERADO",
            "central_idea": "Idea nueva",
            "branches": [{"label": f"Rama {i}", "children": [{"label": "x"}]} for i in range(4)],
        }
    )


def test_regenerating_one_item_calls_ai_once_and_rebuilds_the_zip() -> None:
    w = World(extra_responses=[new_mind_map()])
    item = bonus_mind_map(w)
    pid = w.product["id"]
    before = {f["id"]: f for f in w.files_of(pid)}
    old_item_files = {f["id"] for f in before.values() if f["product_item_id"] == item["id"]}
    other_files = {
        f["id"] for f in before.values() if f["product_item_id"] not in (item["id"], None)
    }

    response = w.client.post(f"/products/{pid}/items/{item['id']}/regenerate")
    assert response.status_code == 202
    w.run_worker()

    assert w.new_calls == 1
    after = {f["id"]: f for f in w.files_of(pid)}
    new_item_files = {f["id"] for f in after.values() if f["product_item_id"] == item["id"]}
    assert new_item_files and not (new_item_files & old_item_files)  # archivos nuevos
    assert other_files <= set(after)  # las demás piezas no se tocaron
    assert w.deps.products.rows[pid]["status"] == "ready"

    zip_row = next(f for f in after.values() if f["file_type"] == "zip")
    archive = zipfile.ZipFile(io.BytesIO(w.deps.storage.objects[zip_row["storage_path"]]))
    svg = next(n for n in archive.namelist() if n.endswith(".svg"))
    assert b"Idea nueva" in archive.read(svg)
    assert sum(f["file_type"] == "zip" for f in after.values()) == 1


def test_regenerating_a_piece_also_completes_a_missing_commercial_sheet() -> None:
    """Paquete a medias (la generación cayó antes de la ficha): regenerar la pieza lo completa."""
    w = World(extra_responses=[new_mind_map(), commercial("BRL")])
    item = bonus_mind_map(w)
    pid = w.product["id"]
    w.product["commercial"] = None
    w.deps.files.rows = {
        k: f
        for k, f in w.deps.files.rows.items()
        if f["product_item_id"] is not None or f["file_type"] == "zip"
    }
    w.deps.products.rows[pid]["status"] = "error"

    assert w.client.post(f"/products/{pid}/items/{item['id']}/regenerate").status_code == 202
    w.run_worker()

    assert w.new_calls == 2  # la pieza y la ficha; las demás piezas no se vuelven a pagar
    assert w.deps.products.rows[pid]["commercial"]["currency"] == "BRL"
    assert w.deps.products.rows[pid]["status"] == "ready"
    assert "ficha-comercial.md" in w.zip_names(pid)


def test_generation_that_dies_at_the_commercial_sheet_does_not_stay_generating() -> None:
    """Sin créditos al armar la ficha: el producto pasa a «error» y se puede regenerar piezas."""
    outline = make_outline()
    deps, product, _, _ = setup([*item_responses(outline), *[LLMRefusal("x")] * 3])
    services = SimpleNamespace(jobs=deps.jobs, products=deps.products, pipeline=lambda: deps)
    assert asyncio.run(run_one(services)) is True

    job = next(iter(deps.jobs.rows.values()))
    assert job["status"] == "error"
    assert product["status"] == "error"
    assert all(i["status"] == "ready" for i in deps.items.rows.values())  # lo bueno se conserva


def test_regenerating_does_not_pay_again_for_an_existing_commercial_sheet() -> None:
    w = World(extra_responses=[new_mind_map()])
    item = bonus_mind_map(w)
    w.client.post(f"/products/{w.product['id']}/items/{item['id']}/regenerate")
    w.run_worker()
    assert w.new_calls == 1


def test_failed_regeneration_keeps_the_previous_files() -> None:
    w = World(extra_responses=[LLMRefusal("x")] * 3)
    item = bonus_mind_map(w)
    pid = w.product["id"]
    before = {f["id"] for f in w.files_of(pid)}
    w.client.post(f"/products/{pid}/items/{item['id']}/regenerate")
    w.run_worker()

    job = next(j for j in w.deps.jobs.rows.values() if j["kind"] == "regenerate_item")
    assert job["status"] == "error"
    assert {f["id"] for f in w.files_of(pid)} == before
    assert w.deps.items.rows[item["id"]]["status"] == "ready"
    assert w.deps.products.rows[pid]["status"] == "ready"


def test_regenerate_rejects_unknown_item_and_busy_package() -> None:
    w = World()
    pid = w.product["id"]
    missing = w.client.post(
        f"/products/{pid}/items/00000000-0000-0000-0000-000000000000/regenerate"
    )
    assert missing.status_code == 404
    item = bonus_mind_map(w)
    assert w.client.post(f"/products/{pid}/items/{item['id']}/regenerate").status_code == 202
    assert w.client.post(f"/products/{pid}/items/{item['id']}/regenerate").status_code == 409


# ─────────────────────────── duplicar a otro mercado ───────────────────────────


def adapted_package() -> AdaptedPackage:
    outline = make_outline()
    outline.product_name = "Adiós Tarjeta de Crédito"
    return AdaptedPackage(
        niche="Finanzas personales",
        problem=make_problem(title="Salir de la deuda de tarjeta en 90 días"),
        outline=outline,
    )


def test_duplicate_adapts_then_generates_native_content() -> None:
    w = World(
        extra_responses=[adapted_package(), *item_responses(make_outline()), commercial("USD")]
    )
    pid = w.product["id"]
    response = w.client.post(f"/products/{pid}/duplicate", json={"market": "es-LATAM"})
    assert response.status_code == 202
    w.run_worker()

    child = w.deps.products.rows[response.json()["product_id"]]
    assert child["market"] == "es-LATAM" and child["status"] == "ready"
    assert child["parent_product_id"] == pid and child["root_product_id"] == pid
    assert child["niche"] == "Finanzas personales"
    assert child["title"] == "Adiós Tarjeta de Crédito"
    assert child["commercial"]["currency"] == "USD"
    assert w.new_calls == 1 + 6 + 1  # adaptación + 6 piezas + ficha comercial

    adapt_call = w.llm.calls[w.calls_after_generate]
    assert adapt_call.schema is AdaptedPackage
    assert "Latinoamérica" in adapt_call.system  # prompt nativo del mercado destino
    assert '"source_market": "pt-BR"' in adapt_call.user
    assert w.deps.products.rows[pid]["market"] == "pt-BR"  # el original no cambia
    assert any(f["file_type"] == "zip" for f in w.files_of(child["id"]))


def test_duplicate_requires_the_other_market() -> None:
    w = World()
    same = w.client.post(f"/products/{w.product['id']}/duplicate", json={"market": "pt-BR"})
    assert same.status_code == 422


def test_adaptation_that_changes_formats_is_rejected_and_retried() -> None:
    bad = adapted_package()
    bad.outline.order_bumps[0] = make_item("order_bump", Format.SWIPE_FILE, "Distinto")
    bad.outline.order_bumps[2] = make_item("order_bump", Format.SHEET, "Planilla")
    w = World(
        extra_responses=[bad, adapted_package(), *item_responses(make_outline()), commercial("USD")]
    )
    response = w.client.post(f"/products/{w.product['id']}/duplicate", json={"market": "es-LATAM"})
    w.run_worker()
    assert w.deps.products.rows[response.json()["product_id"]]["status"] == "ready"
    assert "order_bumps[0].format" in w.llm.calls[w.calls_after_generate + 1].user  # feedback


def test_rules_unchanged_for_normal_packages() -> None:
    assert check_package_rules(make_outline(), make_request()) == []
