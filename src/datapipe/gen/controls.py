"""S3: a run's stems and score become per-frame modulators in controls.json (dawdreamer/specs/handoff.md, controls.json).

Look-independent: hits come straight from the score, loudness from each stem on the 800-sample hop (one video frame,
no centring), brightness from the mix. A Blender project maps them onto its own parameters with datapipe.mapping.
"""

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from .. import mapping
from .score import FPS, FRAMES, SAMPLE_RATE, SAMPLES, Score, frame_table

HOP = SAMPLES // FRAMES        # 800
FLOOR_DB = 48                  # loudness below the stem's peak minus this counts as silence


def loudness(x: np.ndarray, attack: float, release: float) -> np.ndarray:
    """0-1 loudness envelope of a (samples, channels) loop: RMS per frame in dB, followed, then normalised."""
    mono = x.mean(axis=1) if x.ndim == 2 else x
    rms = np.sqrt((mono[:SAMPLES].reshape(FRAMES, HOP) ** 2).mean(axis=1))
    db = 20 * np.log10(rms + 1e-9)
    db = np.maximum(db, db.max() - FLOOR_DB)
    return mapping.normalize(mapping.follow(db, attack, release))


def brightness(x: np.ndarray, smooth_frames: int = 8) -> np.ndarray:
    """0-1 spectral centroid (log frequency) per frame, from a 2048-sample window starting on the frame."""
    mono = x.mean(axis=1) if x.ndim == 2 else x
    n = 2048
    wrapped = np.concatenate([mono, mono[:n]])
    starts = np.arange(FRAMES) * HOP
    windows = wrapped[starts[:, None] + np.arange(n)[None, :]] * np.hanning(n)
    power = np.abs(np.fft.rfft(windows, axis=1)) ** 2
    freqs = np.fft.rfftfreq(n, 1 / SAMPLE_RATE)
    band = (freqs >= 60) & (freqs <= 16000)
    centroid = (power[:, band] * freqs[band]).sum(axis=1) / (power[:, band].sum(axis=1) + 1e-12)
    return mapping.normalize(mapping.smooth(np.log2(centroid + 1.0), smooth_frames))


def build(run_dir: Path) -> dict:
    """Everything a look needs from one run, one value per video frame (480)."""
    run_dir = Path(run_dir)
    score = Score.load(run_dir / "score.json")
    header, rows = frame_table(score)
    col = {name: [r[i] for r in rows] for i, name in enumerate(header)}

    tracks = {}
    for name, notes in score.tracks.items():
        if not notes:
            continue
        hits = {}
        for n in notes:                        # chords: one hit per frame, the loudest note
            f = score.frame_of(n.beat) - 1
            hits[f] = max(hits.get(f, 0.0), round(n.vel / 127, 4))
        tracks[name] = {"hits": sorted([f, a] for f, a in hits.items()), "gate": col[f"{name}_gate"]}
        if f"{name}_pitch" in col:
            tracks[name]["pitch"] = col[f"{name}_pitch"]

    stems = {}
    for wav in sorted((run_dir / "stems").glob("*.wav")):
        x, _ = sf.read(wav, always_2d=True)
        stems[wav.stem] = {"loud": _rounded(loudness(x, attack=1, release=7))}
    mix, _ = sf.read(run_dir / "mix.wav", always_2d=True)

    return {
        "fps": FPS, "frames": FRAMES, "bpm": score.bpm, "frames_per_beat": score.frames_per_beat,
        "sections": [{"name": s, "frame": score.frame_of(b) - 1} for s, b in score.sections],
        "section": col["section"],
        "phase": _rounded(col["phase"]),
        "curves": {name: _rounded(col[f"{name}_curve"]) for name in score.automation},
        "tracks": tracks,
        "stems": stems,
        "mix": {"loud": _rounded(loudness(mix, attack=2, release=12)), "bright": _rounded(brightness(mix))},
        "meta": {k: score.meta.get(k) for k in ("preset", "seed", "key", "mode", "violation")},
    }


def save(run_dir: Path) -> Path:
    path = Path(run_dir) / "controls.json"
    path.write_text(json.dumps(build(run_dir), separators=(",", ":")) + "\n", encoding="utf-8")
    return path


def _rounded(values) -> list[float]:
    return [round(float(v), 5) for v in values]
