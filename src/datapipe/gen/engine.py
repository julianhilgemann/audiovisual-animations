"""S2 audio render: a Score and its preset's mix become stems and a mix in one DawDreamer graph (dawdreamer/specs/engine.md).

Per track: instrument -> inserts -> strip (fader and pan, recorded as the track's stem). Strips feed the send buses
(each recorded as a stem too) and the master sum. The sum is gained to MASTER_IN_LUFS before the master chain, which
runs as a second, small graph, so the master compressor always sees the same level whatever the track faders add up
to. Every graph renders the loop twice and keeps the second pass, so tails from the end wrap into the head.
"""

import ctypes
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field

import numpy as np

from ..config import ROOT
from . import plugins
from .master import lufs, seam
from .score import LOOP_SECONDS, SAMPLE_RATE, SAMPLES, Score

FAUST_DIR = ROOT / "dawdreamer" / "faust"
STATE_DIR = ROOT / "dawdreamer" / "states"
BLOCK = 256
PASSES = 2
MASTER_IN_LUFS = -18.0
_NOISE = ("Steal ", "DPF warning", "objc[")      # voice handover notes, Dragonfly's two-copies notes
_DECLARE = re.compile(r'^\s*declare\s+(\w+)\s+"([^"]*)"\s*;', re.M)
_STRIP = """import("stdfaust.lib");
g = hslider("gain_db", 0, -70, 12, 0.01) : ba.db2linear;
th = (hslider("pan", 0, -1, 1, 0.001) + 1) * ma.PI / 4;
process = {inputs} *(g * cos(th) * sqrt(2)), *(g * sin(th) * sqrt(2));
"""


@dataclass
class Render:
    mix: np.ndarray                                       # (2, SAMPLES): master chain output, before loudness
    stems: dict[str, np.ndarray]                          # track or bus -> (2, SAMPLES), after its fader
    stem_gain_db: float                                   # the gain the sum got on its way into the master chain
    seam: dict                                            # master.seam() of the master chain output
    sources: dict[str, str] = field(default_factory=dict)  # slot -> what played it ("plugin:ripplerx 1.5.19")
    warnings: list[str] = field(default_factory=list)


def render(score: Score, preset: dict, use_plugins: bool = True) -> Render:
    with _engine_output() as printed:
        result = _render(score, preset, use_plugins)
    result.warnings += [f"engine: {line}" for line in printed if line.strip() and not line.startswith(_NOISE)]
    return result


def _render(score: Score, preset: dict, use_plugins: bool) -> Render:
    import dawdreamer as daw

    engine = daw.RenderEngine(SAMPLE_RATE, BLOCK)
    engine.set_bpm(float(score.bpm))
    b = _Builder(engine, score, use_plugins)
    buses = preset.get("bus", {})
    if set(buses) & set(preset["track"]):
        raise ValueError(f"bus and track names share stem names: {sorted(set(buses) & set(preset['track']))}")

    strips = []
    for name, spec in preset["track"].items():
        last = b.slot(name, spec["instrument"], notes=score.tracks.get(name, []))
        for i, fx in enumerate(spec.get("inserts", [])):
            last = b.slot(f"{name}:fx{i}", fx, inputs=[last])
        gain_db = spec.get("gain_db", 0.0) + b.chosen[name].get("trim_db", 0.0)
        strips.append((b.strip(name, last, gain_db, spec.get("pan", 0.0)), spec.get("sends", {})))
        b.warnings += [f"{name}: send to unknown bus {bus!r}" for bus in spec.get("sends", {}) if bus not in buses]

    returns = []
    for bus, spec in buses.items():
        feeds = [(strip, sends[bus]) for strip, sends in strips if bus in sends]
        if not feeds:
            b.warnings.append(f"bus {bus}: no track sends to it, skipped")
            continue
        last = b.add(f"{bus}:send", [s for s, _ in feeds], [10 ** (db / 20) for _, db in feeds])
        for i, fx in enumerate(spec.get("fx", [])):
            last = b.slot(f"{bus}:fx{i}", fx, inputs=[last])
        returns.append(b.strip(bus, last, spec.get("gain_db", 0.0), 0.0))

    sources = [s for s, _ in strips] + returns
    b.add("master:sum", sources, [1.0] * len(sources))
    engine.load_graph(b.graph)
    engine.render(PASSES * LOOP_SECONDS)
    keep = slice((PASSES - 1) * SAMPLES, PASSES * SAMPLES)
    total = engine.get_audio()[:2].astype(np.float64)
    stems = {name: proc.get_audio()[:2, keep].astype(np.float64) for name, proc in b.recorded.items()}

    level = lufs(total[:, keep], SAMPLE_RATE)
    in_gain_db = MASTER_IN_LUFS - level if np.isfinite(level) else 0.0      # silence: master() reports it
    master = daw.RenderEngine(SAMPLE_RATE, BLOCK)
    m = _Builder(master, score, use_plugins)
    last = master.make_playback_processor("master:in", (total * 10 ** (in_gain_db / 20)).astype(np.float32))
    m.graph.append((last, []))
    for i, fx in enumerate(preset.get("master", {}).get("fx", [])):
        last = m.slot(f"master:fx{i}", fx, inputs=[last])
    master.load_graph(m.graph)
    master.render(PASSES * LOOP_SECONDS)
    out = master.get_audio()[:2].astype(np.float64)
    return Render(out[:, keep], stems, in_gain_db, seam(out, SAMPLES), {**b.sources, **m.sources},
                  b.warnings + m.warnings)


