# How to use Datapipe

Datapipe turns music into a finished YouTube Short: a vertical 9:16 video at 60 frames a second, where a glowing neon tunnel moves to your sound. You give it audio, it gives you an MP4 that's ready to upload. There's no editing step.

This guide walks you through it step by step. You don't need to write code; you'll copy a few commands into a terminal window. For how it works inside, see the [README](../README.md) and its diagrams.

## Contents

1. [Set it up (once)](#1-set-it-up-once)
2. [How to type a command](#2-how-to-type-a-command)
3. [Pick your way in](#3-pick-your-way-in)
4. [Your first Short, with nothing to prepare](#4-your-first-short-with-nothing-to-prepare)
5. [A Short from your own music](#5-a-short-from-your-own-music)
6. [When the render finishes](#6-when-the-render-finishes)
7. [Fine-tune it in Blender](#7-fine-tune-it-in-blender)
8. [If something goes wrong](#8-if-something-goes-wrong)

## 1. Set it up (once)

You need two programs and a copy of this project. It works on a Mac or a Windows PC.

1. **Install Blender 5.2 LTS** from [blender.org/download](https://www.blender.org/download/). Install it in the normal place: on a Mac, drag it into *Applications*; on Windows, keep the installer's suggested folder. Blender draws the video.
2. **Install uv**, the tool that sets up everything else for you. On a Mac with [Homebrew](https://brew.sh): `brew install uv`. On Windows: `winget install astral-sh.uv`. Other ways are on [uv's install page](https://docs.astral.sh/uv/getting-started/installation/).
3. **Get the project.** On the [GitHub page](https://github.com/julianhilgemann/audiovisual-animations), click *Code* and then *Download ZIP*, and unzip it wherever you like. (If you use git: `git clone https://github.com/julianhilgemann/audiovisual-animations.git`.)
4. **Open a terminal in the project folder** (see [the next section](#2-how-to-type-a-command)) and run these two commands, one after the other:

   ```
   uv sync
   uv run datapipe doctor
   ```

   The first one downloads what Datapipe needs, which takes a few minutes the first time. It all stays in the project folder and uv's own folder; nothing is installed system-wide. The second one checks the setup. Every line should start with `[ok  ]` or `[info]`, and the last line should say **all required checks passed**.

If `doctor` can't find Blender because you installed it somewhere else, copy `config/machine.example.toml` to `config/machine.toml` and put Blender's location on the `blender = ...` line. The example file shows how.

## 2. How to type a command

All the commands in this guide go into a terminal, a window where you type instructions instead of clicking.

- **Open one in the project folder.** On a Mac, open the *Terminal* app, type `cd` followed by a space, drag the project folder onto the window, and press Enter. On Windows, right-click the project folder in File Explorer and choose *Open in Terminal*.
- **Run a command** by pasting it and pressing Enter. Every Datapipe command starts with `uv run datapipe`.
- **File names with spaces need quotes:** `"inbox/master/My Song.wav"`. Tip: dragging a file onto the terminal window types its location for you.
- **Wait for it.** A command is done when the terminal shows its prompt again. Text scrolling past is the pipeline telling you what it's doing.

## 3. Pick your way in

There are six ways to make a Short. They differ in what you bring. A few words first:

- **Master:** your finished song, the mixdown everyone hears. Always a single audio file.
- **Stems:** the song split into separate audio files, one per instrument (kick, bass, vocals and so on). They all start at the same moment and run equally long.
- **MIDI:** the notes your instruments played, exported from your music software.

Whatever you bring, **the sound of the video is always your master.** Stems and MIDI never change what you hear; they only tell the picture what to react to, and more detail makes the picture react more precisely.

| You have | Use method | The picture follows |
|---|---|---|
| Nothing, you just want to try it | **A** `gen` | a short loop Datapipe composes for you, 8 seconds long |
| One finished song | **B** `master` | the drums and bands it can hear in the mix |
| The song and its stems | **C** `stems` | each instrument on its own |
| The song, stems and MIDI | **D** `midi` | the exact notes, to the frame |
| Sounds that aren't a beat (ambient, field recordings, sound design) as separate files | **E** `slots` | each file, without assuming a tempo or instruments |
| One dense song where the picture should follow everything, not only the drums | **F** `deep` | loudness, tone, stereo width, pitch and the song's big changes |

## 4. Your first Short, with nothing to prepare

Method A composes a loop and makes a Short from it, so you can see the whole thing work before using your own music.

```
uv run datapipe short gen --preset neon_house --seed 42 --preview
```

- `--preview` makes a half-size test version, which takes about a minute. Leave it off for full quality, which takes about five minutes on an M1 Mac.
- `--preset` picks the style of music: `neon_house`, `phonk_180` or `glass_mallets`.
- `--seed` is any number. The same number always gives the same loop; a different number gives a new one.

The finished video is in the `output/gen/` folder. Some presets sound fuller with a few free audio plugins: `uv run datapipe plugins fetch` downloads them into the project. Without them, every sound uses a built-in stand-in.

## 5. A Short from your own music

### Step 1: Export from your music software

Export the stretch of your song you want in the video. The video is exactly as long as your master: over 1 minute you get a warning (YouTube can block a Short over a minute if music in it is claimed), and over 3 minutes Datapipe refuses.

Most audio formats work: WAV, AIFF, FLAC, MP3, M4A, even a video file (only its sound is used).

If you export stems or MIDI, **export everything over the same range, from the same start point.** Datapipe checks that stems line up with the master and stops if they don't.

**In Ableton Live:** set the loop brace over the part you want, from bar 1. Use *File > Export Audio/Video* with *Rendered Track: Master* for the master, and again with *All Individual Tracks* for the stems. For MIDI, select each MIDI track's clips over the same range, press Cmd/Ctrl+J to join them into one clip that starts at the range's start, then right-click and choose *Export MIDI Clip*.

### Step 2: Put the files in the right folder

Each method has its own folder inside `inbox/`. Give each song its own subfolder, named however you like (here `mysong`):

| Method | Put your files here |
|---|---|
| **B** master | `inbox/master/mysong.wav` |
| **C** stems | `inbox/stems/mysong/master.wav`, and the stems in `inbox/stems/mysong/stems/` |
| **D** midi | `inbox/midi/mysong/`: the same files as C (`master.wav` and `stems/`), plus the MIDI files in `midi/` |
| **E** slots | `inbox/slots/mypiece/stems/` (a `master.wav` is optional: without one, the video plays all the stems together) |
| **F** deep | `inbox/deep/mytrack.wav` |

**Name stems after what they are**, so Datapipe knows what each one is: `Kick.wav`, `Snare.wav`, `Clap.wav`, `Hats.wav`, `Bass.wav`, `Lead.wav`, `Pad.wav`, `Riser.wav`, `Impact.wav`, or `Drums.wav` for a whole drum group. Names like `1-Kick`, `Hi-Hat`, `808 Sub` or `Drum Rack` work too. A stem with any other name still works; it just doesn't get a role by default. Name the MIDI files the same way, one file per track.

For **E**, names don't matter, but order does: the first file (alphabetically) drives the strongest part of the picture (the punch), the second the body of the tunnel, the third the sparkle, the fourth the spinning rings. Number your files (`1 Hits.wav`, `2 Drone.wav`, ...) to choose.

**Not sure what it should look like?** This puts a complete example into `inbox/stems/` and prints where:

```
uv run datapipe example stems
```

(`example master` and `example midi` work too.) Open the folder and copy the layout.

### Step 3: Check what Datapipe hears (optional, takes seconds)

```
uv run datapipe analyze stems inbox/stems/mysong
```

This doesn't make a video. It writes a picture, `report.png`, into `work/stems/latest/`. It shows the song's loudness and sections, and every hit Datapipe found as a dot on the bar grid, each row labelled with the part of the picture it will move. If the beats look wrong, see [If something goes wrong](#8-if-something-goes-wrong).

Use the method's name in place of `stems`, and your file or folder, for the other methods.

### Step 4: Make a preview, then the real thing

```
uv run datapipe short stems inbox/stems/mysong --preview
uv run datapipe short stems inbox/stems/mysong
```

Replace `stems` with your method and point to your file or folder:

```
uv run datapipe short master inbox/master/mysong.wav
uv run datapipe short midi inbox/midi/mysong
uv run datapipe short slots inbox/slots/mypiece
uv run datapipe short deep inbox/deep/mytrack.wav
```

A preview is half size and quick to make. The timing in it is the same as in the final, so it's the right place to judge how the picture moves. As a rough guide on an M1 Mac, a 30-second song takes a few minutes as a preview and about a quarter of an hour at full quality.

**Useful extras** you can add to the end of a command:

| Add | What it does |
|---|---|
| `--start 30 --length 45` | use only 45 seconds, starting 30 seconds in |
| `--bpm 124` | tell it the tempo, if it guessed wrong |
| `--style hex_prism` | a different tunnel shape and look; also `square_circuit`, `star_vortex`, `flower_tube`, `speed_rails`, `truchet_maze`, or a style you saved yourself |
| `--look flythrough` | a different world altogether: the camera flies down a winding tunnel through the inside of a watch, gears turning to your beat. Add `--style warp` (hyperspace streaks), `--style kaleido` (a kaleidoscope of crystals) or `--style timewarp` (the watch at warp speed) |
| `--no-loop` | don't make the end of the video flow back into its start |

By default the picture's movement is closed into a loop, so when YouTube replays the Short it carries on without a jump.

The flythrough is slower to draw than the neon tunnel: on an M1 Mac a preview takes about as long, but full quality takes about three times as long (around 40 minutes for 30 seconds). Make previews of a few styles first, then render the one you like.

## 6. When the render finishes

The terminal prints a short list of checks, each marked `ok` or `FAIL`:

| Check | What it looks at |
|---|---|
| format, length, faststart | the file is exactly what YouTube expects and starts playing at once |
| loudness | the sound doesn't clip; a generated loop is also at YouTube's loudness |
| sync | the picture's pulses land on the beats |
| seam | the last frame flows into the first (only for looping videos) |
| flashes | the whole picture never flashes brightly, which can be unsafe for people sensitive to flashing light |

The video is saved either way. A `FAIL` tells you what to look at; [section 8](#8-if-something-goes-wrong) says what to do.

You get three files in `output/<method>/`, named after the date and the song (or, for method A, the preset and seed), plus the look and style when you chose them (`..._flythrough_warp.mp4`), so different versions don't overwrite each other:

- **the MP4**, ready to upload to YouTube Shorts as it is;
- **a PNG**, a still from a strong moment, to use as the thumbnail;
- **a JSON file** with every check and what the render used, in case you want to reproduce it.

The working files of each attempt stay in `work/<method>/`, and `work/<method>/latest/` is always the newest one. You can delete old attempts there, but a song's fine-tuning ([section 7](#7-fine-tune-it-in-blender)) is kept in its folder too.

## 7. Fine-tune it in Blender

The automatic result is a starting point. You can change, by hand and while the song plays, what reacts to what, every visual setting, and the shape of the tunnel, and then render exactly what you see. (The tuner works with the neon tunnel; the flythrough doesn't have one yet.)

### Open the tuner

```
uv run datapipe tune stems inbox/stems/mysong
```

This analyses the song first, the same as `short` does, then opens Blender. To open the song you made most recently with a method, leave out the folder: `uv run datapipe tune stems`. For a generated loop: `uv run datapipe tune gen --preset phonk_180 --seed 5`.

When Blender is open, move the mouse over the big 3D view and press **N**. A sidebar appears on the right; click its **Datapipe** tab. Press **Play** in the panel and the tunnel moves with the song while you change things.

**Coming back later.** Every song's folder in `work/` holds Blender files you can simply double-click: `scene_baked.blend` (what the last video was made from) and `tune.blend` (the tuner's own file: Blender's **Ctrl+S** keeps your changes in it, **Save to run** is what the next video uses). Blender asks whether to allow the file's scripts: click **Allow Execution**, and the Datapipe tab is back, just as you left it. (To stop Blender asking, tick *Auto Run Python Scripts* under Edit > Preferences > Save & Load.) If you don't allow it, the file still plays, only without the tab.

### The main panel

At the top, the **Datapipe tuner** panel shows which song and method you're working on and how long it is, and has these buttons:

| Button | What it does |
|---|---|
| **Play** / **Pause** | play the song with the moving picture |
| **Save to run** | keep your changes for this song. The panel says *Unsaved changes* until you do |
| **Revert** | throw away changes since you last saved |
| **Render preview**, **Render final** | save, then make the video in the background; **Open video** plays it when it's done |
| **Load run...** | switch to another song you've analysed |
| **Viewport samples** | lower it if playback stutters (it only affects the preview in Blender, not the video) |

Below it are the panels that change the picture. Click a panel's title to open it.

### What reacts to what: the two "Reactivity" panels

The picture listens to eight **signals**. Each one moves its own part of the tunnel:

| Signal | Moves |
|---|---|
| kick | the punch: zoom, a jolt in the roll, rings squeezing, walls pumping, a burst forward |
| kick_light | how much the kick lights up the picture |
| bass | walls breathing, the outer shell swelling, haze, roll |
| energy | overall glow, speed and colour cycling, following how loud the song is |
| hats | a sparkle running through the lines |
| mids | the rings spinning |
| bright | the colour palette shifting with the song's brightness |
| twist | a colour jump and an extra camera roll at the big moment (the drop) |

**Reactivity: signals** shows each signal with a meter (how strong it is right now) and the **sources** that feed it, each with a weight slider. A source's name says what it listens to: `hit:kick` is every kick hit, `stem:bass` how loud the bass stem is, `band:sub` how much deep bass is in the master, `mix:loud` the overall loudness, `curve:build` a curve that rises through a build-up, `section:drop` is on during the drop, and `feature:...` are the extra measurements of methods E and F. Raise a weight for more reaction, lower it for less, use **Add source** to pick another one from a list, and the **X** to remove one.

**Reactivity: hits, ring, motion** shapes each hit: **Wind-up** is how many frames the reaction rises before the hit, **Decay** how many it takes to fade. It also picks which sound fires the **light ring** that races into the tunnel and how bright it is, and what speeds the tunnel up over time (for example, the build-up before a drop).

### How it looks: the "Look" panels

Nine panels of sliders: **Kick**, **Bass**, **Hats and mids**, **Loudness**, **Base motion** (the overall speed, and the drift when the music is quiet), **Camera** (lens, off-centre, view distance), **Glow and colour** (bloom, hue, saturation, line style), **Layers** (glow and colour of the walls, rings and outer shell separately) and **Watermark** (how visible the faint *hyperadapted* at the top is; 0 hides it). Most change the picture at once; speeds and spins take a moment to recalculate.

**To change a slider over the course of the song** (say, a lens that zooms in through the drop), use keyframes: move to a moment in the song, set the slider, hover over it and press **I**. Move to another moment, change it, and press **I** again. Blender blends between them.

### The tunnel's shape: the "Shape" panel

Change the cross-section (**Profile**: circle, polygon, star or flower, with its sides and rounding), how many **Cells around** it has, the **Patterns** of the walls, rings and outer shell, and **Twist** or **Bulge**. With **Auto** on, the tunnel rebuilds as you drag; otherwise press **Rebuild tunnel**.

### Save and reuse: the "Styles and defaults" panel

- **Load a style**: click one of the ready-made looks (`default`, `hex_prism`, `square_circuit`, `star_vortex`, `flower_tube`, `speed_rails`, `truchet_maze`).
- **Save style as...** keeps your shape and sliders under a name of your choice, so any song can use them later with `--style <name>`.
- **Save mapping as ... default** makes your reactivity settings the starting point for *every new song* you make with this method. Use it once you're happy with how things react in general.

### Render what you tuned

Press **Render preview** or **Render final** in the panel, or close Blender and run this in the terminal:

```
uv run datapipe short --run work/stems/latest
```

(Add `--preview` for a quick test.) Your changes are kept with that song only, in its folder in `work/`. Blender's template and the other songs aren't touched, and new songs keep using the defaults.

### Tips

- **Too much glow can turn into flashing.** Turning up the kick's light, the glow sliders or the light ring can make the whole picture strobe. The *flashes* check catches it; make a preview to see.
- **Keyframes and loops:** if a keyframed slider ends at a different value than it starts, the end of the video no longer flows into its start, and the *seam* check says so. Give the last keyframe the same value as the first, or render with `--no-loop`.
- **Choppy playback in Blender** doesn't affect the video. Lower *Viewport samples* to make it smoother.

## 8. If something goes wrong

| What you see | What to do |
|---|---|
| `doctor` can't find Blender | install Blender 5.2, or put its location in `config/machine.toml` ([section 1](#1-set-it-up-once)) |
| "the stems are ... ms behind the master" (or "ahead of") | the files were exported from different start points: export them all again over the same range, from the same start |
| The beats in `report.png` are off, or the picture pulses off the beat | give the tempo: `--bpm 124` (your song's tempo) |
| A stem isn't reacting the way it should | name it after its role (`Kick`, `Bass`, ...), see [step 2](#step-2-put-the-files-in-the-right-folder) |
| The song is too long | use `--start` and `--length` to take part of it |
| *flashes* says `FAIL` | in the tuner, lower *kick_light*, the light ring's level or the glow sliders, then render again |
| *seam* says `FAIL` | the end doesn't match the start: match your first and last keyframes, or use `--no-loop` |
| *sync* says `FAIL` | the light ring follows a sound the picture doesn't pulse with: check `report.png`, and in the tuner pick another sound for the light ring |

For everything in more detail: the [README](../README.md), the tuner's own guide in [blender/stem-tunnel/README.md](../blender/stem-tunnel/README.md), and the full design in [SPEC.md](../SPEC.md).
