"""Creativos, fase 5: CSV de copys, ZIP, URLs de la galería y copia del lote a Google Drive."""

import csv
import io
import zipfile
from uuid import uuid4

import pytest

from app.ads import export
from tests.fake_google import FakeTarget
from tests.test_ads_strategy import draft
from tests.test_api_ads import USER, AdsWorld, plan_responses


def row(**over) -> dict:
    base = {
        "id": str(uuid4()),
        "filename": "bandeja_es-latam_mecanismo_checklist_4x5_v1.png",
        "ratio": "4x5",
        "template_id": "checklist",
        "angle": "mecanismo",
        "avatar": "Freelancer",
        "policy_status": "green",
        "pre_score": 7,
        "copy": draft("checklist").model_dump(mode="json"),
        "image_credit": None,
        "status": "rendered",
    }
    return {**base, **over}


def parse(data: bytes) -> list[list[str]]:
    assert data.startswith(b"\xef\xbb\xbf")  # BOM: Excel respeta tildes y ñ
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))


# ───────────────────────────── CSV ─────────────────────────────


def test_csv_has_native_headers_and_one_row_per_creative() -> None:
    rows = parse(export.build_csv("es-LATAM", [row(), row(ratio="1x1")]))
    assert rows[0][0] == "archivo" and "texto_principal_largo" in rows[0]
    assert len(rows) == 3 and rows[1][1] == "4:5" and rows[2][1] == "1:1"
    assert rows[1][5] == "green" and rows[1][6] == "7"
    pt = parse(export.build_csv("pt-BR", [row()]))
    assert pt[0][0] == "arquivo" and "descricao" in pt[0]


def test_csv_keeps_accents_commas_quotes_and_line_breaks_intact() -> None:
    d = draft(
        "checklist",
        primary_long='Línea uno, con coma y "comillas".\nLínea dos con ñ y acentós. ' * 4,
    )
    out = parse(export.build_csv("es-LATAM", [row(copy=d.model_dump(mode="json"))]))
    assert out[1][11] == d.ad.primary_long and "\n" in out[1][11] and "ñ" in out[1][11]


@pytest.mark.parametrize("payload", ['=HYPERLINK("http://x")', "+1+1", "-2+3", "@SUM(A1)", "\t=1"])
def test_csv_neutralizes_cells_a_spreadsheet_would_run_as_a_formula(payload: str) -> None:
    d = draft("checklist", headline=payload)
    out = parse(export.build_csv("es-LATAM", [row(copy=d.model_dump(mode="json"), avatar=payload)]))
    assert out[1][4].startswith("'") and out[1][7].startswith("'")  # avatar y titular de imagen
    assert not any(cell[:1] in "=+-@\t" for cell in out[1] if cell)


def test_csv_names_the_photo_source() -> None:
    credit = {
        "provider": "pixabay",
        "author": "autora",
        "page_url": "https://pixabay.com/photos/x-1/",
    }
    out = parse(export.build_csv("es-LATAM", [row(image_credit=credit)]))
    assert out[1][15] == "autora · https://pixabay.com/photos/x-1/"
    generated = parse(export.build_csv("es-LATAM", [row(image_credit={"provider": "gemini"})]))
    assert generated[1][15] == "gemini"
    assert parse(export.build_csv("es-LATAM", [row()]))[1][15] == ""


# ───────────────────────────── ZIP ─────────────────────────────

FOLDERS = {"4x5": "feed-4x5", "9x16": "stories-9x16", "1x1": "cuadrado-1x1"}