class _Builder:
    """Creates processors in graph order and remembers what each slot ended up using."""

    def __init__(self, engine, score: Score, use_plugins: bool):
        self.engine, self.score, self.use_plugins = engine, score, use_plugins
        self.graph, self.recorded, self.sources, self.chosen, self.warnings = [], {}, {}, {}, []
        self.manifest = plugins.load_manifest()
        self._curves = {}

    def slot(self, name: str, spec: dict, notes: list | None = None, inputs: list | None = None):
        """One processor from a slot spec; the first of the spec and its ``fallback`` chain that is available."""
        candidate = spec
        while candidate:
            if "plugin" in candidate:
                proc, instrument, label = self._plugin(name, candidate)
            elif "faust" in candidate:
                proc, instrument, label = self._faust(name, candidate)
            else:
                raise ValueError(f"{name}: a slot needs `faust` or `plugin`: {candidate}")
            if proc is not None:
                break
            candidate = candidate.get("fallback")
        else:
            raise RuntimeError(f"{name}: none of its plugins are available and it has no faust fallback")
        if notes:
            if not instrument:
                self.warnings.append(f"{name}: {label} is not an instrument, its {len(notes)} notes are ignored")
            for p in range(PASSES):
                for n in notes:
                    proc.add_midi_note(n.pitch, n.vel, self.score.seconds(n.beat) + p * LOOP_SECONDS,
                                       self.score.seconds(n.dur))
        for param, a in candidate.get("automate", {}).items():
            self._automate(proc, name, param, a, "faust" in candidate)
        self.graph.append((proc, [p.get_name() for p in inputs or []]))
        self.sources[name] = label
        self.chosen[name] = candidate
        return proc

    def _plugin(self, name: str, spec: dict):
        key = spec["plugin"]
        path = plugins.locate(key) if self.use_plugins else None
        if path is None:
            if self.use_plugins:
                self.warnings.append(f"{name}: plugin {key} is not fetched here (`datapipe plugins fetch {key}`), "
                                     "using its fallback")
            return None, False, ""
        proc = plugins.load_plugin(self.engine, name, path)
        if spec.get("state"):
            proc.load_state(str(STATE_DIR / spec["state"]))
        plugins.apply_params(proc, spec.get("params", {}))
        if proc.get_latency_samples():
            self.warnings.append(f"{name}: {key} reports {proc.get_latency_samples()} samples of latency (not compensated)")
        entry = self.manifest[key]
        return proc, entry.get("kind") == "instrument", f"plugin:{key} {entry.get('version', '')}".strip()

    def _faust(self, name: str, spec: dict):
        path = FAUST_DIR / f"{spec['faust']}.dsp"
        source = path.read_text(encoding="utf-8")
        meta = dict(_DECLARE.findall(source))
        proc = self.engine.make_faust_processor(name)
        proc.set_dsp_string(source)
        instrument = "voices" in meta
        if instrument:
            proc.num_voices = int(meta["voices"])
            proc.release_length = float(meta.get("release", 1.0))
        try:
            proc.compile()
        except RuntimeError as ex:
            raise RuntimeError(f"{name}: {path.name} does not compile: {ex}") from None
        names = _faust_params(proc)
        params = dict(spec.get("params", {}))
        if "bpm" in names:
            params.setdefault("bpm", self.score.bpm)
        for key, value in params.items():
            if key not in names:
                raise KeyError(f"{name}: {path.name} has no parameter {key!r}; it has {sorted(names)}")
            proc.set_parameter(names[key], float(value))
        return proc, instrument, f"faust:{spec['faust']}"

    def _automate(self, proc, name: str, param: str, a: dict, is_faust: bool) -> None:
        """Drive a parameter from a score curve: ``{curve, from=0, to=1, scale="lin"|"log"}``, at audio rate."""
        curve = self._curve(a["curve"])
        lo, hi = float(a.get("from", 0.0)), float(a.get("to", 1.0))
        values = lo * (hi / lo) ** curve if a.get("scale") == "log" else lo + (hi - lo) * curve
        if is_faust:
            names = _faust_params(proc)
            if param not in names:
                raise KeyError(f"{name}: no parameter {param!r} to automate; it has {sorted(names)}")
            proc.set_automation(names[param], values.astype(np.float32))
        else:
            proc.set_automation(plugins.parameter_index(proc)[param], values.astype(np.float32))

    def _curve(self, curve: str) -> np.ndarray:
        if curve not in self._curves:
            if curve not in self.score.automation:
                raise KeyError(f"no automation curve {curve!r} in the score; it has {sorted(self.score.automation)}")
            points = self.score.automation[curve]
            t = np.arange(PASSES * SAMPLES) / SAMPLE_RATE
            beats = (t % LOOP_SECONDS) * self.score.bpm / 60
            self._curves[curve] = np.interp(beats, [b for b, _ in points], [v for _, v in points])
        return self._curves[curve]

    def strip(self, name: str, source, gain_db: float, pan: float):
        """Fader and equal-power pan; its output is recorded as ``name``'s stem."""
        proc = self.engine.make_faust_processor(f"{name}:strip")
        proc.set_dsp_string(_STRIP.format(inputs="_ <: " if source.get_num_output_channels() == 1 else ""))
        proc.compile()
        names = _faust_params(proc)
        proc.set_parameter(names["gain_db"], float(gain_db))
        proc.set_parameter(names["pan"], float(pan))
        proc.record = True
        self.graph.append((proc, [source.get_name()]))
        self.recorded[name] = proc
        return proc

    def add(self, name: str, sources: list, gains: list[float]):
        proc = self.engine.make_add_processor(name, gains)
        self.graph.append((proc, [s.get_name() for s in sources]))
        return proc


