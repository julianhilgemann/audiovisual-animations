"""`datapipe` command line. Subcommands other than `doctor` land phase by phase (SPEC §11)."""

import argparse
import sys

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
    sub.add_parser("doctor", help="check the toolchain: Python libs, PyAV/FFmpeg, Blender, TouchDesigner, bridge, GPU")
    for name, (help_text, phase) in PLANNED.items():
        sub.add_parser(name, help=f"{help_text} [planned: {phase}]").add_argument("args", nargs="*")
    args = parser.parse_args(argv)

    if args.command == "doctor":
        from .doctor import run_doctor
        return run_doctor(load_config())

    print(f"`datapipe {args.command}` is planned for phase {PLANNED[args.command][1]} (SPEC §11).", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
