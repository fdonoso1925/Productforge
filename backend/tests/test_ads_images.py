"""Creativos, fase 4: proveedores de imagen, router (caché, tope, reserva), plantillas con foto
y las 12 plantillas. Ningún test llama a Pixabay ni a Gemini de verdad."""

import asyncio
import base64
import io
from uuid import uuid4

import httpx
import pypdfium2 as pdfium
import pytest
from PIL import Image

from app.ads import rules
from app.ads.images.base import (
    ImageRequest,
    ProviderError,
    ProviderImage,
    ProviderQuota,
    ProviderRejected,
)
from app.ads.images.gemini import GeminiImageProvider
from app.ads.images.pixabay import PixabayProvider
from app.ads.images.router import ImageRouter, UnusableImage, build_router, fit_image
from app.ads.jobs import FALLBACK_TEMPLATE, available_templates
from app.ads.render import MissingImage, photo_veil
from app.ads.schemas import CreativeDrafts, CreativeReview, CreativeReviews
from app.config import Settings
from tests.memory import MemoryImageCache, MemoryProviderUsage, MemoryStorage
from tests.test_ads_render import BOLD, R, copy, overlapping, text_boxes
from tests.test_ads_strategy import avatar, brief, draft, green, proof, score
from tests.test_api_ads import USER, AdsWorld


def jpeg(size=(1600, 2000), color=(40, 90, 140), fmt="JPEG") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format=fmt)
    return out.getvalue()


REQUEST = ImageRequest(
    prompt="orderly desk with a notebook", keywords=("desk", "notebook"), aspect="4:5"
)


# ───────────────────────────── recorte y validación ─────────────────────────────


@pytest.mark.parametrize(
    ("aspect", "size"), [("4:5", (1080, 1350)), ("9:16", (1080, 1920)), ("1:1", (1080, 1080))]
)
def test_fit_image_crops_to_the_ad_ratio_as_a_clean_jpeg(aspect: str, size: tuple) -> None:
    source = io.BytesIO()
    image = Image.new("RGB", (2400, 1800), "#336699")
    exif = Image.Exif()
    exif[0x010F] = "camara"  # marca de la cámara: no debe sobrevivir
    image.save(source, format="JPEG", exif=exif)
    out = fit_image(source.getvalue(), aspect)
    result = Image.open(io.BytesIO(out))
    assert result.format == "JPEG" and result.size == size
    assert not result.getexif()  # sin EXIF


@pytest.mark.parametrize(
    "data",
    [b"no soy una imagen", jpeg((300, 300)), jpeg((1500, 500)), jpeg(fmt="GIF"), b""],
    ids=["basura", "pequena", "muy-ancha-para-vertical", "gif", "vacio"],
)
def test_fit_image_rejects_what_it_cannot_use(data: bytes) -> None:
    with pytest.raises(UnusableImage):
        fit_image(data, "9:16")
    with pytest.raises(UnusableImage):
        fit_image(jpeg(), "16:9")


# ───────────────────────────── Pixabay ─────────────────────────────

HIT = {
    "id": 77,
    "user": "autora",
    "pageURL": "https://pixabay.com/photos/desk-77/",
    "tags": "desk, notebook, office",
    "largeImageURL": "https://pixabay.com/get/desk-77.jpg",
}
PERSON = {
    **HIT,
    "id": 78,
    "tags": "woman, laptop, office",
    "largeImageURL": "https://pixabay.com/get/p.jpg",
}


