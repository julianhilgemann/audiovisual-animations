# TouchDesigner projects

These are standalone TouchDesigner projects. They aren't part of the Datapipe pipeline. Each one runs on its own; the ones set up with Embody and Envoy externalize their networks to text files that git can diff. To work on one, open the `.toe` named after its folder in TouchDesigner 2025.

| Folder | What it is | Formerly |
|---|---|---|
| `time-series-wavetable/` | The Mortgage Wavetable: the Bundesbank housing-loan series turned into a playable synth. | `econ-sonification/tdapi.toe`; history in the GitHub repo `econ-sonification` |
| `touch-the-sonogram/` | The Audioreactor installation: the Bundesbank wavetable drone, shaped by a camera and a microphone and drawn as a point-cloud sonogram. One COMP, `touch_the_sonogram`. | `econ-sonification/touch-the-sonogram.toe` |
| `caleidoscopic-sonogram-video/` | The square music-video version of the Audioreactor. | `econ-sonification/audioreactor.toe` |
| `audioreactive-pointcloud/` | An audio-reactive point cloud, started from the Embody/Envoy starter project. | `td-sandbox/NewProject.toe` (`Projects/tdt`) |
| `ferroscope/` | The FerroScope network, which has a reusable CRT filter (any TOP in, analog signal and tube emulation out; a portable copy is in `components/CRT.tox`) and YouTube input through yt-dlp. Older versions and AVCloud are in `archive/`. | `ferroscope/inputmadness.toe` (`Projects/inputter`) |
| `color-ribbon-butterfly/` | _to describe_ | |
| `infinite-hypercube/` | _to describe_ | |
| `iridiscent-viz/` | _to describe_ | |
| `noise-attractor-landscape/` | _to describe_ | |
| `octatrack-audio-modulation/` | _to describe_ | |
| `octatrack-av-setup/` | _to describe_ | |
| `octatrack-heat-midi-audio-mapping/` | _to describe_ | |

The three sonogram/wavetable projects were split out of `econ-sonification/`. `touch-the-sonogram/` is pruned to its own COMP. The other two still carry the same `project1/` externalizations (`series_synth`, `audioreactor`, `musicvideo`), so each one restores all three COMPs when it opens. Pruning a project down to the COMPs it uses happens in TouchDesigner, so Embody keeps `externalizations.tsv` in step.

## What stays local

Git (the repo `.gitignore` and each project's own) keeps the following off GitHub:

- `.venv/`, `Backup/`, `logs/`, `.mcp.json` and the generated files in `.embody/` (only `.embody/project.json` is committed)
- `TDImportCache/` and TouchDesigner's numbered incremental saves (`name.17.toe`)
- in `ferroscope/`, the YouTube downloads in `media/`

## Working with Claude

- **Generated files.** Embody generates each project's `CLAUDE.md`, `AGENTS.md` and `.claude/` folder and may overwrite them, so put lasting project notes somewhere else.
- **Starting Claude Code.** Envoy writes `.mcp.json` into the project folder each time TouchDesigner opens the project on a machine. To use the Envoy tools for live TD work, start Claude Code inside that project's folder, not at the repo root. After renaming or copying a project folder, open its `.toe` once so Envoy rewrites `.mcp.json` with the new paths.
