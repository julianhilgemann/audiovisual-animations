# Handoff: the files Blender reads

**v1 · 2026-10-22.** What one `datapipe gen` run writes, and how Blender picks it up. The pipeline is Blender-only (SPEC v0.6). This is the contract between the audio stages (S1, S2) and everything visual (S3–S7 in [SPEC §15](../../SPEC.md#15-generative-loops)). Code: `src/datapipe/gen/score.py` (standard library only, so Blender imports it as is; verified under Blender 5.2's Python 3.13) and `run.py`.

## Run folder

`work/gen/<yyyymmdd>_<preset>_s<seed>/` (or `…_<midi name>/` for `--midi`), mirrored into **`work/gen/latest/`** after every run: one fixed path for Blender and for listening. `latest/RUN.txt` names the run it holds. On Windows a file another program holds open (a player, an open Blender) cannot be replaced; the run then warns that `latest/` is stale for that file, and the run folder itself is still complete.

| File | Format | What |
|---|---|---|
| `mix.wav` | 48 kHz, stereo, 24-bit PCM, 384,000 samples | the mastered loop: −14 LUFS, ≤ −1 dBTP, loops seamlessly |
| `stems/<track>.wav`, `stems/<bus>.wav` | 48 kHz, stereo, 32-bit float | each track and send bus after its fader, at the mix's gain, not limited (engine.md) |
| `loop_x3.wav` | as mix.wav | the loop three times: listen to the seam |
| `score.json` | JSON | every note, section and curve (below) |
| `score.mid` | MIDI type 1, 480 PPQ | one track per score track, named after it, on its own channel; tempo; sections as markers |
| `frames.csv` | CSV, 480 rows | the score on the video frame grid (below) |
| `preset.toml` | TOML | the preset as it was |
| `manifest.json` | JSON | seed, choices, sources, loudness, seam, balance, versions, timings, warnings |

## Timing contract

| | |
|---|---|
| Frames per beat | `fpb = 3600 / bpm` (30 at 120 BPM) |
| Blender frame of a beat | `frame = 1 + floor(beat × fpb + 0.5)`, wrapped into 1…480: half frames round **up** (Python's `round` would round 22.5 down) |
| Time of a frame | `(frame − 1) / 60` s; its first sample is `(frame − 1) × 800` |
| Loop | frame 481 ≡ frame 1, sample 384,000 ≡ sample 0 |
| Beats | 0-based quarter notes from the loop start, on the 1/480-beat MIDI tick grid |

`Score.frame_of(beat)` implements it; use it rather than re-deriving it.

## `score.json`

```json
{
  "bpm": 120, "bars": 4, "beats_per_bar": 4, "fps": 60, "sample_rate": 48000, "frames": 480,
  "tracks": {
    "kick": [{"beat": 0.0, "dur": 0.25, "pitch": 36, "vel": 124}, ...],
    "lead": [{"beat": 0.0, "dur": 0.4, "pitch": 81, "vel": 118}, ...],
    "riser": []
  },
  "sections": [{"name": "hook", "beat": 0.0}, {"name": "twist", "beat": 8.0},
               {"name": "build", "beat": 10.0}, {"name": "windup", "beat": 14.0}],
  "automation": {"riser": [[10.0, 0.0], [16.0, 1.0]]},
  "meta": {"preset": "neon_house", "seed": 42, "key": "A", "mode": "aeolian",
           "progression": ["i", "iv", "VI", "v"], "violation": "kick_dropout", "choices": {...}, "sounds": {...}}
}
```

- Tracks appear in preset order; a track without notes (the riser) is an empty list.
- Automation curves are breakpoints `[beat, value]`, linear between them, holding the first value before the first point. `Score.curve(name, beat)` evaluates one.
- Hits come from here with exact timing, never from analysing the audio (SPEC §15; docs/sticky-av-shorts.md, Audio-to-visual mapping).

## `frames.csv`

One row per video frame, 480 rows, header on the first line.

| Column | Meaning |
|---|---|
| `frame` | 1…480 (Blender's numbering) |
| `time_s`, `beat` | time of the frame |
| `phase` | loop phase φ = (frame − 1) / 480, for everything cyclic |
| `section` | index into `score.json` sections: 0 hook, 1 twist, 2 build, 3 windup |
| `<track>` | note-on velocity 0–1 on the frame a note starts, else 0: the trigger |
| `<track>_gate` | 1 while a note of the track sounds (notes ringing past the end wrap to the start) |
| `<track>_pitch` | tracks with more than one pitch: the lowest sounding MIDI pitch, held after release |
| `<curve>_curve` | each automation curve, e.g. `riser_curve` 0 → 1 through the build |

Envelopes (wind-up before a hit, decay after) are not in this file: they belong to the control build (S4), which reads `controls.json`.

## `controls.json`

`datapipe short` writes it into the run folder (S3, `src/datapipe/gen/controls.py`): everything a look needs, one value per video frame, independent of any look. Hop 800 samples = one frame, no centring offset; every 0–1 value is normalised on its 5th–95th percentile and followed or smoothed around the loop.

| Key | What |
|---|---|
| `fps`, `frames`, `bpm`, `frames_per_beat` | the grid |
| `sections`, `section`, `phase` | section starts as frames (0-based), the section index and loop phase per frame |
| `curves.<name>` | score automation per frame, e.g. `riser` |
| `tracks.<track>.hits` | `[frame, velocity 0-1]` per note-on (chords: the loudest note), frames 0-based on the timing contract |
| `tracks.<track>.gate`, `.pitch` | as in `frames.csv` |
| `stems.<stem>.loud` | the stem's loudness: RMS per frame in dB (floor 48 dB under its peak), follower 1 frame attack / 7 release |
| `mix.loud`, `mix.bright` | the master's loudness (2 / 12 frames) and spectral centroid (log, smoothed over 8) |

A look turns these into its parameters with `src/datapipe/mapping.py` (hit envelopes, followers, loop closure), as `blender/stem-tunnel` does.

## Blender

`uv run datapipe short` does it all; the Blender side is [blender/stem-tunnel](../../blender/stem-tunnel/README.md), run headless (`blender -b stem_tunnel.blend --python stem_tunnel.py -- --run work/gen/<run> --frames-dir …`):

- **Modulators:** `controls.json`, mapped by `mapping.toml` onto the look's signals and baked one key per frame (481, so the restart is a real key), with every accumulated motion closed on the loop.
- **Sound:** `mix.wav` as a sound strip at frame 1 in the saved `scene_baked.blend` (`sequence_editor.strips`, Blender 5.x API), so it plays in sync when opened. The frames render as PNG; the MP4's audio is muxed by the encoder, not by Blender.
- **Other scenes** read the same files: `sys.path.insert(0, "<repo>/src")`, then `from datapipe import mapping` and `from datapipe.gen.score import Score`.

## MIDI in

`uv run datapipe gen --preset <name> --midi <file.mid>` renders any MIDI file through the preset's sounds instead of composing:

- tracks match preset tracks by **track name** (case-insensitive), else by **MIDI channel** (the n-th preset track is channel n, as `score.mid` writes them); others are ignored and listed in the manifest;
- the tempo comes from the file (it must be on the grid) or the preset; starts snap to 16ths, lengths stay;
- notes past the loop are dropped and counted; markers named like sections move them;
- the riser curve and sections come from the preset, as when composing.

Round trip: `score.mid` from a run, rendered with `--midi` and the same seed, reproduces that run's `mix.wav` bit for bit (verified with `glass_mallets` seed 3, plugins included). Edit the notes in any DAW, keep the track names, export a multitrack MIDI file, render.
