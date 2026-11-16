"""Credenciales de Meta Ads y Hotmart: se ingresan en Ajustes y quedan guardadas cifradas.

Lo guardado manda sobre las variables de entorno, campo por campo (el entorno sigue valiendo de
respaldo: quien ya tenía todo en `.env` no tiene que hacer nada). Los valores nunca vuelven al
navegador: el estado solo dice si cada campo está puesto, de dónde viene y los últimos 4 caracteres
de los secretos.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

from app.ads.meta.client import MetaClient
from app.config import Settings
from app.db.supabase import SupabaseRest, eq
from app.hotmart.client import HotmartClient
from app.storage.crypto import TokenCipher, from_bytea, to_bytea

PROVIDERS = ("meta", "hotmart")
TOKEN = re.compile(r"^[A-Za-z0-9._~+/=\-:]{8,1000}$")
DIGITS = re.compile(r"^(act_)?\d{4,30}$")


@dataclass(frozen=True)
class Field:
    key: str
    secret: bool  # los secretos solo muestran los últimos 4 caracteres
    required: bool
    env: str  # nombre de la variable de entorno equivalente


FIELDS: dict[str, tuple[Field, ...]] = {
    "meta": (
        Field("access_token", True, True, "META_ACCESS_TOKEN"),
        Field("ad_account_id", False, True, "META_AD_ACCOUNT_ID"),
        Field("page_id", False, True, "META_PAGE_ID"),
        Field("instagram_user_id", False, False, "META_INSTAGRAM_USER_ID"),
        Field("pixel_id", False, False, "META_PIXEL_ID"),
    ),
    "hotmart": (
        Field("client_id", False, True, "HOTMART_CLIENT_ID"),
        Field("client_secret", True, True, "HOTMART_CLIENT_SECRET"),
        Field("basic", True, False, "HOTMART_BASIC"),
    ),
}


class InvalidCredentials(ValueError):
    pass


class MigrationMissing(RuntimeError):
    """La tabla `integration_credentials` no existe: falta aplicar la migración."""


def missing_table(exc: httpx.HTTPStatusError) -> bool:
    return exc.response.status_code in (404, 400) and "integration_credentials" in str(
        exc.request.url
    )


def validate(provider: str, values: dict[str, str]) -> dict[str, str]:
    """Limpia y valida lo que llega del formulario (los vacíos se descartan)."""
    known = {f.key for f in FIELDS[provider]}
    clean: dict[str, str] = {}
    for key, raw in values.items():
        if key not in known:
            raise InvalidCredentials(f"campo desconocido: {key}")
        value = (raw or "").strip()
        if not value:
            continue
        if key in {"ad_account_id", "page_id", "instagram_user_id", "pixel_id"}:
            if not DIGITS.match(value):
                raise InvalidCredentials(f"{key}: debe ser numérico")
        elif key == "basic":
            body = value.removeprefix("Basic ").removeprefix("basic ").strip()
            if not TOKEN.match(body):
                raise InvalidCredentials("basic: formato no válido")
        elif not TOKEN.match(value):
            raise InvalidCredentials(
                f"{key}: formato no válido (sin espacios, 8 a 1000 caracteres)"
            )
        clean[key] = value
    return clean


class CredentialRepo:
    """Tabla `integration_credentials` (sin policies: solo la service role)."""

    def __init__(self, db: SupabaseRest) -> None:
        self._db = db

    async def get(self, user_id: UUID, provider: str) -> bytes | None:
        try:
            rows = await self._db.select(
                "integration_credentials", user_id=eq(user_id), provider=eq(provider)
            )
        except httpx.HTTPStatusError as exc:
            if missing_table(exc):  # sin migración: se comporta como «nada guardado»
                return None
            raise
        return from_bytea(rows[0]["data_enc"]) if rows else None

    async def save(self, user_id: UUID, provider: str, data_enc: bytes) -> None:
        try:
            await self._db.upsert(
                "integration_credentials",
                {
                    "user_id": str(user_id),
                    "provider": provider,
                    "data_enc": to_bytea(data_enc),
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                on_conflict="user_id,provider",
            )
        except httpx.HTTPStatusError as exc:
            if missing_table(exc):
                raise MigrationMissing("falta aplicar la migración de credenciales") from exc
            raise

    async def delete(self, user_id: UUID, provider: str) -> None:
        try:
            await self._db.delete(
                "integration_credentials", user_id=eq(user_id), provider=eq(provider)
            )
        except httpx.HTTPStatusError as exc:
            if not missing_table(exc):
                raise


class CredentialStore:
    def __init__(self, repo: Any, cipher: TokenCipher | None, settings: Settings) -> None:
        self._repo = repo
        self._cipher = cipher
        self._settings = settings
        self._clients: dict[tuple[str, str], tuple[str, Any]] = {}

    @property
    def can_save(self) -> bool:
        return self._cipher is not None

    def _env(self, provider: str) -> dict[str, str]:
        return {
            f.key: str(getattr(self._settings, f.env.lower(), "") or "").strip()
            for f in FIELDS[provider]
        }

    async def saved(self, user_id: UUID, provider: str) -> dict[str, str]:
        if self._cipher is None:
            return {}
        blob = await self._repo.get(user_id, provider)
        if blob is None:
            return {}
        try:
            data = json.loads(self._cipher.decrypt(blob))
        except Exception:  # clave cambiada o dato dañado: se trata como «sin guardar»
            return {}
        return {k: str(v) for k, v in data.items() if isinstance(v, str)}

    async def effective(self, user_id: UUID, provider: str) -> dict[str, str]:
        merged = self._env(provider)
        merged.update({k: v for k, v in (await self.saved(user_id, provider)).items() if v})
        return merged

    async def save(self, user_id: UUID, provider: str, values: dict[str, str]) -> None:
        """Mezcla con lo ya guardado: lo que no se envía (o llega vacío) se conserva."""
        if self._cipher is None:
            raise InvalidCredentials("falta TOKEN_ENCRYPTION_KEY en el backend")
        merged = {**await self.saved(user_id, provider), **validate(provider, values)}
        await self._repo.save(user_id, provider, self._cipher.encrypt(json.dumps(merged)))
        self._clients.pop((str(user_id), provider), None)

    async def delete(self, user_id: UUID, provider: str) -> None:
        await self._repo.delete(user_id, provider)
        self._clients.pop((str(user_id), provider), None)

    async def status(self, user_id: UUID, provider: str) -> dict[str, Any]:
        saved = await self.saved(user_id, provider)
        env = self._env(provider)
        fields = []
        for f in FIELDS[provider]:
            value, source = (saved[f.key], "saved") if saved.get(f.key) else (env[f.key], "env")
            fields.append(
                {
                    "key": f.key,
                    "secret": f.secret,
                    "required": f.required,
                    "set": bool(value),
                    "source": source if value else None,
                    "hint": hint(value) if value and f.secret else (value if value else None),
                }
            )
        connected = all(x["set"] for x in fields if x["required"])
        return {
            "provider": provider,
            "connected": connected,
            "can_save": self.can_save,
            "has_saved": bool(saved),
            "fields": fields,
            "missing": [x["key"] for x in fields if x["required"] and not x["set"]],
        }

    async def meta_client(self, user_id: UUID) -> MetaClient | None:
        """Cliente con lo guardado (y el entorno de respaldo); None si no se guardó nada."""
        if not await self.saved(user_id, "meta"):
            return None
        v = await self.effective(user_id, "meta")
        return self._cached(
            user_id,
            "meta",
            v,
            lambda: MetaClient(
                access_token=v["access_token"],
                ad_account_id=v["ad_account_id"],
                page_id=v["page_id"],
                instagram_user_id=v["instagram_user_id"],
                pixel_id=v["pixel_id"],
                version=self._settings.meta_api_version,
            ),
        )

    async def hotmart_client(self, user_id: UUID) -> HotmartClient | None:
        if not await self.saved(user_id, "hotmart"):
            return None
        v = await self.effective(user_id, "hotmart")
        return self._cached(
            user_id,
            "hotmart",
            v,
            lambda: HotmartClient(
                client_id=v["client_id"], client_secret=v["client_secret"], basic=v["basic"]
            ),
        )

    def _cached(self, user_id: UUID, provider: str, values: dict[str, str], build: Any) -> Any:
        """Un cliente por usuario y juego de valores (el de Hotmart reutiliza su token OAuth)."""
        digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
        key = (str(user_id), provider)
        cached = self._clients.get(key)
        if cached and cached[0] == digest:
            return cached[1]
        client = build()
        self._clients[key] = (digest, client)
        return client


def hint(secret: str) -> str:
    return "••••" + secret[-4:] if len(secret) > 8 else "••••"


async def resolve_meta(deps: Any, user_id: UUID) -> MetaClient | None:
    """Meta del usuario: lo guardado en Ajustes; si no, lo de las variables de entorno."""
    store = getattr(deps, "credentials", None)
    if store is not None:
        client = await store.meta_client(user_id)
        if client is not None:
            return client
    return getattr(deps, "meta", None)


async def resolve_hotmart(deps: Any, user_id: UUID) -> HotmartClient | None:
    store = getattr(deps, "credentials", None)
    if store is not None:
        client = await store.hotmart_client(user_id)
        if client is not None:
            return client
    return getattr(deps, "hotmart", None)


async def meta_pixel(deps: Any, user_id: UUID) -> str:
    store = getattr(deps, "credentials", None)
    if store is not None:
        return (await store.effective(user_id, "meta")).get("pixel_id", "")
    return str(getattr(getattr(deps, "settings", None), "meta_pixel_id", "") or "")
