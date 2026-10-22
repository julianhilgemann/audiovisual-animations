"""S3 for method F (SPEC §16.7): one complex track measured from every side, each feature hard-mapped to one part of
the look (mappings/deep.toml), so a recipe means the same on every track.

| Feature (``features[name]``) | What | Scale |
| loud.momentary, loud.short | K-weighted loudness (BS.1770), centred 400 ms and 3 s windows | own range (LUFS in meta) |
| loud.dynamics | peak against RMS over 400 ms, a local PLR | fixed: a sine 0, a click 1 |
| spectrum.rolloff | the frequency under which 85 % of the energy lies (log) | own range |
| spectrum.bandwidth | the spread of the spectrum around its centroid (log frequency) | own range |
| spectrum.flatness | noisy against tonal | fixed: a tone 0, white noise 1 |
| spectrum.flux | how much the spectrum rises from one frame to the next | own top |
| onset.<band> | onset strength in each band of ``bands`` (sub, bass, lowmid, mid, highmid, air) | own top |
| stereo.width | side against mid energy over 100 ms | fixed: mono 0, uncorrelated 1 |
| stereo.balance | right against left energy | fixed: left 0, centre 0.5, right 1 |
| harmonic.loud, percussive.loud | energy of the harmonic and the percussive part (HPSS) | own range each |
| harmonic.share | harmonic energy against both | fixed: all percussive 0, all harmonic 1 |
| percussive.onset | onset strength of the percussive part | own top |
| pitch.class | the strongest pitch class of the harmonic part over 0.25 s: C 0, C# 1/12 ... B 11/12 | fixed |
| pitch.change | how fast the harmony moves (chroma distance over 0.25 s), times how harmonic the sound is | own range |
| section.novelty | how much the sound changes here (Foote novelty, self-similarity of 0.5 s blocks) | own range |

The centroid is ``mix.bright`` and the band energies are ``bands``, as in every song method. Hits are onsets of the
percussive part in three bands, ``low`` 30-150 Hz, ``mid`` 1-5 kHz and ``high`` 7-16 kHz: B's detector without its
kick-likeness weighting or drum names. Sections come from the novelty peaks, not a bar grid, so free-tempo material
still gets its changes: loud sections are drops, quiet ones intro, build, breakdown or outro by where they sit.
"""

import librosa
import numpy as np
import pyloudnorm
from scipy import signal
from scipy.ndimage import uniform_filter1d

from .. import features, mapping
from ..features import BANDS, FLOOR_DB, FPS, HOP, SAMPLE_RATE, rounded
from . import analysis, onsets
from .controls import free_grid
from .ingest import Song

HIT_BANDS = {"low": (30, 150), "mid": (1000, 5000), "high": (7000, 16000)}
# BS.1770 K-weighting at 48 kHz: a high shelf (+4 dB over ~1.5 kHz) and a high-pass at ~38 Hz.
K_SHELF = ([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585])
K_HIGHPASS = ([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621])
BLOCK = 30                     # frames per self-similarity block (0.5 s)
MIN_SECTION_S = 4.0
PITCH_FRAMES = 15              # 0.25 s: chroma smoothing and the distance pitch.change looks back


