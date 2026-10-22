"""Find, decode and line up a song's files (SPEC §16.2): the master, the stems and the MIDI, plus song.toml.

B takes one audio file (its sidecar is <name>.toml next to it). C and D take a folder: master.* (or the only audio
file at the top), stems/ (or the other top-level audio files), and for D midi/ (or top-level .mid files), plus an
optional song.toml. Every audio file is decoded to 48 kHz stereo float; the master sets the length.
"""

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import av
import numpy as np
import soundfile as sf
from scipy import signal

from ..features import HOP, SAMPLE_RATE

AUDIO = {".wav", ".wave", ".aif", ".aiff", ".flac", ".ogg", ".mp3", ".m4a", ".aac", ".mp4", ".mov", ".mkv", ".webm"}
MIDI = {".mid", ".midi"}
NATIVE = {".wav", ".wave", ".aif", ".aiff", ".flac", ".ogg"}       # soundfile reads these sample-exact

# The roles the mappings know (A's track names, plus snare and a whole drum bus) and the words that name them.
ROLES = {
    "kick": ("kick", "kik", "bd", "bassdrum", "kickdrum"),
    "snare": ("snare", "snr", "sd"),
    "clap": ("clap", "clp", "claps"),
    "hats": ("hats", "hat", "hihat", "hihats", "hh", "hhat", "ride", "shaker"),
    "bass": ("bass", "sub", "808", "subbass"),
    "lead": ("lead", "melody", "arp", "pluck", "synth"),
    "pad": ("pad", "pads", "chords", "chord", "keys", "strings"),
    "riser": ("riser", "rise", "sweep", "uplifter"),
    "impact": ("impact", "downlifter", "crash"),
    "drums": ("drums", "drum", "drumrack", "drumbus", "beat", "perc", "percussion"),
}
DRUM_PARTS = ("kick", "snare", "clap", "hats")


@dataclass
class Song:
    """A song's files, decoded and lined up on the frame grid."""
    method: str
    source: Path                                   # the file (B) or folder (C, D) it came from
    title: str
    settings: dict
    master: np.ndarray                             # (samples, 2) float32, exactly frames * 800 samples
    stems: dict[str, np.ndarray] = field(default_factory=dict)
    midi: list[Path] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)     # role or name -> the file it came from
    start_s: float = 0.0
    alignment: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def frames(self) -> int:
        return len(self.master) // HOP


