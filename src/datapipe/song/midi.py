"""Method D's MIDI (SPEC §16.2, §16.3): note-ons in seconds, per track, on the song's timeline.

Each file's time 0 is the song's start (consolidate clips from the export start in the DAW). A file with one track
of notes takes the file's name; a multitrack file keeps its track names. Tempo changes are honoured. A drum track
(role ``drums``, or ``[drums] file`` in song.toml) is split into kick, snare, clap and hats by note number.
"""

from dataclasses import dataclass, field
from pathlib import Path

import mido
import numpy as np

from ..features import FPS
from .ingest import _slug, assign_roles

GM_DRUMS = {"kick": [35, 36], "snare": [38, 40], "clap": [39], "hats": [42, 44, 46]}


@dataclass
class Notes:
    tempo_map: list[tuple[float, float]]                     # (second, bpm), first at 0
    beats_per_bar: int
    tracks: dict[str, list[tuple[float, float, int, int]]]   # name -> (on s, off s, pitch, velocity)
    markers: list[tuple[str, float]] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    start: float = 0.0                                       # seconds of the song cut off the front (--start)

    @property
    def bpm(self) -> float:
        return self.tempo_map[0][1]

    def shifted(self, start: float) -> "Notes":
        """The same song with its first ``start`` seconds cut off: times count from the cut, beats stay the song's."""
        if not start:
            return self
        tracks = {name: [(on - start, off - start, p, v) for on, off, p, v in notes if off > start]
                  for name, notes in self.tracks.items()}
        markers = [(name, t - start) for name, t in self.markers if t >= start]
        return Notes(self.tempo_map, self.beats_per_bar, {k: v for k, v in tracks.items() if v}, markers,
                     self.files, self.warnings, self.start + start)

    def beats_at(self, seconds: np.ndarray) -> np.ndarray:
        """Beats from the song's start at each time (counted from the cut, if any), through the tempo map."""
        seconds = np.asarray(seconds, dtype=np.float64) + self.start
        out = np.zeros_like(seconds)
        starts = [t for t, _ in self.tempo_map] + [np.inf]
        beat = 0.0
        for (t0, bpm), t1 in zip(self.tempo_map, starts[1:]):
            inside = (seconds >= t0) & (seconds < t1)
            out[inside] = beat + (seconds[inside] - t0) * bpm / 60
            if np.isfinite(t1):
                beat += (t1 - t0) * bpm / 60
        return out

    def seconds_at_beat(self, beat: float) -> float:
        """The time of a beat of the song, counted from the cut (if any)."""
        starts = [t for t, _ in self.tempo_map]
        b = 0.0
        for i, (t0, bpm) in enumerate(self.tempo_map):
            t1 = starts[i + 1] if i + 1 < len(starts) else np.inf
            span = (t1 - t0) * bpm / 60
            if beat <= b + span:
                return t0 + (beat - b) * 60 / bpm - self.start
            b += span
        return float("inf")


def read(paths: list[Path], settings: dict) -> Notes:
    """All MIDI files of a song, named and assigned to roles, the drum track split."""
    raw, tempo_map, beats_per_bar, markers = {}, None, 4, []
    for path in paths:
        mid = mido.MidiFile(path)
        tmap = _tempo_map(mid)
        if tempo_map is None:
            tempo_map = tmap
        sig = next((m for t in mid.tracks for m in t if m.type == "time_signature"), None)
        if sig is not None and path == paths[0]:
            beats_per_bar = sig.numerator * 4 // sig.denominator or 4
        markers += _markers(mid, tmap)
        tracks = [(t, _notes(t, mid.ticks_per_beat, tmap)) for t in mid.tracks]
        tracks = [(t, n) for t, n in tracks if n]
        for i, (track, notes) in enumerate(tracks):
            if len(tracks) == 1:
                name = path.stem
            else:
                name = next((m.name.strip() for m in track if m.type == "track_name" and m.name.strip()),
                            f"{path.stem} {i + 1}")
            raw.setdefault(name, []).extend(notes)
    roles, warnings = assign_roles(list(raw), settings.get("roles", {}))
    tracks, files = {}, {}
    for name, notes in raw.items():
        tracks.setdefault(roles[name], []).extend(notes)
        files[roles[name]] = name
    drum_cfg = settings.get("drums", {})
    drum_track = roles.get(drum_cfg["file"], _slug(drum_cfg["file"])) if "file" in drum_cfg else "drums"
    if drum_track in tracks:
        split = {role: drum_cfg.get(role, GM_DRUMS.get(role, [])) for role in set(GM_DRUMS) | (set(drum_cfg) - {"file"})}
        rest = []
        for note in tracks.pop(drum_track):
            role = next((r for r, pitches in split.items() if note[2] in pitches), None)
            if role:
                tracks.setdefault(role, []).append(note)
                files.setdefault(role, f"{files.get(drum_track, drum_track)} (notes {split[role]})")
            else:
                rest.append(note)
        if rest:
            tracks[drum_track] = rest
    for notes in tracks.values():
        notes.sort()
    return Notes(tempo_map or [(0.0, 120.0)], beats_per_bar, tracks, sorted(markers, key=lambda m: m[1]), files,
                 warnings)


