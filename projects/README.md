# TouchDesigner projects

These are standalone TouchDesigner projects. They aren't part of the Datapipe pipeline. Each one runs on its own; the ones set up with Embody and Envoy externalize their networks to text files that git can diff. To work on one, open the `.toe` named after its folder in TouchDesigner 2025.

`00-custom-modules/` isn't a project. It holds components the projects share, saved as `.tox` files that projects load through External .tox; its README says how to use and change them.

| Folder | What it is | Formerly |
|---|---|---|
| `time-series-wavetable/` | The Mortgage Wavetable: the Bundesbank housing-loan series turned into a playable synth with a live dashboard. One COMP, `time_series_wavetable`. | `econ-sonification/tdapi.toe`; history in the GitHub repo `econ-sonification` |
| `touch-the-sonogram/` | The Audioreactor installation: the Bundesbank wavetable drone, shaped by a camera and a microphone and drawn as a point-cloud sonogram. One COMP, `touch_the_sonogram`. | `econ-sonification/touch-the-sonogram.toe` |
| `caleidoscopic-sonogram-video/` | The square music-video version of the Audioreactor: the point cloud driven by an audio track and a modulator video. One COMP, `caleidoscopic_sonogram_video`. | `econ-sonification/audioreactor.toe` |
| `audioreactive-pointcloud/` | An audio-reactive point cloud, started from the Embody/Envoy starter project. | `td-sandbox/NewProject.toe` (`Projects/tdt`) |
| `ferroscope/` | The FerroScope network, which has a reusable CRT filter (any TOP in, analog signal and tube emulation out; a portable copy is in `components/CRT.tox`). Its video and audio sources, YouTube input through yt-dlp, and a transport that scrubs them (linked when both come from the same clip) come from the shared `source_deck` module in `00-custom-modules/`. One COMP, `ferroscope`. AVCloud, the webcam-and-mic particle cloud it replaced, is in `archive/`. | `ferroscope/inputmadness.toe` (`Projects/inputter`) |
| `color-ribbon-butterfly/` | 250,000 tiny instanced hexagons placed by an animated 4D simplex-noise texture, smeared into colored ribbons by a feedback loop, RGBA delay and a radial blur. | |
| `infinite-hypercube/` | 262,144 instanced points (one per pixel of a 512×512 noise texture) carried by a noise field that displaces itself through feedback, inside a cube whose faces wrap around: a point leaving one side comes back on the opposite one. Rendered with trails, depth-based blur and RGBA delay. | |
| `iridiscent-viz/` | A music visualizer. A particle stream from a line emitter, its turbulence stirred by an LFO, is lit by an audio track: the kick drives the bloom, the rhythm the glow, and the highs the glow color and the rotation. Feedback trails, mirroring, tiling and RGBA delay make the iridescent, kaleidoscopic look; a Movie File Out records it. | |
| `noise-attractor-landscape/` | A GPU particle swarm (the palette's `particlesGpu`) in turbulence, wind and external-force fields. Three presets of each are spread across the particles through lookup channels, so different parts of the swarm move differently. Instanced and rendered with feedback trails. | |
| `octatrack-audio-modulation/` | An early Octatrack sketch. Octatrack audio and MIDI are read in and shaped (band levels, S-curves), but nothing in the saved network uses them yet: the visual, a million instanced points from a 1000×1000 ramp texture displaced by noise, with bloom, is still moved by LFOs. | |
| `octatrack-av-setup/` | The live AV set. MIDI notes from the Octatrack (channel 3, one per track) and the low and mid bands of its audio, coming in through an Elektron Analog Heat MKII as the audio interface, drive a noise-field particle generator (the engine of `infinite-hypercube`): noise period, spread and amplitude, camera distance, feedback and depth blur. The result goes out at 1920×1080 over Syphon/Spout. | |
| `octatrack-heat-midi-audio-mapping/` | The input layer of `octatrack-av-setup` on its own, with no visuals: Octatrack audio through the Analog Heat MKII split into low, mid and high band levels, and the MIDI note triggers of four tracks (`T1` to `T4`). | |

The three sonogram/wavetable projects were split out of `econ-sonification/`, where all three shared one `project1/` (`series_synth`, `audioreactor`, `musicvideo`). Each is now pruned to its own COMP.

## What stays local

Git (the repo `.gitignore` and each project's own) keeps the following off GitHub:

- `.venv/`, `Backup/`, `logs/`, `.mcp.json` and the generated files in `.embody/` (only `.embody/project.json` is committed)
- `TDImportCache/` and TouchDesigner's numbered incremental saves (`name.17.toe`)
- in `ferroscope/`, the YouTube downloads in `media/`

## Working with Claude

- **Generated files.** Embody generates each project's `CLAUDE.md`, `AGENTS.md` and `.claude/` folder and may overwrite them, so put lasting project notes somewhere else.
- **Starting Claude Code.** Envoy writes `.mcp.json` into the project folder each time TouchDesigner opens the project on a machine. To use the Envoy tools for live TD work, start Claude Code inside that project's folder, not at the repo root. After renaming or copying a project folder, open its `.toe` once so Envoy rewrites `.mcp.json` with the new paths.
