"""Videos con el motor de Lemo-Opuscar: tiempos, datos de la página, requisitos, API y job."""

import os
from pathlib import Path

import pytest

from app.config import Settings
from app.video import lemo
from app.video.engine import DURATION, SAFE, SCENES, SIZES
from app.video.render import VideoResult
from tests.test_ads_strategy import avatar
from tests.test_api_ads import planned_world
from tests.test_video import BOLD, TEMPLATES, script

SETTINGS = Settings(_env_file=None)


def test_every_element_has_its_sound_at_the_same_second_it_appears() -> None:
    s = script()
    marks = lemo.cues(s)
    assert list(marks) == [name for name, _ in SCENES]
    assert len(marks["hook"]) == 1 + len(s.hook_lines)
    assert len(marks["problem"]) == 1 + len(s.problems)
    assert len(marks["benefits"]) == 1 + len(s.benefits)
    events = lemo.sound_events(s)
    times = {round(t, 3) for t, _ in events}
    offset = 0.0
    for name, dur in SCENES:
        assert all(0 < at < dur - 0.5 for at in marks[name]), name  # entra antes del fundido
        silent = {1} if name in ("solution", "cta") else set()  # el mockup entra en silencio
        for i, at in enumerate(marks[name]):
            assert (round(offset + at, 3) in times) is (i not in silent), (name, i)
        offset += dur
    assert sum(1 for _, kind in events if kind == "whoosh") == len(SCENES) - 1
    assert all(0 <= t < DURATION for t, _ in events)
    highlight = marks["hook"][1 + s.hook_highlight]
    assert (round(highlight, 3), "thud") in {(round(t, 3), k) for t, k in events}


def test_the_page_gets_texts_colors_timing_and_the_safe_zone() -> None:
    data = lemo.film_data(
        script(), style="neon", product_name="Bandeja", template=BOLD, ratio="9x16", has_book=True
    )
    assert (data["w"], data["h"]) == SIZES["9x16"] and data["style"] == "neon"
    assert data["safe"]["top"] == round(1920 * SAFE["9x16"][0])
    assert data["safe"]["bottom"] == round(1920 * SAFE["9x16"][1])
    assert sum(s["dur"] for s in data["scenes"]) == DURATION
    assert data["script"]["cta_button"] == script().cta_button and data["book"] == "book.png"
    assert all(v.startswith("#") for v in data["colors"].values())


def test_the_film_page_draws_text_only_on_canvas() -> None:
    page = (lemo.FILM_DIR / "index.html").read_text(encoding="utf-8")
    assert "window.READY = true" in page and "window.render" in page
    assert "innerHTML" not in page and "insertAdjacentHTML" not in page and "eval(" not in page
    for style in lemo.LEMO_STYLES:
        assert f'"{style}"' in page or style == "paper"  # paper es el estilo por defecto


def test_without_the_library_lemo_is_off_with_the_reasons(tmp_path: Path) -> None:
    lemo._resolve.cache_clear()
    setup, problems = lemo.resolve_setup(SETTINGS.model_copy(update={"lemo_opuscar_home": ""}))
    assert setup is None and "LEMO_OPUSCAR_HOME" in problems[0]
    fake = SETTINGS.model_copy(
        update={"lemo_opuscar_home": str(tmp_path), "lemo_ffmpeg": str(tmp_path / "nada.exe")}
    )
    setup, problems = lemo.resolve_setup(fake)
    assert setup is None
    assert any("core/render/video.mjs" in p for p in problems)
    assert any("setup.sh deps" in p for p in problems)
    assert any("ffmpeg 7" in p for p in problems)


def test_unknown_style_is_rejected() -> None:
    setup = lemo.LemoSetup(lib=Path("."), node="node", ffmpeg="ffmpeg")
    with pytest.raises(ValueError):
        lemo.render_lemo(script(), setup=setup, style="grafiti", product_name="x",
                         template=BOLD, templates_dir=TEMPLATES)  # fmt: skip


# ───────────────────────────── API y job ─────────────────────────────


def fake_result() -> VideoResult:
    return VideoResult(
        mp4=b"\x00\x00\x00\x18ftypmp42lemo", thumbnail=b"\x89PNG\r\n", duration=DURATION,
        width=1080, height=1920,
    )  # fmt: skip


