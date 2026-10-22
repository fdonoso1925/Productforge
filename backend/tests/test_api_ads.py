"""API y worker del módulo Creativos: lote → copy → revisión → composición, con IA simulada."""

import asyncio
import io
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

from app.ads.images.router import ImageRouter
from app.ads.jobs import AdDeps
from app.ads.render import AdRenderer
from app.ads.repo import AdBatchRepo
from app.ads.schemas import (
    AvatarProposals,
    CreativeDrafts,
    CreativeReview,
    CreativeReviews,
)
from app.ads.strategy import AdStrategyService
from app.config import Settings, get_settings
from app.content.engines import ContentService, EngineConfig
from app.content.prompts import PromptLibrary
from app.deps import get_services
from app.main import create_app
from app.worker import run_one
from tests.fake_google import FakeTarget
from tests.fakes import FakeLLM, FakeUsage, make_outline, make_problem
from tests.memory import (
    MemoryAdBatches,
    MemoryAdCreatives,
    MemoryAdProofs,
    MemoryImageCache,
    MemoryJobs,
    MemoryProducts,
    MemoryProviderUsage,
    MemoryStorage,
)
from tests.test_ads_strategy import avatar, draft, green, score
from tests.test_auth import ALLOWED, SECRET, make_token
from tests.test_pipeline import USER

assert AdBatchRepo  # el repo real expone la misma interfaz que el de memoria


SETTINGS = Settings(_env_file=None, supabase_jwt_secret=SECRET, allowed_emails=[ALLOWED])


class AdsWorld:
    """API + worker + repos en memoria compartiendo el mismo estado."""

    def __init__(self, responses=(), images=None, drive=None) -> None:
        self.llm = FakeLLM(list(responses))
        prompts = PromptLibrary(SETTINGS.prompts_dir)
        content = ContentService(
            llm=self.llm, prompts=prompts, usage=FakeUsage(), config=EngineConfig("m", "m")
        )
        self.products = MemoryProducts()
        self.product = self.products.add(
            user_id=USER,
            niche="productividad",
            problem=make_problem().model_dump(),
            market="es-LATAM",
            main_format="pdf_guide",
            template_id="bold-moderno",
            outline=make_outline().model_dump(mode="json"),
            prompt_version="test",
        )
        self.batches, self.creatives = MemoryAdBatches(), MemoryAdCreatives()
        self.proofs, self.jobs, self.storage = MemoryAdProofs(), MemoryJobs(), MemoryStorage()
        renderer = AdRenderer(SETTINGS.ad_templates_dir, SETTINGS.templates_dir)
        strategy = AdStrategyService(content)
        self.drive = drive or FakeTarget(connected=False)
        self.images = images or ImageRouter(
            [], MemoryImageCache(), MemoryProviderUsage(), self.storage
        )
        self.services = SimpleNamespace(
            settings=SETTINGS,
            prompts=prompts,
            products=self.products,
            jobs=self.jobs,
            storage=self.storage,
            ad_strategy=strategy,
            ad_renderer=renderer,
            ad_batches=self.batches,
            ad_creatives=self.creatives,
            ad_proofs=self.proofs,
            ad_images=self.images,
            drive=self.drive,
            ads=lambda: AdDeps(
                strategy=strategy,
                renderer=renderer,
                batches=self.batches,
                creatives=self.creatives,
                proofs=self.proofs,
                jobs=self.jobs,
                storage=self.storage,
                templates_dir=SETTINGS.templates_dir,
                images=self.images,
                sync_target=self.drive,
            ),
        )
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: SETTINGS
        app.dependency_overrides[get_services] = lambda: self.services
        self.client = TestClient(app)
        self.client.headers["Authorization"] = f"Bearer {make_token(sub=USER)}"

    def run_worker(self) -> None:
        assert asyncio.run(run_one(self.services)) is True

    def as_user(self, sub: str) -> dict:
        return {"Authorization": f"Bearer {make_token(sub=sub)}"}

    def batch_body(self, **over) -> dict:
        body = {
            "product_id": self.product["id"],
            "price_text": "USD 12",
            "avatars": [avatar().model_dump()],
            "picks": [{"angle_id": "mecanismo", "avatar": avatar().name, "count": 2}],
            "ratios": ["4x5", "1x1"],
        }
        return {**body, **over}


def plan_responses(*, count=2, templates=("product_mockup", "checklist")):
    drafts = [draft(templates[i % len(templates)]) for i in range(count)]
    reviews = [CreativeReview(index=i, policy=green(), score=score()) for i in range(count)]
    return [CreativeDrafts(creatives=drafts), CreativeReviews(reviews=reviews)]


