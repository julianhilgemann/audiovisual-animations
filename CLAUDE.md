# Datapipe

Audio-reactive YouTube Shorts: a file dropped in `inbox/` is analyzed, mapped onto a Blender scene's parameters and rendered headless to an upload-ready MP4 in `output/`. One render, zero post-production.

`SPEC.md` is the design source of truth. Read the section for a stage before building or changing it. When a decision changes, update SPEC in the same commit and bump its version line.

## Status

Phase 0 is done; next is Phase 1, the Director rig (SPEC §11). `uv run datapipe doctor` checks the whole toolchain, and `uv run pytest` runs the tests.

The user wants this machine left intact. Python packages go into `.venv` through `pyproject.toml` and `uv`. FFmpeg comes from PyAV (`av`) inside the venv, not a system ffmpeg. Anything installed outside the repo needs the user's go-ahead first.

Work phase by phase. A phase is done when its "Done when" column in SPEC §11 holds, shown by running the named test and reporting its output.

## One mapping engine, three hosts

`src/datapipe/mapping.py` runs unchanged in the uv env (Python 3.12), Blender (3.13, numpy 2.3) and TouchDesigner (3.11, numpy 2.1). Keep it numpy-only, with Python 3.11 syntax and the numpy ≥ 2.1 API. A recipe tuned in TouchDesigner means the same thing in a Blender render only because all three hosts run this one file. The venv has numpy 2.5, so a passing venv test doesn't prove the file still works on numpy 2.1. Run the mapping tests under Blender's Python as well.

## Environment (Windows 11, PowerShell 5.1)

- Blender 5.2.2 LTS: `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`. Use the 5.x API: `sequence_editor.strips`, and set `image_settings.media_type = "VIDEO"` before `file_format = "FFMPEG"`.
- TouchDesigner 2025.32820: `C:\Program Files\Derivative\TouchDesigner\`. The user edits `.toe` files in TD. Agent work there is the Python in `touchdesigner/scripts/` and the export format (SPEC §6.1).
- Run native tools (Blender, ffmpeg) with `Start-Process -Wait -NoNewWindow -RedirectStandardOutput <log> -RedirectStandardError <log>`, then read the logs. PowerShell 5.1 turns native stderr into error records under `2>&1`.
- GPU: RTX 5060 Laptop, 8 GB. A final 4K EEVEE render costs ~1.15 s/frame including encode, so a 30 s Short takes ~35 min. Run renders in the background and iterate at the draft profile or a reduced `resolution_percentage`.

## Talking to Blender

- **Live** (Blender GUI open): `python tools/blender_bridge.py --ping | -c CODE | -f FILE` runs Python in the open scene through the Blender Lab MCP add-on on `localhost:9876`. Code returns data by assigning a dict to `result`. Use this to inspect or tweak what the user is looking at.
- **Headless server** (no GUI): start `blender -b scenes/neon_tunnel.blend --online-mode -c blender_mcp`, then use the same bridge.
- **Batch**: `blender -b <file> --python <script> -- <args>`.

Saving a `.blend` leaves a `.blend1` backup next to it. Git ignores it.

## Template scenes

`scenes/*.blend` are templates; their contract is in SPEC §5.6. After changing one, prove it with the pixel-diff tests (rig parity, loop closure; SPEC §10) before committing, and put the measured diff numbers in the commit message.

## Git

Commit code, configs, presets, templates and TD projects. Media and pipeline state stay local: `inbox/`, `work/`, `cache/`, `output/`, `archive/`, `reference/` and audio/video files are covered by `.gitignore`.
