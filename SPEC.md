# Datapipe — Audio-reactive Blender Shorts

**Spec v0.7 · 2026-10-22 · Status: draft for review**
*v0.7: A generated loop becomes a finished Short in one command, `datapipe short` (§15, G2–G4): controls from the stems and the score, the Blender project `blender/stem-tunnel` (the neon lines tunnel, loop-closed), a PyAV encode to the Shorts settings and the automatic S7 checks, including a full-frame flash gate. v0.6: The pipeline is Blender-only, because Blender can be driven entirely from code with every file at hand. TouchDesigner stays in the repo for the standalone projects (`projects/`) but no stage depends on it: reactivity is tuned in a tab of the Blender panel (§6.1, P6), and a generated run is read by Blender alone (§15, G2). v0.5: A second mode, generative loops (§15): DawDreamer composes and renders an 8-second loop first and the visuals follow its score; its audio engine (phase G1) is built. Tool paths per OS, so the repo runs on Windows and macOS (§8). v0.4: The repo is on GitHub and also holds standalone TouchDesigner projects under `projects/` (§4). v0.3: Phase 0 done; FFmpeg comes from PyAV inside the venv instead of a system install. v0.2: TouchDesigner becomes the reactivity-tuning tool (§6).*

Drop an audio or video file into a folder → the pipeline analyzes its rhythm and spectrum → a Blender scene is animated from those features plus a hand-tuned look preset → one headless render produces a finished YouTube Short (video + audio) with no further editing.

---

## 1. Goals and non-goals

**Goals**

- **Zero post-production.** One render pass writes the upload-ready MP4: picture, synced audio, fades, correct length and encoding. No editing app, no merging, no re-encode.
- **Audio-reactive.** Transients (kick, snare, hats), frequency bands, loudness, beat/bar phase and song structure drive the animation, frame-accurately at 60 fps.
- **Story, not just reactivity.** The song's structure (build, breakdown, drop) drives a retention arc: hook → build → tension → payoff → seamless loop back to frame 1.
- **Tweak by taste.** Reactivity, shape and look are tuned in a Blender side panel, against the renderer that makes the final picture. Each saves a small file (a mapping recipe or a preset) that the pipeline applies to every new song.
- **Two length modes.** *Full* uses the audio's own length (up to a cap). *Fixed* uses a set length (e.g. 30 s) with an automatically chosen excerpt and an audio fade-out.
- **Reproducible.** Every output can be re-rendered bit-for-bit from its job record (inputs, preset, mapping, versions).

**Non-goals (v1)**

- Auto-uploading to YouTube (possible later via the YouTube Data API).
- Real-time / live VJ performance. Rendering is offline; only the *tweak preview* is real-time.
- Licensing music. Rights to dropped-in songs are the user's responsibility. (Generating music is the separate generative mode, §15.)
- Using the video track of a dropped MP4. Only its audio is used.

---

## 2. Current state (measured 2026-10-19)

| Item | Value |
|---|---|
| Template scene | `scenes/neon_tunnel.blend`. Neon tunnel with 3 meshes (`Tunnel_Walls`, `Tunnel_Portals`, `Tunnel_Outer`), camera `NeonCam`, one procedural emission material `NeonLine`, compositor with 2 Glare nodes. |
| Animation today | Driver formulas based on the frame number: camera travels −Z at π/60 per frame, camera spins +0.25°/frame, outer shell spins −0.25°/frame, material phase `(frame-1)/360`. |
| Rhythm facts | Portals are exactly **π units apart** (49 rings, z −144.5 … 6.3). At the current speed the camera passes **1 portal per second**. The full state repeats after **360 frames** (verified: frame 361 matches frame 1, mean pixel difference 0.0004%). |
| Render settings | EEVEE, 2160×3840, 60 fps, 48 samples, no shadows or ray tracing. Export is already set up for YouTube (see §5.8). |
| Hardware | NVIDIA RTX 5060 Laptop GPU, 8 GB (Blender runs on it, not the AMD iGPU). |
| Measured speed | **~0.98 s/frame** at 4K, render only (first frame 2.1 s for shader compile). No thermal throttling over 360 frames (56–69 °C). GPU averaged 66% load, so part of each frame is CPU-bound. H.264 4K encode on CPU took ~0.16 s/frame. |
| Reference render | `reference/neon_tunnel_5x.mp4`: 30 s, the 6 s loop repeated 5×, 423 MB. |
| Software | Blender **5.2.2 LTS** (bundled Python 3.13.13, numpy 2.3.4). **TouchDesigner 2025.32820** (standalone projects only, not the pipeline). System Python 3.14.5 (untouched), Git, Node. **Pipeline env:** uv 0.13.1 (winget, user scope) with a uv-managed Python 3.12.15 in `.venv`. FFmpeg comes from PyAV inside the venv; there is no system ffmpeg. `uv run datapipe doctor` checks the whole toolchain. |
| Blender bridge | The Blender Lab MCP add-on listens on `localhost:9876` and runs Python sent to it. This lets Claude (or any script) tweak the open scene live. Helper: `tools/blender_bridge.py`. It also works with a headless server (`blender -b <file> --online-mode -c blender_mcp`). |
| Repo | Git, branch `main`, pushed to the public GitHub repo `julianhilgemann/audiovisual-animations`. Agent context lives in `CLAUDE.md`. |
| Second machine | MacBook, Apple M1, macOS 13.5: Blender 5.2.2 LTS, TouchDesigner 2023.12230, uv with Python 3.12.13. The generative audio engine (§15) was built and verified here (2026-10-22). |

