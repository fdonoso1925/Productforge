"""Creativos, fase 6: aprendizaje, importación de Ads Manager, iteraciones y lote en otro idioma."""

from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.ads import learning, results_import
from app.ads.learning import Metrics, build_insights, rank
from app.ads.results_import import (
    ReportError,
    match_creatives,
    parse_day,
    parse_number,
    parse_report,
)
from app.ads.schemas import (
    AdaptedBrief,
    AngleProposals,
    AngleSuggestion,
    AvatarProposals,
    CreativeDrafts,
    CreativeReview,
    CreativeReviews,
)
from tests.test_ads_strategy import avatar, draft, green, score
from tests.test_api_ads import USER, AdsWorld, plan_responses

TODAY = date.today()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()


def res(creative, spend=0, impressions=0, clicks=0, purchases=0, revenue=0, day=YESTERDAY) -> dict:
    return {
        "creative_id": creative,
        "day": day,
        "spend": spend,
        "impressions": impressions,
        "clicks": clicks,
        "purchases": purchases,
        "revenue": revenue,
    }


# ───────────────────────────── métricas y ranking ─────────────────────────────


def test_metrics_are_derived_from_totals_and_never_divide_by_zero() -> None:
    m = Metrics()
    assert (m.ctr, m.cpc, m.cpa, m.roas) == (None, None, None, None)
    m.add(res("a", spend=50, impressions=4000, clicks=80, purchases=2, revenue=150))
    m.add(
        res("a", spend=50, impressions=6000, clicks=120, purchases=3, revenue=350, day="2026-01-02")
    )
    assert (m.spend, m.impressions, m.clicks, m.purchases) == (100, 10000, 200, 5)
    assert m.ctr == 2.0 and m.cpc == 0.5 and m.cpa == 20.0 and m.roas == 5.0
    assert m.enough_data
    assert not Metrics(impressions=999).enough_data and Metrics(impressions=1000).enough_data
    no_revenue = Metrics(spend=10, purchases=1)
    assert no_revenue.roas is None and no_revenue.cpa == 10.0


def metrics(**kw) -> Metrics:
    return Metrics(**{"impressions": 5000, **kw})


def test_without_sales_the_ranking_is_by_ctr_and_ignores_thin_data() -> None:
    items = {
        "a": metrics(clicks=50),  # 1,0 %
        "b": metrics(clicks=150),  # 3,0 %
        "c": Metrics(impressions=200, clicks=100),  # 50 %, pero con 200 impresiones es ruido
        "d": metrics(clicks=0),
    }
    ranking = rank(items)
    assert ranking.metric == "ctr"
    assert ranking.order == ["b", "a", "d", "c"]  # lo que no tiene datos suficientes va al final
    assert ranking.winners == ["b", "a"]  # sin clics no se gana; c nunca gana


def test_with_sales_the_ranking_uses_roas_when_everyone_has_revenue_else_cpa() -> None:
    both = {
        "a": metrics(spend=100, purchases=2, revenue=150),  # roas 1,5
        "b": metrics(spend=100, purchases=4, revenue=500),  # roas 5
        "c": metrics(spend=100, clicks=500),  # no vendió
    }
    r = rank(both)
    assert r.metric == "roas" and r.order == ["b", "a", "c"] and r.winners == ["b", "a"]
    mixed = {
        "a": metrics(spend=100, purchases=2),  # cpa 50, sin valor de conversión
        "b": metrics(spend=100, purchases=5, revenue=300),  # cpa 20
    }
    r = rank(mixed)
    assert r.metric == "cpa" and r.order == ["b", "a"]


def test_no_data_means_no_winners_and_at_most_three_are_named() -> None:
    assert rank({}).metric == "none" and rank({"a": Metrics(impressions=10)}).winners == []
    many = {k: metrics(clicks=10 * (i + 1)) for i, k in enumerate("abcde")}
    assert rank(many).winners == ["e", "d", "c"]


