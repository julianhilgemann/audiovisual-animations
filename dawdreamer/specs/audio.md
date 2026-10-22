# Audio: what a loop must sound like

**v1 · 2026-10-22.** The audio design rules of the generative mode ([SPEC §15](../../SPEC.md#15-generative-loops)), moved here from [docs/sticky-av-shorts.md](../../docs/sticky-av-shorts.md) and extended with how `datapipe gen` implements each rule. The composer is `src/datapipe/gen/compose.py`; a rule marked *(tested)* is checked for every shipped preset by `tests/test_gen_compose.py`.

Audio is the master clock. It is composed first, on a grid that lands on whole video frames, and built to loop without a seam. Every visual event is derived from it.

## Grid

| | Value |
|---|---|
| Loop | 8.0 s, fixed |
| Video | 60 fps = 480 frames |
| Audio | 48 kHz = 384,000 samples = exactly 800 per frame |
| Tempo rule | bars = BPM / 30 (whole bars in 8 s) and 3600 / BPM whole (every beat on a frame) |

Only four tempos satisfy both:

| BPM | Frames per beat | Bars in 8 s | Feel | Preset |
|---|---|---|---|---|
| **120** (default) | 30 | 4 | House and techno pulse; the classic loop | `neon_house`, `glass_mallets` |
| 150 | 24 | 5 | Odd phrase length; only on purpose | |
| 180 | 20 | 6 | Felt as 90 half-time: trap, phonk | `phonk_180` |
| 240 | 15 | 8 | Felt as 120 half-time; same music as 4 bars at 120 | |

At 120 BPM a 16th note falls on a half frame (every 7.5 frames). Half frames round up, so a hit moves by at most 8 ms, well below what anyone perceives as out of sync. The score validator rejects any other tempo *(tested)*.

## Story in 8 seconds

Eight phrases of 1 s each: hook, groove, twist, build and a payoff that is the restart. The composer places the four sections at fixed fractions of the loop, snapped to whole beats; a preset may move them (`[music] sections`), which 180 BPM does to land them on bars.

| Phrase | Time | Section | What the audio does | Implemented by |
|---|---|---|---|---|
| 1 | 0–1 s | `hook` | Downbeat impact; full groove at once; the motif enters | kick, bass and motif on beat 0 *(tested)*; `impact` role; no fade-in, ever |
| 2–4 | 1–4 s | `hook` | Groove and motif repeat with small changes | motif restarts every bar; odd bars answer with one changed note |
| 5 | 4–5 s | `twist` | **The violation**, exactly one per loop *(tested)* | `motif_up` (+5 semitones), `kick_dropout` (tracks with `dropout = true` rest) or `stutter` (the motif's first note in 16ths) |
| 6–7 | 5–7 s | `build` | Filter opens, riser starts, hats double | `riser` curve 0 → 1 from the build to the loop end, drives the riser and any `automate` (the pad's filter); `build = "double"` (hats) and `"roll"` (claps: 8ths, then 16ths) |
| 8 | 7–8 s | `windup` | Peak tension; the last beat drops out | every track with `windup = "drop"` (the default) is silent in the last beat, and notes are cut there *(tested)*; only the riser and reverb tails remain |
| → 1 | 8 s = 0 s | | The downbeat resolves the tension | the restart is the drop: kick, bass, motif and impact on sample 0 |

Sections and the riser curve are written to `score.json`, so the visuals see the same story (handoff.md).

## Hook and structure

- **Strong downbeat at sample 0:** kick and the motif's first note together *(tested)*; bass too where its pattern starts on the one.
- **One motif of 3–5 notes** from the pentatonic of the mode (minor pentatonic for minor modes, major for major), a random walk from the root or fifth, repeated every bar. `scale = "mode"` uses all seven notes.
- **Medium syncopation:** the motif sits on a Euclidean rhythm (5 or 6 in 16, rotated so an onset stays on the downbeat) over a straight kick.
- **Harmony:** one diatonic chord per bar from the preset's progressions, written as Roman numerals of the mode (case is ignored; the mode sets each chord's quality). Pads are voiced close to the previous chord.

## Loop seam

- The last bar builds tension (riser, filter opening, rolls) and the last beat drops out; the downbeat resolves it.
- **Two passes, keep the second:** the engine renders 16 s and keeps 8–16 s, so reverb and delay tails from the end wrap into the head (engine.md).
- **Never fade out.** Check the seam by listening to `loop_x3.wav`: the loop three times in a row.
- The run reports `seam.ok`: the jump from the last sample to the first must not exceed the render's own jump at the pass boundary (the true continuation) by more than a typical large step.

## Sound palette

| Want | Built in (Faust, `dawdreamer/faust/`) | Free plugin (`plugins.toml`) |
|---|---|---|
| Glassy plucks and bells with fast attacks | `glass`: 2-operator phase modulation, bright index decay | RipplerX (Crystal, Kalimba, Bells, Marimba, Vibes), Dexed |
| Bass with strong harmonics, saturated for phone speakers | `bass` (sine + filtered saw, tanh) and the `drive` insert | JC303 (303 acid) |
| Crisp upper-mid transients | `clap` (three bursts + tail), `hat` (808 metal) | |
| Soft, wide pads | `pad` (six detuned saws, slow envelope) + `filter` insert | Dexed |
| Risers, impacts for transitions | `riser` (sweeping band-passed noise), `impact` (falling boom) | |
| Space | `space` (Zita reverb), `echo` (tempo-synced ping-pong) | Dragonfly Plate and Hall, Valhalla Supermassive |

Later: reverse swells, and a Shepard–Risset glissando as a loop-native endless rise.

## Mix balance (measured)

Loudness of each stem relative to the sum of all stems, in LU, measured on seeds 1, 2, 3, 7 and 42 (2026-10-22). Every run prints this line and stores it as `balance_lu` in its manifest; use the table as the target when writing a preset.

| Stem | `neon_house` | `glass_mallets` | `phonk_180` | Rule of thumb |
|---|---|---|---|---|
| kick | −3 | −2.5 to −4.5 | −6 to −7 | the loudest hit, except where an 808 carries the low end |
| bass | −6 to −7.5 | −3.5 to −5 | −1.5 to −2.7 | close to the kick; offbeat bass adds loudness without stacking peaks |
| motif | −7 to −9 | −6 to −8 | −9 to −10 | clearly audible: it is the hook |
| pad | −8 to −11 | | | behind the motif |
| clap | −12.5 | −11 | −9.5 to −10.5 | |
| hats | −15 | −17 to −19 | −17 to −18 | |
| riser, impact | −12 to −14 | −11 to −13 | −17 to −18 | the riser plays only 3 s, so its peak level is higher than its loop loudness |
| returns (space, echo) | −19 to −25 | −15 to −23 | −23 to −25 | |

## Phone translation and loudness

- Phone speakers lose the sub-bass: saturate the bass until its harmonics carry the line (`drive` insert, `bass.drive`).
- Everything below 120 Hz is mono: the `master` DSP removes the side signal below `mono_hz` (default 120).
- **−14 LUFS integrated, true peak ≤ −1 dBTP** (`[master] lufs`, `true_peak_db`). The run gains the mix to the target and a lookahead limiter holds the 4× oversampled true peak 0.3 dB under the ceiling, room for the AAC encode (engine.md). Platforms turn louder masters down, so punch beats loudness.
- Limiter work should stay at about 1–4 dB. More means a peaky mix: lower the kick, raise sustained parts, or saturate the bass (`limiter_max_reduction_db` in the manifest).
- Test on the phone speaker at arm's length and on earbuds.