---

## 3. End-to-end flow

```
 inbox/                          work/<job-id>/                                    output/
┌──────────────┐  1 ingest   ┌─────────────────┐  2 analyze  ┌───────────────┐
│ song.mp4     │────────────▶│ audio_full.wav  │────────────▶│ features.json │
│ song.toml ?  │  (PyAV)     │ (48 kHz stereo) │  (librosa)  │ report.png    │
└──────────────┘             └─────────────────┘             └──────┬────────┘
                                                                    │ 3 window + arc
 presets/<look>.json ──┐                                            ▼
 config/mappings/*.toml┼──────────────────────────────▶ 4 map ┌───────────────┐
 config/params.toml ───┘                                      │ tracks.json   │  per-frame values
                                                              │ audio_final.wav│ trimmed + faded
                                                              └──────┬────────┘
                                                                     │ 5 build + render (Blender -b)
                                                                     ▼
                                    scenes/neon_tunnel.blend ──▶ ┌──────────────────────────┐
                                                                 │ <date>_<song>_<look>.mp4 │
                                                                 └──────────────────────────┘
```

1. **Ingest.** Decode any audio or video to `audio_full.wav` (48 kHz stereo, PCM), then hash it.
2. **Analyze.** Compute features on a 60 fps grid (hop of 800 samples, exactly one sample block per video frame). Detect beats, bars, transients and sections. Write `features.json` and `report.png`.
3. **Window and arc.** Pick the excerpt (fixed mode) or use the full length. Locate hook, build, breakdown and drop, then derive the arc envelopes.
4. **Map.** Combine features, mapping config and preset base values into per-frame parameter tracks. Integrate speed into travel, close the loop, and enforce safety limits. Write `audio_final.wav` (trimmed, faded): exactly the audio the render will use.
5. **Build and render.** Headless Blender opens the template, applies the preset's static parameters, bakes the tracks as keyframes, adds `audio_final.wav` to the video editor's sound track, and renders directly to MP4 with audio.

Steps 1–4 run in the pipeline's Python environment. Step 5 runs inside Blender. The mapping math (step 4) is **numpy-only**, so the same module also runs inside Blender, for the bake and for the reactivity tab's live re-bake.

The two hand-tuned inputs both come from the Blender side panel (§6): `config/mappings/*.toml` from its reactivity tab and `presets/*.json` from its shape and look tabs. The panel doesn't have to be open to render.

---

## 4. Folder structure (target)

Created 2026-10-19. Folders that are still empty hold a `.gitkeep`.

```
datapipe/
├─ SPEC.md
├─ CLAUDE.md                    # agent context for Claude Code
├─ README.md                    # human quick start
├─ .gitignore / .gitattributes
├─ pyproject.toml               # uv project, Python 3.12 pinned (Phase 0, still open)
├─ config/
│  ├─ pipeline.toml             # global defaults: paths (tools per OS), fps, profiles, length rules, [gen]
│  ├─ machine.example.toml      # copy to machine.toml (gitignored) to override paths on one machine
│  ├─ params.toml               # parameter schema (single source of truth, see §5.6)
│  └─ mappings/
│     └─ default.toml           # feature → parameter mapping (see §5.5)
├─ presets/
│  └─ neon_default.json         # look/shape values, written by the Blender side panel
├─ scenes/
│  └─ neon_tunnel.blend         # template scene with Director rig (Phase 1)
├─ inbox/                       # ← DROP FILES HERE (.mp4 .mov .wav .mp3 .flac .m4a .ogg)
│  └─ failed/                   # inputs that failed, plus <name>.error.txt
├─ work/<job-id>/               # per-job intermediates, kept for re-renders and debugging
├─ cache/<audio-hash>/          # analysis cache (re-render with a new preset skips analysis)
├─ output/                      # finished MP4s
├─ archive/                     # processed inputs
├─ reference/
│  └─ neon_tunnel_5x.mp4
├─ src/datapipe/                # pipeline package (runs in the uv environment)
│  ├─ cli.py                    # `datapipe run | watch | analyze | rerender | preview`
│  ├─ ingest.py                 # PyAV decode, trim, fades, optional loudness normalize
│  ├─ analysis.py               # librosa: bands, onsets, beats, bars, sections
│  ├─ window.py                 # fixed-length excerpt selection
│  ├─ arc.py                    # song structure → story arc envelopes
│  ├─ mapping.py                # NUMPY-ONLY, also imported by Blender
│  ├─ jobs.py                   # job folders, sidecars, hashing, job.json
│  ├─ watch.py                  # inbox polling
│  └─ gen/                      # generative loops (§15): compose, engine, master, score, plugins, run
├─ dawdreamer/                  # generative audio (§15): specs, presets, Faust DSP, plugin manifest, states
├─ docs/
│  └─ sticky-av-shorts.md       # design of the generative mode (§15)
├─ blender/
│  ├─ build_and_render.py       # headless entry point (step 5)
│  ├─ rig.py                    # creates or migrates the Director rig in a template
│  └─ addon_datapipe/           # the side panel: reactivity, shape and look (see §6)
├─ projects/                    # standalone TouchDesigner projects, not part of the pipeline (see projects/README.md)
├─ tools/
│  └─ blender_bridge.py         # send Python to a running Blender (localhost:9876)
└─ tests/
   ├─ fixtures/                 # synthetic click tracks
   └─ test_*.py
```