def creative(id_, angle="dolor", template="headline_bold", group=None, status="rendered") -> dict:
    d = draft(template).model_dump(mode="json")
    return {
        "id": id_,
        "batch_id": "b1",
        "group_id": group or id_,
        "angle": angle,
        "template_id": template,
        "status": status,
        "filename": f"{id_}.png",
        "copy": d,
    }


def test_insights_group_by_angle_template_and_hook_and_skip_discarded() -> None:
    creatives = [
        creative("c1", "dolor", "headline_bold", group="g1"),
        creative("c2", "dolor", "headline_bold", group="g1"),  # otro formato del mismo borrador
        creative("c3", "mito", "checklist", group="g3"),
        creative("c4", "mito", "checklist", group="g4", status="discarded"),
    ]
    results = [
        res("c1", spend=10, impressions=3000, clicks=90),
        res("c2", spend=10, impressions=2000, clicks=10),
        res("c3", spend=5, impressions=5000, clicks=250),
        res("c4", spend=99, impressions=99999, clicks=99999),  # descartado: no cuenta
        res("zz", spend=1, impressions=1, clicks=1),  # de otro lote: no cuenta
    ]
    data = build_insights(creatives, results, {"b1": {}})
    assert data["totals"]["spend"] == 25 and data["creatives_with_results"] == 3
    angles = {a["key"]: a for a in data["angles"]["items"]}
    assert angles["dolor"]["impressions"] == 5000 and angles["dolor"]["clicks"] == 100
    assert angles["mito"]["impressions"] == 5000 and angles["mito"]["clicks"] == 250
    assert data["angles"]["metric"] == "ctr" and data["winner_angles"] == ["mito", "dolor"]
    hooks = data["hooks"]["items"]
    assert {h["key"] for h in hooks} == {"g1", "g3"}  # los formatos de un borrador se suman
    assert hooks[0]["headline"] and hooks[0]["creative_id"] in ("c1", "c3")
    assert {t["key"] for t in data["templates"]["items"]} == {"headline_bold", "checklist"}
    assert learning.MIN_IMPRESSIONS == data["min_impressions"]


# ───────────────────────────── lectura del CSV de Ads Manager ─────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.234,56", 1234.56),
        ("1,234.56", 1234.56),
        ("12,5", 12.5),
        ("12.5", 12.5),
        ("45.000", 45000.0),
        ("1.234", 1234.0),
        ("0.500", 0.5),
        ("2.35", 2.35),
        ("1,234", 1234.0),
        ("1.234.567", 1234567.0),
        ("$ 3.40", 3.4),
        ("R$ 1.200,00", 1200.0),
        ("2,35 %", 2.35),
        ("1 234", 1234.0),
        ("", 0.0),
        ("-", 0.0),
        ("—", 0.0),
        ("abc", None),
        ("%", None),
    ],
)
def test_numbers_in_es_pt_and_en_formats(raw: str, expected) -> None:
    assert parse_number(raw) == expected


def test_days_in_iso_and_latin_formats() -> None:
    assert parse_day("2026-03-04") == date(2026, 3, 4)
    assert parse_day("04/03/2026") == date(2026, 3, 4)  # día/mes/año, como en es y pt
    assert parse_day("04-03-2026 00:00") == date(2026, 3, 4)
    assert parse_day("04.03.2026") == date(2026, 3, 4)
    assert parse_day("ayer") is None and parse_day("") is None


ES_REPORT = (
    "Nombre del anuncio;Inicio del informe;Importe gastado (USD);Impresiones;"
    "Clics en el enlace;CTR (porcentaje de clics en el enlace);Clics (todos);Compras;"
    "Valor de conversión de compras\n"
    "bandeja_4x5_v1;2026-03-04;1.234,50;45.000;900;2,00;1.100;12;1.800,00\n"
    "bandeja_1x1_v1;2026-03-04;100,00;8.000;40;0,50;60;0;0\n"
    "Total;;1.334,50;53.000;940;;;12;1.800,00\n"
)


