"""Job `upload`, cola de subidas e integración con la generación (destino simulado)."""

import asyncio
from uuid import UUID, uuid4

import pytest

from app.config import Settings
from app.pipeline.drive_sync import UploadIncomplete, product_folder, run_upload
from app.pipeline.package import PipelineDeps
from app.pipeline.uploads import MAX_ATTEMPTS, UploadQueue
from tests.fake_google import FakeTarget
from tests.memory import MemoryFiles, MemoryItems, MemoryJobs, MemoryProducts, MemoryStorage
from tests.test_remodel import World, bonus_mind_map, new_mind_map

USER = str(uuid4())
SETTINGS = Settings(_env_file=None)


def run(coro):
    return asyncio.run(coro)


class Env:
    """Un producto con archivos ya guardados en Storage, listo para copiarse a Google Drive."""

    def __init__(self, target: FakeTarget | None = None, **product) -> None:
        self.target = target or FakeTarget()
        self.products, self.files, self.jobs = MemoryProducts(), MemoryFiles(), MemoryJobs()
        self.storage = MemoryStorage()
        self.deps = PipelineDeps(
            content=None,  # type: ignore[arg-type]  # no se usa en este job
            products=self.products,
            items=MemoryItems(),
            files=self.files,
            jobs=self.jobs,
            storage=self.storage,
            templates_dir=SETTINGS.templates_dir,
            sync_target=self.target,
            uploads=UploadQueue(self.target, self.jobs, self.files),
        )
        self.product = self.products.add(
            user_id=USER,
            niche="Finanças pessoais",
            market="pt-BR",
            title="Kit Saída do Rotativo",
            created_at="2026-10-21T10:00:00+00:00",
            prompt_version="t",
            **product,
        )
        self.pid = self.product["id"]

    def add_file(self, rel: str, file_type: str = "pdf", **extra) -> dict:
        path = f"{USER}/{self.pid}/{rel}"
        self.storage.objects[path] = b"contenido " + rel.encode()
        return run(
            self.files.add(
                product_id=self.pid,
                user_id=USER,
                item_id=None,
                file_type=file_type,
                storage_path=path,
                size=10,
                **extra,
            )
        )

    def job(self, **payload) -> dict:
        return run(
            self.jobs.enqueue(product_id=self.pid, user_id=USER, kind="upload", payload=payload)
        )

    def upload(self, **payload) -> None:
        run(run_upload(self.job(**payload), self.deps))

    def status(self, row: dict) -> str:
        return self.files.rows[row["id"]]["remote_status"]


# ─────────────────────────── carpeta ───────────────────────────


def test_product_folder_follows_the_documented_layout() -> None:
    root = {
        "id": "abcdef123",
        "market": "pt-BR",
        "niche": "Finanças pessoais",
        "title": "Kit Saída: do Rotativo?",
        "created_at": "2026-10-21T10:00:00Z",
    }
    assert product_folder(root) == "pt-BR/financas-pessoais/2026-10-21_kit-saida-do-rotativo"


def test_derived_versions_get_their_own_folder() -> None:
    root = {
        "id": "abcdef123",
        "market": "pt-BR",
        "niche": "x",
        "title": "Kit",
        "created_at": "2026-10-21",
    }
    child = {**root, "id": "999aaa111", "parent_product_id": "abcdef123"}
    assert product_folder(child) != product_folder(root)
    assert product_folder(child).endswith("-999aaa")


def test_folder_never_contains_path_traversal_or_forbidden_characters() -> None:
    folder = product_folder(
        {
            "id": "x" * 8,
            "market": "pt-BR",
            "niche": "../../etc",
            "title": 'a<b>:"c"|d*',
            "created_at": "2026-10-21",
        }
    )
    assert ".." not in folder and not any(c in folder.split("/", 1)[1] for c in '<>:"|*?\\')
    assert folder.count("/") == 2


# ─────────────────────────── subida ───────────────────────────