def planned_world() -> tuple[AdsWorld, str]:
    w = AdsWorld(plan_responses())
    response = w.client.post("/ads/batches", json=w.batch_body())
    assert response.status_code == 202, response.text
    w.run_worker()
    return w, response.json()["batch_id"]


# ───────────────────────────── brief ─────────────────────────────


def test_brief_comes_from_the_product_without_inventing_price_or_urgency() -> None:
    w = AdsWorld()
    response = w.client.post("/ads/brief", json={"product_id": w.product["id"]})
    assert response.status_code == 200
    data = response.json()
    assert data["market"] == "es-LATAM" and data["product_name"] == "Adeus Cheque Especial"
    assert data["price_text"] == "" and data["real_urgency"] == ""  # solo si el usuario lo da
    assert data["bonuses"]
    given = w.client.post(
        "/ads/brief", json={"product_id": w.product["id"], "price_text": "USD 12"}
    )
    assert given.json()["price_text"] == "USD 12"


def test_a_brief_needs_exactly_one_source_and_the_product_must_be_yours() -> None:
    w = AdsWorld()
    assert w.client.post("/ads/brief", json={}).status_code == 422
    manual = {
        "market": "es-LATAM",
        "niche": "productividad",
        "product_name": "X",
        "problem": "p",
        "audience": "a",
        "promise": "m",
    }
    both = {"product_id": w.product["id"], "brief": manual}
    assert w.client.post("/ads/brief", json=both).status_code == 422
    assert w.client.post("/ads/brief", json={"brief": manual}).status_code == 200
    stranger = w.as_user(str(uuid4()))
    other = w.client.post("/ads/brief", json={"product_id": w.product["id"]}, headers=stranger)
    assert other.status_code == 404


def test_the_ad_endpoints_require_a_session() -> None:
    w = AdsWorld()
    anonymous = TestClient(w.client.app)
    for method, url in [
        ("get", "/ads/batches"),
        ("get", "/ads/proofs"),
        ("post", "/ads/avatars"),
        ("get", f"/ads/creatives/{uuid4()}/url"),
    ]:
        assert getattr(anonymous, method)(url).status_code == 401


def test_templates_endpoint_lists_templates_and_ratios_with_safe_zones() -> None:
    w = AdsWorld()
    data = w.client.get("/ads/templates").json()
    assert len(data["templates"]) == 12
    assert {t["id"] for t in data["templates"] if t["uses_image"]} == {"photo_headline"}
    assert {r["id"] for r in data["ratios"]} == {"4x5", "9x16", "1x1"}


# ───────────────────────────── estrategia ─────────────────────────────


def test_avatars_endpoint_uses_the_ai_with_the_resolved_brief() -> None:
    w = AdsWorld([AvatarProposals(avatars=[avatar("A"), avatar("B")])])
    response = w.client.post("/ads/avatars", json={"product_id": w.product["id"]})
    assert response.status_code == 200
    assert [a["name"] for a in response.json()["avatars"]] == ["A", "B"]
    assert response.json()["brief"]["product_name"] == "Adeus Cheque Especial"


# ───────────────────────────── lote ─────────────────────────────


def test_batch_plan_writes_copy_policy_and_score_for_every_format_without_images() -> None:
    w, batch_id = planned_world()
    state = w.client.get(f"/ads/batches/{batch_id}").json()
    assert state["batch"]["status"] == "review" and state["job"] is None
    creatives = state["creatives"]
    assert len(creatives) == 4  # 2 borradores × 2 formatos
    assert {c["ratio"] for c in creatives} == {"4x5", "1x1"}
    assert all(c["status"] == "planned" and not c["storage_path"] for c in creatives)
    assert all(c["policy_status"] == "green" and c["pre_score"] == 7 for c in creatives)
    # El mismo borrador en sus dos formatos comparte grupo.
    assert len({c["group_id"] for c in creatives}) == 2
    names = {c["filename"] for c in creatives}
    assert "adeus-cheque-especial_es-latam_mecanismo_productmockup_4x5_v1.png" in names
    assert "adeus-cheque-especial_es-latam_mecanismo_checklist_1x1_v1.png" in names
    assert w.storage.objects == {}  # planificar no compone nada