def test_parses_a_spanish_report_with_semicolons_and_thousands_separators() -> None:
    report = parse_report(ES_REPORT.encode("utf-8-sig"))
    assert len(report.rows) == 2 and report.invalid == 0  # la fila «Total» no tiene nombre
    first = report.rows[0]
    assert (first.name, first.day) == ("bandeja_4x5_v1", date(2026, 3, 4))
    assert (first.spend, first.impressions, first.clicks) == (
        1234.5,
        45000,
        900,
    )  # enlaces, no «todos»
    assert (first.purchases, first.revenue) == (12, 1800.0)
    assert {"name", "spend", "impressions", "clicks", "purchases", "revenue"} <= set(report.columns)


def test_parses_portuguese_and_english_headers_and_derives_revenue_from_roas() -> None:
    pt = (
        "Nome do anúncio,Valor usado (BRL),Impressões,Cliques no link,Compras,"
        "ROAS de compras (retorno sobre o investimento em publicidade)\n"
        "kit_4x5_v1,200.50,10000,300,5,3.5\n"
    )
    row = parse_report(pt.encode()).rows[0]
    assert (row.spend, row.impressions, row.clicks, row.purchases) == (200.5, 10000, 300, 5)
    assert row.revenue == pytest.approx(701.75)  # roas × gasto
    assert row.day == date.today()  # sin columna de fecha: el día de la importación
    en = "Ad name,Reporting starts,Amount spent (USD),Impressions,Link clicks,Purchases\nx,2026-01-02,10,1000,20,1\n"
    assert parse_report(en.encode()).rows[0].day == date(2026, 1, 2)


def test_report_encodings_and_delimiters() -> None:
    latin = "Nombre del anuncio\tImpresiones\tClics en el enlace\ncafé_4x5_v1\t5000\t100\n".encode(
        "latin-1"
    )
    row = parse_report(latin).rows[0]
    assert row.name == "café_4x5_v1" and row.clicks == 100
    utf16 = "Ad name,Impressions,Link clicks\nx,100,1\n".encode("utf-16")
    assert parse_report(utf16).rows[0].impressions == 100


def test_bad_numbers_are_counted_not_guessed_and_negative_values_are_rejected() -> None:
    text = "Ad name,Amount spent,Impressions,Link clicks\nok,10,1000,5\nbad,abc,1000,5\nneg,-10,1000,5\n"
    report = parse_report(text.encode())
    assert [r.name for r in report.rows] == ["ok"] and report.invalid == 2


@pytest.mark.parametrize(
    "data",
    [b"", b"Impresiones,Clics\n1,2\n", b"Ad name\nx\n", "A" * (results_import.MAX_BYTES + 1)],
    ids=["vacio", "sin-nombre", "sin-metricas", "enorme"],
)
def test_unusable_files_are_rejected_with_a_clear_error(data) -> None:
    with pytest.raises(ReportError):
        parse_report(data if isinstance(data, bytes) else data.encode())


def test_rows_are_capped() -> None:
    body = "Ad name,Impressions\n" + "".join(
        f"a{i},10\n" for i in range(results_import.MAX_ROWS + 50)
    )
    assert len(parse_report(body.encode()).rows) == results_import.MAX_ROWS


def rows_for(*names):
    return parse_report(
        ("Ad name,Impressions\n" + "".join(f"{n},10\n" for n in names)).encode()
    ).rows


def test_matching_is_by_file_name_without_extension_and_never_guesses() -> None:
    creatives = [
        {"id": "1", "filename": "bandeja_dolor_4x5_v1.png", "status": "rendered"},
        {"id": "2", "filename": "bandeja_dolor_1x1_v1.png", "status": "rendered"},
        {"id": "3", "filename": "repetido_4x5_v1.png", "status": "rendered"},
        {"id": "4", "filename": "repetido_4x5_v1.png", "status": "rendered"},
        {"id": "5", "filename": "descartado_4x5_v1.png", "status": "discarded"},
    ]
    names = [
        "bandeja_dolor_4x5_v1",  # exacto
        "BANDEJA_DOLOR_1X1_V1.PNG",  # extensión y mayúsculas
        "Campaña A | bandeja_dolor_4x5_v1 | copia",  # el nombre contenido en el del anuncio
        "repetido_4x5_v1",  # dos creativos con el mismo nombre: ambiguo
        "descartado_4x5_v1",  # un creativo descartado no recibe resultados
        "no_existe",
    ]
    match = match_creatives(rows_for(*names), creatives)
    assert [c["id"] for _, c in match.matched] == ["1", "2", "1"]
    assert match.ambiguous == ["repetido_4x5_v1"]
    assert sorted(match.unmatched) == ["descartado_4x5_v1", "no_existe"]


