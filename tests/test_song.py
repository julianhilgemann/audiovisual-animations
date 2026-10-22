"""Methods B, C and D (SPEC §16): ingest, MIDI, detection, tempo, sections, the run folder and one render.

The synthetic song (fixtures/song.py) has exact ground truth: D must reproduce its MIDI, C must find it again in
the stems (M3), B in the master alone (M4).
"""

import json
import shutil

import mido
import numpy as np
import pytest
import soundfile as sf

from datapipe.config import load_config, resolve_path
from datapipe.gen.score import Score
from datapipe.shorts import analyze, make
from datapipe.song import controls as song_controls
from datapipe.song import example, ingest, midi
from fixtures.song import BEAT, BPM, INTRO_BARS, make_song, match, notes, true_frames


@pytest.fixture(scope="module")
def song(tmp_path_factory):
    folder = tmp_path_factory.mktemp("song") / "My Track"
    truth = make_song(folder)
    return folder, {name: true_frames(times) for name, times in truth.items()}


def _controls(method, folder, **settings):
    s = ingest.load(method, folder if method != "master" else folder / "master.wav", load_config())
    s.settings.update(settings)
    notes_ = midi.read(s.midi, s.settings) if method == "midi" else None
    return s, song_controls.build(s, notes_, progress=lambda *_: None)


def test_ingest_finds_the_files_names_their_roles_and_lines_them_up(song):
    folder, _ = song
    s = ingest.load("midi", folder, load_config())
    assert set(s.stems) == {"kick", "snare", "hats", "bass"} and len(s.midi) == 4
    assert s.frames == round(sf.info(folder / "master.wav").frames / 800) and len(s.master) == s.frames * 800
    assert s.alignment["checked"] and s.alignment["lag_samples"] == 0
    assert s.title == "my_track"


def test_stems_exported_from_another_start_stop_the_run(song, tmp_path):
    folder, _ = song
    shifted = tmp_path / "shifted"
    shutil.copytree(folder, shifted)
    for wav in (shifted / "stems").glob("*.wav"):
        x, sr = sf.read(wav, always_2d=True)
        sf.write(wav, np.concatenate([np.zeros((2400, 2)), x])[:len(x)], sr, subtype="FLOAT")    # 50 ms late
    with pytest.raises(ValueError, match="behind the master"):
        ingest.load("stems", shifted, load_config())


@pytest.mark.parametrize("name, role", [("1-Kick", "kick"), ("Kick Drum", "kick"), ("Bass Drum", "kick"),
                                        ("Hi-Hat", "hats"), ("808 Sub", "bass"), ("Drum Rack", "drums"),
                                        ("Snare 2", "snare"), ("Vox", None), ("Audio 3", None)])
def test_file_names_say_their_role(name, role):
    assert ingest.role_of(name) == role


def test_midi_hits_land_on_the_exact_frames(song):
    folder, truth = song
    _, c = _controls("midi", folder)
    assert c["bpm"] == BPM and c["meta"]["tempo_source"] == "midi"
    for name in ("kick", "snare", "hats", "bass"):
        assert {f for f, _ in c["tracks"][name]["hits"]} == truth[name], name
        assert c["tracks"][name]["source"] == "midi"
    assert c["tracks"]["bass"]["pitch"][0] == 33
    assert c["bar_frames"][:3] == [0, round(4 * BEAT * 60), round(8 * BEAT * 60)]


def test_stem_onsets_find_the_midi_again(song):
    """M3: kick, snare and hats from the stems within ±1 frame, at least 95 % found and at most 5 % extra."""
    folder, truth = song
    _, c = _controls("stems", folder)
    for name in ("kick", "snare", "hats"):
        m = match(c["tracks"][name]["hits"], truth[name])
        assert m["found"] >= 0.95 and m["extra"] <= 0.05 and m["median_offset"] == 0, (name, m)
        assert c["tracks"][name]["source"] == "onset"
    assert abs(c["bpm"] - BPM) < 0.5


def test_master_alone_finds_kicks_tempo_and_the_drop(song):
    """M4: from the master alone, at least 90 % of kicks within ±1 frame, the tempo, and the drop on its bar."""
    folder, truth = song
    _, c = _controls("master", folder)
    kick = match(c["tracks"]["kick"]["hits"], truth["kick"])
    hats = match(c["tracks"]["hats"]["hits"], truth["hats"])
    assert kick["found"] >= 0.9 and kick["median_offset"] == 0, kick
    assert hats["found"] >= 0.9 and hats["extra"] <= 0.05, hats
    assert abs(c["bpm"] - BPM) < 0.5
    drop = round(INTRO_BARS * 4 * BEAT * 60)
    assert [s["name"] for s in c["sections"]] == ["intro", "drop"]
    assert abs(c["meta"]["drop_frame"] - drop) <= 1
    true_kicks = [a for f, a in c["tracks"]["kick"]["hits"] if any(abs(f - t) <= 1 for t in truth["kick"])]
    others = [a for f, a in c["tracks"]["kick"]["hits"] if not any(abs(f - t) <= 1 for t in truth["kick"])]
    assert np.mean(true_kicks) > np.mean(others)            # bass notes punch less than kicks


