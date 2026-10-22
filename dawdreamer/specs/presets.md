# Presets: the format

**v1 · 2026-10-22.** A preset is one TOML file in `dawdreamer/presets/` that describes a family of loops: the music rules, the tracks with their patterns and sounds, the send buses and the master. A seed turns it into one loop. `uv run datapipe gen --preset <name> --seed <n>` renders it; a copy lands in each run folder as `preset.toml`.

**The one rule:** wherever a value is a list, the seed picks one item (`key = ["D", "F", "A"]`, `pattern = ["x...", "x.x."]`, `Program = ["Crystal", "Bells"]`). A single value is fixed. Sound lists only make sense between sounds of similar level, since one `trim_db` covers them all. The picks are written to the manifest (`music.choices`, `music.sounds`). For values that are lists themselves (`progression`), a list of lists means "pick one".

## `[music]`

| Key | Default | Meaning |
|---|---|---|
| `bpm` | 120 | 120, 150, 180 or 240 (audio.md, Grid) |
| `key` | `"A"` | tonic: C, C#/Db … B |
| `mode` | `"aeolian"` | ionian/major, dorian, phrygian, lydian, mixolydian, aeolian/minor, harmonic_minor |
| `progression` | `["i"]` | one chord per bar as Roman numerals of the mode, cycled over the bars; case is ignored |
| `sevenths` | false | add the seventh to every chord |
| `violation` | all three | the twist: `motif_up`, `kick_dropout`, `stutter` (audio.md, Story) |
| `sections` | story fractions | override section starts in beats, e.g. `{ twist = 12, build = 16, windup = 20 }` |

## `[track.<name>]`

Tracks render in file order. The name is the stem name, the MIDI track name and the column prefix in `frames.csv`.

| Key | Roles | Meaning |
|---|---|---|
| `role` | all | `drums`, `bass`, `motif`, `chords`, `riser`, `impact` (below) |
| `pattern` | drums, bass, chords, motif | a step string, one character per 16th; it repeats to fill the loop, so its length must divide the loop's 16ths (64 at 120 BPM, 96 at 180). Spaces and `|` are ignored |
| `euclid` | drums, bass, motif | `{ hits = 5, steps = 16, rotate = true }` instead of a pattern; rotation keeps an onset on the downbeat |
| `note`, `alt_note` | drums, impact | MIDI notes for `x` and `o` (hats: 42 closed, 46 open) |
| `gate` | all with notes | note length in beats when no `-` holds it (drums 0.25, bass 0.22, motif 0.5) |
| `octave` | bass, motif, chords | octave of the tonic (scientific: A4 = 440 Hz = MIDI 69). Bass 1, motif 5, chords 3 |
| `length` | motif | motif length in notes, `[3, 4, 5]` |
| `scale` | motif | `"pentatonic"` (default) or `"mode"` |
| `build` | drums | `"keep"`, `"double"` (fill every free 16th, rising) or `"roll"` (8ths, then 16ths in the windup) |
| `windup` | all | `"drop"` (default: silent from the last beat on) or `"keep"` |
| `dropout` | drums | rest through the twist when the violation is `kick_dropout` |
| `at` | impact | sections to hit, default `["hook"]` |
| `humanize` | drums | velocity spread, ±4 by default |
| `instrument` | all | the sound: a slot (below) |
| `inserts` | all | effect slots after the instrument, in order |
| `gain_db`, `pan` | all | fader and pan (−1 left … 1 right) |
| `sends` | all | `{ <bus> = <dB> }`, post-fader |

**Pattern characters:** `x` hit, `X` accent, `.` rest, `-` hold the previous note. Drums: `o`/`O` play `alt_note`. Bass: `x` the chord root, `o` an octave up, `5` the fifth.

### Roles

| Role | Writes |
|---|---|
| `drums` | the pattern's hits, plus the `build` treatment and the `dropout` |
| `bass` | the current chord's root on the pattern, kept within a fifth of the bass octave |
| `motif` | the hook (audio.md, Hook and structure); the twist violation applies here |
| `chords` | the progression, one chord per bar (or per pattern onset), voice-led |
| `riser` | no notes; its sound is driven by the score's `riser` curve |
| `impact` | one long hit at each section in `at` |

## Slots: instruments and effects

```toml
instrument = { faust = "kick", params = { tune = 47, decay = 0.45 } }

[track.lead.instrument]                # the same as a sub-table, handy for longer slots
plugin = "ripplerx"                     # a key of dawdreamer/plugins.toml
params = { Program = "Crystal", "A Decay" = "1.2" }
trim_db = 4.0                           # added to the track's fader for this candidate only
fallback = { faust = "glass", trim_db = -2.0, params = { ratio = 2.0 } }
```

| Key | Meaning |
|---|---|
| `faust` | a DSP in `dawdreamer/faust/` (engine.md, Built-in sounds) |
| `plugin` | a plugin key from `plugins.toml` |
| `params` | Faust: slider name → value. Plugin: parameter name → raw 0–1 number, or the displayed value as a string. `datapipe plugins probe <key>` lists them |
| `state` | plugin only: a state file in `dawdreamer/states/`, loaded before `params` |
| `automate` | `{ <param> = { curve = "riser", from = 700, to = 9000, scale = "log" } }`: drive a parameter from a score curve at audio rate; `scale` is `"lin"` (default) or `"log"`; plugin values are raw 0–1 |
| `trim_db` | level correction for this candidate (instrument slots) |
| `fallback` | the next slot to try when the plugin is not available here; chains may be longer |

## `[bus.<name>]` and `[master]`

```toml
[bus.space]
fx = [{ faust = "space", params = { decay = 2.6 } }]   # or [[bus.space.fx]] tables with plugin + fallback
gain_db = 0.0

[master]
lufs = -14.0
true_peak_db = -1.0
fx = [{ faust = "master" }]
```

A bus nobody sends to is skipped (with a warning). Each bus return is recorded as a stem named after the bus, so bus names must differ from track names.

## Writing a preset

1. Copy the nearest preset; keep `neon_house` Faust-only so a fresh clone always works.
2. Render three or four seeds and read the `balance` line against the table in audio.md, Mix balance.
3. Listen to `loop_x3.wav` for the seam and the twist, on a phone speaker too.
4. `uv run pytest tests/test_gen_compose.py` checks every preset in the folder against the story rules.
