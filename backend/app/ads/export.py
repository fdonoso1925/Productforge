"""Entrega de un lote: CSV de copys para Ads Manager, ZIP con las imágenes y carpeta de Drive.

El texto de los anuncios viene de la IA o del usuario, así que el CSV neutraliza las celdas que
Excel o Sheets interpretarían como fórmula (`=`, `+`, `-`, `@`).
"""

import csv
import io
import zipfile
from datetime import date

from app.generators.base import slugify

MAX_ZIP_BYTES = 200 * 1024 * 1024  # un lote real pesa unas decenas de MB
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")

HEADERS = {
    "es-LATAM": [
        "archivo", "formato", "plantilla", "angulo", "avatar", "semaforo", "pre_score",
        "titular_imagen", "subtitular_imagen", "cta_imagen",
        "texto_principal_corto", "texto_principal_largo", "titular", "descripcion", "boton_cta",
        "origen_imagen",
    ],
    "pt-BR": [
        "arquivo", "formato", "template", "angulo", "avatar", "semaforo", "pre_score",
        "titulo_imagem", "subtitulo_imagem", "cta_imagem",
        "texto_principal_curto", "texto_principal_longo", "titulo", "descricao", "botao_cta",
        "origem_imagem",
    ],
}  # fmt: skip
CREDITS_TITLE = {
    "es-LATAM": "Créditos de las imágenes (Pixabay Content License)",
    "pt-BR": "Créditos das imagens (Pixabay Content License)",
}


def safe_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_START) else text


def image_source(creative: dict) -> str:
    credit = creative.get("image_credit") or {}
    if credit.get("page_url"):
        return f"{credit.get('author') or ''} · {credit['page_url']}".strip(" ·")
    return credit.get("provider") or ""


def build_csv(market: str, creatives: list[dict]) -> bytes:
    """CSV en UTF-8 con BOM (así Excel respeta tildes y ñ), una fila por creativo."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(HEADERS[market])
    for c in creatives:
        copy = c["copy"]
        image, ad = copy["image"], copy["ad"]
        writer.writerow(
            [
                safe_cell(v)
                for v in (
                    c["filename"],
                    c["ratio"].replace("x", ":"),
                    c["template_id"],
                    c["angle"],
                    c["avatar"],
                    c.get("policy_status") or "",
                    c.get("pre_score") or "",
                    image["headline"],
                    image.get("subheadline", ""),
                    image.get("cta_text", ""),
                    ad["primary_short"],
                    ad["primary_long"],
                    ad["headline"],
                    ad["description"],
                    ad["cta"],
                    image_source(c),
                )
            ]
        )
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")


def credits_text(market: str, creatives: list[dict]) -> str:
    lines = sorted({f"{c['filename']}: {image_source(c)}" for c in creatives if image_source(c)})
    return f"{CREDITS_TITLE[market]}\n\n" + "\n".join(lines) + "\n" if lines else ""


class ExportTooLarge(Exception):
    pass


def build_zip(
    market: str, creatives: list[dict], images: dict[str, bytes], folders: dict[str, str]
) -> bytes:
    """ZIP con `<carpeta del formato>/<archivo>.png`, `copys.csv` y, si hay fotos, sus créditos.

    `images` mapea el id del creativo a su PNG; `folders`, el id de formato a su carpeta."""
    if sum(len(b) for b in images.values()) > MAX_ZIP_BYTES:
        raise ExportTooLarge
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for c in creatives:
            png = images.get(c["id"])
            if png is not None:
                z.writestr(
                    f"{folders[c['ratio']]}/{c['filename']}", png, compress_type=zipfile.ZIP_STORED
                )
        z.writestr("copys.csv", build_csv(market, creatives), compress_type=zipfile.ZIP_DEFLATED)
        credits = credits_text(market, creatives)
        if credits:
            z.writestr("creditos-imagenes.txt", credits, compress_type=zipfile.ZIP_DEFLATED)
    return out.getvalue()


def batch_slug(batch: dict, brief_name: str) -> str:
    return f"{slugify(brief_name, 40)}_{batch['id'][:6]}"


def drive_folder(batch: dict, brief_name: str) -> str:
    """Carpeta en Drive: `<mercado>/<nicho>/anuncios_<YYYY-MM-DD>_<producto>_<id6>`."""
    day = (batch.get("created_at") or "")[:10] or date.today().isoformat()
    name = batch_slug(batch, brief_name)
    return f"{batch['market']}/{slugify(batch['niche'])}/anuncios_{day}_{name}"
