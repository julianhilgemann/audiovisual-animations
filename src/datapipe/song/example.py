"""`datapipe example <method>`: a generated loop exported the way a DAW exports a song, into the method's inbox.

It shows the folder layout each method expects (SPEC §16.2) and gives material whose hits are known (the score),
for trying a method or measuring its detection. The loop is repeated, the stems are the run's tracks and send
buses (like an Ableton "All Individual Tracks" export, returns included), and each MIDI track is its own file.
"""

import shutil
from pathlib import Path

import mido
import numpy as np
import soundfile as sf

from ..config import ROOT, load_config
from ..gen.run import generate
from ..gen.score import PPQ, Score

SONG_TOML = """\
# song.toml: optional settings for this song (SPEC §16.2). Every line is optional; delete what you don't need.

# bpm = 120                 # stems, master: fixes the beat tracker's tempo. midi reads the tempo from the MIDI
# loop = true               # close the picture's motion so a replay continues without a jump
# start = 0.0               # seconds: trim the start of every file
# length = 24.0             # seconds: trim to this length

# [roles]                   # role = file name, for files whose names don't say what they are
# kick = "Drum Rack 1"      # roles: kick snare clap hats bass lead pad riser impact drums
# bass = "808 Sub"

# [drums]                   # midi: split one drum MIDI file into roles by note number (General MIDI defaults)
# file = "Drums"
# kick = [36]
# snare = [38, 40]

# [sections]                # the bar (1-based) where each section starts; else they are found in the master
# intro = 1
# build = 9
# drop = 17
"""


def export(method: str, preset: str | None = None, seed: int = 1, repeat: int = 3, use_plugins: bool = True,
           dest: Path | None = None, work: Path | None = None) -> Path:
    """Generate a loop (into ``work``, default work/gen/) and write it into inbox/<method>/ (or ``dest``) as a
    song; returns the file (master) or folder. The folder's score.json is the generated score: the true hits."""
    cfg = load_config()
    preset = preset or cfg["gen"]["preset"]
    run, _ = generate(preset, seed, use_plugins=use_plugins, latest=False, out=work)
    name = f"example_{preset}_s{seed}"
    inbox = Path(dest) if dest else ROOT / cfg["methods"][method]["inbox"]
    mix, sr = sf.read(run / "mix.wav", always_2d=True)
    if method == "master":
        inbox.mkdir(parents=True, exist_ok=True)
        out = inbox / f"{name}.wav"
        sf.write(out, np.tile(mix, (repeat, 1)), sr, subtype="PCM_24")
        return out

    folder = inbox / name
    (folder / "stems").mkdir(parents=True, exist_ok=True)
    sf.write(folder / "master.wav", np.tile(mix, (repeat, 1)), sr, subtype="PCM_24")
    for wav in sorted((run / "stems").glob("*.wav")):
        x, _ = sf.read(wav, always_2d=True)
        sf.write(folder / "stems" / f"{wav.stem.capitalize()}.wav", np.tile(x, (repeat, 1)), sr, subtype="FLOAT")
    if not (folder / "song.toml").exists():
        (folder / "song.toml").write_text(SONG_TOML, encoding="utf-8")
    shutil.copyfile(run / "score.json", folder / "score.json")         # the truth, for measuring detection
    if method == "midi":
        (folder / "midi").mkdir(exist_ok=True)
        write_midi(Score.load(run / "score.json"), folder / "midi", repeat)
    return folder


def write_midi(score: Score, folder: Path, repeat: int) -> None:
    """One .mid per track, the loop repeated, as a DAW exports a consolidated clip (notes from the song start)."""
    for name, notes in score.tracks.items():
        if not notes:
            continue
        mid = mido.MidiFile(type=1, ticks_per_beat=PPQ)
        track = mido.MidiTrack([mido.MetaMessage("track_name", name=name, time=0),
                                mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(score.bpm), time=0),
                                mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0)])
        events = []
        for lap in range(repeat):
            offset = lap * score.total_beats
            for n in notes:
                on, off = round((offset + n.beat) * PPQ), round((offset + n.beat + n.dur) * PPQ)
                events += [(on, 1, mido.Message("note_on", note=n.pitch, velocity=n.vel)),
                           (max(off, on + 1), 0, mido.Message("note_off", note=n.pitch, velocity=0))]
        now = 0
        for tick, _, msg in sorted(events, key=lambda e: (e[0], e[1])):
            track.append(msg.copy(time=tick - now))
            now = tick
        mid.tracks.append(track)
        mid.save(folder / f"{name.capitalize()}.mid")
