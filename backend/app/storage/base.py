"""Capa de almacenamiento (§10). Supabase Storage es siempre el respaldo; OneDrive (Fase 6)
u otros (Google Drive, Dropbox) implementan la misma interfaz."""

from typing import ClassVar, Protocol


class StorageProvider(Protocol):
    name: ClassVar[str]

    async def upload(self, path: str, data: bytes, mime: str) -> str:
        """Sube (o reemplaza) el archivo y devuelve su ruta en el proveedor."""
        ...

    async def signed_url(self, path: str, expires_in: int) -> str:
        """URL de descarga temporal."""
        ...
