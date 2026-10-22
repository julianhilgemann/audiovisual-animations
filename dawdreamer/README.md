# DawDreamer: generated audio

Composes an 8-second loop from a preset and a seed, renders it headless with [DawDreamer](https://github.com/DBraun/DawDreamer), masters it to −14 LUFS, and writes what Blender needs: the mix, one stem per track, and the score as JSON, MIDI and a 60 fps frame table. Runs on Windows and macOS from the repo's `.venv`; nothing is installed system-wide.

Design: [SPEC §15](../SPEC.md#15-generative-loops) (where this fits), [docs/sticky-av-shorts.md](../docs/sticky-av-shorts.md) (the product idea), and the specs here:

| Spec | Answers |
|---|---|
| [specs/audio.md](specs/audio.md) | What a loop must sound like: grid, story, hook, seam, palette, balance, loudness |
| [specs/engine.md](specs/engine.md) | How it is rendered: signal flow, two passes, mastering, determinism, the built-in sounds, plugins |
| [specs/presets.md](specs/presets.md) | The preset format |
| [specs/handoff.md](specs/handoff.md) | The files a run writes, the timing contract, how Blender reads them |

## Quick start

```
uv sync                                          # once per machine: DawDreamer, mido, pyloudnorm into .venv
uv run datapipe gen --seed 42 --play             # compose, render, master, play the loop three times
uv run datapipe gen --preset phonk_180 --seeds 1-8    # eight candidates at 180 BPM
uv run datapipe plugins fetch                    # optional: the free VST3 plugins, into dawdreamer/plugins/
uv run datapipe gen --preset glass_mallets --seed 3   # uses them, or falls back to Faust without them
uv run datapipe doctor                           # checks DawDreamer, every Faust DSP and the plugins
```

`uv run datapipe short --seed 42` goes on to render and encode the finished Short in Blender ([blender/stem-tunnel](../blender/stem-tunnel/README.md)). A run takes about 3 s (Apple M1) and prints what played each track, the loudness, the seam check and the stem balance. It lands in `work/gen/<yyyymmdd>_<preset>_s<seed>/` and is copied to **`work/gen/latest/`**, the fixed path for Blender.

## Changing it

| To change | Edit | Then |
|---|---|---|
| Tempo, key, patterns, sounds, mix | `presets/<name>.toml` ([format](specs/presets.md)) | `datapipe gen --preset <name> --seed <n>` |
| The notes themselves | the run's `score.mid` in Ableton, REAPER or any DAW; keep the track names; export multitrack MIDI | `datapipe gen --preset <name> --midi edited.mid` |
| A plugin's sound beyond its parameters | `datapipe plugins edit ripplerx --state dawdreamer/states/my_bells.state` opens its window; closing saves the state | `state = "my_bells.state"` in the slot |
| An instrument or effect | `faust/<name>.dsp` (Faust; its `hslider`s are its parameters) | rerun |

Seeds pick everything a preset leaves open (key, mode, progression, patterns, the twist, plugin programs), each from its own named random stream: the same seed always gives the same loop, and editing one track never reshuffles another.

## Presets

| Preset | Tempo | Sounds | Character |
|---|---|---|---|
| `neon_house` (default) | 120 | Faust only, renders identically on a fresh clone | four-on-the-floor, glass FM motif, offbeat saturated bass, pad opening through the build |
| `glass_mallets` | 120 | RipplerX lead, JC303 bass, Dragonfly plate; Faust fallbacks | techno: Euclidean hats, rubbery 303 line, mallet bells |
| `phonk_180` | 180 (felt 90) | Faust only | half-time: long gliding 808, metallic motif, trap hats |

## Plugins

`plugins.toml` lists them with per-OS download URLs and sha256 checksums; `datapipe plugins list | fetch | probe | edit` manages them. All are free and have VST3 builds for Windows and macOS; all render headless (tested on macOS).

| Plugin | For | Licence |
|---|---|---|
| [RipplerX](https://github.com/tiagolr/ripplerx) | physically modelled mallets: bells, kalimba, marimba, vibes | GPL-3.0 |
| [Dexed](https://github.com/asb2m10/dexed) | FM (DX7): keys, bells, metallic plucks | GPL-3.0 |
| [JC303](https://github.com/midilab/jc303) | TB-303 bass | GPL-3.0 |
| [Dragonfly Reverb](https://github.com/michaelwillis/dragonfly-reverb) (Plate, Hall) | reverbs | GPL-3.0 |
| [Valhalla Supermassive](https://valhalladsp.com/shop/reverb/valhalla-supermassive/) | huge reverbs and delays; install by hand | freeware |

Fetched binaries stay in `plugins/` (gitignored): the public repo never carries third-party binaries.

## Folder

| Path | What |
|---|---|
| `specs/` | the four specs above |
| `presets/` | song presets |
| `faust/` | built-in instruments and effects, compiled at render time |
| `plugins.toml` | the plugin manifest |
| `plugins/` | fetched plugins, per OS (gitignored) |
| `states/` | saved plugin states (committed; small) |

The code is in `src/datapipe/gen/`: `compose.py` (S1), `engine.py` and `master.py` (S2), `score.py` (the shared contract), `plugins.py`, `run.py`. Tests: `tests/test_gen_*.py`.
