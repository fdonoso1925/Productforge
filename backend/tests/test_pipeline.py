import asyncio
import io
import zipfile
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.config import Settings
from app.content.claude_client import LLMRefusal
from app.content.engines import ContentService, EngineConfig
from app.content.prompts import PromptLibrary
from app.content.schemas import Format
from app.generators.samples import SAMPLES
from app.pipeline.generate import PipelineDeps, run_generate
from app.worker import run_one
from tests.fakes import FakeLLM, FakeUsage, make_outline, make_request
from tests.memory import MemoryFiles, MemoryItems, MemoryJobs, MemoryProducts, MemoryStorage
from tests.test_engines import commercial

SETTINGS = Settings(_env_file=None)
USER = str(uuid4())


def setup(responses):
    outline = make_outline()
    products, jobs = MemoryProducts(), MemoryJobs()
    request = make_request()
    product = products.add(
        user_id=USER,
        niche=request.niche,
        problem=request.problem.model_dump(),
        market="pt-BR",
        main_format="pdf_guide",
        template_id="minimal-clean",
        outline=outline.model_dump(mode="json"),
        prompt_version="test",
    )
    llm = FakeLLM(responses)
    deps = PipelineDeps(
        content=ContentService(
            llm=llm,
            prompts=PromptLibrary(SETTINGS.prompts_dir),
            usage=FakeUsage(),
            config=EngineConfig("m", "m"),
        ),
        products=products,
        items=MemoryItems(),
        files=MemoryFiles(),
        jobs=jobs,
        storage=MemoryStorage(),
        templates_dir=SETTINGS.templates_dir,
    )
    job = asyncio.run(
        jobs.enqueue(product_id=product["id"], user_id=USER, kind="generate", payload={})
    )
    return deps, product, job, outline


def item_responses(outline):
    # Las piezas se piden en orden: principal, order bumps, bonus (concurrencia 3, FIFO).
    return [SAMPLES[Format(i.format)] for i in outline.items()]


def test_full_package_generates_files_zip_and_commercial() -> None:
    outline = make_outline()
    deps, product, job, _ = setup([*item_responses(outline), commercial("BRL")])
    asyncio.run(run_generate(job, deps))

    assert product["status"] == "ready"
    assert product["commercial"]["currency"] == "BRL"
    assert all(i["status"] == "ready" for i in deps.items.rows.values())
    assert all(i["content"] and i["content_hash"] for i in deps.items.rows.values())

    progress = deps.jobs.rows[job["id"]]["progress"]
    assert progress["stage"] == "done" and progress["done"] == progress["total"] == 6

    types = sorted(f["file_type"] for f in deps.files.rows.values())
    assert {"pdf", "xlsx", "csv", "docx", "svg", "xmind", "md", "zip"} <= set(types)
    zip_row = next(f for f in deps.files.rows.values() if f["file_type"] == "zip")
    assert zip_row["product_item_id"] is None
    archive = zipfile.ZipFile(io.BytesIO(deps.storage.objects[zip_row["storage_path"]]))
    names = archive.namelist()
    assert any(n.startswith("principal/") for n in names)
    assert any(n.startswith("order-bumps/") for n in names)
    assert any(n.startswith("bonus/") for n in names)
    assert "ficha-comercial.md" in names
    assert all(p.startswith(f"{USER}/{product['id']}/") for p in deps.storage.objects)


def test_failed_item_does_not_block_the_rest() -> None:
    outline = make_outline()
    responses = item_responses(outline)
    responses[0] = LLMRefusal("x")  # el principal falla
    deps, product, job, _ = setup([*responses, commercial("BRL")])
    asyncio.run(run_generate(job, deps))

    statuses = sorted(i["status"] for i in deps.items.rows.values())
    assert statuses.count("error") == 1 and statuses.count("ready") == 5
    assert product["status"] == "error"  # paquete incompleto, pero con archivos
    assert any(f["file_type"] == "zip" for f in deps.files.rows.values())
    assert deps.jobs.rows[job["id"]]["logs"]


def test_all_items_failing_marks_product_error() -> None:
    deps, product, job, _ = setup([LLMRefusal("x")] * 6)
    with pytest.raises(RuntimeError):
        asyncio.run(run_generate(job, deps))
    assert product["status"] == "error"


def worker_services(deps: PipelineDeps):
    return SimpleNamespace(jobs=deps.jobs, pipeline=lambda: deps)


def test_worker_marks_job_done() -> None:
    outline = make_outline()
    deps, _, job, _ = setup([*item_responses(outline), commercial("BRL")])
    assert asyncio.run(run_one(worker_services(deps))) is True
    assert deps.jobs.rows[job["id"]]["status"] == "done"
    assert asyncio.run(run_one(worker_services(deps))) is False  # cola vacía


def test_worker_records_generic_error() -> None:
    deps, _, job, _ = setup([LLMRefusal("detalle interno")] * 6)
    asyncio.run(run_one(worker_services(deps)))
    row = deps.jobs.rows[job["id"]]
    assert row["status"] == "error"
    assert row["error"] == "RuntimeError"  # sin detalles internos


