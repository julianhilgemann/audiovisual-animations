# Stem tunnel (Blender)

The neon lines tunnel from [`blender/audio-tunnel`](../audio-tunnel/README.md), driven by a run's `controls.json` from any of the six input methods (SPEC §16): a generated loop (A), a finished master (B), master and stems (C), master, stems and MIDI (D), any stems as numbered slots (E), or one complex track measured from every side (F). Hits, loudness and features are the modulators, the master is the soundtrack, and one command renders and encodes a finished YouTube Short. It is the central hub: one scene, one mapping per method in `mappings/`, any number of shapes and looks in `styles/`, and a tuner to adjust all of it by hand for one song (SPEC §6).

```
uv run datapipe short gen --preset neon_house --seed 42          # A: compose, render, encode, check
uv run datapipe short master inbox/master/song.wav --preview      # B: half size, 8 samples
uv run datapipe short stems inbox/stems/mytrack                   # C
uv run datapipe short midi inbox/midi/mytrack                     # D
uv run datapipe short slots inbox/slots/mypiece                   # E: a folder of stems, or one file
uv run datapipe short deep inbox/deep/track.wav                   # F
uv run datapipe short stems inbox/stems/mytrack --style hex_prism # another shape and look
uv run datapipe tune stems                                        # tune the latest stems run in Blender, by hand
uv run datapipe short --run work/stems/latest --preview           # render a run again, with what you tuned
```

Output: `output/<method>/<run>.mp4`, a `.json` sidecar with the checks (and which mapping, style and keyframes it used), and a `.png` thumbnail from the twist (or the drop). The run folder keeps the same MP4, `controls.json`, `render.log` and `scene_baked.blend` (open it to scrub, play and tune: the master is on the timeline, and the tuner comes with it, see below); a song's run also has `report.png`, what the analysis found.

## Tune by hand

The pipeline is automatic, but every part of the picture can be adjusted for one song and then rendered exactly as adjusted.

```
uv run datapipe tune stems inbox/stems/mytrack     # analyse a song, then open its run
uv run datapipe tune --run work/midi/latest        # an existing run
uv run datapipe tune deep                          # the method's latest run
uv run datapipe tune gen --preset phonk_180 --seed 5
```

Blender opens on the run with the master on the timeline and a **Datapipe** tab in the 3D view's sidebar (N). Press Play and tune while it plays:

| Panel | What you change | Saved as |
|---|---|---|
| Reactivity: signals | for each look signal (kick, bass, energy, ...): its sources and their weights, add any of the run's sources (hits, stems, bands, curves, sections, features), smoothing; a meter shows the signal at the current frame | `mapping.toml` |
| Reactivity: hits, ring, motion | each track's hit envelope (wind-up, decay), the track and level of the light ring, the curve that speeds the tunnel up, the twist's roll and hue | `mapping.toml` |
| Look: Kick, Bass, ... Watermark | every slider of the look (look.toml `[look]`, 48 of them): reactions, base motion, camera, colour, line style, each layer's glow and hue, the watermark's opacity. Hover a slider and press I to keyframe it: keys become the run's automation, e.g. a lens that zooms in through the drop | `style.toml [look]`, `automation.json` |
| Shape | the tunnel's geometry (below); rebuilds as you change it (Auto), in 0.04–0.15 s | `style.toml [shape]` |
| Styles and defaults | load a style; save the current shape and sliders as a style for any song; save the mapping as the method's default | `styles/<name>.toml`, `mappings/<method>.toml` |

A mapping change re-bakes the signals in milliseconds; a slider that moves the camera or the spins (speeds, roll, spins, colour cycling) re-bakes the motion; the rest are drivers and change at once. The panel bakes with this folder's own `stem_tunnel.py` functions, so the scene you tune is keyed exactly as the render will be (`tests/test_tune.py` checks it).

**Save to run** writes `<run>/tuning/stem-tunnel/` (`mapping.toml`, `style.toml`, `automation.json` when something is keyframed), and from then on `datapipe short --run <run>` renders with it; **Render preview** and **Render final** in the panel save and run exactly that, and show the checks. What a render uses is, for each file, the first that exists: `--mapping` / `--style`, the run's tuning, then the look's `mappings/<method>.toml` and the style `[methods.<method>]` or `[looks.stem-tunnel]` names in `config/pipeline.toml` (`default`). The CLI and the sidecar say which. The session is saved as `<run>/tune.blend`, so the template is never overwritten. Keyframes that don't end where they started break the loop's seam, and the seam check says so: use `--no-loop` for such a song, or key the last frame like the first.