**Job ID:** `<yyyymmdd-HHMMSS>_<song-slug>`. A job folder contains `source.*`, `audio_full.wav`, `audio_final.wav`, `features.json`, `tracks.json`, `preset.json` (snapshot), `job.json`, `report.png`, `render.log` and, optionally, `scene.blend` (the baked scene, for inspection in the Blender GUI).

---

## 5. Stage specifications

### 5.1 Ingest

- Accept `.mp4 .mov .mkv .webm .wav .mp3 .flac .m4a .aac .ogg`. Ignore video streams.
- Decode with PyAV (bundled FFmpeg libraries) and its resampler to 48 kHz, stereo, 32-bit float WAV, written with soundfile. Analysis runs on a mono downmix; the render uses stereo.
- Only start a job once the file in `inbox/` has stopped changing size for 5 s, so a file that is still copying isn't picked up.
- Reject audio shorter than `min_len_s` (default 5 s) and files with no audio stream: move them to `inbox/failed/` and write an `.error.txt` next to them.
- Optional (`loudnorm = true`, default off): normalize `audio_final.wav` to −14 LUFS integrated and −1 dBTP. Default off keeps the artist's master untouched.

### 5.2 Analysis → `features.json`

**Frame grid:** `fps = 60`, `sr = 48000`, hop = **800 samples** = 1 video frame. Feature frame *i* describes audio time `i / 60` s, which is Blender frame `frame_start + i`. A global `sync_offset_frames` (default 0, typical −1) lets visuals anticipate the sound by a frame if that looks tighter.

| Channel | How | Typical use |
|---|---|---|
| `rms` | RMS per hop | overall glow, camera shake |
| `band.sub` 20–60 Hz | mel or STFT band energy | tunnel squeeze, low pulses |
| `band.bass` 60–250 Hz | 〃 | speed modulation |
| `band.lowmid` 250–500 Hz | 〃 | |
| `band.mid` 500 Hz–2 kHz | 〃 | pattern intensity |
| `band.highmid` 2–4 kHz | 〃 | |
| `band.air` 4–16 kHz | 〃 | sparkle, fine-line brightness |
| `centroid` | spectral centroid, log-scaled | color temperature (dark → cool, bright → warm) |
| `onset.kick / snare / hat` | band-limited spectral flux, peak-picked into **events** `[time_s, strength]` and rendered as decaying **envelopes** | flashes, portal pulses, lens punch |
| `onset.all` | full-band onset strength | generic hits |
| `beat.phase`, `bar.phase` | 0→1 ramp per beat or bar from the beat tracker | rhythmic oscillation that stays locked to the song |
| `tempo` | BPM and confidence; beat and downbeat times | bar grid, window snapping |
| `sections` | energy (1-bar smoothing) plus spectral novelty → boundaries snapped to downbeats → labels `intro / build / breakdown / drop / outro` | story arc (§5.4) |
| `drop_s` | the boundary with the largest positive energy jump after a low-energy section | payoff timing |

- **Normalization:** robust per-track scaling to 0..1 using the 5th–95th percentile, then clamped. Computed over the full track so that excerpts behave the same as the full song.
- **Downbeats:** v1 assumes 4/4 and picks the bar phase with the strongest low-band energy on beat 1. If that isn't good enough, the `beat_this` downbeat tracker is an optional upgrade.
- **Cleaner drum hits (optional, Phase 7):** splitting the drums out first (Demucs) before onset detection makes kick and snare reaction much cleaner on busy mixes. It's heavy (PyTorch), so it's off by default.
- **Report:** `report.png` (matplotlib) shows the waveform, band curves, onset events, beat grid, sections, drop marker and chosen window, for a quick visual check.

### 5.3 Length and window selection

| Setting | Default | Notes |
|---|---|---|
| `mode` | `fixed` | `full` or `fixed` |
| `length_s` | 30 | fixed mode only, snapped to whole bars when tempo confidence is high |
| `max_len_s` | 60 | YouTube blocks Shorts **over 1 minute** that have an active Content ID claim, so 60 s is the safe default cap. |
| `hard_max_s` | 180 | the Shorts maximum length |
| `fade_out_s` | 2.0 | equal-power fade ending exactly on the last frame |
| `fade_in_ms` | 10 | anti-click only. **No audible fade-in:** the hook must hit at once. |
| `start_s` | auto | manual override |

- **Full mode:** length = audio duration. If it's longer than `max_len_s`, the job switches to fixed mode with `length_s = max_len_s`.
- **Fixed mode, automatic excerpt:** the candidate start points are downbeats. Each candidate window gets a score:
  - **Payoff position (weight 0.5):** a detected drop near **70%** of the window scores highest.
  - **Hook strength (weight 0.3):** onset and energy in the first second.
  - **Clean ending (weight 0.2):** the window ends on a phrase boundary, i.e. 4 or 8 bars from the start.

  The best-scoring start wins. Sidecar overrides: `start_s`, `drop_s`, `bpm`.
- Frame count = `round(length_s × 60)`. The audio and the frame range are cut from the same numbers, so they can't drift apart.

### 5.4 Story arc (retention)

The arc turns song structure into five macro envelopes, all 0..1 per frame. The mapping uses them like any other feature.

| Envelope | Shape | Visual intent |
|---|---|---|
| `arc.energy` | section energy, smoothed over ~2 bars | overall intensity level |
| `arc.build` | ramps 0→1 across the section before the drop | speed-up, palette shift, tunnel narrowing |
| `arc.tension` | high in the breakdown, peaks right before the drop | brake, lights dying ring by ring, heartbeat center pulse |
| `arc.impact` | impulse at `drop_s`, decaying over ~1 bar | flash, tunnel bursts outward, peak speed |
| `arc.resolve` | 0→1 over the final `fade_out_s` | everything eases back to its frame-1 state |

