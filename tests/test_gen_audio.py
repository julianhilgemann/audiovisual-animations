"""S2 render and mastering: one Faust-only render checked against the audio spec (dawdreamer/specs/engine.md)."""

import hashlib
import json

import numpy as np
import pytest
import soundfile as sf

from datapipe.gen.engine import FAUST_DIR
from datapipe.gen.master import lufs, master, true_peak_db
from datapipe.gen.plugins import load_manifest
from datapipe.gen.run import generate
from datapipe.gen.score import SAMPLE_RATE, SAMPLES


def test_every_faust_dsp_compiles():
    import dawdreamer as daw

    engine = daw.RenderEngine(SAMPLE_RATE, 256)
    for dsp in sorted(FAUST_DIR.glob("*.dsp")):
        proc = engine.make_faust_processor(dsp.stem)
        proc.set_dsp_string(dsp.read_text(encoding="utf-8"))
        assert proc.compile(), dsp.name


def test_master_hits_loudness_and_true_peak_on_a_peaky_loop():
    rng = np.random.default_rng(0)
    t = np.arange(SAMPLES) / SAMPLE_RATE
    kick = np.sin(2 * np.pi * 50 * t) * np.exp(-((t % 0.5) * 12))         # a kick every half second
    x = np.stack([kick, kick]) * 0.3 + rng.normal(0, 0.01, (2, SAMPLES))
    y, report = master(x, SAMPLE_RATE, -14.0, -1.0)
    assert abs(lufs(y, SAMPLE_RATE) + 14.0) < 0.1
    assert true_peak_db(y) <= -1.0
    assert report["limiter_max_reduction_db"] > 0


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("gen")
    run_dir, manifest = generate("neon_house", 42, use_plugins=False, out=out)
    return run_dir, manifest, out


def test_render_writes_the_run_folder_contract(run):
    run_dir, manifest, out = run
    mix, sr = sf.read(run_dir / "mix.wav", always_2d=True)
    info = sf.info(run_dir / "mix.wav")
    assert sr == 48000 and mix.shape == (SAMPLES, 2) and info.subtype == "PCM_24"
    stems = {p.stem for p in (run_dir / "stems").glob("*.wav")}
    assert stems == {"kick", "clap", "hats", "bass", "lead", "pad", "riser", "impact", "space", "echo"}
    for name in ("score.json", "score.mid", "frames.csv", "preset.toml", "loop_x3.wav", "manifest.json"):
        assert (run_dir / name).exists(), name
    assert (out / "latest" / "RUN.txt").read_text().strip() == run_dir.name
    assert json.loads((run_dir / "manifest.json").read_text())["seed"] == 42


def test_render_meets_loudness_peak_and_seam(run):
    run_dir, manifest, _ = run
    mix, _ = sf.read(run_dir / "mix.wav", always_2d=True)
    assert abs(lufs(mix.T, SAMPLE_RATE) + 14.0) < 0.5
    assert true_peak_db(mix.T) <= -0.95                       # -1 dBTP, plus 24-bit rounding
    assert manifest["seam"]["ok"]
    assert manifest["warnings"] == []


def test_render_is_bit_identical_on_rerun(run, tmp_path):
    run_dir, _, _ = run
    again, _ = generate("neon_house", 42, use_plugins=False, out=tmp_path, latest=False)
    for rel in ("mix.wav", "stems/kick.wav", "stems/space.wav", "score.json", "frames.csv"):
        assert hashlib.sha256((run_dir / rel).read_bytes()).digest() == hashlib.sha256((again / rel).read_bytes()).digest(), rel


def test_plugin_manifest_lists_both_oses():
    for name, entry in load_manifest().items():
        if "system" in entry:
            assert entry["system"].endswith(".vst3")
            continue
        for os_key in ("macos", "windows"):
            target = entry[os_key]
            assert target["url"].startswith("https://") and len(target["sha256"]) == 64, (name, os_key)
            assert target["vst3"].endswith(".vst3")


def test_plugin_slots_fall_back_to_faust_without_plugins(tmp_path):
    _, manifest = generate("glass_mallets", 1, use_plugins=False, out=tmp_path, latest=False)
    assert manifest["sources"]["lead"] == "faust:glass" and manifest["sources"]["bass"] == "faust:bass"
