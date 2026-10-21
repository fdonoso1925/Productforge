"""Endurecimiento de la API: límite de peticiones, cabeceras, tamaño de body y logs sin secretos.

El límite NO es una cuota de costo (D6: uso personal, sin tope): es un freno ante loops o clics
repetidos en los endpoints que llaman a la IA. Vive en memoria, así que vale por réplica de la
API; con una sola réplica (lo normal en Railway para esto) es exacto.
"""

import logging
import math
import time
from collections import deque
from collections.abc import Sequence
from typing import Annotated

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, status
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth import CurrentUser, get_current_user
from app.config import Settings, get_settings


class RateLimiter:
    """Ventana deslizante por clave (usuario + grupo de endpoints)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str, limits: Sequence[tuple[int, float]], now: float | None = None) -> int:
        """Registra un intento. Devuelve 0 si pasa, o los segundos de espera si se excedió."""
        now = time.monotonic() if now is None else now
        hits = self._hits.setdefault(key, deque())
        longest = max(window for _, window in limits)
        while hits and hits[0] <= now - longest:
            hits.popleft()
        wait = 0.0
        for limit, window in limits:
            recent = [t for t in hits if t > now - window]
            if len(recent) >= limit:
                wait = max(wait, recent[-limit] + window - now)
        if wait > 0:
            return max(1, math.ceil(wait))
        hits.append(now)
        return 0

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter()


def ai_rate_limit(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Dependencia de los endpoints que usan IA (o encolan jobs que la usan)."""
    limits = [
        (settings.rate_limit_per_minute, 60.0),
        (settings.rate_limit_per_hour, 3600.0),
    ]
    wait = limiter.check(f"ai:{user.id}", limits)
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "demasiadas solicitudes seguidas; espera un momento",
            headers={"Retry-After": str(wait)},
        )


_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-resource-policy", b"cross-origin"),  # el frontend lee la API desde otro origen
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
    # La API solo devuelve JSON (y una PNG de preview): nada ejecutable ni embebible.
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
]


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                present = {name.lower() for name, _ in message["headers"]}
                message["headers"] = [
                    *message["headers"],
                    *[(n, v) for n, v in _SECURITY_HEADERS if n not in present],
                ]
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodyLimitMiddleware:
    """Rechaza bodies enormes según `Content-Length` (todos los bodies de la API son JSON chico)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            for name, value in scope["headers"]:
                if name == b"content-length":
                    try:
                        too_big = int(value) > self.max_bytes
                    except ValueError:
                        too_big = True
                    if too_big:
                        body = b'{"detail":"cuerpo demasiado grande"}'
                        await send(
                            {
                                "type": "http.response.start",
                                "status": 413,
                                "headers": [
                                    (b"content-type", b"application/json"),
                                    (b"content-length", str(len(body)).encode()),
                                ],
                            }
                        )
                        await send({"type": "http.response.body", "body": body})
                        return
        await self.app(scope, receive, send)


class RedactQueryFilter(logging.Filter):
    """Quita la query string del access log: el callback de Google trae `code` y `state`."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            record.args = (*args[:2], args[2].split("?", 1)[0], *args[3:])
        return True


def configure_logging() -> None:
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactQueryFilter) for f in access.filters):
        access.addFilter(RedactQueryFilter())
    # httpx a INFO escribe cada URL llamada (Supabase, Google): ruido que no aporta.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # Uvicorn no configura el logger raíz: sin esto, los INFO de la app (p. ej. tiempos y caché
    # de cada llamada a Claude) no aparecen.
    app_log = logging.getLogger("productforge")
    if not app_log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
        app_log.addHandler(handler)
        app_log.setLevel(logging.INFO)
        app_log.propagate = False


def _is_local(url: str) -> bool:
    return "localhost" in url or "127.0.0.1" in url or "[::1]" in url


def production_problems(settings: Settings) -> list[str]:
    """Lo que falta o es inseguro para correr en producción. Vacío = listo."""
    problems: list[str] = []
    if _is_local(settings.supabase_url):
        problems.append("SUPABASE_URL apunta a un servidor local")
    if not settings.supabase_service_role_key:
        problems.append("falta SUPABASE_SERVICE_ROLE_KEY")
    if not settings.anthropic_api_key:
        problems.append("falta ANTHROPIC_API_KEY")
    if not settings.allowed_emails:
        problems.append("falta ALLOWED_EMAILS")
    if not settings.cors_origins or any(_is_local(o) or o == "*" for o in settings.cors_origins):
        problems.append("CORS_ORIGINS debe listar solo el dominio público del frontend")
    if _is_local(settings.frontend_url):
        problems.append("FRONTEND_URL apunta a un servidor local")
    if settings.google_client_id or settings.google_client_secret:
        if not (settings.google_client_id and settings.google_client_secret):
            problems.append("GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET van juntos")
        if _is_local(settings.google_redirect_uri):
            problems.append("GOOGLE_REDIRECT_URI apunta a un servidor local")
        if not settings.token_encryption_key:
            problems.append("falta TOKEN_ENCRYPTION_KEY (cifra los tokens de Google)")
    if settings.token_encryption_key:
        try:
            Fernet(settings.token_encryption_key.encode())
        except ValueError:
            problems.append("TOKEN_ENCRYPTION_KEY no es una clave Fernet válida")
    return problems


def ensure_production_ready(settings: Settings) -> None:
    """En producción, la app no arranca con una configuración insegura o incompleta."""
    if settings.environment != "production":
        return
    problems = production_problems(settings)
    if problems:
        raise RuntimeError("configuración de producción inválida: " + "; ".join(problems))
