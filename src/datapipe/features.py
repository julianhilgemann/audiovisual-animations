"""Per-frame audio features every method shares (SPEC §5.2, §16.3): loudness, brightness, band energies.

One feature frame per video frame: the hop is 800 samples at 48 kHz, frame i starts at sample i * 800, no centring.
``wrap`` treats the audio as a seamless loop (method A); a song (B, C, D) has a start and an end.
"""

import numpy as np

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


def _power(x: np.ndarray, n_fft: int, wrap: bool) -> tuple[np.ndarray, np.ndarray]:
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
    power, freqs = _power(x, 2048, wrap)
    band = (freqs >= 60) & (freqs <= 16000)
    centroid = (power[:, band] * freqs[band]).sum(axis=1) / (power[:, band].sum(axis=1) + 1e-12)
    return mapping.normalize(mapping.smooth(np.log2(centroid + 1.0), smooth_frames, wrap))


def bands(x: np.ndarray, attack: float = 1, release: float = 6, wrap: bool = True) -> dict[str, np.ndarray]:
    """0-1 energy per band of §5.2 (sub, bass, lowmid, mid, highmid, air): dB per frame from a 4096-sample window,
    floored 48 dB under the band's peak, followed, normalised."""
    power, freqs = _power(x, 4096, wrap)
    out = {}
    for name, (lo, hi) in BANDS.items():
        db = 10 * np.log10(power[:, (freqs >= lo) & (freqs < hi)].sum(axis=1) + 1e-12)
        db = np.maximum(db, db.max() - FLOOR_DB)
        out[name] = mapping.normalize(mapping.follow(db, attack, release, wrap))
    return out


def rounded(values) -> list[float]:
    return [round(float(v), 5) for v in values]
