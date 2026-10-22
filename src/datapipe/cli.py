"""`datapipe` command line. Subcommands other than `doctor`, `gen` and `plugins` land phase by phase (SPEC §11)."""

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import load_config

PLANNED = {
    "run": ("one job end to end", "P3"),
    "watch": ("process new files dropped into inbox/", "P4"),
    "analyze": ("features.json, features_60fps.csv and report.png for a file", "P2"),
    "rerender": ("re-render a job with another preset, mapping or profile", "P4"),
    "preview": ("open a job in the Blender GUI for tweaking", "P5"),
}


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

    short = sub.add_parser("short", help="a generated loop as a finished YouTube Short: audio, Blender render, MP4 (SPEC §15)")
    short.add_argument("--preset", help="compose a new loop with this preset (default: [gen] preset)")
    short.add_argument("--seed", type=int, default=1)
    short.add_argument("--run", type=Path, help="use this existing run folder (e.g. work/gen/latest) instead of composing")
    short.add_argument("--midi", type=Path, help="render this .mid through the preset instead of composing")
    short.add_argument("--preview", action="store_true", help="half resolution, 8 samples, fast encode")
    short.add_argument("--keep-frames", action="store_true", help="keep the PNG frames in the run folder")
    short.add_argument("--no-plugins", action="store_true", help="use every slot's Faust fallback")

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
    if args.command == "short":
        return _short(args)

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


def _short(args: argparse.Namespace) -> int:
    from .gen.video import make_short

    mp4, report = make_short(args.preset, args.seed, run=args.run, preview=args.preview, keep_frames=args.keep_frames,
                             use_plugins=not args.no_plugins, midi=args.midi)
    g = report["gates"]
    print(f"{report['run']}: {g['format']['video']}, {g['format']['audio']}, {g['length']['seconds']} s")
    for name, gate in g.items():
        detail = {k: v for k, v in gate.items() if k not in ("ok", "offsets", "colour", "video", "audio", "samples")}
        print(f"  {'ok  ' if gate['ok'] else 'FAIL'} {name:9} {detail}")
    print(f"  {sum(report['timings_s'].values()):.0f} s ({report['timings_s']})")
    print(f"  -> {mp4}")
    return 0 if report["ok"] else 1


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
