"""Videos con el motor de Lemo-Opuscar: otra estética para el mismo guion de 5 escenas.

Lemo-Opuscar (github.com/lemomo-ai/lemo-opuscar) dibuja cada cuadro en una página web y lo
graba con un navegador sin ventana (Playwright + Chromium) y ffmpeg. Aquí se usa **solo su
código** (`core/render`, licencia MIT): las páginas de estilo (`lemo_film/index.html`) son
nuestras, escritas desde cero, y no incluyen sus guías (CC BY-NC). Los videos son del usuario.

- Mismo guion (`VideoScript`), mismas reglas y semáforo: elegir Lemo no cuesta IA extra.
- Los tiempos de entrada de cada elemento salen de `CUES` (aquí) y viajan a la página en
  `data.json`; el sonido se sintetiza con esos mismos tiempos (`app.video.audio`), en sync.
- Todo el texto del guion se dibuja en un `<canvas>` (nunca como HTML): sin inyección.
- Es opcional: sin la librería instalada, sin Node o sin ffmpeg 7+ la opción no aparece
  (`lemo_problems`) y se usa el motor propio.
"""

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import imageio_ffmpeg
from PIL import Image

from app.generators.mockups import Spine, cached_mockup
from app.templates_engine.model import Template
from app.video.audio import wav_bytes
from app.video.engine import DURATION, FPS, SAFE, SCENES, SIZES
from app.video.render import THUMB_AT, VideoRenderError, VideoResult
from app.video.schemas import VideoRatio, VideoScript
from app.video.style import fonts_from, palette_from

LemoStyle = Literal["kinetic", "swiss", "neon", "paper"]
LEMO_STYLES: tuple[str, ...] = ("kinetic", "swiss", "neon", "paper")
FILM_DIR = Path(__file__).parent / "lemo_film"
RENDER_TIMEOUT = 900  # s: un video de 17,5 s tarda ~1–3 min con 3 navegadores
WORKERS = 3


# ───────────────────────────── tiempos (fuente única) ─────────────────────────────


def cues(script: VideoScript) -> dict[str, list[float]]:
    """Segundo (dentro de su escena) en que entra cada elemento. La página anima con esto y el
    audio pone el efecto en el mismo instante."""
    return {
        "hook": [0.15, *(0.4 + 0.3 * i for i in range(len(script.hook_lines)))],
        "problem": [0.15, *(0.75 + 0.75 * i for i in range(len(script.problems)))],
        "solution": [0.15, 0.6, 0.75, 1.35],  # título, mockup, palabra grande, frase
        "benefits": [0.15, *(0.65 + 0.55 * i for i in range(len(script.benefits)))],
        "cta": [0.15, 0.55, 0.7, 1.25],  # nombre, mockup, botón, línea de confianza
    }


def sound_events(script: VideoScript) -> list[tuple[float, str]]:
    """Efectos de sonido del video: pop al entrar cada elemento, golpe en lo destacado, ding en
    cada entregable y whoosh 0,1 s antes de cada cambio de escena."""
    marks = cues(script)
    loud = {
        "hook": {1 + script.hook_highlight},
        "solution": {2},
        "cta": {2},
    }
    events: list[tuple[float, str]] = []
    offset = 0.0
    for index, (name, dur) in enumerate(SCENES):
        if index > 0:
            events.append((max(0.0, offset - 0.1), "whoosh"))
        for i, at in enumerate(marks[name]):
            if name == "solution" and i == 1 or name == "cta" and i == 1:
                continue  # el mockup entra en silencio
            sound = (
                "thud"
                if i in loud.get(name, set())
                else "ding"
                if name == "benefits" and i
                else "pop"
            )
            events.append((offset + at, sound))
        offset += dur
    return sorted(events)


# ───────────────────────────── requisitos ─────────────────────────────


@dataclass(frozen=True)
class LemoSetup:
    lib: Path
    node: str
    ffmpeg: str


