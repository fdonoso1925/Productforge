"""Descarga las tipografías que usan las plantillas a `templates/_fonts/`.

Son Google Fonts con licencia libre (OFL / Apache); se versionan en el repo para que
el render no dependa de la red. Ejecutar al agregar una plantilla con fuentes nuevas:

    uv run python -m app.templates_engine.fonts
"""

import json
import re
import sys
from pathlib import Path

import httpx

from app.config import get_settings

CSS_API = "https://fonts.googleapis.com/css2"
# Con un user-agent sin soporte de woff, la API sirve un TTF estático completo por peso.
LEGACY_UA = "Wget/1.21"
SRC_URL = re.compile(r"src:\s*url\((https://fonts\.gstatic\.com/[^)]+\.ttf)\)")


def font_path(fonts_dir: Path, family: str, weight: int) -> Path:
    return fonts_dir / family.replace(" ", "") / f"{weight}.ttf"


def required_fonts(templates_dir: Path) -> dict[str, set[int]]:
    needed: dict[str, set[int]] = {}
    for config in templates_dir.glob("*/template.json"):
        fonts = json.loads(config.read_text(encoding="utf-8"))["fonts"]
        for spec in fonts.values():
            needed.setdefault(spec["family"], set()).update(spec["weights"])
    return needed


def fetch(templates_dir: Path) -> None:
    fonts_dir = templates_dir / "_fonts"
    with httpx.Client(timeout=30, headers={"User-Agent": LEGACY_UA}) as client:
        for family, weights in sorted(required_fonts(templates_dir).items()):
            for weight in sorted(weights):
                target = font_path(fonts_dir, family, weight)
                if target.exists():
                    continue
                css = client.get(CSS_API, params={"family": f"{family}:wght@{weight}"})
                css.raise_for_status()
                match = SRC_URL.search(css.text)
                if not match:
                    sys.exit(f"sin TTF para {family} {weight}")
                data = client.get(match.group(1))
                data.raise_for_status()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data.content)
                print(f"{family} {weight}: {len(data.content) // 1024} KB")


if __name__ == "__main__":
    fetch(get_settings().templates_dir)
