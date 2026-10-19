# TouchDesigner projects

These are standalone TouchDesigner projects. They aren't part of the Datapipe pipeline. Each one runs on its own, with Embody and Envoy externalizing its networks to text files that git can diff. To work on one, open its main `.toe` in TouchDesigner 2025.

| Folder | What it is | Open | Formerly |
|---|---|---|---|
| `econ-sonification/` | Economic data as sound and image. The Mortgage Wavetable turns the Bundesbank housing-loan series into a playable synth. Also here: the Audioreactor installation and its square music-video version. | `audioreactor.toe`, `tdapi.toe` | `Projects/TDAPI`; history in the GitHub repo `econ-sonification` |
| `ferroscope/` | The FerroScope network, which has a reusable CRT filter (any TOP in, analog signal and tube emulation out; a portable copy is in `components/CRT.tox`) and YouTube input through yt-dlp. Older versions and AVCloud are in `archive/`. | `inputmadness.toe` | `Projects/inputter` |
| `td-sandbox/` | An empty Embody/Envoy starter project for trying things out. | `NewProject.toe` | `Projects/tdt` |

## What stays local

Each project's `.gitignore` keeps the following off GitHub:

- `.venv/`, `Backup/`, `logs/` and `.mcp.json`
- `TDImportCache/` and TouchDesigner's numbered incremental saves (`name.17.toe`)
- in `ferroscope/`, the YouTube downloads in `media/`

## Working with Claude

- **Generated files.** Embody generates each project's `CLAUDE.md`, `AGENTS.md` and `.claude/` folder and may overwrite them, so put lasting project notes somewhere else.
- **Starting Claude Code.** Envoy writes `.mcp.json` into the project folder the first time TouchDesigner opens the project on a machine. To use the Envoy tools for live TD work, start Claude Code inside that project's folder, not at the repo root.
