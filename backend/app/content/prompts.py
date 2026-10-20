"""Carga de prompts versionados desde `prompts/<mercado>/` (§8)."""

import json
from functools import lru_cache
from pathlib import Path
from string import Template

from app.content.schemas import Format, Market

# Etiqueta que delimita los datos del usuario en cada mercado (ver system.md).
DATA_TAG: dict[str, str] = {"pt-BR": "dados_do_usuario", "es-LATAM": "datos_del_usuario"}


class PromptLibrary:
    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def version(self) -> str:
        return _read(self.root / "VERSION").strip()

    def system(self, market: Market) -> str:
        return _read(self.root / market / "system.md")

    def render(self, market: Market, name: str, **values: object) -> str:
        """Rellena las variables `$x` del prompt. Solo valores del sistema, nunca del usuario."""
        text = _read(self.root / market / f"{name}.md")
        return Template(text).substitute({k: str(v) for k, v in values.items()})

    def format_guide(self, market: Market, fmt: Format) -> str:
        return _read(self.root / market / "formats" / f"{fmt.value}.md")


def wrap_user_data(market: Market, data: dict) -> str:
    """Serializa los datos del usuario como JSON dentro de su etiqueta delimitadora.

    Se escapa `</` para que ningún valor pueda cerrar la etiqueta antes de tiempo.
    """
    tag = DATA_TAG[market]
    payload = json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return f"<{tag}>\n{payload}\n</{tag}>"


@lru_cache(maxsize=256)
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")
