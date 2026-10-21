"""Capa de almacenamiento (§10). Supabase Storage es siempre el respaldo; Google Drive (Fase 6)
u otros (Google Drive, Dropbox) implementan la misma interfaz."""

from dataclasses import dataclass
from typing import ClassVar, Protocol
from uuid import UUID


class StorageProvider(Protocol):
    name: ClassVar[str]

    async def upload(self, path: str, data: bytes, mime: str) -> str:
        """Sube (o reemplaza) el archivo y devuelve su ruta en el proveedor."""
        ...

    async def signed_url(self, path: str, expires_in: int) -> str:
        """URL de descarga temporal."""
        ...

    async def download(self, path: str) -> bytes:
        """Contenido de un archivo ya subido."""
        ...

    async def delete(self, paths: list[str]) -> None:
        """Borra archivos (ignora los que no existen)."""
        ...


@dataclass(frozen=True)
class RemoteFile:
    id: str
    url: str


class SyncTarget(Protocol):
    """Destino externo al que se COPIAN los archivos ya guardados en Supabase Storage.

    Google Drive hoy; OneDrive o Dropbox mañana implementarían lo mismo. Supabase sigue siendo
    el respaldo: si el destino falla, el archivo no se pierde y la copia se reintenta.
    """

    name: ClassVar[str]

    def configured(self) -> bool:
        """¿El backend tiene las credenciales de la app para hablar con este destino?"""
        ...

    async def is_connected(self, user_id: UUID) -> bool: ...

    async def upload(self, user_id: UUID, path: str, data: bytes, mime: str) -> RemoteFile:
        """Sube (reemplazando si existe) a `path`, relativo a la carpeta de la app."""
        ...

    async def delete(self, user_id: UUID, remote_id: str) -> None: ...

    async def folder_url(self, user_id: UUID, path: str) -> str | None: ...
