"""`datapipe` command line: `short`, `analyze` and `tune` for the six input methods (SPEC §16, §6), `gen`, `example`,
`plugins` and `doctor`; the rest lands phase by phase (SPEC §11)."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import load_config

PLANNED = {
    "watch": ("process new files dropped into inbox/<method>/", "P4"),
}
METHOD_HELP = ("gen (A): compose a loop; master (B): one finished track; stems (C): master + stems; "
               "midi (D): master + stems + MIDI; slots (E): any stems, no instrument names; "
               "deep (F): one complex track, every feature")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="datapipe", description="Audio-reactive YouTube Shorts rendered with Blender.")
    parser.add_argument("--version", action="version", version=f"datapipe {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check the toolchain: Python libs, PyAV/FFmpeg, DawDreamer, Blender, GPU")

    gen = sub.add_parser("gen", help="compose and render an 8-second loop: score, MIDI, stems, mix (SPEC §15)")
    gen.add_argument("--preset", help="dawdreamer/presets/<name>.toml or a path (default: [gen] preset in pipeline.toml)")
    gen.add_argument("--seed", type=int, default=1, help="one seed (default 1)")
    gen.add_argument("--seeds", help="several runs: 1-8 or 3,7,11")
    gen.add_argument("--midi", type=Path, help="render this .mid instead of composing (tracks matched by name)")
    gen.add_argument("--no-plugins", action="store_true", help="use every slot's Faust fallback")
    gen.add_argument("--play", action="store_true", help="play loop_x3.wav when done (the loop three times)")
    gen.add_argument("--out", type=Path, help="parent folder for the run (default: [gen] out in pipeline.toml)")

    short = sub.add_parser("short", help="a finished YouTube Short from any input method (SPEC §16)",
                           description=f"Methods: {METHOD_HELP}. Without a method: gen.")
    _method_args(short)
    short.add_argument("--run", type=Path, help="render this run folder again (e.g. work/stems/latest), with its tuning")
    _look_args(short)
    short.add_argument("--preview", action="store_true", help="half resolution, 8 samples, fast encode")
    short.add_argument("--keep-frames", action="store_true", help="keep the PNG frames in the run folder")

    analyze = sub.add_parser("analyze", help="a run folder (controls.json, report.png) from any method, no render",
                             description=f"Methods: {METHOD_HELP}.")
    _method_args(analyze)

    tune = sub.add_parser("tune", help="open a run in Blender to tune its mapping, sliders and shape by hand (SPEC §6)",
                          description=f"Methods: {METHOD_HELP}. With an input, analyse it first; with neither an "
                                      "input nor --run, open the method's latest run. In Blender: the Datapipe tab "
                                      "of the sidebar (N); Save to run, then `datapipe short --run <run>` (or the "
                                      "panel's Render buttons) renders with what you tuned.")
    _method_args(tune)
    tune.add_argument("--run", type=Path, help="tune this run folder (e.g. work/stems/latest)")
    _look_args(tune)

    example = sub.add_parser("example", help="export a generated loop into inbox/<method>/ the way a DAW would")
    example.add_argument("method", choices=["master", "stems", "midi"])
    example.add_argument("--preset", help="dawdreamer/presets/<name>.toml (default: [gen] preset)")
    example.add_argument("--seed", type=int, default=1)
    example.add_argument("--repeat", type=int, default=3, help="loop repeats (default 3: 24 s at 120 BPM)")
    example.add_argument("--no-plugins", action="store_true", help="use every slot's Faust fallback")

    plug = sub.add_parser("plugins", help="the free VST3 plugins in dawdreamer/plugins.toml: list, fetch, probe, edit")
    plug.add_argument("action", choices=["list", "fetch", "probe", "edit"])
    plug.add_argument("names", nargs="*", help="manifest keys (default: all)")
    plug.add_argument("--force", action="store_true", help="fetch: download and unpack again")
    plug.add_argument("--state", type=Path, help="edit: the state file to load and save (e.g. dawdreamer/states/x.state)")

    for name, (help_text, phase) in PLANNED.items():
        sub.add_parser(name, help=f"{help_text} [planned: {phase}]").add_argument("args", nargs="*")
    args = parser.parse_args(argv)

    if args.command == "doctor":
        from .doctor import run_doctor
        return run_doctor(load_config())
    if args.command == "gen":
        return _gen(args)
    if args.command == "plugins":
        return _plugins(args)
    if args.command in ("short", "analyze", "tune"):
        try:
            return {"short": _short, "analyze": _analyze, "tune": _tune}[args.command](args)
        except (ValueError, FileNotFoundError) as e:      # the input's fault: say what to fix, no traceback
            print(f"datapipe {args.command}: {e}", file=sys.stderr)
            return 2
    if args.command == "example":
        from .song.example import export

        where = export(args.method, args.preset, args.seed, args.repeat, use_plugins=not args.no_plugins)
        print(f"-> {where}\n   uv run datapipe short {args.method} \"{where}\" --preview")
        return 0

    print(f"`datapipe {args.command}` is planned for phase {PLANNED[args.command][1]} (SPEC §11).", file=sys.stderr)
    return 2


def _gen(args: argparse.Namespace) -> int:
    from .gen.run import generate, play

    preset = args.preset or load_config().get("gen", {}).get("preset", "neon_house")
    seeds = _seed_list(args.seeds) if args.seeds else [args.seed]
    for seed in seeds:
        run_dir, m = generate(preset, seed, midi=args.midi, use_plugins=not args.no_plugins, out=args.out)
        music, loud = m["music"], m["loudness"]
        if "key" in music:
            print(f"{m['preset']} s{seed}: {music['key']} {music['mode']}, {'-'.join(music['progression'])}, "
                  f"{m['grid']['bpm']} BPM, violation {music['violation']}")
        else:
            print(f"{m['preset']}: {music['source']} at {m['grid']['bpm']} BPM")
        for slot, source in m["sources"].items():
            if ":" not in slot:
                print(f"  {slot:10} {source}")
        print(f"  mix {loud['lufs']} LUFS, true peak {loud['true_peak_db']} dBTP "
              f"(gain {loud['gain_db']:+} dB, limiter {loud['limiter_max_reduction_db']} dB), "
              f"seam {'ok' if m['seam']['ok'] else 'JUMPS'}, {sum(m['timings_s'].values()):.1f} s")
        print("  balance " + "  ".join(f"{k} {v:+}" for k, v in m["balance_lu"].items() if v is not None) + " LU")
        for w in m["warnings"]:
            print(f"  warning: {w}")
        print(f"  -> {run_dir}")
        if args.play:
            play(run_dir / "loop_x3.wav")
    return 0


def _method_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("method", nargs="?", choices=["gen", "master", "stems", "midi", "slots", "deep"],
                   help="the input method (default gen)")
    p.add_argument("input", nargs="?", type=Path,
                   help="master, deep: the song's file; stems, midi: the song's folder; slots: either")
    p.add_argument("--preset", help="gen: compose with this preset (default: [gen] preset)")
    p.add_argument("--seed", type=int, default=1, help="gen: the seed")
    p.add_argument("--midi", type=Path, help="gen: render this .mid through the preset instead of composing")
    p.add_argument("--no-plugins", action="store_true", help="gen: use every slot's Faust fallback")
    p.add_argument("--start", type=float, help="song: skip this many seconds of every file")
    p.add_argument("--length", type=float, help="song: keep this many seconds")
    p.add_argument("--bpm", type=float, help="song: the tempo, if the tracker gets it wrong")
    p.add_argument("--no-loop", action="store_true", help="song: don't close the picture's motion on a loop")


def _look_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--look", help="render with this look from [looks] in pipeline.toml (default: the method's)")
    p.add_argument("--style", help="the look's shape and sliders: a name in its styles/ (e.g. hex_prism) or a .toml "
                                   "(default: the run's tuning, else [methods]/[looks] style)")
    p.add_argument("--mapping", help="which sources drive the look: a name in its mappings/ or a .toml "
                                     "(default: the run's tuning, else mappings/<method>.toml)")


def _song_kwargs(args: argparse.Namespace) -> dict:
    return {"preset": args.preset, "seed": args.seed, "midi": args.midi, "use_plugins": not args.no_plugins,
            "start": args.start, "length": args.length, "bpm": args.bpm, "loop": False if args.no_loop else None}


def _analyze(args: argparse.Namespace) -> int:
    from .shorts import analyze

    run = analyze(args.method or "gen", args.input, **_song_kwargs(args))
    record = run / ("run.json" if (run / "run.json").exists() else "manifest.json")
    info = json.loads(record.read_text(encoding="utf-8"))
    controls = json.loads((run / "controls.json").read_text(encoding="utf-8"))
    tempo = f"{controls['bpm']} BPM" if controls.get("bpm") else "no tempo grid"
    print(f"{run.name}: {controls['frames']} frames ({controls['frames'] / 60:.2f} s), {tempo}")
    if "hits" in info:
        print(f"  tempo {info['tempo_source']}; sections ({info['sections_from']}): "
              + ", ".join(f"{s['name']} {s['frame'] / 60:.1f}s" for s in info["sections"]))
        print("  hits " + "  ".join(f"{k} {v}" for k, v in info["hits"].items()))
        if info["alignment"].get("checked"):
            print(f"  stems line up with the master: lag {info['alignment']['lag_ms']} ms, "
                  f"correlation {info['alignment']['correlation']}")
    for w in info.get("warnings", []):
        print(f"  warning: {w}")
    print(f"  -> {run}")
    return 0


def _short(args: argparse.Namespace) -> int:
    from .shorts import make

    mp4, report = make(args.method, args.input, run=args.run, look=args.look, preview=args.preview,
                       keep_frames=args.keep_frames, style=args.style, mapping=args.mapping, **_song_kwargs(args))
    g = report["gates"]
    print(f"{report['run']} ({report['method']}, look {report['look']}): {g['format']['video']}, "
          f"{g['format']['audio']}, {g['length']['seconds']} s")
    tuning = report["tuning"]
    print(f"  tuning: mapping {tuning['mapping']} ({tuning['mapping_from']}), style {tuning['style'] or 'look.toml'} "
          f"({tuning['style_from']})" + (f", keyframes {tuning['automation']}" if tuning["automation"] else ""))
    for name, gate in g.items():
        detail = {k: v for k, v in gate.items() if k not in ("ok", "offsets", "colour", "video", "audio", "samples")}
        print(f"  {'ok  ' if gate['ok'] else 'FAIL'} {name:9} {detail}")
    print(f"  {sum(report['timings_s'].values()):.0f} s ({report['timings_s']})")
    print(f"  -> {mp4}")
    return 0 if report["ok"] else 1


def _tune(args: argparse.Namespace) -> int:
    from .shorts import tune

    opened = tune(args.method, args.input, run=args.run, look=args.look, style=args.style, mapping=args.mapping,
                  **_song_kwargs(args))
    t = opened["tuning"]
    print(f"Tuning {opened['run'].name} in Blender (pid {opened['pid']}): the Datapipe tab in the sidebar (N).")
    print(f"  mapping {t['mapping']} ({t['mapping_from']}), style {t['style'] or 'look.toml'} ({t['style_from']})")
    print(f"  Save to run writes {opened['save_to']}")
    print(f"  then: uv run datapipe short --run \"{opened['run']}\" [--preview]   (or the panel's Render buttons)")
    print(f"  Blender's log: {opened['log']}")
    return 0


def _seed_list(text: str) -> list[int]:
    if "-" in text:
        lo, hi = (int(v) for v in text.split("-"))
        return list(range(lo, hi + 1))
    return [int(v) for v in text.split(",")]


def _plugins(args: argparse.Namespace) -> int:
    from .gen import plugins

    manifest = plugins.load_manifest()
    unknown = [n for n in args.names if n not in manifest]
    if unknown:
        print(f"unknown plugin(s): {', '.join(unknown)}; known: {', '.join(manifest)}", file=sys.stderr)
        return 2
    if args.action == "list":
        for name, entry in manifest.items():
            where = plugins.locate(name)
            status = "ready" if where else ("not installed" if "system" in entry else "not fetched")
            print(f"{name:16} {entry.get('kind', ''):10} {entry.get('version', '-'):8} {status:13} {entry['about']}")
    elif args.action == "fetch":
        for line in plugins.fetch(args.names or None, force=args.force):
            print(line)
    elif args.action == "probe":
        for name in args.names or [n for n in manifest if plugins.locate(n)]:
            print("\n".join(plugins.probe(name)))
    elif args.action == "edit":
        if len(args.names) != 1 or not args.state:
            print("usage: datapipe plugins edit <name> --state dawdreamer/states/<file>", file=sys.stderr)
            return 2
        print(plugins.edit(args.names[0], args.state))
    return 0


if __name__ == "__main__":
    sys.exit(main())