@pytest.fixture
def lemo_on(monkeypatch):
    setup = lemo.LemoSetup(lib=Path("."), node="node", ffmpeg="ffmpeg")
    calls: list[dict] = []
    monkeypatch.setattr(lemo, "resolve_setup", lambda settings: (setup, []))

    def render(script, **kwargs):
        calls.append(kwargs)
        return fake_result()

    monkeypatch.setattr(lemo, "render_lemo", render)
    return calls


def test_engines_report_lemo_off_when_it_is_not_installed(monkeypatch) -> None:
    monkeypatch.setattr(lemo, "resolve_setup", lambda settings: (None, ["falta ffmpeg 7"]))
    w, batch_id = planned_world()
    engines = w.client.get("/ads/videos/engines").json()
    assert engines["motion"] is True and engines["lemo"] is False
    assert engines["lemo_problems"] == ["falta ffmpeg 7"]
    body = {"angle": "mecanismo", "avatar": avatar().name, "engine": "lemo", "style": "neon"}
    response = w.client.post(f"/ads/batches/{batch_id}/videos", json=body)
    assert response.status_code == 409 and "ffmpeg" in response.text


def test_a_lemo_video_uses_the_same_script_and_renders_with_its_style(lemo_on) -> None:
    w, batch_id = planned_world()
    assert w.client.get("/ads/videos/engines").json()["lemo_styles"] == list(lemo.LEMO_STYLES)
    w.llm.responses.append(script())
    body = {"angle": "mecanismo", "avatar": avatar().name, "engine": "lemo", "style": "neon"}
    response = w.client.post(f"/ads/batches/{batch_id}/videos", json=body)
    assert response.status_code == 202, response.text
    video_id = response.json()["video_id"]
    w.run_worker()
    video = w.videos.rows[video_id]
    assert (video["engine"], video["style"], video["status"]) == ("lemo", "neon", "ready")
    assert lemo_on[-1]["style"] == "neon" and lemo_on[-1]["ratio"] == "9x16"
    assert w.storage.objects[video["storage_path"]][4:8] == b"ftyp"
    # Cambiar de estilo (o volver al motor propio) reutiliza el guion: sin IA.
    calls = len(w.llm.calls)
    switch = {"engine": "lemo", "style": "paper"}
    assert w.client.post(f"/ads/videos/{video_id}/render", json=switch).status_code == 202
    w.run_worker()
    assert lemo_on[-1]["style"] == "paper" and len(w.llm.calls) == calls
    back = w.client.post(f"/ads/videos/{video_id}/render", json={"engine": "motion"})
    assert back.status_code == 202
    assert (w.videos.rows[video_id]["engine"], w.videos.rows[video_id]["style"]) == ("motion", None)


def test_bad_engine_or_style_is_a_422(lemo_on) -> None:
    w, batch_id = planned_world()
    url = f"/ads/batches/{batch_id}/videos"
    base = {"angle": "mecanismo", "avatar": avatar().name}
    assert w.client.post(url, json={**base, "engine": "otro"}).status_code == 422
    assert w.client.post(url, json={**base, "engine": "lemo", "style": "x"}).status_code == 422


# ───────────────────────────── render real (si Lemo está instalado) ─────────────────────────────


def real_setup():
    home = os.environ.get("LEMO_OPUSCAR_HOME") or str(Path.home() / "lemo-opuscar")
    lemo._resolve.cache_clear()
    current = SETTINGS.model_copy(
        update={"lemo_opuscar_home": home, "lemo_ffmpeg": os.environ.get("LEMO_FFMPEG", "")}
    )
    return lemo.resolve_setup(current)[0]


@pytest.mark.skipif(real_setup() is None, reason="Lemo-Opuscar no está instalado aquí")
def test_real_lemo_render_produces_the_full_video_with_sound() -> None:
    from app.ads.render import product_mockup
    from app.video.render import probe_seconds

    cover = product_mockup(BOLD, "es-LATAM", "Bandeja Única", "Un método")
    result = lemo.render_lemo(
        script(), setup=real_setup(), style="kinetic", product_name="Bandeja Única",
        template=BOLD, templates_dir=TEMPLATES, cover_png=cover,
    )  # fmt: skip
    assert result.mp4[4:8] == b"ftyp" and result.thumbnail.startswith(b"\x89PNG")
    frames, seconds = probe_seconds(result.mp4)
    assert seconds == pytest.approx(DURATION, abs=0.1)
