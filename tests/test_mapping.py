"""datapipe.mapping: the loop-aware modulation math shared by the pipeline and Blender."""

import numpy as np

from datapipe import mapping

N = 480


def test_hit_envelope_peaks_on_the_hit_and_wraps_its_windup_and_decay():
    env = mapping.hit_envelope([(0, 1.0), (470, 0.5)], N, windup=3, decay=9)
    assert env[0] == 1.0 and env[470] == 0.5
    assert 0 < env[477] < env[478] < env[479] < env[0]          # anticipation runs over the seam
    assert env[9] < 0.06 and env[1] > env[2] > env[3]            # 5 % after `decay` frames
    assert env[475] > env[476] and env[476] > 0                  # the late hit's tail


def test_since_last_hit_wraps_around_the_seam():
    age, last = mapping.since_last_hit([(30, 0.8), (420, 0.4)], N)
    assert age[30] == 0 and last[30] == 0.8
    assert age[0] == 60 and last[0] == 0.4                       # frame 0 still sees the hit at 420
    assert np.all(mapping.since_last_hit([], N)[0] >= 1e4)


def test_close_loop_ends_on_whole_periods():
    rng = np.random.default_rng(1)
    rate = 0.3 + rng.random(N)
    for period in (7.0, 50.0, 1000.0):
        pos, info = mapping.close_loop(rate, period)
        assert len(pos) == N + 1 and pos[0] == 0
        assert abs(pos[-1] / period - round(pos[-1] / period)) < 1e-9
        assert info["periods"] == round(pos[-1] / period)
        assert np.all(np.diff(pos) >= 0)                         # forward motion never reverses


def test_close_loop_scales_instead_of_reversing_a_slow_forward_motion():
    rate = np.zeros(N)
    rate[::60] = 1.0                                            # bursts, 8 units in total
    pos, info = mapping.close_loop(rate, 20.0)                  # nearest is 0 periods: shifting would reverse
    assert info["how"] == "scaled" and info["periods"] == 1 and np.isclose(pos[-1], 20.0)
    assert np.all(np.diff(pos) >= 0)


def test_follow_and_smooth_treat_the_input_as_a_loop():
    x = np.zeros(N)
    x[-5:] = 1.0                                                # loud at the end of the loop
    y = mapping.follow(x, attack=1, release=20)
    assert y[0] > 0.5                                           # the head inherits the tail's release
    s = mapping.smooth(x, 12)
    assert s[0] > 0 and np.isclose(s.sum(), x.sum())


def test_normalize_maps_percentiles_and_survives_flat_input():
    x = np.linspace(0, 10, N)
    y = mapping.normalize(x, 5, 95)
    assert y.min() == 0 and y.max() == 1
    assert np.all(mapping.normalize(np.ones(N)) == 0)


def test_without_wrap_nothing_flows_from_the_end_into_the_start():
    x = np.zeros(N)
    x[-5:] = 1.0
    assert mapping.follow(x, attack=1, release=20, wrap=False)[0] == 0
    assert mapping.smooth(x, 12, wrap=False)[0] == 0
    env = mapping.hit_envelope([(2, 1.0), (478, 1.0)], N, windup=4, decay=9, wrap=False)
    assert env[0] > 0 and env[1] > env[0]                       # the early hit's wind-up is cut at frame 0
    assert env[479] > 0 and env[:2].max() < 0.31                 # the late hit's tail stops at the end
    age, last = mapping.since_last_hit([(30, 0.8)], N, wrap=False)
    assert age[0] >= 1e4 and last[0] == 0 and age[30] == 0 and age[40] == 10
    pos, info = mapping.integrate(np.ones(N))
    assert len(pos) == N + 1 and pos[-1] == N and info["how"] == "open"
