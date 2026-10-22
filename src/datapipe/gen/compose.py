"""S1 compose: a preset and a seed become a Score (dawdreamer/specs/audio.md); `ingest_midi` reads a .mid instead.

Every random choice comes from a stream named after what it decides (``audio`` for the key, mode, progression and
violation; ``audio/<track>`` per track), so editing one track never reshuffles another.
"""

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import ROOT
from .score import BEATS_PER_BAR, PPQ, Note, Score, read_midi

PRESET_DIR = ROOT / "dawdreamer" / "presets"
STEPS_PER_BEAT = 4                                # patterns are written in 16th notes
NOTE_NAMES = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6,
              "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
MODES = {
    "ionian": (0, 2, 4, 5, 7, 9, 11), "major": (0, 2, 4, 5, 7, 9, 11),
    "dorian": (0, 2, 3, 5, 7, 9, 10), "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11), "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "aeolian": (0, 2, 3, 5, 7, 8, 10), "minor": (0, 2, 3, 5, 7, 8, 10),
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11),
}
NUMERALS = {"i": 0, "ii": 1, "iii": 2, "iv": 3, "v": 4, "vi": 5, "vii": 6}
STORY = (("hook", 0), ("twist", 4 / 8), ("build", 5 / 8), ("windup", 7 / 8))   # phrase starts as loop fractions
VIOLATIONS = ("motif_up", "kick_dropout", "stutter")


def load_preset(name: str | Path) -> dict:
    path = Path(name)
    if not path.suffix:
        path = PRESET_DIR / f"{name}.toml"
    with open(path, "rb") as fh:
        preset = tomllib.load(fh)
    preset.setdefault("name", path.stem)
    preset["_path"] = str(path)
    return preset


