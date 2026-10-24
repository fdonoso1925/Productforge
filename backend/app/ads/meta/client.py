"""Cliente mínimo de la Meta Marketing API (Graph API), hablado directo con `httpx`.

Reglas que este módulo hace cumplir por construcción:
- **Todo nace en PAUSA.** Campaña, conjunto y anuncio se crean con `status=PAUSED` fijo; no existe
  un parámetro para cambiarlo y nada de la app pide activar. Activar (y por tanto gastar) lo hace
  el usuario en Ads Manager.
- El token viaja en la cabecera `Authorization`, nunca en la URL ni en los logs.
- Los errores de Meta se resumen en `MetaError` (código y mensaje de Meta, sin el token).
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("productforge.meta")

GRAPH = "https://graph.facebook.com"
TIMEOUT = httpx.Timeout(60.0, connect=10.0)
MAX_ATTEMPTS = 4
# Códigos de límite de velocidad de la Graph API (app, usuario, cuenta publicitaria).
RATE_LIMIT_CODES = {4, 17, 32, 613, 80000, 80003, 80004}
# Monedas sin decimales: el presupuesto se envía en la unidad, no en centavos.
ZERO_DECIMAL = {"CLP", "ISK", "JPY", "KRW", "PYG", "UGX", "VND", "XAF", "XOF"}

OBJECTIVES = {"traffic": "OUTCOME_TRAFFIC", "sales": "OUTCOME_SALES"}


class MetaError(Exception):
    def __init__(self, message: str, *, code: int | None = None, subcode: int | None = None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode


class MetaNotConfigured(MetaError):
    pass


@dataclass
class AdAccount:
    id: str
    name: str
    currency: str
    status: int  # 1 = activa


def minor_units(amount: float, currency: str) -> int:
    """Presupuesto en la unidad mínima de la moneda (centavos, salvo las monedas sin decimales)."""
    return round(amount) if currency.upper() in ZERO_DECIMAL else round(amount * 100)


def act_id(raw: str) -> str:
    raw = raw.strip()
    return raw if raw.startswith("act_") else f"act_{raw}"


class MetaClient:
    def __init__(
        self,
        *,
        access_token: str,
        ad_account_id: str,
        page_id: str,
        instagram_user_id: str = "",
        pixel_id: str = "",
        version: str = "v25.0",
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = access_token
        self.account = act_id(ad_account_id) if ad_account_id.strip() else ""
        self.page_id = page_id.strip()
        self.instagram_user_id = instagram_user_id.strip()
        self.pixel_id = pixel_id.strip()
        self._base = f"{GRAPH}/{version}"
        self._http = http
        self._currency: str | None = None

    def configured(self) -> bool:
        return bool(self._token and self.account and self.page_id)

    # ───────────────────────── HTTP ─────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict:
        if not self.configured():
            raise MetaNotConfigured("Meta no está configurado")
        # Los valores que no son texto (listas, objetos) viajan como JSON, como pide la Graph API.
        body = {
            k: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
            for k, v in (params or {}).items()
            if v is not None
        }
        headers = {"Authorization": f"Bearer {self._token}"}
        owns = self._http is None
        client = self._http or httpx.AsyncClient(timeout=TIMEOUT, trust_env=False)
        try:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    if method == "GET":
                        response = await client.get(
                            f"{self._base}/{path}", params=body, headers=headers
                        )
                    else:
                        response = await client.post(
                            f"{self._base}/{path}", data=body, files=files, headers=headers
                        )
                except httpx.TransportError as exc:
                    if attempt == MAX_ATTEMPTS:
                        raise MetaError(f"sin conexión con Meta ({type(exc).__name__})") from exc
                    await asyncio.sleep(2**attempt)
                    continue
                if response.status_code < 400:
                    return response.json()
                error = _error_of(response)
                retryable = response.status_code >= 500 or error.code in RATE_LIMIT_CODES
                if retryable and attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(2**attempt)
                    continue
                raise error
        finally:
            if owns:
                await client.aclose()
        raise MetaError("Meta no respondió")  # pragma: no cover

    async def _paginate(self, path: str, params: dict[str, Any]) -> list[dict]:
        out: list[dict] = []
        page = await self._request("GET", path, params=params)
        while True:
            out.extend(page.get("data", []))
            after = (page.get("paging") or {}).get("cursors", {}).get("after")
            if not after or not (page.get("paging") or {}).get("next"):
                return out
            page = await self._request("GET", path, params={**params, "after": after})

    # ───────────────────────── cuenta ─────────────────────────

    async def account_info(self) -> AdAccount:
        data = await self._request(
            "GET", self.account, params={"fields": "name,currency,account_status"}
        )
        self._currency = data.get("currency", "USD")
        return AdAccount(
            id=self.account,
            name=data.get("name", ""),
            currency=self._currency or "USD",
            status=int(data.get("account_status", 0)),
        )

    async def currency(self) -> str:
        if self._currency is None:
            await self.account_info()
        return self._currency or "USD"

    # ───────────────────────── creación (siempre en pausa) ─────────────────────────

    async def upload_image(self, filename: str, data: bytes) -> str:
        """Sube un PNG a la biblioteca de imágenes de la cuenta y devuelve su `hash`."""
        result = await self._request(
            "POST", f"{self.account}/adimages", files={"filename": (filename, data, "image/png")}
        )
        images = result.get("images") or {}
        try:
            return next(iter(images.values()))["hash"]
        except (StopIteration, KeyError, TypeError) as exc:
            raise MetaError("Meta no devolvió el hash de la imagen") from exc

    async def create_campaign(self, name: str, objective: str) -> str:
        result = await self._request(
            "POST",
            f"{self.account}/campaigns",
            params={
                "name": name,
                "objective": OBJECTIVES[objective],
                "status": "PAUSED",
                "special_ad_categories": [],
                # El presupuesto va en el conjunto de anuncios, no compartido en la campaña.
                "is_adset_budget_sharing_enabled": False,
            },
        )
        return str(result["id"])

    async def create_adset(
        self,
        *,
        name: str,
        campaign_id: str,
        objective: str,
        daily_budget: float,
        countries: list[str],
        age_min: int = 18,
        age_max: int = 65,
    ) -> str:
        currency = await self.currency()
        params: dict[str, Any] = {
            "name": name,
            "campaign_id": campaign_id,
            "status": "PAUSED",
            "daily_budget": str(minor_units(daily_budget, currency)),
            "billing_event": "IMPRESSIONS",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "targeting": {
                "geo_locations": {"countries": countries},
                "age_min": age_min,
                "age_max": age_max,
                "targeting_automation": {"advantage_audience": 0},
            },
        }
        if objective == "sales":
            if not self.pixel_id:
                raise MetaError("el objetivo «ventas» necesita META_PIXEL_ID")
            params["optimization_goal"] = "OFFSITE_CONVERSIONS"
            params["promoted_object"] = {"pixel_id": self.pixel_id, "custom_event_type": "PURCHASE"}
        else:
            params["optimization_goal"] = "LINK_CLICKS"
        result = await self._request("POST", f"{self.account}/adsets", params=params)
        return str(result["id"])

    async def create_creative(
        self,
        *,
        name: str,
        image_hash: str,
        link: str,
        message: str,
        headline: str,
        description: str,
        cta: str,
    ) -> str:
        spec: dict[str, Any] = {
            "page_id": self.page_id,
            "link_data": {
                "image_hash": image_hash,
                "link": link,
                "message": message,
                "name": headline,
                "description": description,
                "call_to_action": {"type": cta, "value": {"link": link}},
            },
        }
        if self.instagram_user_id:
            spec["instagram_user_id"] = self.instagram_user_id
        result = await self._request(
            "POST", f"{self.account}/adcreatives", params={"name": name, "object_story_spec": spec}
        )
        return str(result["id"])

    async def create_ad(self, *, name: str, adset_id: str, creative_id: str) -> str:
        result = await self._request(
            "POST",
            f"{self.account}/ads",
            params={
                "name": name,
                "adset_id": adset_id,
                "creative": {"creative_id": creative_id},
                "status": "PAUSED",
            },
        )
        return str(result["id"])

    # ───────────────────────── lectura ─────────────────────────

    async def ad_statuses(self, ad_ids: list[str]) -> dict[str, str]:
        """`effective_status` de cada anuncio (para avisar si Meta los rechazó o ya se activó)."""
        out: dict[str, str] = {}
        for i in range(0, len(ad_ids), 50):
            chunk = ad_ids[i : i + 50]
            data = await self._request(
                "GET", "", params={"ids": ",".join(chunk), "fields": "effective_status"}
            )
            for ad_id, value in data.items():
                out[ad_id] = (value or {}).get("effective_status", "")
        return out

    async def insights(self, ad_ids: list[str], since: str, until: str) -> list[dict]:
        """Filas diarias por anuncio entre dos fechas ISO (inclusive)."""
        if not ad_ids:
            return []
        return await self._paginate(
            f"{self.account}/insights",
            {
                "level": "ad",
                "fields": "ad_id,spend,impressions,inline_link_clicks,actions,action_values",
                "time_increment": "1",
                "time_range": {"since": since, "until": until},
                "filtering": [{"field": "ad.id", "operator": "IN", "value": ad_ids}],
                "limit": "500",
            },
        )


def _error_of(response: httpx.Response) -> MetaError:
    try:
        err = response.json().get("error") or {}
    except ValueError:
        err = {}
    # `error_user_msg` es el texto pensado para el usuario; si falta, el mensaje técnico de Meta.
    message = err.get("error_user_msg") or err.get("message") or f"HTTP {response.status_code}"
    return MetaError(str(message)[:400], code=err.get("code"), subcode=err.get("error_subcode"))
