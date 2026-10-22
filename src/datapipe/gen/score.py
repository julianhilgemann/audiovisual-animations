"""The score of one loop: the timing contract, its notes, sections and curves, and their files (dawdreamer/specs/handoff.md).

Standard library only, Python 3.11 syntax: Blender and TouchDesigner import this module to read score.json and
frames.csv the same way the pipeline writes them. MIDI goes through `mido`, imported only where it is used.
"""

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

FPS = 60
SAMPLE_RATE = 48000
LOOP_SECONDS = 8
FRAMES = FPS * LOOP_SECONDS               # 480
SAMPLES = SAMPLE_RATE * LOOP_SECONDS      # 384,000: 800 per frame
BEATS_PER_BAR = 4
ALLOWED_BPM = (120, 150, 180, 240)        # bars = bpm / 30 and frames per beat = 3600 / bpm are both whole
PPQ = 480                                 # MIDI ticks per quarter note


@dataclass
class Note:
    beat: float     # 0-based, in quarter notes from the loop start
    dur: float      # in quarter notes
    pitch: int
    vel: int


@dataclass
class Score:
    bpm: int
    tracks: dict[str, list[Note]]
    sections: list[tuple[str, float]]                  # (name, start beat), first at 0
    automation: dict[str, list[tuple[float, float]]] = field(default_factory=dict)  # name -> [(beat, value)]
    meta: dict = field(default_factory=dict)           # what the composer chose: key, mode, violation, ...

    @property
    def bars(self) -> int:
        return self.bpm // 30

    @property
    def total_beats(self) -> int:
        return self.bars * BEATS_PER_BAR

    @property
    def frames_per_beat(self) -> float:
        return 3600 / self.bpm

    def seconds(self, beat: float) -> float:
        return beat * 60 / self.bpm

    def frame_of(self, beat: float) -> int:
        """Blender frame (1-based) of a beat; half frames round up, so a 16th at 7.5 frames lands on frame 9."""
        return 1 + math.floor(beat * self.frames_per_beat + 0.5) % FRAMES

    def curve(self, name: str, beat: float) -> float:
        """Linear interpolation of an automation curve; before its first point it holds the first value."""
        points = self.automation[name]
        if beat <= points[0][0]:
            return points[0][1]
        for (b0, v0), (b1, v1) in zip(points, points[1:]):
            if beat <= b1:
                return v0 if b1 == b0 else v0 + (v1 - v0) * (beat - b0) / (b1 - b0)
        return points[-1][1]

    def section_at(self, beat: float) -> int:
        return max(i for i, (_, start) in enumerate(self.sections) if start <= beat)

    def validate(self) -> list[str]:
        """Return the contract violations; an empty list means the score is valid."""
        errors = []
        if self.bpm not in ALLOWED_BPM:
            errors.append(f"bpm {self.bpm} is off the 8-second grid; allowed: {ALLOWED_BPM}")
            return errors
        for name, notes in self.tracks.items():
            for n in notes:
                if not 0 <= n.beat < self.total_beats:
                    errors.append(f"{name}: note at beat {n.beat} is outside the loop (0..{self.total_beats})")
                if n.dur <= 0 or not 0 <= n.pitch <= 127 or not 1 <= n.vel <= 127:
                    errors.append(f"{name}: bad note {n}")
        starts = [b for _, b in self.sections]
        if not starts or starts[0] != 0:
            errors.append("sections must start at beat 0")
        if any(b1 <= b0 for b0, b1 in zip(starts, starts[1:])) or (starts and starts[-1] >= self.total_beats):
            errors.append(f"section starts must rise inside the loop: {starts}")
        for name, points in self.automation.items():
            beats = [b for b, _ in points]
            if not points or beats != sorted(beats) or beats[0] < 0 or beats[-1] > self.total_beats:
                errors.append(f"automation {name}: points must be sorted beats inside 0..{self.total_beats}")
        return errors

    # ---- score.json -------------------------------------------------------------------------------------------

    def to_json(self) -> dict:
        return {
            "bpm": self.bpm, "bars": self.bars, "beats_per_bar": BEATS_PER_BAR,
            "fps": FPS, "sample_rate": SAMPLE_RATE, "frames": FRAMES,
            "tracks": {name: [asdict(n) for n in notes] for name, notes in self.tracks.items()},
            "sections": [{"name": name, "beat": beat} for name, beat in self.sections],
            "automation": {name: [list(p) for p in points] for name, points in self.automation.items()},
            "meta": self.meta,
        }

    @classmethod
    def from_json(cls, data: dict) -> "Score":
        return cls(
            bpm=data["bpm"],
            tracks={name: [Note(**n) for n in notes] for name, notes in data["tracks"].items()},
            sections=[(s["name"], s["beat"]) for s in data["sections"]],
            automation={name: [tuple(p) for p in points] for name, points in data.get("automation", {}).items()},
            meta=data.get("meta", {}),
        )

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.to_json(), indent=1) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Score":
        return cls.from_json(json.loads(Path(path).read_text(encoding="utf-8")))

    # ---- score.mid --------------------------------------------------------------------------------------------

    def save_midi(self, path: Path) -> None:
        """One MIDI track per score track, named after it, on its own channel; sections become markers."""
        import mido

        mid = mido.MidiFile(type=1, ticks_per_beat=PPQ)
        head = mido.MidiTrack([
            mido.MetaMessage("track_name", name="score", time=0),
            mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(self.bpm), time=0),
            mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0),
        ])
        head.extend(_delta([(round(b * PPQ), 0, mido.MetaMessage("marker", text=name)) for name, b in self.sections]))
        head.append(mido.MetaMessage("end_of_track", time=PPQ * self.total_beats - sum(m.time for m in head)))
        mid.tracks.append(head)
        for channel, (name, notes) in enumerate(self.tracks.items()):
            ch = channel % 16
            events = []
            for n in notes:
                on, off = round(n.beat * PPQ), round((n.beat + n.dur) * PPQ)
                events.append((on, 1, mido.Message("note_on", note=n.pitch, velocity=n.vel, channel=ch)))
                events.append((max(off, on + 1), 0, mido.Message("note_off", note=n.pitch, velocity=0, channel=ch)))
            track = mido.MidiTrack([mido.MetaMessage("track_name", name=name, time=0)])
            track.extend(_delta(events))
            mid.tracks.append(track)
        mid.save(path)


