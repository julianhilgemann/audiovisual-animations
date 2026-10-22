"""Shared modulation math: numpy only, so the pipeline and Blender run this same file (SPEC §5.5, §15).

Every function treats its input as one loop of n frames: frame n-1 flows into frame 0. Envelopes wrap around the
seam, followers start from the state the end of the loop leaves them in, and accumulated motion is closed so it
ends a whole number of periods from where it started.
"""

import numpy as np


def follow(x: np.ndarray, attack: float, release: float) -> np.ndarray:
    """One-pole envelope follower with attack and release time constants in frames, run twice around the loop."""
    x = np.asarray(x, dtype=np.float64)
    up = np.exp(-1.0 / attack) if attack > 0 else 0.0
    down = np.exp(-1.0 / release) if release > 0 else 0.0
    y = np.empty_like(x)
    state = float(x[-1])
    for _lap in range(2):
        for i, v in enumerate(x):
            c = up if v > state else down
            state = c * state + (1.0 - c) * v
            y[i] = state
    return y


def smooth(x: np.ndarray, frames: int) -> np.ndarray:
    """Centred moving average over ``frames``, wrapping around the loop."""
    frames = max(1, int(frames))
    if frames == 1:
        return np.asarray(x, dtype=np.float64).copy()
    padded = np.concatenate([x[-frames:], x, x[:frames]])
    kernel = np.full(frames, 1.0 / frames)
    return np.convolve(padded, kernel, mode="same")[frames:-frames]


def normalize(x: np.ndarray, lo: float = 5.0, hi: float = 95.0) -> np.ndarray:
    """Scale so the ``lo`` and ``hi`` percentiles map to 0 and 1, clamped; a flat input becomes zeros."""
    a, b = np.percentile(x, [lo, hi])
    if b - a < 1e-9:
        return np.zeros(len(x))
    return np.clip((np.asarray(x, dtype=np.float64) - a) / (b - a), 0.0, 1.0)


def hit_envelope(hits: list, n: int, windup: int = 0, decay: float = 8.0, windup_level: float = 0.3) -> np.ndarray:
    """Envelopes for note-ons ``[(frame, amplitude), ...]``: the full amplitude on the hit frame, a rise to
    ``windup_level`` of it over ``windup`` frames before (anticipation), and an exponential decay to 5 % after
    ``decay`` frames. Overlapping hits take the maximum; everything wraps around the loop."""
    env = np.zeros(n)
    tau = max(float(decay), 1e-3) / 3.0
    tail = np.exp(-np.arange(n) / tau)
    for frame, amp in hits:
        f = int(frame) % n
        env = np.maximum(env, amp * np.roll(tail, f))
        for k in range(1, int(windup) + 1):
            i = (f - k) % n
            env[i] = max(env[i], amp * windup_level * (1.0 - (k - 1) / windup) ** 2)
    return env


def since_last_hit(hits: list, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Per frame: frames since the latest hit (wrapping) and that hit's amplitude; no hits gives a large age."""
    age, last = np.full(n, 1e5), np.zeros(n)
    if not hits:
        return age, last
    marks = {int(f) % n: float(a) for f, a in hits}
    start = max(marks)                       # walk from the last hit, so the head inherits the wrap
    current_age, current_amp = 0.0, marks[start]
    for step in range(1, n + 1):
        i = (start + step) % n
        if i in marks:
            current_age, current_amp = 0.0, marks[i]
        else:
            current_age += 1.0
        age[i], last[i] = current_age, current_amp
    return age, last


def close_loop(rate: np.ndarray, period: float) -> tuple[np.ndarray, dict]:
    """Integrate a per-frame rate into a position that, one loop later, is a whole number of ``period``s from where
    it started, so frame n is the same picture as frame 0. Returns n + 1 positions (the last one is frame n, the
    loop's restart) and what was done.

    The nearest whole number of periods (zero allowed) is reached by adding one constant to every frame's rate,
    which keeps the music's ups and downs intact. When that would make a forward motion run backwards, the rate is
    scaled instead.
    """
    rate = np.asarray(rate, dtype=np.float64)
    n, total = len(rate), float(rate.sum())
    turns = int(round(total / period))
    target = turns * period
    shift = (target - total) / n
    if rate.min() >= 0 and (rate + shift).min() < 0 and total > 0:
        turns = max(turns, 1)
        target = turns * period
        adjusted, how = rate * (target / total), "scaled"
    else:
        adjusted, how = rate + shift, "shifted"
    position = np.concatenate([[0.0], np.cumsum(adjusted)])
    return position, {"periods": turns, "raw_periods": round(total / period, 3), "how": how}
