"""Pista de audio sintetizada con numpy: música a 120 bpm y efectos en sync con la animación.

Nada grabado ni con derechos: arpegio C–Am–F–G (4 pulsos por acorde), bajo, bombo, contratiempo
y palmada; los primeros 3 s (el gancho) van más livianos. Encima, un efecto por cada cosa que
aparece: *pop* en textos, golpe grave en cada ✕, *ding* en cada ✓ y en el botón, *whoosh* antes de
cada cambio de escena. Mezcla con saturación suave (`tanh`) y normalizada a 0,89 de pico.
"""

import io
import wave

import numpy as np

SR = 44_100
BPM = 120
BEAT = 60 / BPM  # 0,5 s
LIGHT_INTRO = 3.0
TAIL_FADE = 0.35
PEAK = 0.89
TARGET_RMS = 10 ** (-15 / 20)  # −15 dB de volumen medio
# Acordes (frecuencias de sus notas) y su tónica para el bajo.
CHORDS = (
    ((261.63, 329.63, 392.00, 523.25), 130.81),  # C
    ((220.00, 261.63, 329.63, 440.00), 110.00),  # Am
    ((174.61, 220.00, 261.63, 349.23), 87.31),  # F
    ((196.00, 246.94, 293.66, 392.00), 98.00),  # G
)


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * SR)) / SR


def _add(track: np.ndarray, sound: np.ndarray, at: float, gain: float = 1.0) -> None:
    start = int(at * SR)
    if start >= len(track):
        return
    end = min(len(track), start + len(sound))
    track[start:end] += gain * sound[: end - start]


def _pluck(freq: float, dur: float = 0.42) -> np.ndarray:
    t = _t(dur)
    tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(4 * np.pi * freq * t)
    tone += 0.12 * np.sin(6 * np.pi * freq * t)
    return tone * np.exp(-t * 7.5)


def _bass(freq: float, dur: float = BEAT * 0.95) -> np.ndarray:
    t = _t(dur)
    return np.sin(2 * np.pi * freq * t) * np.minimum(1, t * 60) * np.exp(-t * 2.2)


def _kick() -> np.ndarray:
    t = _t(0.28)
    freq = 45 + (135 - 45) * np.exp(-t * 28)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return np.sin(phase) * np.exp(-t * 11)


def _noise(rng: np.random.Generator, dur: float) -> np.ndarray:
    return rng.uniform(-1, 1, int(dur * SR))


def _hat(rng: np.random.Generator) -> np.ndarray:
    n = _noise(rng, 0.05)
    n = np.diff(n, prepend=0)  # agudos: diferencia de primer orden
    return n * np.exp(-_t(0.05) * 80)


def _clap(rng: np.random.Generator) -> np.ndarray:
    n = _noise(rng, 0.16)
    env = np.exp(-_t(0.16) * 26)
    return np.convolve(n, np.ones(4) / 4, mode="same") * env


def _pop() -> np.ndarray:
    t = _t(0.1)
    freq = 520 + 900 * t / 0.1
    return np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 32)


def _thud() -> np.ndarray:
    t = _t(0.22)
    freq = 70 + 60 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 16)


def _ding() -> np.ndarray:
    t = _t(0.6)
    tone = np.sin(2 * np.pi * 1318.5 * t) + 0.5 * np.sin(2 * np.pi * 2637 * t)
    return tone * np.exp(-t * 6.5) * 0.6


def _whoosh(rng: np.random.Generator) -> np.ndarray:
    dur = 0.32
    n = _noise(rng, dur)
    out = np.zeros_like(n)
    y = 0.0
    for i, x in enumerate(n):  # paso bajo de un polo que se abre: el filtro «sube»
        a = 0.02 + 0.5 * (i / len(n))
        y += a * (x - y)
        out[i] = y
    t = _t(dur)
    return out * np.sin(np.pi * t / dur) ** 2 * 2.2


def music(duration: float) -> np.ndarray:
    track = np.zeros(int(duration * SR) + SR)
    beats = int(duration / BEAT)
    rng = np.random.default_rng(7)
    hat, clap, kick = _hat(rng), _clap(rng), _kick()
    for beat in range(beats):
        at = beat * BEAT
        notes, root = CHORDS[(beat // 4) % len(CHORDS)]
        light = at < LIGHT_INTRO
        # Arpegio en corcheas: dos notas por pulso.
        for half in range(2):
            note = notes[(beat * 2 + half) % len(notes)]
            _add(track, _pluck(note), at + half * BEAT / 2, 0.16 if light else 0.2)
        _add(track, _bass(root), at, 0.22 if light else 0.32)
        if not light:
            _add(track, kick, at, 0.55)
            _add(track, hat, at + BEAT / 2, 0.16)
            if beat % 2 == 1:
                _add(track, clap, at, 0.22)
    # Acorde final que se sostiene hasta el cierre.
    final_at = max(0.0, duration - 1.0)
    for note in CHORDS[0][0]:
        _add(track, _pluck(note, 1.0), final_at, 0.14)
    return track[: int(duration * SR)]


def soundtrack(duration: float, events: list[tuple[float, str]]) -> np.ndarray:
    """Música + efectos, mono (el estéreo se arma al escribir el WAV)."""
    rng = np.random.default_rng(11)
    track = music(duration)
    sounds = {"pop": (_pop(), 0.32), "thud": (_thud(), 0.6), "ding": (_ding(), 0.34)}
    for at, kind in events:
        if kind == "whoosh":
            _add(track, _whoosh(rng), at, 0.3)
        elif kind in sounds:
            sound, gain = sounds[kind]
            _add(track, sound, at, gain)
    fade = int(TAIL_FADE * SR)
    track[-fade:] *= np.linspace(1, 0, fade)
    track = np.tanh(track * 1.4)
    peak = float(np.max(np.abs(track))) or 1.0
    track = track * (PEAK / peak)
    # Volumen medio de unos −15 dB (lo que mide `volumedetect`): fuerte sin cansar en el feed.
    rms = float(np.sqrt(np.mean(track**2))) or 1.0
    return track * min(1.0, TARGET_RMS / rms)


def wav_bytes(duration: float, events: list[tuple[float, str]]) -> bytes:
    """WAV estéreo de 16 bits a 44,1 kHz con la duración exacta del video."""
    mono = soundtrack(duration, events)
    # Un estéreo leve: la derecha un poco más brillante que la izquierda.
    left = mono
    right = np.concatenate([[0.0], mono[:-1]]) * 0.15 + mono * 0.85
    stereo = np.stack([left, right], axis=1)
    pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return out.getvalue()
