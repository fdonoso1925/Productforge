import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.deps import get_services
from app.main import create_app
from tests.fakes import make_outline, make_request
from tests.memory import MemoryFiles, MemoryJobs, MemoryProducts, MemoryStorage
from tests.test_auth import ALLOWED, SECRET, make_token

USER = str(uuid4())


@pytest.fixture
def ctx():
    settings = Settings(_env_file=None, supabase_jwt_secret=SECRET, allowed_emails=[ALLOWED])
    services = SimpleNamespace(
        products=MemoryProducts(),
        jobs=MemoryJobs(),
        files=MemoryFiles(),
        storage=MemoryStorage(),
    )
    request = make_request()
    product = services.products.add(
        user_id=USER,
        niche=request.niche,
        problem=request.problem.model_dump(),
        market="pt-BR",
        main_format="pdf_guide",
        template_id="minimal-clean",
        outline=make_outline().model_dump(mode="json"),
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_services] = lambda: services
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {make_token(sub=USER)}"
    return client, services, product


def test_save_outline_applies_rules(ctx) -> None:
    client, services, product = ctx
    outline = make_outline().model_dump(mode="json")
    outline["product_name"] = "Nome novo"
    assert client.put(f"/products/{product['id']}/outline", json=outline).status_code == 200
    assert product["title"] == "Nome novo"

    outline["order_bumps"] = outline["order_bumps"][:2]
    response = client.put(f"/products/{product['id']}/outline", json=outline)
    assert response.status_code == 422
    assert response.json()["detail"]["errors"]


def test_generate_enqueues_once(ctx) -> None:
    client, services, product = ctx
    response = client.post(f"/products/{product['id']}/generate")
    assert response.status_code == 202
    assert product["status"] == "generating"
    assert len(services.jobs.rows) == 1
    assert client.post(f"/products/{product['id']}/generate").status_code == 409


def test_other_users_product_is_404(ctx) -> None:
    client, _, product = ctx
    client.headers["Authorization"] = f"Bearer {make_token(sub=str(uuid4()))}"
    assert client.post(f"/products/{product['id']}/generate").status_code == 404


def test_download_returns_signed_url_only_for_owner(ctx) -> None:
    client, services, product = ctx

    file = asyncio.run(
        services.files.add(
            product_id=product["id"],
            user_id=USER,
            item_id=None,
            file_type="zip",
            storage_path=f"{USER}/{product['id']}/x.zip",
            size=1,
        )
    )
    response = client.get(f"/files/{file['id']}/download")
    assert response.status_code == 200
    assert response.json()["url"].startswith("https://storage.test/")
    client.headers["Authorization"] = f"Bearer {make_token(sub=str(uuid4()))}"
    assert client.get(f"/files/{file['id']}/download").status_code == 404


def test_templates_catalog_and_preview(ctx) -> None:
    client, _, _ = ctx
    templates = client.get("/templates").json()
    assert len(templates) >= 10
    response = client.get(f"/templates/{templates[0]['id']}/preview.png")
    assert response.status_code == 200 and response.content.startswith(b"\x89PNG")
    assert client.get("/templates/..%2F..%2Fetc/preview.png").status_code == 404