# ───────────────────── retomar una generación que quedó a medias ─────────────────────


def rerun(deps, product, responses):
    """Vuelve a encolar la generación del mismo producto con una IA que solo tiene `responses`."""
    deps.content.llm.responses[:] = list(responses)
    job = asyncio.run(
        deps.jobs.enqueue(product_id=product["id"], user_id=USER, kind="generate", payload={})
    )
    asyncio.run(run_generate(job, deps))
    return job


def files_of(deps, item_id=None):
    return [f for f in deps.files.rows.values() if f["product_item_id"] == item_id]


def test_resuming_only_redoes_the_missing_piece_and_keeps_the_rest() -> None:
    outline = make_outline()
    responses = item_responses(outline)
    responses[0] = LLMRefusal("x")  # el principal se cae
    deps, product, job, _ = setup([*responses, commercial("BRL")])
    asyncio.run(run_generate(job, deps))
    assert product["status"] == "error"
    kept = {
        i["id"]: sorted(f["id"] for f in files_of(deps, i["id"]))
        for i in deps.items.rows.values()
        if i["status"] == "ready"
    }
    sheet = sorted(f["id"] for f in files_of(deps) if f["file_type"] != "zip")

    rerun(deps, product, [SAMPLES[Format(outline.main.format)]])  # una sola llamada de IA

    assert deps.content.llm.responses == [] and len(deps.content.llm.calls) == 8
    assert product["status"] == "ready"
    assert all(i["status"] == "ready" for i in deps.items.rows.values())
    for item_id, ids in kept.items():  # las piezas completas no se tocaron
        assert sorted(f["id"] for f in files_of(deps, item_id)) == ids
    assert sorted(f["id"] for f in files_of(deps) if f["file_type"] != "zip") == sheet
    assert len(deps.items.rows) == 6
    assert len([f for f in files_of(deps) if f["file_type"] == "zip"]) == 1
    zip_row = next(f for f in files_of(deps) if f["file_type"] == "zip")
    names = zipfile.ZipFile(io.BytesIO(deps.storage.objects[zip_row["storage_path"]])).namelist()
    assert any(n.startswith("principal/") for n in names)  # la pieza rehecha ya está en el ZIP


def test_a_piece_whose_content_was_saved_is_rebuilt_without_paying_ai_again() -> None:
    outline = make_outline()
    deps, product, job, _ = setup([*item_responses(outline), commercial("BRL")])
    asyncio.run(run_generate(job, deps))
    calls = len(deps.content.llm.calls)

    victim = next(i for i in deps.items.rows.values() if i["role"] == "bonus")
    for f in files_of(deps, victim["id"]):  # se cayó entre el contenido y los archivos
        del deps.files.rows[f["id"]]
    victim["status"] = "error"
    product["status"] = "error"

    rerun(deps, product, [])  # sin respuestas de IA: si la llamara, fallaría

    assert len(deps.content.llm.calls) == calls
    assert victim["status"] == "ready" and files_of(deps, victim["id"])
    assert product["status"] == "ready"


def test_a_package_that_died_before_the_commercial_sheet_only_adds_the_sheet() -> None:
    outline = make_outline()
    deps, product, job, _ = setup([*item_responses(outline), commercial("BRL")])
    asyncio.run(run_generate(job, deps))
    for f in [f for f in files_of(deps) if f["file_type"] != "zip"]:
        del deps.files.rows[f["id"]]
    product["commercial"] = None
    product["status"] = "error"
    before = {
        i["id"]: sorted(f["id"] for f in files_of(deps, i["id"])) for i in deps.items.rows.values()
    }

    rerun(deps, product, [commercial("BRL")])  # solo la ficha

    assert product["commercial"]["currency"] == "BRL" and product["status"] == "ready"
    assert any(f["file_type"] == "md" for f in files_of(deps))
    for item_id, ids in before.items():
        assert sorted(f["id"] for f in files_of(deps, item_id)) == ids


def test_a_stored_commercial_sheet_is_only_re_laid_out_not_regenerated() -> None:
    outline = make_outline()
    deps, product, job, _ = setup([*item_responses(outline), commercial("BRL")])
    asyncio.run(run_generate(job, deps))
    for f in [f for f in files_of(deps) if f["file_type"] != "zip"]:
        del deps.files.rows[
            f["id"]
        ]  # los archivos de la ficha se perdieron, pero ella sigue guardada
    product["status"] = "error"
    calls = len(deps.content.llm.calls)

    rerun(deps, product, [])

    assert len(deps.content.llm.calls) == calls and any(
        f["file_type"] == "md" for f in files_of(deps)
    )


def test_a_product_without_pieces_still_starts_from_scratch() -> None:
    outline = make_outline()
    deps, product, job, _ = setup([*item_responses(outline), commercial("BRL")])
    assert deps.items.rows == {}
    asyncio.run(run_generate(job, deps))
    assert len(deps.items.rows) == 6 and product["status"] == "ready"