def load(method: str, path: Path, cfg: dict, start: float | None = None, length: float | None = None) -> Song:
    """Find, decode, trim and check a song's inputs for ``method`` (master, stems or midi)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    master_file, stem_files, midi_files, settings, folder = _find(method, path)
    warnings = []
    start = float(start if start is not None else settings.get("start", 0.0))
    length = length if length is not None else settings.get("length")

    master = _cut(decode(master_file), start, length)
    frames = int(round(len(master) / HOP))
    seconds = frames / 60
    limits = cfg.get("song", {})
    if seconds < limits.get("min_len_s", 1):
        raise ValueError(f"{master_file.name}: {seconds:.2f} s is too short")
    if seconds > limits.get("max_len_s", 180):
        raise ValueError(f"{master_file.name}: {seconds:.1f} s is longer than the {limits.get('max_len_s', 180)} s "
                         f"Shorts maximum; trim it with --start/--length (or start/length in song.toml)")
    if seconds > limits.get("warn_len_s", 60):
        warnings.append(f"{seconds:.1f} s: Shorts over {limits.get('warn_len_s', 60)} s with a Content ID claim are blocked")
    master = fit(master, frames * HOP)

    roles, role_warnings = assign_roles([p.stem for p in stem_files], settings.get("roles", {}))
    warnings += role_warnings
    stems, files = {}, {"master": master_file.name}
    for p in stem_files:
        name = roles[p.stem]
        stems[name] = fit(_cut(decode(p), start, length), frames * HOP)
        files[name] = str(p.relative_to(folder))
    song = Song(method, path, _slug(path.stem if path.is_file() else path.name), settings, master, stems,
                midi_files, files, start, warnings=warnings)
    if stems:
        song.alignment = check_alignment(master, stems, limits.get("align_max_lag", 400),
                                         settings.get("check_alignment", True), song.warnings)
    return song


def _find(method: str, path: Path) -> tuple[Path, list[Path], list[Path], dict, Path]:
    """The master, stems, MIDI files and settings for a method's input, by the folder rules of SPEC §16.2."""
    if path.is_file():
        if method != "master":
            raise ValueError(f"method {method!r} takes a folder (master, stems/, midi/), not a file: {path}")
        if path.suffix.lower() not in AUDIO:
            raise ValueError(f"{path.name}: not an audio or video file ({', '.join(sorted(AUDIO))})")
        sidecar = path.with_suffix(".toml")
        return path, [], [], _settings(sidecar if sidecar.exists() else None), path.parent

    top = sorted(p for p in path.iterdir() if p.is_file() and not p.name.startswith("."))
    audio = [p for p in top if p.suffix.lower() in AUDIO]
    named = [p for p in audio if _slug(p.stem) == "master"]
    if not named:                                   # "My Song Master.wav", "Mixdown.wav": one file says so
        named = [p for p in audio if {"master", "mixdown", "mix"} & set(_tokens(p.stem))]
        named = named if len(named) == 1 else []
    if named:
        master = named[0]
    elif len(audio) == 1:
        master = audio[0]
    else:
        listing = ", ".join(p.name for p in audio) or "no audio files"
        raise ValueError(f"{path}: name the master master.wav (or leave it the only audio file at the top); found {listing}")
    stem_dir = path / "stems"
    if stem_dir.is_dir():
        stems = sorted(p for p in stem_dir.iterdir() if p.suffix.lower() in AUDIO and not p.name.startswith("."))
    else:
        stems = [p for p in audio if p != master]
    midi_dir = path / "midi"
    midi = sorted(p for p in (midi_dir.iterdir() if midi_dir.is_dir() else top) if p.suffix.lower() in MIDI)
    tomls = [p for p in top if p.suffix.lower() == ".toml"]
    settings = _settings(path / "song.toml" if (path / "song.toml").exists() else (tomls[0] if len(tomls) == 1 else None))

    if method == "master":
        stems, midi = [], []
    elif method == "stems":
        if not stems:
            raise ValueError(f"{path}: method 'stems' needs stem files in stems/ (or next to the master)")
        midi = []
    elif method == "midi":
        if not midi:
            raise ValueError(f"{path}: method 'midi' needs .mid files in midi/ (or next to the master)")
    return master, stems, midi, settings, path