def pixabay(hits, log=None, search_status=200) -> PixabayProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if log is not None:
            log.append(request)
        if request.url.path == "/api/":
            return httpx.Response(search_status, json={"hits": hits})
        return httpx.Response(200, content=jpeg(), headers={"content-type": "image/jpeg"})

    return PixabayProvider("k", httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_pixabay_searches_safely_downloads_the_photo_and_credits_the_author() -> None:
    log: list = []
    image = asyncio.run(pixabay([HIT], log).fetch(REQUEST))
    search = log[0].url.params
    assert search["safesearch"] == "true" and search["image_type"] == "photo"
    assert search["orientation"] == "vertical" and search["q"] == "desk notebook"
    assert image.provider == "pixabay" and image.cost_usd == 0
    assert Image.open(io.BytesIO(image.data)).size == (1600, 2000)  # descargada, no enlazada
    assert image.credit == {
        "provider": "pixabay",
        "id": 77,
        "author": "autora",
        "page_url": "https://pixabay.com/photos/desk-77/",
        "license": "Pixabay Content License",
    }


def test_pixabay_skips_photos_with_people_in_sensitive_niches() -> None:
    sensitive = ImageRequest(REQUEST.prompt, REQUEST.keywords, "4:5", sensitive=True)
    assert asyncio.run(pixabay([PERSON, HIT]).fetch(sensitive)).credit["id"] == 77
    with pytest.raises(ProviderRejected):
        asyncio.run(pixabay([PERSON]).fetch(sensitive))
    # En un nicho normal sí se puede usar.
    assert asyncio.run(pixabay([PERSON]).fetch(REQUEST)).credit["id"] == 78


def test_pixabay_caches_searches_for_24_hours_and_respects_its_rate_limit() -> None:
    log: list = []
    provider = pixabay([HIT], log)
    asyncio.run(provider.fetch(REQUEST))
    asyncio.run(provider.fetch(REQUEST))
    assert sum(r.url.path == "/api/" for r in log) == 1  # la búsqueda se reutiliza
    other = ImageRequest("x", ("coffee",), "4:5")
    for _ in range(100):
        try:
            asyncio.run(provider.fetch(ImageRequest("x", (f"q{_}",), "4:5")))
        except ProviderQuota:
            break
    else:
        pytest.fail("no aplicó el límite por minuto")
    assert other  # el objeto se creó sin llamar a la red


@pytest.mark.parametrize(
    ("hits", "status", "error"),
    [([], 200, ProviderRejected), ([HIT], 429, ProviderQuota), ([HIT], 500, ProviderError)],
)
def test_pixabay_errors_map_to_router_friendly_exceptions(hits, status, error) -> None:
    with pytest.raises(error):
        asyncio.run(pixabay(hits, search_status=status).fetch(REQUEST))


def test_pixabay_is_off_without_a_key_and_needs_keywords() -> None:
    assert not PixabayProvider("").enabled() and PixabayProvider("k").enabled()
    with pytest.raises(ProviderRejected):
        asyncio.run(pixabay([HIT]).fetch(ImageRequest("x", (), "4:5")))


# ───────────────────────────── Gemini ─────────────────────────────


def gemini(response: httpx.Response, log=None, cap=1.0, key="k") -> GeminiImageProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if log is not None:
            log.append(request)
        return response

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GeminiImageProvider(key, "modelo-x", 0.034, cap, client)


def gemini_ok() -> httpx.Response:
    data = base64.b64encode(jpeg()).decode()
    part = {"inlineData": {"mimeType": "image/jpeg", "data": data}}
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [part]}}]})


def test_gemini_generates_an_image_with_the_key_in_a_header_not_in_the_url() -> None:
    log: list = []
    image = asyncio.run(gemini(gemini_ok(), log).fetch(REQUEST))
    request = log[0]
    assert request.headers["x-goog-api-key"] == "k" and "k" not in str(request.url)
    assert request.url.path.endswith("/models/modelo-x:generateContent")
    body = request.read().decode()
    assert '"aspectRatio":"4:5"' in body.replace(" ", "") and "orderly desk" in body
    assert "logo" in body  # el prompt negativo viaja
    assert image.provider == "gemini" and image.cost_usd == pytest.approx(0.034)
    assert image.credit["generated"] is True