def _ffmpeg_major(exe: str) -> int:
    try:
        out = subprocess.run(  # noqa: S603
            [exe, "-version"], capture_output=True, text=True, timeout=20, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    match = re.search(r"ffmpeg version n?(\d+)\.", out)
    return int(match.group(1)) if match else 0


def _node_major(exe: str) -> int:
    try:
        out = subprocess.run(  # noqa: S603
            [exe, "--version"], capture_output=True, text=True, timeout=20, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    match = re.match(r"v(\d+)\.", out.strip())
    return int(match.group(1)) if match else 0


def resolve_setup(settings) -> tuple[LemoSetup | None, list[str]]:
    """La instalación de Lemo lista para usar, o la lista de lo que falta (vacía = todo bien).
    Se recuerda mientras la configuración no cambie (comprobarla ejecuta `node` y `ffmpeg`)."""
    return _resolve(
        (getattr(settings, "lemo_opuscar_home", "") or "").strip(),
        (getattr(settings, "lemo_node", "") or "node").strip(),
        (getattr(settings, "lemo_ffmpeg", "") or "").strip(),
    )


@lru_cache(maxsize=4)
def _resolve(home: str, node_name: str, ffmpeg_path: str) -> tuple[LemoSetup | None, list[str]]:
    problems: list[str] = []
    if not home:
        return None, ["falta LEMO_OPUSCAR_HOME (carpeta de la librería Lemo-Opuscar)"]
    lib = Path(home).expanduser()
    if not (lib / "core" / "render" / "video.mjs").is_file():
        problems.append(f"{lib} no es la librería Lemo-Opuscar (falta core/render/video.mjs)")
    if not (lib / "node_modules" / "playwright-core").is_dir():
        problems.append("faltan los paquetes del renderizador: corre `sh setup.sh deps`")
    node = shutil.which(node_name) or ""
    if not node or _node_major(node) < 20:
        problems.append("falta Node 20 o más nuevo")
    ffmpeg = ffmpeg_path or shutil.which("ffmpeg") or ""
    if not ffmpeg or _ffmpeg_major(ffmpeg) < 7:
        problems.append("falta ffmpeg 7 o más nuevo (LEMO_FFMPEG o en el PATH)")
    if problems:
        return None, problems
    return LemoSetup(lib=lib.resolve(), node=node, ffmpeg=ffmpeg), []


# ───────────────────────────── render ─────────────────────────────


def film_data(
    script: VideoScript,
    *,
    style: str,
    product_name: str,
    template: Template,
    ratio: VideoRatio,
    has_book: bool,
) -> dict:
    """Lo que la página lee de `data.json`: textos, colores, tiempos y zona segura."""
    pal = palette_from(template)
    width, height = SIZES[ratio]
    top, bottom = SAFE[ratio]
    return {
        "style": style,
        "w": width,
        "h": height,
        "fps": FPS,
        "safe": {"top": round(height * top), "bottom": round(height * bottom), "side": 70},
        "scenes": [{"name": n, "dur": d} for n, d in SCENES],
        "cues": cues(script),
        "colors": {
            "bg": pal.bg,
            "text": pal.text,
            "accent": pal.accent,
            "onAccent": pal.on_accent,
            "sub": pal.sub,
            "deco": pal.deco,
            "primary": template.palette.primary,
            "secondary": template.palette.secondary,
        },
        "product": product_name,
        "book": "book.png" if has_book else "",
        "script": script.model_dump(mode="json"),
    }


def _copy_fonts(template: Template, templates_dir: Path, dest: Path) -> None:
    fonts = fonts_from(template, templates_dir)
    for name, path in (
        ("heading", fonts.heading),
        ("bold", fonts.bold),
        ("regular", fonts.regular),
    ):
        shutil.copyfile(path, dest / f"{name}.ttf")


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str], timeout: int) -> None:
    try:
        proc = subprocess.run(  # noqa: S603
            cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False,
            encoding="utf-8", errors="replace",
        )  # fmt: skip
    except subprocess.TimeoutExpired as exc:
        raise VideoRenderError("el render de Lemo tardó demasiado") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-500:]
        raise VideoRenderError(f"el render de Lemo falló: {tail}")


def render_lemo(
    script: VideoScript,
    *,
    setup: LemoSetup,
    style: str,
    product_name: str,
    template: Template,
    templates_dir: Path,
    ratio: VideoRatio = "9x16",
    cover_png: bytes | None = None,
    spine: Spine | None = None,
) -> VideoResult:
    """MP4 + miniatura del guion en el estilo `style`. CPU y navegador: se llama desde un hilo."""
    if style not in LEMO_STYLES:
        raise ValueError(f"estilo de Lemo desconocido: {style}")
    width, height = SIZES[ratio]
    # Carpeta sin `#` ni `?` (el servidor de Lemo los leería como parte de la URL).
    with tempfile.TemporaryDirectory(prefix="pf-lemo-") as tmp:
        film = Path(tmp) / "film"
        film.mkdir()
        shutil.copyfile(FILM_DIR / "index.html", film / "index.html")
        _copy_fonts(template, templates_dir, film)
        if cover_png:
            (film / "book.png").write_bytes(cached_mockup("book", cover_png, spine))
        data = film_data(
            script, style=style, product_name=product_name, template=template, ratio=ratio,
            has_book=bool(cover_png),
        )  # fmt: skip
        (film / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        silent = Path(tmp) / "silent.mp4"
        env = {
            **os.environ,
            "PATH": f"{Path(setup.ffmpeg).parent}{os.pathsep}{os.environ.get('PATH', '')}",
        }
        _run(
            [
                setup.node, "core/render/video.mjs", str(film), "--fps", str(FPS),
                "--workers", str(WORKERS), "--size", f"{width}x{height}", "--out", str(silent),
            ],
            cwd=setup.lib, env=env, timeout=RENDER_TIMEOUT,
        )  # fmt: skip
        if not silent.is_file():
            raise VideoRenderError("el render de Lemo no dejó el video")
        wav = Path(tmp) / "audio.wav"
        wav.write_bytes(wav_bytes(DURATION, sound_events(script)))
        final, thumb = Path(tmp) / "video.mp4", Path(tmp) / "thumb.png"
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        _run(
            [
                ffmpeg, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav),
                "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", "-movflags", "+faststart", str(final),
            ],
            cwd=Path(tmp), env=env, timeout=120,
        )  # fmt: skip
        _run(
            [
                ffmpeg, "-y", "-loglevel", "error", "-ss", str(THUMB_AT), "-i", str(silent),
                "-frames:v", "1", str(thumb),
            ],
            cwd=Path(tmp), env=env, timeout=60,
        )  # fmt: skip
        mp4 = final.read_bytes()
        png = io.BytesIO()
        Image.open(thumb).convert("RGB").save(png, "PNG", optimize=True)
    return VideoResult(
        mp4=mp4, thumbnail=png.getvalue(), duration=DURATION, width=width, height=height
    )
