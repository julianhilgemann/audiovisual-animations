# Datapipe

Audio-reactive YouTube Shorts: a file dropped in `inbox/` is analyzed, mapped onto a Blender scene's parameters and rendered headless to an upload-ready MP4 in `output/`. One render, zero post-production. The pipeline uses Blender only, because it can be driven entirely from code; TouchDesigner is in the repo for the standalone projects in `projects/`.

`SPEC.md` is the design source of truth. Read the section for a stage before building or changing it. When a decision changes, update SPEC in the same commit and bump its version line.

## Status

Four input methods run end to end on macOS (SPEC §16, v0.8): `uv run datapipe short gen|master|stems|midi …` turns a generated loop (A, SPEC §15), a finished master (B), master and stems (C), or master, stems and MIDI (D) into a finished Short. Open: a real Ableton export for D, three real tracks for B (M2, M4), the overlay-mask gate, a Windows run. The Director rig (old P1) is now an optional second look; next after that is P4 (`watch`). `uv run datapipe doctor` checks the whole toolchain, and `uv run pytest` runs the tests.

The user wants this machine left intact. Python packages go into `.venv` through `pyproject.toml` and `uv`. FFmpeg comes from PyAV (`av`) inside the venv, not a system ffmpeg. Anything installed outside the repo needs the user's go-ahead first.

Work phase by phase. A phase is done when its "Done when" column in SPEC §11 holds, shown by running the named test and reporting its output.

## One mapping engine, two hosts

`src/datapipe/mapping.py` runs unchanged in the uv env (Python 3.12) and in Blender (3.13, numpy 2.3), where the panel's reactivity tab re-bakes with it. Keep it numpy-only, with the numpy ≥ 2.3 API. A recipe tuned in the panel means the same thing in a headless render only because both run this one file. The venv has numpy 2.5, so a passing venv test doesn't prove the file still works on numpy 2.3. Run the mapping tests under Blender's Python as well.

## Input methods (`src/datapipe/shorts.py`, SPEC §16)

- Each method has its own front end (A `gen/`, B–D `song/`), landing zone (`inbox/<method>/`) and run folders (`work/<method>/`); all write the same `controls.json` (contract in `dawdreamer/specs/handoff.md`) and share one back end, `render.py` (S5–S7).
- One Blender look is the hub: `blender/stem-tunnel/stem_tunnel.blend` with `mappings/<method>.toml`. `[looks]` and `[methods]` in `config/pipeline.toml` pick the look; a new look is a new folder with the same four mapping files.
- Songs don't wrap (`wrap: false`): `mapping.py` functions take `wrap`, and nothing may flow from a song's end into its start. Motion still closes on a loop unless `loop = false`.
- After changing detection (`song/onsets.py`, `song/analysis.py`), run `tests/test_song.py` and compare hits against a generated loop's score (`datapipe example stems` writes `score.json` next to the export).

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

The second machine. Tool paths come from `[paths.macos]` in `config/pipeline.toml`: Blender 5.2.2 LTS at `/Applications/Blender.app/Contents/MacOS/Blender`, TouchDesigner 2023.12230 (standalone projects only). PyAV is capped below 16 here because its newer macOS wheels need macOS 14. Native tools run with plain `subprocess` argument lists.

## Environment, Windows 11 (PowerShell 5.1)

