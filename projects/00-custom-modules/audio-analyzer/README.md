# audio_analyzer

Audio in and its analysis, in one COMP: pick where the sound comes from, and get 36 features that follow it (levels, eight bands, timbre, energy and onsets), each 0-1 and named `a_*`.

## Connectors

| Connector | |
|---|---|
| Input 1 (CHOP) | Optional audio. While something is wired here, Audio Source External Input uses it instead of the Interface Device. |
| Output 1 (CHOP) | The features, one sample per channel. |
| Output 2 (CHOP) | A 128-bin log spectrum, for visuals that want the whole curve. |
| Output 3 (CHOP) | The audio itself, as chosen. |

## Parameters

- **Sources.** Audio Source: Microphone (the default Windows input), Audio File, External Input, YouTube. YouTube Audio Link with Download Audio. Play to Speakers and Speaker Volume, for the file and YouTube only. **Interface Device** is what External Input opens when nothing is wired in (pick it from the list); **Interface Channels** picks its channels by name (`chan3 chan4`; `*` or channels it lacks mean all).
- **Transport.** Play, Position, Time, Loop and Restart for the file and YouTube audio.
- **Analysis.** Input Gain; Gate, the dBFS level below which everything reads 0; Range, how many dB below the running peak read 0; Normalize Speed; Attack and Release of the levels; Slow Energy Time.
- **Onsets.** A sensitivity for kick, snare, hat and any onset; Envelope Decay.
- **Module.** YouTube Folder (default `media/youtube` in the project) and Save Module.

## Features

| Channels | Meaning |
|---|---|
| `a_level`, `a_peak`, `a_loud`, `a_active` | Normalized RMS and peak; absolute loudness (−60 to 0 dBFS as 0-1); 1 while above the gate. |
| `a_sub`, `a_bass`, `a_lowmid`, `a_mid`, `a_highmid`, `a_presence`, `a_brilliance`, `a_air` | 20-60, 60-150, 150-400, 400-1k, 1k-2.5k, 2.5k-6k, 6k-12k and 12k-20k Hz. |
| `a_lows`, `a_mids`, `a_highs` | The bands in three groups: 20-150 Hz, 150 Hz-2.5 kHz, 2.5-20 kHz. |
| `a_centroid`, `a_rolloff`, `a_flatness`, `a_width`, `a_crest` | Brightness (80 Hz-8 kHz, log scale), where 85% of the energy lies, noisiness, stereo width, transient sharpness. |
| `a_energy`, `a_energy_slow`, `a_build`, `a_flux` | Intensity now and over Slow Energy Time; build-up above 0.5, breakdown below; spectral change. |
| `a_kick`, `a_snare`, `a_hat`, `a_onset` (+ `_env`, `_count`) | One-frame onset triggers, each with a decaying envelope and a hit count. |

## How it works

- The sources are the `source_deck` module, nested and loaded from `../source-deck/source_deck.tox`, with its video side off. Its audio parameters are bound to the analyzer's.
- Each level is measured in dB against its own running peak, which falls at Normalize Speed, so a quiet microphone and a loud file both fill 0-1. The peak never falls below Gate + Range, offset for each band by that band's usual distance from the overall level, so audio just above the gate reads near 0 instead of being blown up.
- Onsets are spectral flux peaks over an adaptive threshold (running mean plus a multiple of the running deviation) with a refractory time. The snare needs its body (180-400 Hz) and its noise (1.5-5 kHz) to rise together, so hats and basslines don't fire it.
- On a mixed electronic track, kicks landed on the quarter notes and hats on the eighths. A laptop microphone in a quiet room (about −54 dBFS) gates to 0 at the default −50 dB.
- The analysis costs about 0.3 ms per frame.

## Requirements

- TouchDesigner 2025 (built and tested on 2025.32820).
- `../source-deck/source_deck.tox` beside this folder, and for YouTube what source_deck needs: yt-dlp and yt-dlp-ejs in the host project's venv, Node.js on the PATH.

## Files

| File | |
|---|---|
| `audio_analyzer.tox` | The module. Projects load this through External .tox. |
| `audio_analyzer.tdxn` | Its network as text, written by Save Module. |
| `script_features_callbacks.py`, `module_callbacks.py` | Its scripts as text, written by Save Module. Edit them inside TouchDesigner, not here. |