def test_batch_validates_angles_avatars_formats_and_limits() -> None:
    w = AdsWorld()
    post = lambda **over: w.client.post("/ads/batches", json=w.batch_body(**over))  # noqa: E731
    cases = [
        {"picks": [{"angle_id": "inventado", "avatar": avatar().name, "count": 1}]},
        {"picks": [{"angle_id": "dolor", "avatar": "Nadie", "count": 1}]},
        {"picks": [{"angle_id": "autoridad", "avatar": avatar().name, "count": 1}]},  # sin pruebas
        {"picks": [{"angle_id": "dolor", "avatar": avatar().name, "count": 9}]},
        {"ratios": ["4x5", "4x5"]},
        {"ratios": ["16x9"]},
        {"ratios": []},
        {"template_id": "no-existe"},
        {"picks": [{"angle_id": "dolor", "avatar": avatar().name, "count": 5}] * 5},  # >20
    ]
    for case in cases:
        assert post(**case).status_code == 422, case
    assert w.jobs.rows == {} and w.batches.rows == {}  # nada se encola si no valida


def test_real_proofs_unlock_the_proof_angle() -> None:
    w = AdsWorld()
    pick = [{"angle_id": "autoridad", "avatar": avatar().name, "count": 1}]
    assert w.client.post("/ads/batches", json=w.batch_body(picks=pick)).status_code == 422
    added = w.client.post(
        "/ads/proofs",
        json={"kind": "testimonial", "text": "Ordené mis pedidos en una semana", "author": "A. M."},
    )
    assert added.status_code == 201
    assert w.client.post("/ads/batches", json=w.batch_body(picks=pick)).status_code == 202
    listed = w.client.get("/ads/proofs").json()
    assert [p["text"] for p in listed] == ["Ordené mis pedidos en una semana"]
    stranger = w.as_user(str(uuid4()))
    assert w.client.get("/ads/proofs", headers=stranger).json() == []
    w.client.delete(f"/ads/proofs/{listed[0]['id']}", headers=stranger)
    assert len(w.client.get("/ads/proofs").json()) == 1  # nadie borra pruebas ajenas
    assert w.client.delete(f"/ads/proofs/{listed[0]['id']}").status_code == 204
    assert w.client.get("/ads/proofs").json() == []
    bad = w.client.post("/ads/proofs", json={"kind": "invento", "text": "algo"})
    assert bad.status_code == 422


def test_a_failed_plan_leaves_the_batch_in_error_not_stuck() -> None:
    w = AdsWorld([RuntimeError("sin créditos")])
    response = w.client.post("/ads/batches", json=w.batch_body())
    w.run_worker()
    batch = w.batches.rows[response.json()["batch_id"]]
    assert batch["status"] == "error"
    assert w.jobs.rows[response.json()["job_id"]]["status"] == "error"
    assert w.product["status"] == "outline_ready"  # un job de anuncios no toca al producto


# ───────────────────────────── composición ─────────────────────────────


def test_render_composes_every_creative_at_its_exact_size_and_stores_it() -> None:
    w, batch_id = planned_world()
    calls = len(w.llm.calls)
    response = w.client.post(f"/ads/batches/{batch_id}/render", json={})
    assert response.status_code == 202
    assert w.client.post(f"/ads/batches/{batch_id}/render", json={}).status_code == 409
    w.run_worker()

    assert len(w.llm.calls) == calls  # componer no usa IA
    state = w.client.get(f"/ads/batches/{batch_id}").json()
    assert state["batch"]["status"] == "ready"
    sizes = {"4x5": (1080, 1350), "1x1": (1080, 1080)}
    for c in state["creatives"]:
        assert c["status"] == "rendered"
        assert c["storage_path"].startswith(f"{USER}/ads/{batch_id}/")
        assert c["storage_path"].endswith(c["filename"])
        image = Image.open(io.BytesIO(w.storage.objects[c["storage_path"]]))
        assert image.format == "PNG" and image.size == sizes[c["ratio"]]
    url = w.client.get(f"/ads/creatives/{state['creatives'][0]['id']}/url")
    assert url.status_code == 200 and url.json()["url"].startswith("https://storage.test/")
    # Con todo compuesto no queda nada por hacer.
    w.client.post(f"/ads/batches/{batch_id}/render", json={})
    before = dict(w.storage.objects)
    w.run_worker()
    assert w.storage.objects == before


