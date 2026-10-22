# Stem tunnel (Blender)

The neon lines tunnel from [`blender/audio-tunnel`](../audio-tunnel/README.md), driven by a generated loop instead of one analysed audio file. The score's hits (the MIDI) and the stems are the modulators, the master is the soundtrack, and one command renders and encodes a finished 8-second YouTube Short.

```
uv run datapipe short --preset neon_house --seed 42            # compose, render, encode, check
uv run datapipe short --run work/gen/latest --preview          # reuse a run; half size, 8 samples, ~1 min
uv run datapipe short --preset phonk_180 --seed 3 --keep-frames
```

Output: `output/<run>.mp4`, a `.json` sidecar with the checks, and a `.png` thumbnail from the twist. The run folder keeps the same MP4, `controls.json`, `render.log` and `scene_baked.blend` (open it, scrub, play: the mix is on the timeline).

## How a run becomes a Short

| Stage | Where | What |
|---|---|---|
| Audio | `datapipe gen` (`dawdreamer/`) | score, stems, mastered mix |
| S3 controls | `src/datapipe/gen/controls.py` | per frame: each track's note-ons, each stem's loudness, the mix's loudness and brightness, the riser curve, the story's sections → `controls.json` |
| S4 mapping | `mapping.toml`, `stem_tunnel.py` (in Blender) | modulators → the look's signals on the `AudioSignals` empty; motion integrated and closed on the loop |
| S5 render | Blender, headless, EEVEE | 480 PNG frames at 1080×1920, 60 fps, plus frame 481 for the seam check |
| S6 encode | `src/datapipe/gen/video.py` (PyAV) | H.264 High, yuv420p, BT.709 matrix and tags, TV range, GOP 30, 2 B-frames, CRF 16 (x264 slow), AAC 320 kb/s 48 kHz, faststart; the audio is trimmed first if its AAC encode would overshoot −1 dBTP (it does by up to 0.4 dB on distorted bass) |
| S7 checks | same | format, length (480 frames, 8.0 s), faststart, kick sync, seam, flashes |

The shared math (envelopes, followers, loop closure) is `src/datapipe/mapping.py`, the same file in the pipeline and in Blender.

## What drives what (`mapping.toml`)

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

Sources are `hit:<track>`, `stem:<name>`, `mix:loud`, `mix:bright`, `curve:<name>` and `section:<name>`; each signal is a weighted sum. A preset without a track simply contributes nothing. The look's own sliders (speeds, glow, flash, lens, colours) are custom properties on the `NeonControls` empty in `stem_tunnel.blend` (Object Properties > Custom Properties), carried over from the reference scene.

## The loop closes

Accumulated motion (forward travel, camera roll, portal and outer spin, colour phase) is integrated in Python and baked, not driven by `frame`. Each is closed so frame 481 is the same picture as frame 1: its rate gets one constant added so the total is a whole number of the pattern's periods (walls repeat every 2 segments in depth; around the tunnel every 2 segments for an even symmetry, portals and the outer shell every segment), or is scaled when that would run a forward motion backwards. The render prints what it did (`closure` in the result). Envelopes and the kick ring's age wrap around the seam too. Measured: frame 481 against frame 1, mean difference 0.00002 to 0.00005.

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
| `mapping.toml` | which modulator drives which look signal |

After re-tuning the look in `blender/audio-tunnel/neon_tunnel_audio.blend`, rebuild the template from it:

```
blender -b blender/audio-tunnel/neon_tunnel_audio.blend --python blender/stem-tunnel/stem_tunnel.py -- \
    --make-template blender/stem-tunnel/stem_tunnel.blend
```

## Speed (Apple M1)

EEVEE at 1080×1920: 0.38 s a frame at 32 samples, 0.10 s at the preview's 50 % and 8 samples. A final Short took 4.3 minutes (render 185 s, x264 `slow` encode 52 s, checks 16 s) and is about 70 MB (CRF 16: ~70 Mb/s, far above YouTube's 12 Mb/s guide, which is fine since YouTube re-encodes); a preview takes about 1 minute.
