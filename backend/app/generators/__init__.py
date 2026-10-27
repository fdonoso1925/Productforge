"""Importar los módulos registra cada generador en REGISTRY."""

from app.generators import epub, maps, office, pdf, printable, sheet  # noqa: F401
from app.generators.base import REGISTRY, FileArtifact, RenderContext, generate_files

__all__ = ["REGISTRY", "FileArtifact", "RenderContext", "generate_files"]
