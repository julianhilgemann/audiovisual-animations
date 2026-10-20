# Learnings: pruning a project split out of econ-sonification

`time-series-wavetable/`, `touch-the-sonogram/` and `caleidoscopic-sonogram-video/` were split out of `econ-sonification/`, and each one started with all three COMPs in `project1/`: `series_synth`, `audioreactor` and `musicvideo`. On 2026-10-21 all three were pruned to their one COMP: `touch-the-sonogram` (`d3632e5`), `time-series-wavetable` (`a745d03`) and `caleidoscopic-sonogram-video`. These are the notes from those runs. Use them for any future project that has to be split out and pruned the same way. Copy this file into the project folder you're working on. It isn't an Embody-generated file, so Embody won't overwrite it the way it overwrites `CLAUDE.md`.

## 1. Connect Envoy first

**If your Claude Code session already has the Envoy tools** (from working on another project), you don't need to restart. Close the old project in TouchDesigner, open the new `.toe`, and call `get_td_status`; it lists the new instance on 9870. Then call `switch_instance('<toe name>')` so the session is pinned to it. That's how the second project was done. The rest of this section is for a session that starts with no Envoy tools.

**Symptom:** TouchDesigner is running and Envoy listens on 9870, but Claude Code shows no `mcp__envoy__*` tools, or `envoy` fails with `CONNECTION_CLOSED`.

**Cause:** the project folder's `.mcp.json` still points at the deleted `projects/econ-sonification/` venv and bridge. Both other folders have this stale file right now. Embody treats the git root as its AI root, so Envoy writes the fresh config to the **repo root** (`../../.mcp.json`), not into the project folder.

**Fix:**
1. Close any other TouchDesigner project, so this one gets port 9870. Open `<project>.toe`.
2. Open the repo root's `.mcp.json`. Its `command` must be `projects/<this-project>/.venv/Scripts/python.exe`. If it names a different project, Envoy hasn't started for this one yet. Wait for the Embody toolbar to show the port.
3. Copy the root `.mcp.json` over `projects/<project>/.mcp.json`. Both are gitignored.
4. Restart Claude Code in the project folder with `/exit`, then `claude --continue`, and approve `envoy`.
5. Call `get_td_status`. Its `active_instance` must be this project.

Don't write your own HTTP client against Envoy's port. The auto-mode classifier blocks it as a workaround.

## 2. Map before you cut (read-only)

| Folder | Keep | Remove |
|---|---|---|
| `caleidoscopic-sonogram-video/` (done) | `musicvideo`, now `caleidoscopic_sonogram_video` | `series_synth`, `audioreactor`, `null_reactor` |
| `time-series-wavetable/` (done) | `series_synth`, now `time_series_wavetable` | `audioreactor`, `musicvideo` |
| `touch-the-sonogram/` (done) | `audioreactor`, now `touch_the_sonogram` | the other two |

The root-level extras differ per project, so map each one live:
- `time-series-wavetable` had only `null_dashboard`, one annotation and a correct `synth_controls`.
- `touch-the-sonogram` had `null_reactor`, `null_musicvideo` and three annotations.
- `caleidoscopic-sonogram-video` had the same set, but its backdrop (`null_reactor`) showed the outgoing COMP. The kept COMP and its null were moved up into the free slot, and the null got the display flag, so all three projects share one layout.

**Sub-COMPs with cooking off:** in `caleidoscopic-sonogram-video`, the kept COMP's `data` and `engine` had cooking off by design. The music video is driven by its track, so the Bundesbank series and the drone were idle there, and `MusicVideoExt` never implemented Fetch. In a second pass they were trimmed too:
- deleted `data`, `engine` and `synth_controls`;
- deleted 7 parameter pages (`Data`, `Wavetable`, `Shape`, `Pitch`, `Filter`, `Output`, `Sound Mod`; 31 parameters);
- removed those pages from `_PAGE_ORDER`.

`activeOps` didn't change, so the idle parts cost nothing at runtime; the cut was 133 operators.

How to remove leftover parameters safely:
- Only parameters **not** in the extension's `_PAR_SCHEMA` can go. `ensurePars()` recreates schema parameters on every reinit.
- Check for readers outside the deleted COMPs in two forms: `par.X` in expressions, and `p.X` in scripts that alias `p = parent.Caleido.par`.
- Some leftover pages are still used. Here the legacy `Visual` parameters feed `viz/glsl_field`, and the `Inputs` page (camera, mic, background learning) feeds `sense`. Those stay.

Things to check in `/project1`:
- **What's actually live:** read `allowCooking` on each COMP. Don't trust the annotations. One said `audioreactor` was "parked (cooking off)" while it was the only COMP cooking. Cooking on doesn't mean it costs anything, though: in `time-series-wavetable`, `audioreactor` had cooking on, but `activeOps` didn't change after deleting it, because nothing pulled its output.
- **Root-level extras:**
  - `null_reactor` / `null_musicvideo` are Null TOPs. The one with its display flag on is the network backdrop.
  - `synth_controls` is a Parameter COMP. Its `op` is an absolute `/project1/audioreactor`, and its `pagescope` lists `Gate Amp*`, which are series_synth pages. Repoint it or delete it.
  - `annotate1` to `annotate3` have stale text.