# ───────────────────────────── API: resultados ─────────────────────────────


def world_with_batch(extra=()):
    w = AdsWorld([*plan_responses(), *extra])
    batch_id = w.client.post("/ads/batches", json=w.batch_body()).json()["batch_id"]
    w.run_worker()
    creatives = w.client.get(f"/ads/batches/{batch_id}").json()["creatives"]
    return w, batch_id, creatives


def body(**over) -> dict:
    return {
        "day": YESTERDAY,
        "spend": 20,
        "impressions": 4000,
        "clicks": 80,
        "purchases": 2,
        "revenue": 90,
        **over,
    }


def test_manual_results_are_validated_saved_and_replaced_per_day() -> None:
    w, _, creatives = world_with_batch()
    cid = creatives[0]["id"]
    assert w.client.put(f"/ads/creatives/{cid}/results", json=body()).status_code == 200
    w.client.put(f"/ads/creatives/{cid}/results", json=body(spend=30))  # mismo día: reemplaza
    listed = w.client.get(f"/ads/creatives/{cid}/results").json()
    assert len(listed) == 1 and listed[0]["spend"] == 30 and listed[0]["source"] == "manual"
    w.client.put(f"/ads/creatives/{cid}/results", json=body(day="2026-01-01"))
    assert len(w.client.get(f"/ads/creatives/{cid}/results").json()) == 2

    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    for bad in (
        body(day=tomorrow),
        body(clicks=5000),  # más clics que impresiones
        body(clicks=0, purchases=1),  # compras sin clics
        body(spend=-1),
        body(impressions=-5),
        {"day": "no-es-fecha"},
    ):
        assert w.client.put(f"/ads/creatives/{cid}/results", json=bad).status_code == 422, bad


def test_results_are_private_and_can_be_deleted_only_by_their_owner() -> None:
    w, _, creatives = world_with_batch()
    cid = creatives[0]["id"]
    w.client.put(f"/ads/creatives/{cid}/results", json=body())
    stranger = w.as_user(str(uuid4()))
    assert w.client.get(f"/ads/creatives/{cid}/results", headers=stranger).status_code == 404
    assert (
        w.client.put(f"/ads/creatives/{cid}/results", json=body(), headers=stranger).status_code
        == 404
    )
    rid = w.client.get(f"/ads/creatives/{cid}/results").json()[0]["id"]
    assert w.client.delete(f"/ads/results/{rid}", headers=stranger).status_code == 404
    assert w.client.delete(f"/ads/results/{rid}").status_code == 204
    assert w.client.get(f"/ads/creatives/{cid}/results").json() == []


def csv_for(creatives, rows) -> bytes:
    header = "Nombre del anuncio;Inicio del informe;Importe gastado (USD);Impresiones;Clics en el enlace;Compras\n"
    lines = "".join(
        f"{c['filename']};{day};{spend};{imp};{clk};{buy}\n"
        for c, day, spend, imp, clk, buy in rows
    )
    return (header + lines).encode("utf-8-sig")