- **Hook:** something must happen within the first second (an onset-driven event, or a forced `hook` pulse at frame ~20 if the excerpt starts quietly). No fade-in, no title.
- **Pattern interrupts:** the mapping should change *something* (a color step, spin reversal or ring flash) at least every 2 bars. This comes almost free from `bar.phase` events.
- **Fallback:** if no drop is detected (ambient or spoken audio), a template arc is laid on the bar grid (or on a time grid if there are no beats): cruise 25% · build 25% · tension 12% · payoff 25% · resolve 13%.
- **Seamless loop:** see loop closure in §5.5. When Shorts auto-replays, the picture continues without a visible jump.

### 5.5 Mapping → `tracks.json`

The mapping lives in `config/mappings/*.toml` and is human-edited. Each rule modulates one dynamic parameter:

```toml
# config/mappings/default.toml
[[rule]]
param   = "glow"            # a dynamic param from params.toml
source  = "onset.kick"      # any feature or arc channel
gain    = 3.0
curve   = 1.5               # exponent applied after normalization (>1 = punchier)
attack_ms  = 0              # one-pole smoothing, rising
release_ms = 180            # one-pole smoothing, falling
mode    = "add"             # add | multiply | replace | max

[[rule]]
param  = "speed"
source = "arc.build"
gain   = 1.0                # +100% speed at the end of the build
mode   = "multiply"

[[rule]]
param  = "blackout"
source = "arc.tension"
gain   = 0.85
mode   = "max"

[limits]
flash_max_per_s  = 3        # photosensitivity safety: max 3 flashes per second
flash_min_frames = 4        # no single-frame flashes (they also compress badly)
```

**Evaluation order per parameter:** preset base value → rules in file order → limits → `arc.resolve` blend toward the frame-1 value → clamp to the schema's min/max.

**Derived tracks** are computed in the mapping engine, not with Blender drivers, because drivers can't integrate over time:

- `travel = cumsum(speed) × π/60`, where speed is measured in portals per second.
- `spin = cumsum(spin_rate)`.

**Loop closure:** the total travel and spin are rescaled by up to ±3% so that the final frame lands on an exact multiple of the scene's repeat periods. The periods are stored in the template as `Director["period_travel"]`, `["period_spin"]` and so on. For the current scene the verified combined period is a travel of 6π with spins of ±90° and material phase +1; π-only periodicity of the portals is to be tested in Phase 1. The result: frame N+1 equals frame 1, so the loop is invisible.

**`tracks.json`** holds one float array per dynamic parameter, each with `n_frames` values, plus window metadata.

### 5.6 Parameters: static look vs dynamic motion

`config/params.toml` is the **single source of truth**. The Blender side panel builds its sliders from it, the mapping validates against it, and Blender applies it.

```toml
[param.sides]
group = "shape";  kind = "static";  type = "int";   default = 4;   min = 3;   max = 12
target = { kind = "gn_input", object = "Tunnel", modifier = "TunnelGen", input = "Sides" }

[param.ring_spacing]
group = "shape";  kind = "static";  type = "float"; default = 3.14159; min = 1.0; max = 8.0
target = { kind = "gn_input", object = "Tunnel", modifier = "TunnelGen", input = "Ring Spacing" }

[param.palette]
group = "look";   kind = "static";  type = "color_list"; default = ["#00E5FF", "#FF2BD6", "#FFD400"]
target = { kind = "material_ramp", material = "NeonLine", node = "Palette" }

[param.glow]
group = "motion"; kind = "dynamic"; type = "float"; default = 2.0; min = 0.0; max = 12.0
target = { kind = "director", prop = "glow" }
```

| Kind | Set when | Lives in | Examples (neon tunnel) |
|---|---|---|---|
| **static: shape** | once per render, from the preset | Geometry Nodes modifier inputs | sides, radius, ring spacing, ring thickness, line width, pattern density, pattern seed, twist, outer-shell radius |
| **static: look** | once per render, from the preset | material and compositor values | palette, base emission, glare size and threshold, lens (mm), color view transform |
| **dynamic: motion** | every frame, from `tracks.json` | custom properties on the `Director` empty, read by drivers | speed, travel, spin, outer spin, hue shift, glow, flash, squeeze, shake, blackout, lens punch, portal pulse |

**Template contract.** Any `.blend` used as a template must have:

1. An empty named **`Director`** with one custom property per dynamic parameter, with UI min, max and default set.
2. **No `frame`-based drivers.** Everything animated reads from `Director` with a single driver hop, so all motion comes from one place.
3. The static shape as a **Geometry Nodes** modifier with named inputs. Phase 5 rebuilds the current static tunnel meshes as a `TunnelGen` node group.
4. Repeat periods stored as `Director` properties, used for loop closure.
5. Render settings that match the `final` profile, which build-and-render overrides anyway.

### 5.7 Blender build and render (`blender/build_and_render.py`)

```
blender -b scenes/neon_tunnel.blend --python blender/build_and_render.py -- --job work/<job-id>/job.json [--profile draft|final]
```

