"""`datapipe short`: a run becomes a YouTube Short in one go (S3-S7 of docs/sticky-av-shorts.md, SPEC §15).

controls.json (S3) -> the Blender project renders 480 PNG frames headless (S5) -> PyAV encodes them with the mix to
H.264/AAC MP4 at the Shorts settings (S6) -> the file is checked (S7) -> output/<run>.mp4 with a sidecar .json and
a thumbnail from the twist.
"""

import io
import json
import shutil
import subprocess
import time
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import soundfile as sf
from av.video.reformatter import VideoReformatter

from ..config import ROOT, load_config, resolve_path
from . import controls
from .master import lufs, true_peak_db
from .run import generate
from .score import FPS, FRAMES, SAMPLE_RATE, SAMPLES, Score

BT709 = 1                      # AVCOL_PRI_BT709, AVCOL_TRC_BT709, AVCOL_SPC_BT709
TV_RANGE = 1                   # AVCOL_RANGE_MPEG: 16-235


def make_short(preset: str | None = None, seed: int = 1, run: Path | None = None, preview: bool = False,
               keep_frames: bool = False, use_plugins: bool = True, midi: Path | None = None,
               progress=print, out_dir: Path | None = None, **overrides) -> tuple[Path, dict]:
    """Audio (unless ``run`` is given), controls, render, encode, check; returns the MP4 and its report.
    ``overrides`` replace profile settings (percent, eevee_samples, crf, x264_preset) for this call."""
    cfg = load_config()
    short = cfg["short"]
    profile = {**short, **(short["preview"] if preview else {}), **overrides}
    times = {}

    t = time.perf_counter()
    if run is None:
        run, _ = generate(preset or cfg["gen"]["preset"], seed, midi=midi, use_plugins=use_plugins)
    run = Path(run)
    if (run / "RUN.txt").exists():                 # work/gen/latest/ mirrors a run: render into the run itself
        run = run.parent / (run / "RUN.txt").read_text(encoding="utf-8").strip()
    times["audio"] = time.perf_counter() - t

    t = time.perf_counter()
    controls.save(run)
    frames = run / "frames"
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir()
    project = ROOT / short["project"]
    width, height = short["resolution"]
    cmd = [str(resolve_path(cfg, "blender")), "-b", str(project / short["scene"]),
           "--python", str(project / short["script"]), "--",
           "--run", str(run), "--frames-dir", str(frames), "--width", str(width), "--height", str(height),
           "--percent", str(profile["percent"]), "--samples", str(profile["eevee_samples"]),
           "--seam", "--save-blend", str(run / "scene_baked.blend")]
    blender = _blender(cmd, run / "render.log", progress)
    times["render"] = time.perf_counter() - t

    t = time.perf_counter()
    name = run.name + ("_preview" if preview else "")
    mp4 = run / f"{name}.mp4"
    encoded = encode(sorted(frames.glob("frame_*.png")), run / "mix.wav", mp4, profile["crf"], profile["x264_preset"])
    times["encode"] = time.perf_counter() - t

    t = time.perf_counter()
    score = Score.load(run / "score.json")
    report = check(mp4, frames, score, (width * profile["percent"] // 100, height * profile["percent"] // 100))
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    report["gates"]["audio_seam"] = {"ok": manifest["seam"]["ok"], **{k: v for k, v in manifest["seam"].items() if k != "ok"}}
    report["gates"]["loudness"]["aac_trim_db"] = encoded["audio_trim_db"]
    report["ok"] = all(g["ok"] for g in report["gates"].values())
    times["check"] = time.perf_counter() - t

    out_dir = Path(out_dir) if out_dir else ROOT / cfg["paths"]["output"]
    out_dir.mkdir(parents=True, exist_ok=True)
    twist = next((b for s, b in score.sections if s == "twist"), 0.0)
    thumb = frames / f"frame_{min(score.frame_of(twist) + 15, FRAMES):04d}.png"
    shutil.copyfile(thumb, out_dir / f"{name}.png")
    shutil.copyfile(mp4, out_dir / f"{name}.mp4")
    report.update({"run": run.name, "preview": preview, "blender": blender,
                   "settings": {k: profile[k] for k in ("percent", "eevee_samples", "crf", "x264_preset")},
                   "timings_s": {k: round(v, 1) for k, v in times.items()}})
    sidecar = json.dumps(report, indent=1) + "\n"
    (out_dir / f"{name}.json").write_text(sidecar, encoding="utf-8")
    (run / f"{name}.json").write_text(sidecar, encoding="utf-8")
    if not keep_frames:
        shutil.rmtree(frames)
    return out_dir / f"{name}.mp4", report


def _blender(cmd: list[str], log: Path, progress) -> dict:
    """Run Blender, keep its whole output in ``log``, report progress, return the script's result line."""
    result, started = {}, time.perf_counter()
    with open(log, "w", encoding="utf-8") as fh, subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace") as p:
        for line in p.stdout:
            fh.write(line)
            if line.startswith("STEM_TUNNEL frame "):
                done = int(line.split()[2].split("/")[0])
                if done % 60 == 0:
                    rate = (time.perf_counter() - started) / done
                    progress(f"  render {done}/{FRAMES} ({rate:.2f} s/frame)")
            elif line.startswith("STEM_TUNNEL_RESULT "):
                result = json.loads(line.split(" ", 1)[1])
    if p.returncode != 0 or not result:
        raise RuntimeError(f"Blender failed (exit {p.returncode}); see {log}")
    return result


def encode(frames: list[Path], audio: Path, out: Path, crf: int = 16, preset: str = "slow",
           ceiling_db: float = -1.0) -> dict:
    """PNG frames + WAV -> MP4 for YouTube: H.264 High, yuv420p, BT.709 matrix and tags, TV range, GOP 30 with
    2 B-frames, AAC 320 kb/s at 48 kHz, index at the front (faststart). The audio is trimmed first if its AAC
    encode would overshoot ``ceiling_db`` true peak; returns the trim."""
    if len(frames) != FRAMES:
        raise ValueError(f"expected {FRAMES} frames, found {len(frames)}")
    pcm, sr = sf.read(audio, dtype="float32", always_2d=True)
    if sr != SAMPLE_RATE or len(pcm) != SAMPLES:
        raise ValueError(f"{audio.name}: expected {SAMPLES} samples at {SAMPLE_RATE} Hz")
    pcm, trim_db = _fit_aac_true_peak(pcm, ceiling_db)
    to_yuv = VideoReformatter()
    with av.open(str(out), "w", format="mp4", options={"movflags": "+faststart"}) as container:
        video = container.add_stream("libx264", rate=FPS)
        video.codec_context.time_base = Fraction(1, FPS)
        first = _read(frames[0])
        video.width, video.height, video.pix_fmt = first.width, first.height, "yuv420p"
        cc = video.codec_context
        cc.gop_size, cc.max_b_frames = FPS // 2, 2
        cc.color_primaries = cc.color_trc = cc.colorspace = BT709
        cc.color_range = TV_RANGE
        video.options = {"crf": str(crf), "preset": preset, "profile": "high"}
        sound = container.add_stream("aac", rate=SAMPLE_RATE, layout="stereo")
        sound.bit_rate = 320_000
        for i, path in enumerate(frames):
            frame = to_yuv.reformat(_read(path), format="yuv420p", dst_colorspace="ITU709", dst_color_range="MPEG")
            frame.pts, frame.time_base = i, Fraction(1, FPS)
            container.mux(video.encode(frame))
        container.mux(video.encode())
        _encode_audio(container, sound, pcm)
    return {"audio_trim_db": round(trim_db, 2)}


def _encode_audio(container, stream, pcm: np.ndarray) -> None:
    for start in range(0, SAMPLES, 1024):
        chunk = av.AudioFrame.from_ndarray(np.ascontiguousarray(pcm[start:start + 1024].T), format="fltp",
                                           layout="stereo")
        chunk.sample_rate, chunk.pts, chunk.time_base = SAMPLE_RATE, start, Fraction(1, SAMPLE_RATE)
        container.mux(stream.encode(chunk))
    container.mux(stream.encode())


def _aac_true_peak(pcm: np.ndarray) -> float:
    """True peak in dBTP of ``pcm`` after an AAC 320 kb/s round trip in memory (the encoder is deterministic)."""
    buffer = io.BytesIO()
    with av.open(buffer, "w", format="mp4") as container:
        stream = container.add_stream("aac", rate=SAMPLE_RATE, layout="stereo")
        stream.bit_rate = 320_000
        _encode_audio(container, stream, pcm)
    buffer.seek(0)
    with av.open(buffer) as container:
        decoded = np.concatenate([f.to_ndarray() for f in container.decode(audio=0)], axis=1)
    return true_peak_db(decoded.astype(np.float64))


def _fit_aac_true_peak(pcm: np.ndarray, ceiling_db: float) -> tuple[np.ndarray, float]:
    """AAC overshoots the mix's peaks by 0.1-0.4 dB depending on the material (dense, distorted bass the most):
    lower the gain by exactly what keeps the encoded true peak under ``ceiling_db``."""
    trim = 0.0
    for _ in range(3):
        over = _aac_true_peak(pcm * 10 ** (trim / 20)) - (ceiling_db - 0.05)
        if over <= 0:
            break
        trim -= over
    return pcm * np.float32(10 ** (trim / 20)), trim


def _read(path: Path) -> av.VideoFrame:
    with av.open(str(path)) as c:
        return next(c.decode(video=0)).reformat(format="rgb24")


def check(mp4: Path, frames: Path, score: Score, size: tuple[int, int]) -> dict:
    """S7, the gates that need no human: format, length, faststart, colour tags, audio, kick sync, seam, flashes."""
    gates = {}
    with av.open(str(mp4)) as c:
        v, a = c.streams.video[0], c.streams.audio[0]
        cc, ac = v.codec_context, a.codec_context
        luma = np.array([_relative_luminance(f) for f in c.decode(video=0)])
        gates["format"] = {
            "ok": (cc.name == "h264" and (v.width, v.height) == size and v.average_rate == FPS
                   and v.pix_fmt == "yuv420p" and ac.name == "aac" and ac.sample_rate == SAMPLE_RATE
                   and ac.channels == 2),
            "video": f"{cc.name} {cc.profile} {v.width}x{v.height} {v.pix_fmt} {v.average_rate} fps",
            "audio": f"{ac.name} {ac.sample_rate} Hz {ac.channels} ch {round((ac.bit_rate or 0) / 1000)} kb/s",
            "colour": {"primaries": cc.color_primaries, "transfer": cc.color_trc, "matrix": cc.colorspace,
                       "range": cc.color_range},
        }
        gates["format"]["ok"] &= (cc.color_primaries, cc.color_trc, cc.colorspace, cc.color_range) == (1, 1, 1, 1)
        seconds = float(c.duration / av.time_base) if c.duration else 0.0
    gates["length"] = {"ok": len(luma) == FRAMES and abs(seconds - FRAMES / FPS) < 0.05,
                       "frames": len(luma), "seconds": round(seconds, 3)}
    gates["faststart"] = {"ok": _moov_first(mp4)}
    gates["loudness"] = _loudness(mp4)
    gates["sync"] = _sync(luma, score)
    gates["seam"] = _seam(frames)
    gates["flashes"] = _flashes(luma)
    return {"file": str(mp4), "bytes": mp4.stat().st_size, "ok": all(g["ok"] for g in gates.values()),
            "gates": gates}


def _loudness(mp4: Path) -> dict:
    """The delivered audio, decoded from the AAC: -14 +- 1 LUFS and true peak at most -1 dBTP."""
    with av.open(str(mp4)) as c:
        pcm = np.concatenate([f.to_ndarray() for f in c.decode(audio=0)], axis=1).astype(np.float64)
    level, peak = lufs(pcm, SAMPLE_RATE), true_peak_db(pcm)
    return {"ok": abs(level + 14) <= 1 and peak <= -1.0, "lufs": round(level, 2), "true_peak_db": round(peak, 2),
            "samples": pcm.shape[1]}


def _moov_first(mp4: Path) -> bool:
    """The index (moov) comes before the media (mdat), so a phone starts playing at once."""
    with open(mp4, "rb") as fh:
        while header := fh.read(8):
            size, kind = int.from_bytes(header[:4], "big"), header[4:8]
            if kind in (b"moov", b"mdat"):
                return kind == b"moov"
            fh.seek(size - 8, 1)
    return False


def _sync(luma: np.ndarray, score: Score) -> dict:
    """Kick against picture: the brightness peak nearest each kick, in frames after it (±4 searched)."""
    kicks = sorted({score.frame_of(n.beat) - 1 for n in score.tracks.get("kick", [])})
    offsets = []
    for f in kicks:
        window = [luma[(f + k) % FRAMES] for k in range(-4, 5)]
        offsets.append(int(np.argmax(window)) - 4)
    if not offsets:
        return {"ok": True, "kicks": 0}
    median = float(np.median(offsets))
    return {"ok": abs(median) <= 1, "kicks": len(kicks), "median_offset_frames": median,
            "within_1_frame": round(float(np.mean(np.abs(offsets) <= 1)), 2), "offsets": offsets}


def _seam(frames: Path) -> dict:
    """Frame 481 (rendered past the end) against frame 1: the same picture if the loop closes."""
    first, after = frames / "frame_0001.png", frames / f"seam_{FRAMES + 1:04d}.png"
    if not after.exists():
        return {"ok": False, "reason": "no seam frame rendered"}
    diff = float(np.abs(_read(first).to_ndarray().astype(float) - _read(after).to_ndarray().astype(float)).mean() / 255)
    return {"ok": diff < 0.002, "mean_abs_diff": round(diff, 6)}


def _relative_luminance(frame: av.VideoFrame) -> float:
    """Mean relative luminance (linear light, 0-1) of a decoded frame, the quantity WCAG's flash rule uses."""
    y = frame.to_ndarray(format="gray").astype(np.float64) / 255
    return float(np.where(y <= 0.04045, y / 12.92, ((y + 0.055) / 1.055) ** 2.4).mean())


def _flashes(luma: np.ndarray) -> dict:
    """Whole-frame flashes in mean relative luminance: a peak at least 0.1 above the darkest of the 6 frames before
    it, with that darker frame under 0.8 (WCAG 2.3.1). At most 3 per second, over every 1-second window of the loop."""
    n = len(luma)
    peaks = [i for i in range(n)
             if luma[i] >= max(luma[(i + k) % n] for k in range(-3, 4))
             and luma[i] - (dark := min(luma[(i - k) % n] for k in range(1, 7))) >= 0.1 and dark < 0.8]
    marks = np.zeros(n)
    marks[peaks] = 1
    per_second = max(int(np.roll(marks, -s)[:FPS].sum()) for s in range(n)) if peaks else 0
    swing = float(luma.max() - luma.min())
    return {"ok": per_second <= 3, "max_per_second": per_second, "count": len(peaks),
            "luma_min_mean_max": [round(float(luma.min()), 3), round(float(luma.mean()), 3), round(float(luma.max()), 3)],
            "luma_swing": round(swing, 3)}