def test_gemini_stays_off_without_a_daily_cap_even_with_a_key() -> None:
    assert not gemini(gemini_ok(), cap=0).enabled()
    assert not gemini(gemini_ok(), key="").enabled()
    assert gemini(gemini_ok(), cap=0.5).enabled()


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(429, json={}), ProviderQuota),
        (httpx.Response(403, text="quota exceeded"), ProviderQuota),
        (httpx.Response(500, text="boom"), ProviderError),
        (httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}), ProviderRejected),
        (
            httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "no"}]}}]}),
            ProviderRejected,
        ),
    ],
    ids=["429", "cuota", "500", "bloqueado", "sin-imagen"],
)
def test_gemini_errors_map_to_router_friendly_exceptions(response, error) -> None:
    with pytest.raises(error):
        asyncio.run(gemini(response).fetch(REQUEST))


# ───────────────────────────── router ─────────────────────────────


class Fake:
    """Proveedor de prueba: devuelve imágenes o levanta lo que se le indique, y cuenta llamadas."""

    def __init__(self, name, kind="search", *, outcomes=(), cost=0.0, cap=0.0, on=True) -> None:
        self.name, self.kind = name, kind
        self.outcomes = list(outcomes)
        self.cost, self.daily_cap, self.on = cost, cap, on
        self.calls = 0

    def enabled(self) -> bool:
        return self.on

    def unit_cost(self) -> float:
        return self.cost

    async def fetch(self, request: ImageRequest) -> ProviderImage:
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else "ok"
        if isinstance(outcome, Exception):
            raise outcome
        return ProviderImage(
            data=jpeg(), mime="image/jpeg", provider=self.name, cost_usd=self.cost,
            credit={"provider": self.name},
        )  # fmt: skip


def make_router(*providers):
    storage, cache, usage = MemoryStorage(), MemoryImageCache(), MemoryProviderUsage()
    return ImageRouter(list(providers), cache, usage, storage), storage, cache, usage


def get(router, request=REQUEST, user=USER):
    return asyncio.run(router.get(user_id=user, request=request))


def test_router_uses_the_first_provider_that_can_and_caches_the_scene() -> None:
    first, second = Fake("a"), Fake("b")
    router, storage, cache, _ = make_router(first, second)
    image = get(router)
    assert image.provider == "a" and not image.from_cache and (first.calls, second.calls) == (1, 0)
    assert Image.open(io.BytesIO(image.jpeg)).size == (1080, 1350)
    assert (
        image.storage_path.startswith(f"{USER}/ads/_images/")
        and image.storage_path in storage.objects
    )
    again = get(router)
    assert again.from_cache and again.provider == "a" and first.calls == 1  # sin gastar nada
    assert again.credit == {"provider": "a"}
    assert len(cache.rows) == 1


def test_the_cache_is_per_user_and_per_format() -> None:
    router, *_ = make_router(Fake("a"))
    get(router)
    assert not get(router, user=uuid4()).from_cache  # otro usuario no comparte imágenes
    vertical = ImageRequest(REQUEST.prompt, REQUEST.keywords, "9:16")
    assert not get(router, vertical).from_cache


def test_a_provider_without_quota_is_skipped_for_the_rest_of_the_day() -> None:
    paid = Fake("gemini", "generate", outcomes=[ProviderQuota("429")], cost=0.034, cap=1.0)
    free = Fake("pixabay")
    router, _, _, usage = make_router(paid, free)
    assert get(router).provider == "pixabay"  # la reserva atiende la petición
    assert usage.rows[("gemini", str(router.today()))]["exhausted"] is True
    other = ImageRequest("otra escena", ("coffee", "desk"), "4:5")
    assert get(router, other).provider == "pixabay"
    assert paid.calls == 1  # no se vuelve a intentar hoy