def _settings(path: Path | None) -> dict:
    if path is None:
        return {}
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def decode(path: Path) -> np.ndarray:
    """Any audio or video file -> (samples, 2) float32 at 48 kHz. WAV, AIFF, FLAC and OGG are read sample-exact
    and resampled only if needed; everything else goes through PyAV (FFmpeg), which also drops a video stream."""
    if path.suffix.lower() in NATIVE:
        x, sr = sf.read(path, dtype="float32", always_2d=True)
        if sr != SAMPLE_RATE:
            g = np.gcd(int(sr), SAMPLE_RATE)
            x = signal.resample_poly(x, SAMPLE_RATE // g, int(sr) // g, axis=0).astype(np.float32)
    else:
        resampler = av.AudioResampler(format="fltp", layout="stereo", rate=SAMPLE_RATE)
        chunks = []
        with av.open(str(path)) as container:
            if not container.streams.audio:
                raise ValueError(f"{path.name}: no audio stream")
            for frame in container.decode(audio=0):
                chunks += [f.to_ndarray() for f in resampler.resample(frame)]
            chunks += [f.to_ndarray() for f in resampler.resample(None)]
        x = np.concatenate(chunks, axis=1).T.astype(np.float32)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    return np.ascontiguousarray(x[:, :2])


def _cut(x: np.ndarray, start: float, length: float | None) -> np.ndarray:
    a = int(round(start * SAMPLE_RATE))
    b = len(x) if length is None else a + int(round(float(length) * SAMPLE_RATE))
    return x[a:b]


def fit(x: np.ndarray, n: int) -> np.ndarray:
    """Exactly ``n`` samples: trimmed, or padded with silence."""
    if len(x) >= n:
        return x[:n]
    return np.concatenate([x, np.zeros((n - len(x), x.shape[1]), x.dtype)])


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "untitled"


def _tokens(name: str) -> list[str]:
    """``"1-Kick Drum"`` -> ["1", "kick", "drum"]; letters and digits stay apart (``kick2`` -> kick, 2)."""
    return re.findall(r"[a-z]+|[0-9]+", name.lower())


def role_of(name: str) -> str | None:
    """The role a file or MIDI track name stands for, or None when no role or more than one fits."""
    joined = re.sub(r"[^a-z0-9]", "", name.lower())
    for role, words in ROLES.items():
        if joined in words:
            return role
    tokens = set(_tokens(name))
    found = {role for role, words in ROLES.items() if tokens & set(words)}
    if len(found) > 1:
        found -= {"drums"}                          # "Kick Drum", "Snare Drum": the specific part wins
    return found.pop() if len(found) == 1 else None


def assign_roles(names: list[str], overrides: dict) -> tuple[dict[str, str], list[str]]:
    """Each name -> the role it plays (song.toml [roles] first, then the name itself) or its own slug. A role goes
    to the first name that claims it; later ones keep their own name, with a warning."""
    by_file = {_slug(str(v)): role for role, v in overrides.items()}
    out, taken, warnings = {}, set(), []
    for name in names:
        role = by_file.get(_slug(name)) or role_of(name)
        if role and role in taken:
            warnings.append(f"{name}: role {role!r} is taken by another file; it stays {_slug(name)!r}")
            role = None
        if role:
            taken.add(role)
        own = _slug(name)
        while not role and own in taken:
            own += "_2"
        out[name] = role or own
        taken.add(out[name])
    unmatched = [n for n in names if out[n] not in ROLES]
    if unmatched:
        warnings.append(f"no role for {', '.join(unmatched)}: usable in a mapping by their own names "
                        f"({', '.join(out[n] for n in unmatched)}); name roles in song.toml [roles]")
    return out, warnings


def check_alignment(master: np.ndarray, stems: dict[str, np.ndarray], max_lag: int, enforce: bool,
                    warnings: list[str]) -> dict:
    """Cross-correlate the sum of the stems with the master (first 30 s, at 12 kHz). A lag beyond ``max_lag``
    samples means the exports started at different positions: stop, unless song.toml says check_alignment = false."""
    span = min(len(master), 30 * SAMPLE_RATE)
    a = signal.decimate(master[:span].mean(axis=1), 4)
    b = signal.decimate(sum(s[:span] for s in stems.values()).mean(axis=1), 4)
    if np.std(a) < 1e-6 or np.std(b) < 1e-6:
        warnings.append("alignment not checked: the master or the stems are silent")
        return {"checked": False}
    corr = signal.correlate(a - a.mean(), b - b.mean(), mode="full", method="fft")
    lags = np.arange(-len(b) + 1, len(a))
    window = np.abs(lags) <= SAMPLE_RATE // 4                       # ±1 s at 12 kHz
    best = int(np.argmax(np.abs(corr[window])))
    lag = int(-lags[window][best] * 4)                               # samples at 48 kHz; > 0: stems are late
    strength = float(np.abs(corr[window][best]) / (np.linalg.norm(a - a.mean()) * np.linalg.norm(b - b.mean())))
    result = {"checked": True, "lag_samples": lag, "lag_ms": round(lag / SAMPLE_RATE * 1000, 2),
              "correlation": round(strength, 3)}
    if strength < 0.3:
        warnings.append(f"alignment not verified: the stems resemble the master only weakly (correlation {strength:.2f})")
        result["checked"] = False
    elif abs(lag) > max_lag:
        msg = (f"the stems are {abs(result['lag_ms'])} ms {'behind' if lag > 0 else 'ahead of'} the master: export every "
               f"file from the same start position (or set check_alignment = false in song.toml)")
        if enforce:
            raise ValueError(msg)
        warnings.append(msg)
    return result
