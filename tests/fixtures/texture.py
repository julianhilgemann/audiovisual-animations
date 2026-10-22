"""Non-musical stems with known events (SPEC §16.7, M5): no tempo, no kick, nothing a drum detector expects.

Bursts: noise bursts at irregular times (0.18-0.9 s apart) and levels; Drone: a 55 Hz tone with detuned partials
that swells slowly; Texture: band-passed noise whose level wanders, like wind or a room. 12 s, stems only.
"""

from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

SR = 48000
SECONDS = 12.0


def burst_times(seed: int = 4) -> list[float]:
    rng = np.random.default_rng(seed)
    t, times = 0.4, []
    while t < SECONDS - 0.5:
        times.append(round(float(t), 4))
        t += rng.uniform(0.18, 0.9)
    return times


def _bursts(times: list[float]) -> np.ndarray:
    rng = np.random.default_rng(5)
    x = np.zeros(int(SECONDS * SR))
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    for start_s in times:
        start = int(round(start_s * SR))
        noise = np.diff(rng.standard_normal(n + 1))                  # tilted toward the highs
        env = np.minimum(t / 0.002, 1.0) * np.exp(-t / 0.04)
        x[start:start + n] += 0.4 * rng.uniform(0.3, 1.0) * noise * env
    return x


def _drone() -> np.ndarray:
    t = np.arange(int(SECONDS * SR)) / SR
    tone = np.sin(2 * np.pi * 55 * t) + 0.5 * np.sin(2 * np.pi * 110.4 * t) + 0.25 * np.sin(2 * np.pi * 165.3 * t)
    return 0.25 * tone * (0.6 + 0.4 * np.sin(2 * np.pi * t / 6)) * np.minimum(t / 1.5, 1.0)


def _texture() -> np.ndarray:
    t = np.arange(int(SECONDS * SR)) / SR
    sos = signal.butter(2, [200, 3000], btype="bandpass", fs=SR, output="sos")
    noise = signal.sosfilt(sos, np.random.default_rng(6).standard_normal(len(t)))
    level = 0.5 + 0.3 * np.sin(2 * np.pi * t / 4.3) + 0.2 * np.sin(2 * np.pi * t / 1.7)
    return 0.3 * noise * level * np.minimum(t / 1.0, 1.0)


def make_texture(folder: Path) -> dict[str, list[float]]:
    """Write stems/Bursts.wav, Drone.wav and Texture.wav into ``folder`` (no master); return the burst times."""
    stems = Path(folder) / "stems"
    stems.mkdir(parents=True, exist_ok=True)
    times = burst_times()
    for name, x in (("Bursts", _bursts(times)), ("Drone", _drone()), ("Texture", _texture())):
        sf.write(stems / f"{name}.wav", np.stack([x, x], axis=1), SR, subtype="FLOAT")
    return {"Bursts": times}
