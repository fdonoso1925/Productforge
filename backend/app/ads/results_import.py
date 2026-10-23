"""Importa el CSV que exporta Ads Manager y lo empareja con los creativos por nombre de archivo.

Ads Manager exporta en el idioma de la cuenta (es, pt o en), con `,` o `;` y con números como
`1.234,56` o `1,234.56`. Todo el archivo es entrada no confiable: se limita su tamaño, se ignoran
las columnas desconocidas y solo se guardan números ya validados.
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
TOTAL_ROWS = {"total", "totales", "totais", "total general", "total geral"}

# Para cada campo, los comienzos de cabecera (ya normalizada) que lo identifican, en orden de
# preferencia: «clics en el enlace» gana a «clics (todos)», y «CTR (… clics en el enlace)» no se
# confunde porque empieza distinto.
HEADERS: dict[str, tuple[str, ...]] = {
    "name": ("nombre del anuncio", "nome do anuncio", "ad name"),
    "day": (
        "dia", "day", "inicio del informe", "inicio dos relatorios", "reporting starts", "date",
    ),
    "spend": ("importe gastado", "valor usado", "amount spent", "gasto"),
    "impressions": ("impresiones", "impressoes", "impressions"),
    "clicks": (
        "clics en el enlace", "cliques no link", "link clicks",
        "clics (todos)", "cliques (todos)", "clicks (all)",
    ),
    "purchases": ("compras", "purchases", "resultados de compras"),
    "revenue": (
        "valor de conversion de compras", "valor de conversao de compras",
        "purchases conversion value", "purchase conversion value",
    ),
    "roas": ("roas de compras", "roas (retorno", "purchase roas", "roas"),
}  # fmt: skip


class ReportError(ValueError):
    """El archivo no se puede leer como un informe de Ads Manager."""


@dataclass
class ParsedRow:
    name: str
    day: date
    spend: float = 0.0
    impressions: int = 0
    clicks: int = 0
    purchases: int = 0
    revenue: float = 0.0


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    invalid: int = 0  # filas con nombre pero con números que no se pudieron leer
    columns: list[str] = field(default_factory=list)  # campos reconocidos (para avisar al usuario)


def normalize(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", plain.lower()).strip()


def parse_number(raw: str) -> float | None:
    """`1.234,56`, `1,234.56`, `12,5 %`, `$ 3.40` → número. Vacío o `-` → 0. Ilegible → None.

    Un único separador seguido de exactamente 3 dígitos (`45.000`, `1,234`) es de MILES: ninguna
    métrica de Ads Manager lleva 3 decimales, y así las impresiones de un export es/pt no se leen
    como 45. Solo `0.xxx` se deja como decimal."""
    text = raw.strip().replace("\xa0", " ")
    if text in ("", "-", "—", "–"):
        return 0.0
    text = re.sub(r"[^\d.,\-]", "", text)
    if not re.search(r"\d", text):
        return None
    negative = text.startswith("-")
    text = text.lstrip("-")
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        text = text.replace(thousands, "").replace(decimal, ".")
    elif "," in text:
        # Varias comas o grupos de 3 dígitos = miles (1,234 / 1,234,567); si no, decimal (12,5).
        text = (
            text.replace(",", "")
            if re.fullmatch(r"\d{1,3}(,\d{3})+", text)
            else text.replace(",", ".")
        )
    elif text.count(".") > 1 or re.fullmatch(r"[1-9]\d{0,2}\.\d{3}", text):
        text = text.replace(".", "")  # 1.234.567 o 45.000
    try:
        value = float(text)
    except ValueError:
        return None
    return -value if negative else value


def parse_day(raw: str) -> date | None:
    text = raw.strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def decode(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise ReportError("el archivo es demasiado grande")
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeError:
            continue
    raise ReportError("no se pudo leer el archivo")


def detect_columns(header: list[str]) -> dict[str, int]:
    normalized = [normalize(h) for h in header]
    found: dict[str, int] = {}
    for field_name, starts in HEADERS.items():
        for start in starts:
            index = next((i for i, h in enumerate(normalized) if h.startswith(start)), None)
            if index is not None and index not in found.values():
                found[field_name] = index
                break
    return found


def stem(name: str) -> str:
    """Nombre sin espacios sobrantes ni extensión de imagen, en minúsculas."""
    return re.sub(r"\.(png|jpe?g|webp)$", "", name.strip(), flags=re.IGNORECASE).lower()


def cell(line: list[str], columns: dict[str, int], name: str) -> str:
    index = columns.get(name)
    return line[index] if index is not None and index < len(line) else ""


def parse_report(data: bytes, today: date | None = None) -> ParseResult:
    text = decode(data)
    sample = text[:4096]
    delimiter = max((",", ";", "\t"), key=sample.count)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        raise ReportError("el archivo está vacío") from None
    columns = detect_columns(header)
    if "name" not in columns:
        raise ReportError("no se encontró la columna con el nombre del anuncio")
    if not {"impressions", "spend", "clicks", "purchases"} & columns.keys():
        raise ReportError("no se encontró ninguna columna de métricas")

    result = ParseResult(columns=sorted(columns))
    default_day = today or date.today()
    for line in reader:
        if len(result.rows) + result.invalid >= MAX_ROWS:
            break
        name = cell(line, columns, "name").strip()
        if not name or normalize(name) in TOTAL_ROWS:  # filas de total o vacías
            continue
        numbers: dict[str, float] = {}
        ok = True
        for f in ("spend", "impressions", "clicks", "purchases", "revenue", "roas"):
            value = parse_number(cell(line, columns, f))
            if value is None or value < 0:
                ok = False
                break
            numbers[f] = value
        if not ok:
            result.invalid += 1
            continue
        revenue = numbers["revenue"] or round(numbers["roas"] * numbers["spend"], 2)
        result.rows.append(
            ParsedRow(
                name=name,
                day=parse_day(cell(line, columns, "day")) or default_day,
                spend=round(numbers["spend"], 2),
                impressions=int(numbers["impressions"]),
                clicks=int(numbers["clicks"]),
                purchases=int(numbers["purchases"]),
                revenue=round(revenue, 2),
            )
        )
    return result


@dataclass
class Match:
    matched: list[tuple[ParsedRow, dict]] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)


def match_creatives(rows: list[ParsedRow], creatives: list[dict]) -> Match:
    """Empareja por nombre de archivo: igual (sin extensión) o contenido en el nombre del anuncio.

    Si un nombre apunta a más de un creativo (mismo archivo en lotes distintos), no se adivina."""
    by_stem: dict[str, list[dict]] = {}
    for c in creatives:
        if c.get("status") != "discarded":
            by_stem.setdefault(stem(c["filename"]), []).append(c)
    match = Match()
    seen: set[str] = set()
    for row in rows:
        key = stem(row.name)
        candidates = by_stem.get(key)
        if not candidates:
            candidates = [c for s, cs in by_stem.items() if s and s in key for c in cs]
        if len(candidates) == 1:
            match.matched.append((row, candidates[0]))
        elif candidates:
            if row.name not in seen:
                match.ambiguous.append(row.name)
        elif row.name not in seen:
            match.unmatched.append(row.name)
        seen.add(row.name)
    return match