def test_import_matches_by_file_name_merges_same_day_rows_and_is_idempotent() -> None:
    w, _, creatives = world_with_batch()
    a, b = creatives[0], creatives[1]
    data = (
        csv_for(
            creatives,
            [
                (a, YESTERDAY, "10,50", "2.000", 40, 1),
                (
                    a,
                    YESTERDAY,
                    "4,50",
                    "1.000",
                    10,
                    0,
                ),  # mismo anuncio y día (otro conjunto): se suma
                (b, YESTERDAY, "5,00", "3.000", 30, 0),
            ],
        )
        + b"desconocido;"
        + YESTERDAY.encode()
        + b";1;100;1;0\n"
    )
    response = w.client.post("/ads/results/import", content=data)
    assert response.status_code == 200, response.text
    out = response.json()
    assert (out["rows"], out["matched"], out["imported"]) == (4, 3, 2)
    assert out["unmatched"] == ["desconocido"] and out["ambiguous"] == [] and out["invalid"] == 0
    stored = {r["creative_id"]: r for r in w.results.rows.values()}
    assert stored[a["id"]]["spend"] == 15 and stored[a["id"]]["impressions"] == 3000
    assert stored[a["id"]]["clicks"] == 50 and stored[a["id"]]["source"] == "csv"
    w.client.post("/ads/results/import", content=data)  # volver a importar no duplica
    assert len(w.results.rows) == 2 and {r["spend"] for r in w.results.rows.values()} == {15, 5}


def test_import_rejects_bad_files_and_only_matches_the_users_own_creatives() -> None:
    w, _, creatives = world_with_batch()
    assert w.client.post("/ads/results/import", content=b"").status_code == 422
    assert w.client.post("/ads/results/import", content=b"hola,mundo\n1,2\n").status_code == 422
    big = b"x" * (results_import.MAX_BYTES + 200_000)
    assert w.client.post("/ads/results/import", content=big).status_code == 413
    data = csv_for(creatives, [(creatives[0], YESTERDAY, "1", "1000", 5, 0)])
    stranger = w.as_user(str(uuid4()))
    out = w.client.post("/ads/results/import", content=data, headers=stranger).json()
    assert out["matched"] == 0 and len(out["unmatched"]) == 1 and w.results.rows == {}


# ───────────────────────────── API: aprendizaje ─────────────────────────────


def load_results(w, creatives, *, angle_boost=True):
    """Ángulo `mecanismo` con CTR alto y buenas ventas."""
    for c in creatives:
        w.client.put(
            f"/ads/creatives/{c['id']}/results",
            json=body(
                spend=50,
                impressions=5000,
                clicks=250 if angle_boost else 5,
                purchases=5,
                revenue=400,
            ),
        )


def test_insights_show_winners_and_can_be_filtered_by_market_and_niche() -> None:
    w, _, creatives = world_with_batch()
    empty = w.client.get("/ads/insights").json()
    assert empty["creatives_with_results"] == 0 and empty["winner_angles"] == []
    load_results(w, creatives)
    data = w.client.get("/ads/insights").json()
    assert data["creatives_with_results"] == 4 and data["winner_angles"] == ["mecanismo"]
    assert data["angles"]["metric"] == "roas"
    top = data["angles"]["items"][0]
    assert (
        top["key"] == "mecanismo"
        and top["winner"]
        and top["roas"] == 8.0
        and top["purchases"] == 20
    )
    assert data["hooks"]["items"] and data["templates"]["items"]
    assert w.client.get("/ads/insights", params={"market": "es-LATAM"}).json()["winner_angles"] == [
        "mecanismo"
    ]
    assert w.client.get("/ads/insights", params={"market": "pt-BR"}).json()["winner_angles"] == []
    assert w.client.get("/ads/insights", params={"niche": "PRODUCTIVIDAD"}).json()[
        "winner_angles"
    ] == ["mecanismo"]
    assert w.client.get("/ads/insights", params={"niche": "otro"}).json()["winner_angles"] == []
    assert w.client.get("/ads/insights", params={"market": "fr"}).status_code == 422
    stranger = w.as_user(str(uuid4()))
    assert w.client.get("/ads/insights", headers=stranger).json()["creatives_with_results"] == 0


