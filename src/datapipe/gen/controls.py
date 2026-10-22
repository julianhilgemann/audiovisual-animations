"""S3: a run's stems and score become per-frame modulators in controls.json (dawdreamer/specs/handoff.md, controls.json).

Look-independent: hits come straight from the score, loudness from each stem on the 800-sample hop (one video frame,
no centring), brightness and band energies from the mix. A Blender project maps them onto its own parameters with
datapipe.mapping. The song methods (B, C, D) write the same contract (src/datapipe/song/controls.py).
"""

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from ..features import bands, brightness, loudness, rounded
from .score import FPS, FRAMES, Score, frame_table


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
        tracks[name] = {"hits": sorted([f, a] for f, a in hits.items()), "gate": col[f"{name}_gate"], "source": "score"}
        if f"{name}_pitch" in col:
            tracks[name]["pitch"] = col[f"{name}_pitch"]

    stems = {}
    for wav in sorted((run_dir / "stems").glob("*.wav")):
        x, _ = sf.read(wav, always_2d=True)
        stems[wav.stem] = {"loud": rounded(loudness(x, attack=1, release=7))}
    mix, _ = sf.read(run_dir / "mix.wav", always_2d=True)
    beats = np.arange(FRAMES) / score.frames_per_beat

    return {
        "method": "gen", "wrap": True, "close": True,
        "fps": FPS, "frames": FRAMES, "bpm": score.bpm, "frames_per_beat": score.frames_per_beat,
        "sections": [{"name": s, "frame": score.frame_of(b) - 1} for s, b in score.sections],
        "section": col["section"],
        "phase": rounded(col["phase"]),
        "beat": rounded(beats % 1.0),
        "bar": rounded(beats / 4 % 1.0),
        "curves": {name: rounded(col[f"{name}_curve"]) for name in score.automation},
        "tracks": tracks,
        "stems": stems,
        "mix": {"loud": rounded(loudness(mix, attack=2, release=12)), "bright": rounded(brightness(mix))},
        "bands": {k: rounded(v) for k, v in bands(mix).items()},
        "meta": {k: score.meta.get(k) for k in ("preset", "seed", "key", "mode", "violation")},
    }


def save(run_dir: Path) -> Path:
    path = Path(run_dir) / "controls.json"
    path.write_text(json.dumps(build(run_dir), separators=(",", ":")) + "\n", encoding="utf-8")
    return path
