"""Methods E (slots) and F (deep), SPEC §16.7: M5 on non-musical stems with known events (fixtures/texture.py), M6 on
the synthetic song's master (fixtures/song.py) and on a tonal-then-percussive signal with known pitch and width.
"""

import json
import time

import numpy as np
import pyloudnorm
import pytest
import soundfile as sf

from datapipe.config import load_config, resolve_path
from datapipe.shorts import analyze, make
from datapipe.song import deep, ingest, slots
from fixtures.song import BEAT, INTRO_BARS, make_song, match, true_frames
from fixtures.texture import burst_times, make_texture

SR = 48000


@pytest.fixture(scope="module")
def texture(tmp_path_factory):
    folder = tmp_path_factory.mktemp("texture") / "Wind and Hits"
    make_texture(folder)
    (folder / "song.toml").write_text('slots = ["Bursts", "Texture"]\n', encoding="utf-8")
    return folder, {int(np.floor(t * 60 + 0.5)) for t in burst_times()}


@pytest.fixture(scope="module")
def song(tmp_path_factory):
    folder = tmp_path_factory.mktemp("song") / "My Track"
    truth = make_song(folder, midi=False, stems=False)
    return folder / "master.wav", {name: true_frames(times) for name, times in truth.items()}


def _slots(folder, **settings):
    s = ingest.load("slots", folder, load_config())
    s.settings.update(settings)
    return s, slots.build(s, progress=lambda *_: None)


def test_slots_follow_song_toml_and_without_a_master_the_stems_sum_is_heard(texture):
    folder, _ = texture
    s, c = _slots(folder)
    assert c["meta"]["slots"] == {"slot1": "stems/Bursts.wav", "slot2": "stems/Texture.wav", "slot3": "stems/Drone.wav"}
    total = sum(x for x in s.stems.values())
    assert np.allclose(s.master, total * (np.abs(s.master).max() / np.abs(total).max()), atol=1e-5)
    assert np.abs(s.master).max() <= ingest.SUM_PEAK + 1e-6 and "scaled to -1 dBFS" in " ".join(s.warnings)
    one = ingest.load("slots", folder / "stems" / "Drone.wav", load_config())
    assert list(one.stems) == ["slot1"] and np.array_equal(one.stems["slot1"], one.master)


def test_slot_transients_find_the_events_and_nothing_in_a_drone_or_a_texture(texture):
    """M5: the injected bursts within ±1 frame (at least 95 % found, at most 5 % extra), no hits where there are no
    events, the transient and loudness curves on the events, and no tempo, kick or section step."""
    folder, truth = texture
    _, c = _slots(folder)
    m = match(c["tracks"]["slot1"]["hits"], truth)
    assert m["found"] >= 0.95 and m["extra"] <= 0.05 and m["median_offset"] == 0, m
    assert c["tracks"]["slot2"]["hits"] == [] and c["tracks"]["slot3"]["hits"] == []
    f = c["features"]
    transient, loud = np.array(f["slot1.transient"]), np.array(f["slot1.loud"])
    on_time = [max(transient[t - 1:t + 2]) >= 0.5 for t in truth]
    rises = [int(np.argmax(loud[t - 3:t + 7] >= 0.5 * loud[t - 3:t + 7].max())) - 3 for t in truth]   # half way up
    assert np.mean(on_time) >= 0.95 and np.mean(np.abs(rises) <= 1) >= 0.95, (on_time, rises)
    assert max(f["slot2.transient"]) < 0.25 and max(f["slot3.transient"]) < 0.1
    assert np.mean(f["slot3.active"][120:]) > 0.95 and np.mean(f["slot1.active"]) < 0.5
    assert c["bpm"] is None and "beat" not in c and c["meta"]["tempo_source"] == "none"
    assert c["sections"] == [{"name": "main", "frame": 0}] and list(c["curves"]) == ["energy"]
    n = c["frames"]
    assert all(len(v) == n and 0 <= min(v) and max(v) <= 1 for v in f.values())


def test_slots_take_a_grid_only_when_given_a_tempo(texture):
    folder, _ = texture
    _, c = _slots(folder, bpm=100)
    assert c["bpm"] == 100 and len(c["beat"]) == c["frames"] and c["meta"]["tempo_source"] == "given"


def test_deep_measures_the_whole_mix(song, tmp_path):
    """M6 on the synthetic song: the drop within one bar from novelty alone, the kicks among the low hits, the drop
    louder than the intro, every feature 0-1 on the frame grid, and the analysis under 2x real time."""
    master, truth = song
    t = time.perf_counter()
    run = analyze("deep", master, out=tmp_path, progress=lambda *_: None)
    elapsed = time.perf_counter() - t
    c = json.loads((run / "controls.json").read_text())
    n = c["frames"]
    assert elapsed < 2 * n / 60, elapsed
    drop = round(INTRO_BARS * 4 * BEAT * 60)
    assert [s["name"] for s in c["sections"]] == ["intro", "drop"]
    assert abs(c["meta"]["drop_frame"] - drop) <= 4 * BEAT * 60
    assert match(c["tracks"]["low"]["hits"], truth["kick"])["found"] >= 0.9
    f = c["features"]
    assert np.mean(f["loud.short"][drop + 60:]) > np.mean(f["loud.short"][:drop - 60]) + 0.3
    assert all(len(v) == n and 0 <= min(v) and max(v) <= 1 for v in f.values())
    assert set(c["tracks"]) == {"low", "mid", "high"} and c["bpm"] is None
    assert (run / "report.png").exists() and c["meta"]["loudness"]["integrated"] < 0