def stream(seed: int, name: str) -> np.random.Generator:
    """The RNG for one named decision: depends only on (seed, name)."""
    digest = hashlib.sha256(f"{seed}:{name}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "little"))


def choose(rng: np.random.Generator, value, nested: bool = False):
    """A list in a preset means "the seed picks one"; ``nested`` for values that are lists themselves."""
    if isinstance(value, list) and (not nested or (value and isinstance(value[0], list))):
        return value[int(rng.integers(len(value)))]
    return value


def euclid(hits: int, steps: int) -> list[int]:
    """Spread ``hits`` onsets as evenly as possible over ``steps`` (Bresenham form of Bjorklund's algorithm)."""
    return [1 if (i * hits) % steps < hits else 0 for i in range(steps)]


def parse_pattern(text: str) -> list[str]:
    """A step string, one character per 16th; spaces and bars (|) are ignored."""
    return [c for c in text if c not in " |\t\n"]


@dataclass
class Context:
    bpm: int
    total: int                          # beats in the loop
    sections: dict[str, float]          # name -> start beat
    tonic: int                          # pitch class 0-11
    mode: tuple[int, ...]
    chords: list[tuple[int, ...]]       # per bar: chord tones as mode degrees
    violation: str

    def section(self, beat: float) -> str:
        return max(((b, n) for n, b in self.sections.items() if b <= beat))[1]

    def chord(self, beat: float) -> tuple[int, ...]:
        return self.chords[int(beat // BEATS_PER_BAR) % len(self.chords)]

    def pitch(self, degree: int, octave: int, scale: tuple[int, ...] | None = None) -> int:
        """MIDI pitch of a scale degree (any integer, wraps into octaves) above the tonic in ``octave`` (C4 = 60)."""
        scale = scale or self.mode
        return 12 * (octave + 1) + self.tonic + scale[degree % len(scale)] + 12 * (degree // len(scale))


def sections_for(bpm: int, override: dict | None = None) -> dict[str, float]:
    """The 8-phrase story on this tempo's grid, snapped to whole beats; ``[music.sections]`` overrides any start."""
    total = bpm // 30 * BEATS_PER_BAR
    sections = {name: float(int(frac * total + 0.5)) for name, frac in STORY}
    sections.update({k: float(v) for k, v in (override or {}).items()})
    return sections


def compose(preset: dict, seed: int) -> Score:
    music = preset["music"]
    rng = stream(seed, "audio")
    bpm = int(music.get("bpm", 120))
    key = choose(rng, music.get("key", "A"))
    mode_name = choose(rng, music.get("mode", "aeolian"))
    progression = choose(rng, music.get("progression", ["i"]), nested=True)
    violation = choose(rng, music.get("violation", list(VIOLATIONS)))
    mode = MODES[mode_name]
    sections = sections_for(bpm, music.get("sections"))
    ctx = Context(bpm, bpm // 30 * BEATS_PER_BAR, sections, NOTE_NAMES[key], mode,
                  [_triad(numeral, music.get("sevenths", False)) for numeral in progression], violation)

    tracks, choices = {}, {}
    for name, spec in preset["track"].items():
        role = ROLES[spec["role"]]
        notes, picked = role(ctx, spec, stream(seed, f"audio/{name}"))
        notes = [Note(_tick(n.beat), _tick(n.dur), n.pitch, n.vel) for n in _arc(ctx, spec, notes)]
        tracks[name] = sorted(notes, key=lambda n: (n.beat, n.pitch))
        if picked:
            choices[name] = picked

    meta = {"preset": preset["name"], "seed": seed, "key": key, "mode": mode_name,
            "progression": progression, "violation": violation, "choices": choices}
    return Score(bpm, tracks, sorted(sections.items(), key=lambda s: s[1]), _automation(ctx), meta)


def ingest_midi(preset: dict, path: Path, quantize: float = 0.25) -> Score:
    """S1 ingest: notes from any .mid, matched to the preset's tracks by track name, else by MIDI channel."""
    bpm, found, channels, markers = read_midi(path)
    bpm = round(bpm) if bpm else int(preset["music"].get("bpm", 120))
    names = list(preset["track"])
    by_lower = {n.lower(): n for n in names}
    sections = sections_for(bpm, preset["music"].get("sections"))
    marked = {name: beat for name, beat in markers if name in sections}
    if marked.get("hook", 0) == 0:
        sections.update(marked)
    ctx_total = bpm // 30 * BEATS_PER_BAR
    tracks, ignored, dropped = {n: [] for n in names}, [], 0
    for midi_name, notes in found.items():
        target = by_lower.get(midi_name.lower())
        if target is None and channels.get(midi_name, 99) < len(names):
            target = names[channels[midi_name]]
        if target is None:
            ignored.append(midi_name)
            continue
        for n in notes:
            beat = round(n.beat / quantize) * quantize if quantize else n.beat
            if beat >= ctx_total:
                dropped += 1
                continue
            tracks[target].append(Note(beat, max(n.dur, 1 / 64), n.pitch, n.vel))     # starts snap, lengths stay
    ctx = Context(bpm, ctx_total, sections, 0, MODES["aeolian"], [(0, 2, 4)], "none")
    meta = {"preset": preset["name"], "source": str(path), "ignored_tracks": ignored, "dropped_notes": dropped}
    return Score(bpm, {k: sorted(v, key=lambda n: (n.beat, n.pitch)) for k, v in tracks.items()},
                 sorted(sections.items(), key=lambda s: s[1]), _automation(ctx), meta)


def resolve_sounds(preset: dict, seed: int) -> tuple[dict, dict]:
    """A copy of the preset with every list-valued sound parameter picked by the seed (stream ``sound/<slot>``),
    plus the picks. Instruments and effects take one value per parameter; the list form is for exploring."""
    picks = {}

    def walk(spec: dict, slot: str) -> dict:
        spec = dict(spec)
        rng = stream(seed, f"sound/{slot}")
        params = {}
        for key, value in spec.get("params", {}).items():
            params[key] = choose(rng, value)
            if isinstance(value, list):
                picks[f"{slot}.{key}"] = params[key]
        if params:
            spec["params"] = params
        if "fallback" in spec:
            spec["fallback"] = walk(spec["fallback"], slot + ".fallback")
        return spec

    out = dict(preset)
    out["track"] = {name: {**t, "instrument": walk(t["instrument"], name),
                           "inserts": [walk(fx, f"{name}:fx{i}") for i, fx in enumerate(t.get("inserts", []))]}
                    for name, t in preset["track"].items()}
    out["bus"] = {name: {**b, "fx": [walk(fx, f"{name}:fx{i}") for i, fx in enumerate(b.get("fx", []))]}
                  for name, b in preset.get("bus", {}).items()}
    master = preset.get("master", {})
    out["master"] = {**master, "fx": [walk(fx, f"master:fx{i}") for i, fx in enumerate(master.get("fx", []))]}
    return out, picks


def _tick(beat: float) -> float:
    """Snap to the MIDI tick grid (1/480 beat), so a score survives score.mid unchanged."""
    return round(beat * PPQ) / PPQ


def _triad(numeral: str, sevenths: bool) -> tuple[int, ...]:
    degree = NUMERALS[numeral.strip("°+7").lower()]
    return (degree, degree + 2, degree + 4) + ((degree + 6,) if sevenths else ())


def _automation(ctx: Context) -> dict[str, list[tuple[float, float]]]:
    """``riser``: 0 until the build starts, then a straight ramp to 1 at the loop end; the downbeat resets it."""
    return {"riser": [(ctx.sections["build"], 0.0), (float(ctx.total), 1.0)]}


# ---- roles: each returns (notes, the choices it made) --------------------------------------------------------------

def _rhythm(ctx: Context, spec: dict, rng: np.random.Generator) -> tuple[list[str], dict]:
    """The track's step pattern for the whole loop: ``pattern`` (string) or ``euclid`` {hits, steps}."""
    steps = ctx.total * STEPS_PER_BEAT
    if "pattern" in spec:
        text = choose(rng, spec["pattern"])
        cells, picked = parse_pattern(text), {"pattern": text}
    else:
        e = spec.get("euclid", {})
        hits, n = int(choose(rng, e.get("hits", 4))), int(e.get("steps", 16))
        cells = ["x" if on else "." for on in euclid(hits, n)]
        onsets = [i for i, c in enumerate(cells) if c == "x"]
        shift = onsets[int(rng.integers(len(onsets)))] if e.get("rotate", True) else 0
        cells = cells[shift:] + cells[:shift]                     # rotated so an onset stays on the downbeat
        picked = {"euclid": [hits, n, shift]}
    if steps % len(cells):
        raise ValueError(f"pattern length {len(cells)} does not divide the loop's {steps} sixteenths")
    return cells * (steps // len(cells)), picked


def _lengths(cells: list[str], i: int, gate: float) -> float:
    """Duration in beats of the onset at step ``i``: through any following ``-`` holds, else ``gate``."""
    j = i + 1
    while j < len(cells) and cells[j] == "-":
        j += 1
    held = (j - i) / STEPS_PER_BEAT
    if j > i + 1:
        return held
    nxt = next((k for k in range(i + 1, len(cells)) if cells[k] not in ".-"), len(cells))
    return min(gate, (nxt - i) / STEPS_PER_BEAT)


def _vel(rng: np.random.Generator, base: int, humanize: int) -> int:
    return int(np.clip(base + rng.integers(-humanize, humanize + 1), 1, 127))


def drums(ctx: Context, spec: dict, rng: np.random.Generator):
    cells, picked = _rhythm(ctx, spec, rng)
    note, alt = int(spec.get("note", 36)), int(spec.get("alt_note", spec.get("note", 36)))
    gate, humanize = float(spec.get("gate", 0.25)), int(spec.get("humanize", 4))
    notes = []
    for i, c in enumerate(cells):
        if c in "xXoO":
            notes.append(Note(i / STEPS_PER_BEAT, gate * (2 if c in "oO" else 1),
                              alt if c in "oO" else note, _vel(rng, 124 if c.isupper() else 100, humanize)))
    build = spec.get("build", "keep")
    b0, w0 = ctx.sections["build"], ctx.sections["windup"]
    taken = {n.beat for n in notes}
    if build == "double":           # fill every free 16th through build and windup, rising
        for i in range(int(b0 * STEPS_PER_BEAT), ctx.total * STEPS_PER_BEAT):
            beat = i / STEPS_PER_BEAT
            if beat not in taken:
                rise = (beat - b0) / (ctx.total - b0)
                notes.append(Note(beat, gate, note, _vel(rng, int(60 + 45 * rise), humanize)))
    elif build == "roll":           # 8ths through the build, 16ths through the windup, crescendo
        notes = [n for n in notes if n.beat < b0]
        for i in range(int(b0 * STEPS_PER_BEAT), ctx.total * STEPS_PER_BEAT):
            beat = i / STEPS_PER_BEAT
            if beat >= w0 or i % 2 == 0:
                rise = (beat - b0) / (ctx.total - b0)
                notes.append(Note(beat, gate * 0.5, note, _vel(rng, int(70 + 55 * rise), humanize)))
    if ctx.violation == "kick_dropout" and spec.get("dropout", False):
        notes = [n for n in notes if ctx.section(n.beat) != "twist"]
    return notes, picked


def bass(ctx: Context, spec: dict, rng: np.random.Generator):
    """Chord roots on the track's rhythm: ``x`` root, ``o`` octave up, ``5`` fifth, ``-`` hold."""
    cells, picked = _rhythm(ctx, spec, rng)
    octave, gate = int(spec.get("octave", 1)), float(spec.get("gate", 0.22))
    low = 12 * (octave + 1) + ctx.tonic
    notes = []
    for i, c in enumerate(cells):
        if c not in "xXo5":
            continue
        beat = i / STEPS_PER_BEAT
        root = ctx.pitch(ctx.chord(beat)[0], octave)
        root -= 12 if root >= low + 7 else 0
        pitch = root + {"o": 12, "5": 7}.get(c, 0)
        notes.append(Note(beat, _lengths(cells, i, gate), pitch, _vel(rng, 120 if c == "X" else 96, 4)))   # 303s accent above 100
    return notes, picked


def motif(ctx: Context, spec: dict, rng: np.random.Generator):
    """The hook: a 3-5 note motif on a Euclidean rhythm, restarting every bar; odd bars answer with a changed note."""
    cells, picked = _rhythm(ctx, spec, rng)
    minor = 3 in ctx.mode
    scale = ctx.mode if spec.get("scale", "pentatonic") == "mode" else ((0, 3, 5, 7, 10) if minor else (0, 2, 4, 7, 9))
    length = int(choose(rng, spec.get("length", [3, 4, 5])))
    degrees = [int(rng.choice([0, 0, 3] if len(scale) == 5 else [0, 0, 4]))]
    for _ in range(length - 1):
        step = int(rng.choice([-2, -1, 1, 2, 3], p=[0.15, 0.3, 0.3, 0.15, 0.1]))
        degrees.append(int(np.clip(degrees[-1] + step, -2, 7)))
    answer = degrees[-1] + int(rng.choice([-1, 1, 2]))
    octave, gate = int(spec.get("octave", 5)), float(spec.get("gate", 0.5))
    steps_per_bar = BEATS_PER_BAR * STEPS_PER_BEAT
    notes = []
    for bar in range(ctx.total // BEATS_PER_BAR):
        onsets = [i for i in range(bar * steps_per_bar, (bar + 1) * steps_per_bar) if cells[i] in "xX"]
        for k, i in enumerate(onsets):
            deg = degrees[k % length]
            if bar % 2 == 1 and k == len(onsets) - 1:
                deg = answer
            beat = i / STEPS_PER_BEAT
            notes.append(Note(beat, _lengths(cells, i, gate), ctx.pitch(deg, octave, scale),
                              _vel(rng, 118 if k == 0 else 96, 6)))
    t0, t1 = ctx.sections["twist"], ctx.sections["build"]
    if ctx.violation == "motif_up":
        notes = [Note(n.beat, n.dur, n.pitch + 5, n.vel) if t0 <= n.beat < t1 else n for n in notes]
    elif ctx.violation == "stutter":
        notes = [n for n in notes if not t0 <= n.beat < t1]
        first = ctx.pitch(degrees[0], octave, scale)
        steps = int((t1 - t0) * STEPS_PER_BEAT)
        notes += [Note(t0 + s / STEPS_PER_BEAT, 0.2, first, int(70 + 45 * s / steps)) for s in range(steps)]
    picked.update({"degrees": degrees, "answer": answer, "scale": list(scale)})
    return notes, picked


def chords(ctx: Context, spec: dict, rng: np.random.Generator):
    """One chord per bar (or per ``pattern`` onset), voiced close to the previous chord."""
    octave = int(spec.get("octave", 4))
    center = 12 * (octave + 1) + ctx.tonic + 5        # chords centre a fourth above the tonic
    if "pattern" in spec:
        cells, picked = _rhythm(ctx, spec, rng)
        onsets = [(i / STEPS_PER_BEAT, _lengths(cells, i, 1.0)) for i, c in enumerate(cells) if c in "xX"]
    else:
        onsets, picked = [(float(b), BEATS_PER_BAR - 0.05) for b in range(0, ctx.total, BEATS_PER_BAR)], {}
    notes, prev = [], None
    for beat, dur in onsets:
        tones = sorted(ctx.pitch(d, octave) for d in ctx.chord(beat))
        voicing = _voice(tones, prev, center)
        notes += [Note(beat, dur, p, _vel(rng, 84, 4)) for p in voicing]
        prev = voicing
    return notes, picked


def _voice(tones: list[int], prev: list[int] | None, center: int) -> list[int]:
    candidates = []
    for inv in range(len(tones)):
        v = sorted(tones[inv:] + [t + 12 for t in tones[:inv]])
        candidates += [[p + shift for p in v] for shift in (-12, 0, 12)]
    if prev:
        return min(candidates, key=lambda v: sum(abs(a - b) for a, b in zip(v, prev)))
    return min(candidates, key=lambda v: abs(sum(v) / len(v) - center))


def riser(ctx: Context, spec: dict, rng: np.random.Generator):
    return [], {}                   # driven by the score's riser curve, not by notes


def impact(ctx: Context, spec: dict, rng: np.random.Generator):
    at = spec.get("at", ["hook"])
    return [Note(ctx.sections[s], 1.0, int(spec.get("note", 36)), 127) for s in at], {}


ROLES = {"drums": drums, "bass": bass, "motif": motif, "chords": chords, "riser": riser, "impact": impact}


def _arc(ctx: Context, spec: dict, notes: list[Note]) -> list[Note]:
    """The windup: by default every track's last beat drops out, so the downbeat lands on silence and the riser."""
    if spec.get("windup", "drop") == "drop":
        end = ctx.total - 1
        notes = [Note(n.beat, min(n.dur, end - n.beat), n.pitch, n.vel) for n in notes if n.beat < end]
    return notes