1. Read `job.json`, then put `src/` on `sys.path` and import `datapipe.mapping`, which is numpy-only.
2. Apply the preset's static parameters through the `params.toml` targets.
3. Bake `tracks.json` into F-curves on the `Director` properties using `keyframe_points.add(n)` and `foreach_set("co", …)`, which is fast for thousands of keys. Interpolation is `LINEAR`, one key per frame.
4. Set the frame range to `1 … n_frames` at 60 fps.
5. Add `audio_final.wav` as a **sound strip** at frame 1 in the scene's video editor. With only sound strips there, Blender renders the 3D camera and mixes the audio into the MP4 in the same pass. *(Assumption to verify in Phase 3.)*
6. Apply the render profile and output path, then render the animation straight to MP4. No PNG intermediates by default.
7. Log per-frame times through render handlers to `render.log`, and optionally save the baked `scene.blend` to the job folder.

**Profiles** (in `config/pipeline.toml`):

| Profile | Resolution | EEVEE samples | Encode | Purpose |
|---|---|---|---|---|
| `draft` | 1080×1920 | 16 | CRF Medium | check pacing and sync quickly |
| `final` | 2160×3840 | 48 | CRF High | upload |
| `safe` | 2160×3840 | 48 | PNG frames → encode | resumable, for very long renders |

### 5.8 Output and export settings

Based on YouTube's upload recommendations:

| Setting | Value | Why |
|---|---|---|
| Aspect / size | 9:16, **2160×3840** (final) | YouTube recommends 1080×1920 for Shorts; sources disagree whether Shorts are ever served in 4K. A 4K upload never hurts and gives the encoder more detail on thin lines. A 1080×1920 profile is available for speed. |
| Frame rate | 60 fps | matches the analysis grid |
| Container / codec | MP4, H.264 | |
| Quality | CRF "High" (~100+ Mbps measured) | YouTube's reference for 2160p60 SDR is 53–68 Mbps and higher is fine, since YouTube re-encodes everything. |
| GOP / B-frames | 30 / 2 | YouTube recommends a GOP of half the frame rate and 2 B-frames. |
| Audio | AAC, 48 kHz, stereo, 320 kbps | |
| File name | `output/<yyyymmdd-HHMM>_<song-slug>_<preset>_<len>s.mp4` | plus `_draft` for drafts |

**Compression-proof look rules**, enforced by limits or preset defaults:
- Use motion blur during fast sections.
- Make flashes last 4 frames or more.
- Keep glow on thin saturated red and magenta lines, which lose their color first under YouTube's 4:2:0 encoding.
- Keep the focal point at center or upper center, because the bottom and right edges are covered by the Shorts UI.

---

## 6. Tweak tools

Two different things get tuned by feel, both in the Blender side panel, so everything is judged in the renderer that makes the final picture and every step can also run from code. Each tab writes a small file to the repo, and the pipeline applies those files to every new song. The panel doesn't have to be open to render.

| What | Where | Writes | Judged on |
|---|---|---|---|
| **Reactivity:** which feature drives which parameter; gains, curves, attack/release, thresholds, limits | **Reactivity tab** (§6.1) | `config/mappings/<name>.toml` | timing and feel, replayed with the song |
| **Shape and look:** geometry, palette, glow, lens, base values | **Shape and look tabs** (§6.2) | `presets/<name>.json` | the real EEVEE render |

**Why Blender only.** Blender can be driven entirely from code (headless batch, the bridge, the add-on), and every file it needs is in the repo or the job folder, so the pipeline has one host to automate, test and version. TouchDesigner is in the repo for the standalone projects (`projects/`), not for the pipeline. A browser tool (three.js with Web Audio) stays a last resort: its preview differs from the Blender render, so taste may not carry over.

### 6.1 Reactivity tab

**The rule that makes it work:** the tab tunes the *recipe*, not the analysis. It loads the pipeline's own `features.json` for a song and runs the pipeline's own `mapping.py`, so a recipe means the same thing in the tab and in the render.

1. **Pick a reference song.** `datapipe analyze song.mp4` writes `features.json` and `audio_full.wav` into the job folder; **Load job** in the panel bakes it and puts the audio on the timeline.
2. **Tune.** Every recipe value is a slider generated from the mapping schema: per rule source, gain, curve, attack, release and mode; globally the limits and the sync offset. A change re-bakes the tracks with `mapping.py` (milliseconds for a few thousand frames) into the `Director` keyframes.
3. **Replay.** Play the timeline with sound, or scrub. If the viewport can't hold 60 fps with the scene, lower the viewport resolution or judge timing in a `draft` render. Switch songs to check that the recipe holds up on more than one track.
4. **Export.** A button writes `config/mappings/<name>.toml`, and optionally the base values into a preset. Commit the file.

**From code.** The same steps run through the bridge (§2) or headless: set recipe values, re-bake, render a draft. Claude can tune a recipe this way ("punchier kick flash, slower release").

**Optional hero override.** For one special song, edited tracks can be saved to `work/<job-id>/tracks_override.csv`, and `build_and_render.py` then uses those instead of computing them. This is manual and per song, outside the automatic flow.

### 6.2 Blender side panel (`blender/addon_datapipe/`)

A "Datapipe" tab in Blender's sidebar (N panel) with:

- sliders generated from `config/params.toml` for every static shape and look parameter and for every dynamic parameter's base value, updating the viewport live;
- **Save / Load preset** (`presets/<name>.json`) and a preset dropdown;
- **Load job**, which bakes a job's tracks and loads its audio so you can scrub or play the timeline with the music;
- **Render draft** for the current job.

Claude can drive the same parameters through the bridge ("thicker lines, more magenta, slower spin") and save a preset. That's handy for big moves; the sliders are for fine adjustment.

