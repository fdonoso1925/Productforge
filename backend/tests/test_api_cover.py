"""API de portadas: vista previa, subida de imagen, selección y remodelado sin IA."""

import io
import os
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings, get_settings
from app.content.engines import ContentService, EngineConfig
from app.content.prompts import PromptLibrary
from app.deps import get_content_service, get_product_repo
from app.generators.cover import image_path
from app.main import create_app
from tests.fakes import FakeLLM, FakeProductRepo, FakeUsage, make_outline, make_problem
from tests.test_auth import ALLOWED, SECRET, make_token
from tests.test_pipeline import USER
from tests.test_remodel import World

IMAGE_HEADERS = {"Content-Type": "application/octet-stream"}


def photo(size=(1000, 1400), color="#556b2f", fmt="JPEG") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format=fmt)
    return out.getvalue()


def noisy_jpeg() -> bytes:
    """Un JPEG de varios MB (el ruido no se comprime): prueba el tope de subida propio."""
    image = Image.frombytes("RGB", (1500, 1500), os.urandom(1500 * 1500 * 3))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=95)
    return out.getvalue()


def main_pdf(w: World, product_id: str) -> bytes:
    f = next(
        f
        for f in w.files_of(product_id)
        if f["file_type"] == "pdf" and "/principal/" in f["storage_path"]
    )
    return w.deps.storage.objects[f["storage_path"]]


def test_art_preview_is_public_and_validates_its_inputs() -> None:
    client = TestClient(create_app())  # sin sesión: lo usa el selector
    ok = client.get("/cover/art/topo.svg", params={"template": "bold-moderno", "seed": "demo"})
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("image/svg+xml")
    assert ok.text.startswith("<svg")
    other = client.get("/cover/art/topo.svg", params={"template": "dark-elegante", "seed": "demo"})
    assert other.text != ok.text  # toma la paleta de la plantilla
    for url, params in [
        ("/cover/art/grafiti.svg", {}),
        ("/cover/art/auto.svg", {}),
        ("/cover/art/topo.svg", {"template": "../etc"}),
        ("/cover/art/topo.svg", {"template": "no-existe"}),
        ("/cover/art/topo.svg", {"seed": "<script>"}),
    ]:
        assert client.get(url, params=params).status_code == 404


def test_upload_select_and_use_an_own_image() -> None:
    w = World()
    c, pid = w.client, w.product["id"]

    # Subida: se valida, se guarda como JPEG limpio y devuelve una URL firmada.
    up = c.post("/cover-images", content=photo(), headers=IMAGE_HEADERS)
    assert up.status_code == 201
    image_id = up.json()["image_id"]
    assert up.json()["url"] and (up.json()["width"], up.json()["height"]) == (1000, 1400)
    stored = w.deps.storage.objects[image_path(USER, image_id)]
    assert Image.open(io.BytesIO(stored)).format == "JPEG"
    assert c.get(f"/cover-images/{image_id}/url").status_code == 200

    # Una imagen de otro usuario no se puede ver ni usar.
    c.headers["Authorization"] = f"Bearer {make_token(sub=str(uuid4()))}"
    assert c.get(f"/cover-images/{image_id}/url").status_code == 404
    c.headers["Authorization"] = f"Bearer {make_token(sub=USER)}"

    # Remodelar con otra portada: solo maqueta (sin IA) y conserva la original.
    parent_pdf = main_pdf(w, pid)
    parent_cover = dict(w.deps.products.rows[pid].get("cover") or {})
    response = c.post(
        f"/products/{pid}/remodel", json={"cover": {"art": "none", "image_id": image_id}}
    )
    assert response.status_code == 202
    assert response.json()["plan"] == {"generate": 0, "rerender": 6}
    w.run_worker()
    assert w.new_calls == 0
    child = w.deps.products.rows[response.json()["product_id"]]
    assert child["status"] == "ready"
    assert child["cover"] == {"art": "none", "image_id": image_id}
    assert main_pdf(w, child["id"]) != parent_pdf  # la portada cambió el PDF
    assert (w.deps.products.rows[pid].get("cover") or {}) == parent_cover  # original intacto