- **Cross-references:** the three COMPs don't reference each other, but sweep to confirm. Scope the sweep to the COMP you keep, because `musicvideo` and `audioreactor` share the shortcut `Reactor`.
- **`data/stats_series` + `out_stats`:**
  - Unused in `audioreactor` (removed).
  - **Used in `series_synth`**: `viz/labels/labels_lib.py` reads `data/stats_series` for the dashboard. Keep it.
  - In `musicvideo`, probably unused. Confirm before deleting.
- **Out DAT order:** a COMP's output connectors are numbered by its Out ops. In `data`, `out_series` is connector 0 and feeds `engine`; `out_stats` is 1 and feeds nothing. Read `outputConnectors` before deleting an Out op, because removing a lower index shifts the wires above it.
- **The About page** (`Build`, `Date`, `Touchbuild`) belongs to Embody. Leave it.

The reference sweep (`execute_python`; set `KEEP` and `PAT`):

```python
import re
KEEP = '/project1/series_synth'          # the COMP you keep
PAT = re.compile(r'audioreactor|musicvideo|null_reactor|stats_series|out_stats')
hits = []
for o in [op(KEEP)] + op(KEEP).findChildren() + [x for x in [op('/project1/synth_controls')] if x]:
    for p in o.pars():
        if p.mode == ParMode.EXPRESSION and PAT.search(p.expr): hits.append((o.path, p.name, p.expr))
        elif p.mode == ParMode.BIND and PAT.search(p.bindExpr): hits.append((o.path, p.name, p.bindExpr))
        elif p.mode == ParMode.CONSTANT and isinstance(p.val, str) and PAT.search(p.val): hits.append((o.path, p.name, p.val))
    if o.isDAT and PAT.search(o.text): hits.append((o.path, 'TEXT', sorted(set(PAT.findall(o.text)))))
result = hits
```

A `Connector` has no `.path`. Use `conn.owner.path`.

## 3. Remove through Embody, in this order

```python
emb = op.Embody.ext.Embody
t = emb.Externalizations
comp = '/project1/audioreactor'
rows = [(emb._cellVal(i, 'path'), emb._cellVal(i, 'rel_file_path'))
        for i in range(1, t.numRows) if emb._cellVal(i, 'path').startswith(comp + '/')]
for path, rel in rows:
    emb.removeListerRow(path, rel, delete_file=True)   # child DAT rows + their files
emb.removeTDXNEntry(comp, delete_file=True)           # the COMP row + its .tdxn
```

Then delete the COMP, its root null and its annotations with `delete_op` in one `batch_operations` call.

- **Why child rows first:** `remove_externalization_tag` on a TDXN COMP drops only the COMP's own row, so the child rows would stay behind.
- **Why not delete first:** deleting the operator before untracking it leaves the files on disk (`Filecleanup` is `keep`) or opens a continuity dialog.
- **One DAT inside a kept COMP:** `removeListerRow` on its row, then `delete_op`.
- **Annotations:** always `delete_op`, never `.destroy()`. Otherwise the stale entry in the `.tdxn` brings them back on the next load.

## 4. Rename

