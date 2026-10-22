"""VST3 plugins for the engine: the manifest, fetching per OS, locating, parameters by name, probing and editing.

`dawdreamer/plugins.toml` lists the plugins. `fetch` downloads one archive per plugin, checks its sha256 and copies
the plugin's .vst3 bundle into dawdreamer/plugins/<os>/<key>/; nothing is installed outside the repo. On macOS a
.dmg is mounted read-only with hdiutil and a .pkg inside it is unpacked with `pkgutil --expand-full`, never installed.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

from ..config import OS_KEY, ROOT

MANIFEST = ROOT / "dawdreamer" / "plugins.toml"
PLUGIN_DIR = ROOT / "dawdreamer" / "plugins"
SYSTEM_VST3 = {
    "macos": [Path("/Library/Audio/Plug-Ins/VST3"), Path.home() / "Library/Audio/Plug-Ins/VST3"],
    "windows": [Path(os.environ.get("COMMONPROGRAMFILES", r"C:\Program Files\Common Files")) / "VST3",
                Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local")) / "Programs/Common/VST3"],
    "linux": [Path.home() / ".vst3", Path("/usr/lib/vst3"), Path("/usr/local/lib/vst3")],
}


def load_manifest() -> dict:
    with open(MANIFEST, "rb") as fh:
        return tomllib.load(fh)


def locate(name: str) -> Path | None:
    """The .vst3 bundle for a manifest key on this OS, or None when it is not fetched or installed."""
    entry = load_manifest().get(name)
    if entry is None:
        raise KeyError(f"no plugin {name!r} in {MANIFEST.relative_to(ROOT)}")
    if "system" in entry:
        return next((d / entry["system"] for d in SYSTEM_VST3[OS_KEY] if (d / entry["system"]).exists()), None)
    target = entry.get(OS_KEY)
    bundle = PLUGIN_DIR / OS_KEY / name / target["vst3"] if target else None
    return bundle if bundle and bundle.exists() else None


def fetch(names: list[str] | None = None, force: bool = False) -> list[str]:
    """Download and unpack plugins for this OS; returns one status line per plugin."""
    manifest = load_manifest()
    lines = []
    for name in names or list(manifest):
        entry = manifest[name]
        if "system" in entry:
            where = locate(name)
            lines.append(f"{name:16} {'installed at ' + str(where) if where else 'not installed; get it from ' + entry['home']}")
            continue
        target = entry.get(OS_KEY)
        if target is None:
            lines.append(f"{name:16} no {OS_KEY} build listed")
            continue
        dest = PLUGIN_DIR / OS_KEY / name
        if locate(name) and not force:
            lines.append(f"{name:16} already fetched ({entry['version']})")
            continue
        archive = _download(target["url"], target["sha256"])
        with tempfile.TemporaryDirectory(prefix="datapipe_plugin_") as tmp:
            found = _unpack(archive, Path(tmp), target["vst3"])
            if dest.exists():
                shutil.rmtree(dest)
            dest.mkdir(parents=True)
            shutil.copytree(found, dest / target["vst3"], symlinks=True)
        lines.append(f"{name:16} fetched {entry['version']} -> {(dest / target['vst3']).relative_to(ROOT)}")
    shutil.rmtree(PLUGIN_DIR / "_downloads", ignore_errors=True)    # archives shared by entries stay for one run
    return lines


def _download(url: str, sha256: str) -> Path:
    cache = PLUGIN_DIR / "_downloads"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / url.rsplit("/", 1)[-1]
    if not path.exists() or _sha256(path) != sha256:
        print(f"  downloading {url}", file=sys.stderr)
        part = path.with_suffix(path.suffix + ".part")
        with urllib.request.urlopen(url, timeout=60) as response, open(part, "wb") as fh:
            shutil.copyfileobj(response, fh)
        part.replace(path)
    digest = _sha256(path)
    if digest != sha256:
        path.unlink()
        raise RuntimeError(f"sha256 mismatch for {url}: got {digest}, manifest says {sha256}")
    return path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _unpack(archive: Path, tmp: Path, bundle: str) -> Path:
    """Unpack ``archive`` under ``tmp`` and return the directory of the named .vst3 bundle inside it."""
    out = tmp / "x"
    if archive.suffix == ".zip":
        if sys.platform == "darwin":       # ditto keeps the symlinks and permissions a signed bundle needs
            subprocess.run(["ditto", "-x", "-k", str(archive), str(out)], check=True)
        else:
            with zipfile.ZipFile(archive) as z:
                z.extractall(out)
    elif archive.suffix == ".dmg":
        mount = tmp / "mnt"
        mount.mkdir()
        out.mkdir()
        subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", str(mount),
                        str(archive)], check=True, capture_output=True)
        try:
            found = _find(mount, bundle)
            if found:
                shutil.copytree(found, out / bundle, symlinks=True)
            else:
                for i, pkg in enumerate(mount.glob("*.pkg")):
                    subprocess.run(["pkgutil", "--expand-full", str(pkg), str(out / f"pkg{i}")], check=True)
        finally:
            subprocess.run(["hdiutil", "detach", str(mount), "-quiet"], check=False)
    else:
        raise RuntimeError(f"cannot unpack {archive.name}")
    found = _find(out, bundle)
    if found is None:
        raise RuntimeError(f"{bundle} not found in {archive.name}")
    return found


def _find(root: Path, bundle: str) -> Path | None:
    return next((p for p in root.rglob(bundle) if p.is_dir()), None)


def load_plugin(engine, proc_name: str, path: Path):
    """``make_plugin_processor`` with the bundle; on Windows, retry with the DLL inside it."""
    try:
        return engine.make_plugin_processor(proc_name, str(path))
    except Exception:
        inner = path / "Contents" / "x86_64-win" / path.name
        if OS_KEY == "windows" and inner.exists():
            return engine.make_plugin_processor(proc_name, str(inner))
        raise


# ---- parameters ---------------------------------------------------------------------------------------------------

def parameter_index(proc) -> dict[str, int]:
    return {d["name"]: d["index"] for d in proc.get_parameters_description() if not d["name"].startswith("MIDI CC ")}


def apply_params(proc, params: dict) -> None:
    """Set plugin parameters by name. A number is the raw 0-1 value; a string is the value as the plugin displays
    it ("TUB BELLS", "Saw", "2.5"): an exact text match wins, else the nearest number."""
    index = parameter_index(proc)
    lower = {k.lower(): v for k, v in index.items()}
    for name, value in params.items():
        i = index.get(name, lower.get(name.lower()))
        if i is None:
            raise KeyError(f"{proc.get_name()}: no parameter {name!r}; run `datapipe plugins probe` for the list")
        proc.set_parameter(i, float(value) if not isinstance(value, str) else _value_for_text(proc, i, value))


def _value_for_text(proc, index: int, text: str) -> float:
    ranges = proc.get_parameter_range(index, 2000, False)
    target = text.strip().lower()
    for (lo, hi), label in ranges.items():
        if str(label).strip().lower() == target:
            return (lo + hi) / 2
    number = _number(target)
    numeric = [((lo + hi) / 2, _number(str(label))) for (lo, hi), label in ranges.items()]
    numeric = [(x, v) for x, v in numeric if v is not None]
    if number is None or not numeric:
        labels = ", ".join(sorted({str(v).strip() for v in ranges.values()})[:40])
        raise ValueError(f"{proc.get_name()}: {proc.get_parameter_name(index)!r} has no value {text!r}; it shows: {labels}")
    return min(numeric, key=lambda xv: abs(xv[1] - number))[0]


def _number(text: str) -> float | None:
    head = text.strip().split(" ")[0].rstrip("%")
    try:
        return float(head)
    except ValueError:
        return None


# ---- probe and edit -----------------------------------------------------------------------------------------------

def probe(name: str, sample_rate: int = 48000) -> list[str]:
    """Load a plugin headless, list its parameters (and programs) and render a test: proves it works here."""
    import dawdreamer as daw
    import numpy as np

    path = locate(name)
    if path is None:
        return [f"{name}: not available on this machine; run `datapipe plugins fetch {name}`"]
    engine = daw.RenderEngine(sample_rate, 512)
    proc = load_plugin(engine, name, path)
    index = parameter_index(proc)
    lines = [f"{name}: {path}", f"  inputs {proc.get_num_input_channels()}, outputs {proc.get_num_output_channels()}, "
             f"latency {proc.get_latency_samples()} samples, {len(index)} parameters"]
    for pname, i in index.items():
        lines.append(f"  [{i:4}] {pname} = {proc.get_parameter_text(i).strip()}")
    if "Program" in index:
        programs = [str(v).strip() for _, v in sorted(proc.get_parameter_range(index["Program"], 2000, False).items())]
        lines.append(f"  programs ({len(programs)}): {', '.join(programs)}")
    graph = [(proc, [])]
    if load_manifest()[name].get("kind") == "effect":
        src = engine.make_faust_processor("probe_src")
        src.set_dsp_string('import("stdfaust.lib"); process = no.multinoise(2) : *(ba.time < 2400), *(ba.time < 2400);')
        src.compile()
        graph = [(src, []), (proc, ["probe_src"])]
    else:
        for k, pitch in enumerate((60, 64, 67, 72)):
            proc.add_midi_note(pitch, 100, 0.25 * k, 0.2)
    engine.load_graph(graph)
    engine.render(2.0)
    audio = engine.get_audio()
    peak = float(np.abs(audio).max())
    ok = peak > 1e-4 and np.isfinite(audio).all()
    lines.append(f"  test render: peak {20 * np.log10(peak + 1e-12):.1f} dBFS -> {'OK' if ok else 'SILENT OR BROKEN'}")
    return lines


def edit(name: str, state: Path, params: dict | None = None) -> str:
    """Open the plugin's own window; when it closes, save its full state to ``state`` for a preset to load."""
    import dawdreamer as daw

    path = locate(name)
    if path is None:
        raise FileNotFoundError(f"{name} is not available; run `datapipe plugins fetch {name}`")
    engine = daw.RenderEngine(48000, 512)
    proc = load_plugin(engine, name, path)
    if state.exists():
        proc.load_state(str(state))
    apply_params(proc, params or {})
    proc.open_editor()
    state.parent.mkdir(parents=True, exist_ok=True)
    proc.save_state(str(state))
    return f"saved {name} state to {state}"
