"""S3, S6, S7: controls from a run, the Shorts encode and its checks; one tiny end-to-end render through Blender."""

import json
from fractions import Fraction

import av
import numpy as np
import pytest
import soundfile as sf

from datapipe.config import load_config, resolve_path
from datapipe.gen import controls
from datapipe.gen.run import generate
from datapipe.gen.score import FRAMES, SAMPLE_RATE, SAMPLES, Score
from datapipe.gen.video import _flashes, _moov_first, check, encode, make_short


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    run_dir, _ = generate("neon_house", 7, use_plugins=False, out=tmp_path_factory.mktemp("gen"), latest=False)
    return run_dir


def test_controls_hold_one_value_per_frame_for_every_track_and_stem(run):
    c = controls.build(run)
    assert c["frames"] == FRAMES and len(c["phase"]) == FRAMES and len(c["section"]) == FRAMES
    assert set(c["stems"]) == {p.stem for p in (run / "stems").glob("*.wav")}
    assert all(len(s["loud"]) == FRAMES and 0 <= min(s["loud"]) and max(s["loud"]) <= 1 for s in c["stems"].values())
    score = Score.load(run / "score.json")
    kicks = {score.frame_of(n.beat) - 1 for n in score.tracks["kick"]}
    assert {f for f, _ in c["tracks"]["kick"]["hits"]} == kicks
    assert len(c["curves"]["riser"]) == FRAMES and c["curves"]["riser"][-1] > 0.9


def _frames(folder, size=(64, 112)):
    folder.mkdir()
    for i in range(FRAMES):
        rgb = np.full((size[1], size[0], 3), 20 + (i % 60), np.uint8)
        frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
        with av.open(str(folder / f"frame_{i + 1:04d}.png"), "w") as c:
            s = c.add_stream("png")
            s.width, s.height, s.pix_fmt = size[0], size[1], "rgb24"
            c.mux(s.encode(frame))
            c.mux(s.encode())
    return sorted(folder.glob("frame_*.png"))


def test_encode_writes_a_shorts_ready_mp4(tmp_path):
    frames = _frames(tmp_path / "frames")
    t = np.arange(SAMPLES) / SAMPLE_RATE
    sf.write(tmp_path / "mix.wav", np.stack([np.sin(2 * np.pi * 220 * t)] * 2, axis=1) * 0.3, SAMPLE_RATE, subtype="PCM_24")
    mp4 = tmp_path / "short.mp4"
    encode(frames, tmp_path / "mix.wav", mp4, crf=23, preset="ultrafast")
    assert _moov_first(mp4)
    with av.open(str(mp4)) as c:
        v, a = c.streams.video[0], c.streams.audio[0]
        assert v.average_rate == Fraction(60) and v.codec_context.name == "h264" and v.pix_fmt == "yuv420p"
        assert (v.codec_context.color_primaries, v.codec_context.colorspace, v.codec_context.color_range) == (1, 1, 1)
        assert a.codec_context.name == "aac" and a.codec_context.sample_rate == SAMPLE_RATE and a.codec_context.channels == 2
        assert sum(1 for _ in c.decode(video=0)) == FRAMES
        assert abs(c.duration / av.time_base - 8.0) < 0.05


def test_flash_gate_counts_full_frame_flashes_per_second():
    calm = np.full(FRAMES, 0.05)
    assert _flashes(calm)["max_per_second"] == 0
    strobe = calm.copy()
    strobe[::15] = 0.5                                           # 4 a second
    assert not _flashes(strobe)["ok"] and _flashes(strobe)["max_per_second"] == 4
    pulse = calm.copy()
    pulse[::30] = 0.5                                            # 2 a second, allowed
    assert _flashes(pulse)["ok"]


@pytest.mark.skipif(not resolve_path(load_config(), "blender").exists(), reason="Blender not installed here")
def test_short_end_to_end_through_blender(run, tmp_path):
    mp4, report = make_short(run=run, preview=True, out_dir=tmp_path, percent=10, eevee_samples=1, progress=lambda *_: None)
    g = report["gates"]
    assert g["format"]["ok"] and g["length"]["ok"] and g["faststart"]["ok"], g
    assert g["seam"]["ok"], g["seam"]                            # frame 481 renders as frame 1
    assert g["sync"]["ok"], g["sync"]
    assert mp4.exists() and (run / "scene_baked.blend").exists()
    assert json.loads((tmp_path / f"{run.name}_preview.json").read_text())["gates"]["seam"]["ok"]
