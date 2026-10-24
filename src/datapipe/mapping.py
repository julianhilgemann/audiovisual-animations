"""Shared modulation math: numpy only, so the pipeline and Blender run this same file (SPEC §5.5, §15, §16).

By default every function treats its input as one loop of n frames: frame n-1 flows into frame 0. Envelopes wrap
around the seam, followers start from the state the end of the loop leaves them in, and accumulated motion is closed
so it ends a whole number of periods from where it started. ``wrap=False`` treats the input as a song with a start
and an end instead (methods B, C and D): nothing flows from the end into the start.
"""

import numpy as np


def follow(x: np.ndarray, attack: float, release: float, wrap: bool = True) -> np.ndarray:
    """One-pole envelope follower with attack and release time constants in frames: run twice around the loop, or
    once from the first value."""
    x = np.asarray(x, dtype=np.float64)
    up = np.exp(-1.0 / attack) if attack > 0 else 0.0
    down = np.exp(-1.0 / release) if release > 0 else 0.0
    y = np.empty_like(x)
    state = float(x[-1] if wrap else x[0])
    for _lap in range(2 if wrap else 1):
        for i, v in enumerate(x):
            c = up if v > state else down
            state = c * state + (1.0 - c) * v
            y[i] = state
    return y


def smooth(x: np.ndarray, frames: int, wrap: bool = True) -> np.ndarray:
    """Centred moving average over ``frames``, wrapping around the loop or holding the end values."""
    frames = max(1, int(frames))
    x = np.asarray(x, dtype=np.float64)
    if frames == 1:
        return x.copy()
    padded = np.concatenate([x[-frames:], x, x[:frames]]) if wrap else np.pad(x, frames, mode="edge")
    kernel = np.full(frames, 1.0 / frames)
    return np.convolve(padded, kernel, mode="same")[frames:-frames]


def normalize(x: np.ndarray, lo: float = 5.0, hi: float = 95.0) -> np.ndarray:
    """Scale so the ``lo`` and ``hi`` percentiles map to 0 and 1, clamped; a flat input becomes zeros."""
    a, b = np.percentile(x, [lo, hi])
    if b - a < 1e-9:
        return np.zeros(len(x))
    return np.clip((np.asarray(x, dtype=np.float64) - a) / (b - a), 0.0, 1.0)


def hit_envelope(hits: list, n: int, windup: int = 0, decay: float = 8.0, windup_level: float = 0.3,
                 wrap: bool = True) -> np.ndarray:
    """Envelopes for note-ons ``[(frame, amplitude), ...]``: the full amplitude on the hit frame, a rise to
    ``windup_level`` of it over ``windup`` frames before (anticipation), and an exponential decay to 5 % after
    ``decay`` frames. Overlapping hits take the maximum; with ``wrap`` everything wraps around the loop, without it
    a tail stops at the last frame and a wind-up at the first."""
    env = np.zeros(n)
    tau = max(float(decay), 1e-3) / 3.0
    tail = np.exp(-np.arange(n) / tau)
    for frame, amp in hits:
        f = int(frame) % n if wrap else int(frame)
        if not 0 <= f < n:
            continue
        if wrap:
            env = np.maximum(env, amp * np.roll(tail, f))
        else:
            env[f:] = np.maximum(env[f:], amp * tail[:n - f])
        for k in range(1, int(windup) + 1):
            i = (f - k) % n if wrap else f - k
            if 0 <= i < n:
                env[i] = max(env[i], amp * windup_level * (1.0 - (k - 1) / windup) ** 2)
    return env