def build(song: Song, bpm: float | None = None, progress=print) -> dict:
    """controls.json for method F: every feature of the master, hits by band, sections from novelty."""
    n, master = song.frames, song.master
    bpm = bpm or song.settings.get("bpm")
    progress("  loudness and spectrum")
    feats, lufs = loudness_features(master, n)
    power, freqs = features.power_spectrum(master, 2048, wrap=False)
    feats.update(spectrum_features(master, power, freqs, n))
    feats.update(onset_features(master, n))
    feats.update(stereo_features(master, n))
    progress("  harmonic, percussive, pitch")
    tonal, chroma = harmonic_features(power, n)
    feats.update(tonal)
    progress("  hits and sections")
    tracks = {name: {"hits": [h for h in hits if h[0] < n], "source": "onset"}
              for name, hits in onsets.band_hits(master, HIT_BANDS, full_mix=True).items()}
    bands = features.bands(master, wrap=False)
    rows = np.vstack([np.array(list(bands.values())), chroma, feats["harmonic.share"][None, :]])
    nov = novelty(rows, n)
    feats["section.novelty"] = nov
    named, drop = sections(nov, rows, lufs["momentary_db"], n)
    grid, tempo_source = free_grid(master, n, bpm)

    meta = {"method": song.method, "title": song.title, "files": song.files, "warnings": song.warnings,
            "tempo_source": tempo_source, "sections_from": "novelty", "drop_frame": drop, "roles": [],
            "detection": {k: len(v["hits"]) for k, v in tracks.items()},
            "loudness": {k: v for k, v in lufs.items() if k != "momentary_db"}}
    return {
        "method": song.method, "wrap": False, "close": bool(song.settings.get("loop", True)),
        "fps": FPS, "frames": n, **grid,
        "sections": [{"name": name, "frame": int(f)} for name, f in named],
        "section": analysis.section_index(named, n).tolist(),
        "phase": rounded(np.arange(n) / n),
        "curves": {"build": rounded(analysis.build_curve(named, n)), "energy": rounded(feats["loud.short"])},
        "tracks": tracks,
        "stems": {},
        "features": {k: rounded(v) for k, v in feats.items()},
        "mix": {"loud": rounded(features.loudness(master, attack=2, release=12, wrap=False)),
                "bright": rounded(features.brightness(master, wrap=False))},
        "bands": {k: rounded(v) for k, v in bands.items()},
        "meta": meta,
    }


def window_lufs(x: np.ndarray, n: int, frames: int) -> np.ndarray:
    """K-weighted loudness (LUFS, ungated) per frame over a centred window of ``frames``."""
    y = signal.lfilter(*K_HIGHPASS, signal.lfilter(*K_SHELF, x, axis=0), axis=0)
    ms = (y[:n * HOP] ** 2).reshape(n, HOP, -1).mean(axis=1).sum(axis=1)
    return -0.691 + 10 * np.log10(uniform_filter1d(ms, frames, mode="nearest") + 1e-12)


def loudness_features(x: np.ndarray, n: int) -> tuple[dict[str, np.ndarray], dict]:
    """loud.momentary, loud.short and loud.dynamics; and the track's LUFS: integrated (gated, pyloudnorm), the
    loudest momentary and short-term values, and the momentary curve in dB for the sections."""
    momentary, short = window_lufs(x, n, 24), window_lufs(x, n, 180)

    def unit(db: np.ndarray) -> np.ndarray:
        return mapping.normalize(np.maximum(db, db.max() - FLOOR_DB))

    integrated = float(pyloudnorm.Meter(SAMPLE_RATE).integrated_loudness(x.astype(np.float64)))
    lufs = {"integrated": round(integrated, 2) if np.isfinite(integrated) else None,
            "momentary_max": round(float(momentary.max()), 2), "short_max": round(float(short.max()), 2),
            "momentary_db": momentary}
    return {"loud.momentary": unit(momentary), "loud.short": unit(short),
            "loud.dynamics": mapping.smooth(features.crest(x, 24, wrap=False), 6, wrap=False)}, lufs


def spectrum_features(x: np.ndarray, power: np.ndarray, freqs: np.ndarray, n: int) -> dict[str, np.ndarray]:
    """spectrum.rolloff, .bandwidth, .flatness and .flux from the 2048-sample spectrum on each frame."""
    band = (freqs >= 60) & (freqs <= 16000)
    p, logf = power[:, band], np.log2(freqs[band])
    total = p.sum(axis=1) + 1e-12
    rolloff = logf[np.argmax(np.cumsum(p, axis=1) >= 0.85 * total[:, None], axis=1)]
    centroid = (p * logf).sum(axis=1) / total
    bandwidth = np.sqrt((p * (logf[None, :] - centroid[:, None]) ** 2).sum(axis=1) / total)
    mag = np.sqrt(p)
    level = np.log1p(100.0 * mag / (mag.max() + 1e-12))
    flux = np.concatenate([[0.0], np.maximum(np.diff(level, axis=0), 0.0).mean(axis=1)])
    return {"spectrum.rolloff": mapping.normalize(mapping.smooth(rolloff, 8, wrap=False)),
            "spectrum.bandwidth": mapping.normalize(mapping.smooth(bandwidth, 8, wrap=False)),
            "spectrum.flatness": features.flatness(x, wrap=False),
            "spectrum.flux": mapping.follow(_top(flux), 0, 4, wrap=False)}