@contextmanager
def _engine_output():
    """Collect what libfaust and plugins print from C++ to stdout and stderr (a mono voice handing over prints a
    line per note), so the run reports it as warnings instead of scattering it over the terminal."""
    sys.stdout.flush()
    sys.stderr.flush()
    saved = os.dup(1), os.dup(2)
    lines = []
    with tempfile.TemporaryFile() as tmp:
        os.dup2(tmp.fileno(), 1)
        os.dup2(tmp.fileno(), 2)
        try:
            yield lines
        finally:
            _flush_c_stdout()
            for fd, copy in zip((1, 2), saved):
                os.dup2(copy, fd)
                os.close(copy)
            tmp.seek(0)
            lines.extend(tmp.read().decode("utf-8", "replace").splitlines())


def _flush_c_stdout() -> None:
    """C and C++ buffer stdout; flush it while it still points at the capture file."""
    try:
        libc = ctypes.CDLL("ucrtbase") if sys.platform == "win32" else ctypes.CDLL(None)
        libc.fflush(None)
    except (OSError, AttributeError):
        pass


def _faust_params(proc) -> dict[str, str]:
    """Short name -> full Faust path ("/dawdreamer/cutoff", "/Sequencer/DSP1/Polyphonic/Voices/kick/tune")."""
    return {d["name"].rsplit("/", 1)[-1]: d["name"] for d in proc.get_parameters_description()}
