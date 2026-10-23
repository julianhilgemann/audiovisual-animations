# Datapipe

Audio-reactive YouTube Shorts rendered with Blender. Generate a loop, or bring your own music or sound (a master, stems, MIDI), and get a finished 9:16 MP4 in `output/`.

> **Status:** six input methods work end to end on macOS (SPEC §16): a generated loop, a finished master, master and stems, master, stems and MIDI, any stems without instrument names, and one complex track measured from every side. Design and roadmap: [SPEC.md](SPEC.md).

## Setup

```
uv sync                    # creates .venv with Python 3.12 and all libraries (nothing installed system-wide)
uv run datapipe doctor     # checks Python libs, PyAV/FFmpeg, DawDreamer, Blender, GPU
uv run pytest              # runs the tests
uv run datapipe gen --seed 42 --play     # compose, render and play an 8-second loop
uv run datapipe short --seed 42          # the same loop as a finished YouTube Short in output/gen/
```

## Your own music

Six methods, side by side. The master is always what you hear; stems and MIDI only steer the picture. The video is as long as your master (warning over 60 s, refused over 180 s).

| Method | Put this | Run |
|---|---|---|
| **B** `master`: one finished track | `inbox/master/mysong.wav` (WAV, AIFF, FLAC, MP3, M4A, or a video) | `uv run datapipe short master inbox/master/mysong.wav` |
| **C** `stems`: quick, controlled visuals | `inbox/stems/mysong/master.wav` and `inbox/stems/mysong/stems/*.wav` | `uv run datapipe short stems inbox/stems/mysong` |
| **D** `midi`: exact timing | as C, plus `inbox/midi/mysong/midi/*.mid` (one file per track) | `uv run datapipe short midi inbox/midi/mysong` |
| **E** `slots`: stems of anything, no beat needed | `inbox/slots/mypiece/stems/*.wav` (master optional; `slots = [...]` in `song.toml` sets the order) | `uv run datapipe short slots inbox/slots/mypiece` |
| **F** `deep`: one complex track, every feature | `inbox/deep/mytrack.wav` | `uv run datapipe short deep inbox/deep/mytrack.wav` |
| **A** `gen`: fully generated | nothing | `uv run datapipe short gen --preset neon_house --seed 42` |

E reads every stem the same way (loudness, transients, density, crest, brightness, flatness, three bands, activity) and gives slot 1 the punch, slot 2 the body, slot 3 the sparkle and slot 4 the portals; no tempo, kick or sections are assumed. F measures loudness (BS.1770), spectral shape, onsets per band, stereo width, the harmonic and percussive parts, pitch and structural changes, and maps each one to a fixed part of the tunnel. SPEC §16.7 has the details.

```
inbox/midi/mysong/
├─ master.wav            the mixdown: the Short's soundtrack
├─ song.toml             optional: bpm, roles, sections, start/length, loop
├─ stems/
│  ├─ Kick.wav           name each file after what it is: kick, snare, clap, hats, bass, lead, pad, riser, impact,
│  ├─ Bass.wav           or drums for a whole drum bus (names like "1-Kick", "Hi-Hat", "808 Sub", "Drum Rack" work)
│  └─ ...
└─ midi/
   ├─ Kick.mid           one file per MIDI track, starting at the song's start
   └─ Drum Rack.mid      a drum rack is split into kick, snare, clap and hats by note number (General MIDI)
```

**From Ableton:** set the loop brace over the part you want, from bar 1. *File > Export Audio/Video* with *Rendered Track: Master* gives `master.wav`; again with *All Individual Tracks* gives the stems (same range, so they line up; the run checks this and stops if they don't). For MIDI, select each MIDI track's clips over the same range, consolidate them (Cmd/Ctrl+J) so the clip starts at the range start, then right-click > *Export MIDI Clip*. Files that aren't named after a role keep their own name; map them in `song.toml` (`[roles] bass = "Reese"`).

**Try the layout first:** `uv run datapipe example midi` (or `stems`, `master`) writes a generated loop into that inbox exactly as an export would look, with a commented `song.toml`.

**Check before rendering:** `uv run datapipe analyze stems inbox/stems/mysong` writes the run folder with `report.png` (detected hits, tempo, sections) in a few seconds; `--preview` renders at half size in about a tenth of a second per frame. Re-render a run after editing its mapping (`blender/stem-tunnel/mappings/<method>.toml`) with `uv run datapipe short --run work/stems/latest --preview`.

**Tune by hand:** `uv run datapipe tune stems` opens the latest stems run in Blender with a *Datapipe* tab in the sidebar (N): which sounds drive what and how strongly, every slider of the look (keyframable for one song), and the tunnel's shape, all live while the song plays. *Save to run*, then `uv run datapipe short --run work/stems/latest` (or the panel's *Render* buttons) renders exactly that. A shape and look you want for every song becomes a style: `--style hex_prism` (also `square_circuit`, `star_vortex`, `flower_tube`, `speed_rails`, `truchet_maze`, or your own from the panel). See [blender/stem-tunnel/README.md](blender/stem-tunnel/README.md#tune-by-hand).

Requirements, on Windows or macOS: [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`, or `brew install uv`), and Blender 5.2 LTS. The pipeline needs nothing else. Tool paths per OS are in `config/pipeline.toml`; `config/machine.toml` overrides them for one machine.

## Folders

| Folder | What goes there |
|---|---|
| `inbox/master/`, `inbox/stems/`, `inbox/midi/`, `inbox/slots/`, `inbox/deep/` | Your music, per method (see above; watched automatically from Phase 4) |
| `output/<method>/` | Finished Shorts: MP4, a `.json` with the checks, a thumbnail |
| `scenes/` | Blender template scenes |
| `config/mappings/` | Reactivity recipes for the Director rig look (optional, not built yet) |
| `dawdreamer/` | Generated audio: specs, presets, Faust instruments, the free VST3 plugin list (see [dawdreamer/README.md](dawdreamer/README.md)) |
| `blender/stem-tunnel/` | The neon lines tunnel every method renders with: one mapping per method in `mappings/`, shapes and looks in `styles/`, the tuner (see its [README](blender/stem-tunnel/README.md)) |
| `docs/` | Design of the generative mode ([sticky-av-shorts.md](docs/sticky-av-shorts.md)) |
| `reference/` | Reference renders |
| `work/`, `cache/`, `archive/` | Pipeline internals; runs land in `work/<method>/`, the newest in `work/<method>/latest/` |

## Working with Claude

Open a terminal in this folder and run `claude`. `CLAUDE.md` gives it the project context. For example: "start Phase 0", or "make the rings thicker in the open Blender scene".

## Tools

- `python tools/blender_bridge.py --ping` checks that Claude and scripts can reach the open Blender (MCP add-on on `localhost:9876`).
