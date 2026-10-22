"""The six input methods behind two calls (SPEC §16): ``analyze`` makes a run folder, ``make`` a finished Short.

    from datapipe import shorts
    mp4, report = shorts.make("gen", preset="neon_house", seed=42)     # A: compose, render, encode, check
    mp4, report = shorts.make("master", "inbox/master/song.wav")       # B: one finished track
    mp4, report = shorts.make("stems", "inbox/stems/mytrack")          # C: master + stems
    mp4, report = shorts.make("midi", "inbox/midi/mytrack", preview=True)   # D: master + stems + MIDI
    mp4, report = shorts.make("slots", "inbox/slots/mypiece")          # E: any stems, no instrument names
    mp4, report = shorts.make("deep", "inbox/deep/track.wav")          # F: one complex track, every feature
    run = shorts.analyze("stems", "inbox/stems/mytrack")              # up to controls.json and report.png
    mp4, report = shorts.make(run=run)                                 # render a run again (method from the run)
"""

import json
import time
from pathlib import Path

from .config import load_config
from .render import make_short, resolve_run

METHODS = ("gen", "master", "stems", "midi", "slots", "deep")


def analyze(method: str, input: Path | None = None, *, preset: str | None = None, seed: int = 1,
            midi: Path | None = None, use_plugins: bool = True, out: Path | None = None,
            start: float | None = None, length: float | None = None, bpm: float | None = None,
            loop: bool | None = None, progress=print) -> Path:
    """A run folder with controls.json and mix.wav for any method; ``input`` is the song's file (master, deep) or
    folder (stems, midi), either for slots. ``gen`` composes from ``preset`` and ``seed`` (or renders ``midi``)
    instead."""
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; one of {', '.join(METHODS)}")
    if method == "gen":
        from .gen import controls
        from .gen.run import generate

        run, _ = generate(preset or load_config()["gen"]["preset"], seed, midi=midi, use_plugins=use_plugins,
                          out=out)
        controls.save(run)
        return run
    if input is None:
        raise ValueError(f"method {method!r} needs an input: the song's {'file' if method == 'master' else 'folder'}")
    from .song.run import analyze as analyze_song

    return analyze_song(method, Path(input), out=out, start=start, length=length, bpm=bpm, loop=loop,
                        progress=progress)


def make(method: str | None = None, input: Path | None = None, *, run: Path | None = None, look: str | None = None,
         preview: bool = False, keep_frames: bool = False, progress=print, out_dir: Path | None = None,
         preset: str | None = None, seed: int = 1, midi: Path | None = None, use_plugins: bool = True,
         start: float | None = None, length: float | None = None, bpm: float | None = None,
         loop: bool | None = None, **overrides) -> tuple[Path, dict]:
    """A finished Short: analyse (unless ``run`` is given), render with the method's look, encode, check. Returns
    the MP4 in output/<method>/ and its report. ``overrides`` replace profile settings (percent, eevee_samples,
    crf, x264_preset) for this call."""
    t = time.perf_counter()
    if run is None:
        run = analyze(method or "gen", input, preset=preset, seed=seed, midi=midi, use_plugins=use_plugins,
                      start=start, length=length, bpm=bpm, loop=loop, progress=progress)
    else:
        run = resolve_run(run)
        if not (run / "controls.json").exists():           # a run from `datapipe gen`: build its controls now
            from .gen import controls

            controls.save(run)
        made_by = json.loads((run / "controls.json").read_text(encoding="utf-8")).get("method", "gen")
        if method and method != made_by:
            raise ValueError(f"{run} was made by method {made_by!r}, not {method!r}")
    analysed = time.perf_counter() - t
    mp4, report = make_short(run, look=look, preview=preview, keep_frames=keep_frames, progress=progress,
                             out_dir=out_dir, **overrides)
    report["timings_s"] = {"analyze": round(analysed, 1), **report["timings_s"]}
    return mp4, report
