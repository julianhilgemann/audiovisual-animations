"""S1 compose: the audio design rules of dawdreamer/specs/audio.md, checked on every shipped preset."""

import copy

import pytest

from datapipe.gen.compose import PRESET_DIR, VIOLATIONS, compose, euclid, load_preset, resolve_sounds, stream

PRESETS = sorted(p.stem for p in PRESET_DIR.glob("*.toml"))


def test_euclid_spreads_hits_evenly():
    pattern = euclid(5, 16)
    onsets = [i for i, v in enumerate(pattern) if v]
    gaps = {(b - a) % 16 for a, b in zip(onsets, onsets[1:] + onsets[:1])}
    assert len(onsets) == 5 and gaps <= {3, 4}


def test_streams_depend_only_on_seed_and_name():
    assert stream(7, "audio/kick").integers(1 << 30) == stream(7, "audio/kick").integers(1 << 30)
    assert stream(7, "audio/kick").integers(1 << 30) != stream(7, "audio/hats").integers(1 << 30)


@pytest.mark.parametrize("name", PRESETS)
@pytest.mark.parametrize("seed", [1, 2, 3, 42])
def test_preset_composes_a_valid_loop_that_follows_the_story(name, seed):
    preset = load_preset(name)
    s = compose(preset, seed)
    assert s.validate() == []
    assert compose(preset, seed).to_json() == s.to_json()               # deterministic
    assert s.meta["violation"] in VIOLATIONS                             # exactly one violation per loop
    assert [n for n, _ in s.sections] == ["hook", "twist", "build", "windup"]
    assert any(n.beat == 0 for n in s.tracks["kick"])                    # strong downbeat at sample 0
    motif = [t for t, spec in preset["track"].items() if spec["role"] == "motif"]
    assert all(any(n.beat == 0 for n in s.tracks[t]) for t in motif)     # the motif's first note with it
    last_beat = s.total_beats - 1
    for t, spec in preset["track"].items():
        if spec.get("windup", "drop") == "drop":
            assert all(n.beat + n.dur <= last_beat + 1e-9 for n in s.tracks[t]), t   # the last beat drops out


def test_editing_one_track_never_reshuffles_another():
    preset = load_preset("neon_house")
    edited = copy.deepcopy(preset)
    edited["track"]["lead"]["length"] = [3]
    a, b = compose(preset, 5), compose(edited, 5)
    for t in ("kick", "clap", "hats", "bass", "pad"):
        assert a.tracks[t] == b.tracks[t]


def test_sound_lists_are_picked_by_the_seed():
    preset = load_preset("glass_mallets")
    programs = ["Crystal", "Kalimba", "Vibes"]
    preset["track"]["lead"]["instrument"]["params"]["Program"] = programs
    picked = {resolve_sounds(preset, seed)[0]["track"]["lead"]["instrument"]["params"]["Program"] for seed in range(12)}
    assert len(picked) > 1 and picked <= set(programs)
    assert resolve_sounds(preset, 5)[1] == resolve_sounds(preset, 5)[1]