**Preset format** (`presets/<name>.json`, written by the panel):

```json
{
  "version": 1,
  "name": "neon_default",
  "template": "neon_tunnel.blend",
  "static": { "sides": 4, "radius": 4.0, "ring_spacing": 3.14159, "line_width": 0.04,
              "palette": ["#00E5FF", "#FF2BD6", "#FFD400"], "lens_mm": 16 },
  "base":   { "speed": 1.0, "glow": 2.0, "hue_shift": 0.0, "spin_rate": 0.25 },
  "mapping": "default"
}
```

---

## 7. Orchestration

**CLI** (`uv run datapipe …`):

| Command | Does |
|---|---|
| `run <file> [--preset P] [--mapping M] [--mode full\|fixed] [--length 30] [--start 42.0] [--profile draft\|final]` | one job, end to end |
| `watch [--profile …]` | polls `inbox/` every 3 s and runs a job per new, stable file, one at a time (the GPU is the bottleneck) |
| `analyze <file>` | stages 1–2 only: `features.json` and `report.png` |
| `rerender <job-id> [--preset P] [--mapping M] [--profile …]` | reuses the cached analysis; for trying another look on the same song |
| `preview <job-id>` | opens the Blender GUI with the job baked and audio loaded, for tweaking |

**Sidecar (optional):** drop `song.toml` next to `song.mp4` to override settings for that file:

```toml
preset  = "neon_magenta"
mode    = "fixed"
length_s = 30
start_s  = 61.5      # or omit for auto
bpm      = 124       # fixes half/double-tempo detection errors
profile  = "final"
```

**Job lifecycle:** `inbox/song.mp4` → `work/<job-id>/source.mp4` → (stages 1–5) → `output/…mp4`. The source then moves to `archive/`. On failure the source goes to `inbox/failed/` with an `.error.txt`, and the job folder is kept for debugging.

**`job.json`** records:
- the resolved settings;
- hashes of the audio, preset, mapping and template;
- the Blender and pipeline versions (git commit);
- per-stage timings;
- the output paths.

That's enough to reproduce any output exactly.

---

## 8. Tech stack and prerequisites

| Component | Choice | Notes |
|---|---|---|
| Blender | 5.2.2 LTS (installed), pinned | Its API changed in 5.x (`sequences` → `strips`, `image_settings.media_type`), so scripts target 5.2. The Blender version is recorded in `job.json`. |
| TouchDesigner | 2025.32820 (installed) | Not part of the pipeline (v0.6). Used by the standalone projects in `projects/`. |
| Pipeline Python | **3.12.15 via `uv` 0.13.1**, in `.venv` | Kept separate from the system Python 3.14 to avoid librosa/numba compatibility risk. Remove it all with: delete `.venv`, `uv python uninstall 3.12`, `uv cache clean`, `winget uninstall astral-sh.uv`. |
| Python packages | numpy, scipy, librosa, soundfile, matplotlib; for §15: dawdreamer, mido, pyloudnorm | `tomllib` is built into the standard library for config |
| Audio engine (§15) | **DawDreamer 0.9** | Headless audio graph: Faust (libfaust embedded, with its standard libraries), VST3 hosting, sample-exact MIDI, per-processor recording. Wheels for Python 3.12 on macOS (arm64, x86_64), Windows x64 and Linux. Plugins are fetched into `dawdreamer/plugins/` (gitignored), never installed system-wide. |
| Platforms | Windows 11 and macOS 13+ | Tool paths per OS in `config/pipeline.toml` (`[paths.windows]`, `[paths.macos]`), overridable per machine in `config/machine.toml`. |
| Shared mapping code | numpy-only, Python 3.12 syntax, numpy ≥ 2.3 | runs unchanged in the uv environment (3.12) and in Blender (3.13, numpy 2.3) |
| Media | **PyAV** (`av`), which bundles the FFmpeg libraries | Decodes any container and probes outputs in tests. Pinned in `uv.lock` and lives only in the venv. Capped below 16 on macOS, whose newer wheels need macOS 14. If an ffmpeg command-line tool is ever needed, `imageio-ffmpeg` adds one inside the venv too. |
| Version control | Git (installed) | the `datapipe/` folder becomes a repo. Renders, `work/`, `cache/` and `inbox/` are git-ignored. |
| Optional | beat_this (downbeats), Demucs (drum stems) | Phase 7 |

**Security note:** the Blender bridge runs any Python sent to `localhost:9876`. Keep its host on `localhost` (the default) and never forward that port.

---

## 9. Performance budget

| Step | Estimate | Basis |
|---|---|---|
| Ingest and analysis | ~10–30 s per track | estimate, measured in Phase 2 |
| Final render, 4K | **~1.15 s/frame**: 30 s ≈ 35 min, 60 s ≈ 70 min | measured 0.98 s render + 0.16 s encode |
| Draft render, 1080p | to be measured, expected several times faster | Phase 3 |

`watch` processes one job at a time. Recommended workflow: draft first, check `report.png` and the draft, then run `rerender --profile final`. Alternatively, set `profile = "final"` in the sidecar for unattended runs.

---

## 10. Testing and acceptance