def test_zip_groups_images_by_format_and_adds_csv_and_credits() -> None:
    a, b = row(), row(ratio="1x1", filename="otro_1x1_v1.png")
    credit = {
        "provider": "pixabay",
        "author": "autora",
        "page_url": "https://pixabay.com/photos/x-1/",
    }
    c = row(filename="foto_4x5_v1.png", image_credit=credit)
    data = export.build_zip(
        "es-LATAM", [a, b, c], {a["id"]: b"AAA", b["id"]: b"BBB", c["id"]: b"CCC"}, FOLDERS
    )
    z = zipfile.ZipFile(io.BytesIO(data))
    assert sorted(z.namelist()) == sorted(
        [
            f"feed-4x5/{a['filename']}",
            "cuadrado-1x1/otro_1x1_v1.png",
            "feed-4x5/foto_4x5_v1.png",
            "copys.csv",
            "creditos-imagenes.txt",
        ]
    )
    assert z.read("cuadrado-1x1/otro_1x1_v1.png") == b"BBB"
    assert "autora" in z.read("creditos-imagenes.txt").decode()
    plain = zipfile.ZipFile(io.BytesIO(export.build_zip("es-LATAM", [a], {a["id"]: b"A"}, FOLDERS)))
    assert "creditos-imagenes.txt" not in plain.namelist()


def test_zip_refuses_an_oversized_batch_and_skips_creatives_without_image() -> None:
    a = row()
    with pytest.raises(export.ExportTooLarge):
        export.build_zip("es-LATAM", [a], {a["id"]: b"x" * (export.MAX_ZIP_BYTES + 1)}, FOLDERS)
    z = zipfile.ZipFile(io.BytesIO(export.build_zip("es-LATAM", [a], {}, FOLDERS)))
    assert z.namelist() == ["copys.csv"]


def test_drive_folder_is_stable_and_readable() -> None:
    batch = {
        "id": "abcdef123",
        "market": "es-LATAM",
        "niche": "Productividad Pro",
        "created_at": "2026-10-22T10:00:00Z",
    }
    assert export.drive_folder(batch, "Bandeja Única") == (
        "es-LATAM/productividad-pro/anuncios_2026-10-22_bandeja-unica_abcdef"
    )


# ───────────────────────────── API ─────────────────────────────


def rendered_world(drive=None):
    w = AdsWorld(plan_responses(), drive=drive)
    batch_id = w.client.post("/ads/batches", json=w.batch_body()).json()["batch_id"]
    w.run_worker()
    return w, batch_id


def render_everything(w, batch_id):
    w.client.post(f"/ads/batches/{batch_id}/render", json={})
    w.run_worker()


def test_urls_endpoint_signs_only_rendered_creatives_of_the_owner() -> None:
    w, batch_id = rendered_world()
    assert w.client.post(f"/ads/batches/{batch_id}/urls").json() == {}  # nada compuesto aún
    render_everything(w, batch_id)
    urls = w.client.post(f"/ads/batches/{batch_id}/urls").json()
    assert len(urls) == 4 and all(u.startswith("https://storage.test/") for u in urls.values())
    assert (
        w.client.post(f"/ads/batches/{batch_id}/urls", headers=w.as_user(str(uuid4()))).status_code
        == 404
    )


def test_export_returns_a_zip_and_a_csv_with_every_rendered_image() -> None:
    w, batch_id = rendered_world()
    assert w.client.post(f"/ads/batches/{batch_id}/export").status_code == 409  # sin imágenes
    render_everything(w, batch_id)
    response = w.client.post(f"/ads/batches/{batch_id}/export")
    assert response.status_code == 200
    out = response.json()
    assert (
        out["images"] == 4
        and out["zip_name"].endswith(".zip")
        and out["zip_url"].startswith("https://")
    )
    base = f"{USER}/ads/{batch_id}/export/"
    zips = [k for k in w.storage.objects if k.startswith(base) and k.endswith(".zip")]
    z = zipfile.ZipFile(io.BytesIO(w.storage.objects[zips[0]]))
    names = z.namelist()
    assert "copys.csv" in names and sum(n.endswith(".png") for n in names) == 4
    assert any(n.startswith("feed-4x5/") for n in names) and any(
        n.startswith("cuadrado-1x1/") for n in names
    )
    assert (
        w.client.post(
            f"/ads/batches/{batch_id}/export", headers=w.as_user(str(uuid4()))
        ).status_code
        == 404
    )


def test_discarded_creatives_stay_out_of_the_export() -> None:
    w, batch_id = rendered_world()
    render_everything(w, batch_id)
    first = w.client.get(f"/ads/batches/{batch_id}").json()["creatives"][0]
    w.client.post(f"/ads/creatives/{first['id']}/discard")
    assert w.client.post(f"/ads/batches/{batch_id}/export").json()["images"] == 3


