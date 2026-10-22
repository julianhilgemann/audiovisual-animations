"""`datapipe gen`: a preset and a seed (or a MIDI file) become a run folder (dawdreamer/specs/handoff.md, Run folder).

work/gen/<yyyymmdd>_<preset>_s<seed>/ holds score.json, score.mid, frames.csv, stems/*.wav, mix.wav, loop_x3.wav,
preset.toml and manifest.json. The newest run is mirrored into work/gen/latest/, one fixed path for Blender to
read.
"""

import json
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.io import wavfile

from .. import __version__
from ..config import ROOT, load_config
from . import engine
from .compose import compose, ingest_midi, load_preset, resolve_sounds
from .master import lufs, master
from .score import FPS, FRAMES, SAMPLE_RATE, SAMPLES, save_frames


def generate(preset_name: str, seed: int = 1, midi: Path | None = None, use_plugins: bool = True,
             out: Path | None = None, latest: bool = True) -> tuple[Path, dict]:
    """Compose (or ingest), render, master and write one run; returns its folder and manifest."""
    cfg = load_config()
    out_root = Path(out) if out else ROOT / cfg.get("gen", {}).get("out", "work/gen")
    times = {}

    t = time.perf_counter()
    preset = load_preset(preset_name)
    score = ingest_midi(preset, Path(midi)) if midi else compose(preset, seed)
    sounds, picks = resolve_sounds(preset, seed)
    score.meta["sounds"] = picks
    errors = score.validate()
    if errors:
        raise ValueError("invalid score:\n  " + "\n  ".join(errors))
    times["compose"] = time.perf_counter() - t

    t = time.perf_counter()
    rendered = engine.render(score, sounds, use_plugins)
    times["render"] = time.perf_counter() - t

    t = time.perf_counter()
    settings = preset.get("master", {})
    mix, loudness = master(rendered.mix, SAMPLE_RATE, settings.get("lufs", -14.0), settings.get("true_peak_db", -1.0))
    gain = 10 ** ((rendered.stem_gain_db + loudness["gain_db"]) / 20)
    reference = lufs(sum(rendered.stems.values()), SAMPLE_RATE)
    balance = {name: _relative(lufs(stem, SAMPLE_RATE), reference) for name, stem in rendered.stems.items()}
    times["master"] = time.perf_counter() - t

    t = time.perf_counter()
    run_dir = out_root / f"{datetime.now():%Y%m%d}_{preset['name']}_{Path(midi).stem if midi else f's{seed}'}"
    if (run_dir / "stems").exists():
        shutil.rmtree(run_dir / "stems")
    (run_dir / "stems").mkdir(parents=True)
    score.save(run_dir / "score.json")
    score.save_midi(run_dir / "score.mid")
    save_frames(score, run_dir / "frames.csv")
    shutil.copyfile(preset["_path"], run_dir / "preset.toml")
    sf.write(run_dir / "mix.wav", mix.T, SAMPLE_RATE, subtype="PCM_24")
    sf.write(run_dir / "loop_x3.wav", np.tile(mix, 3).T, SAMPLE_RATE, subtype="PCM_24")
    for name, stem in rendered.stems.items():   # float, since stems are not limited; scipy adds no timestamp chunk
        wavfile.write(run_dir / "stems" / f"{name}.wav", SAMPLE_RATE, (stem * gain).T.astype(np.float32))
    times["write"] = time.perf_counter() - t

    manifest = {
        "run": run_dir.name,
        "created": datetime.now().isoformat(timespec="seconds"),
        "preset": preset["name"],
        "seed": seed,
        "source": f"midi:{midi}" if midi else "compose",
        "grid": {"bpm": score.bpm, "bars": score.bars, "fps": FPS, "frames": FRAMES,
                 "sample_rate": SAMPLE_RATE, "samples": SAMPLES},
        "music": score.meta,
        "sources": rendered.sources,
        "loudness": {**loudness, "master_in_gain_db": round(rendered.stem_gain_db, 2)},
        "seam": rendered.seam,
        "balance_lu": balance,
        "warnings": rendered.warnings,
        "versions": _versions(),
        "timings_s": {k: round(v, 3) for k, v in times.items()},
        "files": sorted(str(p.relative_to(run_dir)).replace("\\", "/") for p in run_dir.rglob("*") if p.is_file()),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    if latest:
        problem = _mirror(run_dir, out_root / "latest")
        if problem:
            manifest["warnings"].append(problem)
    return run_dir, manifest


def _relative(level: float, reference: float) -> float | None:
    """A stem's loudness relative to the sum of all stems, in LU; None for a silent stem."""
    return round(level - reference, 1) if np.isfinite(level) else None


def _mirror(run_dir: Path, latest: Path) -> str | None:
    """Copy the run into latest/ file by file, so a file another program holds open fails alone."""
    failed = []
    wanted = {p.relative_to(run_dir) for p in run_dir.rglob("*") if p.is_file()}
    if latest.exists():
        for old in [p for p in latest.rglob("*") if p.is_file() and p.relative_to(latest) not in wanted]:
            old.unlink(missing_ok=True)
    for rel in sorted(wanted):
        target = latest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(run_dir / rel, target)
        except PermissionError:
            failed.append(str(rel))
    (latest / "RUN.txt").write_text(run_dir.name + "\n", encoding="utf-8")
    if failed:
        return f"latest/ is stale for {', '.join(failed)}: another program (a player, Blender) has them open"
    return None


def _versions() -> dict:
    import dawdreamer

    try:
        commit = subprocess.run(["git", "describe", "--always", "--dirty"], cwd=ROOT, capture_output=True,
                                text=True, timeout=10).stdout.strip()
    except OSError:
        commit = ""
    return {"datapipe": __version__, "git": commit, "python": platform.python_version(),
            "dawdreamer": getattr(dawdreamer, "__version__", "?"), "numpy": np.__version__,
            "os": f"{platform.system()} {platform.release()} {platform.machine()}"}


def play(path: Path) -> None:
    """Play a WAV and wait for it: afplay on macOS, winsound on Windows, aplay elsewhere."""
    if sys.platform == "darwin":
        subprocess.run(["afplay", str(path)], check=False)
    elif sys.platform == "win32":
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME)
    else:
        subprocess.run(["aplay", "-q", str(path)], check=False)