def test_the_next_batch_prioritizes_the_winning_angles() -> None:
    angles_response = AngleProposals(
        angles=[
            AngleSuggestion(angle_id=a, avatar=avatar().name, why="funcionó")
            for a in ("mecanismo", "dolor", "transformacion", "persona", "objecion")
        ]
    )
    w, _, creatives = world_with_batch([angles_response])
    load_results(w, creatives)
    response = w.client.post(
        "/ads/angles",
        json={
            "product_id": w.product["id"],
            "avatars": [avatar().model_dump()],
            "price_text": "USD 12",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["winners"] == ["mecanismo"]
    sent = w.llm.calls[-1].user
    assert '"winners"' in sent and "mecanismo" in sent.split('"winners"')[1][:80]
    # Sin resultados, no hay ganadores que priorizar.
    fresh = AdsWorld([angles_response])
    out = fresh.client.post(
        "/ads/angles", json={"product_id": fresh.product["id"], "avatars": [avatar().model_dump()]}
    ).json()
    assert out["winners"] == []


# ───────────────────────────── iterar ─────────────────────────────


def iterate_responses(count=1):
    drafts = [
        draft("checklist", headline=f"Otro gancho {i} para tus pedidos") for i in range(count)
    ]
    reviews = [CreativeReview(index=i, policy=green(), score=score(8)) for i in range(count)]
    return [CreativeDrafts(creatives=drafts), CreativeReviews(reviews=reviews)]


def test_iterating_a_creative_adds_new_hooks_linked_to_it_with_its_metrics_in_the_prompt() -> None:
    w, batch_id, creatives = world_with_batch(iterate_responses(2))
    source = creatives[0]
    w.client.put(
        f"/ads/creatives/{source['id']}/results", json=body(impressions=5000, clicks=100, spend=40)
    )
    calls = len(w.llm.calls)
    response = w.client.post(f"/ads/creatives/{source['id']}/iterate", json={"count": 2})
    assert response.status_code == 202, response.text
    assert w.batches.rows[batch_id]["status"] == "planning"
    assert (
        w.client.post(f"/ads/creatives/{source['id']}/iterate", json={}).status_code == 409
    )  # ya en curso
    w.run_worker()

    assert len(w.llm.calls) == calls + 2  # el texto nuevo y su revisión
    prompt = w.llm.calls[calls].user
    assert "iterate_from" in prompt and source["copy"]["image"]["headline"] in prompt
    assert '"ctr": 2.0' in prompt and '"impressions": 5000' in prompt  # lo que ya se probó
    rows = w.creatives.rows.values()
    new = [c for c in rows if c.get("parent_creative_id") == source["id"]]
    assert len(new) == 4  # 2 hooks × los 2 formatos del borrador original
    assert {c["ratio"] for c in new} == {"4x5", "1x1"} and {c["status"] for c in new} == {"planned"}
    assert len({c["group_id"] for c in new}) == 2 and source["group_id"] not in {
        c["group_id"] for c in new
    }
    assert len({c["filename"] for c in rows}) == len(list(rows))  # nombres siempre únicos
    assert all(c["angle"] == source["angle"] and c["avatar"] == source["avatar"] for c in new)
    assert all(c["policy_status"] == "green" and c["pre_score"] == 8 for c in new)
    assert w.batches.rows[batch_id]["status"] == "review"
    assert w.jobs.rows[response.json()["job_id"]]["status"] == "done"


def test_a_failed_iteration_leaves_the_batch_and_its_creatives_untouched() -> None:
    w, batch_id, creatives = world_with_batch([RuntimeError("sin créditos")])
    before = {c["id"] for c in w.creatives.rows.values()}
    job = w.client.post(f"/ads/creatives/{creatives[0]['id']}/iterate", json={"count": 1}).json()
    w.run_worker()
    assert w.jobs.rows[job["job_id"]]["status"] == "error"
    assert w.batches.rows[batch_id]["status"] == "review"  # no queda trabado ni pasa a error
    assert {c["id"] for c in w.creatives.rows.values()} == before


def test_iterate_validates_ownership_state_and_count() -> None:
    w, _, creatives = world_with_batch()
    cid = creatives[0]["id"]
    stranger = w.as_user(str(uuid4()))
    assert (
        w.client.post(f"/ads/creatives/{cid}/iterate", json={}, headers=stranger).status_code == 404
    )
    for bad in ({"count": 0}, {"count": 4}):
        assert w.client.post(f"/ads/creatives/{cid}/iterate", json=bad).status_code == 422
    w.client.post(f"/ads/creatives/{cid}/discard")
    assert w.client.post(f"/ads/creatives/{cid}/iterate", json={}).status_code == 409


# ───────────────────────────── variantes sin IA ─────────────────────────────


def test_a_variant_in_another_format_stays_in_the_draft_and_costs_nothing() -> None:
    w, batch_id, creatives = world_with_batch()
    source = next(c for c in creatives if c["ratio"] == "4x5")
    calls = len(w.llm.calls)
    response = w.client.post(f"/ads/creatives/{source['id']}/variant", json={"ratio": "9x16"})
    assert response.status_code == 201, response.text
    new = response.json()
    assert len(w.llm.calls) == calls  # sin IA
    assert new["ratio"] == "9x16" and new["group_id"] == source["group_id"]
    assert new["parent_creative_id"] == source["id"] and new["status"] == "planned"
    assert new["copy"] == source["copy"] and new["filename"] != source["filename"]
    assert "9x16" in new["filename"]
    # El mismo formato dos veces dentro del mismo borrador no tiene sentido.
    assert (
        w.client.post(f"/ads/creatives/{source['id']}/variant", json={"ratio": "9x16"}).status_code
        == 409
    )


def test_a_variant_with_another_template_is_a_new_draft_with_the_same_text() -> None:
    w, _, creatives = world_with_batch()
    source = next(
        c for c in creatives if c["template_id"] == "product_mockup" and c["ratio"] == "4x5"
    )
    response = w.client.post(
        f"/ads/creatives/{source['id']}/variant", json={"template_id": "checklist"}
    )
    assert response.status_code == 201, response.text
    new = response.json()
    assert new["template_id"] == "checklist" and new["copy"]["template_id"] == "checklist"
    assert new["group_id"] != source["group_id"] and new["ratio"] == source["ratio"]
    assert new["copy"]["image"] == source["copy"]["image"]
    assert "checklist" in new["filename"]
    # Se puede repetir: el nombre nuevo no choca (v2).
    again = w.client.post(
        f"/ads/creatives/{source['id']}/variant", json={"template_id": "checklist"}
    ).json()
    names = [c["filename"] for c in w.creatives.rows.values()]
    assert again["filename"] != new["filename"] and len(set(names)) == len(names)


def test_variants_pass_through_the_same_rules_as_any_text() -> None:
    w, _, creatives = world_with_batch()
    source = creatives[0]
    post = lambda **b: w.client.post(f"/ads/creatives/{source['id']}/variant", json=b)  # noqa: E731
    assert post().status_code == 422  # sin nada que cambiar
    assert post(template_id="no_existe").status_code == 422
    assert post(template_id="photo_headline").status_code == 422  # sin proveedor de imágenes
    assert post(template_id="testimonial").status_code == 422  # sin pruebas
    assert post(ratio="16x9").status_code == 422
    assert post(template_id="Checklist; drop").status_code == 422
    # El texto tiene 3 ítems: «antes y después» exige 2 o 4, y la regla es la misma que para la IA.
    assert post(template_id="before_after").status_code == 422
    assert post(template_id="offer_stack").status_code == 201  # 3 ítems y precio real: vale
    stranger = w.as_user(str(uuid4()))
    assert (
        w.client.post(
            f"/ads/creatives/{source['id']}/variant", json={"ratio": "9x16"}, headers=stranger
        ).status_code
        == 404
    )


def test_a_variant_of_a_finished_batch_reopens_it_for_review() -> None:
    w, batch_id, creatives = world_with_batch()
    w.client.post(f"/ads/batches/{batch_id}/render", json={})
    w.run_worker()
    assert w.batches.rows[batch_id]["status"] == "ready"
    w.client.post(f"/ads/creatives/{creatives[0]['id']}/variant", json={"ratio": "9x16"})
    assert w.batches.rows[batch_id]["status"] == "review"


# ───────────────────────────── duplicar a otro idioma ─────────────────────────────


def adapted(bonuses: int = 2) -> AdaptedBrief:
    pt = avatar("Freelancer com clientes no WhatsApp")
    return AdaptedBrief(
        niche="produtividade",
        product_name="Caixa Única",
        problem="Os pedidos se perdem entre chats e e-mails",
        audience="Freelancers e mini agências",
        promise="Um sistema para não perder nenhuma data de entrega",
        bonuses=[f"Bônus {i}" for i in range(bonuses)],
        avatars=[pt],
    )


def test_duplicating_a_batch_adapts_the_brief_keeps_user_facts_and_plans_a_new_batch() -> None:
    extra = [adapted(), *plan_responses()]
    w, batch_id, _ = world_with_batch(extra)
    calls = len(w.llm.calls)
    response = w.client.post(f"/ads/batches/{batch_id}/duplicate", json={"market": "pt-BR"})
    assert response.status_code == 202, response.text
    new_id = response.json()["batch_id"]
    new = w.batches.rows[new_id]
    assert (
        new["parent_batch_id"] == batch_id
        and new["market"] == "pt-BR"
        and new["status"] == "planning"
    )
    assert new["brief"]["product_name"] == "Caixa Única" and new["brief"]["market"] == "pt-BR"
    assert new["brief"]["price_text"] == "USD 12"  # el precio real es del usuario: no se toca
    assert new["niche"] == "produtividade" and new["product_id"] is None
    assert new["avatars"][0]["name"] == "Freelancer com clientes no WhatsApp"
    assert [p["avatar"] for p in new["picks"]] == ["Freelancer com clientes no WhatsApp"]
    assert new["picks"][0]["angle_id"] == "mecanismo" and new["ratios"] == ["4x5", "1x1"]
    assert len(w.llm.calls) == calls + 1  # solo la adaptación; el lote se planifica en el worker
    assert "Adapte para o mercado do Brasil" in w.llm.calls[-1].user  # prompt NATIVO del destino
    w.run_worker()
    assert w.batches.rows[new_id]["status"] == "review"
    assert len([c for c in w.creatives.rows.values() if c["batch_id"] == new_id]) == 4
    assert w.batches.rows[batch_id]["market"] == "es-LATAM"  # el original no cambia


def test_duplicate_needs_the_other_market_and_an_owned_batch() -> None:
    w, batch_id, _ = world_with_batch()
    assert (
        w.client.post(f"/ads/batches/{batch_id}/duplicate", json={"market": "es-LATAM"}).status_code
        == 422
    )
    assert (
        w.client.post(f"/ads/batches/{batch_id}/duplicate", json={"market": "fr"}).status_code
        == 422
    )
    stranger = w.as_user(str(uuid4()))
    assert (
        w.client.post(
            f"/ads/batches/{batch_id}/duplicate", json={"market": "pt-BR"}, headers=stranger
        ).status_code
        == 404
    )


def test_duplicate_numbers_repeated_avatar_names_so_the_batch_stays_valid() -> None:
    twin = AdaptedBrief(**{**adapted().model_dump(), "avatars": [avatar("Igual"), avatar("Igual")]})
    two = AvatarProposals  # noqa: F841 (solo documenta que son avatares del mismo esquema)
    w = AdsWorld(plan_responses() + [twin])
    body_ = w.batch_body(avatars=[avatar("A").model_dump(), avatar("B").model_dump()])
    body_["picks"] = [{"angle_id": "mecanismo", "avatar": "B", "count": 2}]
    batch_id = w.client.post("/ads/batches", json=body_).json()["batch_id"]
    w.run_worker()
    new_id = w.client.post(f"/ads/batches/{batch_id}/duplicate", json={"market": "pt-BR"}).json()[
        "batch_id"
    ]
    names = [a["name"] for a in w.batches.rows[new_id]["avatars"]]
    assert (
        names == ["Igual", "Igual (2)"]
        and w.batches.rows[new_id]["picks"][0]["avatar"] == "Igual (2)"
    )
    assert USER  # el usuario del mundo de prueba es el dueño