# ───────────────────────────── Google Drive ─────────────────────────────


def test_drive_copy_needs_configuration_connection_images_and_no_other_copy_running() -> None:
    w, batch_id = rendered_world(FakeTarget(configured=False))
    assert w.client.post(f"/ads/batches/{batch_id}/drive").status_code == 503
    w, batch_id = rendered_world(FakeTarget(connected=False))
    assert w.client.post(f"/ads/batches/{batch_id}/drive").status_code == 409  # sin conexión
    w, batch_id = rendered_world(FakeTarget())
    assert w.client.post(f"/ads/batches/{batch_id}/drive").status_code == 409  # sin imágenes
    render_everything(w, batch_id)
    assert w.client.post(f"/ads/batches/{batch_id}/drive").status_code == 202
    assert w.client.post(f"/ads/batches/{batch_id}/drive").status_code == 409  # ya en curso
    assert (
        w.client.post(f"/ads/batches/{batch_id}/drive", headers=w.as_user(str(uuid4()))).status_code
        == 404
    )


def test_drive_copy_uploads_images_and_csv_into_one_folder_and_reports_progress() -> None:
    target = FakeTarget()
    w, batch_id = rendered_world(target)
    render_everything(w, batch_id)
    w.client.post(f"/ads/batches/{batch_id}/drive")
    assert w.client.get(f"/ads/batches/{batch_id}/drive").json()["status"] == "uploading"
    w.run_worker()

    paths = [p for _, p, _, _ in target.uploads]
    assert len(paths) == 5  # 4 imágenes + el CSV
    folder = "es-LATAM/productividad/anuncios_"
    assert all(p.startswith(folder) for p in paths)
    assert (
        sum(p.endswith(".png") for p in paths) == 4
        and sum(p.endswith("/copys.csv") for p in paths) == 1
    )
    assert {p.split("/")[-2] for p in paths if p.endswith(".png")} == {"feed-4x5", "cuadrado-1x1"}
    assert {m for *_, m in target.uploads} == {"image/png", "text/csv"}
    status = w.client.get(f"/ads/batches/{batch_id}/drive").json()
    assert status["status"] == "done" and (
        status["uploaded"],
        status["total"],
        status["failed"],
    ) == (5, 5, 0)
    assert status["folder_url"].startswith("https://drive.test/folder/")
    assert all(c["remote_url"] for c in w.creatives.rows.values())
    assert w.storage.objects  # Storage sigue siendo la fuente de verdad
    assert w.batches.rows[batch_id]["status"] == "ready"  # Drive no cambia el estado del lote


def test_a_failed_file_marks_the_copy_as_error_but_uploads_the_rest() -> None:
    target = FakeTarget(fail=("feed-4x5/" + "x",))
    w, batch_id = rendered_world(target)
    render_everything(w, batch_id)
    victim = next(c for c in w.creatives.rows.values() if c["ratio"] == "1x1")
    target.fail = (victim["filename"],)
    w.client.post(f"/ads/batches/{batch_id}/drive")
    w.run_worker()
    status = w.client.get(f"/ads/batches/{batch_id}/drive").json()
    assert status["status"] == "error" and status["failed"] == 1 and status["uploaded"] == 4
    assert w.batches.rows[batch_id]["status"] == "ready"
    # Reintentar sube todo de nuevo (los archivos se reemplazan en su lugar).
    target.fail = ()
    w.client.post(f"/ads/batches/{batch_id}/drive")
    w.run_worker()
    assert w.client.get(f"/ads/batches/{batch_id}/drive").json()["status"] == "done"


def test_a_revoked_connection_stops_the_copy_without_touching_the_batch() -> None:
    target = FakeTarget(raise_not_connected=True)
    w, batch_id = rendered_world(target)
    render_everything(w, batch_id)
    w.client.post(f"/ads/batches/{batch_id}/drive")
    w.run_worker()
    assert w.client.get(f"/ads/batches/{batch_id}/drive").json()["status"] == "error"
    assert w.batches.rows[batch_id]["status"] == "ready" and w.storage.objects