def _delta(events: list) -> list:
    """(tick, order, message) with absolute ticks -> messages with delta times; note-offs sort before note-ons."""
    out, now = [], 0
    for tick, _, msg in sorted(events, key=lambda e: (e[0], e[1])):
        out.append(msg.copy(time=tick - now))
        now = tick
    return out


def read_midi(path: Path) -> tuple[float | None, dict[str, list[Note]], dict[str, int], list[tuple[str, float]]]:
    """Read any MIDI file: (bpm or None, notes per track name, MIDI channel per track name, markers)."""
    import mido

    mid = mido.MidiFile(path)
    ppq = mid.ticks_per_beat
    bpm, tracks, channels, markers = None, {}, {}, []
    for i, track in enumerate(mid.tracks):
        name, tick, held, notes = f"track{i}", 0, {}, []
        for msg in track:
            tick += msg.time
            if msg.type == "track_name" and msg.name.strip():
                name = msg.name.strip()
            elif msg.type == "set_tempo" and bpm is None:
                bpm = round(mido.tempo2bpm(msg.tempo), 3)
            elif msg.type == "marker":
                markers.append((msg.text.strip(), tick / ppq))
            elif msg.type == "note_on" and msg.velocity > 0:
                held[(msg.channel, msg.note)] = (tick, msg.velocity)
                channels.setdefault(name, msg.channel)
            elif msg.type in ("note_off", "note_on") and (msg.channel, msg.note) in held:
                start, vel = held.pop((msg.channel, msg.note))
                notes.append(Note(start / ppq, max(tick - start, 1) / ppq, msg.note, vel))
        if notes:
            tracks.setdefault(name, []).extend(notes)
    return bpm, tracks, channels, markers


# ---- frames.csv ---------------------------------------------------------------------------------------------------

def frame_table(score: Score) -> tuple[list[str], list[list[float]]]:
    """The score on the video frame grid, one row per frame (dawdreamer/specs/handoff.md, frames.csv).

    Per track with notes: ``<track>`` is the note-on velocity (0-1) on the frame a note starts, ``<track>_gate`` is 1
    while a note sounds, and ``<track>_pitch`` (tracks with more than one pitch) the lowest sounding pitch, held after
    release. Per automation curve: ``<curve>_curve``.
    """
    fpb, total = score.frames_per_beat, score.total_beats
    beats = [f / fpb for f in range(FRAMES)]
    header = ["frame", "time_s", "beat", "phase", "section"]
    columns = [[f + 1 for f in range(FRAMES)], [f / FPS for f in range(FRAMES)], beats,
               [f / FRAMES for f in range(FRAMES)], [score.section_at(b) for b in beats]]
    for name, notes in score.tracks.items():
        if not notes:
            continue
        hit, gate, low = [0.0] * FRAMES, [0.0] * FRAMES, [math.inf] * FRAMES
        for n in notes:
            f0 = score.frame_of(n.beat) - 1
            hit[f0] = max(hit[f0], n.vel / 127)
            for f, b in enumerate(beats):
                if (b - n.beat) % total < n.dur:          # wraps notes that ring past the loop end
                    gate[f] = 1.0
                    low[f] = min(low[f], n.pitch)
        header += [name, f"{name}_gate"]
        columns += [hit, gate]
        if len({n.pitch for n in notes}) > 1:
            held, last = [], next((p for p in reversed(low) if p != math.inf), 0)
            for p in low:
                last = p if p != math.inf else last
                held.append(last)
            header.append(f"{name}_pitch")
            columns.append(held)
    for name in score.automation:
        header.append(f"{name}_curve")
        columns.append([score.curve(name, b) for b in beats])
    return header, [list(row) for row in zip(*columns)]


def save_frames(score: Score, path: Path) -> None:
    header, rows = frame_table(score)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        out = csv.writer(fh)
        out.writerow(header)
        out.writerows([[_fmt(v) for v in row] for row in rows])


def _fmt(v: float) -> str:
    return str(v) if isinstance(v, int) else f"{v:.6g}"
