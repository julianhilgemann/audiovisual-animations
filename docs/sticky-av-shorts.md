# Sticky AV Shorts — Spec

Oct 22, 2026 · @Julian

> **In this repo** this is the design of the generative mode ([SPEC §15](../SPEC.md#15-generative-loops)). The audio stages S0–S2 are built: `uv run datapipe gen` composes, renders and masters a loop with DawDreamer ([dawdreamer/](../dawdreamer/README.md)). The audio rules moved to [dawdreamer/specs/audio.md](../dawdreamer/specs/audio.md); the run files Blender and TouchDesigner read are in [dawdreamer/specs/handoff.md](../dawdreamer/specs/handoff.md). S3–S7 are next.

## Purpose and targets

Each run turns one seed into a seamless 8-second vertical loop. The audio is composed first, and every visual event is derived from it.

| Spec | Target |
| --- | --- |
| Format | 1080 × 1920 (9:16), H.264 MP4 |
| Frame rate | 60 fps, 480 frames |
| Length | 8.0 s, fixed; tempo from the grid table under Audio design rules (default 120 BPM = 4 bars) |
| Audio | 48 kHz stereo (384,000 samples, 800 per frame), −14 LUFS integrated, true peak ≤ −1 dBTP |
| Loop | Last frame and last sample flow into the first without a visible or audible seam |
| Determinism | Same seed + same config → identical file on one machine; visually identical across machines |
| Operation | One command, unattended; a preview mode for fast iteration |

Success is measured per upload, with its full parameter vector logged so results can be attributed:

- **Viewed vs. swiped away** share: the hook metric.
- **Average percentage viewed** above 100%: proof that the loop seam works and people rewatch.
- Likes and shares as secondary signals.

## Salience model

A viewer decides in about a second whether to stay. The piece wins by giving eye and ear one predictable thing to lock onto, then rewarding them on schedule.

- **Instant onset.** Full energy in frame 1 and sample 1. No fade, no intro, no logo.
- **Audiovisual binding.** When sound and image change on the same frame, the brain fuses them into one event. Tight sync reads as satisfying; drift of more than a frame or two reads as cheap.
- **Prediction with one violation.** Repetition lets the viewer predict; one surprise per loop recaptures attention. Too regular bores, too random becomes noise.
- **Anticipation and payoff.** A visible wind-up before a hit makes the hit land harder. Offline rendering lets visuals start moving before the sound arrives.
- **The loop seam as reward.** The biggest payoff sits at the loop point, exactly when the thumb would move. A seamless seam hides the restart.
- **Optic flow and looming.** Forward motion toward a vanishing point and expanding shapes grab attention reflexively. The tunnel uses both.
- **Radial symmetry.** Centred, symmetric forms are read instantly and pin the gaze to the middle of the frame.

## Audio design rules

Audio is the master clock. It is composed first, on a grid that lands on whole video frames (8.0 s, 60 fps = 480 frames, 48 kHz = 800 samples per frame; tempos 120, 150, 180 or 240 BPM), and built to loop without a seam: a strong downbeat at sample 0, one 3–5 note motif on a Euclidean rhythm, exactly one violation per loop, a last bar that builds and a downbeat that resolves it, two render passes, never a fade. Glassy plucks, saturated bass, crisp transients over soft pads; bass mono below 120 Hz; −14 LUFS, ≤ −1 dBTP.

The full rules, how the composer implements each one and the measured mix balance: [dawdreamer/specs/audio.md](../dawdreamer/specs/audio.md).

## Visual design rules

The image always moves, centres on one focal point, uses a small saturated palette on near-black, and stays clear of the Shorts interface.

**Motion**

- Nothing is ever static: a slow base motion (camera drift, rotation) runs under all hits.
- Eased curves only; hard cuts only on a downbeat, on purpose.
- 60 fps with light motion blur for smoothness.
- Every cyclic parameter has a period that divides the loop: 480, 240, 120 or 60 frames, or one beat.

**Elements**

- One hero: the tunnel's vanishing point or the kaleidoscope centre.
- Secondary layers (rings, light streaks, particles), each owned by one instrument.
- Radial symmetry with a switchable order (6, 8, 12 segments) as a section marker.
- Depth cues (fog, scale, parallax) to sell forward motion.

**Colour**

- Near-black background so emissive colours pop; 2–3 hues plus a white-hot highlight.
- Complementary or split-complementary pairs: magenta/cyan, orange/teal, violet/lime.
- Hue rotates once per loop or per section, so frame 480 flows into frame 1.
- Saturation and brightness track audio energy; the loudest moment is the brightest.
- Blender's AgX view transform pushes bright neon toward white. Use Standard, or AgX with a punchy look, for candy colours.

**Composition and safe zones**

- The hero sits in the centre. Shorts overlays cover the bottom (title, captions) and the right edge (buttons).
- Those zones carry decoration only. Take the exact overlay mask from a current iPhone screenshot and store it as a PNG for the QA stage.

**Compression**

- YouTube re-encodes hard: fine noise, dense particles and grain turn into blocks.
- Prefer large smooth shapes and gradients; add dither against banding in dark gradients.
- Avoid full-frame high-frequency texture.

**Photosensitivity**

- At most three full-screen flashes per second and no saturated red flashing, following WCAG 2.3.1. The QA stage enforces it.
- Use brightness pulses and scale changes instead of strobes.

## Story in 8 seconds

Each loop is an eight-phrase micro-story: hook, groove, twist, build, and a payoff that is the restart. A phrase is 1 s = 60 frames at any allowed tempo: 2 beats at 120 BPM, 1 bar at 240 BPM. At 180 BPM, map the arc onto its 6 bars.

| Phrase | Time | Audio | Visual | Viewer state |
| --- | --- | --- | --- | --- |
| 1 | 0–1 s | Downbeat impact; full groove at once; motif enters | Hero at full energy, camera already moving, bright palette | Hooked |
| 2–4 | 1–4 s | Groove and motif repeat with small variations | Pulses lock to hits; steady base motion | Predicting, enjoying the sync |
| 5 | 4–5 s | The violation: motif jumps +5 semitones, a new texture, or a kick dropout | Mode change: symmetry order, hue shift, camera twist | Surprised, re-engaged |
| 6–7 | 5–7 s | Build: filter opens, riser starts, hats double | Compression: tunnel narrows, speed and saturation climb | Tension |
| 8 | 7–8 s | Peak tension; the last beat drops out or reverses | Wind-up: zoom in, brightness held back | Expecting release |
| → 1 | 8 s = 0 s | Downbeat resolves the tension | Release burst into the phrase-1 state | Reward; the loop goes unnoticed |

The visuals must end phrase 8 in exactly the state phrase 1 starts from. The control-build stage enforces this by wrapping every curve.

## Audio-to-visual mapping

Discrete hits come from the score with exact timing. Continuous texture comes from stem analysis. The loop phase drives everything cyclic.

| Source | Signal | Visual target | Envelope (frames) |
| --- | --- | --- | --- |
| Kick (score) | Note-on | Hero scale pulse + bloom | 6 wind-up, peak on hit, 12 decay |
| Snare / clap (score) | Note-on | Hue jump or ring emission | 2 attack, 20 decay; ≤ 3 flashes/s |
| Hats (score) | Note-on | Sparkle, fine light streaks | Instant, 4 decay |
| Lead motif (score) | Pitch, velocity | Colour band, vertical position, emission | Pitch → hue band; velocity → brightness |
| Bass (stem) | RMS envelope | Tunnel radius, geometry displacement | Follower: 1 attack, 7 release |
| Mix (analysis) | Spectral centroid | Saturation | Smoothed over 8 |
| Mix (analysis) | RMS | Camera speed above a base floor | Smoothed over 12 |
| Sections (score) | Markers | Symmetry order, palette, camera mode | Switch on downbeat, eased over one beat |
| Riser (score automation) | 0 → 1 curve | Zoom, tunnel narrowing | Same curve, eased |
| Loop phase | φ = (frame − 1) / 480 | Hue rotation, camera path, noise seeds on a circle | Periodic by construction |

**Anticipation.** The renderer knows the future. Each hit starts its wind-up 4–8 frames before the sound and overshoots slightly after, as in classic animation.

**Natural correspondences.** Map the way people already hear and see: higher pitch → higher and brighter, louder → bigger, rougher timbre → sharper geometry.

## Pipeline and signal flow

Audio is rendered first, and Blender only reads finished control curves. Every stage hands the next a file, so each runs and caches on its own.

&#91;embedded content: pipeline · 8 stages, 2 side branches\]

The score feeds two branches: exact hit times go straight to the control build, while analysis only adds continuous texture. The finished mix skips Blender entirely and is muxed unchanged in the encode stage.

**Design principles**

- Deterministic: seed + config → identical output.
- Audio-first: the score is the single source of truth for timing.
- Offline look-ahead: visuals may anticipate any event.
- File boundaries between stages: any stage can rerun alone.

## Stage specs

Eight stages, each a standalone script with file inputs and outputs, so any stage can be rerun alone.

### S0 · Config and seed *(built: `datapipe gen`)*

- Input: `dawdreamer/presets/<name>.toml` ([format](../dawdreamer/specs/presets.md)) and `--seed`.
- Every random choice comes from a named RNG stream derived from (seed, stream name): `audio` (and `audio/<track>`, `sound/<slot>`), later `visual`, `camera`. Changing one stream never reshuffles another.
- Output: `work/gen/<run_id>/manifest.json` with seed, preset, resolved choices, sources, loudness, tool versions and git commit.

### S1 · Compose or ingest MIDI *(built: `src/datapipe/gen/compose.py`)*

Two entry modes write the same `score.json`.

- **Generate:** a pattern generator per track (scale, motif, Euclidean rhythms, section plan, automation curves such as the riser).
- **Ingest:** a `.mid` from Octatrack, Ableton or REAPER (`datapipe gen --midi`), parsed with `mido`, starts quantised to 16ths, tracks mapped to the preset's tracks by name, else by channel.
- Validation: whole bars only, all events inside the loop, sections cover every bar.
- Also writes `score.mid` (multitrack) for inspection in any DAW.

### S2 · Audio render *(built: `src/datapipe/gen/engine.py`, `master.py`; [engine spec](../dawdreamer/specs/engine.md))*

- A DawDreamer graph built from the preset: per track an instrument (Faust, or a VST3 with parameters by name and an optional saved state, falling back to Faust), an insert chain and send levels; return buses; a master chain fed at −18 LUFS.
- Two passes rendered, the second kept, so tails wrap into the head.
- Each track's and bus's output is recorded to `stems/`.
- Loudness: gain to −14 LUFS (`pyloudnorm`), then a circular lookahead limiter on the 4× oversampled true peak to −1 dBTP. Cross-check with ffmpeg's `ebur128` in S7.
- Output: `mix.wav` (48 kHz, 24-bit), `stems/*.wav` (32-bit float), plus `frames.csv`, the score on the frame grid.
- **Bypass:** an external bounce (`mix.wav` + its `.mid`) skips generation and rendering and enters at S3 *(not built yet; its MIDI alone already renders through `--midi`)*.

### S3 · Analysis

- Per stem and mix, hop = 800 samples = exactly one video frame, no centring offset.
- Features: RMS, onset strength, spectral centroid, band energies (sub < 120 Hz, low, mid, high > 4 kHz).
- Envelope followers with attack and release in frames; each feature normalised to 0–1 using its 5th–95th percentile.
- Wrap-aware: the tail is prepended before smoothing, so frame 1 has the right history.
- Output: `features.npz`, 480 rows.

### S4 · Control build (modulation matrix)

- Reads `score.json`, `features.npz`, `mapping.yaml` and `param_map.yaml`.
- Score hits become envelopes (wind-up, peak, decay); features become scaled curves; the loop phase becomes periodic curves.
- Contributions per target are summed with weights and clamped to each parameter's safe range.
- Envelopes that run past frame 480 are added back from frame 1.
- Flash limiter: luminance-driving pulses capped at 3 per second.
- Output: `controls.json`, 480 values per logical parameter.

### S5 · Blender ingest and render

```bash
blender -b scene.blend --addons kaleido,tunnel_tools -y \
  -P pipeline/blender_ingest.py -- --run runs/<run_id>
```

- Applies render settings and static parameters from the preset.
- Bakes `controls.json` into keyframes, one per frame, linear interpolation. Keyframes, not a frame handler, so motion blur sees correct sub-frame values.
- Saves `scene_baked.blend` for debugging: open it, scrub, see exactly what rendered.
- Renders `frames/0001.png … 0480.png`.

### S6 · Encode

```bash
ffmpeg -y -framerate 60 -i frames/%04d.png -i mix.wav \
  -vf scale=out_color_matrix=bt709:out_range=tv \
  -c:v libx264 -profile:v high -preset slow -crf 16 \
  -pix_fmt yuv420p -g 30 -bf 2 \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 \
  -c:a aac -b:a 320k -ar 48000 \
  -movflags +faststart -shortest short.mp4
```

- The `scale` filter converts with the BT.709 matrix. Without it, ffmpeg converts RGB with BT.601 while the file is tagged 709, and colours shift.
- `+faststart` puts the index first, so the file plays instantly on the phone.
- Seam preview: `ffmpeg -stream_loop 2 -i short.mp4 -c copy loop_check.mp4`.

### S7 · QA gates

A run is publishable only if every gate passes; results go to `qa.json`.

| Gate | Check | Pass |
| --- | --- | --- |
| Length | ffprobe frames and samples | 480 frames, 384,000 samples |
| Seam | Frame 480 vs frame 1; first vs last audio samples | Below a difference threshold |
| Sync | Kick onsets vs hero brightness peaks (cross-correlation) | Offset ≤ 1 frame |
| Loudness | ffmpeg `ebur128` | −14 ± 1 LUFS, ≤ −1 dBTP |
| Flashes | Frame-to-frame luminance jumps | ≤ 3 per second |
| Safe zone | Hero brightness inside the overlay mask | Below a threshold |
| File | Codec, pixel format, fps, colour tags | Matches S6 spec |

## Blender parameter interface

The pipeline never touches Blender paths directly. It talks to logical parameter names, and `param_map.yaml` translates them into data paths on the owning datablock.

```yaml
tunnel.speed:
  owner: objects["Tunnel"]
  path: modifiers["GeometryNodes"]["Socket_3"]   # GN input by identifier
  range: [0.2, 4.0]
hero.pulse:
  owner: objects["Tunnel"]
  path: '["pulse"]'                                # custom property
  range: [0.0, 1.0]
neon.emission:
  owner: materials["Neon"].node_tree              # shader keys live on the node tree
  path: nodes["Emission"].inputs["Strength"].default_value
  range: [2.0, 40.0]
kaleido.segments:
  owner: scenes["Scene"]
  path: kaleido.segments                          # add-on PropertyGroup
  range: [6, 12]
  interpolation: constant                         # switches only on downbeats
```

**Discovery.** `introspect.py` dumps every animatable property into `params_catalog.json`: object and custom properties, Geometry Nodes inputs (identifier → display name via the node group's interface), material node inputs, and add-on property groups. `param_map.yaml` is written against that catalogue. For a single field, *Preferences → Interface → Python Tooltips* shows its path on hover.

**Baking.** For each mapped parameter and frame: resolve the owner, set the value, `owner.keyframe_insert(path, frame=f)`. New-keyframe interpolation is set to linear first. This uses only the stable keyframe API, which matters because Blender's lower-level animation API has changed across recent versions.

**Static parameters** (palette, scene variant, base speed) are set once and not keyed.

**Add-on caveats**

- Properties with `update=` callbacks do not fire when animated by keyframes. Such an add-on needs either Geometry Nodes inputs or a `frame_change_post` handler that calls its update.
- Add-ons are enabled per run with `--addons`. Extensions installed in Blender 4.2+ use the module name `bl_ext.<repo>.<name>`.
- Python-expression drivers run only with auto-run scripts enabled, hence `-y` on the command line.

**Render settings set by the script:** engine, samples, resolution, fps, frame range, view transform and look, dither, motion blur, output format, and compositor glare for bloom. The engine identifier differs between Blender 4.x and 5.x, so it comes from the preset.

## Data contracts and repo layout

Three JSON files carry everything between stages; each run lives in its own folder, so any result can be traced and re-rendered. The built format of `score.json`, plus `frames.csv` and the run folder, is specified in [dawdreamer/specs/handoff.md](../dawdreamer/specs/handoff.md).

**`score.json`** (beats are 0-based, in quarter notes)

```json
{
  "bpm": 120, "bars": 4, "beats_per_bar": 4,
  "fps": 60, "sample_rate": 48000, "frames": 480,
  "tracks": {
    "kick": [{"beat": 0.0, "dur": 0.25, "pitch": 36, "vel": 120}],
    "lead": [{"beat": 0.0, "dur": 0.2, "pitch": 62, "vel": 100}]
  },
  "sections": [
    {"name": "hook", "beat": 0}, {"name": "twist", "beat": 8},
    {"name": "build", "beat": 10}, {"name": "windup", "beat": 14}
  ],
  "automation": {"riser": [[10.0, 0.0], [16.0, 1.0]]}
}
```

**`controls.json`**: `{"fps": 60, "frames": 480, "params": {"tunnel.speed": [600 floats], …}}`

**`manifest.json`**: seed, preset, resolved parameters, git commit, Blender and DawDreamer versions, per-stage durations, QA result.

**Timing contract**

- Frames per beat: `fpb = 3600 / BPM` (30 at 120 BPM).
- Blender frame of a beat: `frame = 1 + round(beat × fpb)` (frames are 1-based), half frames rounding up.
- Time of a frame: `(frame − 1) / 60` s. First sample of a frame: `(frame − 1) × 800`.
- Loop: frame 481 ≡ frame 1, sample 384,000 ≡ sample 0.

**Repo layout** (inside the `audiovisual-animations` repo, next to the song pipeline)

```
dawdreamer/                 # audio: specs/, presets/*.toml, faust/*.dsp, plugins.toml, states/
src/datapipe/gen/           # compose.py (S1)  engine.py, master.py (S2)  score.py  plugins.py  run.py
  (next)                    # analyze (S3), controls (S4), blender ingest (S5), encode (S6), qa (S7)
config/                     # pipeline.toml ([gen], tool paths per OS); mapping.toml, param_map.toml later
scenes/neon_tunnel.blend    # templates
work/gen/<yyyymmdd>_<preset>_s<seed>/
  manifest.json  preset.toml  score.json  score.mid  frames.csv
  mix.wav  loop_x3.wav  stems/          # built
  features.npz  controls.json  scene_baked.blend  frames/  short.mp4  qa.json   # later
work/gen/latest/            # the newest run, the fixed path for TouchDesigner and Blender
```

Presets and configs are TOML, like the rest of the repo; YAML in the examples above reads the same.

## CLI, performance and fast export

One command produces a finished MP4; caching makes reruns cost only the stages whose inputs changed.

```bash
# built: the audio of one loop, or a batch of candidates
uv run datapipe gen --preset neon_house --seed 42 --play
uv run datapipe gen --preset neon_house --seeds 1-20
uv run datapipe gen --preset neon_house --midi bounce.mid      # notes from Ableton or Octatrack

# planned: the whole short
uv run datapipe short --preset neon_house --seed 42
uv run datapipe short --run work/gen/20261022_neon_house_s42 --from s4
uv run datapipe short --preset kaleido --audio bounce.wav --midi bounce.mid
```

**Caching.** Each stage hashes its inputs (files + config section). Unchanged inputs mean the stage is skipped, so tweaking `mapping.yaml` reruns S4–S7 only.

**Speed levers**

- Render time dominates; the audio stages take seconds. Log per-stage duration in the manifest and optimise from that.
- EEVEE with low samples: 16–32 for finals, 4–8 for preview.
- Preview mode: 50% resolution, same 60 fps (so timing stays identical), ffmpeg `-preset ultrafast -crf 23`.
- PNG compression at 0–15% cuts frame write time.
- Split frame ranges across machines (`-s 1 -e 300`, `-s 301 -e 600`). Several processes on one GPU rarely help.

**Fast export mode.** Blender writes the MP4 itself, then ffmpeg only adds the audio with `-c:v copy`. Fewer files and no separate encode, at the cost of encoder control. Blender's video-output settings have moved between versions, so this mode is pinned to the Blender version in the preset.

**Delivery.** Output lands as `out/<date>_<preset>_s<seed>.mp4` with a sidecar `.json` and a thumbnail from the phrase-5 twist. A synced folder (iCloud Drive) puts it on the iPhone within seconds for a test watch on the real screen and speaker.

## Cross-platform setup (Windows + macOS)

Python is the only glue, everything OS-specific lives in one machine file, and no stage assumes a shell. No Docker: containers on macOS get no GPU, and Mac plugins don't load in a Linux container.

| Piece | How it is pinned | Notes |
| --- | --- | --- |
| Python + packages | `uv` with `pyproject.toml`, `uv.lock`, `.python-version` | One lockfile resolves for both OSes; Python 3.12, which DawDreamer 0.9 ships wheels for (macOS arm64/x86_64, Windows x64). PyAV is capped below 16 on macOS, whose newer wheels need macOS 14 |
| ffmpeg | PyAV (`av`), FFmpeg libraries inside the venv | `imageio-ffmpeg` adds a CLI binary if one is ever needed |
| Blender | 5.2.2 LTS everywhere; path per OS in `config/pipeline.toml`, overridable in `config/machine.toml` | Same version everywhere; only the GPU backend differs |
| Blender add-ons | Zips in `blender/addons/`, installed by a setup command | Never installed by hand |
| Synths and effects | Faust built-ins first; VST3 only, no AU; fetched per OS into `dawdreamer/plugins/` by `datapipe plugins fetch` (sha256-checked); versions logged in the manifest | Plugin must ship VST3 for both OSes |
| Sound states | Parameters by display value in the preset (portable); binary states in `dawdreamer/states/` | Test once that a Mac-saved state loads on Windows |

**Free plugins with VST3 on Windows and macOS** (chosen 2026-10-22; all render headless in DawDreamer on macOS)

- RipplerX (open source): physically modelled mallets, the glassy plucks and bells.
- Dexed (open source): FM keys, bells and plucks.
- JC303 (open source): TB-303 bass.
- Dragonfly Reverb (open source): plate and hall.
- Valhalla Supermassive (freeware, installed by hand): huge reverbs and delays.
- Not chosen: Surge XT (very good, but 180 MB plus a content folder), Vital (needs an account to download), TAL-NoiseMaker (installer only). The built-in Faust instruments cover kick, clap, hats, bass, pads, plucks, riser and impact without any plugin.

**`config/machine.toml`** (gitignored; `config/machine.example.toml` is committed) overrides any key of `config/pipeline.toml` for one machine. The defaults per OS already cover both machines:

```toml
[paths.windows]
blender = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
[paths.macos]
blender = "/Applications/Blender.app/Contents/MacOS/Blender"
```

System VST3 folders (for plugins installed by hand) are looked up per OS: `C:\Program Files\Common Files\VST3`, `/Library/Audio/Plug-Ins/VST3`.

**Code rules**

- `pathlib` for every path; external tools via `subprocess.run([...])` with argument lists. The bash lines in this spec are illustrations only.
- Setup and orchestration in Python: `uv run datapipe doctor`, `uv run datapipe gen --seed 42`, `uv run datapipe plugins fetch`.
- No `:` in file names (run IDs like `2026-10-22_neon_tunnel_s42`); keep paths short for Windows' 260-character limit.
- `if __name__ == "__main__":` in every entry script, because Windows starts worker processes fresh.
- `.gitattributes` with `* text=auto`, so line endings never flip.

**`datapipe doctor`** checks the Python libraries, PyAV, DawDreamer (every Faust DSP compiles, a one-second render), the Blender version, paths, plugins and GPU. A new machine is ready when every required line passes. A one-second test video render joins it with S5.

**Determinism** is bit-exact only on one machine; Metal and NVIDIA renders differ by tiny pixel amounts.

## Risks and open decisions

The biggest risks are tooling drift and platform policy, not rendering; each has a cheap mitigation.

| Risk | Mitigation |
| --- | --- |
| VST plugins misbehave headless in DawDreamer | Tested 2026-10-22: all six chosen plugins load and render headless on macOS. Every plugin slot has a Faust fallback; versions and checksums pinned in `dawdreamer/plugins.toml`. Windows still to test |
| Blender API drift (engine ids, animation API, video output) | Pin one Blender version per preset; smoke-test on every upgrade |
| Add-on properties with update callbacks don't animate | Expose them as Geometry Nodes inputs, or call the update from a frame handler |
| YouTube treats templated, repetitive Shorts as inauthentic content and demonetises it | Curation gate: render many, publish few; vary concept per series; keep a hand-made audio element |
| Photosensitivity | The QA flash gate blocks publishing |
| Compression artefacts on YouTube | Upload a test early; tune particle density and dither |

Open decisions:

- [ ] Tempo on the 8-second grid: 120 (default), 180 or 240 BPM
- [ ] v1 audio source: Octatrack harvest, Ableton stems, or generated *(generated and MIDI-ingest paths built 2026-10-22)*
- [x] Synth under DawDreamer: Faust built-ins as the core; RipplerX, Dexed, JC303 and Dragonfly as optional plugins (all pass the headless test)
- [x] Blender version to pin: 5.2.2 LTS (SPEC §8)
- [ ] Shorts overlay mask from a current iPhone screenshot
- [ ] Publishing: manual upload or YouTube Data API

Sources: [YouTube monetisation update on inauthentic content (Gulf News)](https://gulfnews.com/technology/youtube-updates-monetisation-policies-ai-and-repetitive-content-ban-begins-july-15-1.500192660) · [DawDreamer](https://GitHub.com/DBraun/DawDreamer)
