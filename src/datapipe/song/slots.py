"""S3 for method E (SPEC §16.7): instrument-agnostic stems. Every stem is a slot (slot1, slot2, ...) and gets the same
generic features whatever it holds, so a field recording and a bass line are read the same way: no roles, no kick or
snare, no tempo or sections unless a tempo is given.

| Feature (``features["slot<N>.<name>"]``) | What | Scale |
| loud | RMS loudness, followed 1 / 7 frames | the slot's own 5-95 % range |
| transient | onset strength (SuperFlux over the whole band), the largest step in each frame, released over 4 | fixed |
| density | onsets per second over the surrounding second | fixed: 8 a second is 1 |
| crest | peak against RMS over 100 ms: how percussive | fixed: a sine 0, a click 1 |
| bright | spectral centroid (log) | own range |
| flat | spectral flatness: noisy against tonal | fixed: a tone 0, white noise 1 |
| low, mid, high | energy under 250 Hz, 250 Hz-4 kHz, over 4 kHz | own range each |
| active | 1 while the slot plays: within 30 dB of its loud end and above -60 dBFS; on at once, out over 6 | fixed |

The normalised features (loud, bright, low, mid, high) and flat are multiplied by ``active``, so a slot's noise floor
is not normalised up into motion; transient, density and crest are on fixed scales and read 0 in silence anyway. The
slot's onsets are its hits (``tracks["slot<N>"]``); a hit must reach an absolute onset strength, so a drone or a
texture has none. ``curves.energy`` is the master's short-term loudness (K-weighted, 3 s), the slow level.
"""

import numpy as np

from .. import features, mapping
from ..features import FPS, rounded
from . import analysis, onsets
from .controls import free_grid
from .deep import window_lufs
from .ingest import Song

SLOT_BANDS = {"low": (20, 250), "mid": (250, 4000), "high": (4000, 16000)}
TRANSIENT_FULL = 1.0           # onset strength per bin that reads as transient 1
# Onset strength per bin a hit must reach. Measured (SuperFlux per bin, 30 Hz-16 kHz): a wandering noise texture
# peaks at 0.12 and a drone at 0.006; hits of a synthetic kick stem sit at 0.48-0.57, hats 0.98-1.8, snare 1.3-1.6,
# noise bursts 1.3-2.3. Tonal bass note onsets (0.03-0.25) mostly fall under it.
MIN_FLUX = 0.25
DENSITY_FULL = 8.0             # onsets per second that read as density 1
ACTIVE_RANGE_DB = 30
ACTIVE_FLOOR_DB = -60


def build(song: Song, bpm: float | None = None, progress=print) -> dict:
    """controls.json for method E: the slots' features and hits, the master's loudness, brightness and bands."""
    n, master = song.frames, song.master
    bpm = bpm or song.settings.get("bpm")
    progress("  slots")
    tracks, feats = {}, {}
    for slot in sorted(song.stems, key=lambda s: int(s.removeprefix("slot"))):
        hits, curves = slot_features(song.stems[slot], n)
        tracks[slot] = {"hits": hits, "source": "onset"}
        feats.update({f"{slot}.{name}": rounded(v) for name, v in curves.items()})
    grid, tempo_source = free_grid(master, n, bpm)
    named = [("main", 0)]
    short = window_lufs(master, n, 180)                    # the slow level, so a burst's loudness doesn't lead
    energy = mapping.normalize(np.maximum(short, short.max() - features.FLOOR_DB))
    meta = {"method": song.method, "title": song.title, "files": song.files, "warnings": song.warnings,
            "slots": {slot: song.files[slot] for slot in tracks}, "tempo_source": tempo_source,
            "sections_from": "none", "drop_frame": None, "roles": [],
            "detection": {k: len(v["hits"]) for k, v in tracks.items()}}
    return {
        "method": song.method, "wrap": False, "close": bool(song.settings.get("loop", True)),
        "fps": FPS, "frames": n, **grid,
        "sections": [{"name": name, "frame": int(f)} for name, f in named],
        "section": analysis.section_index(named, n).tolist(),
        "phase": rounded(np.arange(n) / n),
        "curves": {"energy": rounded(energy)},
        "tracks": tracks,
        "stems": {},
        "features": feats,
        "mix": {"loud": rounded(features.loudness(master, attack=2, release=12, wrap=False)),
                "bright": rounded(features.brightness(master, wrap=False))},
        "bands": {k: rounded(v) for k, v in features.bands(master, wrap=False).items()},
        "meta": meta,
    }


def slot_features(x: np.ndarray, n: int) -> tuple[list[list], dict[str, np.ndarray]]:
    """One stem's hits and its generic features, n values each (see the module table)."""
    mag, freqs = onsets.spectrogram(x)
    bins = int(((freqs >= 30) & (freqs < 16000)).sum())
    nov = onsets.novelty(mag, freqs, 30, 16000) / bins
    hits = [h for h in onsets.pick(nov, onsets.level_db(mag, freqs, 30, 16000), floor=MIN_FLUX) if h[0] < n]

    active = activity(x)
    transient = mapping.follow(np.clip(onsets.per_frame(nov, n) / TRANSIENT_FULL, 0.0, 1.0), 0, 4, wrap=False)
    marks = np.zeros(n)
    for f, _ in hits:
        marks[int(f)] += 1.0
    density = mapping.smooth(np.convolve(marks, np.ones(FPS), mode="same") / DENSITY_FULL, 15, wrap=False)
    gated = {
        "loud": features.loudness(x, attack=1, release=7, wrap=False),
        "bright": features.brightness(x, wrap=False),
        "flat": features.flatness(x, wrap=False),
        **features.bands(x, wrap=False, table=SLOT_BANDS),
    }
    gated = {k: v * active for k, v in gated.items()}
    return hits, {"loud": gated["loud"], "transient": transient, "density": np.clip(density, 0.0, 1.0),
                  "crest": mapping.smooth(features.crest(x, 6, wrap=False), 6, wrap=False),
                  "bright": gated["bright"], "flat": gated["flat"],
                  **{k: gated[k] for k in SLOT_BANDS}, "active": active}


def activity(x: np.ndarray) -> np.ndarray:
    """1 while a stem plays: its frame level within ``ACTIVE_RANGE_DB`` of its loud end (95th percentile) and above
    ``ACTIVE_FLOOR_DB``. It opens on the frame the level crosses, so an onset is not dimmed, and eases out over 6
    frames. A silent stem is never active."""
    db = analysis.frame_db(x)
    threshold = max(float(np.percentile(db, 95)) - ACTIVE_RANGE_DB, ACTIVE_FLOOR_DB)
    return mapping.follow((db > threshold).astype(np.float64), 0, 6, wrap=False)