| Test | Method | Pass criterion |
|---|---|---|
| Analysis golden | Synthetic 120 BPM click track (kick on beats 1 and 3, snare on 2 and 4, hats on 8ths), generated in `tests/fixtures/` | tempo within 120 ± 0.5 BPM; kick, snare and hat events within ±1 frame |
| **Audio-visual sync** | Render the click track at 25% resolution with a "flash on kick" mapping, decode the MP4, measure mean brightness per frame | brightness peaks within **±1 frame** of the kick times |
| Loop closure | Render frames 1 and N+1, compute the pixel difference (the method used on 2026-10-19) | mean absolute difference < 0.001 |
| Rig parity | Phase 1 Director rig vs the original drivers at frames 1, 120 and 360 | mean absolute difference < 0.005 |
| Export | PyAV probe of the output | 2160×3840, 60 fps, frames = round(length × 60), AAC 48 kHz stereo, duration within ±1 frame |
| Mapping unit tests | pytest on smoothing, normalization, limits, integration and loop closure | flash limiter never exceeds 3 per second; tracks stay within schema min/max |
| Watch | Drop 3 valid files and 1 broken file | 3 outputs; 1 file in `failed/` with a readable error |

---

## 11. Implementation phases

| Phase | Scope | Done when |
|---|---|---|
| **P0 Foundations** | *done 2026-10-19:* folder structure, git, `CLAUDE.md`, README, bridge helper, uv + `.venv`, `pyproject.toml`, `pipeline.toml`, CLI with `doctor` | `uv run datapipe doctor` passes (PyAV decode, Blender 5.2, paths); `uv run pytest` green. **Both met.** |
| **P1 Template rig** | add the `Director` empty; replace the frame drivers with Director drivers; store periods; test π vs 6π periodicity | rig parity and loop tests pass; `rig.py` can redo it on any template |
| **P2 Analysis** | ingest, features, beats and bars, sections, drop, `report.png`, cache | click-track golden test passes; reports from 3 real tracks reviewed and judged plausible |
| **P3 Map, bake, render** | `mapping.py`, `window.py`, `arc.py`, loop closure, limits, `build_and_render.py`, draft and final profiles, audio in the MP4 | `datapipe run song.mp4 --length 30` produces an MP4 that passes the export and sync tests |
| **P4 Orchestration** | `watch`, sidecars, job lifecycle, failure handling, `job.json`, `rerender` | watch test passes; re-rendering with a new preset skips analysis |
| **P5 Shape and look panel** | `TunnelGen` Geometry Nodes rebuild, `params.toml`, `addon_datapipe` panel, presets, `preview` | moving a slider updates the viewport live; a saved preset gets used by `rerender`; the new tunnel matches the old look (signed off by eye) |
| **P6 Reactivity tab** | reactivity tab in `addon_datapipe`: recipe sliders from the mapping schema, live re-bake through `mapping.py`, replay with audio, TOML export | a recipe tuned in the tab and rendered by the pipeline matches the tab's replay timing (sync test, ±1 frame); an exported TOML round-trips (load, export, identical file) |
| **P7 Optional** | browser tool, Demucs stems, beat_this downbeats, more templates, YouTube upload | per item |

The pipeline produces usable Shorts after **P3**, with the fixed tunnel shape and a hand-edited mapping. P5 adds shape tweaking and P6 reactivity tuning, both in the Blender panel. P6 builds on the panel from P5 but not on its Geometry Nodes rebuild.

---

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Beat tracker locks to half or double tempo | `bpm` sidecar override; low confidence → onset-only mapping and a time-grid arc |
| No clear drop (ambient, acoustic, speech) | template arc fallback; `drop_s` override |
| Long 4K renders (≈70 min for 60 s) | draft-first workflow; 1080p profile; one job at a time; `safe` profile for resumability |
| librosa/numba on Python 3.14 | pin 3.12 via uv |
| Blender API changes between versions | pin 5.2 LTS; version in `job.json`; parity tests on upgrade |
| Strobing and photosensitivity | enforced flash limits (§5.5) |
| YouTube compression artifacts on thin neon lines | look rules (§5.8); 4K upload |
| Copyright and Content ID | default cap 60 s; prefer royalty-free sources such as the YouTube Audio Library |
| Geometry Nodes rebuild doesn't match the current look | keep the original meshes as a fallback template; check parity by eye |
| The Blender viewport can't play the scene with audio at 60 fps for live reactivity tuning | re-baking takes milliseconds; lower the viewport resolution, or judge timing in a reduced-resolution `draft` render (§6.1) |

---

## 13. Assumptions to verify

1. When Blender's video editor holds **only sound strips**, a headless render still renders the 3D camera and muxes the audio into the MP4 (Phase 3).
2. The tunnel also loops seamlessly after a travel of **π** (one portal) with no rotation, which gives finer loop closure; otherwise 6π (Phase 1).
3. ~~librosa runs cleanly on Python 3.12 on Windows with this setup.~~ Verified 2026-10-19: librosa 1.0.0 with numba 0.68 imports and runs under `doctor`.
4. How YouTube currently handles 4K uploads for Shorts. This doesn't block anything; the 1080p profile exists either way.
5. Blender re-bakes a whole song's tracks from `mapping.py` and keys them on the `Director` fast enough to feel instant while dragging a slider, and its viewport plays the scene with audio smoothly enough to judge timing (P6).

## 14. Open decisions

| # | Question | Default if not decided |
|---|---|---|
| 1 | ~~Reactivity tuning in TouchDesigner, or Blender-only (§6)?~~ | **Decided in v0.6: Blender only.** TouchDesigner stays for the standalone projects |
| 2 | Default length mode and length | fixed, 30 s, cap 60 s |
| 3 | Default render profile in `watch` | `draft`; final through `rerender` |
| 4 | Final resolution | 2160×3840 |
| 5 | Watch folder vs manual command only | both available |
| 6 | Further templates beyond the neon tunnel | tunnel only in v1 |
| 7 | Loudness normalization of the output audio | off |

