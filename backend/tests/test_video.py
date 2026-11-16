"""Videos de motion graphics: reglas del guion, motor, audio, render con ffmpeg y API."""

import io
import wave
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from app.ads.render import product_mockup
from app.config import Settings
from app.generators.mockups import cached_mockup
from app.templates_engine.model import load_template
from app.video import rules as video_rules
from app.video.audio import PEAK, SR, soundtrack, wav_bytes
from app.video.engine import (
    DURATION,
    FPS,
    SAFE,
    SCENES,
    SIZES,
    build_scenes,
    timeline,
    visible_box,
)
from app.video.render import preview_frames, probe_seconds, render_video
from app.video.schemas import VideoBenefit, VideoScript
from app.video.style import fonts_from, palette_from
from tests.test_ads_strategy import avatar, brief, service
from tests.test_api_ads import planned_world

SETTINGS = Settings(_env_file=None)
TEMPLATES = SETTINGS.templates_dir
BOLD = load_template(TEMPLATES, "bold-moderno")
USER = uuid4()


def script(**over) -> VideoScript:
    data = {
        "hook_tag": "Si trabajas por chat",
        "hook_lines": ["¿Pedidos perdidos", "entre chats", "y correos?"],
        "hook_highlight": 1,
        "problem_title": "Lo que pasa cuando todo llega por chat:",
        "problems": ["Mensajes que se pierden", "Fechas que se olvidan", "Clientes que esperan"],
        "solution_title": "Existe un método",
        "solution_big": "una sola lista",
        "solution_caption": "Registra cada pedido con responsable y fecha en un solo lugar",
        "benefits_title": "Con el método recibes:",
        "benefits": [
            VideoBenefit(title="El método completo", detail="Paso a paso para ordenarte"),
            VideoBenefit(title="Plantilla de captura", detail="Lista para usar hoy"),
            VideoBenefit(title="Revisión semanal", detail="Para no perder fechas"),
        ],
        "cta_button": "Quiero ordenarme",
        "cta_sub": "Acceso inmediato al comprar",
    }
    return VideoScript(**{**data, **over})


# ───────────────────────────── reglas del guion ─────────────────────────────


def test_a_good_script_passes_and_is_green() -> None:
    assert video_rules.check_script(script(), brief()) == []
    assert video_rules.script_policy(script(), brief(), []).status == "green"


@pytest.mark.parametrize(
    ("over", "fragment"),
    [
        ({"hook_lines": ["Una sola línea"]}, "2 o 3 líneas"),
        ({"hook_lines": ["uno dos tres cuatro cinco", "x"]}, "supera 4 palabras"),
        ({"hook_highlight": 5}, "hook_highlight"),
        ({"problems": ["a", "b"]}, "exactamente 3"),
        ({"cta_button": ""}, "no puede estar vacío"),
        ({"solution_big": "una lista *simple*"}, "asteriscos"),
    ],
)
def test_script_rules_explain_what_to_fix(over: dict, fragment: str) -> None:
    errors = video_rules.check_script(script(**over), brief())
    assert any(fragment in e for e in errors), errors


def test_numbers_not_in_the_brief_are_invented_and_rejected() -> None:
    errors = video_rules.check_script(script(cta_sub="Más de 5000 alumnos"), brief())
    assert any("5000" in e and "no está en el brief" in e for e in errors)
    # el precio real del brief sí se puede mostrar
    assert video_rules.check_script(script(cta_sub="Hoy por USD 12"), brief()) == []


def test_the_video_uses_the_same_meta_policy_light_as_static_ads() -> None:
    risky = script(problems=["¿Estás endeudado otra vez?", "Fechas que se olvidan", "x y z"])
    assert video_rules.script_policy(risky, brief(), []).status == "red"


# ───────────────────────────── estrategia (IA simulada) ─────────────────────────────


def test_the_script_is_retried_until_rules_and_policy_pass() -> None:
    import asyncio

    bad = script(cta_sub="Más de 5000 alumnos")
    svc, llm = service(bad, script())
    result = asyncio.run(
        svc.video_script(
            user_id=USER, brief=brief(), avatar=avatar(), angle_id="mecanismo", proofs=[]
        )
    )
    assert result == script()
    assert len(llm.calls) == 2 and "5000" in llm.calls[1].user  # el error vuelve como feedback


