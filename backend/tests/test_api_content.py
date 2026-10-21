import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.content.engines import ContentService, EngineConfig
from app.content.prompts import PromptLibrary
from app.content.schemas import ProblemProposals
from app.deps import get_content_service, get_product_repo
from app.main import create_app
from tests.fakes import FakeLLM, FakeProductRepo, FakeUsage, make_outline, make_problem
from tests.test_auth import ALLOWED, SECRET, make_token


@pytest.fixture
def ctx():
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


def test_problems_requires_auth(ctx) -> None:
    client, _, _ = ctx
    response = client.post("/problems", json={"niche": "Pets"}, headers={"Authorization": ""})
    assert response.status_code == 401


def test_problems_ok(ctx) -> None:
    client, llm, _ = ctx
    llm.responses.append(ProblemProposals(problems=[make_problem()] * 5))
    response = client.post("/problems", json={"niche": "Pets", "market": "es-LATAM"})
    assert response.status_code == 200
    assert len(response.json()["problems"]) == 5


def test_problems_rejects_long_niche(ctx) -> None:
    client, _, _ = ctx
    assert client.post("/problems", json={"niche": "x" * 121}).status_code == 422


def outline_body(**overrides) -> dict:
    return {
        "niche": "Finanças pessoais",
        "problem": make_problem().model_dump(),
        "market": "pt-BR",
        "main_format": "pdf_guide",
        "template_id": "minimal-clean",
        **overrides,
    }


def test_outline_persists_product(ctx) -> None:
    client, llm, repo = ctx
    llm.responses.append(make_outline())
    response = client.post("/outline", json=outline_body())
    assert response.status_code == 200
    assert response.json()["outline"]["product_name"] == "Adeus Cheque Especial"
    saved = repo.created[0]
    assert saved["template_id"] == "minimal-clean"
    assert saved["prompt_version"]


def test_outline_rejected_returns_502_with_errors(ctx) -> None:
    client, llm, repo = ctx
    bad = make_outline()
    bad.order_bumps.pop()
    llm.responses.extend([bad, bad, bad])
    response = client.post("/outline", json=outline_body())
    assert response.status_code == 502
    assert response.json()["errors"]
    assert repo.created == []


def test_outline_validates_template_id(ctx) -> None:
    client, _, _ = ctx
    assert client.post("/outline", json=outline_body(template_id="../x")).status_code == 422


def test_no_credits_message_is_actionable(ctx) -> None:
    import anthropic
    import httpx

    client, llm, _ = ctx
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(400, request=request)
    llm.responses.append(
        anthropic.BadRequestError(
            "Your credit balance is too low to access the Anthropic API.",
            response=response,
            body=None,
        )
    )
    result = client.post("/problems", json={"niche": "Pets"})
    assert result.status_code == 503
    assert "créditos" in result.json()["detail"]