---

## 15. Generative loops

The song pipeline (§1–§11) starts from a finished track. The generative mode starts from a preset and a seed and composes the audio first: an 8-second seamless loop whose exact score drives every visual event, so sync comes from the notes, not from analysis. The product design, salience model, story, visual rules, mapping and QA are in [docs/sticky-av-shorts.md](docs/sticky-av-shorts.md); the audio is specified in [dawdreamer/](dawdreamer/README.md).

| | Song pipeline | Generative loops |
|---|---|---|
| Input | an audio or video file in `inbox/` | a preset and a seed, or a MIDI file |
| Length | the song, or a fixed excerpt (§5.3) | 8.0 s: 480 frames, 384,000 samples, 120/150/180/240 BPM |
| Timing source | beat tracking and onsets | the score; analysis adds texture only |
| Picture | 2160×3840 | 1080×1920 (docs/sticky-av-shorts.md) |
| Run folder | `work/<job-id>/` | `work/gen/<yyyymmdd>_<preset>_s<seed>/`, newest mirrored to `work/gen/latest/` |
| Command | `datapipe run` (P3) | `datapipe gen` (audio), `datapipe short` (the finished Short) |
| Blender scene | `scenes/neon_tunnel.blend`, Director rig (P1) | `blender/stem-tunnel/stem_tunnel.blend`: the lines tunnel of `blender/audio-tunnel`, its own signal rig |

**Stages.** All built in a first version. S0 config and seed, S1 compose or ingest MIDI (`gen/compose.py`), S2 audio render (`gen/engine.py`, `gen/master.py`); S3 controls from the stems and the score (`gen/controls.py` → `controls.json`); S4 the mapping onto a look (`blender/stem-tunnel/mapping.toml` with the shared `src/datapipe/mapping.py`, which also closes every accumulated motion on the loop); S5 the headless Blender render (`blender/stem-tunnel/stem_tunnel.py`); S6 the PyAV encode and S7 the checks (`gen/video.py`). Still open: band energies and onset strength in S3, the Shorts overlay-mask gate in S7, and the song pipeline's Director rig (P1) as a second scene for this mode. Project notes: [blender/stem-tunnel/README.md](blender/stem-tunnel/README.md).

**Specs.** [audio.md](dawdreamer/specs/audio.md): what a loop must sound like. [engine.md](dawdreamer/specs/engine.md): the render graph, mastering, determinism, built-in sounds, plugins. [presets.md](dawdreamer/specs/presets.md): the preset format. [handoff.md](dawdreamer/specs/handoff.md): the run files, the timing contract, how Blender reads them.

**Phases**

| Phase | Scope | Done when |
|---|---|---|
| **G1 Audio engine** | *done 2026-10-22 on macOS:* DawDreamer, 13 Faust instruments and effects, composer (roles, story, one violation per loop), MIDI ingest, two-pass render, stems, −18 LUFS master staging, −14 LUFS and −1 dBTP mastering, seam check, plugin manifest with fetch and probe, three presets, run folder with `score.json`, `score.mid`, `frames.csv`, `latest/`, `doctor` checks | `uv run pytest` green including `tests/test_gen_*.py`; every preset renders at −14 ± 0.5 LUFS, ≤ −1 dBTP, seam ok; reruns are bit-identical. **Met on macOS (32 tests). Windows: run `uv sync`, `datapipe plugins fetch`, `datapipe doctor` and the tests.** |
| **G2 Read a run in Blender** | *done 2026-10-22 on macOS:* `blender/stem-tunnel` loads a run headless: score hits and stem loudness keyed on the `AudioSignals` empty, the reference look's drivers re-wired to them, `mix.wav` on the timeline of the saved `scene_baked.blend` | a kick-driven pulse lands within ±1 frame of the kick. **Met: median offset 0–1 frame in the sync gate.** |
| **G3 Stem analysis, control build** | *first version done:* S3 per-frame loudness of every stem and the mix, mix brightness, score hits, sections, curves; S4 hit envelopes with wind-up, followers, smoothing, loop closure; the flash safety comes from the look (`kick_light`, the portals' `near_fade`) and is measured in S7 rather than limited in S4 | controls wrap seamlessly (frame 480 → 1) and pass the flash gate. **Met: frame 481 renders as frame 1 (mean difference 0.00002–0.00005); no full-frame flash in `neon_house` seed 42.** |
| **G4 Render, encode, QA** | *first version done:* `datapipe short`, S5–S7 at 1080×1920, `--preview` at half size | the MP4 passes the S7 gates (format and colour tags, length, faststart, loudness of the delivered AAC, kick sync, seam, flashes); safe-zone gate still open (needs the overlay mask). Test: `tests/test_gen_video.py`. |

---

### References

- [YouTube: Understand three-minute Shorts (Content ID rule over 1 minute)](https://support.google.com/youtube/answer/15424877?hl=en)
- [YouTube: Music eligibility for Shorts](https://support.google.com/youtube/answer/13486873?hl=en)
- [YouTube: Recommended upload encoding settings](https://support.google.com/youtube/answer/1722171?hl=en)
- [ShortSync: Shorts upload requirements 2026 (third party)](https://shortsync.app/resources/youtube-shorts-upload-requirements-2026)
- [Blender Lab MCP server](https://www.blender.org/lab/mcp-server/)
