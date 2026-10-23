"""Recorrido completo del módulo Creativos por la API, con IA, imágenes y Drive simulados.

Cubre los criterios de aceptación del módulo: un lote de ≥3 ángulos × 2 variantes en 4:5 y 9:16,
copy y semáforo por creativo, nada inventado, edición sin IA, Gemini sin cuota → Pixabay sin
errores, resultados → ganadores → siguiente lote, y entrega (ZIP, CSV y Drive)."""

import io
import zipfile

from PIL import Image

from app.ads.images.base import ProviderQuota
from app.ads.schemas import (
    AngleProposals,
    AngleSuggestion,
    AvatarProposals,
    CreativeDrafts,
    CreativeReview,
    CreativeReviews,
)
from tests.fake_google import FakeTarget
from tests.test_ads_images import Fake, make_router
from tests.test_ads_strategy import avatar, draft, green, score
from tests.test_api_ads import AdsWorld

QUOTE = "Lo apliqué en una semana y entendí mis gastos"
SIZES = {"4x5": (1080, 1350), "9x16": (1080, 1920)}


def reviews(n: int) -> CreativeReviews:
    return CreativeReviews(
        reviews=[CreativeReview(index=i, policy=green(), score=score(7 + i % 2)) for i in range(n)]
    )


def test_full_ads_flow_from_a_product_to_winners_and_delivery() -> None:
    gemini = Fake("gemini", "generate", outcomes=[ProviderQuota("429")] * 8, cost=0.034, cap=1.0)
    pixabay = Fake("pixabay")
    router, _, _, usage = make_router(gemini, pixabay)
    target = FakeTarget()
    w = AdsWorld(images=router, drive=target)
    router._storage = w.storage  # el mismo Storage que sube los PNG
    client = w.client

    # 1. Pruebas REALES del usuario: lo único que los anuncios pueden citar.
    proof = client.post(
        "/ads/proofs", json={"kind": "testimonial", "text": QUOTE, "author": "A. M."}
    ).json()

    # 2. Avatares y ángulos (IA simulada). Con una prueba cargada aparece el ángulo «autoridad».
    angle_ids = ("mecanismo", "dolor", "autoridad", "objecion", "transformacion")
    w.llm.responses += [
        AvatarProposals(avatars=[avatar("A"), avatar("B")]),
        AngleProposals(
            angles=[AngleSuggestion(angle_id=a, avatar="A", why="funciona") for a in angle_ids]
        ),
    ]
    brief = {"product_id": w.product["id"], "price_text": "USD 12"}
    assert client.post("/ads/avatars", json=brief).status_code == 200
    proposed = client.post(
        "/ads/angles",
        json={**brief, "avatars": [avatar("A").model_dump(), avatar("B").model_dump()]},
    ).json()
    assert "autoridad" in {a["id"] for a in proposed["available"]}
    assert proposed["winners"] == []  # todavía no hay resultados

    # 3. Lote: 3 ángulos × 2 variantes, en 4:5 y 9:16.
    quote_draft = draft("testimonial", proof_id=proof["id"], note=QUOTE[:30], subheadline="A. M.")
    invented = draft("testimonial", proof_id=proof["id"], note="Gané USD 5000 en un mes")
    w.llm.responses += [
        CreativeDrafts(creatives=[draft("product_mockup"), draft("checklist")]),
        reviews(2),
        CreativeDrafts(creatives=[draft("headline_bold"), draft("photo_headline")]),
        reviews(2),
        # La IA intenta inventar un testimonio: las reglas lo rechazan y se le pide corregirlo.
        CreativeDrafts(creatives=[invented, draft("headline_bold", proof_id=proof["id"])]),
        CreativeDrafts(creatives=[quote_draft, draft("headline_bold", proof_id=proof["id"])]),
        reviews(2),
    ]
    picks = [
        {"angle_id": "mecanismo", "avatar": "A", "count": 2},
        {"angle_id": "dolor", "avatar": "A", "count": 2},
        {"angle_id": "autoridad", "avatar": "B", "count": 2},
    ]
    created = client.post(
        "/ads/batches",
        json={
            **brief,
            "avatars": [avatar("A").model_dump(), avatar("B").model_dump()],
            "picks": picks,
            "ratios": ["4x5", "9x16"],
        },
    )
    assert created.status_code == 202, created.text
    batch_id = created.json()["batch_id"]
    w.run_worker()
    state = client.get(f"/ads/batches/{batch_id}").json()
    creatives = state["creatives"]
    assert (
        state["batch"]["status"] == "review" and len(creatives) == 12
    )  # 6 borradores × 2 formatos
    assert {c["angle"] for c in creatives} == {"mecanismo", "dolor", "autoridad"}
    assert {c["ratio"] for c in creatives} == {"4x5", "9x16"}
    # Copy completo, semáforo y pre-score con explicación en cada creativo.
    for c in creatives:
        ad = c["copy"]["ad"]
        assert ad["primary_short"] and ad["primary_long"] and ad["headline"] and ad["cta"]
        assert c["policy_status"] in ("green", "yellow", "red") and 1 <= c["pre_score"] <= 10
        assert c["score_notes"]["explanation"] and c["score_notes"]["improvement"]
    # Nada inventado: todo testimonio cita textualmente la prueba real y no hay cifras de la nada.
    quoted = [c for c in creatives if c["template_id"] == "testimonial"]
    assert quoted and all(c["copy"]["image"]["note"] in QUOTE for c in quoted)
    assert all("5000" not in str(c["copy"]) for c in creatives)
    assert all(c["copy"]["proof_id"] == proof["id"] for c in creatives if c["angle"] == "autoridad")
    assert w.storage.objects == {}  # planificar no compone ni gasta imágenes

    # 4. Componer con Gemini sin cuota: el lote se completa igual con Pixabay.
    calls = len(w.llm.calls)
    assert client.post(f"/ads/batches/{batch_id}/render", json={}).status_code == 202
    w.run_worker()
    assert len(w.llm.calls) == calls  # componer no usa IA
    state = client.get(f"/ads/batches/{batch_id}").json()
    creatives = state["creatives"]
    assert state["batch"]["status"] == "ready" and state["job"] is None
    assert {c["status"] for c in creatives} == {"rendered"}  # ningún error visible
    for c in creatives:
        image = Image.open(io.BytesIO(w.storage.objects[c["storage_path"]]))
        assert image.size == SIZES[c["ratio"]] and image.format == "PNG"
    photos = [c for c in creatives if c["copy"]["template_id"] == "photo_headline"]
    assert len(photos) == 2 and {c["image_provider"] for c in photos} == {"pixabay"}
    assert all(float(c["image_cost_usd"]) == 0 for c in creatives)  # costo de imágenes: USD 0
    assert usage.rows[("gemini", str(router.today()))]["exhausted"] is True
    assert gemini.calls == 1  # una sola vez: después se salta por el resto del día

    # 5. Editar un texto y recomponer: segundos y sin IA.
    target_creative = next(c for c in creatives if c["template_id"] == "checklist")
    before = w.storage.objects[target_creative["storage_path"]]
    image = {**target_creative["copy"]["image"], "headline": "Tus pedidos, en una sola lista"}
    edited = client.put(f"/ads/creatives/{target_creative['id']}", json={"image": image})
    assert edited.status_code == 200 and len(w.llm.calls) == calls
    assert w.storage.objects[target_creative["storage_path"]] != before

    # 6. Resultados de Ads Manager (CSV) → ganadores.
    header = (
        "Nombre del anuncio;Inicio del informe;Importe gastado (USD);Impresiones;"
        "Clics en el enlace;Compras\n"
    )
    rows = ""
    for c in creatives:
        strong = c["angle"] == "mecanismo"
        rows += (
            f"{c['filename']};2026-10-22;{'30,00' if strong else '25,00'};"
            f"{'6.000' if strong else '5.000'};{'180' if strong else '40'};{4 if strong else 0}\n"
        )
    imported = client.post(
        "/ads/results/import", content=(header + rows).encode("utf-8-sig")
    ).json()
    assert imported["matched"] == 12 and imported["unmatched"] == [] and imported["ambiguous"] == []
    insights = client.get("/ads/insights").json()
    assert insights["winner_angles"] == ["mecanismo"] and insights["angles"]["metric"] == "cpa"

    # 7. El siguiente lote prioriza los ángulos ganadores.
    w.llm.responses.append(
        AngleProposals(angles=[AngleSuggestion(angle_id=a, avatar="A", why="x") for a in angle_ids])
    )
    next_batch = client.post(
        "/ads/angles", json={**brief, "avatars": [avatar("A").model_dump()]}
    ).json()
    assert next_batch["winners"] == ["mecanismo"]
    sent = "".join(w.llm.calls[-1].user.split())  # el JSON del prompt, sin espacios
    assert '"winners":["mecanismo"]' in sent  # la IA recibe los ganadores

    # 8. Entrega: ZIP con imágenes y copys, CSV y copia a Drive.
    export = client.post(f"/ads/batches/{batch_id}/export").json()
    assert export["images"] == 12
    zipped = next(
        v
        for k, v in w.storage.objects.items()
        if k.endswith(".zip") and f"/{batch_id}/export/" in k
    )
    names = zipfile.ZipFile(io.BytesIO(zipped)).namelist()
    assert sum(n.endswith(".png") for n in names) == 12 and "copys.csv" in names
    assert any(n.startswith("feed-4x5/") for n in names) and any(
        n.startswith("stories-9x16/") for n in names
    )
    assert "creditos-imagenes.txt" in names  # las fotos de Pixabay llevan su autor y licencia
    assert client.post(f"/ads/batches/{batch_id}/drive").status_code == 202
    w.run_worker()
    drive = client.get(f"/ads/batches/{batch_id}/drive").json()
    assert drive["status"] == "done" and drive["uploaded"] == 13 and drive["failed"] == 0
    assert len(target.uploads) == 13  # 12 imágenes + copys.csv
    assert w.batches.rows[batch_id]["status"] == "ready"