def test_the_daily_usd_cap_stops_a_paid_provider_before_calling_it() -> None:
    paid = Fake("gemini", "generate", cost=0.034, cap=0.07)  # alcanza para 2 imágenes
    free = Fake("pixabay")
    router, _, _, usage = make_router(paid, free)
    scenes = [ImageRequest(f"escena {i}", ("desk",), "4:5") for i in range(4)]
    providers = [get(router, s).provider for s in scenes]
    assert providers == ["gemini", "gemini", "pixabay", "pixabay"]
    assert paid.calls == 2
    row = usage.rows[("gemini", str(router.today()))]
    assert row["requests"] == 2 and row["cost_usd"] == pytest.approx(0.068)


def test_errors_fall_through_to_the_next_provider_and_none_means_text_only() -> None:
    broken = Fake("a", outcomes=[ProviderError("500"), RuntimeError("inesperado")])
    rejecting = Fake("b", outcomes=[ProviderRejected("sin fotos"), UnusableImage("chica")])
    router, storage, cache, _ = make_router(broken, rejecting)
    assert get(router) is None and not cache.rows and not storage.objects
    assert get(router) is None  # un error inesperado tampoco tumba el lote
    assert get(router).provider == "a"  # al volver a intentar, el primero ya responde


def test_disabled_providers_are_ignored_and_the_order_is_respected() -> None:
    off, on = Fake("off", on=False), Fake("on")
    router, *_ = make_router(off, on)
    assert get(router).provider == "on" and off.calls == 0
    assert router.active() == ["on"]
    empty, *_ = make_router(Fake("x", on=False))
    assert get(empty) is None and empty.active() == []


def test_an_unusable_download_moves_on_to_the_next_provider() -> None:
    class Tiny(Fake):
        async def fetch(self, request):
            return ProviderImage(data=jpeg((200, 200)), mime="image/jpeg", provider=self.name)

    router, *_ = make_router(Tiny("tiny"), Fake("ok"))
    assert get(router).provider == "ok"


def test_build_router_follows_env_order_ignores_unknown_names_and_keeps_gemini_off() -> None:
    settings = Settings(
        _env_file=None,
        image_providers="gemini, pixabay, desconocido",
        gemini_api_key="g",
        pixabay_api_key="p",
    )
    router = build_router(settings, MemoryImageCache(), MemoryProviderUsage(), MemoryStorage())
    assert [p.name for p in router.providers] == ["gemini", "pixabay"]
    assert router.active() == ["pixabay"]  # sin tope diario, Gemini no gasta
    paid = Settings(
        _env_file=None, image_providers="gemini", gemini_api_key="g", gemini_daily_usd_cap=1
    )
    assert build_router(
        paid, MemoryImageCache(), MemoryProviderUsage(), MemoryStorage()
    ).active() == ["gemini"]
    default = Settings(_env_file=None)
    assert default.image_providers == ["pixabay"] and default.gemini_daily_usd_cap == 0


def test_scene_hash_ignores_case_and_spaces_but_not_meaning() -> None:
    a = ImageRequest("Orderly Desk ", ("Desk", "notebook"), "4:5")
    b = ImageRequest("orderly desk", ("desk", " notebook"), "4:5")
    assert a.scene_hash(USER) == b.scene_hash(USER)
    assert a.scene_hash(USER) != ImageRequest("orderly desk", ("desk",), "4:5").scene_hash(USER)
    assert a.scene_hash(USER) != ImageRequest(
        a.prompt, a.keywords, "4:5", sensitive=True
    ).scene_hash(USER)


# ───────────────────────────── plantilla con foto ─────────────────────────────


def stripes(size=(1080, 1350), light=True) -> bytes:
    """Foto de prueba muy clara (peor caso para texto claro) o muy oscura."""
    image = Image.new("RGB", size, (250, 250, 245) if light else (10, 10, 20))
    return fit_image_bytes(image)


def fit_image_bytes(image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="JPEG")
    return out.getvalue()


