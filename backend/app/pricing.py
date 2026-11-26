"""Precio de venta y precio normal («de R$ 97 por R$ 47»).

Los dos los da el usuario; la IA nunca los escribe ni los inventa. El código los pone tal cual en
los anuncios y en la página de ventas y calcula el ahorro solo a partir de esas dos cifras reales.
"""

import re

_NUMBER = re.compile(r"\d[\d.,\s]*\d|\d")


def amount(text: str) -> float | None:
    """La cifra de un precio escrito («R$ 47,90», «US$ 1,299.00», «12x de R$ 4,90» → la última
    cifra no sirve: se toma la primera). None si no hay una cifra clara."""
    match = _NUMBER.search(text or "")
    if not match:
        return None
    raw = re.sub(r"\s", "", match.group(0))
    last_dot, last_comma = raw.rfind("."), raw.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        decimal = "," if last_comma > last_dot else "."
    elif last_comma >= 0:
        decimal = "," if len(raw) - last_comma - 1 in (1, 2) else ""
    elif last_dot >= 0:
        decimal = "." if len(raw) - last_dot - 1 in (1, 2) else ""
    else:
        decimal = ""
    thousands = {",", "."} - {decimal}
    for sep in thousands:
        raw = raw.replace(sep, "")
    if decimal:
        raw = raw.replace(decimal, ".")
    try:
        return float(raw)
    except ValueError:
        return None


def savings_percent(base_price_text: str, price_text: str) -> int | None:
    """Cuánto menos cuesta frente al precio normal, redondeado; None si no se puede afirmar
    (falta alguna cifra o el precio normal no es mayor)."""
    base, price = amount(base_price_text), amount(price_text)
    if not base or price is None or price <= 0 or price >= base:
        return None
    return round((1 - price / base) * 100)


def price_errors(price_text: str, base_price_text: str) -> list[str]:
    """Un precio normal solo tiene sentido con un precio de venta menor."""
    if not base_price_text.strip():
        return []
    if not price_text.strip():
        return ["el precio normal necesita también el precio de venta"]
    base, price = amount(base_price_text), amount(price_text)
    if base is None or price is None:
        return ["escribe el precio y el precio normal con su cifra (p. ej. R$ 97 y R$ 47)"]
    if price >= base:
        return ["el precio normal debe ser mayor que el precio de venta"]
    return []
