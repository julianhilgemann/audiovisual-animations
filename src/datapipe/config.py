"""Load config/pipeline.toml and resolve its paths against the repo root."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: Path | None = None) -> dict:
    with open(path or ROOT / "config" / "pipeline.toml", "rb") as fh:
        return tomllib.load(fh)


def resolve_path(cfg: dict, key: str) -> Path:
    """Return ``cfg["paths"][key]`` as an absolute path (relative paths are repo-relative)."""
    p = Path(cfg["paths"][key])
    return p if p.is_absolute() else ROOT / p