| Thing | Convention | touch-the-sonogram |
|---|---|---|
| Folder and `.toe` | kebab-case | `touch-the-sonogram` |
| Main COMP | same words in snake_case (TD names can't contain hyphens) | `touch_the_sonogram` |
| Parent shortcut and extension name | one CamelCase word, the same for both | `Sonogram` |
| Extension DAT and class | `<ProjectInCamelCase>Ext` | `TouchTheSonogramExt` |
| Parameter Execute DAT | `parexec_<short>` | `parexec_sonogram` |
| Root output Null | `null_<short>` | `null_sonogram` |

The user's rule: the COMP is named after the folder; everything else uses one short word.

| | COMP | shortcut / ext name | class | parexec | root null |
|---|---|---|---|---|---|
| `time-series-wavetable` (done) | `time_series_wavetable` | `Wavetable` | `TimeSeriesWavetableExt` | `parexec_wavetable` | `null_wavetable` |
| `caleidoscopic-sonogram-video` (done) | `caleidoscopic_sonogram_video` | `Caleido` | `CaleidoscopicSonogramVideoExt` | `parexec_caleido` | `null_caleido` |
| `touch-the-sonogram` (done) | `touch_the_sonogram` | `Sonogram` | `TouchTheSonogramExt` | `parexec_sonogram` | `null_sonogram` |

Steps:
1. **COMP:** rename it with `rename_op`, then run `op.Embody.Update()`. Embody moves the `.tdxn` and every child file, rewrites each DAT's `file` parameter and updates the table. Read the table back to confirm the new paths.
2. **Identity, in one `execute_python` call:**
   - Rename the extension DAT and the parexec DAT.
   - Edit the DAT text: the class name, docstrings and `debug()` labels; `parent.Old.ext.Old.` becomes `parent.New.ext.New.`, and `parent.Old.` becomes `parent.New.`.
   - Rewrite every `par.expr` and `par.bindExpr`.
   - Set `parentshortcut`, `ext0name` and `ext0object`.
   - Pulse `reinitextensions`.

   Before applying anything, check that every targeted text replacement matches exactly once. It must be one call because script DATs cook every frame and the parexec fires on any parameter change, so a half-renamed state throws.

   Match the shortcut with a word-boundary regex (`parent\.Synth\b`), not `'parent.Synth.'`: `labels_lib` has a bare `synth = parent.Synth` at the end of a line.

   In the same call, set any constant OP-reference string (`synth_controls.op = 'series_synth'`); it doesn't follow the rename.

   Scale: touch-the-sonogram rewrote 48 expressions and 7 DATs; time-series-wavetable rewrote 76 expressions and 8 DATs.
3. **DATs:** run `op.Embody.Update()` again so Embody follows the DAT renames. Keep this separate from the COMP rename.
4. **OP references:** fix any constant OP-reference parameter that held the old path. Use the sibling name (`touch_the_sonogram`), never an absolute path.
5. **Disk:** editing `.text` in TD on a `syncfile` DAT writes the file, **but only when the DAT's parent COMP is cooking.** In `caleidoscopic-sonogram-video`, the four DATs inside `data` and `engine` (both with cooking off) kept their old text on disk while the live text was correct. `save_externalization` doesn't help: it skips DATs as "file-synced automatically by TouchDesigner". What worked was writing each one with `d.save(os.path.join(project.folder, d.par.file.eval()))`. Always compare live text with the file for every externalized DAT, not only by grepping:

   ```python
   import os
   stale = []
   for d in op(KEEP).findChildren(type=DAT):
       f = d.par['file'].eval() if d.par['file'] is not None else ''
       if f and open(os.path.join(project.folder, f), encoding='utf-8').read().replace('\r\n', '\n').rstrip() != d.text.replace('\r\n', '\n').rstrip():
           stale.append(d.path)
   result = stale
   ```

## 5. Verify, save, commit

- Take a baseline before touching anything: `get_project_performance`, a `capture_top` of `out1`, and `get_chop_data` on the audio null (`engine/null_audio`).
- `get_op_errors('/project1', recurse=True)` returns 0 errors and 0 warnings.
- Capture `out1` twice, a few seconds apart. Both should report `Quality: OK`, and the frames should differ.
- Audio still plays: `engine/null_audio` std stays around 0.2.
- Fetch round trip: set **Status** to a marker, pulse **Fetch**, and read **Status** in the *next* call, because pulse callbacks run after the frame. It should read "N months YYYY-MM .. YYYY-MM". This one pulse exercises the parexec, the extension and the web-client callbacks.
  - First check that the extension has `Fetch`. `CaleidoscopicSonogramVideoExt` doesn't, so there the pulse does nothing and the marker just overwrites the user's **Status**. Note the old value and put it back.
  - In a track-driven project, check the audio on `sense/audiofilein_track` instead of `engine/null_audio`, which is empty while the drone is off.
- Compare performance with the baseline. A single `frameTimeMs` reading jitters by a few ms, so judge fps, dropped frames and `totalOps`. touch-the-sonogram: 60 fps and 934 fewer operators. time-series-wavetable: 61 fps and 837 fewer operators.
- Grep `project1/` on disk for every old name, and run the live-versus-file comparison from section 4. Expect no matches and no stale DATs.
- `save_project`: the job reports `<name>.1.toe`. TD's incremental save also rewrites `<name>.toe` with an identical hash, and git ignores the numbered copy.
- `diff_tdxn` returns `changed_count: 0`.
- Stage only `projects/<name>` and `projects/README.md`. Renames show as `R`; git may pair identical files from different old COMPs, which is harmless.
- Ledger: `announce_task` at the start; at the end, `update_task(status='committed', commit=<sha>)` and `release_scope`.

## Small things that cost time

- **A rename that only changes letter case** (`FerroScope` → `ferroscope`, done in `projects/ferroscope`):
  - Embody updates its table, but on Windows the folder on disk keeps the old casing. Fix it with two renames through a temporary name.
  - Git (`core.ignorecase=true`) keeps the old path in its index; fix it with `git rm --cached <old path>` and then `git add <new path>`.
  - Otherwise a Linux or macOS clone gets a different folder from the one Embody's table names.
- To archive a COMP before deleting it, use `op.Embody.ExportPortableTox(target=comp, save_path=...)`. Then load the `.tox` into `/project1` once and compare child and parameter counts against the live COMP, so you know the archive opens.
- `findChildren(type=annotateCOMP)` misses annotations, because they're utility ops. Use `get_annotations` instead.
- A shell `ls`/`find` inside `project1/` was blocked once by the auto-mode classifier. Glob and PowerShell `Get-ChildItem` worked.
- `projects/README.md` says Envoy writes `.mcp.json` into the project folder. It writes it at the repo root (section 1).