def _tempo_map(mid: mido.MidiFile) -> list[tuple[float, float]]:
    """(second, bpm) for every tempo change in the file; 120 BPM when it has none."""
    changes = []
    for track in mid.tracks:
        tick = 0
        for msg in track:
            tick += msg.time
            if msg.type == "set_tempo":
                changes.append((tick, msg.tempo))
    changes = sorted(set(changes)) or [(0, 500000)]
    if changes[0][0] > 0:
        changes.insert(0, (0, changes[0][1]))
    out, seconds, last_tick, last_tempo = [], 0.0, 0, changes[0][1]
    for tick, tempo in changes:
        seconds += mido.tick2second(tick - last_tick, mid.ticks_per_beat, last_tempo)
        out.append((seconds, round(mido.tempo2bpm(tempo), 4)))
        last_tick, last_tempo = tick, tempo
    return out


def _to_seconds(tick: int, ppq: int, tmap: list[tuple[float, float]]) -> float:
    beat, t_prev, bpm_prev, b_prev = tick / ppq, 0.0, tmap[0][1], 0.0
    for t, bpm in tmap[1:]:
        b_here = b_prev + (t - t_prev) * bpm_prev / 60
        if beat < b_here:
            break
        t_prev, bpm_prev, b_prev = t, bpm, b_here
    return t_prev + (beat - b_prev) * 60 / bpm_prev


def _notes(track: mido.MidiTrack, ppq: int, tmap) -> list[tuple[float, float, int, int]]:
    tick, held, out = 0, {}, []
    for msg in track:
        tick += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            held[(msg.channel, msg.note)] = (tick, msg.velocity)
        elif msg.type in ("note_off", "note_on") and (msg.channel, msg.note) in held:
            start, vel = held.pop((msg.channel, msg.note))
            out.append((_to_seconds(start, ppq, tmap), _to_seconds(max(tick, start + 1), ppq, tmap), msg.note, vel))
    for (channel, note), (start, vel) in held.items():           # never released: a short note
        out.append((_to_seconds(start, ppq, tmap), _to_seconds(start + ppq // 4, ppq, tmap), note, vel))
    return out


def _markers(mid: mido.MidiFile, tmap) -> list[tuple[str, float]]:
    out = []
    for track in mid.tracks:
        tick = 0
        for msg in track:
            tick += msg.time
            if msg.type in ("marker", "cue_marker") and msg.text.strip():
                out.append((msg.text.strip().lower(), _to_seconds(tick, mid.ticks_per_beat, tmap)))
    return out


def track_controls(notes: list[tuple[float, float, int, int]], n: int) -> dict:
    """A track's hits (one per frame, the loudest), gate and (with more than one pitch) lowest sounding pitch."""
    hits, gate, low = {}, np.zeros(n), np.full(n, np.inf)
    for on, off, pitch, vel in notes:
        f0 = int(np.floor(on * FPS + 0.5))
        if 0 <= f0 < n:
            hits[f0] = max(hits.get(f0, 0.0), round(vel / 127, 4))
        a, b = max(f0, 0), min(int(np.floor(off * FPS + 0.5)), n)
        if b <= a and 0 <= f0 < n:
            b = a + 1
        gate[a:b] = 1.0
        low[a:b] = np.minimum(low[a:b], pitch)
    out = {"hits": sorted([f, a] for f, a in hits.items()), "gate": gate.tolist(), "source": "midi"}
    if len({p for _, _, p, _ in notes}) > 1 and np.isfinite(low).any():
        held, last = [], float(low[np.isfinite(low)][0])
        for p in low:
            last = float(p) if np.isfinite(p) else last
            held.append(last)
        out["pitch"] = held
    return out
