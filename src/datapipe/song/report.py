"""report.png (SPEC §5.2, §16.3): what the analysis found, to judge a song's reactivity before rendering it.

Top: the master's loudness, its six bands as a heat map, the sections and the drop. Middle: every track's hits, one
row each, dot size by strength, played (MIDI) in one colour and detected (onsets) in another. Bottom: the bar grid.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ..features import BANDS, FPS  # noqa: E402

SECTION_COLOURS = {"intro": "#d9e6f2", "build": "#fbe3c4", "drop": "#f6c9c9", "breakdown": "#dcefd9",
                   "outro": "#e5e0f0", "main": "#eeeeee"}


def write(controls: dict, path: Path) -> Path:
    n = controls["frames"]
    seconds = np.arange(n) / FPS
    tracks = controls["tracks"]
    rows = sorted(tracks, key=lambda t: (t not in ("kick", "snare", "clap", "hats"), t))
    width = float(np.clip(n / FPS / 2.5, 10, 36))
    fig, (top, bands, hits) = plt.subplots(3, 1, figsize=(width, 4 + 0.32 * len(rows)), sharex=True,
                                           gridspec_kw={"height_ratios": [1.2, 1.2, max(1.0, 0.35 * len(rows))]})
    starts = [s["frame"] for s in controls["sections"]] + [n]
    for ax in (top, hits):
        for s, end in zip(controls["sections"], starts[1:]):
            ax.axvspan(s["frame"] / FPS, end / FPS, color=SECTION_COLOURS.get(s["name"], "#eeeeee"), lw=0)
    for s in controls["sections"]:
        top.text(s["frame"] / FPS + 0.1, 1.02, s["name"], fontsize=8, va="bottom")
    drop = controls["meta"].get("drop_frame")
    if drop is not None:
        top.axvline(drop / FPS, color="#c0392b", lw=1.5)
    top.plot(seconds, controls["mix"]["loud"], color="#222222", lw=0.8, label="loudness")
    top.plot(seconds, controls["mix"]["bright"], color="#2e86c1", lw=0.6, alpha=0.7, label="brightness")
    top.plot(seconds, controls["curves"]["build"], color="#e67e22", lw=1, label="build")
    top.set_ylim(0, 1.15)
    top.legend(loc="upper right", fontsize=7, ncol=3, frameon=False)
    m = controls["meta"]
    top.set_title(f"{m['title']} · {m['method']} · {n / FPS:.1f} s · {controls['bpm']} BPM ({m['tempo_source']}) · "
                  f"sections from {m['sections_from']}", fontsize=9, loc="left")

    grid = np.array([controls["bands"][b] for b in BANDS])
    bands.imshow(grid, aspect="auto", origin="lower", cmap="magma", extent=(0, n / FPS, 0, len(BANDS)),
                 interpolation="nearest")
    bands.set_yticks(np.arange(len(BANDS)) + 0.5, list(BANDS), fontsize=7)

    for i, name in enumerate(rows):
        track = tracks[name]
        if not track["hits"]:
            continue
        f, a = np.array(track["hits"], dtype=float).T
        colour = "#1f618d" if track.get("source") == "midi" else "#b03a2e"
        hits.scatter(f / FPS, np.full(len(f), i), s=4 + 30 * a, color=colour, alpha=0.8, lw=0)
    for f in controls["bar_frames"]:
        hits.axvline(f / FPS, color="#999999", lw=0.4)
    hits.set_yticks(range(len(rows)), [f"{r} ({len(tracks[r]['hits'])}, {tracks[r].get('source', '')})" for r in rows],
                    fontsize=7)
    hits.set_ylim(-0.7, len(rows) - 0.3)
    hits.set_xlim(0, n / FPS)
    hits.set_xlabel("seconds  ·  hits: blue = played (MIDI), red = detected; grey lines = bars")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
