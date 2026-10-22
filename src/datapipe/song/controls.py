"""S3 for methods B, C and D: a song becomes controls.json, the same contract as a generated run (SPEC §16.1, §16.3).

| Signal | master (B) | stems (C) | midi (D) |
| hits | onsets in the mix, by band | onsets per stem | MIDI note-ons; stems without MIDI: onsets |
| stem loudness | none | every stem | every stem |
| mix loudness, brightness, bands | the master | the master | the master |
| tempo, beat and bar | tracked on the master | tracked on the drum stems | the MIDI's tempo map |
| sections | song.toml, else bar loudness | as B | song.toml, else MIDI markers, else as B |

A song does not loop: ``wrap`` is false, so no envelope runs from the end into the start. ``close`` (song.toml
``loop``, default true) still closes the picture's accumulated motion.
"""

import numpy as np

from .. import features
from ..features import FPS, rounded
from . import analysis, onsets
from .ingest import ROLES, Song
from .midi import Notes, track_controls

DRUM_ROLES = ("kick", "snare", "clap", "hats", "drums")


def build(song: Song, notes: Notes | None = None, bpm: float | None = None, progress=print) -> dict:
    """controls.json for a song (method B, C or D); ``notes`` is D's MIDI, ``bpm`` an override of the tempo."""
    n, master = song.frames, song.master
    bpm = bpm or song.settings.get("bpm")
    meta = {"method": song.method, "title": song.title, "files": song.files, "warnings": song.warnings}

    progress("  hits")
    tracks: dict[str, dict] = {}
    if notes is not None:
        notes = notes.shifted(song.start_s)
        for name, track_notes in notes.tracks.items():
            tracks[name] = track_controls(track_notes, n)
        meta["midi"] = notes.files
        song.warnings.extend(notes.warnings)
    if song.method == "master":
        for role, hits in onsets.drum_hits(master, full_mix=True).items():
            tracks[role] = {"hits": hits, "source": "onset"}
    for name, x in song.stems.items():
        if name in tracks:
            continue                                     # D: the MIDI times this stem
        if name == "drums":
            for role, hits in onsets.drum_hits(x).items():
                if role not in tracks and role not in song.stems:
                    tracks[role] = {"hits": hits, "source": "onset"}
        tracks[name] = {"hits": onsets.hits(x), "source": "onset"}

    stems = {name: {"loud": rounded(features.loudness(x, attack=1, release=7, wrap=False))}
             for name, x in song.stems.items()}

    progress("  tempo and sections")
    if notes is not None and not bpm:
        tempo, bpb = notes.bpm, notes.beats_per_bar
        beat = notes.beats_at(np.arange(n) / FPS)
        whole = np.arange(np.ceil(beat[0]), beat[-1] + 1)
        beats_s = np.array([notes.seconds_at_beat(b) for b in whole])
        downbeat, tempo_source = int((-whole[0]) % bpb) if len(whole) else 0, "midi"
        beat_phase, bar_phase = beat % 1.0, (beat / bpb) % 1.0
        bars = np.arange(np.ceil(beat[0] / bpb) * bpb, beat[-1] + 1, bpb)
        bar_frames = sorted({int(np.floor(notes.seconds_at_beat(b) * FPS + 0.5)) for b in bars} | {0})
        bar_frames = [f for f in bar_frames if 0 <= f < n]
    else:
        drums = [x for name, x in song.stems.items() if name in DRUM_ROLES]
        source = sum(drums) if drums else master
        tracked = analysis.track_beats(source, bpm)
        tempo, beats_s, downbeat = tracked["bpm"], tracked["beats"], tracked["downbeat"]
        tempo_source = tracked["source"] + (" on the drum stems" if drums else " on the master")
        g = analysis.grid(beats_s, n, downbeat, tempo)
        beat_phase, bar_phase, bar_frames = g["beat"], g["bar"], g["bar_frames"]

    structure = analysis.sections(master, bar_frames, n)
    named, how = structure["sections"], "bar loudness"
    if "sections" in song.settings:
        named, how = _sections_from_bars(song.settings["sections"], tempo, notes, n, song.start_s), "song.toml"
    elif notes is not None and notes.markers:
        named, how = _sections_from_markers(notes.markers, n), "MIDI markers"
    drop = next((f for name, f in named if name == "drop"), None) if how != "bar loudness" else structure["drop"]
    frames_per_bar = 4 * FPS * 60 / tempo

    meta.update({"tempo_source": tempo_source, "sections_from": how, "drop_frame": drop,
                 "roles": sorted(set(tracks) & set(ROLES)), "detection": {k: len(v["hits"]) for k, v in tracks.items()}})
    return {
        "method": song.method, "wrap": False, "close": bool(song.settings.get("loop", True)),
        "fps": FPS, "frames": n, "bpm": round(float(tempo), 3), "frames_per_beat": round(FPS * 60 / tempo, 4),
        "downbeat": int(downbeat), "beats": [round(float(b), 4) for b in beats_s],
        "sections": [{"name": name, "frame": int(f)} for name, f in named],
        "section": analysis.section_index(named, n).tolist(),
        "phase": rounded(np.arange(n) / n),
        "beat": rounded(beat_phase),
        "bar": rounded(bar_phase),
        "bar_frames": [int(f) for f in bar_frames],
        "curves": {"build": rounded(analysis.build_curve(named, n)),
                   "energy": rounded(analysis.energy_curve(structure["energy"], frames_per_bar))},
        "tracks": tracks,
        "stems": stems,
        "mix": {"loud": rounded(features.loudness(master, attack=2, release=12, wrap=False)),
                "bright": rounded(features.brightness(master, wrap=False))},
        "bands": {k: rounded(v) for k, v in features.bands(master, wrap=False).items()},
        "meta": meta,
    }


def _sections_from_bars(table: dict, bpm: float, notes: Notes | None, n: int, start: float = 0.0
                        ) -> list[tuple[str, int]]:
    """song.toml [sections]: name = the bar (1-based, from the start of the file, before any --start cut) where it
    starts."""
    out = []
    for name, bar in table.items():
        beat = (float(bar) - 1) * (notes.beats_per_bar if notes else 4)
        seconds = notes.seconds_at_beat(beat) if notes else beat * 60 / bpm - start
        out.append((str(name).lower(), int(np.clip(np.floor(seconds * FPS + 0.5), 0, n - 1))))
    out.sort(key=lambda s: s[1])
    if not out or out[0][1] > 0:
        out.insert(0, ("intro", 0))
    return _dedupe(out)


def _sections_from_markers(markers: list[tuple[str, float]], n: int) -> list[tuple[str, int]]:
    out = sorted((name, min(int(np.floor(t * FPS + 0.5)), n - 1)) for name, t in markers)
    out.sort(key=lambda s: s[1])
    if not out or out[0][1] > 0:
        out.insert(0, ("intro", 0))
    return _dedupe(out)


def _dedupe(named: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """One section per start frame (the last named wins)."""
    by_frame = {}
    for name, f in named:
        by_frame[f] = name
    return [(name, f) for f, name in sorted(by_frame.items())]
