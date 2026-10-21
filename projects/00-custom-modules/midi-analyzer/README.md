# midi_analyzer

MIDI in as named modulation channels, plus a clock that follows MIDI clock and transport. The CC map that ships with it is the Elektron Octatrack's (manual OS 1.40A, appendix C), so every Octatrack knob, track, MIDI track, the crossfader, scenes and patterns arrive by name. Another device needs only another CC map.

## Connectors

| Connector | |
|---|---|
| Output 1 (CHOP) | The channels, one sample each, every value 0-1 except counts, `clk_bpm`, `clk_beat`, `clk_bar` and `clk_step`. |

## Parameters

- **MIDI.** MIDI Device ID (from Dialogs > MIDI Device Mapper); Audio Track Channels and MIDI Track Channels (eight channels each, `0` for off); CC Smoothing; Note Envelope Decay; **Last Event**, which shows the last message and the channels it changed, so moving a knob tells you its name; Reset Values.
- **Clock.** Clock Source (Auto, MIDI Clock, Internal); Internal BPM; Beats per Bar; Freeze When Stopped; Restart Clock; Clock Status.
- **Learn.** Learn Name, Learn Type (CC by default, so a running sequencer can't grab a knob mapping with its next note; Note; Any), Learn, Learn Status.
- **Mapping.** CC Map and Custom Map tables. Empty uses the module's own `ot_cc` and `custom_map`. Point Custom Map at a table in your project to keep its rows: the module's own is replaced whenever the module reloads.
- **Module.** Save Module.

## Channels

| Channels | From |
|---|---|
| `t1_` … `t8_` + `src_a`-`src_f`, `amp_a`-`amp_e`, `lfo_a`-`lfo_f`, `fx1_a`-`fx1_f`, `fx2_a`-`fx2_f` | The six knobs (A-F) of each Octatrack audio-track page, by knob position. |
| `t1_level`, `_cue`, `_mute`, `_solo`, `_cued` | Track and cue level; mute, solo and cue as 0 or 1. |
| `xfade`, `scene_a`, `scene_b`, `scene_trig` | Crossfader, selected scenes (0-15 as 0-1), a trigger when either changes. |
| `mt1_` … `mt8_` + `gate`, `vel`, `note`, `trig`, `env`, `count`, `bend`, `press`; `mt1_mute` … `mt8_solo` | Notes, pitch bend and pressure on the MIDI Track Channels; the MIDI-track mutes and solos. |
| Custom map names (+ `_trig`, `_env`, `_count` for notes) | Single notes and extra CCs, from the custom map or Learn. |
| `pattern`, `pattern_num`, `pattern_trig`, `note_trig`, `note_env` | Program change; any note on any channel. |
| `clk_bpm`, `clk_run`, `clk_ext`, `clk_beat`, `clk_phase`, `clk_bar`, `clk_bar_phase`, `clk_phrase_phase`, `clk_step`, `clk_beat_trig`, `clk_bar_trig`, `clk_step_trig` | The clock. |

## How it works

- `midi_in` passes every message, clock ticks included, to `ot_engine` as raw bytes, so the numbers match the device manual (C3 is note 48). Script CHOP `script_midi` writes the channels once a frame, and `rename_midi` names them.
- Ticks reach TD in per-frame batches, so the tempo comes from a regression over the last four beats (136.0 BPM measured against an Octatrack at 136). The beat position is a locked loop that the tick count corrects each frame. Start and song position put it on the bar, so when TD opens mid-song, one stop and start on the device aligns the bars.
- Devices send a knob's value only when it moves, so the last values are kept in the project's root storage (one entry per analyzer path) and come back after a reload.
- The Octatrack sends notes only from its MIDI tracks and from trig keys pressed live, never from sequenced audio-track trigs.
- It costs about 0.33 ms per frame.

## Files

| File | |
|---|---|
| `midi_analyzer.tox` | The module. Projects load this through External .tox. |
| `midi_analyzer.tdxn` | Its network as text, written by Save Module. |
| `ot_engine.py`, `midi_in_callbacks.py`, `script_midi_callbacks.py`, `module_callbacks.py` | Its scripts as text, written by Save Module. Edit them inside TouchDesigner, not here. |
| `ot_cc.tsv`, `custom_map.tsv` | Its tables as text, written by Save Module. |
