# Stem tunnel (Blender)

The neon lines tunnel from [`blender/audio-tunnel`](../audio-tunnel/README.md), driven by a run's `controls.json` from any of the four input methods (SPEC §16): a generated loop (A), a finished master (B), master and stems (C), or master, stems and MIDI (D). Hits and loudness are the modulators, the master is the soundtrack, and one command renders and encodes a finished YouTube Short. It is the central hub: one scene, one mapping per method in `mappings/`.

```
uv run datapipe short gen --preset neon_house --seed 42          # A: compose, render, encode, check
uv run datapipe short master inbox/master/song.wav --preview      # B: half size, 8 samples
uv run datapipe short stems inbox/stems/mytrack                   # C
uv run datapipe short midi inbox/midi/mytrack                     # D
uv run datapipe short --run work/midi/latest --preview            # render a run again, e.g. after editing its mapping
```

Output: `output/<method>/<run>.mp4`, a `.json` sidecar with the checks, and a `.png` thumbnail from the twist (or the drop). The run folder keeps the same MP4, `controls.json`, `render.log` and `scene_baked.blend` (open it, scrub, play: the master is on the timeline); a song's run also has `report.png`, what the analysis found.

## How a run becomes a Short

| Stage | Where | What |
|---|---|---|
| Audio | A: `datapipe gen` (`dawdreamer/`); B, C, D: your files (`src/datapipe/song/ingest.py`) | score, stems, mastered mix; or your master, stems and MIDI, lined up at 48 kHz |
| S3 controls | `src/datapipe/gen/controls.py`, `src/datapipe/song/controls.py` | per frame: each track's hits (score, MIDI or detected onsets), each stem's loudness, the mix's loudness, brightness and bands, beat and bar phase, curves, sections → `controls.json` |
| S4 mapping | `mappings/<method>.toml`, `stem_tunnel.py` (in Blender) | modulators → the look's signals on the `AudioSignals` empty; motion integrated and (by default) closed on the loop |
| S5 render | Blender, headless, EEVEE | one PNG per frame at 1080×1920, 60 fps (480 for a loop, the song's length otherwise), plus frame n + 1 for the seam check |
| S6 encode | `src/datapipe/render.py` (PyAV) | H.264 High, yuv420p, BT.709 matrix and tags, TV range, GOP 30, 2 B-frames, CRF 16 (x264 slow), AAC 320 kb/s 48 kHz, faststart; the audio is trimmed first if its AAC encode would overshoot −1 dBTP (it does by up to 0.4 dB on distorted bass) |
| S7 checks | same | format, length, faststart, true peak (and −14 LUFS for a loop), kick sync, seam, flashes |

The shared math (envelopes, followers, loop closure) is `src/datapipe/mapping.py`, the same file in the pipeline and in Blender.

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

Sources are `hit:<track>`, `stem:<name>`, `mix:loud`, `mix:bright`, `band:<name>` (sub, bass, lowmid, mid, highmid, air), `curve:<name>` and `section:<name>`; each signal is a weighted sum. A run without a track simply contributes nothing. `[motion] speed_curve` names the curve that speeds the tunnel up (the riser for a loop, `build` for a song).

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

A song doesn't wrap: no envelope runs from the last frame into the first. The look's own sliders (speeds, glow, flash, lens, colours) are custom properties on the `NeonControls` empty in `stem_tunnel.blend` (Object Properties > Custom Properties), carried over from the reference scene.

## The loop closes

Accumulated motion (forward travel, camera roll, portal and outer spin, colour phase) is integrated in Python and baked, not driven by `frame`. Each is closed so frame n + 1 is the same picture as frame 1 (frame 481 for a loop): its rate gets one constant added so the total is a whole number of the pattern's periods (walls repeat every 2 segments in depth; around the tunnel every 2 segments for an even symmetry, portals and the outer shell every segment), or is scaled when that would run a forward motion backwards. The render prints what it did (`closure` in the result). In a loop, envelopes and the kick ring's age wrap around the seam too. Measured: frame 481 against frame 1, mean difference 0.00002 to 0.00005; a 23.7 s song (method D), frame 1425 against frame 1, 0.00005. A song with `loop = false` in its `song.toml` (or `--no-loop`) skips the closure and the seam gate.

## Flashes

The checks count full-frame flashes in mean relative luminance (a rise of 0.1 or more, as WCAG 2.3.1 defines them; at most 3 a second). Two things in the reference look flashed:

- **Flying through a portal.** A portal ring sweeping past the camera lifted the whole frame by 0.13–0.17, about once a second. The template adds `near_fade` (NeonControls, default 55): portals fade out as they come within that distance of the camera plane, so they dissolve instead of sweeping bright. Walls and the outer shell are untouched.
- **The kick lighting the frame.** The kick drove glow, bloom and the ring at full strength (`kick_glow` is at its maximum), up to 0.89 relative luminance: a white screen twice a second. `kick_light` and the ring level separate the light from the motion, so the kick still punches (zoom, jolt) but pulses rather than strobes.

With the defaults the 50 % preview of `neon_house` seed 42 has no flashes; the kick pulses lift the frame by 0.02–0.09. Raising `kick_light` brings the strobe back; the check will say so.

## Files

| File | What |
|---|---|
| `stem_tunnel.blend` | the template: the reference lines tunnel and its look, no kaleidoscope, no UI script, drivers on the run signals, `near_fade` on the portals |
| `stem_tunnel.py` | runs inside Blender: maps controls onto the look, bakes, wires the drivers, renders; `--make-template` rebuilds the template |
| `mappings/<method>.toml` | which modulator drives which look signal, per input method: `gen`, `master`, `stems`, `midi` |

After re-tuning the look in `blender/audio-tunnel/neon_tunnel_audio.blend`, rebuild the template from it:

```
blender -b blender/audio-tunnel/neon_tunnel_audio.blend --python blender/stem-tunnel/stem_tunnel.py -- \
    --make-template blender/stem-tunnel/stem_tunnel.blend
```

## Speed (Apple M1)

EEVEE at 1080×1920: 0.38 s a frame at 32 samples, 0.10 s at the preview's 50 % and 8 samples. A final Short took 4.3 minutes (render 185 s, x264 `slow` encode 52 s, checks 16 s) and is about 70 MB (CRF 16: ~70 Mb/s, far above YouTube's 12 Mb/s guide, which is fine since YouTube re-encodes); a preview takes about 1 minute.