def onset_features(x: np.ndarray, n: int) -> dict[str, np.ndarray]:
    """onset.<band>: SuperFlux onset strength in each band of ``bands``, on the frame grid, released over 4 frames."""
    mag, freqs = onsets.spectrogram(x)
    return {f"onset.{name}": mapping.follow(_top(onsets.per_frame(onsets.novelty(mag, freqs, lo, hi), n)), 0, 4,
                                            wrap=False)
            for name, (lo, hi) in BANDS.items()}


def stereo_features(x: np.ndarray, n: int) -> dict[str, np.ndarray]:
    """stereo.width and stereo.balance over centred 100 ms windows; silence is mono and centred."""
    left, right = (x[:n * HOP, i].astype(np.float64).reshape(n, HOP) for i in (0, 1))

    def energy(v: np.ndarray) -> np.ndarray:
        return uniform_filter1d((v ** 2).mean(axis=1), 6, mode="nearest")

    mid, side, l_e, r_e = energy((left + right) / 2), energy((left - right) / 2), energy(left), energy(right)
    width = np.where(mid + side > 1e-10, side / (mid + side + 1e-24), 0.0)
    balance = np.where(l_e + r_e > 1e-10, r_e / (l_e + r_e + 1e-24), 0.5)
    return {"stereo.width": np.clip(mapping.smooth(2 * width, 6, wrap=False), 0.0, 1.0),
            "stereo.balance": mapping.smooth(balance, 6, wrap=False)}


def harmonic_features(power: np.ndarray, n: int) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """HPSS on the frame-rate spectrum (harmonic kernel 15 frames = 0.25 s, percussive 31 bins = 730 Hz): the two
    parts' loudness, the harmonic share, the percussive onsets, and pitch class and change from the harmonic part's
    chroma. Also returns the smoothed chroma (12, n) for the novelty."""
    mag = np.sqrt(power).T
    harmonic, percussive = librosa.decompose.hpss(mag, kernel_size=(15, 31))
    h_e, p_e = (harmonic ** 2).sum(axis=0), (percussive ** 2).sum(axis=0)

    def unit(e: np.ndarray) -> np.ndarray:
        db = 10 * np.log10(e + 1e-12)
        return mapping.normalize(mapping.follow(np.maximum(db, db.max() - FLOOR_DB), 1, 7, wrap=False))

    share = np.where(h_e + p_e > 1e-9, h_e / (h_e + p_e + 1e-12), 0.5)
    level = np.log1p(100.0 * percussive / (percussive.max() + 1e-12))
    p_flux = np.concatenate([[0.0], np.maximum(np.diff(level, axis=1), 0.0).mean(axis=0)])

    chroma = librosa.feature.chroma_stft(S=harmonic ** 2, sr=SAMPLE_RATE, n_fft=2048, tuning=0.0)
    chroma = uniform_filter1d(chroma, PITCH_FRAMES, axis=1, mode="nearest")
    unit_chroma = chroma / (np.linalg.norm(chroma, axis=0, keepdims=True) + 1e-12)
    before = np.concatenate([np.repeat(unit_chroma[:, :1], PITCH_FRAMES, axis=1), unit_chroma[:, :-PITCH_FRAMES]],
                            axis=1)[:, :n]
    change = (1.0 - (unit_chroma * before).sum(axis=0)) * np.clip(2 * share, 0.0, 1.0)
    return {"harmonic.loud": unit(h_e), "percussive.loud": unit(p_e),
            "harmonic.share": mapping.smooth(share, 6, wrap=False),
            "percussive.onset": mapping.follow(_top(p_flux), 0, 4, wrap=False),
            "pitch.class": np.argmax(chroma, axis=0) / 12.0,
            "pitch.change": mapping.normalize(mapping.smooth(change, 8, wrap=False))}, chroma