def test_the_photo_template_needs_a_photo_and_never_flags_the_full_bleed_background() -> None:
    with pytest.raises(MissingImage):
        R.compose(
            template_id="photo_headline",
            copy=copy(),
            ratio="4x5",
            product_template=BOLD,
            market="es-LATAM",
        )
    for ratio, size in {"4x5": (1080, 1350), "9x16": (1080, 1920), "1x1": (1080, 1080)}.items():
        png, report = R.render_with_report(
            template_id="photo_headline", copy=copy(), ratio=ratio, product_template=BOLD,
            market="es-LATAM", bg_jpeg=stripes(size),
        )  # fmt: skip
        assert Image.open(io.BytesIO(png)).size == size and report.outside == []


def test_the_veil_gets_stronger_over_a_bright_photo_and_text_stays_readable() -> None:
    spec = R.ratios["4x5"]
    palette = BOLD.palette
    bright = photo_veil(stripes(light=True), palette.primary, palette.on_primary, spec)
    dark = photo_veil(stripes(light=False), palette.primary, palette.on_primary, spec)
    assert 0.35 <= dark < bright <= 0.9
    png, _ = R.render_with_report(
        template_id="photo_headline", copy=copy(), ratio="4x5", product_template=BOLD,
        market="es-LATAM", bg_jpeg=stripes(light=True),
    )  # fmt: skip
    pixel = Image.open(io.BytesIO(png)).convert("RGB").getpixel((5, 5))  # esquina: solo foto + velo
    assert sum(pixel) < 3 * 200  # la foto blanca ya no es blanca: el velo la oscureció


# ───────────────────────────── las 12 plantillas ─────────────────────────────

PAIR = ["Pedidos en chats sueltos", "Fechas en la memoria", "Un solo lugar", "Responsable y fecha"]
VARIANTS = {
    "headline_bold": {},
    "photo_headline": {},
    "product_mockup": {},
    "checklist": {},
    "note": {},
    "text_post": {},
    "notification": {},
    "before_after": {"bullets": PAIR},
    "comparison": {"bullets": PAIR},
    "question": {"headline": "¿Cuántos pedidos se te perdieron este mes?"},
    "testimonial": {"note": "Lo apliqué en una semana", "subheadline": "A. M."},
    "offer_stack": {},
}
HEADLINES = [
    "Corto",
    "Capturas, notas y chats: el pedido nunca aparece",
    "Un sistema completo para ordenar tus pedidos del mes sin perder fechas",
]


@pytest.mark.parametrize("ratio", ["4x5", "9x16", "1x1"])
@pytest.mark.parametrize("template", sorted(VARIANTS))
@pytest.mark.parametrize("headline", HEADLINES)
def test_every_template_fits_the_safe_zone_and_never_overlaps_text(
    template: str, ratio: str, headline: str
) -> None:
    c = copy(**{"headline": headline, **VARIANTS[template]})
    spec = R.ratios[ratio]
    mockup = None
    if R.templates[template].uses_mockup:
        from tests.test_ads_render import mockup as make_mockup

        mockup = make_mockup()
    pdf, report = R.compose(
        template_id=template, copy=c, ratio=ratio, product_template=BOLD, market="es-LATAM",
        product_name="Bandeja Única", mockup_png=mockup,
        bg_jpeg=stripes((spec.width, spec.height)) if R.templates[template].uses_image else None,
    )  # fmt: skip
    assert report.outside == [], (template, ratio, headline)
    assert overlapping(text_boxes(pdf)) == [], (template, ratio, headline)


def test_comparison_labels_and_testimonial_quote_are_native_to_each_market() -> None:
    def text(template, market, **over):
        c = copy(**{**VARIANTS[template], **over})
        pdf, _ = R.compose(
            template_id=template, copy=c, ratio="4x5", product_template=BOLD, market=market
        )
        doc = pdfium.PdfDocument(pdf)
        try:
            # Los rótulos llevan espaciado entre letras: se compara sin espacios.
            return "".join(doc[0].get_textpage().get_text_range().split()).upper()
        finally:
            doc.close()

    assert "DESPUÉS" in text("before_after", "es-LATAM")
    assert "DEPOIS" in text("before_after", "pt-BR")
    assert "LODESIEMPRE" in text("comparison", "es-LATAM")
    assert "ODESEMPRE" in text("comparison", "pt-BR")
    assert "—A.M." in text("testimonial", "es-LATAM")


