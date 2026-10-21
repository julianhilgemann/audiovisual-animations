# Learnings: turning a project feature into a shared module

On 2026-10-21 ferroscope's sources and transport became `source-deck/`, the first module here (`7e229f1`; the transport itself was built just before, in `22fcd6d`). These are the notes from that run, so the next extraction starts from the answers instead of rediscovering them. Every TD fact below was measured on TouchDesigner 2025.32820 with Embody 6.2.72, using scratch COMPs that were deleted afterwards.

## 1. The fast path

Decisions already made (section 5 says why). Steps in order:

1. **Map the feature.** List its operators, the host parameters they read (`parent.Host.par.*` in expressions), the host operators that read its outputs, its script DATs and their Embody tags, and which host parameters presets write (the `presets` table rows).
2. **Baseline.** Pause at a fixed position and save the output as a numpy array in the scratchpad (`np.save(path, op('null_video').numpyArray())`). Record every parameter value you're about to touch.
3. **Create the module inside the host**, next to the feature: a Base COMP with `parentshortcut` set to one CamelCase word (`SourceDeck`). Set `allowCooking = False` while building, or the copies start webcams and play audio twice.
4. **Parameters.** `page.appendPar(name, par=hostPar)` copies style, label, default, range, menu and read-only, **but not the help text**: set help again, in wording that doesn't name the host. Get-or-create with `comp.par['Name'] is None`; `comp.par.Name` raises when it's missing.
5. **Operators.** `module.copyOPs([...])` keeps the wires between copied ops. Then, in the same call:
   - rewrite `parent.Host.` to `parent.Module.` in every expression;
   - on copied script DATs, clear `file` and `syncfile` and remove the Embody tags (they still point into the host's folder);
   - add `outTOP` / `outCHOP` (set `connectorder` for the second connector) and `inTOP` / `inCHOP` fed by a constant for when nothing is wired;
   - make the host keep its own In ops and output Nulls, so nothing downstream changes.
6. **Switch over.** Untrack the host's moved DATs first (`remove_externalization_tag(op, delete_file=True)`). Then in one call:
   - set `active = False` on the host's old frame-driven script (two transports on the same parameters fight);
   - bind each module parameter to the host's: `module.par.X.bindExpr = 'parent.Host.par.X'`;
   - destroy the host's originals;
   - wire host In ops into the module, and the module's outputs into the host Nulls (`null.inputConnectors[0].connect(module.outputConnectors[1])`; connecting to the COMP itself fails);
   - turn cooking on.
7. **Pulses don't bind.** The host's parameter callback presses the module's pulse; see `_deckPulse` in `ferroscope/project1/ferroscope/controls_callbacks.py`.
8. **Verify.** The baseline frame must match exactly (`np.abs(now - base).max() == 0.0`). Then test behaviour through the **host's** parameters, because those are what the user touches.
9. **Release.** Give the module a Save Module pulse (copy `_saveModule` and `_writeSnapshot` from `source-deck/deck_callbacks.py`). Set the External .tox Path on the instance while Enable External .tox is still off, press Save Module, then turn on Enable External .tox, turn off Reload Custom and Reload Built-In Parameters, and reload. Check that the binds survived.
10. **Fresh-load test.** `op('/project1').loadTox(path)` with nothing bound: `get_op_errors` must be 0 and the outputs must carry signal. Delete it.
11. **Document and commit.** Add the module's README and a row in `README.md`. The user saves the host `.toe` (Ctrl+S) before the commit, because the instance's binds and External .tox setting live only there.

## 2. External .tox, measured

| Setting or action | What happens |
|---|---|
| Reload Custom Parameters **on** (the default) | Every reload resets the instance's custom parameters to the `.tox` values and drops its binds. The project's settings are lost. |
| Reload Custom Parameters **off** | The instance keeps its values and binds across reloads, and parameters newly added to the `.tox` still appear. |
| Tags on the module COMP | They come from the `.tox` on every reload; tags added on the instance are wiped. Ship tags the host needs (`tdxn_exclude`) inside the `.tox`. |
| `par.val = x` on a bound parameter | Stays in BIND mode and writes through to the master. Works in both directions, so a module script can write its own bound parameters. |
| Switching a parameter to CONSTANT | TD keeps the old `bindExpr` and `expr` text. A `.tox` saved that way makes every new project report "Error occurred while evaluating bind parameter". Clear `bindExpr` and `expr` before saving. |
| `Par.bindMaster` | The host parameter a bound one points at. Use it for attributes that don't bind, such as `normMax` (the slider range). |
| Relative External .tox Path | Resolved against `project.folder`, so `../00-custom-modules/<module>/<name>.tox` works for every project in `projects/`. |
| `COMP.save(path)` | Keeps the COMP's tags, comment and color in the `.tox`. |

## 3. Embody, measured

- **Embody ignores External .tox.** Its `.tdxn` export copies the child's whole network into the host's file and drops `externaltox` and the reload toggles. The bare `tdxn_exclude` tag removes the module from the host's `.tdxn`, but the wires to and from it are still written (`inputs: [source_deck]`, `- source: source_deck` / `out: 1`).
- **This repo runs Embody in `export` mode** (`op.Embody.par.Tdxnmode`). The `.toe` is the source of truth, and nothing is stripped or rebuilt on save or open; strip-on-save and create-on-start only exist in `full` mode. A test that rebuilds a COMP from its `.tdxn` doesn't reflect what the user experiences.
- **Don't test with `ext.TDXN.importNetworkFromFile(..., clear_first=True)`.** It restored the nested CRT COMP as an empty shell, so its two wires failed. It also re-spawned the GLSL TOPs' default `*_compute` DATs that the network had deleted, and reset `tdxn_exclude:<par>` parameters to their defaults. An autosave then wrote all of that to disk. Repairing it took a careful diff against `git HEAD`.
- **`ExportNetwork` skips anything under `/sys`.** A copy staged in `/sys/quiet` exports as `operators: []`. Load the saved `.tox` into a normal network for the export, then delete it (`_writeSnapshot` does this).
- **Tab-indented DAT text** is written as one escaped YAML line, which makes a useless diff. Write each script as its own `.py` and tag the temporary copy's DATs `tdxn_exclude:dat_content`.
- **Drop `source_file`, `exported_at` and `network_path`** from the snapshot; they change with every save and host.
- **`tdxn_exclude:<par>`** on a COMP keeps runtime values (playheads, time readouts, audio cue points) out of its `.tdxn`, so playback doesn't show up in diffs.
- **Envoy draws its mascot** (`envoy_bot_*` annotations) inside whichever COMP it's working on. Delete them from the release copy. Embody's exporter already leaves them out.

## 4. TouchDesigner gotchas hit on the way

- **Pulse callbacks run after your script returns.** A Save Module pulse followed by a reload pulse in the same call reloaded the old `.tox` first, and the new code was lost. Pulse in one call and check in the next; never pulse save and reload together.
- **Edits inside an External .tox COMP are lost on the next reload** unless Save Module ran. Saving the `.toe` doesn't save the module.
- **`Par.page` and `Par.order` are writable**, so parameters move between pages without being recreated. `comp.sortCustomPages(*names)` orders pages.
- **`/sys/quiet`** (cooking disabled) is the right place for a clean copy to save as `.tox`, but not for the Embody export.
- **Audio File In:**
  - Specify Index mode is sample-exact (zero residual against Sequential, with a constant 0.2 s latency). But a stopped index loops the last 735-sample chunk as a buzz, and it can't play backwards.
  - Sequential with `play` and cue fades pauses and jumps cleanly; a cue lands on the target sample in the next frame. Use Sequential and cue it.
  - Sequential audio only advances while something cooks it.
  - The Info CHOP gives `sample`, `file_length` and `open`; Audio File In has no Python members for position or length.
- **Movie File In:** use Specify Index with Index Unit seconds. `numSeconds`, `index` and `rate` are Python members. Each jump to a new spot in a 720p H.264 file costs 25–53 ms; an audio cue costs nothing.
- **A frame-start Execute DAT** that reads about 20 parameters and writes a few costs about 0.02 ms per frame.

## 5. Design choices, and why

- **The host's parameters are the masters; the module's bind to them.** The host panel and presets stay unchanged, the host's `.tdxn` keeps readable values, and the same module still works on its own values in a project that binds nothing.
- **No extension.** Module DATs plus one parexec dispatcher, matching the repo's style. The module's interface is its parameters, pulses included.
- **The code lives only in the `.tox`.** The `.tdxn` and `.py` files are generated by Save Module, for reading and diffing.
- **Reload Built-In Parameters is off too**, as a precaution. The released `.tox` is saved with Enable External .tox off, and with built-in reloads on, that value might be applied to the instance. This wasn't tested.

## 6. Checks before you commit

- Load the released `.tox` into `/sys/quiet`, then delete it. Expect the right tags (`tdxn_exclude`), the right child count (`findChildren(maxDepth=1, includeUtility=True)`), and an empty `[p for p in comp.customPars if p.bindExpr or p.expr]`.
- Each generated `.py` minus its 3 header lines equals the live DAT text.
- `get_op_errors` on the host returns 0 errors. Ferroscope's `glsl_fluid` cook-loop warning is older and unrelated: its uniform reads `me.width / me.height`.
- `get_project_performance`: fps and dropped frames unchanged. Memory can briefly rise after test loads and comes back down.
- After the user's Ctrl+S, `diff_tdxn` returns `changed_count: 0`.
