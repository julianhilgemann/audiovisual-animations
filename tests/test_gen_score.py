"""The timing contract, score files and the frame table (dawdreamer/specs/handoff.md)."""

from datapipe.gen.compose import compose, ingest_midi, load_preset
from datapipe.gen.score import ALLOWED_BPM, FRAMES, SAMPLES, Note, Score, frame_table


def _score(bpm=120):
    return Score(bpm, {"kick": [Note(4.0, 0.25, 36, 120), Note(15.75, 0.5, 36, 100)]},
                 [("hook", 0.0), ("build", 10.0)], {"riser": [(10.0, 0.0), (16.0, 1.0)]})


def test_every_allowed_tempo_fills_the_loop_with_whole_bars_and_frames():
    assert SAMPLES == 384_000 and FRAMES == 480
    for bpm in ALLOWED_BPM:
        s = Score(bpm, {}, [("hook", 0.0)])
        assert s.total_beats * s.frames_per_beat == FRAMES
        assert s.frames_per_beat == int(s.frames_per_beat)


def test_frame_of_rounds_half_frames_up_and_wraps():
    s = _score()
    assert s.frame_of(0) == 1
    assert s.frame_of(0.25) == 9            # 7.5 frames after the downbeat
    assert s.frame_of(0.75) == 24           # 22.5: Python's round() would give 22
    assert s.frame_of(15.99) == 1           # rounds onto frame 481 = frame 1


def test_validate_catches_contract_breaks():
    assert _score().validate() == []
    assert any("grid" in e for e in Score(125, {}, [("hook", 0.0)]).validate())
    bad = _score()
    bad.tracks["kick"].append(Note(16.0, 0.25, 36, 100))
    assert any("outside the loop" in e for e in bad.validate())


def test_score_json_round_trip(tmp_path):
    s = _score()
    s.save(tmp_path / "score.json")
    assert Score.load(tmp_path / "score.json") == s


def test_frame_table_one_row_per_frame_with_triggers_gates_and_curves():
    header, rows = frame_table(_score())
    assert len(rows) == FRAMES and len(header) == len(set(header))
    col = {name: [r[i] for r in rows] for i, name in enumerate(header)}
    assert col["kick"][120] == 120 / 127 and sum(1 for v in col["kick"] if v) == 2   # beat 4 = frame 121
    assert col["kick_gate"][0] == 1 and col["kick_gate"][7] == 1    # the 15.75 note rings 0.25 beat past the end
    assert col["kick_gate"][8] == 0
    assert col["riser_curve"][0] == 0 and col["riser_curve"][-1] > 0.99
    assert col["section"][0] == 0 and col["section"][-1] == 1


def test_score_mid_round_trips_through_ingest(tmp_path):
    preset = load_preset("neon_house")
    s = compose(preset, 42)
    s.save_midi(tmp_path / "score.mid")
    back = ingest_midi(preset, tmp_path / "score.mid")
    assert back.tracks == s.tracks
    assert back.sections == s.sections