def test_an_unavailable_angle_is_refused_before_calling_the_ai() -> None:
    import asyncio

    svc, llm = service()
    with pytest.raises(ValueError, match="no disponible"):
        asyncio.run(
            svc.video_script(
                user_id=USER,
                brief=brief(price_text=""),
                avatar=avatar(),
                angle_id="oferta",
                proofs=[],
            )  # fmt: skip
        )
    assert llm.calls == []


# ───────────────────────────── motor ─────────────────────────────


def scenes(ratio="9x16", cover=True):
    cover_png = product_mockup(BOLD, "es-LATAM", "Bandeja Única", "Un método") if cover else None
    book = bundle = None
    if cover_png:
        book = Image.open(io.BytesIO(cached_mockup("book", cover_png))).convert("RGBA")
        bundle = Image.open(io.BytesIO(cached_mockup("bundle", cover_png))).convert("RGBA")
    return build_scenes(
        script(),
        product_name="Bandeja Única: el método para ordenar pedidos",
        pal=palette_from(BOLD),
        fonts=fonts_from(BOLD, TEMPLATES),
        ratio=ratio,
        mockup_book=book,
        mockup_bundle=bundle,
    )


def test_five_fixed_scenes_aligned_to_the_beat() -> None:
    assert [name for name, _ in SCENES] == ["hook", "problem", "solution", "benefits", "cta"]
    assert all((dur / 0.5).is_integer() for _, dur in SCENES)  # pulsos de 0,5 s a 120 bpm
    assert 15 <= DURATION <= 20


def test_the_hook_is_complete_before_two_seconds() -> None:
    _, built = scenes()
    hook = built[0]
    assert all(el.start + 0.42 <= 2.0 for el in hook.elements)


@pytest.mark.parametrize("ratio", ["9x16", "4x5"])
def test_everything_visible_stays_inside_the_safe_zone(ratio: str) -> None:
    lay, built = scenes(ratio)
    W, H = SIZES[ratio]
    top, bottom = round(H * SAFE[ratio][0]), round(H * (1 - SAFE[ratio][1]))
    for scene in built:
        for el in scene.elements:
            x0, y0, x1, y1 = visible_box(el.sprite)  # lo que se ve (sin la sombra tenue)
            left = el.cx - el.sprite.width / 2 + x0
            upper = el.cy - el.sprite.height / 2 + y0
            assert upper >= top - 2 and upper + (y1 - y0) <= bottom + 2, (scene.name, ratio)
            assert left >= 0 and left + (x1 - x0) <= W, (scene.name, ratio)


def test_sound_effects_follow_the_animation() -> None:
    _, built = scenes()
    events = timeline(built)
    assert events == sorted(events)
    kinds = [k for _, k in events]
    assert kinds.count("whoosh") == len(SCENES) - 1  # uno antes de cada cambio de escena
    assert (
        kinds.count("thud") == 3 and kinds.count("ding") >= 4
    )  # ✕ problemas, ✓ beneficios + botón
    changes = [3.0, 7.0, 10.5, 14.0]
    whooshes = [t for t, k in events if k == "whoosh"]
    assert whooshes == pytest.approx([c - 0.1 for c in changes])


def test_a_video_without_cover_still_renders_every_scene() -> None:
    frames = preview_frames(
        script(), product_name="Bandeja Única", template=BOLD, templates_dir=TEMPLATES
    )
    assert len(frames) == 5 and all(f.size == SIZES["9x16"] for f in frames)


# ───────────────────────────── audio ─────────────────────────────


def test_the_soundtrack_has_the_exact_length_and_safe_levels() -> None:
    track = soundtrack(DURATION, [(0.1, "pop"), (2.9, "whoosh"), (4.0, "thud"), (8.0, "ding")])
    assert len(track) == int(DURATION * SR)
    assert np.max(np.abs(track)) <= PEAK + 1e-6
    rms_db = 20 * np.log10(np.sqrt(np.mean(track**2)))
    assert -17 <= rms_db <= -13  # alrededor de −15 dB
    with wave.open(io.BytesIO(wav_bytes(2.0, []))) as w:
        assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (2, SR, 2)
        assert w.getnframes() == 2 * SR


