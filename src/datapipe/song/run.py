"""Methods B, C and D up to the run folder (SPEC §16.1, §16.2): work/<method>/<yyyymmdd-HHMMSS>_<song>/ holds
mix.wav (the master, 48 kHz, exactly 800 samples per frame), controls.json, report.png and run.json; the newest is
mirrored into work/<method>/latest/.
"""

import hashlib
import json
import platform
import subprocess
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from .. import __version__
from ..config import ROOT, load_config
from ..features import SAMPLE_RATE
from ..gen.run import _mirror
from . import controls as song_controls
from . import ingest, midi, report

SONG_METHODS = ("master", "stems", "midi")


def analyze(method: str, path: Path, out: Path | None = None, start: float | None = None,
            length: float | None = None, bpm: float | None = None, loop: bool | None = None,
            progress=print, latest: bool = True) -> Path:
    """Load, analyse and write one song's run folder; returns it."""
    if method not in SONG_METHODS:
        raise ValueError(f"unknown song method {method!r}; one of {', '.join(SONG_METHODS)}")
    cfg = load_config()
    times = {}
    t = time.perf_counter()
    progress(f"{method}: {path}")
    song = ingest.load(method, Path(path), cfg, start, length)
    if loop is not None:
        song.settings["loop"] = loop
    notes = midi.read(song.midi, song.settings) if method == "midi" else None
    times["load"] = time.perf_counter() - t

    t = time.perf_counter()
    controls = song_controls.build(song, notes, bpm, progress)
    times["analyze"] = time.perf_counter() - t

    t = time.perf_counter()
    root = Path(out) if out else ROOT / cfg["methods"][method]["work"]
    run_dir = root / f"{datetime.now():%Y%m%d-%H%M%S}_{song.title}"
    run_dir.mkdir(parents=True)
    sf.write(run_dir / "mix.wav", song.master, SAMPLE_RATE, subtype="FLOAT")
    (run_dir / "controls.json").write_text(json.dumps(controls, separators=(",", ":")) + "\n", encoding="utf-8")
    report.write(controls, run_dir / "report.png")
    times["write"] = time.perf_counter() - t
    record = {
        "run": run_dir.name, "method": method, "created": datetime.now().isoformat(timespec="seconds"),
        "source": str(Path(path).resolve()), "inputs": _inputs(song), "settings": song.settings,
        "start_s": song.start_s, "frames": song.frames, "seconds": round(song.frames / 60, 3),
        "bpm": controls["bpm"], "tempo_source": controls["meta"]["tempo_source"],
        "sections": controls["sections"], "sections_from": controls["meta"]["sections_from"],
        "drop_frame": controls["meta"]["drop_frame"], "hits": controls["meta"]["detection"],
        "files": song.files, "alignment": song.alignment, "warnings": song.warnings,
        "versions": _versions(), "timings_s": {k: round(v, 2) for k, v in times.items()},
    }
    (run_dir / "run.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    if latest:
        problem = _mirror(run_dir, root / "latest")
        if problem:
            song.warnings.append(problem)
    return run_dir


def _inputs(song: ingest.Song) -> dict:
    """Every input file with its size and sha256, so a run can be traced back to the exact export."""
    source = song.source if song.source.is_dir() else song.source.parent
    files = [source / f for f in song.files.values()] + list(song.midi)
    out = {}
    for p in files:
        p = Path(p)
        if p.is_file():
            out[str(p.relative_to(source))] = {"bytes": p.stat().st_size,
                                                "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    return out


def _versions() -> dict:
    import librosa

    try:
        commit = subprocess.run(["git", "describe", "--always", "--dirty"], cwd=ROOT, capture_output=True,
                                text=True, timeout=10).stdout.strip()
    except OSError:
        commit = ""
    return {"datapipe": __version__, "git": commit, "python": platform.python_version(), "numpy": np.__version__,
            "librosa": librosa.__version__, "os": f"{platform.system()} {platform.release()} {platform.machine()}"}
