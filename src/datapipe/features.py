"""Per-frame audio features every method shares (SPEC §5.2, §16.3): loudness, brightness, band energies; and the
fixed-scale ones E and F add (§16.7): flatness and crest.

One feature frame per video frame: the hop is 800 samples at 48 kHz, frame i starts at sample i * 800, no centring.
``wrap`` treats the audio as a seamless loop (method A); a song (B-F) has a start and an end.
"""

import numpy as np
from scipy.ndimage import maximum_filter1d, uniform_filter1d

from . import mapping

FPS = 60
SAMPLE_RATE = 48000
HOP = SAMPLE_RATE // FPS       # 800
FLOOR_DB = 48                  # loudness below the signal's peak minus this counts as silence
BANDS = {"sub": (20, 60), "bass": (60, 250), "lowmid": (250, 500), "mid": (500, 2000), "highmid": (2000, 4000),
         "air": (4000, 16000)}


def mono(x: np.ndarray) -> np.ndarray:
    return x.mean(axis=1) if x.ndim == 2 else x


def frames_of(x: np.ndarray) -> int:
    return len(x) // HOP


def loudness(x: np.ndarray, attack: float, release: float, wrap: bool = True) -> np.ndarray:
    """0-1 loudness envelope of a (samples, channels) signal: RMS per frame in dB, followed, then normalised."""
    m = mono(x)
    n = frames_of(m)
    rms = np.sqrt((m[:n * HOP].reshape(n, HOP) ** 2).mean(axis=1))
    db = 20 * np.log10(rms + 1e-9)
    db = np.maximum(db, db.max() - FLOOR_DB)
    return mapping.normalize(mapping.follow(db, attack, release, wrap))


def power_spectrum(x: np.ndarray, n_fft: int, wrap: bool) -> tuple[np.ndarray, np.ndarray]:
    """Power spectrum per frame from an ``n_fft`` window starting on the frame (wrapping or zero-padded)."""
    m = mono(x)
    n = frames_of(m)
    tail = m[:n_fft] if wrap else np.zeros(n_fft)
    padded = np.concatenate([m, tail])
    starts = np.arange(n) * HOP
    power = np.empty((n, n_fft // 2 + 1))
    window = np.hanning(n_fft)
    for lo in range(0, n, 512):              # in blocks, so a three-minute song stays small in memory
        idx = starts[lo:lo + 512, None] + np.arange(n_fft)[None, :]
        power[lo:lo + 512] = np.abs(np.fft.rfft(padded[idx] * window, axis=1)) ** 2
    return power, np.fft.rfftfreq(n_fft, 1 / SAMPLE_RATE)


def brightness(x: np.ndarray, smooth_frames: int = 8, wrap: bool = True) -> np.ndarray:
    """0-1 spectral centroid (log frequency) per frame, from a 2048-sample window starting on the frame."""
    power, freqs = power_spectrum(x, 2048, wrap)
    band = (freqs >= 60) & (freqs <= 16000)
    centroid = (power[:, band] * freqs[band]).sum(axis=1) / (power[:, band].sum(axis=1) + 1e-12)
    return mapping.normalize(mapping.smooth(np.log2(centroid + 1.0), smooth_frames, wrap))


def bands(x: np.ndarray, attack: float = 1, release: float = 6, wrap: bool = True,
          table: dict[str, tuple[float, float]] = BANDS) -> dict[str, np.ndarray]:
    """0-1 energy per band of ``table`` (default §5.2's sub, bass, lowmid, mid, highmid, air): dB per frame from a
    4096-sample window, floored 48 dB under the band's peak, followed, normalised."""
    power, freqs = power_spectrum(x, 4096, wrap)
    out = {}
    for name, (lo, hi) in table.items():
        db = 10 * np.log10(power[:, (freqs >= lo) & (freqs < hi)].sum(axis=1) + 1e-12)
        db = np.maximum(db, db.max() - FLOOR_DB)
        out[name] = mapping.normalize(mapping.follow(db, attack, release, wrap))
    return out


def flatness(x: np.ndarray, smooth_frames: int = 6, wrap: bool = True) -> np.ndarray:
    """0-1 spectral flatness per frame (60 Hz-16 kHz, 2048-sample window) on a fixed scale: a pure tone is near 0,
    white noise near 1 (its flatness through a Hann window is about 0.56, scaled by 1 / 0.5). Not normalised, so
    noisy against tonal means the same on every signal; silence counts as tonal."""
    power, freqs = power_spectrum(x, 2048, wrap)
    p = power[:, (freqs >= 60) & (freqs <= 16000)] + 1e-12
    flat = np.exp(np.log(p).mean(axis=1)) / p.mean(axis=1)
    flat[power.sum(axis=1) < 1e-9] = 0.0
    return np.clip(mapping.smooth(flat / 0.5, smooth_frames, wrap), 0.0, 1.0)


def crest(x: np.ndarray, window_frames: int, wrap: bool = True) -> np.ndarray:
    """0-1 crest factor (peak against RMS) over a centred window of ``window_frames``, on a fixed scale: a sine
    (3 dB) is 0, 21 dB (a click in silence) is 1. How percussive the sound is; silence is 0."""
    m = mono(x)
    n = frames_of(m)
    blocks = m[:n * HOP].reshape(n, HOP).astype(np.float64)
    mode = "wrap" if wrap else "nearest"
    peak = maximum_filter1d(np.abs(blocks).max(axis=1), window_frames, mode=mode)
    ms = np.maximum(uniform_filter1d((blocks ** 2).mean(axis=1), window_frames, mode=mode), 0.0)
    db = 20 * np.log10((peak + 1e-12) / np.sqrt(ms + 1e-24))
    db[ms < 1e-10] = 3.0
    return np.clip((db - 3.0) / 18.0, 0.0, 1.0)


def rounded(values) -> list[float]:
    return [round(float(v), 5) for v in values]
