"""Load config/pipeline.toml (plus the gitignored config/machine.toml) and resolve its paths against the repo root."""

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OS_KEY = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def load_config(path: Path | None = None) -> dict:
    with open(path or ROOT / "config" / "pipeline.toml", "rb") as fh:
        cfg = tomllib.load(fh)
    machine = ROOT / "config" / "machine.toml"
    if path is None and machine.exists():
        with open(machine, "rb") as fh:
            _merge(cfg, tomllib.load(fh))
    return cfg


def _merge(base: dict, override: dict) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value


def resolve_path(cfg: dict, key: str) -> Path:
    """Return this OS's ``[paths.<os>]`` entry for ``key``, else ``[paths]``; relative paths are repo-relative."""
    paths = cfg["paths"]
    p = Path(paths.get(OS_KEY, {}).get(key) or paths[key])
    return p if p.is_absolute() else ROOT / p