def test_the_untrusted_note_of_a_testimonial_is_escaped() -> None:
    hostile = copy(note="<script>alert(1)</script> {{ 7*7 }}", subheadline="<b>x</b>")
    pdf, _ = R.compose(
        template_id="testimonial",
        copy=hostile,
        ratio="4x5",
        product_template=BOLD,
        market="es-LATAM",
    )
    doc = pdfium.PdfDocument(pdf)
    try:
        page_text = doc[0].get_textpage().get_text_range()
    finally:
        doc.close()
    assert "<script>" in page_text and "{{ 7*7 }}" in page_text and "49" not in page_text


# ───────────────────────────── reglas de las plantillas nuevas ─────────────────────────────

PROOF = proof(text="Lo apliqué en una semana y entendí mis gastos", id="p1")


def errors(template, proofs=(), **over):
    d = draft(template, **over)
    return rules.check_draft(d, allowed_templates=[template], brief=brief(), proofs=list(proofs))


def test_paired_templates_need_two_or_four_bullets() -> None:
    for template in ("before_after", "comparison"):
        assert errors(template, bullets=PAIR) == []
        assert errors(template, bullets=PAIR[:2]) == []
        assert any("2 o 4" in e for e in errors(template, bullets=PAIR[:3]))
        assert any("2 o 4" in e for e in errors(template, bullets=[]))


def test_offer_stack_needs_a_real_price_and_a_list() -> None:
    items = ["Guía paso a paso", "Plantilla de captura", "Respuestas rápidas"]
    assert errors("offer_stack", bullets=items, price_text="USD 12") == []
    assert any("3 y 5" in e for e in errors("offer_stack", bullets=items[:2]))
    no_price = rules.check_draft(
        draft("offer_stack", bullets=items),
        allowed_templates=["offer_stack"],
        brief=brief(price_text=""),
        proofs=[],
    )
    assert any("precio real" in e for e in no_price)
    invented = errors("offer_stack", bullets=items, price_text="USD 5 (antes USD 50)")
    assert any("price_text" in e for e in invented)


def test_photo_headline_needs_a_scene_and_keywords() -> None:
    assert errors("photo_headline") == []
    assert any("stock_keywords" in e for e in errors("photo_headline", stock_keywords=["a"]))
    assert any("scene" in e for e in errors("photo_headline", scene=""))


def test_a_testimonial_can_only_quote_a_real_proof_verbatim() -> None:
    good = errors(
        "testimonial", [PROOF], proof_id="p1", note="Lo apliqué en una semana", subheadline="A. M."
    )
    assert good == []
    quoted = errors(
        "testimonial", [PROOF], proof_id="p1", note="«lo apliqué en una semana»", subheadline=""
    )
    assert quoted == []  # comillas y mayúsculas no importan
    assert any("proof" in e for e in errors("testimonial", [PROOF], note="Lo apliqué"))
    assert any("proof_id" in e for e in errors("testimonial", [], proof_id="p9", note="x"))
    invented = errors(
        "testimonial", [PROOF], proof_id="p1", note="Me cambió la vida y gané USD 5000"
    )
    assert any("cita textual" in e for e in invented)
    other_author = errors(
        "testimonial",
        [PROOF],
        proof_id="p1",
        note="Lo apliqué en una semana",
        subheadline="Carlos P.",
    )
    assert any("autor" in e for e in other_author)


# ───────────────────────────── el lote con imágenes ─────────────────────────────


