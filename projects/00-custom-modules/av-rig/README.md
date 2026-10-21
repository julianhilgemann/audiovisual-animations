# av_rig

The three modules wired together: `audio_analyzer` and `midi_analyzer` feed `modulator`. Drop it into a project and every audio feature, every MIDI channel, the clock and six LFOs are there by name, routable to anything.

## Using it

1. Add a Base COMP, on its Common page set External .tox Path to `../00-custom-modules/av-rig/av_rig.tox`, turn off Reload Custom Parameters and Reload Built-In Parameters, then turn on Enable External .tox. Set Parent Shortcut to `Rig` (a new COMP doesn't take it from the `.tox` with Reload Built-In off).
2. Press **Create Mapping** on its Mapping page. That makes `<rig>_mapping` beside it, with copies of the example tables and one Base slider per destination. This COMP is your project's: edit its tables and the project saves them.
3. Wire a Null CHOP after Output 1 and point parameters at it, e.g. `op('null_mod')['noise_period']`; a Null after Output 2 holds every source. That is how `octatrack-av-setup` drives its visuals.

## Connectors

| Connector | |
|---|---|
| Input 1 (CHOP) | Optional audio; Audio Source External Input uses it instead of the Interface Device. |
| Output 1 (CHOP) | The destinations. |
| Output 2 (CHOP) | Every source: the 36 audio features, the MIDI channels, the clock and the LFOs. |
| Output 3 (CHOP) | The 128-bin log spectrum. |
| Output 4 (CHOP) | The audio. |

## Parameters

The rig shows the controls of its three modules on its own pages, bound to them: Audio, Transport, Analysis and Onsets (audio_analyzer); MIDI, Clock and Learn (midi_analyzer); Modulation (the modulator's Depth page). The modules' READMEs say what each one does. Its own pages:

- **Mapping.** Mapping (the project's mapping COMP), Create Mapping, and CC Map (empty: the Octatrack map).
- **Module.** YouTube Folder and Save Module.

The rig's parameters are the project's settings: they live on the instance in the project's `.toe` and survive every reload of the module. Pulses are passed on to the modules by `module_callbacks`.

## How it works

- The three modules are nested External .tox instances, each loaded from its own folder whenever the rig loads, so a change saved in one reaches the rig too. Their parameters are bound to the rig's. The Mapping tables and Bases COMP reach them as expressions such as `(parent.Rig.par.Mapping.eval() or me).op('routes')`, so a project without a mapping uses the examples.
- Everything that belongs to a project stays out of the modules: the parameter values on the rig instance, the tables and bases in the mapping COMP, and the last knob values in root storage. Module contents, storage and parameters added after loading are all replaced when a module reloads.
- To change a module, edit it inside the rig (in a project that uses it) and press Save Module on that module, not on the rig.
- It costs about 1.2-1.4 ms per frame.

## Files

| File | |
|---|---|
| `av_rig.tox` | The module. Projects load this through External .tox. It expects `../audio-analyzer/`, `../midi-analyzer/`, `../modulator/` and `../source-deck/` beside it, which is the case for every project in `projects/`. |
| `av_rig.tdxn` | Its network as text, written by Save Module. |
| `module_callbacks.py` | Its pulse handlers (Create Mapping among them), written by Save Module. |
