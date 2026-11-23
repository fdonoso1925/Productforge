"""Del guion al MP4: escenas → cuadros por tubería a ffmpeg + audio sintetizado, en un paso.

ffmpeg viene en el paquete `imageio-ffmpeg` (versión fijada): no hay que instalar nada en el
sistema ni en la imagen Docker. Es CPU pura (~15–30 s por video): se llama desde un hilo.
"""

import io
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
from PIL import Image

from app.generators.mockups import Spine, cached_mockup
from app.templates_engine.model import Template
from app.video.audio import wav_bytes
from app.video.engine import (
    DURATION,
    FPS,
    background,
    build_scenes,
    frame_at,
    render_frames,
    timeline,
)
from app.video.schemas import VideoRatio, VideoScript
from app.video.style import fonts_from, palette_from

THUMB_AT = 2.6  # el gancho ya completo: buena miniatura


class VideoRenderError(RuntimeError):
    """ffmpeg no pudo codificar el video."""


@dataclass(frozen=True)
class VideoResult:
    mp4: bytes
    thumbnail: bytes  # PNG del gancho completo (miniatura del anuncio de video en Meta)
    duration: float
    width: int
    height: int


def _scenes(
    script: VideoScript,
    product_name: str,
    template: Template,
    templates_dir: Path,
    ratio: VideoRatio,
    cover_png: bytes | None,
    spine: Spine | None = None,
):
    pal = palette_from(template)
    fonts = fonts_from(template, templates_dir)
    book = bundle = None
    if cover_png:
        book = Image.open(io.BytesIO(cached_mockup("book", cover_png, spine))).convert("RGBA")
        bundle = Image.open(io.BytesIO(cached_mockup("bundle", cover_png, spine))).convert("RGBA")
    lay, scenes = build_scenes(
        script,
        product_name=product_name,
        pal=pal,
        fonts=fonts,
        ratio=ratio,
        mockup_book=book,
        mockup_bundle=bundle,
    )
    return pal, lay, scenes


def preview_frames(
    script: VideoScript,
    *,
    product_name: str,
    template: Template,
    templates_dir: Path,
    ratio: VideoRatio = "9x16",
    cover_png: bytes | None = None,
    seed: str = "preview",
    spine: Spine | None = None,
) -> list[Image.Image]:
    """Un cuadro por escena con todo ya en pantalla (t = dur − 0,4): para revisar a ojo que no
    haya textos cortados, glifos faltantes ni sombras recortadas antes del render completo."""
    pal, lay, scenes = _scenes(
        script, product_name, template, templates_dir, ratio, cover_png, spine
    )
    base, shapes = background(lay, pal, seed)
    out, offset = [], 0.0
    for scene in scenes:
        t = scene.dur - 0.4
        out.append(frame_at(lay, scene, t, base, shapes, offset + t).convert("RGB"))
        offset += scene.dur
    return out


def render_video(
    script: VideoScript,
    *,
    product_name: str,
    template: Template,
    templates_dir: Path,
    ratio: VideoRatio = "9x16",
    cover_png: bytes | None = None,
    seed: str = "video",
    spine: Spine | None = None,
) -> VideoResult:
    pal, lay, scenes = _scenes(
        script, product_name, template, templates_dir, ratio, cover_png, spine
    )
    events = timeline(scenes)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    thumb: Image.Image | None = None
    with tempfile.TemporaryDirectory(prefix="pf-video-") as tmp:
        wav = Path(tmp) / "audio.wav"
        wav.write_bytes(wav_bytes(DURATION, events))
        partial, final = Path(tmp) / "video.part.mp4", Path(tmp) / "video.mp4"
        cmd = [
            ffmpeg, "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{lay.W}x{lay.H}", "-r", str(FPS),
            "-i", "-", "-i", str(wav),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
            "-f", "mp4", str(partial),
        ]  # fmt: skip
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)  # noqa: S603
        assert proc.stdin is not None
        thumb_index = round(THUMB_AT * FPS)
        try:
            for index, frame in enumerate(render_frames(lay, scenes, pal, seed)):
                rgb = frame.convert("RGB")
                if index == thumb_index:
                    thumb = rgb
                proc.stdin.write(rgb.tobytes())
        except BrokenPipeError:
            pass  # ffmpeg terminó antes: su error se reporta abajo
        finally:
            proc.stdin.close()
        stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        if proc.wait() != 0 or not partial.exists():
            raise VideoRenderError(f"ffmpeg no pudo codificar el video: {stderr[-400:]}")
        os.replace(partial, final)
        mp4 = final.read_bytes()
    buffer = io.BytesIO()
    (thumb or Image.new("RGB", (lay.W, lay.H), pal.bg)).save(buffer, "PNG", optimize=True)
    return VideoResult(
        mp4=mp4, thumbnail=buffer.getvalue(), duration=DURATION, width=lay.W, height=lay.H
    )


def probe_seconds(mp4: bytes) -> tuple[int, float]:
    """Cuadros y segundos reales del MP4 (para verificar el render sin ffprobe)."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
        handle.write(mp4)
        path = handle.name
    try:
        return imageio_ffmpeg.count_frames_and_secs(path)
    finally:
        os.unlink(path)