- Blender 5.2.2 LTS: `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`. Use the 5.x API: `sequence_editor.strips`, and set `image_settings.media_type = "VIDEO"` before `file_format = "FFMPEG"`.
- TouchDesigner 2025.32820: `C:\Program Files\Derivative\TouchDesigner\`, for the standalone projects only (below); the pipeline never needs it. The user edits `.toe` files in TD.
- Run native tools (Blender, ffmpeg) with `Start-Process -Wait -NoNewWindow -RedirectStandardOutput <log> -RedirectStandardError <log>`, then read the logs. PowerShell 5.1 turns native stderr into error records under `2>&1`.
- GPU: RTX 5060 Laptop, 8 GB. A final 4K EEVEE render costs ~1.15 s/frame including encode, so a 30 s Short takes ~35 min. Run renders in the background and iterate at the draft profile or a reduced `resolution_percentage`.

## Talking to Blender

- **Live** (Blender GUI open): `python tools/blender_bridge.py --ping | -c CODE | -f FILE` runs Python in the open scene through the Blender Lab MCP add-on on `localhost:9876`. Code returns data by assigning a dict to `result`. Use this to inspect or tweak what the user is looking at.
- **Headless server** (no GUI): start `blender -b scenes/neon_tunnel.blend --online-mode -c blender_mcp`, then use the same bridge.
- **Batch**: `blender -b <file> --python <script> -- <args>`.

Saving a `.blend` leaves a `.blend1` backup next to it. Git ignores it.

## Template scenes

`scenes/*.blend` are templates; their contract is in SPEC §5.6. After changing one, prove it with the pixel-diff tests (rig parity, loop closure; SPEC §10) before committing, and put the measured diff numbers in the commit message.

## Standalone TD projects (`projects/`)

`projects/` holds standalone TouchDesigner projects, one folder per project with a `.toe` of the same name. They aren't part of the pipeline, so the phases and SPEC don't govern them. The Embody-managed ones have their own `CLAUDE.md`, `AGENTS.md` and `.claude/`, all generated by Embody; follow those when working inside a project. `projects/README.md` lists them and says what each one is.

`projects/00-custom-modules/` holds modules the projects share: one COMP per module, saved as a `.tox` that projects load through External .tox with Reload Custom Parameters off. A module is changed inside a project that uses it and saved with its Save Module pulse, which also writes the `.tdxn` and `.py` text versions; never edit those by hand. Its README covers using and changing modules. Read its `LEARNINGS.md` before extracting a feature into a new module: it has the recipe and the measured TD and Embody behaviour.

## Git

Commit code, configs, presets, templates and TD projects. Media and pipeline state stay local: `inbox/`, `work/`, `cache/`, `output/`, `archive/`, `reference/` and audio/video files are covered by `.gitignore`.

`origin` is the **public** GitHub repo `julianhilgemann/audiovisual-animations`, and the user wants it public. Never commit secrets, and keep third-party media out of it.

<!-- BEGIN Embody/Envoy -- auto-managed, do not edit inside -->
## Embody / Envoy -- auto-generated section

*Everything from this heading down to the END marker is rewritten by
Embody on each deploy, so edits inside it are replaced. Put your own
instructions OUTSIDE this section -- above or below, wherever you like.
Embody never touches those, and Uninstall removes only this block.*

<!-- Generated by Embody/Envoy - Do not remove this comment -->
# TouchDesigner Project (powered by Embody + Envoy)

This project uses **Embody** (it externalizes COMP and DAT operators to version-controlled files: `.py`, `.json`, `.xml` and `.tdxn` as text, `.tox` and `.toe` as binary) and **Envoy** (an MCP server inside TouchDesigner that lets you create, wire, parameterize, query and externalize operators).

## No Envoy MCP tools?

`.mcp.json` is deliberately not committed (it hard-codes one machine's venv and bridge paths), so a fresh clone arrives with this file, `AGENTS.md` and `.claude/` but no server. A missing `.mcp.json` never means the project has no path into TD; it means Envoy has not run on this machine yet. Open the project's `.toe` in TouchDesigner; Envoy starts itself from the committed `.embody/project.json` (or turn on **Enable Envoy** on the Embody COMP), writes `.mcp.json`, and the AI client picks it up on restart. With **Embody Mode** on `Advanced - ask first` the write waits for `op.Embody.InitEnvoy()`; with **Configure For** on None nothing is written. While TD is already running you can also point at the port Envoy reports (the **Envoy Status** parameter or `.embody/envoy.json`; 9870 by default, 9871+ when that is busy):

```json
{"mcpServers": {"envoy": {"type": "http", "url": "http://127.0.0.1:9870/mcp"}}}
```

Envoy replaces that with the stdio bridge entry on its next start, which adds `get_td_status`, `launch_td`, `restart_td`, `switch_instance` and a cached tool list while TD is down.

## Critical rules

1. **Read TDXN-externalized COMPs from disk first.** They are YAML with the complete network (operators, parameters, connections, positions, flags, DAT content, annotations), cheaper than MCP round-trips. Never glob for an extension: Embody writes `.tdxn` and still writes `.tdn` for COMPs externalized before 6.1; `externalizations.tsv` or `get_externalizations` names the file (strategy value `tdxn`, `tdn` before 6.2.30). To edit one: change the file, then `import_network` with `clear_first=True` so TD reloads it. For project-wide questions (who references X, the signal-flow topology) grep the project-wide snapshot that Embody's Externalize Full Project writes. Use MCP for live runtime state and for operators that are not TDXN.
2. **Use Envoy for live state and everything else.** Never say a `.tox` or `.toe` is a binary you cannot access: inspect and modify it through the MCP tools.
3. **Never guess paths.** `query_network` on `/` for the real structure; never hardcode `/project1`.
4. **New COMPs go in Embody's container.** `execute_python` with `result = op.Embody.parent().path` returns the same home every run. Build in `ui.panes.current.owner.path` only when the user has deliberately navigated into a content network, never treat the bare root `/` as that home, and never build under `/local`. See `/create-operator`.
5. **Never edit `externalizations.tsv`** (Embody owns it), and always use forward slashes in paths.
6. **Verify TD behavior before asserting it.** For an unfamiliar operator, API or file format: `describe_op_type` for the real parameter names, `get_docs` for the official page. Do not invent TD features.
7. **Check errors after each group of creations**: `get_op_errors` with `recurse=true` once the group is wired and positioned. When a result looks wrong or a call fails, read the `_logs`, `_effects` and `recovery_hints` on the response, then `get_logs`; the log files in Embody's `Logfolder` hold the full history.
8. **Annotate groups, not operators**: `create_annotation` around each logical cluster; OP comments are a last resort.
9. **Batch repetitive calls**: never 3+ individual calls to the same tool. `batch_operations` for positioning, connecting, parameters and flags; `execute_python` for computed or looped logic.
10. **Prefer the operator-creating tools** (`create_op`, `copy_op`, `create_extension`) over raw `execute_python`: they auto-position, lint layout and auto-externalize when the `Autoexternalize` preference asks for it, and a `copy_op` gets a fresh externalization of its own.
11. **Load the relevant skill BEFORE acting.** Skills are prerequisites, not reference:
    - `/mcp-tools-reference` before the first MCP call of a session
    - `/create-operator` before `create_op`, `copy_op`, `set_op_position`, or any `execute_python` that creates or moves operators
    - `/manage-annotations` before `create_annotation` or `set_annotation`
    - `/create-extension` before `create_extension`
    - `/externalize-operator` before `externalize_op` or `save_externalization`
    - `/td-api-reference` before writing TD Python (`execute_python`, `set_dat_content`, `edit_dat_content`); its `references/background-work.md` before any HTTP fetch or background work; its `references/heavy-build-safety.md` before any heavy build
    - `/parameter-design` before creating or designing custom parameters
    - `/glsl-shaders` before writing GLSL or creating a glslTOP, glslmultiTOP, glslMAT or glslPOP
    - `/operator-gotchas` before wiring TOP, CHOP, MAT, DAT, light, camera or instancing operators you have not built before
    - `/pop-networks` before POP operators, particle systems or GPU geometry
    - `/visual-aesthetics` before building or refining anything shown on screen
    - `/movie-export` before recording or exporting any movie or image sequence
    - `/testing` before declaring a build, fix or show done, and before any soak or performance test (`run_soak_test`)
    - `/debug-operator` when diagnosing operator errors
    - `/td-recovery` when connectivity has not self-healed after about 15 s
    - `/multi-session-etiquette` the moment a `_peers` advisory or a second session appears
    - `/merge-divergent-tox` when a merge or rebase conflicts on a `.tox` or `.toe`

## How to work

- Verify that the file you are about to edit is the one that produces the behavior; grep and trace before changing it. Minimal, targeted changes; no speculative abstractions.
- State the hypothesis, verify with evidence, then fix. Define success criteria first and loop until they are verified; checkpoint after each significant step.
- Fail loud: "done" with anything skipped, or "tests pass" with any skipped, is wrong. Surface conflicts between rules instead of averaging them.
- Visual TOP work is output-first: create an Out TOP `out1` with its display flag on BEFORE building the chain and keep the chain wired into it. Success is a captured, assessed frame (`capture_top`, `capture_op`), never a black or empty one.
- Guard performance: `get_project_performance` before and after cook-heavy builds; stop and diagnose on the `performance.md` thresholds.

`/brief <request>` compiles a conversational ask into a task brief in `briefs/` (skills to load, anchors, success criteria, gates) that the work then executes from; suggest it for substantive multi-step asks. `/collab` switches the session to thinking-partner mode (one small step at a time in the visible output, the next decision handed back); `/brief` or "just build it" returns to the autonomous default.

## Envoy, Convoy, permissions

- Envoy runs on the port it allocates (**Envoy Port**, 9870 by default, or the next free port above it) and writes `.mcp.json` when it starts.
- With **Enable Convoy** on, `convoy_*` tools relay work to other Convoy-enabled machines on the trusted LAN. Every lifecycle action needs a unique `idempotency_key` and the node's CURRENT runtime id; fetch remote results only through `convoy_get_artifact` / `convoy_save_artifact` (a remote path in a result is text, never a local file). Reach remote nodes through Convoy, not SSH; move code by git (push here, `convoy_git` fetch/pull/switch there, optionally in a worktree) and single files with `convoy_send_file` (the "Choosing the channel" section of the mcp-tools-reference coordination file).
- Embody deploys `.claude/settings.local.json` once (never overwriting yours) pre-allowing the Envoy tools per the **Tool Permissions** posture; edit its `permissions.allow` to tighten or loosen.

## Python files and packages

- Create Python files by creating the Text DAT in TD (`create_op`), writing it (`set_dat_content`), then `externalize_op`; Embody writes the file. Never set `file` or `syncfile` yourself.
- Extensions: promoted (capitalized) methods are called on the COMP (`op.X.DoSomething()`), everything else through `op.X.ext.X.helper()`; never cache extension references, they go stale on reinit. Detail: `td-python.md`.
- Third-party packages live in the project venv (`.venv/` beside the `.toe`, importable from any DAT or extension). ASK THE USER before adding one, then `op.Embody.InstallPackages(['pkg>=1.0'])` via `execute_python` (plain name-based requirements only, wheels only, recorded in the committed `.embody/project.json`). Never call pip or uv yourself, never install packages TD bundles (numpy, opencv), and treat a logged "restart TouchDesigner" notice as authoritative. Packages declared by other machines need the user's explicit `op.Embody.ApplyDeclaredExtras()`. External scripts run under `op.Embody.VenvPython`.

## Key references

The TD wiki is https://docs.derivative.ca (`get_docs` reads the offline mirror first). `.claude/rules/` holds the always-on rules: network layout, TD Python, parameters, performance, connectivity, multi-session, worktrees, TDXN economy, MCP safety.
<!-- END Embody/Envoy -->