**The tuner travels with the .blend.** A run's `scene_baked.blend` (every render saves one) and `tune.blend` carry the panel as a small text block, `datapipe_tuner.py`, that loads `tuner.py` from this repo. Open either in Blender and click *Allow Execution* when Blender asks (or turn on *Auto Run Python Scripts* in Preferences > Save & Load, which skips the question): the Datapipe tab is back on the run, exactly as the file was saved, with nothing re-baked, and Save to run and the Render buttons work as in `datapipe tune`. Blender's own Ctrl+S keeps your changes in the file; Save to run is what a render takes. Without allowing scripts, the file still plays and renders as baked; only the panel is missing. If the repo has moved, the panel can't load: open the run with `datapipe tune --run <run>` instead.

## Shapes and styles

A style (`styles/<name>.toml`) is the shape of the tunnel plus any of the look's sliders; it lists only what it changes, and `look.toml` holds every control with its range, default and help. The geometry is built by `shapes.py` (numpy, 0.04–0.15 s): each layer is a pattern of neon ribbons laid onto a cross-section.

| Control | Options |
|---|---|
| `profile` | `circle`, `polygon` (`sides` 3–12, `corner_round`), `star` (`sides` points, `profile_depth`, `corner_round`), `flower` (`sides` lobes, `profile_depth`); `profile_angle` turns it; every profile has the perimeter of a circle of `radius`, so cells keep their size |
| `symmetry`, `cell_depth`, `line_width` | cells around the tunnel; a row's length relative to a cell's width (speed counts rows, so the rhythm stays); ribbon width |
| `walls` | `maze` (the reference look), `grid`, `diamonds`, `chevrons`, `hexes`, `circuit`, `stripes`, `rails`, `zigzag`, `truchet` (random quarter circles, `seed`), `dots`, `none` |
| `portals` | `crenel` (the reference look), `rings`, `spokes`, `teeth`, `triple`, `frame`, `none`; `portal_every` rows, `portal_inner` the opening |
| `outer_pattern`, `outer_size` | `ladder` (the reference look), `rails`, `helix`, `grid`, `dots`, `none`; the shell's radius relative to the tunnel |
| `twist`, `wave`, `wave_count` | the cross-section turns along the tunnel (cells per row, in eighths); the tunnel swells and narrows |

The live sliders added to the reference look's: `hue_base`, `hue_depth`, `hue_across`, `saturation`, `line_edges`, `line_core`, `line_sharp`, `fill_glow`, `wave_amount`, `view_far`, `cam_orbit` (the camera off the axis, orbiting with the roll), and `walls_glow`, `portals_glow`, `outer_glow`, `walls_hue`, `portals_hue`, `outer_hue` per layer.

**The watermark.** A white, letter-spaced *hyperadapted* in Blender's own sans-serif sits at the top centre, barely there: `watermark` is its opacity (0.02 by default; 0 hides it). It is a text object just in front of the camera, parented to it and scaled against the lens, so it holds still while the tunnel rolls and the kick punches the zoom. Its light stays under the glare's threshold, so it doesn't bloom, and it doesn't move the checks: a preview of the same run counted the same flashes at the same mean luminance (0.058) with it as without.

Styles in the repo: `default` (the reference look), `hex_prism`, `square_circuit`, `star_vortex`, `flower_tube`, `speed_rails`, `truchet_maze`.

