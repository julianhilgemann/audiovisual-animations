# Datapipe

Audio-reactive YouTube Shorts rendered with Blender. Drop a song into `inbox/` and get a finished 9:16 MP4 in `output/`.

> **Status:** Phase 0 done: toolchain and skeleton. The generative mode's audio engine works: `datapipe gen` composes and renders 8-second loops with DawDreamer ([dawdreamer/](dawdreamer/README.md)). Design and roadmap: [SPEC.md](SPEC.md).

## Setup

```
uv sync                    # creates .venv with Python 3.12 and all libraries (nothing installed system-wide)
uv run datapipe doctor     # checks Python libs, PyAV/FFmpeg, DawDreamer, Blender, GPU
uv run pytest              # runs the tests
uv run datapipe gen --seed 42 --play     # compose, render and play an 8-second loop
```

Requirements, on Windows or macOS: [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`, or `brew install uv`), and Blender 5.2 LTS. The pipeline needs nothing else; TouchDesigner is only for the standalone projects. Tool paths per OS are in `config/pipeline.toml`; `config/machine.toml` overrides them for one machine.

## Folders

| Folder | What goes there |
|---|---|
| `inbox/` | Audio or video files to turn into Shorts (watched automatically from Phase 4) |
| `output/` | Finished Shorts |
| `scenes/` | Blender template scenes |
| `presets/` | Shape and look presets, saved from the Blender side panel |
| `config/mappings/` | Reactivity recipes, exported from the Blender panel or hand-edited |
| `projects/` | Standalone TouchDesigner projects that aren't part of the pipeline (see [projects/README.md](projects/README.md)) |
| `dawdreamer/` | Generated audio: specs, presets, Faust instruments, the free VST3 plugin list (see [dawdreamer/README.md](dawdreamer/README.md)) |
| `docs/` | Design of the generative mode ([sticky-av-shorts.md](docs/sticky-av-shorts.md)) |
| `reference/` | Reference renders |
| `work/`, `cache/`, `archive/` | Pipeline internals; generated loops land in `work/gen/`, the newest in `work/gen/latest/` |

## Working with Claude

Open a terminal in this folder and run `claude`. `CLAUDE.md` gives it the project context. For example: "start Phase 0", or "make the rings thicker in the open Blender scene".

## Tools

- `python tools/blender_bridge.py --ping` checks that Claude and scripts can reach the open Blender (MCP add-on on `localhost:9876`).
