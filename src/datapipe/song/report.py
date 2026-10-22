"""report.png (SPEC §5.2, §16.3, §16.7): what the analysis found, to judge a song's reactivity before rendering it.

Top: the master's loudness, its six bands as a heat map, the sections and the drop. Middle: every track's hits, one
row each, dot size by strength, played (MIDI) in one colour and detected (onsets) in another; then (E, F) every
feature as a heat map row. Each hit and feature row names the look signals the method's mapping drives with it, or
says it is unused. Grey lines: the bar grid, when the run has one.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ..features import BANDS, FPS  # noqa: E402

SECTION_COLOURS = {"intro": "#d9e6f2", "build": "#fbe3c4", "drop": "#f6c9c9", "breakdown": "#dcefd9",
                   "outro": "#e5e0f0", "main": "#eeeeee"}


def write(controls: dict, path: Path, mapping: dict | None = None) -> Path:
    n = controls["frames"]
    seconds = np.arange(n) / FPS
    tracks, feats = controls["tracks"], controls.get("features", {})
    targets = _targets(mapping or {})
    rows = sorted(tracks, key=lambda t: (t not in ("kick", "snare", "clap", "hats"), t))
    width = float(np.clip(n / FPS / 2.5, 10, 36))
    ratios = [1.2, 1.2, max(1.0, 0.35 * len(rows))] + ([max(1.0, 0.22 * len(feats))] if feats else [])
    fig, axes = plt.subplots(len(ratios), 1, figsize=(width, 4 + 0.32 * len(rows) + 0.2 * len(feats)), sharex=True,
                             gridspec_kw={"height_ratios": ratios})
    top, bands, hits = axes[:3]
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
    if "build" in controls["curves"]:
        top.plot(seconds, controls["curves"]["build"], color="#e67e22", lw=1, label="build")
    top.set_ylim(0, 1.15)
    top.legend(loc="upper right", fontsize=7, ncol=3, frameon=False)
    m = controls["meta"]
    tempo = f"{controls['bpm']} BPM ({m['tempo_source']})" if controls.get("bpm") else "no tempo grid"
    top.set_title(f"{m['title']} · {m['method']} · {n / FPS:.1f} s · {tempo} · sections from {m['sections_from']}",
                  fontsize=9, loc="left")

    grid = np.array([controls["bands"][b] for b in BANDS])
    bands.imshow(grid, aspect="auto", origin="lower", cmap="magma", extent=(0, n / FPS, 0, len(BANDS)),
                 interpolation="nearest")
    bands.set_yticks(np.arange(len(BANDS)) + 0.5, [_label(b, targets.get(f"band:{b}")) for b in BANDS], fontsize=7)

    for i, name in enumerate(rows):
        track = tracks[name]
        if not track["hits"]:
            continue
        f, a = np.array(track["hits"], dtype=float).T
        colour = "#1f618d" if track.get("source") == "midi" else "#b03a2e"
        hits.scatter(f / FPS, np.full(len(f), i), s=4 + 30 * a, color=colour, alpha=0.8, lw=0)
    for f in controls.get("bar_frames", []):
        hits.axvline(f / FPS, color="#999999", lw=0.4)
    hits.set_yticks(range(len(rows)), [_label(f"{r} ({len(tracks[r]['hits'])}, {tracks[r].get('source', '')})",
                                              targets.get(f"hit:{r}")) for r in rows], fontsize=7)
    hits.set_ylim(-0.7, len(rows) - 0.3)
    hits.set_xlim(0, n / FPS)

    if feats:
        names = list(feats)[::-1]                          # the first feature on top
        axes[3].imshow(np.array([feats[k] for k in names]), aspect="auto", origin="lower", cmap="viridis",
                       extent=(0, n / FPS, 0, len(names)), interpolation="nearest", vmin=0, vmax=1)
        axes[3].set_yticks(np.arange(len(names)) + 0.5, [_label(k, targets.get(f"feature:{k}")) for k in names],
                           fontsize=6)
    axes[-1].set_xlabel("seconds  ·  hits: blue = played (MIDI), red = detected; grey lines = bars; "
                        "→ the look signals each row drives")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def _targets(mapping: dict) -> dict[str, list[str]]:
    """Each source the mapping uses -> the look signals it feeds (and ``ring`` for the ring's track)."""
    out: dict[str, list[str]] = {}
    for signal, sources in mapping.get("signals", {}).items():
        for source in sources:
            out.setdefault(source, []).append(signal)
    ring = mapping.get("ring", {}).get("track")
    if ring:
        out.setdefault(f"hit:{ring}", []).append("ring")
    return out


def _label(name: str, signals: list[str] | None) -> str:
    return f"{name} → {', '.join(signals)}" if signals else f"{name} (unused)"