def test_deep_loudness_is_bs1770():
    """The K-weighted windows against pyloudnorm on a steady signal (no gating): within 0.1 LU."""
    t = np.arange(4 * SR) / SR
    x = np.stack([0.1 * np.sin(2 * np.pi * 1000 * t), 0.05 * np.sin(2 * np.pi * 120 * t)], axis=1)
    reference = pyloudnorm.Meter(SR).integrated_loudness(x)
    ours = deep.window_lufs(x, len(t) // 800, 180)
    assert abs(np.median(ours) - reference) < 0.1, (np.median(ours), reference)


def test_deep_splits_tonal_from_percussive_and_names_the_pitch(tmp_path):
    """M6: 4 s of a wide A (440 Hz, left sine, right cosine), then 4 s of mono noise clicks. The harmonic share is
    right on 95 % of the frames where one part dominates, the pitch class is A, and the width follows."""
    t = np.arange(4 * SR) / SR
    tone = 0.3 * np.stack([np.sin(2 * np.pi * 440 * t), np.cos(2 * np.pi * 440 * t)], axis=1)
    tone *= np.minimum(t / 0.05, 1)[:, None]
    clicks = np.zeros(4 * SR)
    rng = np.random.default_rng(7)
    for k in range(32):
        start = int(k * SR / 8)
        clicks[start:start + 720] += 0.5 * rng.standard_normal(720) * np.exp(-np.arange(720) / 120)
    x = np.concatenate([tone, np.stack([clicks, clicks], axis=1)])
    sf.write(tmp_path / "split.wav", x, SR, subtype="FLOAT")
    run = analyze("deep", tmp_path / "split.wav", out=tmp_path / "work", progress=lambda *_: None)
    f = {k: np.array(v) for k, v in json.loads((run / "controls.json").read_text())["features"].items()}
    tonal, percussive = slice(20, 220), slice(260, 470)
    sounding = np.abs(clicks.reshape(-1, 800)).max(axis=1)[percussive.start - 240:percussive.stop - 240] > 0.05
    assert np.mean(f["harmonic.share"][tonal] > 0.5) >= 0.95
    assert np.mean(f["harmonic.share"][percussive][sounding] < 0.5) >= 0.95
    assert np.mean(np.abs(f["pitch.class"][tonal] - 9 / 12) < 1e-6) >= 0.95
    assert np.mean(f["stereo.width"][tonal]) > 0.9 and np.mean(f["stereo.width"][percussive]) < 0.05


blender = pytest.mark.skipif(not resolve_path(load_config(), "blender").exists(), reason="Blender not installed here")


@blender
def test_a_slots_short_end_to_end_through_blender(texture, tmp_path):
    folder, _ = texture
    run = analyze("slots", folder, out=tmp_path / "work", length=8.0, progress=lambda *_: None)
    mp4, report = make(run=run, preview=True, out_dir=tmp_path / "out", percent=20, eevee_samples=2,
                       progress=lambda *_: None)
    g = report["gates"]
    assert report["method"] == "slots" and g["length"]["frames"] == 480 and g["length"]["ok"], g["length"]
    assert g["format"]["ok"] and g["faststart"]["ok"] and g["loudness"]["ok"] and g["flashes"]["ok"], g
    assert g["sync"]["ok"] and g["sync"]["track"] == "slot1" and g["sync"]["hits"] >= 10, g["sync"]
    assert g["seam"]["ok"], g["seam"]
    assert mp4.exists()


@blender
def test_a_deep_short_end_to_end_through_blender(song, tmp_path):
    master, _ = song
    run = analyze("deep", master, out=tmp_path / "work", start=4.0, length=8.0, progress=lambda *_: None)
    mp4, report = make(run=run, preview=True, out_dir=tmp_path / "out", percent=20, eevee_samples=2,
                       progress=lambda *_: None)
    g = report["gates"]
    assert report["method"] == "deep" and g["length"]["frames"] == 480 and g["length"]["ok"], g["length"]
    assert g["format"]["ok"] and g["faststart"]["ok"] and g["loudness"]["ok"] and g["flashes"]["ok"], g
    assert g["sync"]["ok"] and g["sync"]["track"] == "low" and g["sync"]["hits"] >= 8, g["sync"]
    assert g["seam"]["ok"], g["seam"]
    assert mp4.exists()