def test_remodel_with_art_is_free_and_each_version_keeps_the_family() -> None:
    w = World()
    c, pid = w.client, w.product["id"]
    parent_pdf = main_pdf(w, pid)

    same = c.post(f"/products/{pid}/remodel", json={"cover": {"art": "none"}})
    assert same.status_code == 422  # el producto anterior ya está sin arte: nada cambia

    first = c.post(f"/products/{pid}/remodel", json={"cover": {"art": "waves"}})
    assert first.status_code == 202 and first.json()["plan"] == {"generate": 0, "rerender": 6}
    w.run_worker()
    waves_id = first.json()["product_id"]
    assert w.new_calls == 0
    assert main_pdf(w, waves_id) != parent_pdf

    # Cambiar solo la plantilla de esa versión conserva su arte (misma raíz, misma semilla).
    second = c.post(f"/products/{waves_id}/remodel", json={"template_id": "dark-elegante"})
    assert second.status_code == 202
    child = w.deps.products.rows[second.json()["product_id"]]
    assert child["cover"] == {"art": "waves", "image_id": None}
    assert child["root_product_id"] == pid


def test_cover_rules_for_unknown_images_and_generated_packages() -> None:
    w = World()
    c, pid = w.client, w.product["id"]
    ghost = {"art": "topo", "image_id": str(uuid4())}

    assert c.post(f"/products/{pid}/remodel", json={"cover": ghost}).status_code == 422
    # Un paquete ya generado cambia de portada remodelando, no editándolo.
    assert c.put(f"/products/{pid}/cover", json={"art": "topo"}).status_code == 409

    w.deps.products.rows[pid]["status"] = "outline_ready"
    assert c.put(f"/products/{pid}/cover", json=ghost).status_code == 422
    ok = c.put(f"/products/{pid}/cover", json={"art": "bauhaus", "image_id": None})
    assert ok.status_code == 200
    assert w.deps.products.rows[pid]["cover"] == {"art": "bauhaus", "image_id": None}
    assert c.put(f"/products/{pid}/cover", json={"art": "grafiti"}).status_code == 422
    assert c.put(f"/products/{pid}/cover", json={"art": "topo", "x": 1}).status_code == 422

    c.headers["Authorization"] = f"Bearer {make_token(sub=str(uuid4()))}"
    assert c.put(f"/products/{pid}/cover", json={"art": "topo"}).status_code == 404


def test_upload_rejects_bad_files_and_huge_bodies() -> None:
    w = World()
    c = w.client
    before = len(w.deps.storage.objects)

    for body, fragment in [
        (b"", "vacío"),
        (b"%PDF-1.7 " + b"x" * 5000, "no se pudo leer"),
        (photo(size=(300, 300)), "muy chica"),
        (photo(fmt="GIF"), "JPG, PNG o WebP"),
    ]:
        bad = c.post("/cover-images", content=body, headers=IMAGE_HEADERS)
        assert bad.status_code == 422 and fragment in bad.json()["detail"]
    assert len(w.deps.storage.objects) == before  # nada se guardó

    assert c.post("/cover-images", content=b"x" * (6 * 1024 * 1024)).status_code == 413
    # Una foto de varios MB pasa: el tope general de 1 MB no aplica a esta ruta.
    big = noisy_jpeg()
    assert len(big) > 1_000_000
    assert c.post("/cover-images", content=big, headers=IMAGE_HEADERS).status_code == 201
    # Y las demás rutas siguen con su tope.
    assert (
        c.put(f"/products/{w.product['id']}/outline", content=b"x" * 1_100_000).status_code == 413
    )

    anonymous = TestClient(create_app()).post("/cover-images", content=photo())
    assert anonymous.status_code == 401


# ───────────────────────── paso del asistente: estilo de arte ─────────────────────────


def outline_ctx():
    settings = Settings(_env_file=None, supabase_jwt_secret=SECRET, allowed_emails=[ALLOWED])
    llm, repo = FakeLLM(), FakeProductRepo()
    svc = ContentService(
        llm=llm,
        prompts=PromptLibrary(settings.prompts_dir),
        usage=FakeUsage(),
        config=EngineConfig(model_outline="m", model_content="m"),
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_content_service] = lambda: svc
    app.dependency_overrides[get_product_repo] = lambda: repo
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {make_token()}"
    return client, llm, repo


def outline_body(**overrides) -> dict:
    return {
        "niche": "Finanças pessoais",
        "problem": make_problem().model_dump(),
        "market": "pt-BR",
        "main_format": "pdf_guide",
        "template_id": "minimal-clean",
        **overrides,
    }


def test_outline_stores_the_chosen_art_style_and_defaults_to_auto() -> None:
    client, llm, repo = outline_ctx()
    llm.responses.extend([make_outline(), make_outline()])
    assert client.post("/outline", json=outline_body()).status_code == 200
    assert repo.created[-1]["cover"] == {"art": "auto", "image_id": None}
    assert client.post("/outline", json=outline_body(cover_art="bauhaus")).status_code == 200
    assert repo.created[-1]["cover"] == {"art": "bauhaus", "image_id": None}
    assert client.post("/outline", json=outline_body(cover_art="grafiti")).status_code == 422