def novelty(rows: np.ndarray, n: int) -> np.ndarray:
    """0-1 Foote novelty per frame: ``rows`` (features, n) averaged into 0.5 s blocks and standardised, a cosine
    self-similarity matrix, and a Gaussian-tapered checkerboard kernel slid along its diagonal. The kernel spans
    a quarter of the track, at least 2 s and at most 8 s each side."""
    m = n // BLOCK
    if m < 8:
        return np.zeros(n)
    blocks = rows[:, :m * BLOCK].reshape(len(rows), m, BLOCK).mean(axis=2).T
    blocks = (blocks - blocks.mean(axis=0)) / (blocks.std(axis=0) + 1e-9)
    unit = blocks / (np.linalg.norm(blocks, axis=1, keepdims=True) + 1e-9)
    sim = unit @ unit.T
    half = int(np.clip(m // 8, 4, 16))
    k = np.arange(-half, half) + 0.5
    taper = np.exp(-(k / (0.5 * half)) ** 2)
    kernel = np.outer(np.sign(k), np.sign(k)) * np.outer(taper, taper)
    padded = np.pad(sim, half, mode="edge")
    curve = np.array([(kernel * padded[i:i + 2 * half, i:i + 2 * half]).sum() for i in range(m)])
    centres = (np.arange(m) + 0.5) * BLOCK
    return mapping.normalize(np.maximum(np.interp(np.arange(n), centres, curve), 0.0), 0, 100)


def sections(nov: np.ndarray, rows: np.ndarray, momentary_db: np.ndarray, n: int
             ) -> tuple[list[tuple[str, int]], int | None]:
    """Section starts at the novelty peaks (at least ``MIN_SECTION_S`` apart and from either end), each moved to the
    frame within a block where ``rows`` change most, named by loudness as B names its bars: loud runs are drops,
    quiet ones intro, build, breakdown or outro; neighbours with the same name join. Less than 3 dB between the 10th
    and 90th percentile of the momentary loudness, or no peak, gives one ``main`` section."""
    gap = int(MIN_SECTION_S * FPS)
    peaks, _ = signal.find_peaks(nov, distance=gap, prominence=0.2, height=0.3)
    starts = [0] + sorted({_sharpen(rows, int(p)) for p in peaks if gap <= p <= n - gap})
    lo, hi = np.percentile(momentary_db, [10, 90])
    if len(starts) < 2 or hi - lo < 3.0:
        return [("main", 0)], None
    edges = starts + [n]
    energy = [float(momentary_db[a:b].mean()) for a, b in zip(edges, edges[1:])]
    loud = [e >= (lo + hi) / 2 for e in energy]
    named = []
    for i, (a, b) in enumerate(zip(edges, edges[1:])):
        if loud[i]:
            name = "drop"
        elif i == 0:
            name = "intro"
        elif i == len(energy) - 1:
            name = "outro"
        elif loud[i + 1] and momentary_db[(a + b) // 2:b].mean() > momentary_db[a:(a + b) // 2].mean() + 1.0:
            name = "build"
        else:
            name = "breakdown"
        if not named or named[-1][0] != name:
            named.append((name, a))
    edges = [f for _, f in named] + [n]
    drop, best_step = None, -np.inf
    for i, (name, a) in enumerate(named):
        if name == "drop" and i > 0:
            step = momentary_db[a:edges[i + 1]].mean() - momentary_db[edges[i - 1]:a].mean()
            if step > best_step:
                best_step, drop = step, a
    if drop is None and any(nm == "drop" for nm, _ in named):
        drop = next(f for nm, f in named if nm == "drop")
    return named, drop


def _sharpen(rows: np.ndarray, frame: int) -> int:
    """The frame within a block of ``frame`` where the mean of ``rows`` over the next 0.25 s differs most from the
    0.25 s before: the novelty works on 0.5 s blocks, a section starts on a frame."""
    w, n = PITCH_FRAMES, rows.shape[1]
    span = range(max(w, frame - BLOCK), min(n - w, frame + BLOCK) + 1)
    return max(span, key=lambda t: float(np.linalg.norm(rows[:, t:t + w].mean(axis=1) - rows[:, t - w:t].mean(axis=1))),
               default=frame)


def _top(v: np.ndarray) -> np.ndarray:
    """Scale an onset-strength curve so its strong onsets reach 1: by its 99.5th percentile, but at least a fifth of
    its maximum (a sparse curve's percentile is still its noise floor)."""
    scale = max(float(np.percentile(v, 99.5)), 0.2 * float(v.max()))
    return np.clip(v / scale, 0.0, 1.0) if scale > 0 else np.zeros(len(v))
