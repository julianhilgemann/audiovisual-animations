# Flythrough (Blender)

A second look for every input method (SPEC §16.8): the camera really flies down a winding tunnel, through a watch movement's gear trains, warp streaks or a kaleidoscope of crystals, driven by a run's `controls.json` like the [stem tunnel](../stem-tunnel/README.md). The same six mappings, the same look signals, the same render, encode and checks; only the world differs.

```
uv run datapipe short gen --preset neon_house --seed 42 --look flythrough             # clockwork, the default
uv run datapipe short --run work/gen/latest --look flythrough --style warp --preview  # a run again, another world
uv run datapipe short deep inbox/deep/clock.wav --look flythrough --style timewarp
```

Output, run folder and sidecar are the stem tunnel's, named `output/<method>/<run>_flythrough[_<style>].mp4` so they sit beside the stem tunnel's (`scene_baked_flythrough.blend` in the run folder to scrub and play). `datapipe tune` doesn't work with this look yet: the tuner panel is the stem tunnel's. Change a style file and render again instead.

## Worlds

A style picks the layers and sizes them (`styles/<name>.toml`, every control in `look.toml`):

| Style | What you fly through |
|---|---|
| `clockwork` | a watch movement: plates with Geneva stripes, bridges with blued screws and glowing seams; gear trains on two levels that mesh and turn, with ruby jewels; dial rings with lume, ring gears and balance wheels as portals |
| `warp` | hyperspace: a tube of light lines with gates, and streaks that grow from points into lines with the speed |
| `kaleido` | a kaleidoscope: slabs of crystal mirrored six times around, turning against each other, rosettes to fly through; the colours repeat, mirrored, in every wedge |
| `timewarp` | clockwork, flown faster, with streaks racing past the gears |

| Layer (`[shape]`) | Options |
|---|---|
| `walls` | `plates` (`sides` plates around), `grid` (lines of light), `none` |
| `gears`, `gear_levels`, `gear_size` | how densely gear trains cover the plates (0 = none), on 1 to 3 levels, and their tooth size |
| `portals` | `clockwork` (dial ring, ring gear and balance wheel in turn), `dial`, `ring_gear`, `balance`, `gate`, `rosette`, `none`; `portal_every` segments, `portal_inner` the opening |
| `streaks`, `streak_length` | warp streaks per bend length and their longest |
| `shards` | how densely crystal slabs fill the tunnel (0 = none) |
| `fold`, `mirror` | the content repeats `fold` times around; `mirror = 1` mirrors each repeat as a kaleidoscope does |
| `segment`, `bend`, `bend_segments` | the distance between portals; how far the path swings (share of the radius); segments before its bends repeat |

## How it flies

The path bends left, right, up and down: x = A sin(ws), y = A/2 sin(2ws + 0.9), z = -s, repeating after one bend length Q = `bend_segments` × `segment`. Everything along it is built for one Q and tiled (`worlds.py`), so the picture at s + Q is the picture at s. The camera's location, heading and pitch are simple-expression drivers of the baked `travel` (`worlds.path_expressions`); it wraps by Q, which nobody can see, and leans into the bends (`bank`). The lantern and two coloured side lights fly with it, so the metal catches the light as it passes; every hit of the ring's track launches a light that races ahead down the path and lights the walls as it goes.

Gears, portals and crystal slabs are Geometry Nodes instances (`FlySpinners`): a cloud of points names each one's prototype (in the `FlyProtos` collection), frame, phase and channel weights, and the node group turns each about its own axle by phase + weights · channels. Five baked channels turn them: `tick` (the gear trains the kick advances like an escapement), `drive` (bass), `whirr` (hats), `portal` (mids) and `balance` (the balance wheels rock to the beat, wider with the energy). Gears in a train touch on their pitch circles, turn the other way at the same tooth rate and start with a tooth in the other's gap, so they mesh at any speed (`tests/test_flythrough.py` checks it).

## What drives what

The look signals are the stem tunnel's, so `mappings/<method>.toml` carry the same sources and a recipe means the same on both looks:

| Look signal | Drives |
|---|---|
| `kick` | zoom punch, roll jolt, a burst of speed, the escapement's tick |
| `kick_light` | the lights and everything that glows pulse |
| `bass` | the drive trains turn, the seams and lume glow (haze), the view rolls |
| `energy` | speed, lantern, glow, colour cycling |
| `hats` | the small gear trains whirr, streaks and crystals sparkle |
| `mids` | dial rings, gates, rosettes and crystal slabs turn |
| `bright` | palette shift |
| `twist` | hue jump and extra roll |
| ring | the racing light, and a ring of light along everything that glows |

The flight's speed, as flown, is baked too (`warp`, followed with a 6-frame rise and 40-frame fall so a kick surges the flight without strobing): it lengthens the streaks and widens the lens (`warp_fov`). `[motion] speed_curve` (the riser, a song's build) adds speed on top, which is where the warp speed comes from.

## The loop closes

Accumulated motion is closed on the built world's periods (`worlds.periods`): travel on the bend length; the roll on whole turns (the content repeats `fold` times around, but the bends ahead and the coloured lights flying with the camera don't); the gear channels on 12 teeth, after which every gear, its spokes and its pinion are what they were; the portal channel on the turn every portal and slab repeats after (12 for dial rings, ring gears, balance wheels and gates, `fold` for rosettes and crystals); the balance's swing on a full swing. Measured on `neon_house` seed 42 at half size: frame 481 against frame 1, mean difference 0.00001 to 0.0002 for all four styles; a 7.8 s song (method F) 0.0002, a 24 s song (method C) 0.00003.

## Checks

At half size, 8 samples, all gates pass for every style on `neon_house` seed 42, with these mean luminances: clockwork 0.055, warp 0.10, kaleido 0.08, timewarp 0.08 (the stem tunnel: 0.058); sync median 0 frames. Warp counted 2 flashes a second before its streak length followed the smoothed speed; now none. A shape that puts more streaks or crystals near the camera, or brighter glow sliders, can bring flashes back, and the check says so.

## Files

| File | What |
|---|---|
| `flythrough.blend` | the template, built from Blender's factory scene by `flythrough.py --make-template`: camera, sliders, lights, materials, the spinners' node group, compositor (mist, then two blooms), watermark, the clockwork world |
| `flythrough.py` | runs inside Blender: maps controls onto the look, builds the style's world, bakes, wires the drivers, renders |
| `worlds.py` | the geometry in numpy: the path, the gear trains, the prototypes, walls, streaks and the periods the loop closes on |
| `look.toml` | every control: the look signals, the sliders and the shape, with ranges, defaults and help |
| `mappings/<method>.toml` | which modulator drives which look signal, per input method |
| `styles/<name>.toml` | the worlds above |

Rebuild the template after changing `flythrough.py`, `worlds.py` or `styles/clockwork.toml`, then run `uv run pytest tests/test_flythrough.py` and a `--preview` Short of each style:

```
blender -b --factory-startup --python blender/flythrough/flythrough.py -- --make-template blender/flythrough/flythrough.blend
```

## Speed (Apple M1)

EEVEE at 1080×1920: about 0.15–0.19 s a frame at the preview's half size and 8 samples, about 1.3 s at 32 samples for clockwork (the stem tunnel: 0.46 s here). Shadows are off: seen from lights that fly with the camera they fall behind what casts them, and they doubled the time. The rest goes to the lit metals and the instanced gears.
