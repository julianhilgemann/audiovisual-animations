"""`datapipe doctor`: verify every tool the pipeline depends on, with a pass/fail line each."""

import importlib
import re
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import ROOT, resolve_path

REQUIRED_LIBS = ("numpy", "scipy", "librosa", "soundfile", "av", "matplotlib")


def _line(ok: bool | None, name: str, detail: str) -> None:
    mark = {True: "ok  ", False: "FAIL", None: "info"}[ok]
    print(f"[{mark}] {name:<16} {detail}")


def _check_libs() -> bool:
    ok = True
    for name in REQUIRED_LIBS:
        try:
            mod = importlib.import_module(name)
            _line(True, name, getattr(mod, "__version__", "?"))
        except Exception as ex:  # noqa: BLE001 - report any import failure
            _line(False, name, f"import failed: {ex}")
            ok = False
    return ok


def _check_pyav_roundtrip() -> bool:
    """Write a short WAV with soundfile, decode it with PyAV: proves the bundled FFmpeg works."""
    try:
        import av
        import numpy as np
        import soundfile as sf

        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "tone.wav"
            t = np.arange(4800) / 48000
            sf.write(wav, np.sin(2 * np.pi * 440 * t).astype(np.float32), 48000)
            with av.open(str(wav)) as container:
                samples = sum(f.samples for f in container.decode(audio=0))
        libs = ", ".join(f"{k} {'.'.join(map(str, v))}" for k, v in sorted(av.library_versions.items())
                         if k in ("libavcodec", "libavformat"))
        ok = samples == 4800
        _line(ok, "pyav decode", f"{samples}/4800 samples decoded ({libs})")
        return ok
    except Exception as ex:  # noqa: BLE001
        _line(False, "pyav decode", str(ex))
        return False


def _check_blender(cfg: dict) -> bool:
    exe = resolve_path(cfg, "blender")
    if not exe.exists():
        _line(False, "blender", f"not found at {exe}")
        return False
    out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=120).stdout
    m = re.search(r"Blender (\d+\.\d+\.\d+[^\r\n]*)", out)
    version = m.group(1).strip() if m else "unknown"
    ok = version.startswith("5.2")
    _line(ok, "blender", f"{version} at {exe}" + ("" if ok else " (scripts target 5.2)"))
    return ok


def _check_paths(cfg: dict) -> bool:
    ok = True
    for key in ("template", "inbox", "work", "cache", "output", "archive"):
        p = resolve_path(cfg, key)
        exists = p.exists()
        _line(exists, key, str(p.relative_to(ROOT)))
        ok &= exists
    td = resolve_path(cfg, "touchdesigner")
    _line(None, "touchdesigner", f"{'found' if td.exists() else 'not found'} at {td} (needed for P6 only)")
    return ok


def _check_bridge() -> None:
    try:
        with socket.create_connection(("localhost", 9876), timeout=0.5):
            _line(None, "blender bridge", "listening on localhost:9876")
    except OSError:
        _line(None, "blender bridge", "not running (only needed for live tweaks)")


def _check_gpu() -> None:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=15).stdout.strip()
        _line(None, "gpu", out or "nvidia-smi returned nothing")
    except (OSError, subprocess.TimeoutExpired):
        _line(None, "gpu", "nvidia-smi not available")


def run_doctor(cfg: dict) -> int:
    py_ok = sys.version_info[:2] == (3, 12)
    _line(py_ok, "python", f"{sys.version.split()[0]} at {sys.executable}")
    hop = cfg["grid"]["sample_rate"] / cfg["grid"]["fps"]
    hop_ok = hop.is_integer()
    _line(hop_ok, "frame grid", f"{cfg['grid']['fps']} fps x {cfg['grid']['sample_rate']} Hz -> hop {hop:g} samples")
    results = [py_ok, hop_ok, _check_libs(), _check_pyav_roundtrip(), _check_blender(cfg), _check_paths(cfg)]
    _check_bridge()
    _check_gpu()
    ok = all(results)
    print("\nall required checks passed" if ok else "\nsome required checks FAILED")
    return 0 if ok else 1