def test_files_are_copied_with_the_folder_structure_and_zip_is_skipped() -> None:
    env = Env()
    pdf = env.add_file("principal/guia.pdf")
    xlsx = env.add_file("order-bumps/planilha.xlsx", "xlsx")
    ficha = env.add_file("ficha-comercial.md", "md")
    zip_row = env.add_file("kit.zip", "zip")

    env.upload()

    base = "pt-BR/financas-pessoais/2026-10-21_kit-saida-do-rotativo"
    assert sorted(path for _, path, _, _ in env.target.uploads) == sorted(
        [
            f"{base}/principal/guia.pdf",
            f"{base}/order-bumps/planilha.xlsx",
            f"{base}/ficha-comercial.md",
        ]
    )
    assert {m for _, _, _, m in env.target.uploads} >= {"application/pdf", "text/markdown"}
    for row in (pdf, xlsx, ficha):
        saved = env.files.rows[row["id"]]
        assert saved["remote_status"] == "uploaded" and saved["upload_attempts"] == 1
        assert saved["remote_id"].startswith("remote-") and saved["remote_url"].startswith(
            "https://"
        )
    assert env.status(zip_row) == "skipped"
    assert all(user == USER for user, *_ in env.target.uploads)


def test_failures_are_recorded_and_retried_without_losing_anything() -> None:
    env = Env(FakeTarget(fail=("planilha.xlsx",)))
    ok = env.add_file("principal/guia.pdf")
    bad = env.add_file("order-bumps/planilha.xlsx", "xlsx")

    with pytest.raises(UploadIncomplete):
        env.upload()
    assert env.status(ok) == "uploaded"
    assert env.status(bad) == "failed" and env.files.rows[bad["id"]]["upload_attempts"] == 1
    assert env.storage.objects[bad["storage_path"]]  # el respaldo en Supabase sigue ahí

    env.target.fail = ()  # Drive se recupera
    env.upload()
    assert env.status(bad) == "uploaded" and env.files.rows[bad["id"]]["upload_attempts"] == 2
    uploaded_again = [p for _, p, _, _ in env.target.uploads if p.endswith("guia.pdf")]
    assert len(uploaded_again) == 1  # lo que ya estaba subido no se vuelve a subir


def test_files_that_exhausted_their_attempts_are_left_alone() -> None:
    env = Env()
    stuck = env.add_file("principal/guia.pdf", remote_status="failed", upload_attempts=MAX_ATTEMPTS)
    env.upload()
    assert env.target.attempted == [] and env.status(stuck) == "failed"


def test_lost_access_aborts_and_keeps_files_pending() -> None:
    env = Env(FakeTarget(raise_not_connected=True))
    rows = [env.add_file("principal/a.pdf"), env.add_file("bonus/b.pdf")]
    with pytest.raises(Exception, match="revocado"):
        env.upload()
    assert [env.status(r) for r in rows] == ["pending", "pending"]


def test_missing_supabase_object_marks_the_file_failed() -> None:
    env = Env()
    row = env.add_file("principal/a.pdf")
    del env.storage.objects[row["storage_path"]]
    with pytest.raises(UploadIncomplete):
        env.upload()
    assert env.status(row) == "failed"


def test_replaced_files_are_deleted_from_drive_best_effort() -> None:
    env = Env(FakeTarget(fail_delete=True))
    env.add_file("principal/a.pdf")
    env.upload(delete_item_ids=["old-1", "old-2"])  # el borrado falla y no rompe el job
    assert env.target.deleted == ["old-1", "old-2"]


def test_job_without_a_configured_target_fails_clearly() -> None:
    env = Env()
    env.deps.sync_target = None
    with pytest.raises(RuntimeError):
        env.upload()


# ─────────────────────────── cola ───────────────────────────


def test_queue_skips_unconfigured_or_disconnected_users() -> None:
    for target in (FakeTarget(connected=False), FakeTarget(configured=False)):
        env = Env(target)
        env.add_file("principal/a.pdf")
        assert run(env.deps.uploads.enqueue(UUID(USER), UUID(env.pid))) is False
        assert env.jobs.rows == {}