def test_render_only_the_requested_creatives_and_never_discarded_ones() -> None:
    w, batch_id = planned_world()
    creatives = w.client.get(f"/ads/batches/{batch_id}").json()["creatives"]
    first, second = creatives[0], creatives[1]
    w.client.post(f"/ads/creatives/{second['id']}/discard")
    w.client.post(f"/ads/batches/{batch_id}/render", json={"creative_ids": [first["id"]]})
    w.run_worker()
    by_id = {c["id"]: c for c in w.creatives.rows.values()}
    assert by_id[first["id"]]["status"] == "rendered"
    assert by_id[second["id"]]["status"] == "discarded" and not by_id[second["id"]]["storage_path"]
    assert len(w.storage.objects) == 1


def test_editing_the_text_recomposes_without_ai_and_updates_the_other_formats() -> None:
    w, batch_id = planned_world()
    w.client.post(f"/ads/batches/{batch_id}/render", json={})
    w.run_worker()
    calls = len(w.llm.calls)
    creatives = w.client.get(f"/ads/batches/{batch_id}").json()["creatives"]
    target = creatives[0]
    old_png = w.storage.objects[target["storage_path"]]
    image = {**target["copy"]["image"], "headline": "Tu lista de pedidos en un solo lugar"}

    edited = w.client.put(f"/ads/creatives/{target['id']}", json={"image": image})
    assert edited.status_code == 200, edited.text
    assert len(w.llm.calls) == calls  # editar y recomponer es gratis
    assert w.storage.objects[target["storage_path"]] != old_png
    siblings = [c for c in w.creatives.rows.values() if c["group_id"] == target["group_id"]]
    assert len(siblings) == 2
    assert all(c["copy"]["image"]["headline"] == image["headline"] for c in siblings)
    assert all(c["status"] == "rendered" for c in siblings)
    other = [c for c in w.creatives.rows.values() if c["group_id"] != target["group_id"]]
    assert all(c["copy"]["image"]["headline"] != image["headline"] for c in other)


def test_edits_go_through_the_same_rules_and_traffic_light_as_the_ai_text() -> None:
    w, batch_id = planned_world()
    target = w.client.get(f"/ads/batches/{batch_id}").json()["creatives"][0]
    long = {**target["copy"]["image"], "headline": "palabra " * 30}
    assert w.client.put(f"/ads/creatives/{target['id']}", json={"image": long}).status_code == 422
    assert w.client.put(f"/ads/creatives/{target['id']}", json={}).status_code == 422
    bad = {**target["copy"]["image"], "headline": "Garantizado 100%: nunca más pierdes un pedido"}
    risky = w.client.put(f"/ads/creatives/{target['id']}", json={"image": bad})
    assert risky.status_code == 200
    assert risky.json()["policy_status"] in ("yellow", "red")  # el semáforo se recalcula
    assert w.creatives.rows[target["id"]]["policy_notes"]["notes"]


def test_creatives_are_private_to_their_owner() -> None:
    w, batch_id = planned_world()
    creative = w.client.get(f"/ads/batches/{batch_id}").json()["creatives"][0]
    stranger = w.as_user(str(uuid4()))
    for method, url, body in [
        ("get", f"/ads/batches/{batch_id}", None),
        ("post", f"/ads/batches/{batch_id}/render", {}),
        ("put", f"/ads/creatives/{creative['id']}", {"ad": creative["copy"]["ad"]}),
        ("post", f"/ads/creatives/{creative['id']}/render", None),
        ("post", f"/ads/creatives/{creative['id']}/discard", None),
        ("get", f"/ads/creatives/{creative['id']}/url", None),
    ]:
        kwargs = {"json": body} if body is not None else {}
        response = getattr(w.client, method)(url, headers=stranger, **kwargs)
        assert response.status_code == 404, (method, url)
    assert w.client.get("/ads/batches", headers=stranger).json() == []
    assert len(w.client.get("/ads/batches").json()) == 1


def test_render_one_creative_synchronously() -> None:
    w, batch_id = planned_world()
    creative = w.client.get(f"/ads/batches/{batch_id}").json()["creatives"][0]
    assert w.client.get(f"/ads/creatives/{creative['id']}/url").status_code == 404  # sin imagen
    done = w.client.post(f"/ads/creatives/{creative['id']}/render")
    assert done.status_code == 200 and done.json()["status"] == "rendered"
    assert len(w.storage.objects) == 1


def test_a_batch_that_is_still_planning_cannot_be_rendered() -> None:
    w = AdsWorld(plan_responses())
    batch_id = w.client.post("/ads/batches", json=w.batch_body()).json()["batch_id"]
    assert w.client.post(f"/ads/batches/{batch_id}/render", json={}).status_code == 409
    assert w.client.get(f"/ads/batches/{batch_id}").json()["job"]["kind"] == "ad_plan"
