"""Detector de parecidos con la página que se toma de modelo.

De esa página no se guarda su texto: solo una «huella», los hashes de cada grupo de 5 palabras
consecutivas. Al generar o editar, el texto nuevo se parte igual y se cuentan los grupos que ya
estaban. Dos páginas del mismo tema comparten muy pocos grupos de 5 palabras; que compartan muchos,
o una tirada larga seguida, es copiar. También se buscan los nombres de marca de la página modelo.
"""

import base64
import re
import struct
import unicodedata
import zlib
from typing import Any

from app.pages.schemas import PageContent, SimilarityField, SimilarityReport

SHINGLE = 5  # palabras por grupo
MAX_FINGERPRINT = 12_000
MIN_WORDS = 8  # los textos más cortos (botones, títulos de 3 palabras) no se miden

# Umbrales: por debajo de WARN es parecido natural entre páginas del mismo tema.
WARN_RATIO, BLOCK_RATIO = 0.03, 0.08
WARN_RUN, BLOCK_RUN = 9, 14  # palabras seguidas idénticas

_WORD = re.compile(r"[a-z0-9ñ]+")
SKIP = {"seo_title", "seo_description"}


def words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return _WORD.findall(folded)


def _hash(group: list[str]) -> int:
    return zlib.crc32(" ".join(group).encode())


def shingles(tokens: list[str]) -> list[int]:
    return [_hash(tokens[i : i + SHINGLE]) for i in range(len(tokens) - SHINGLE + 1)]


def fingerprint(text: str) -> list[int]:
    """Huella de un texto: hashes únicos de sus grupos de 5 palabras (sin el texto)."""
    return sorted(set(shingles(words(text))))[:MAX_FINGERPRINT]


def brand_pattern(brands: list[str]) -> re.Pattern[str] | None:
    parts = [" ".join(words(b)) for b in brands]
    parts = [p for p in parts if len(p) >= 4]
    if not parts:
        return None
    return re.compile(
        r"\b(?:"
        + "|".join(re.escape(p) for p in sorted(set(parts), key=len, reverse=True))
        + r")\b"
    )


def flatten(value: Any, path: str = "") -> list[tuple[str, str]]:
    """Todos los textos de la página con su ruta (`hero.headline`, `faq.2.a`…)."""
    out: list[tuple[str, str]] = []
    if isinstance(value, str):
        if value.strip() and path.split(".")[0] not in SKIP:
            out.append((path, value))
    elif isinstance(value, dict):
        for k, v in value.items():
            out += flatten(v, f"{path}.{k}" if path else k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out += flatten(v, f"{path}.{i}" if path else str(i))
    return out


def level_for(ratio: float, run: int, brands: list[str]) -> str:
    if brands or ratio >= BLOCK_RATIO or run >= BLOCK_RUN:
        return "block"
    if ratio >= WARN_RATIO or run >= WARN_RUN:
        return "warn"
    return "ok"


def check(
    content: PageContent | dict,
    known: list[int] | set[int],
    brand_terms: list[str],
    own_text: str = "",
) -> SimilarityReport:
    """Compara el texto de la página con la huella de la página modelo.

    `own_text` (nombre del producto y nicho del usuario) evita acusar de copia a una marca que el
    usuario también usa legítimamente."""
    known = set(known)
    data = content.model_dump() if isinstance(content, PageContent) else content
    own = set(words(own_text))
    brand_terms = [b for b in brand_terms if not set(words(b)) <= own]
    pattern = brand_pattern(brand_terms)
    total = hits = longest = 0
    fields: list[SimilarityField] = []
    brands: set[str] = set()
    for path, text in flatten(data):
        tokens = words(text)
        if pattern is not None:
            brands.update(pattern.findall(" ".join(tokens)))
        if len(tokens) < MIN_WORDS or not known:
            continue
        marks = [h in known for h in shingles(tokens)]
        total += len(marks)
        hits += sum(marks)
        run = best = 0
        for hit in marks:
            run = run + 1 if hit else 0
            best = max(best, run)
        run_words = best + SHINGLE - 1 if best else 0
        longest = max(longest, run_words)
        ratio = sum(marks) / len(marks)
        if ratio >= WARN_RATIO or run_words >= WARN_RUN:
            fields.append(SimilarityField(path=path, ratio=round(ratio, 3), run_words=run_words))
    overall = hits / total if total else 0.0
    found = sorted(brands)
    return SimilarityReport(
        level=level_for(overall, longest, found),  # type: ignore[arg-type]
        ratio=round(overall, 4),
        longest_run_words=longest,
        fields=sorted(fields, key=lambda f: (-f.run_words, -f.ratio))[:12],
        brands=found,
    )


def pack(hashes: list[int]) -> str:
    """La huella como texto compacto (4 bytes por grupo) para ir y volver por el cliente."""
    return base64.b64encode(struct.pack(f"<{len(hashes)}I", *hashes)).decode()


def unpack(packed: str) -> list[int]:
    """Lee una huella que vino del cliente: valida tamaño y forma (no es de fiar)."""
    try:
        raw = base64.b64decode(packed, validate=True)
    except ValueError as exc:
        raise ValueError("huella inválida") from exc
    if len(raw) % 4 or len(raw) > MAX_FINGERPRINT * 4:
        raise ValueError("huella inválida")
    return list(struct.unpack(f"<{len(raw) // 4}I", raw))