# ───────────────────────────── render completo ─────────────────────────────


def test_render_produces_an_mp4_with_matching_video_and_thumbnail() -> None:
    cover = product_mockup(BOLD, "es-LATAM", "Bandeja Única", "Un método")
    result = render_video(
        script(),
        product_name="Bandeja Única",
        template=BOLD,
        templates_dir=TEMPLATES,
        cover_png=cover,
        seed="test",
    )
    assert result.mp4[4:8] == b"ftyp" and result.thumbnail.startswith(b"\x89PNG")
    frames, seconds = probe_seconds(result.mp4)
    assert frames == round(DURATION * FPS) and seconds == pytest.approx(DURATION, abs=0.05)
    assert (result.width, result.height) == (1080, 1920)


# ───────────────────────────── API y job ─────────────────────────────


def test_a_video_is_scripted_once_rendered_and_stored() -> None:
    w, batch_id = planned_world()
    w.llm.responses.append(script())
    body = {"angle": "mecanismo", "avatar": avatar().name}
    response = w.client.post(f"/ads/batches/{batch_id}/videos", json=body)
    assert response.status_code == 202, response.text
    video_id = response.json()["video_id"]
    assert w.client.get(f"/ads/videos/{video_id}/url").status_code == 409  # aún no está
    w.run_worker()
    video = w.videos.rows[video_id]
    assert video["status"] == "ready" and video["policy_status"] == "green"
    assert video["filename"].endswith("_mecanismo_video_9x16_v1.mp4")
    assert w.storage.objects[video["storage_path"]][4:8] == b"ftyp"
    assert video["ad_copy"]["headline"]  # el texto del anuncio sale de un creativo del lote
    urls = w.client.get(f"/ads/videos/{video_id}/url").json()
    assert urls["url"].startswith("https://storage.test/") and urls["thumb_url"]
    # Volver a componer no llama a la IA: reutiliza el guion guardado.
    calls = len(w.llm.calls)
    assert w.client.post(f"/ads/videos/{video_id}/render").status_code == 202
    w.run_worker()
    assert len(w.llm.calls) == calls and w.videos.rows[video_id]["status"] == "ready"


def test_editing_the_script_follows_the_same_rules_without_ai() -> None:
    w, batch_id = planned_world()
    w.llm.responses.append(script())
    body = {"angle": "mecanismo", "avatar": avatar().name}
    video_id = w.client.post(f"/ads/batches/{batch_id}/videos", json=body).json()["video_id"]
    w.run_worker()
    bad = script(cta_sub="Más de 5000 alumnos").model_dump(mode="json")
    response = w.client.put(f"/ads/videos/{video_id}/script", json=bad)
    assert response.status_code == 422 and "5000" in str(response.json())
    good = script(cta_button="Quiero empezar").model_dump(mode="json")
    assert w.client.put(f"/ads/videos/{video_id}/script", json=good).status_code == 200
    assert w.videos.rows[video_id]["script"]["cta_button"] == "Quiero empezar"


def test_video_requests_are_validated_and_private() -> None:
    w, batch_id = planned_world()
    url = f"/ads/batches/{batch_id}/videos"
    assert (
        w.client.post(url, json={"angle": "inexistente", "avatar": avatar().name}).status_code
        == 422
    )
    assert w.client.post(url, json={"angle": "mecanismo", "avatar": "Nadie"}).status_code == 422
    stranger = w.as_user(str(uuid4()))
    body = {"angle": "mecanismo", "avatar": avatar().name}
    assert w.client.post(url, json=body, headers=stranger).status_code == 404
    w.llm.responses.append(script())
    video_id = w.client.post(url, json=body).json()["video_id"]
    assert w.client.get(f"/ads/videos/{video_id}/url", headers=stranger).status_code == 404
    w.run_worker()
    assert w.client.delete(f"/ads/videos/{video_id}", headers=stranger).status_code == 404
    assert w.client.delete(f"/ads/videos/{video_id}").status_code == 204
    assert video_id not in w.videos.rows
    assert not [p for p in w.storage.objects if "/videos/" in p]  # se borran también los archivos