def test_queue_does_not_stack_upload_jobs_but_always_queues_deletions() -> None:
    env = Env()
    q, user, pid = env.deps.uploads, UUID(USER), UUID(env.pid)
    assert run(q.enqueue(user, pid)) is True
    assert run(q.enqueue(user, pid)) is False  # ya hay una subida pendiente
    assert run(q.enqueue(user, pid, ["x"])) is True  # los borrados no se pierden
    kinds = [(j["kind"], j["payload"]["delete_item_ids"]) for j in env.jobs.rows.values()]
    assert kinds == [("upload", []), ("upload", ["x"])]


def test_enqueue_unsynced_picks_only_products_with_pending_files() -> None:
    env = Env()
    env.add_file("principal/a.pdf")
    env.add_file("kit.zip", "zip")
    other = env.products.add(user_id=USER, niche="n", market="pt-BR", prompt_version="t")
    run(
        env.files.add(
            product_id=other["id"],
            user_id=USER,
            item_id=None,
            file_type="pdf",
            storage_path="x",
            size=1,
            remote_status="uploaded",
        )
    )
    assert run(env.deps.uploads.enqueue_unsynced(UUID(USER))) == 1
    assert [j["product_id"] for j in env.jobs.rows.values()] == [env.pid]


# ─────────────────────────── integración con la generación ───────────────────────────


def with_drive(world: World, target: FakeTarget) -> None:
    world.deps.sync_target = target
    world.deps.uploads = UploadQueue(target, world.deps.jobs, world.deps.files)


def upload_jobs(world: World) -> list[dict]:
    return [j for j in world.deps.jobs.rows.values() if j["kind"] == "upload"]


def test_generation_queues_the_drive_copy_when_connected() -> None:
    w = World()
    with_drive(w, FakeTarget())
    response = w.client.post(
        f"/products/{w.product['id']}/remodel", json={"template_id": "soft-pastel"}
    )
    w.run_worker()
    [job] = upload_jobs(w)
    assert job["product_id"] == response.json()["product_id"]


def test_generation_does_not_queue_anything_without_drive() -> None:
    w = World()
    with_drive(w, FakeTarget(connected=False))
    w.client.post(f"/products/{w.product['id']}/remodel", json={"template_id": "soft-pastel"})
    w.run_worker()
    assert upload_jobs(w) == []


def test_a_broken_queue_never_fails_the_generation() -> None:
    w = World()
    with_drive(w, FakeTarget())

    async def boom(*_a, **_k):
        raise RuntimeError("cola caída")

    w.deps.uploads.enqueue = boom  # type: ignore[method-assign]
    response = w.client.post(
        f"/products/{w.product['id']}/remodel", json={"template_id": "soft-pastel"}
    )
    w.run_worker()
    assert w.deps.products.rows[response.json()["product_id"]]["status"] == "ready"


def test_regenerating_a_piece_schedules_cleanup_of_its_old_drive_files() -> None:
    w = World(extra_responses=[new_mind_map()])
    with_drive(w, FakeTarget())
    item = bonus_mind_map(w)
    mine = [f for f in w.deps.files.rows.values() if f["product_item_id"] == item["id"]]
    for i, f in enumerate(mine):
        f["remote_status"], f["remote_id"] = "uploaded", f"old-{i}"

    w.client.post(f"/products/{w.product['id']}/items/{item['id']}/regenerate")
    w.run_worker()

    [job] = upload_jobs(w)
    assert sorted(job["payload"]["delete_item_ids"]) == sorted(f"old-{i}" for i in range(len(mine)))
    new_files = [f for f in w.deps.files.rows.values() if f["product_item_id"] == item["id"]]
    assert new_files and all(f["remote_status"] == "pending" for f in new_files)


def test_the_zip_row_is_created_as_skipped() -> None:
    w = World()
    zips = [f for f in w.deps.files.rows.values() if f["file_type"] == "zip"]
    assert zips and all(z["remote_status"] == "skipped" for z in zips)
