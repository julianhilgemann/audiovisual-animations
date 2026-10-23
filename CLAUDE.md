# Datapipe

Audio-reactive YouTube Shorts: a file dropped in `inbox/` is analyzed, mapped onto a Blender scene's parameters and rendered headless to an upload-ready MP4 in `output/`. One render, zero post-production. The pipeline uses Blender only, because it can be driven entirely from code.

`SPEC.md` is the design source of truth. Read the section for a stage before building or changing it. When a decision changes, update SPEC in the same commit and bump its version line.

## Status

Six input methods run end to end on macOS (SPEC §16, v0.9): `uv run datapipe short gen|master|stems|midi|slots|deep …` turns a generated loop (A, SPEC §15), a finished master (B), master and stems (C), master, stems and MIDI (D), any stems as numbered slots without a tempo (E), or one complex track measured from every side (F, SPEC §16.7) into a finished Short. Any of their runs can be tuned by hand in Blender and rendered as tuned (`datapipe tune`, SPEC §6, v0.10: P5 and P6 on the stem tunnel), and the tunnel's shape is a style (`--style`). Open: a real Ableton export for D, three real tracks for B and F, real non-drum stems for E (M2, M4, M5, M6), the overlay-mask gate, a Windows run, the tuner's GUI on Windows. The Director rig (old P1) is now an optional second look; next after that is P4 (`watch`). `uv run datapipe doctor` checks the whole toolchain, and `uv run pytest` runs the tests.

The user wants this machine left intact. Python packages go into `.venv` through `pyproject.toml` and `uv`. FFmpeg comes from PyAV (`av`) inside the venv, not a system ffmpeg. Anything installed outside the repo needs the user's go-ahead first.

Work phase by phase. A phase is done when its "Done when" column in SPEC §11 holds, shown by running the named test and reporting its output.

## One mapping engine, two hosts

`src/datapipe/mapping.py` runs unchanged in the uv env (Python 3.12) and in Blender (3.13, numpy 2.3), where the panel's reactivity tab re-bakes with it. Keep it numpy-only, with the numpy ≥ 2.3 API. A recipe tuned in the panel means the same thing in a headless render only because both run this one file. The venv has numpy 2.5, so a passing venv test doesn't prove the file still works on numpy 2.3. Run the mapping tests under Blender's Python as well.

## Input methods (`src/datapipe/shorts.py`, SPEC §16)

- Each method has its own front end (A `gen/`, B–F `song/`: E is `song/slots.py`, F `song/deep.py`), landing zone (`inbox/<method>/`) and run folders (`work/<method>/`); all write the same `controls.json` (contract in `dawdreamer/specs/handoff.md`) and share one back end, `render.py` (S5–S7).
- One Blender look is the hub: `blender/stem-tunnel/stem_tunnel.blend` with `mappings/<method>.toml`. `[looks]` and `[methods]` in `config/pipeline.toml` pick the look; a new look is a new folder with the same six mapping files. The sync gate checks the track the mapping's `ring` follows.
- Songs don't wrap (`wrap: false`): `mapping.py` functions take `wrap`, and nothing may flow from a song's end into its start. Motion still closes on a loop unless `loop = false`.
- After changing detection (`song/onsets.py`, `song/analysis.py`), run `tests/test_song.py` and `tests/test_slots_deep.py` and compare hits against a generated loop's score (`datapipe example stems` writes `score.json` next to the export).

## Tuning and shapes (`blender/stem-tunnel/`, SPEC §6)

- `uv run datapipe tune <method> [input | --run R]` opens the run in the Blender GUI with the Datapipe panel (`tuner.py`). Save to run writes `<run>/tuning/stem-tunnel/` (mapping, style, `automation.json`), and a render takes, per file, `--mapping`/`--style`, then the run's tuning, then the look's (`render.look_files`). The tuner must keep baking through `stem_tunnel.py`'s own functions, never a copy: `tests/test_tune.py` compares the panel's baked keys with the render's.
- `look.toml` is the single list of the look's controls (signals, 47 sliders, 19 shape controls). A new slider goes there first, then into `stem_tunnel.py` (a driver in `wire`, or `SHADER` for the material, or `motion` with `motion = true`), then rebuild the template.
- Mapping and style files are written in one canonical form by `src/datapipe/recipe.py` (stdlib only: Blender imports it). The round-trip test requires the committed files to be in it: after a hand edit, rewrite with `recipe.save(p, recipe.dumps_mapping(recipe.load(p), schema, recipe.header(p)))` (`dumps_style` for styles).
- `shapes.py` builds the meshes in numpy. With the default style it must keep rebuilding the reference meshes (mesh parity test); a new pattern needs its repeat periods in `_pattern_periods` and passes `test_every_shape_repeats_after_its_periods`. Shapes that put more lines in view raise the base brightness and the kick pulses with it: check a new style's flash and sync gates at `--preview`.

## Generative audio (`dawdreamer/`, `src/datapipe/gen/`)

`uv run datapipe gen --preset <name> --seed <n>` composes, renders with DawDreamer and masters an 8-second loop into `work/gen/<run>/`, mirrored to `work/gen/latest/`. Read `dawdreamer/README.md` and the spec for the part you touch in `dawdreamer/specs/` first.

- `gen/score.py` is the contract Blender imports: keep it standard-library only, and check it under Blender's Python after changes.
- Every slot that names a plugin needs a Faust `fallback`, and `neon_house` stays Faust-only, so a fresh clone renders without plugins. Plugins are fetched into `dawdreamer/plugins/` (gitignored) by `datapipe plugins fetch`; never commit them, and add new ones to `plugins.toml` with URLs and sha256 for both OSes.
- Set plugin parameters by display value (`"A Decay" = "1.2"`); `datapipe plugins probe <key>` lists them.
- After a sound or gain change, render a few seeds and compare the printed `balance` line with the table in `specs/audio.md`; the limiter should take 1–4 dB.
- Keep a `RenderEngine` alive while its processors are used: a freed engine segfaults them.
- The Blender side of a Short is `blender/stem-tunnel/` (README there). `stem_tunnel.blend` is derived from `blender/audio-tunnel/neon_tunnel_audio.blend` by `stem_tunnel.py --make-template`; rebuild it that way rather than editing it by hand, then run `tests/test_gen_video.py` and `tests/test_song.py` and a `--preview` Short and check the seam and flash gates.
- Every look change can bring back flashes: the S7 gate counts full-frame flashes in mean relative luminance. Iterate at `--preview`, not 25 %: the compositor glare scales with resolution.

## Environment, macOS (Apple M1, macOS 13.5, zsh)

The second machine. Tool paths come from `[paths.macos]` in `config/pipeline.toml`: Blender 5.2.2 LTS at `/Applications/Blender.app/Contents/MacOS/Blender`. PyAV is capped below 16 here because its newer macOS wheels need macOS 14. Native tools run with plain `subprocess` argument lists.

## Environment, Windows 11 (PowerShell 5.1)

- Blender 5.2.2 LTS: `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`. Use the 5.x API: `sequence_editor.strips`, and set `image_settings.media_type = "VIDEO"` before `file_format = "FFMPEG"`.
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

Commit code, configs, presets and templates. Media and pipeline state stay local: `inbox/`, `work/`, `cache/`, `output/`, `archive/`, `reference/` and audio/video files are covered by `.gitignore`.

`origin` is the **public** GitHub repo `julianhilgemann/audiovisual-animations`, and the user wants it public. Never commit secrets, and keep third-party media out of it.