def since_last_hit(hits: list, n: int, wrap: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Per frame: frames since the latest hit and that hit's amplitude; no hit yet (or none at all) gives a large
    age. With ``wrap`` the head of the loop still sees the last hit before the seam."""
    age, last = np.full(n, 1e5), np.zeros(n)
    if not hits:
        return age, last
    marks = {int(f) % n: float(a) for f, a in hits} if wrap else {int(f): float(a) for f, a in hits if 0 <= int(f) < n}
    if not marks:
        return age, last
    if not wrap:
        current_age, current_amp = None, 0.0
        for i in range(n):
            if i in marks:
                current_age, current_amp = 0.0, marks[i]
            elif current_age is not None:
                current_age += 1.0
            if current_age is not None:
                age[i], last[i] = current_age, current_amp
        return age, last
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


def integrate(rate: np.ndarray) -> tuple[np.ndarray, dict]:
    """Integrate a per-frame rate into n + 1 positions without closing anything (``loop = false``)."""
    rate = np.asarray(rate, dtype=np.float64)
    return np.concatenate([[0.0], np.cumsum(rate)]), {"how": "open"}


# ---- a run's modulators -> a look's signals (every look, in Blender) ------------------------------------------------

def look_signals(controls: dict, cfg: dict, levels: tuple) -> dict[str, np.ndarray]:
    """A look's 0-1 signals from the run's modulators (controls.json), as a method's mapping wires them; a signal
    the mapping leaves out of ``levels`` is zero. Also the ring's track (``kick_age``, ``kick_last``) and the
    twist's hue jump (``hue_off``)."""
    n, wrap = controls["frames"], controls.get("wrap", True)
    zeros = np.zeros(n)
    hit_shapes = cfg.get("hit", {})
    ease = int(cfg.get("motion", {}).get("section_ease", 15))

    def source(name: str) -> np.ndarray:
        kind, _, key = name.partition(":")
        if kind == "hit":
            track = controls["tracks"].get(key)
            shape = {**hit_shapes.get("default", {}), **hit_shapes.get(key, {})}
            return (hit_envelope(track["hits"], n, shape.get("windup", 0), shape.get("decay", 8), wrap=wrap)
                    if track else zeros)
        if kind == "stem":
            return np.asarray(controls["stems"].get(key, {}).get("loud", zeros))
        if kind == "mix":
            return np.asarray(controls["mix"][key])
        if kind == "band":
            return np.asarray(controls.get("bands", {}).get(key, zeros))
        if kind == "curve":
            return np.asarray(controls["curves"].get(key, zeros))
        if kind == "section":
            return section(controls, key, ease)
        if kind == "feature":
            return np.asarray(controls.get("features", {}).get(key, zeros))
        raise ValueError(f"mapping: unknown source {name!r}")

    out = {name: np.clip(sum((w * source(s) for s, w in sources.items()), zeros), 0.0, 1.0)
           for name, sources in cfg["signals"].items()}
    for name, frames in cfg.get("smooth", {}).items():
        out[name] = smooth(out[name], frames, wrap)
    for name in levels:
        out.setdefault(name, zeros)
    ring_cfg = cfg.get("ring", {})
    ring = controls["tracks"].get(ring_cfg.get("track", "kick"))
    out["kick_age"], last = since_last_hit(ring["hits"] if ring else [], n, wrap)
    out["kick_last"] = float(ring_cfg.get("level", 1.0)) * last
    out["hue_off"] = float(cfg.get("motion", {}).get("twist_hue", 0.0)) * out["twist"]
    return out


def available_sources(controls: dict) -> list[str]:
    """Every source a mapping can read from this run, as `kind:name`."""
    names = [f"hit:{t}" for t in controls.get("tracks", {})]
    names += [f"stem:{s}" for s in controls.get("stems", {})]
    names += [f"mix:{m}" for m in controls.get("mix", {})]
    names += [f"band:{b}" for b in controls.get("bands", {})]
    names += [f"curve:{c}" for c in controls.get("curves", {})]
    names += [f"section:{s}" for s in dict.fromkeys(s["name"] for s in controls.get("sections", []))]
    names += [f"feature:{f}" for f in controls.get("features", {})]
    return names


def section(controls: dict, name: str, ease: int) -> np.ndarray:
    """1 inside a section of the story, with linear ramps of ``ease`` frames centred on its edges."""
    n = controls["frames"]
    starts = sorted((s["frame"], s["name"]) for s in controls["sections"]) + [(n, "")]
    gate = np.zeros(n)
    for (a, nm), (b, _) in zip(starts, starts[1:]):
        if nm == name:
            gate[a:b] = 1.0
    return smooth(gate, ease, controls.get("wrap", True))
