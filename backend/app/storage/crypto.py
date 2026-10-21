"""Cifrado de tokens OAuth y estado firmado del flujo de autorización."""

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class TokenCipher:
    """Fernet (AES-128-CBC + HMAC-SHA256). La clave vive solo en el entorno del backend."""

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt(self, text: str) -> bytes:
        return self._fernet.encrypt(text.encode())

    def decrypt(self, token: bytes) -> str:
        return self._fernet.decrypt(token).decode()

    # ── estado OAuth: opaco, con expiración y a prueba de manipulación ──

    def seal(self, purpose: str, payload: dict[str, Any]) -> str:
        data = json.dumps({"purpose": purpose, **payload}, separators=(",", ":"))
        return self._fernet.encrypt(data.encode()).decode()

    def unseal(self, purpose: str, token: str, ttl_seconds: int) -> dict[str, Any] | None:
        """Devuelve el contenido o None si está vencido, alterado o es de otro propósito."""
        try:
            raw = self._fernet.decrypt(token.encode(), ttl=ttl_seconds)
            data = json.loads(raw)
        except (InvalidToken, ValueError, UnicodeError):
            return None
        return data if isinstance(data, dict) and data.get("purpose") == purpose else None


def to_bytea(data: bytes) -> str:
    """Formato hexadecimal que PostgREST acepta para columnas bytea."""
    return "\\x" + data.hex()


def from_bytea(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("\\x"))
