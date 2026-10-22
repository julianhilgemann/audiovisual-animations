# Engine: how a loop is rendered

**v1 · 2026-10-22.** Stage S2 of the generative mode ([SPEC §15](../../SPEC.md#15-generative-loops)): a score and a preset become stems and a mastered mix. Code: `src/datapipe/gen/engine.py` (graph), `master.py` (loudness, limiter, seam), `plugins.py` (VST3), `run.py` (the run folder). Verified on macOS 13.5 arm64 (Apple M1) with DawDreamer 0.9.0, Python 3.12; Windows uses the same code and wheels but has not been run yet.

## Signal flow

```
 per track                                                       per send bus
 instrument ─▶ inserts ─▶ strip (fader, pan) ══▶ stem <track>.wav     sum of sends ─▶ fx ─▶ strip ══▶ stem <bus>.wav
   Faust or VST3   Faust/VST3      │                                        ▲
   notes ×2 passes                 ├──── send (dB) ─────────────────────────┘
                                   ▼
                     master sum (all strips + bus returns)
                                   │  gain to -18 LUFS (MASTER_IN_LUFS)
                                   ▼
                   master chain (second graph: playback ─▶ master fx)
                                   │  keep pass 2
                                   ▼
               gain to -14 LUFS ─▶ lookahead true-peak limiter (-1 dBTP) ══▶ mix.wav
```

- **One graph per render.** Every processor is created in graph order by a small builder; each slot records what actually played it (`sources` in the manifest).
- **Two passes.** Notes and automation are scheduled twice (0–8 s and 8–16 s), the graph renders 16 s, and samples 384,000–768,000 are kept. Tails from the end of pass 1 sound in the head of pass 2, exactly as when the loop repeats. Tails longer than 8 s would need a third pass.
- **Rendering in seconds, not beats.** `engine.render(16.0)` returns exactly 768,000 samples. Rendering by beats rounds up to the block size (16 beats gave 384,128).
- **Timing is sample-exact.** A note at 1 s + 37 samples starts on sample 48,037 (measured).
- **Stems** are each track's and each bus's strip output: after inserts and fader, before the master chain. They carry the same two gains as the mix (into the master chain, then to the target loudness) but no limiting, so they are 32-bit float. The sum of the stems equals the mix before the master chain and limiter.
- **Master staging.** The summed mix is gained to −18 LUFS before the master chain, which runs as a second small graph (a playback processor into the master fx, again two passes). The master compressor's threshold therefore means the same for every preset, whatever its track faders add up to. Without this a hot preset drove the glue compressor into 7 dB of reduction.

## Mastering (`master.py`)

1. **Loudness:** integrated BS.1770 loudness (`pyloudnorm`) of the loop played three times, so the gating blocks see it as it is heard.
2. **Gain** to the preset's `lufs` (default −14).
3. **True-peak limiter, circular:** per-sample true peak from 4× polyphase oversampling with wrap-around padding; the gain each sample needs is held over a 2 ms lookahead, released over 80 ms (one-pole, run twice around the loop so the seam starts in steady state), then averaged over the lookahead so it starts falling before each peak. Every peak sees its full reduction. Ceiling: `true_peak_db` − 0.15 dB margin.
4. **Iterate** gain and limiter until the loudness is within 0.05 LU of the target (usually two or three rounds).
5. **Report** loudness, true peak, gain, the deepest limiter reduction and the seam check into the manifest.

Measured: −14.0 ± 0.05 LUFS, −1.15 dBTP, limiter 1.3–3.7 dB across the shipped presets.

## Determinism

Same preset, seed and machine give bit-identical files: `mix.wav`, every stem, `score.json`, `frames.csv` *(tested, Faust-only; also observed with RipplerX and JC303)*. What makes it so:

- every random choice comes from a named stream, `sha256(seed:name)` into numpy's PCG64: `audio` (key, mode, progression, violation), `audio/<track>` (each track's notes), `sound/<slot>` (list-valued sound parameters);
- composed note times and lengths sit on the MIDI tick grid (1/480 beat), so `score.mid` holds the score exactly and `--midi score.mid` reproduces the mix bit for bit;
- Faust noise is a fixed-seed generator; stems are written with `scipy.io.wavfile`, because libsndfile stamps a time into float WAVs.

Across machines nothing has been compared yet. Faust renders should match closely but perhaps not bit for bit (libfaust's LLVM code generation targets each CPU); plugin output may differ more. The manifest records the OS, versions and the source of every slot.

## Built-in sounds (`dawdreamer/faust/`)

Each `.dsp` is plain Faust, compiled by DawDreamer's embedded libfaust at render time (all 13 compile in under 0.25 s each). Its `hslider`s are its parameters, set by short name from a preset. `declare voices "N"` makes it a polyphonic MIDI instrument (with `freq`, `gain` = velocity, `gate`); `declare release` is how long a voice keeps sounding after note-off. Every instrument defines `effect = _, _;`, which keeps libfaust from printing an error about a missing effect.

| DSP | Kind | What it is | Main parameters |
|---|---|---|---|
| `kick` | instrument, 2 voices | sine swept from `sweep`×`tune` down to `tune`, noise click, tanh drive; phase restarts each hit | tune, sweep, pitch_decay, decay, click, drive |
| `clap` | instrument | three noise bursts `spread` apart into a tail, band-passed, stereo noise | tone, decay, spread |
| `hat` | instrument | six squares at the 808's metal ratios + noise, band-passed; notes < 44 closed, ≥ 44 open | closed, open, tone, pitch, noise |
| `bass` | instrument, 1 voice | sine + moog-filtered saw with filter envelope and tanh; `glide` slides | cutoff, env_mod, res, decay, sustain, drive, sub, glide |
| `glass` | instrument, 8 voices | 2-op phase modulation pluck, L/R detuned, octave shimmer | ratio, index, bright, decay, release, width, shimmer |
| `pad` | instrument, 8 voices | three detuned saws per side, low-pass, slow envelope | attack, release, detune, cutoff |
| `impact` | instrument, 1 voice | boom falling from `high` to `low` Hz + low-passed noise burst | low, high, decay, noise |
| `riser` | generator | band-passed noise climbing from `low` to `high` with `amount` (automate it) | amount, low, high, level |
| `drive` | effect | tanh saturation, tone low-pass, dry/wet | drive, tone, mix |
| `filter` | effect | resonant low-pass; automate `cutoff` | cutoff, res |
| `space` | effect | Zita reverb, fully wet, high-passed input | decay, predelay (ms), lowcut, damp |
| `echo` | effect | ping-pong delay synced to the score's tempo (`bpm` is set automatically) | beats, feedback, tone, lowcut |
| `master` | effect | side below `mono_hz` removed, glue compressor | mono_hz, ratio, thresh, attack, release |

## Plugins

`dawdreamer/plugins.toml` lists free VST3 plugins chosen for: open source (or freeware), VST3 builds for Windows and macOS, small downloads, and headless rendering in DawDreamer. `uv run datapipe plugins fetch` downloads each archive for this OS, checks its sha256 and copies the bundle into `dawdreamer/plugins/<os>/<key>/` (gitignored). On macOS a `.zip` is unpacked with `ditto` (keeps the symlinks and permissions a signed bundle needs) and a `.dmg` is mounted read-only with `hdiutil`; a `.pkg` inside is unpacked with `pkgutil --expand-full`, never installed. Nothing is written outside the repo.

| Key | Kind | Size (macOS) | Headless test (macOS arm64) | Notes |
|---|---|---|---|---|
| `ripplerx` 1.5.19 | instrument | 14 MB | loads 0.37 s, renders | factory programs ring 4–13 s: set `"A Decay"`/`"B Decay"` after `Program`; programs differ by up to 9 dB in a mix (Crystal −6 to −8 LU, Kalimba −12 to −15) |
| `dexed` 1.0.1 | instrument | 10 MB | loads 0.19 s, renders | the default cartridge has no classic DX7 bells; 32 programs by name |
| `jc303` 0.13.0 | instrument | 26 MB | loads 0.28 s, renders | raw 0–1 values; output about 10 dB below the Faust bass; peaky with high resonance: put `drive` after it |
| `dragonfly_plate`, `dragonfly_hall` 3.2.10 | effect | 4 MB each | load 0.4 s, render | two Dragonfly plugins in one process print Objective-C class warnings on macOS; use one per preset |
| `supermassive` | effect | system install | loads, renders | freeware without a direct download: install it by hand on each machine |

**Fallbacks.** A slot names a plugin and a `fallback` (normally Faust). When the plugin is not fetched, or `--no-plugins` is given, the fallback plays and the run warns. Every shipped preset renders on a fresh clone.

**Levels.** Plugins come out at their own levels (RipplerX measured about 3 dB hotter than `glass`, JC303 about 10 dB quieter than `bass`). A slot's `trim_db` is added to the track fader for that candidate only, so plugin and fallback sit at the same place in the mix.

**Parameters** are set by their display name. A number is the raw 0–1 value; a string is the value as the plugin shows it, matched exactly (`Program = "Crystal"`, `"Filter Model" = "TeeBee"`) or, for numbers, to the nearest shown value (`"A Decay" = "1.2"` reads back 1.20). Display values are portable across operating systems; binary states may not be. `uv run datapipe plugins probe <key>` lists every parameter with its current display value, the program names, and renders a test.

**States.** `uv run datapipe plugins edit <key> --state dawdreamer/states/<file>` opens the plugin's own window (DawDreamer `open_editor`); when you close it, the full state is saved, and `state = "<file>"` in a slot loads it before the parameters. Not yet tried on this machine (it needs a desktop session); a state saved on macOS must be tested on Windows before relying on it.

**Latency** is not compensated. All five fetched plugins report 0 samples; the run warns if a plugin reports any.

**Windows.** The `.vst3` is passed as the bundle folder; if that fails, `load_plugin` retries the DLL inside (`Contents/x86_64-win/`). Unverified until the first Windows run.

## Known behaviour

- **A freed engine crashes its processors.** Keep the `RenderEngine` in a variable for as long as any processor made from it is used; a temporary engine segfaulted `doctor` (exit 139).
- **libfaust and plugins print from C++.** A single-voice instrument handing its voice to the next note prints `Steal release voice` on stderr. The engine captures stdout and stderr during a render; known noise is dropped and anything else becomes a run warning.
- **Polyphonic Faust parameters** are addressed as `/Sequencer/DSP1/Polyphonic/Voices/<name>/<slider>`, mono ones as `/dawdreamer/<slider>`; the engine matches them by the last segment.
- **Speed (Apple M1):** compose 2 ms, render 1.4–1.9 s (including Faust JIT compile), master 0.7 s, write 0.1 s: about 2.5–3 s per loop; a batch of four seeds took 11.7 s.