def photo_world(router, count=2):
    drafts = [draft("photo_headline") for _ in range(count)]
    reviews = [CreativeReview(index=i, policy=green(), score=score()) for i in range(count)]
    w = AdsWorld(
        [CreativeDrafts(creatives=drafts), CreativeReviews(reviews=reviews)], images=router
    )
    pick = [{"angle_id": "dolor", "avatar": avatar().name, "count": count}]
    response = w.client.post("/ads/batches", json=w.batch_body(picks=pick, ratios=["4x5"]))
    assert response.status_code == 202, response.text
    w.run_worker()
    return w, response.json()["batch_id"]


def render_all(w, batch_id):
    w.client.post(f"/ads/batches/{batch_id}/render", json={})
    w.run_worker()
    return w.client.get(f"/ads/batches/{batch_id}").json()["creatives"]


def test_photo_creatives_record_the_provider_credit_and_cost_and_reuse_the_cache() -> None:
    paid = Fake("gemini", "generate", cost=0.034, cap=1.0)
    router, storage, cache, usage = make_router(paid)
    w, batch_id = photo_world(router)
    router._storage = w.storage  # el storage del mundo es el que sube los PNG
    creatives = render_all(w, batch_id)
    assert len(creatives) == 2 and all(c["status"] == "rendered" for c in creatives)
    # Dos creativos con la misma escena: una sola generación (la segunda sale de la caché).
    assert paid.calls == 1
    assert {c["image_provider"] for c in creatives} == {"gemini"}
    assert sorted(float(c["image_cost_usd"]) for c in creatives) == [0, pytest.approx(0.034)]
    assert all(c["base_image_path"] for c in creatives)
    first = creatives[0]
    # Editar el texto recompone sin volver a pedir la imagen.
    image = {**first["copy"]["image"], "headline": "Otro titular distinto"}
    assert w.client.put(f"/ads/creatives/{first['id']}", json={"image": image}).status_code == 200
    assert paid.calls == 1
    assert Image.open(io.BytesIO(w.storage.objects[first["storage_path"]])).size == (1080, 1350)


def test_without_any_image_the_creative_falls_back_to_the_text_template() -> None:
    router, *_ = make_router(Fake("a", outcomes=[ProviderError("x")] * 5))
    w, batch_id = photo_world(router)
    creatives = render_all(w, batch_id)
    assert all(c["status"] == "rendered" for c in creatives)  # el lote no se cae
    assert {c["template_id"] for c in creatives} == {FALLBACK_TEMPLATE}
    assert all(c["copy"]["template_id"] == FALLBACK_TEMPLATE for c in creatives)
    assert all(
        "headlinebold" in c["filename"] and "photoheadline" not in c["filename"] for c in creatives
    )
    assert len({c["filename"] for c in creatives}) == 2  # nombres únicos (v1 y v2)
    assert all(c["image_provider"] is None and c["base_image_path"] is None for c in creatives)
    assert all(c["storage_path"].endswith(c["filename"]) for c in creatives)


def test_templates_offered_to_the_ai_depend_on_images_price_and_proofs() -> None:
    w = AdsWorld()
    deps = w.services.ads()
    plain = available_templates(deps, brief(price_text=""), [])
    assert (
        "photo_headline" not in plain and "offer_stack" not in plain and "testimonial" not in plain
    )
    deps.images = make_router(Fake("a"))[0]
    full = available_templates(deps, brief(price_text="USD 12"), [PROOF])
    assert len(full) == 12
    assert "photo_headline" in full and "offer_stack" in full and "testimonial" in full


def test_image_status_lists_providers_without_secrets() -> None:
    router, *_ = make_router(Fake("pixabay", on=True), Fake("gemini", "generate", on=False))
    w = AdsWorld(images=router)
    data = w.client.get("/ads/images/status").json()
    assert data["providers"] == [
        {"name": "pixabay", "kind": "search", "enabled": True},
        {"name": "gemini", "kind": "generate", "enabled": False},
    ]
    assert data["photo_templates"] is True
    assert "key" not in str(data).lower()
