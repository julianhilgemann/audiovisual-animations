"""Render the architecture diagrams: specs/*.json -> <name>.svg, <name>.png and datapipe.drawio, next to this file.

The renderer and icon kit come from the data-architecture-diagrams skill (a folder, or the .skill zip); the extra
glyphs this pipeline needs (audio, stems, MIDI, film, Blender, ...) are in icons/ and are merged into a copy of the
kit for the run. The PNGs come from the skill's render_png.py when Playwright is installed, else from macOS Quick
Look. Standard library only.

    uv run python docs/diagrams/build.py --skill <path to data-architecture-diagrams[.skill]> [--lint]

icons/x-*.svg are drawn for this repo; icons/logo-blender.svg is the Simple Icons Blender mark (CC0 artwork; the
logo is a trademark of the Blender Foundation). The kit's own icons keep the licences in its assets/icons/LICENSES.md.
"""

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPECS = ("pipeline", "methods")


def skill_dir(path: Path, tmp: Path) -> Path:
    """The skill's folder: ``path`` itself, or the folder inside a .skill zip, unpacked into ``tmp``."""
    if path.is_file():
        with zipfile.ZipFile(path) as z:
            z.extractall(tmp / "skill")
        path = tmp / "skill"
    found = next((p.parents[1] for p in [path / "scripts/diagram.py", *path.glob("*/scripts/diagram.py")] if p.exists()), None)
    if found is None:
        sys.exit(f"no scripts/diagram.py under {path}")
    return found


def merged_kit(skill: Path, tmp: Path) -> Path:
    """A copy of the skill's sprite and icons.json with icons/*.svg added (an icon here replaces one of the same id)."""
    kit = tmp / "kit"
    kit.mkdir()
    sprite = (skill / "assets/icons/sprite.svg").read_text()
    icons = json.loads((skill / "assets/icons/icons.json").read_text())
    symbols = []
    for svg in sorted((HERE / "icons").glob("*.svg")):
        text = svg.read_text().strip()
        root, inner = re.match(r"<svg([^>]*)>(.*)</svg>$", text, re.S).groups()
        keep = re.sub(r'\s(xmlns|width|height|viewBox)="[^"]*"', "", root)
        view = re.search(r'viewBox="([^"]*)"', root).group(1)
        sprite = re.sub(r'<symbol id="%s".*?</symbol>' % re.escape(svg.stem), "", sprite, flags=re.S)
        symbols.append(f'<symbol id="{svg.stem}" viewBox="{view}"{keep}>{inner}</symbol>')
        icons[svg.stem] = text
    i = sprite.rindex("</svg>")
    (kit / "sprite.svg").write_text(sprite[:i] + "".join(symbols) + sprite[i:])
    (kit / "icons.json").write_text(json.dumps(icons))
    return kit


def quicklook_png(svg: Path, tmp: Path) -> None:
    """<name>.png next to ``svg`` at 1:1, through macOS Quick Look. Quick Look only makes square thumbnails, so the
    page is centred on a square canvas first and the thumbnail cropped back to the page (sips crops around the centre)."""
    text = svg.read_text()
    root = re.search(r'viewBox="0 0 (\d+) (\d+)" width="\d+" height="\d+"', text)
    w, h = int(root.group(1)), int(root.group(2))
    s = max(w, h)
    square = tmp / svg.name
    square.write_text(text.replace(root.group(0), f'viewBox="{(w - s) / 2} {(h - s) / 2} {s} {s}" width="{s}" height="{s}"', 1))
    subprocess.run(["qlmanage", "-t", "-s", str(s), "-o", str(tmp), str(square)], check=True, capture_output=True)
    subprocess.run(["sips", "-c", str(h), str(w), str(tmp / f"{svg.name}.png"), "--out", str(svg.with_suffix(".png"))],
                   check=True, capture_output=True)
    print(f"wrote {svg.with_suffix('.png')}")


def render_pngs(skill: Path, svgs: list[Path], tmp: Path) -> None:
    """The skill's render_png.py (Playwright and Chromium) when it can run, else Quick Look on macOS."""
    if importlib.util.find_spec("playwright"):
        subprocess.run([sys.executable, str(skill / "scripts/render_png.py"), *map(str, svgs)], check=True)
    elif sys.platform == "darwin":
        for svg in svgs:
            quicklook_png(svg, tmp)
    else:
        print("no PNGs: install Playwright (pip install playwright && playwright install chromium) to render them")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skill", default=os.environ.get("DATA_ARCH_SKILL"),
                    help="the data-architecture-diagrams skill folder or .skill file (or set DATA_ARCH_SKILL)")
    ap.add_argument("--lint", action="store_true", help="print the renderer's layout warnings")
    a = ap.parse_args()
    if not a.skill:
        sys.exit("give --skill or set DATA_ARCH_SKILL")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        skill = skill_dir(Path(a.skill).expanduser(), tmp)
        kit = merged_kit(skill, tmp)
        cmd = [sys.executable, str(skill / "scripts/diagram.py"), *(str(HERE / "specs" / f"{s}.json") for s in SPECS),
               "--out", str(HERE), "--drawio", "datapipe.drawio", "--kit", str(kit)] + (["--lint"] if a.lint else [])
        subprocess.run(cmd, check=True)
        render_pngs(skill, [HERE / f"{s}.svg" for s in SPECS], tmp)


if __name__ == "__main__":
    main()
