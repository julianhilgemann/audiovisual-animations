# Handoff: the files Blender and TouchDesigner read

**v1 · 2026-10-22.** What one `datapipe gen` run writes, and how the other tools pick it up. This is the contract between the audio stages (S1, S2) and everything visual (S3–S7 in [SPEC §15](../../SPEC.md#15-generative-loops)). Code: `src/datapipe/gen/score.py` (standard library only, so Blender and TouchDesigner import it as is; verified under Blender 5.2's Python 3.13 and Python 3.11) and `run.py`.

## Run folder

`work/gen/<yyyymmdd>_<preset>_s<seed>/` (or `…_<midi name>/` for `--midi`), mirrored into **`work/gen/latest/`** after every run: one fixed path to point TouchDesigner and Blender at. `latest/RUN.txt` names the run it holds. On Windows a file another program holds open cannot be replaced; the run then warns that `latest/` is stale for that file, and the run folder itself is still complete.

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

Envelopes (wind-up before a hit, decay after) are not in this file: they belong to the control build (S4), which reads `score.json` and the stem analysis.

## TouchDesigner

The intended recipe (not yet built in a project):

1. **Audio File In CHOP** → `work/gen/latest/mix.wav`, play mode locked to the timeline; the project runs at 60 fps with a 480-frame range.
2. **File In DAT** → `work/gen/latest/frames.csv` (CSV) → **DAT to CHOP** with the first row as names: one channel per column, 480 samples. The value for the current frame is sample `frame − 1`, e.g. `op('frames')['kick'][me.time.frame - 1]` in an expression. Untested in TouchDesigner so far: check the operator parameters with Envoy's `describe_op_type` when building it.
3. Optional: an Audio File In per `stems/*.wav` for per-instrument analysis CHOPs.
4. Reload after each `datapipe gen`: the paths stay the same. On Windows, TouchDesigner holding `mix.wav` open can block the copy into `latest/` (the run warns).

The shared `av_rig` module in `projects/00-custom-modules/` already turns audio and MIDI into named channels; a `frames.csv` source for it is the natural next step.

## Blender

- **Sound:** a sound strip with `mix.wav` at frame 1 in the scene's sequencer (`sequence_editor.strips`, Blender 5.x API), so the render muxes it (SPEC §5.7).
- **Hits and curves:** `score.json` or `frames.csv`, baked to keyframes one per frame by the S5 ingest (docs/sticky-av-shorts.md, Blender parameter interface). From Blender's Python: `sys.path.insert(0, "<repo>/src")`, then `from datapipe.gen.score import Score`.

## MIDI in

`uv run datapipe gen --preset <name> --midi <file.mid>` renders any MIDI file through the preset's sounds instead of composing:

- tracks match preset tracks by **track name** (case-insensitive), else by **MIDI channel** (the n-th preset track is channel n, as `score.mid` writes them); others are ignored and listed in the manifest;
- the tempo comes from the file (it must be on the grid) or the preset; starts snap to 16ths, lengths stay;
- notes past the loop are dropped and counted; markers named like sections move them;
- the riser curve and sections come from the preset, as when composing.

Round trip: `score.mid` from a run, rendered with `--midi` and the same seed, reproduces that run's `mix.wav` bit for bit (verified with `glass_mallets` seed 3, plugins included). Edit the notes in any DAW, keep the track names, export a multitrack MIDI file, render.