def test_a_drum_rack_midi_file_splits_by_note_and_song_toml_sets_sections(song, tmp_path):
    folder, truth = song
    rack = tmp_path / "rack"
    shutil.copytree(folder, rack)
    for f in (rack / "midi").glob("*.mid"):
        f.unlink()
    mid = mido.MidiFile(type=1, ticks_per_beat=480)
    track = mido.MidiTrack([mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(BPM), time=0)])
    events = []
    for name, ev in notes().items():
        if name != "bass":
            for b, p, v in ev:
                events += [(round(b * 480), 1, mido.Message("note_on", note=p, velocity=v)),
                           (round(b * 480) + 60, 0, mido.Message("note_off", note=p, velocity=0))]
    now = 0
    for tick, _, msg in sorted(events, key=lambda e: (e[0], e[1])):
        track.append(msg.copy(time=tick - now))
        now = tick
    mid.tracks.append(track)
    mid.save(rack / "midi" / "Drum Rack.mid")
    (rack / "song.toml").write_text("[sections]\nintro = 1\ndrop = 5\n", encoding="utf-8")
    _, c = _controls("midi", rack)
    for name in ("kick", "snare", "hats"):
        assert {f for f, _ in c["tracks"][name]["hits"]} == truth[name], name
    assert c["sections"] == [{"name": "intro", "frame": 0}, {"name": "drop", "frame": round(16 * BEAT * 60)}]
    assert c["meta"]["sections_from"] == "song.toml"
    assert c["tracks"]["bass"]["source"] == "onset"           # no MIDI for the bass stem: detected


def test_a_run_folder_holds_the_contract(song, tmp_path):
    folder, _ = song
    run = analyze("stems", folder, out=tmp_path, progress=lambda *_: None)
    c = json.loads((run / "controls.json").read_text())
    n = c["frames"]
    assert c["method"] == "stems" and c["wrap"] is False and c["close"] is True
    for key in ("section", "phase", "beat", "bar"):
        assert len(c[key]) == n, key
    for group in (c["mix"], c["bands"], c["curves"], {k: v["loud"] for k, v in c["stems"].items()}):
        assert all(len(v) == n for v in group.values())
    assert sf.info(run / "mix.wav").frames == n * 800
    assert (run / "report.png").exists() and json.loads((run / "run.json").read_text())["alignment"]["checked"]
    assert (tmp_path / "latest" / "RUN.txt").read_text().strip() == run.name


def test_stems_of_a_generated_song_find_its_score(tmp_path):
    """Realistic material: a generated loop exported like a DAW song; the stems' onsets against its score."""
    folder = example.export("stems", "neon_house", 7, repeat=2, use_plugins=False, dest=tmp_path / "inbox",
                            work=tmp_path / "work")
    score = Score.load(folder / "score.json")
    _, c = _controls("stems", folder)
    for name in ("kick", "clap", "hats"):
        truth = {score.frame_of(n.beat) - 1 + lap * 480 for lap in range(2) for n in score.tracks[name]}
        m = match(c["tracks"][name]["hits"], truth)
        assert m["found"] >= 0.95 and m["extra"] <= 0.05, (name, m)


@pytest.mark.skipif(not resolve_path(load_config(), "blender").exists(), reason="Blender not installed here")
def test_a_song_short_end_to_end_through_blender(song, tmp_path):
    folder, _ = song
    run = analyze("midi", folder, out=tmp_path / "work", start=7.0, length=8.0, progress=lambda *_: None)
    mp4, report = make(run=run, preview=True, out_dir=tmp_path / "out", percent=20, eevee_samples=2,
                       progress=lambda *_: None)          # smaller or shorter, and hats and snares outshine kicks
    g = report["gates"]
    assert report["method"] == "midi" and g["length"]["frames"] == 480 and g["length"]["ok"], g["length"]
    assert g["format"]["ok"] and g["faststart"]["ok"] and g["loudness"]["ok"], g
    assert g["sync"]["ok"] and g["sync"]["kicks"] >= 14, g["sync"]         # the drop starts 0.74 s in
    assert g["seam"]["ok"], g["seam"]
    assert mp4.exists() and (tmp_path / "out" / f"{run.name}_preview.png").exists()
