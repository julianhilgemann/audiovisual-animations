# Octatrack AV setup

The live AV set: an Octatrack (MIDI through a Roland UM-ONE, audio through an Elektron Analog Heat MKII) drives a noise-field particle generator that goes out at 1920×1080 over Syphon/Spout.

```
av_rig (shared module) --out 1--> null_mod      (drives the visuals)
       ^               --out 2--> null_sources  (every source)
       |
av_rig_mapping (this project's destinations, routes, LFOs, custom MIDI map, Bases)
```

The input layer is the shared module `av_rig` from `../00-custom-modules/av-rig/`: audio in and analysis, the Octatrack's MIDI as named channels with a clock, and an LFO bank and routing matrix. The module READMEs list every channel. What this project adds is its mapping and its settings.

## The visuals' parameters

Sixteen parameters read `op('null_mod')['<destination>']`: noise1 period, amplitude, spread, exponent and gain; level1 and level2 opacity (the two feedback mixes); level3 brightness 2 (the trails); lumablur1 white width (depth blur); displace1 and displace2 weight; slope1 strength; cam1 translate Z; rgbaDelay red, green and blue delay (from one destination, `rgb_split`, as −1×, −0.75× and −1.25× frames).

To change a resting value, use the Bases page of `av_rig_mapping`, not the operator. To change what moves what, edit `av_rig_mapping/routes`. The rig's Modulation page scales the routes by family: Audio, MIDI, LFO, Clock and Master.

## Settings of this project (on `av_rig`)

| Page | Setting |
|---|---|
| Audio | Interface Device: the Analog Heat MKII, Interface Channels `chan3 chan4` (the pair the original network used). Audio Source External Input listens to it; Microphone, Audio File and YouTube are the other sources. |
| MIDI | MIDI Device ID 1 (the UM-ONE); Audio Track Channels and MIDI Track Channels `1 2 3 4 5 6 7 8`. |
| Mapping | Mapping: `av_rig_mapping`. |

## Octatrack settings

| Setting | Why |
|---|---|
| PROJECT > MIDI > SYNC: CLOCK SEND and TRANSPORT SEND on | Tempo, start, stop and song position for the clock. After TD opens mid-song, one stop and start aligns the bars. |
| PROJECT > MIDI > CONTROL: AUDIO CC OUT = INT+EXT | The audio-track knobs send CCs while still working on the sound. EXT makes them control only the visuals. |
| PROJECT > MIDI > SYNC: PROG CH SEND on | Pattern changes arrive as `pattern`. |
| PROJECT > MIDI > CHANNELS: TRIG CH 1-8 | Must match Audio Track Channels. |
| MIDI track NOTE SETUP > CHAN | Must match MIDI Track Channels. |

The Octatrack sends notes only from its MIDI tracks and from trig keys pressed live; sequenced audio-track trigs send nothing. For a visual hit on every kick, sequence a MIDI track alongside it, or use the audio onsets (`a_kick`).

## The mapping (`av_rig_mapping`)

- `destinations`: the 14 destinations above with their ranges and smoothing.
- `routes`: the original moves (`key1` → noise period, `key2` → amplitude, `key4` → feedback 1, the low band → depth blur), plus MIDI track 1 hits on the period, the crossfader pulling the camera in, `lfo1` breathing the camera once a bar, snare hits widening the RGB split and the slow energy lengthening the trails.
- `lfo_table`: six LFOs, from a one-bar sine to a noise drift that kicks restart.
- `custom_map`: `key1` … `key4`, the notes C3, D3, E3 and F3 on channel 3 (the original T1-T4). Learn adds rows here.

Embody writes it to `project1/av_rig_mapping.tdxn` with the tables as `.tsv`, so a change of routing shows up in git.

## Files

| File | |
|---|---|
| `octatrack-av-setup.toe` | The project. The rig's settings live only here. |
| `project1/av_rig_mapping.tdxn`, `project1/av_rig_mapping/*.tsv` | The mapping, written by Embody. TD reloads a table the moment its file changes on disk. |
| `media/youtube/` | YouTube downloads (not in git). |
