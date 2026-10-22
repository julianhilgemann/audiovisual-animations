"""Loudness and peaks for a loop: BS.1770 loudness, 4x oversampled true peak and a lookahead limiter.

Everything is circular: the end of the loop flows into its start, so loudness is measured on the loop played three
times, and the limiter's lookahead and release wrap around the seam.
"""

import numpy as np
import pyloudnorm
from scipy.signal import resample_poly

OVERSAMPLE = 4


def lufs(x: np.ndarray, sr: int) -> float:
    """Integrated loudness (LUFS) of a (channels, samples) loop as it sounds when repeated."""
    return float(pyloudnorm.Meter(sr).integrated_loudness(np.tile(x, 3).T))


def true_peaks(x: np.ndarray) -> np.ndarray:
    """Per sample, the highest absolute value of any channel between it and the next sample, 4x oversampled."""
    pad = 64
    n = x.shape[1]
    wrapped = np.concatenate([x[:, -pad:], x, x[:, :pad]], axis=1)
    up = resample_poly(wrapped, OVERSAMPLE, 1, axis=1)[:, pad * OVERSAMPLE:(pad + n) * OVERSAMPLE]
    return np.abs(up).max(axis=0).reshape(n, OVERSAMPLE).max(axis=1)


def true_peak_db(x: np.ndarray) -> float:
    return float(20 * np.log10(true_peaks(x).max() + 1e-12))


def limit(x: np.ndarray, sr: int, ceiling_db: float, lookahead_ms: float = 2.0,
          release_ms: float = 80.0) -> tuple[np.ndarray, float]:
    """Keep true peaks under ``ceiling_db``; returns the limited loop and the deepest gain reduction in dB.

    The gain needed at each sample is held for the lookahead window, released with a one-pole curve and then
    averaged over the lookahead, so it starts falling before a peak and every peak sees its full reduction.
    """
    n = x.shape[1]
    need = np.minimum(1.0, 10 ** (ceiling_db / 20) / np.maximum(true_peaks(x), 1e-12))
    look = max(1, int(lookahead_ms * sr / 1000))
    held = need.copy()
    for k in range(1, look + 1):                    # held[i] = min(need[i .. i + look]), wrapping
        np.minimum(held, np.roll(need, -k), out=held)
    if held.min() >= 1.0:
        return x.copy(), 0.0
    coeff = np.exp(-1.0 / (release_ms * sr / 1000))
    released = np.empty(n)
    g = 1.0
    for _lap in range(2):                           # second lap starts from the wrapped state
        for i in range(n):
            h = held[i]
            g = h if h < g else h + (g - h) * coeff
            released[i] = g
    window = np.concatenate([released[-look:], released])
    smooth = np.convolve(window, np.full(look + 1, 1.0 / (look + 1)), mode="valid")
    return x * smooth, float(-20 * np.log10(smooth.min()))


def master(x: np.ndarray, sr: int, target_lufs: float = -14.0, ceiling_db: float = -1.0) -> tuple[np.ndarray, dict]:
    """Gain the loop to ``target_lufs``, limit its true peaks to ``ceiling_db``, and report what was done."""
    before = lufs(x, sr)
    if not np.isfinite(before):
        raise ValueError("the mix is silent")
    gain_db = target_lufs - before
    margin = 0.15                                   # the oversampled estimate can miss a hair of the real peak
    for _ in range(6):
        y, reduction = limit(x * 10 ** (gain_db / 20), sr, ceiling_db - margin)
        error = target_lufs - lufs(y, sr)
        if abs(error) < 0.05:
            break
        gain_db += error
    report = {
        "lufs_before": round(before, 2), "gain_db": round(gain_db, 2),
        "lufs": round(lufs(y, sr), 2), "true_peak_db": round(true_peak_db(y), 2),
        "limiter_max_reduction_db": round(reduction, 2),
    }
    return y, report


def seam(passes: np.ndarray, n: int) -> dict:
    """Does the loop's wrap (last sample -> first) jump more than the render's own pass boundary, the true
    continuation? ``passes`` holds two passes of ``n`` samples. Noise sources differ between passes, so the wrap
    may exceed the boundary by up to a typical large step (99.9th percentile) of the loop."""
    loop = passes[:, n:2 * n]
    wrap = float(np.abs(loop[:, 0] - loop[:, -1]).max())
    boundary = float(np.abs(passes[:, n] - passes[:, n - 1]).max())
    typical = float(np.percentile(np.abs(np.diff(loop, axis=1)).max(axis=0), 99.9))
    return {"wrap": round(wrap, 5), "boundary": round(boundary, 5), "p999_step": round(typical, 5),
            "ok": wrap <= boundary + typical}
