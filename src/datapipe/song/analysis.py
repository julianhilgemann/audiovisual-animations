"""Tempo, beat and bar grid, and song structure from audio (SPEC §5.2, §5.4, §16.3).

The beat grid has a constant tempo, as a song made in a DAW does: librosa gives the rough tempo, then a comb over the
onset curve (kick-weighted, 4 ms steps) finds the exact beat length and phase. Beat 1 is the phase with snares on
2 and 4, kicks and loudness steps on 1 (4/4). Sections come from bar loudness: loud runs of at least 4 bars are
drops, quiet ones intro, build, breakdown or outro by where they sit. The drop is the loud section with the biggest
step up from the one before.
"""

import librosa
import numpy as np
from scipy.ndimage import maximum_filter1d

from .. import mapping
from ..features import FPS, HOP, SAMPLE_RATE
from . import onsets

BEATS_PER_BAR = 4
MIN_SECTION_BARS = 4
STEP = onsets.DET_HOP / SAMPLE_RATE                       # seconds per onset-curve step


def track_beats(x: np.ndarray, bpm: float | None = None) -> dict:
    """A constant-tempo beat grid: beat times (s) from the start of the file, the index of the first beat that is
    a downbeat, and the tempo. ``bpm`` (song.toml or --bpm) fixes the tempo; the phase is still found."""
    mag, freqs = onsets.spectrogram(x)
    kick = _unit(onsets.novelty(mag, freqs, *onsets.DRUM_BANDS["kick"]))
    snare = _unit(onsets.novelty(mag, freqs, *onsets.DRUM_BANDS["snare"]))
    full = _unit(onsets.novelty(mag, freqs, 30, 16000))
    if bpm:
        rough, span = float(bpm), 0.0
    else:
        m = x.mean(axis=1) if x.ndim == 2 else x
        env = librosa.onset.onset_strength(y=m, sr=SAMPLE_RATE, hop_length=480)
        rough, span = float(np.atleast_1d(librosa.feature.tempo(onset_envelope=env, sr=SAMPLE_RATE, hop_length=480))[0]), 0.03
        rough = _meter(kick + 0.5 * full, rough)
    period, phase, fit = _comb(kick + 0.5 * full, rough, span)
    end = len(kick) * STEP
    beats = np.arange(phase, end, period)
    return {"bpm": round(60.0 / period, 2), "beats": beats, "downbeat": _downbeat(beats, kick, snare, x),
            "source": "given" if bpm else "tracked", "fit": round(fit, 3)}


def _unit(x: np.ndarray) -> np.ndarray:
    top = np.percentile(x, 99.5)
    return np.clip(x / top, 0.0, 1.0) if top > 0 else x


def _meter(env: np.ndarray, bpm: float) -> float:
    """librosa's tempo can sit on a wrong meter (120 for half-time 180, whose felt beat is 90). A tempo 3/4, 2/3,
    4/3 or 3/2 of it wins when its grid lands on at least 15 % more onset energy; octaves stay librosa's call
    (measured on generated phonk, house and techno: phonk 0.83 at 90 against 0.65 at 120; house 1.21 at 120
    against 1.18 at 80)."""
    fit = _comb(env, bpm, 0.01)[2]
    best = (fit * 1.15, bpm)
    for ratio in (3 / 4, 2 / 3, 4 / 3, 3 / 2):
        if 60 <= bpm * ratio <= 200:
            other = _comb(env, bpm * ratio, 0.01)[2]
            if other > best[0]:
                best = (other, bpm * ratio)
    return best[1]


