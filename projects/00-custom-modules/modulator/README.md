# modulator

An LFO bank and a routing matrix: named source channels in, one channel per destination out. Any source can drive any destination, and any source can speed up, deepen or restart an LFO.

## Connectors

| Connector | |
|---|---|
| Input 1, Input 2 (CHOP) | Source channels, merged: audio features, MIDI channels, anything with names. One sample each. |
| Output 1 (CHOP) | One channel per destination, in the destination's own units. |
| Output 2 (CHOP) | The source bus: both inputs and the LFOs. |

## Parameters

- **Depth.** Master Depth, and a depth per source family: Audio (`a_*`), MIDI (everything not listed here), LFO (`lfo*`), Clock (`clk_*`). Hold freezes every destination; Bypass outputs the bases alone.
- **Mapping.** Destinations, Routes and LFOs tables, each empty to use the module's own examples. **Bases COMP**: a COMP that gets one Base slider per destination on its Bases page. Use a COMP your project saves, not one inside a module, or the sliders vanish when the module reloads. Empty takes the bases from the base column of the destinations.
- **Module.** Save Module.

## Tables

- **Destinations**: `name`, `min`, `max`, `base`, `smooth` (seconds), `target` (a note on what it drives).
- **Routes**: `source`, `dest`, `amount`, `curve`, `comment`. The amount is a fraction of the destination's range, added to the base. Curves: `lin`; `sq` (slow start); `sqrt` (fast start); `inv`; `bi` (2x − 1, for sources centred on 0.5, such as LFOs, so the destination swings both ways around its base); `step`. A `#` before the source turns a row off.
- **LFOs**: `name`, `shape` (`sine`, `tri`, `saw`, `ramp`, `square`, `pulse`, `sh`, `noise`), `sync` (`beat`: `rate` is beats per cycle, locked to `clk_beat`; `free`: `rate` is Hz), `depth`, `phase`, `rate_src`/`rate_amt` (octaves faster at full source; whole doublings in beat mode, so it stays on the grid), `depth_src`/`depth_amt`, `reset_src` (restarts the cycle on a trigger), `smooth`.

The examples: `pulse` (audio kicks and MIDI track 1), `energy`, `sweep` (`lfo1`, once a bar) and `fader` (the crossfader), and six LFOs from a one-bar sine to a noise drift that kicks restart.

## How it works

- `script_lfo` advances the LFOs once a frame. Without a `clk_beat` input, beat LFOs run at 120 BPM.
- `script_matrix` sums the routes in each destination's 0-1 range on top of its base, clamps, smooths and maps to min-max. When the destinations table changes, it updates the sliders on Bases COMP one frame later.
- It costs about 0.2 ms per frame.

## Files

| File | |
|---|---|
| `modulator.tox` | The module. Projects load this through External .tox. |
| `modulator.tdxn` | Its network as text, written by Save Module. |
| `script_lfo_callbacks.py`, `script_matrix_callbacks.py`, `module_callbacks.py` | Its scripts as text, written by Save Module. Edit them inside TouchDesigner, not here. |
| `destinations.tsv`, `routes.tsv`, `lfo_table.tsv` | The example tables, written by Save Module. |
