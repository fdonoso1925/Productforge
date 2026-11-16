"""Tipos de cambio diarios para mostrar las ventas de Hotmart en USD.

Fuente: `fawazahmed0/currency-api` (gratuita, sin clave, un archivo por día con todas las monedas,
BRL y COP incluidas), servida por jsDelivr con espejo en Cloudflare Pages. Devuelve cuántas
unidades de cada moneda valen 1 USD. Un día sin dato (futuro, hueco, fallo de red) no rompe nada:
el frontend usa el último tipo de cambio conocido para esa moneda.

Los montos de las ventas se convierten con el tipo de cambio del día de cada venta; la comisión de
Hotmart (`hotmart_fee.total`) ya viene en USD aunque la venta sea en otra moneda (se comprobó con
ventas reales: 6,9 % + 0,50 USD sobre el precio convertido).
"""

import asyncio
import logging
import time
from datetime import date

import httpx

logger = logging.getLogger("productforge.hotmart.fx")

PRIMARY = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{version}/v1/currencies/usd.json"
MIRROR = "https://{version}.currency-api.pages.dev/v1/currencies/usd.json"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)
CONCURRENCY = 8
MAX_DAYS = 1100  # unos tres años de días distintos con ventas
LATEST_TTL = 3600.0


class FxRates:
    """Caché en memoria de tipos de cambio por día (los de días pasados no cambian)."""

    def __init__(self, http: httpx.AsyncClient | None = None) -> None:
        self._http = http
        self._days: dict[str, dict[str, float] | None] = {}
        self._latest: dict[str, float] | None = None
        self._latest_at = 0.0

    async def _fetch(self, client: httpx.AsyncClient, version: str) -> dict[str, float] | None:
        for template in (PRIMARY, MIRROR):
            try:
                response = await client.get(template.format(version=version))
            except httpx.TransportError:
                continue
            if response.status_code != 200:
                continue
            try:
                table = response.json().get("usd") or {}
            except ValueError:
                continue
            rates = {
                str(code).upper(): float(value)
                for code, value in table.items()
                if isinstance(value, int | float) and value > 0
            }
            if rates:
                return rates
        return None

    async def rates(
        self, days: list[date], currencies: list[str]
    ) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
        """Por día y moneda (unidades por 1 USD) y el último tipo de cambio por moneda."""
        wanted = {c.upper() for c in currencies if c.upper() != "USD"}
        if not wanted:
            return {}, {}
        unique = sorted({d.isoformat() for d in days}, reverse=True)[:MAX_DAYS]
        owns = self._http is None
        client = self._http or httpx.AsyncClient(timeout=TIMEOUT, trust_env=False)
        try:
            gate = asyncio.Semaphore(CONCURRENCY)

            async def day(version: str) -> None:
                if version in self._days:
                    return
                async with gate:
                    self._days[version] = await self._fetch(client, version)

            async def newest() -> None:
                # el «último» cambia a diario: se reutiliza una hora
                if self._latest is None or time.monotonic() - self._latest_at > LATEST_TTL:
                    self._latest = await self._fetch(client, "latest") or self._latest
                    self._latest_at = time.monotonic()

            await asyncio.gather(*(day(v) for v in unique), newest())
        finally:
            if owns:
                await client.aclose()
        latest = self._latest or {}
        by_day: dict[str, dict[str, float]] = {}
        for version in unique:
            table = self._days.get(version)
            if table:
                by_day[version] = {c: table[c] for c in wanted if c in table}
        # un día que falló no queda «para siempre» sin intentar: se reintenta en la próxima consulta
        for version in [v for v, t in self._days.items() if t is None]:
            self._days.pop(version, None)
        return by_day, {c: latest[c] for c in wanted if c in latest}
