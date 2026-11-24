"""Página de ventas con infografías, fotos del tema y mockups del producto."""

import asyncio
import re
from uuid import uuid4

from app.config import Settings
from app.content.schemas.formats import PhotoSpec, Visual, VisualItem
from app.pages import rules
from app.pages.media import asset_path, asset_uris, resolve_assets
from app.pages.render import render_page
from app.templates_engine.model import load_template
from tests.test_cover_editorial import FakeProducts, product
from tests.test_pages import brief, content, proofs
from tests.test_visuals import FakeRouter

SETTINGS = Settings(_env_file=None)
TEMPLATE = load_template(SETTINGS.templates_dir, "minimal-clean")
JPG = "data:image/jpeg;base64,/9j/AAAA"
PNG = "data:image/png;base64,iVBORw0KGgo="


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def upload(self, path, data, mime):
        self.objects[path] = data

    async def download(self, path):
        return self.objects[path]


# ───────────────────────────── reglas ─────────────────────────────


def test_generation_requires_a_method_infographic_and_a_photo_but_edits_do_not() -> None:
    assert rules.media_errors(content(), required=True) == []
    bare = content(solution_visual=None, problem_photo=None)
    errors = rules.media_errors(bare, required=True)
    assert any("solution_visual" in e for e in errors) and any("problem_photo" in e for e in errors)
    assert rules.media_errors(bare) == []  # una página vieja se sigue pudiendo editar


def test_the_page_never_shows_charts_with_numbers() -> None:
    chart = Visual(
        kind="bars",
        title="x",
        items=[VisualItem(label="a", value=1), VisualItem(label="b", value=2)],
    )
    errors = rules.media_errors(content(solution_visual=chart))
    assert any("bars ni donut" in e for e in errors)
    bad_photo = PhotoSpec(scene="desk", keywords=["desk"])
    assert any("hero_photo" in e for e in rules.media_errors(content(hero_photo=bad_photo)))


# ───────────────────────────── maqueta ─────────────────────────────


def test_infographics_are_inline_svg_and_images_are_embedded() -> None:
    images = {"bundle": PNG, "problem": JPG, "book": PNG}
    html = render_page(content(), brief(), proofs(), TEMPLATE, None, images)
    assert html.count("<svg") >= 2  # el método (IA) + el camino (código)
    assert "El método en tres pasos" in html and "Tu camino, paso a paso" in html
    assert 'class="mock"' in html and 'class="offer-mock"' in html and JPG in html
    # Sigue siendo un único archivo: ninguna imagen ni recurso se pide a otro sitio.
    assert not re.search(r"""(src|href)=["']https?://(?!.*#oferta)""", html.replace(PNG, ""))


def test_without_mockups_the_hero_uses_the_photo_and_without_anything_still_renders() -> None:
    html = render_page(content(), brief(), proofs(), TEMPLATE, None, {"hero": JPG})
    assert 'class="photo"' in html
    plain = render_page(content(solution_visual=None), brief(), proofs(), TEMPLATE, None)
    assert "hero-media" not in plain.split("</style>")[1] and "<svg" in plain  # el camino igual


def test_infographic_text_is_escaped() -> None:
    evil = Visual(
        kind="cards",
        title="<script>alert(1)</script>",
        items=[VisualItem(label="<img src=x onerror=1>", detail="d")] * 3,
    )
    html = render_page(content(solution_visual=evil), brief(), proofs(), TEMPLATE, None)
    assert "<script>alert" not in html and "<img src=x" not in html


def test_only_image_data_uris_get_into_the_page() -> None:
    html = render_page(
        content(), brief(), proofs(), TEMPLATE, None, {"hero": "javascript:alert(1)"}
    )
    assert "javascript:alert" not in html


# ───────────────────────────── imágenes del job ─────────────────────────────


def test_the_job_saves_photos_and_product_mockups_once() -> None:
    storage, router, user = MemoryStorage(), FakeRouter(), uuid4()
    page = {"id": "p1", "product_id": str(uuid4())}
    row = {**product("editorial"), "market": "es-LATAM", "niche": "orden"}
    row["outline"]["main"]["promise"] = "Orden en una semana"
    page_content = content(hero_photo=PhotoSpec(scene="tidy desk", keywords=["tidy", "desk"]))
    assets = asyncio.run(
        resolve_assets(
            page, page_content, brief(), user_id=user, images=router, storage=storage,
            products=FakeProducts(row), templates_dir=SETTINGS.templates_dir,
        )
    )  # fmt: skip
    assert set(assets) == {"hero", "problem", "bundle", "book"}
    assert assets["book"] == asset_path(user, "p1", "book") and assets["book"].endswith(".png")
    assert [r.aspect for r in router.requests] == ["16:9", "16:9"]
    uris = asyncio.run(asset_uris(storage, {**assets, "evil": "x", "lost": "nada.png"}))
    assert set(uris) == {"hero", "problem", "bundle", "book"}
    assert uris["book"].startswith("data:image/png;base64,")


def test_without_provider_or_product_the_page_has_no_images_and_nothing_breaks() -> None:
    storage = MemoryStorage()
    page = {"id": "p2", "product_id": None}
    off = FakeRouter(active=False)
    assets = asyncio.run(
        resolve_assets(page, content(), brief(), user_id=uuid4(), images=off, storage=storage)
    )
    assert assets == {}
    failing = FakeRouter(fail={"messy desk"})
    assets = asyncio.run(
        resolve_assets(page, content(), brief(), user_id=uuid4(), images=failing, storage=storage)
    )
    assert assets == {}
    assert asyncio.run(resolve_assets(page, content(), brief(), user_id=uuid4())) == {}
