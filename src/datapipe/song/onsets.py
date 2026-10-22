"""Hits from audio (SPEC §16.3): band-limited spectral flux, peak-picked onto the video frame grid.

Method C runs it on each stem (a clean signal, so the whole band works); a drum bus and method B's full mix are
split into kick, snare and hats by band, B after a harmonic-percussive split so held notes trigger less. A hit is
``[frame, strength]`` like a MIDI note-on (frame 0-based, the nearest frame to the onset; strength 0-1), so the
mappings treat detected and played hits the same.
"""

import librosa
import numpy as np
from scipy.ndimage import maximum_filter1d

from ..features import FPS, SAMPLE_RATE

DET_HOP = 200                  # samples: 4 detection steps per video frame
N_FFT = 1024                   # 21 ms: sharp in time, coarse in frequency
DRUM_BANDS = {"kick": (30, 150), "snare": (1000, 5000), "hats": (7000, 16000)}
SILENT_DB = -60                # a signal whose loudest 100 ms stays under this has no hits


def spectrogram(x: np.ndarray, n_fft: int = N_FFT, hop: int = DET_HOP) -> tuple[np.ndarray, np.ndarray]:
    """Magnitude per detection step (rows) and bin, window centred on sample ``row * hop``."""
    m = x.mean(axis=1) if x.ndim == 2 else x
    padded = np.concatenate([np.zeros(n_fft // 2), m, np.zeros(n_fft // 2)]).astype(np.float64)
    rows = 1 + (len(padded) - n_fft) // hop
    window = np.hanning(n_fft)
    mag = np.empty((rows, n_fft // 2 + 1), np.float32)
    for lo in range(0, rows, 4096):
        idx = (np.arange(lo, min(lo + 4096, rows)) * hop)[:, None] + np.arange(n_fft)[None, :]
        mag[lo:lo + 4096] = np.abs(np.fft.rfft(padded[idx] * window, axis=1))
    return mag, np.fft.rfftfreq(n_fft, 1 / SAMPLE_RATE)


def percussive(mag: np.ndarray) -> np.ndarray:
    """The percussive part of a magnitude spectrogram (median-filter HPSS, harmonic kernel ~250 ms)."""
    harmonic_kernel = int(0.25 * SAMPLE_RATE / DET_HOP) | 1
    _, perc = librosa.decompose.hpss(mag.T, kernel_size=(harmonic_kernel, 31), margin=(1.0, 2.0))
    return perc.T


def novelty(mag: np.ndarray, freqs: np.ndarray, lo: float, hi: float, lag: int = 2) -> np.ndarray:
    """SuperFlux in a band: the rise of log-compressed magnitude over the step ``lag`` steps earlier, max-filtered
    across ±1 bin, so a pitch glide or vibrato (a kick's sweep, a bass slide) does not count as a new onset."""
    band = mag[:, (freqs >= lo) & (freqs < hi)]
    ref = float(band.max())
    if ref <= 0:
        return np.zeros(len(mag))
    y = np.log1p(100.0 * band / ref)
    before = maximum_filter1d(y, size=3, axis=1)
    flux = np.maximum(y[lag:] - before[:-lag], 0.0).sum(axis=1)
    return np.concatenate([np.zeros(lag), flux])


def pick(nov: np.ndarray, level_db: np.ndarray, delta: float = 0.1, wait_s: float = 0.045,
         separation: float = 4.0) -> list[list]:
    """Peaks of a novelty curve -> ``[[frame, strength], ...]`` on the video frame grid. A peak must top its
    ±30 ms neighbourhood and its ±100 ms mean by ``delta`` (relative to the curve's top), and come ``wait_s``
    after the previous one. When the peak heights fall into two groups whose means differ by ``separation`` times
    or more, the low group is crosstalk (hats in the snare band, a kick's tail) and goes. One hit per frame."""
    if nov.max() <= 0 or level_db.max() < SILENT_DB:
        return []
    top = np.percentile(nov[nov > 0], 99.9)
    x = np.clip(nov / top, 0.0, 1.5)
    step = DET_HOP / SAMPLE_RATE
    peaks = librosa.util.peak_pick(x, pre_max=round(0.03 / step), post_max=round(0.03 / step) + 1,
                                   pre_avg=round(0.1 / step), post_avg=round(0.1 / step) + 1,
                                   delta=delta, wait=round(wait_s / step))
    peaks = np.array([p for p in peaks if level_db[min(p + 2, len(level_db) - 1)] > level_db.max() - 45], int)
    if not len(peaks):
        return []
    heights = x[peaks]
    floor = _crosstalk_floor(heights, separation)
    peaks, heights = peaks[heights >= floor], heights[heights >= floor]
    scale = float(np.percentile(heights, 90)) or 1.0
    hits = {}
    for p, h in zip(peaks, heights):
        frame = int(np.floor(p * step * FPS + 0.5))
        hits[frame] = max(hits.get(frame, 0.0), round(float(min(h / scale, 1.0)), 4))
    return sorted([f, a] for f, a in hits.items())


def _crosstalk_floor(heights: np.ndarray, separation: float) -> float:
    """The split between two groups of peak heights (Otsu on log height) if their means differ by ``separation``
    times and the upper group has at least 4 peaks; else 0 (keep everything)."""
    if len(heights) < 8:
        return 0.0
    h = np.sort(np.log(heights))
    best, split = -1.0, None
    for i in range(1, len(h)):
        lo, hi = h[:i], h[i:]
        between = len(lo) * len(hi) * (lo.mean() - hi.mean()) ** 2
        if between > best:
            best, split = between, i
    lo, hi = h[:split], h[split:]
    if len(hi) >= 4 and hi.mean() - lo.mean() >= np.log(separation):
        return float(np.exp((lo.max() + hi.min()) / 2))
    return 0.0


def _level_db(mag: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Band level in dBFS-like units per detection step (for the silence gate)."""
    band = mag[:, (freqs >= lo) & (freqs < hi)]
    power = (band ** 2).sum(axis=1) / (N_FFT * np.hanning(N_FFT).sum() / 2) + 1e-12
    return 10 * np.log10(power)


def hits(x: np.ndarray, lo: float = 30, hi: float = 16000) -> list[list]:
    """Onsets of a clean signal (a stem), over the whole band by default."""
    mag, freqs = spectrogram(x)
    return pick(novelty(mag, freqs, lo, hi), _level_db(mag, freqs, lo, hi))


def drum_hits(x: np.ndarray, full_mix: bool = False) -> dict[str, list[list]]:
    """Kick, snare and hats from a drum bus, or (``full_mix``) from a whole master after HPSS. In a full mix the
    low band also fires on bass notes, so each kick candidate is weighted by how kick-like it sounds (``kickness``)
    and dropped below 0.15: a pure low thump keeps its strength, a harmonic bass note fades out."""
    mag, freqs = spectrogram(x)
    if full_mix:
        mag = percussive(mag)
    out = {role: pick(novelty(mag, freqs, lo, hi), _level_db(mag, freqs, lo, hi), separation=3.0 if full_mix else 4.0)
           for role, (lo, hi) in DRUM_BANDS.items()}
    if full_mix:
        m = x.mean(axis=1) if x.ndim == 2 else x
        weighted = [[f, round(a * kickness(m, f), 4)] for f, a in out["kick"]]
        out["kick"] = [h for h in weighted if h[1] >= 0.15]
    return out


def kickness(m: np.ndarray, frame: int) -> float:
    """0-1: how much the 85 ms from a low-band onset sound like a kick rather than a bass note. A kick's energy
    under 300 Hz sits almost all below 90 Hz and is spread by its pitch sweep (no harmonic lines); a bass note
    has overtones above 90 Hz and a peaky, harmonic spectrum. Measured on generated house, techno and phonk runs:
    kicks 0.92-0.98 below 90 Hz with flatness 0.01-0.06; house bass 0.51-0.69 with flatness 0.06-0.37."""
    start = int(frame) * (SAMPLE_RATE // FPS)
    seg = m[start:start + 4096]
    if len(seg) < 4096:
        seg = np.concatenate([seg, np.zeros(4096 - len(seg))])
    spec = np.abs(np.fft.rfft(seg * np.hanning(4096))) ** 2
    f = np.fft.rfftfreq(4096, 1 / SAMPLE_RATE)
    low = spec[(f >= 25) & (f < 300)]
    sub = spec[(f >= 25) & (f < 90)].sum() / (low.sum() + 1e-12)
    flat = np.exp(np.mean(np.log(low + 1e-12))) / (np.mean(low) + 1e-12)
    return float(np.clip((sub - 0.55) / 0.35, 0, 1) * np.clip((0.35 - flat) / 0.25, 0, 1))