def _comb(env: np.ndarray, bpm: float, span: float) -> tuple[float, float, float]:
    """The beat length and phase (s) whose grid lands on the most onset energy (±1 step), searched within
    ``span`` of ``bpm`` in 0.01 BPM steps; returns them and the mean energy on the grid."""
    smooth = maximum_filter1d(env, 3)
    best = (-1.0, 60.0 / bpm, 0.0)
    for b in (np.arange(bpm * (1 - span), bpm * (1 + span), 0.01) if span else [bpm]):
        p = 60.0 / b / STEP
        k = np.arange(int((len(env) - 1) / p))
        if not len(k):
            continue
        idx = np.round(np.arange(int(np.ceil(p)))[:, None] + k[None, :] * p).astype(int)
        scores = smooth[np.minimum(idx, len(env) - 1)].mean(axis=1)
        j = int(np.argmax(scores))
        if scores[j] > best[0]:
            best = (float(scores[j]), p * STEP, j * STEP)
    return best[1], best[2], best[0]


def _downbeat(beats: np.ndarray, kick: np.ndarray, snare: np.ndarray, x: np.ndarray) -> int:
    """Which of the first 4 beats is beat 1: snares on 2 and 4 rather than 1 and 3, kicks on 1, and the steps up
    in loudness (a section starting) on 1."""
    if len(beats) < 2 * BEATS_PER_BAR:
        return 0
    steps = np.clip(np.round(beats / STEP).astype(int), 0, len(kick) - 1)
    near = lambda env: np.array([env[max(0, s - 2):s + 3].max() for s in steps])  # noqa: E731
    k, s = near(kick), near(snare)
    db = frame_db(x)
    frames = np.clip(np.round(beats * FPS).astype(int), 0, len(db) - 1)
    beat_frames = max(1, int(np.diff(beats).mean() * FPS))
    rise = np.array([max(0.0, db[f:f + beat_frames].mean() - db[max(0, f - beat_frames):f].mean())
                     if f > 0 else 0.0 for f in frames]) / 6.0
    scores = []
    for p in range(BEATS_PER_BAR):
        pos = (np.arange(len(beats)) - p) % BEATS_PER_BAR
        one, two, three, four = (pos == 0), (pos == 1), (pos == 2), (pos == 3)
        scores.append(k[one].mean() + s[two].mean() + s[four].mean() - s[one].mean() - s[three].mean()
                      + 2 * rise[one].mean())
    return int(np.argmax(scores))


def grid(beats: np.ndarray, n: int, first_downbeat: int = 0, bpm: float = 120.0) -> dict:
    """Per frame: beat phase and bar phase (0-1 ramps), and the bar starts as frames. The grid runs on before the
    first and after the last beat at the same beat length."""
    beats = np.asarray(beats, dtype=np.float64)
    period = float(np.diff(beats).mean()) if len(beats) >= 2 else 60.0 / bpm
    if not len(beats):
        beats = np.array([0.0])
    end = n / FPS
    before = np.arange(beats[0] - period, -period - 1e-9, -period)[::-1]
    after = np.arange(beats[-1] + period, end + 2 * period, period)
    full = np.concatenate([before, beats, after])
    downbeat = len(before) + first_downbeat                # index of a downbeat in ``full``
    t = np.arange(n) / FPS
    idx = np.clip(np.searchsorted(full, t, side="right") - 1, 0, len(full) - 2)
    beat_phase = np.clip((t - full[idx]) / (full[idx + 1] - full[idx]), 0.0, 1.0)
    in_bar = (idx - downbeat) % BEATS_PER_BAR
    bar_phase = (in_bar + beat_phase) / BEATS_PER_BAR
    bar_beats = full[downbeat % BEATS_PER_BAR::BEATS_PER_BAR]
    bar_frames = sorted({int(np.floor(b * FPS + 0.5)) for b in bar_beats if 0 <= b * FPS < n})
    if not bar_frames or bar_frames[0] >= period * BEATS_PER_BAR * FPS / 2:
        bar_frames = [0] + bar_frames                      # a pickup before the first full bar
    else:
        bar_frames[0] = 0                                  # the first bar starts with the file
    return {"beat": beat_phase, "bar": bar_phase, "bar_frames": bar_frames, "beat_seconds": period}


