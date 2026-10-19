# Datapipe

Audio-reactive YouTube Shorts rendered with Blender. Drop a song into `inbox/` and get a finished 9:16 MP4 in `output/`.

> **Status:** Phase 0, project skeleton. The pipeline itself isn't built yet. Design and roadmap: [SPEC.md](SPEC.md).

## Folders

| Folder | What goes there |
|---|---|
| `inbox/` | Audio or video files to turn into Shorts (watched automatically from Phase 4) |
| `output/` | Finished Shorts |
| `scenes/` | Blender template scenes |
| `presets/` | Shape and look presets, saved from the Blender side panel |
| `config/mappings/` | Reactivity recipes, exported from TouchDesigner or hand-edited |
| `touchdesigner/` | The TouchDesigner Reactivity Lab project |
| `reference/` | Reference renders |
| `work/`, `cache/`, `archive/` | Pipeline internals |

## Working with Claude

Open a terminal in this folder and run `claude`. `CLAUDE.md` gives it the project context. For example: "start Phase 0", or "make the rings thicker in the open Blender scene".

## Tools

- `python tools/blender_bridge.py --ping` checks that Claude and scripts can reach the open Blender (MCP add-on on `localhost:9876`).
