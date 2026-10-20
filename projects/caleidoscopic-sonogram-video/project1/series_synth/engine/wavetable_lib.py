"""
wavetable_lib -- the series-to-wavetable DSP, shared by the engine Script CHOPs.

Everything except read_config() is pure numpy and touches no TD object.

One cycle is built in five steps:
  extract    window of `length` months starting at fractional month `start`
  condition  detrend (mean / linear), optional ping-pong mirror, zero mean, peak 1
  resample   cyclic interpolation (step / linear / Catmull-Rom cubic) to `size` samples
  shape      waveshaper (tanh / hard clip / sine fold / bitcrush), dry-wet, DC removed
  bandlimit  zero every harmonic above Nyquist for the playback pitch (no aliasing)

Pitch only changes the playback rate of the finished table, so the waveform
keeps its shape across the keyboard; band-limiting removes only the harmonics
the sample rate cannot carry at that pitch.
"""
from typing import Optional, Tuple

import numpy as np

TABLE_SIZE = 2048          # samples per audio wavetable cycle
FRAME_SIZE = 256           # samples per cycle in the 3D frame stack
NUM_FRAMES = 32            # windows spread over the whole history for the 3D stack
NUM_HARMONICS = 64         # harmonics reported by harmonics_db()
SAMPLE_RATE = 44100.0
_NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def note_to_hz(note: float, cents: float = 0.0) -> float:
    """Equal-tempered frequency of a (fractional) MIDI note plus cents."""
    return 440.0 * 2.0 ** ((note - 69.0) / 12.0 + cents / 1200.0)


def note_name(note: float) -> str:
    """Nearest note name with octave, e.g. 45 -> 'A2'."""
    n = int(round(note))
    return '%s%d' % (_NOTE_NAMES[n % 12], n // 12 - 1)


def window_bounds(n: int, start: float, length: int, scan: Optional[float]) -> Tuple[float, int, float]:
    """(start, length, span) of the loop window inside n months.

    length is clipped to [4, n]; span = n - length is the room the start can move in.
    Without scan the start is clamped into [0, span]; with scan, start + scan is
    folded ping-pong into [0, span] so the window glides back and forth through history.
    """
    length = int(max(4, min(int(length), n)))
    span = float(n - length)
    if span <= 0.0:
        return 0.0, length, 0.0
    if scan is None:
        return min(max(float(start), 0.0), span), length, span
    period = 2.0 * span
    pos = (float(start) + float(scan)) % period
    return (period - pos if pos > span else pos), length, span


def extract(values: np.ndarray, start: float, length: int) -> np.ndarray:
    """`length` monthly values from fractional month `start` (linear between months)."""
    idx = start + np.arange(length, dtype=np.float64)
    return np.interp(idx, np.arange(len(values), dtype=np.float64), values)


def normalize(x: np.ndarray) -> np.ndarray:
    """Zero mean, peak absolute value 1."""
    x = x - x.mean()
    peak = np.abs(x).max()
    return x / peak if peak > 1e-12 else x


def condition(w: np.ndarray, loopmode: str, detrend: str) -> np.ndarray:
    """Make a window loopable: detrend, optional mirror, then normalize."""
    if detrend == 'linear' and len(w) > 1:
        # remove the line through the first and last month: the wrap has no step
        w = w - np.linspace(w[0], w[-1], len(w))
    if loopmode == 'pingpong' and len(w) > 2:
        w = np.concatenate([w, w[-2:0:-1]])
    return normalize(w)


def resample_cyclic(w: np.ndarray, size: int, interp: str) -> np.ndarray:
    """Resample a periodic sequence to `size` samples (step, linear or cubic)."""
    count = len(w)
    pos = np.arange(size, dtype=np.float64) * (count / float(size))
    i1 = np.floor(pos).astype(np.int64)
    f = pos - i1
    p1 = w[i1 % count]
    if interp == 'step':
        return p1.copy()
    p2 = w[(i1 + 1) % count]
    if interp == 'linear':
        return p1 + (p2 - p1) * f
    p0 = w[(i1 - 1) % count]
    p3 = w[(i1 + 2) % count]
    return p1 + 0.5 * f * (p2 - p0 + f * (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3
                                          + f * (3.0 * (p1 - p2) + p3 - p0)))


def shape(x: np.ndarray, mode: str, drive_db: float, bias: float, mix: float) -> np.ndarray:
    """Waveshape a normalized cycle; the result is level-matched (peak 1, no DC)."""
    if mode == 'crush':
        steps = 2.0 ** (max(1.0, 8.0 - drive_db / 6.0) - 1.0)   # 0 dB = 8 bit, 36 dB = 2 bit
        y = np.round(x * steps + bias) / steps
    else:
        u = x * 10.0 ** (drive_db / 20.0) + bias
        if mode == 'hard':
            y = np.clip(u, -1.0, 1.0)
        elif mode == 'fold':
            y = np.sin(0.5 * np.pi * u)
        else:
            y = np.tanh(u)
    return normalize((1.0 - mix) * x + mix * normalize(y))


def harmonic_limit(hz: float, size: int, sample_rate: float = SAMPLE_RATE) -> int:
    """Highest harmonic below Nyquist at `hz`, capped by the table resolution."""
    return int(min(size // 2, (0.5 * sample_rate) // max(hz, 1.0)))


def bandlimit(y: np.ndarray, hz: float, enabled: bool, sample_rate: float = SAMPLE_RATE) -> np.ndarray:
    """Remove harmonics above Nyquist for playback at `hz`; peak kept <= 1."""
    if not enabled:
        return y
    spectrum = np.fft.rfft(y)
    spectrum[harmonic_limit(hz, len(y), sample_rate) + 1:] = 0.0
    out = np.fft.irfft(spectrum, n=len(y))
    return out / max(1.0, np.abs(out).max())


def build_cycle(values: np.ndarray, start: float, length: int, cfg: dict, hz: float,
                size: int = TABLE_SIZE) -> Tuple[np.ndarray, np.ndarray]:
    """(raw, shaped) single cycles of `size` samples for one window of the series."""
    w = condition(extract(values, start, length), cfg['loopmode'], cfg['detrend'])
    raw = normalize(resample_cyclic(w, size, cfg['interp']))
    shaped = shape(raw, cfg['shapemode'], cfg['drive'], cfg['bias'], cfg['mix'])
    return raw, bandlimit(shaped, hz, cfg['bandlimit'])


def harmonics_db(y: np.ndarray, count: int = NUM_HARMONICS, floor_db: float = -90.0) -> np.ndarray:
    """Magnitudes of harmonics 1..count in dB relative to the strongest one."""
    mag = np.abs(np.fft.rfft(y))[1:count + 1]
    ref = max(float(mag.max()), 1e-12)
    return np.maximum(20.0 * np.log10(np.maximum(mag / ref, 1e-12)), floor_db)


def read_config(par) -> dict:
    """Main thread only: the wavetable settings from the SeriesSynth custom parameters."""
    return {
        'loopmode': par.Loopmode.eval(),
        'detrend': par.Detrend.eval(),
        'interp': par.Interp.eval(),
        'shapemode': par.Shapemode.eval(),
        'drive': float(par.Drive.eval()),
        'bias': float(par.Bias.eval()),
        'mix': float(par.Mix.eval()),
        'bandlimit': bool(par.Bandlimit.eval()),
    }