def frame_db(x: np.ndarray) -> np.ndarray:
    """RMS level per frame in dB."""
    m = x.mean(axis=1) if x.ndim == 2 else x
    n = len(m) // HOP
    return 20 * np.log10(np.sqrt((m[:n * HOP].reshape(n, HOP) ** 2).mean(axis=1)) + 1e-9)


def sections(x: np.ndarray, bar_frames: list[int], n: int) -> dict:
    """Song structure on the bar grid: [(name, frame)], the drop's frame (or None) and the bar energy per frame."""
    db = frame_db(x)
    edges = list(bar_frames) + [n]
    energy = np.array([db[a:b].mean() if b > a else db[a] for a, b in zip(edges, edges[1:])])
    per_frame = np.repeat(energy, np.diff(edges))
    lo, hi = np.percentile(energy, 10), np.percentile(energy, 90)
    if len(energy) < 2 * MIN_SECTION_BARS or hi - lo < 3.0:
        return {"sections": [("main", 0)], "drop": None, "energy": per_frame}
    loud = energy >= (lo + hi) / 2
    runs = _runs(loud)
    while len(runs) > 1 and min(b - a for a, b, _ in runs) < MIN_SECTION_BARS:
        i = min(range(len(runs)), key=lambda k: runs[k][1] - runs[k][0])
        a, b, _ = runs[i]
        j = i - 1 if i > 0 else i + 1                      # a short run joins its neighbour
        na, nb, nl = runs[j]
        runs[j] = (min(a, na), max(b, nb), nl)
        del runs[i]
        runs = _merge_same(runs)

    named, drop, best_step = [], None, -np.inf
    for i, (a, b, is_loud) in enumerate(runs):
        mean = energy[a:b].mean()
        if is_loud:
            name = "drop"
            step = mean - energy[runs[i - 1][0]:runs[i - 1][1]].mean() if i > 0 else -np.inf
            if step > best_step:
                best_step, drop = step, edges[a]
        elif i == 0:
            name = "intro"
        elif i == len(runs) - 1:
            name = "outro"
        elif runs[i + 1][2]:
            half = (a + b) // 2
            rising = b - a >= 2 and energy[half:b].mean() > energy[a:half].mean() + 1.0
            name = "build" if rising else "breakdown"
        else:
            name = "breakdown"
        named.append((name, edges[a] if i else 0))
    if drop is None and any(nm == "drop" for nm, _ in named):
        drop = next(f for nm, f in named if nm == "drop")
    return {"sections": named, "drop": drop, "energy": per_frame}


def _runs(flags: np.ndarray) -> list[tuple[int, int, bool]]:
    out, start = [], 0
    for i in range(1, len(flags) + 1):
        if i == len(flags) or flags[i] != flags[start]:
            out.append((start, i, bool(flags[start])))
            start = i
    return out


def _merge_same(runs: list) -> list:
    out = []
    for a, b, flag in sorted(runs):
        if out and out[-1][2] == flag:
            out[-1] = (out[-1][0], b, flag)
        else:
            out.append((a, b, flag))
    return out


def section_index(named: list[tuple[str, int]], n: int) -> np.ndarray:
    starts = [f for _, f in named] + [n]
    out = np.zeros(n, dtype=int)
    for i, (a, b) in enumerate(zip(starts, starts[1:])):
        out[a:b] = i
    return out


def build_curve(named: list[tuple[str, int]], n: int) -> np.ndarray:
    """0 -> 1 across every build section (arc.build of §5.4), 0 elsewhere."""
    curve = np.zeros(n)
    starts = [f for _, f in named] + [n]
    for (name, a), b in zip(named, starts[1:]):
        if name == "build" and b > a:
            curve[a:b] = np.linspace(0.0, 1.0, b - a)
    return curve


def energy_curve(per_frame_db: np.ndarray, frames_per_bar: float) -> np.ndarray:
    """Bar loudness as a 0-1 curve, smoothed over a bar (arc.energy of §5.4)."""
    return mapping.normalize(mapping.smooth(per_frame_db, max(1, int(frames_per_bar)), wrap=False), 2, 98)
