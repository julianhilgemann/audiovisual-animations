"""A synthetic song with known hits, written the way a DAW exports one (SPEC §16.6): master, stems and MIDI.

124 BPM, 12 bars (23.2 s): a quiet 4-bar intro (hats and bass), then an 8-bar drop with a four-on-the-floor kick,
snare on 2 and 4, eighth hats and an off-beat bass that competes with the kick in the low band.
"""

from pathlib import Path

import mido
import numpy as np
import soundfile as sf

SR = 48000
BPM = 124
BARS = 12
INTRO_BARS = 4
BEAT = 60 / BPM


def _kick(n: int) -> np.ndarray:
    t = np.arange(n) / SR
    freq = 45 + 105 * np.exp(-t / 0.03)
    tone = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t / 0.18)
    click = np.random.default_rng(1).standard_normal(n) * np.exp(-t / 0.002) * 0.3
    return tone + click


def _snare(n: int) -> np.ndarray:
    t = np.arange(n) / SR
    noise = np.random.default_rng(2).standard_normal(n)
    noise = np.diff(noise, prepend=0.0)                          # tilt toward the highs
    return 0.5 * noise * np.exp(-t / 0.09) + 0.5 * np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.06)


def _hat(n: int) -> np.ndarray:
    t = np.arange(n) / SR
    noise = np.random.default_rng(3).standard_normal(n)
    for _ in range(3):
        noise = np.diff(noise, prepend=0.0)                      # a crude high-pass
    return 0.08 * noise * np.exp(-t / 0.025)


def _bass(n: int, f: float) -> np.ndarray:
    t = np.arange(n) / SR
    saw = 2 * ((t * f) % 1.0) - 1
    smooth = np.convolve(saw, np.ones(24) / 24, mode="same")      # a soft low-pass
    attack = np.minimum(t / 0.005, 1.0)
    return 0.6 * smooth * attack * np.exp(-t / 0.15)


def notes() -> dict[str, list[tuple[float, int, int]]]:
    """Per track: (beat, pitch, velocity), beats from the song start."""
    out = {"kick": [], "snare": [], "hats": [], "bass": []}
    for bar in range(BARS):
        drop = bar >= INTRO_BARS
        for beat in range(4):
            b = bar * 4 + beat
            if drop:
                out["kick"].append((b, 36, 120))
                if beat in (1, 3):
                    out["snare"].append((b, 38, 110))
            for half in (0, 0.5):
                out["hats"].append((b + half, 42, 90 if half else 70))
            out["bass"].append((b + 0.5, 33 + (bar % 2) * 5, 100))
    return out


def make_song(folder: Path, midi: bool = True, stems: bool = True) -> dict[str, list[float]]:
    """Write master.wav, stems/*.wav and midi/*.mid into ``folder``; return the true onset times per track."""
    folder = Path(folder)
    total = int((BARS * 4 * BEAT + 0.5) * SR)
    tracks = {name: np.zeros(total) for name in ("kick", "snare", "hats", "bass")}
    truth = {}
    for name, events in notes().items():
        truth[name] = []
        for beat, pitch, vel in events:
            start = int(round(beat * BEAT * SR))
            n = min(int(0.4 * SR), total - start)
            sound = {"kick": lambda: _kick(n), "snare": lambda: _snare(n), "hats": lambda: _hat(n),
                     "bass": lambda: _bass(n, 440 * 2 ** ((pitch - 69) / 12))}[name]()
            level = 0.4 if beat < INTRO_BARS * 4 else 1.0
            tracks[name][start:start + n] += sound * vel / 127 * (0.5 if name == "bass" else 0.7) * level
            truth[name].append(start / SR)
    mix = sum(tracks.values())
    master = np.tanh(1.5 * mix) / 1.5 * 0.9                       # a soft limiter, as a mastering chain would
    folder.mkdir(parents=True, exist_ok=True)
    sf.write(folder / "master.wav", np.stack([master, master], axis=1), SR, subtype="PCM_24")
    if stems:
        (folder / "stems").mkdir(exist_ok=True)
        for name, x in tracks.items():
            sf.write(folder / "stems" / f"{name.capitalize()}.wav", np.stack([x, x], axis=1), SR, subtype="FLOAT")
    if midi:
        (folder / "midi").mkdir(exist_ok=True)
        for name, events in notes().items():
            mid = mido.MidiFile(type=1, ticks_per_beat=480)
            track = mido.MidiTrack([mido.MetaMessage("track_name", name=f"{name} clip", time=0),
                                    mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(BPM), time=0)])
            timeline = []
            for beat, pitch, vel in events:
                timeline += [(round(beat * 480), 1, mido.Message("note_on", note=pitch, velocity=vel)),
                             (round((beat + 0.25) * 480), 0, mido.Message("note_off", note=pitch, velocity=0))]
            now = 0
            for tick, _, msg in sorted(timeline, key=lambda e: (e[0], e[1])):
                track.append(msg.copy(time=tick - now))
                now = tick
            mid.tracks.append(track)
            mid.save(folder / "midi" / f"{name.capitalize()}.mid")
    return truth


def true_frames(times: list[float]) -> set[int]:
    return {int(np.floor(t * 60 + 0.5)) for t in times}


def match(found: list, truth: set[int], tolerance: int = 1) -> dict:
    """Detected hits against true frames: share found within ``tolerance`` frames, and extra hits."""
    frames = sorted(int(f) for f, _ in found)
    hit = sum(1 for t in truth if any(abs(f - t) <= tolerance for f in frames))
    extra = sum(1 for f in frames if not any(abs(f - t) <= tolerance for t in truth))
    offsets = [min((f - t for f in frames), key=abs) for t in truth if frames]
    return {"found": hit / len(truth) if truth else 1.0, "extra": extra / max(len(frames), 1),
            "median_offset": float(np.median(offsets)) if offsets else None, "n": len(frames)}