**The loop still closes on any shape.** `shapes.periods()` works out after what distance the tunnel repeats (the walls' pattern rows, `portal_every`, the bulges, and for a twist the rows until the turn is a symmetry of the whole cross-section) and after what angles the roll, portals and shell repeat (the pattern's cells around, combined with the profile's symmetry). The template stores them on NeonControls (`_period_*`), and the motion closes on them (`tests/test_tune.py` checks the vertices of every style and more against them).

## How a run becomes a Short

| Stage | Where | What |
|---|---|---|
| Audio | A: `datapipe gen` (`dawdreamer/`); B to F: your files (`src/datapipe/song/ingest.py`) | score, stems, mastered mix; or your master, stems and MIDI, lined up at 48 kHz |
| S3 controls | `src/datapipe/gen/controls.py`, `src/datapipe/song/controls.py`, `slots.py` (E), `deep.py` (F) | per frame: each track's hits (score, MIDI or detected onsets), each stem's loudness, the mix's loudness, brightness and bands, beat and bar phase, curves, sections, and E's and F's features → `controls.json` |
| S4 mapping | `mappings/<method>.toml` (or the run's tuning), `stem_tunnel.py` (in Blender) | modulators → the look's signals on the `AudioSignals` empty; motion integrated and (by default) closed on the loop |
| Style | `styles/<name>.toml` (or the run's tuning), `shapes.py` | the sliders onto NeonControls, the shape rebuilt if it isn't the template's, keyframes from `automation.json` |
| S5 render | Blender, headless, EEVEE | one PNG per frame at 1080×1920, 60 fps (480 for a loop, the song's length otherwise), plus frame n + 1 for the seam check |
| S6 encode | `src/datapipe/render.py` (PyAV) | H.264 High, yuv420p, BT.709 matrix and tags, TV range, GOP 30, 2 B-frames, CRF 16 (x264 slow), AAC 320 kb/s 48 kHz, faststart; the audio is trimmed first if its AAC encode would overshoot −1 dBTP (it does by up to 0.4 dB on distorted bass) |
| S7 checks | same | format, length, faststart, true peak (and −14 LUFS for a loop), sync of the ring's track (the kick, E's `slot1`, F's `low`), seam, flashes |

The shared math (envelopes, followers, loop closure) is `src/datapipe/mapping.py`, the same file in the pipeline and in Blender; `src/datapipe/recipe.py` reads, checks and writes the mapping and style files on both sides.

## What drives what (`mappings/gen.toml`)

| Look signal | Default source | Drives (the reference look's drivers) |
|---|---|---|
| `kick` | the kick's hits, 3-frame wind-up, 9-frame decay | zoom punch, roll jolt, portal squeeze, wall pump, forward burst |
| `kick_light` | the kick's hits × 0.2 | glow and bloom on the kick |
| `bass` | the bass stem's loudness | walls breathe, outer shell swells, haze, roll |
| `energy` | the master's loudness + the riser, smoothed over 12 frames | base glow, bloom, forward speed, colour cycling |
| `hats` | the hats' hits | sparkle wave |
| `mids` | clap and lead hits | portal spin |
| `bright` | the master's brightness + the riser | palette shift |
| `twist` | the story's twist section | hue jump and an extra camera roll: the violation |
| ring | the kick's hits × 0.3 | the light ring racing into the tunnel |

Sources are `hit:<track>`, `stem:<name>`, `mix:loud`, `mix:bright`, `band:<name>` (sub, bass, lowmid, mid, highmid, air), `curve:<name>`, `section:<name>` and `feature:<name>` (E and F, SPEC §16.7); each signal is a weighted sum. A run without a track simply contributes nothing. `[motion] speed_curve` names the curve that speeds the tunnel up (the riser for a loop, `build` for a song). The mapping files are written in the tuner's canonical form (`recipe.dumps_mapping`): the comment after each line comes from `look.toml`, notes about a method go in its header.

The song methods use the same look signals, fed by what they have:

| Look signal | `master.toml` (B) | `stems.toml` (C), `midi.toml` (D) |
|---|---|---|
| `kick`, `kick_light`, ring | detected kicks, weighted by how kick-like they sound | the kick's hits (detected in the stem, or the MIDI) |
| `bass` | the master's sub and bass bands | the bass stem's loudness |
| `energy` | loudness, bar energy and the build curve | the same |
| `hats` | detected hats + the air band | the hats' hits |
| `mids` | detected snares + the mid band | snare, clap and lead hits |
| `bright` | brightness + the build curve | the same |
| `twist` | the drop section: a hue shift and extra camera roll | the same |

E and F have no instrument names, so their mappings give each slot or feature a fixed part of the picture (`report.png` in the run folder labels every row with what it drives, or "unused"):

| Look signal | `slots.toml` (E) | `deep.toml` (F) |
|---|---|---|
| `kick`, `kick_light`, ring | slot 1's transients (ring 0.15, glow 0.3: the ring lit sparse transients late) | low percussive onsets + the percussive onset strength |
| `bass` | slot 2's loudness and low band | sub and bass bands and their onsets |
| `energy` | the master's 3 s loudness + slot 1's onset density | momentary and short-term loudness, percussive loudness, build curve |
| `hats` | slot 3's transients and high band | high onsets, air onsets and band, flatness |
| `mids` | slot 4's loudness + slot 2's transients | mid onsets, harmonic loudness, harmonic change, spectral flux |
| `bright` | brightness + slot 3's flatness | brightness, rolloff, bandwidth, stereo width, harmonic share |
| `twist` | slot 4 playing | the drop section + novelty at every change |

A song doesn't wrap: no envelope runs from the last frame into the first. The look's own sliders (speeds, glow, flash, lens, colours) are custom properties on the `NeonControls` empty in `stem_tunnel.blend`, set from the style at every render.

## The loop closes

Accumulated motion (forward travel, camera roll, portal and outer spin, colour phase) is integrated in Python and baked, not driven by `frame`. Each is closed so frame n + 1 is the same picture as frame 1 (frame 481 for a loop): its rate gets one constant added so the total is a whole number of the shape's periods (for the reference shape: walls repeat every 2 segments in depth; around the tunnel every 2 segments for an even symmetry, portals and the outer shell every segment; other shapes, see Shapes and styles), or is scaled when that would run a forward motion backwards. The render prints what it did (`closure` in the result). In a loop, envelopes and the kick ring's age wrap around the seam too. Measured: frame 481 against frame 1, mean difference 0.00002 to 0.00005; a 23.7 s song (method D), frame 1425 against frame 1, 0.00005. A song with `loop = false` in its `song.toml` (or `--no-loop`) skips the closure and the seam gate.

## Flashes

The checks count full-frame flashes in mean relative luminance (a rise of 0.1 or more, as WCAG 2.3.1 defines them; at most 3 a second). Two things in the reference look flashed:

- **Flying through a portal.** A portal ring sweeping past the camera lifted the whole frame by 0.13–0.17, about once a second. The template adds `near_fade` (NeonControls, default 55): portals fade out as they come within that distance of the camera plane, so they dissolve instead of sweeping bright. Walls and the outer shell are untouched.
- **The kick lighting the frame.** The kick drove glow, bloom and the ring at full strength (`kick_glow` is at its maximum), up to 0.89 relative luminance: a white screen twice a second. `kick_light` and the ring level separate the light from the motion, so the kick still punches (zoom, jolt) but pulses rather than strobes.

With the defaults the 50 % preview of `neon_house` seed 42 has no flashes; the kick pulses lift the frame by 0.02–0.09. Raising `kick_light`, the glow sliders, or a shape that puts more lines in view (more cells, a narrower profile) can bring the strobe back; the check will say so, and the tuner's Render preview shows it.

## Files

| File | What |
|---|---|
| `stem_tunnel.blend` | the template: the reference lines tunnel at `styles/default.toml`, no kaleidoscope, no UI script, drivers on the run signals, `near_fade` on the portals, the watermark |
| `stem_tunnel.py` | runs inside Blender: maps controls onto the look, applies the style, bakes, wires the drivers, renders; `--tune` opens the tuner, `--make-template` rebuilds the template |
| `tuner.py` | the Datapipe panel (`datapipe tune`, and every saved run's .blend) |
| `shapes.py` | the geometry: profiles, patterns, twist and wave, and the periods the loop closes on |
| `look.toml` | every control: the look signals, the sliders and the shape, with ranges, defaults and help |
| `mappings/<method>.toml` | which modulator drives which look signal, per input method: `gen`, `master`, `stems`, `midi`, `slots`, `deep` |
| `styles/<name>.toml` | shapes and looks: `default` and the examples above |

After re-tuning the look in `blender/audio-tunnel/neon_tunnel_audio.blend`, or changing `styles/default.toml`, rebuild the template from it (the sliders come from `styles/default.toml`, the meshes from `shapes.py`, the material from `stem_tunnel.py`):

```
blender -b blender/audio-tunnel/neon_tunnel_audio.blend --python blender/stem-tunnel/stem_tunnel.py -- \
    --make-template blender/stem-tunnel/stem_tunnel.blend
```

## Speed (Apple M1)

EEVEE at 1080×1920: 0.38 s a frame at 32 samples, 0.10 s at the preview's 50 % and 8 samples. A final Short took 4.3 minutes (render 185 s, x264 `slow` encode 52 s, checks 16 s) and is about 70 MB (CRF 16: ~70 Mb/s, far above YouTube's 12 Mb/s guide, which is fine since YouTube re-encodes); a preview takes about 1 minute. Building a shape takes 0.04–0.15 s for 130,000–370,000 vertices.
