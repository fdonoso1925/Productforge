"""Validación del JWT de Supabase en cada request.

Soporta los dos esquemas de firma de Supabase:
- HS256 con el secreto del proyecto (Supabase local y proyectos legacy),
- claves asimétricas (ES256/RS256) publicadas en el JWKS del proyecto.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)
AUDIENCE = "authenticated"


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)


def decode_token(token: str, settings: Settings) -> dict:
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise jwt.InvalidTokenError("HS256 sin SUPABASE_JWT_SECRET configurado")
            key: object = settings.supabase_jwt_secret
        elif alg in ("ES256", "RS256"):
            key = _jwks_client(settings.jwks_url).get_signing_key_from_jwt(token).key
        else:
            raise jwt.InvalidTokenError("algoritmo no soportado")
        return jwt.decode(
            token,
            key,
            algorithms=[alg],
            audience=AUDIENCE,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token inválido") from exc


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "falta token")
    claims = decode_token(credentials.credentials, settings)
    email = str(claims.get("email", "")).lower()
    # Uso personal (D1): solo los emails permitidos usan la API.
    if email not in settings.allowed_emails:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "usuario no autorizado")
    return CurrentUser(id=UUID(claims["sub"]), email=email)
