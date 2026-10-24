"""The flythrough look (blender/flythrough): a camera that flies a winding path through gears, streaks or crystals.

Without Blender: its mapping and style files round-trip and check against look.toml, the camera's driver expressions
are the path the world is built along, every world repeats after its travel period, every prototype after its turn
period, and the gear trains mesh (tangent pitch circles, opposite turns, a tooth in a gap). With Blender: the camera
flies the path, every style closes the loop, and a run renders through the whole pipeline with this look.
"""

import json
import math
import os
import subprocess
import sys

import numpy as np
import pytest
from scipy.spatial import cKDTree

from datapipe import recipe
from datapipe.config import ROOT, load_config, resolve_path
from datapipe.gen.run import generate
from datapipe.render import look_files, open_tuner
from datapipe.shorts import make

LOOK = ROOT / "blender" / "flythrough"
SCHEMA = recipe.load(LOOK / "look.toml")
STYLES = sorted(p.stem for p in (LOOK / "styles").glob("*.toml"))
FILES = sorted((LOOK / "mappings").glob("*.toml")) + sorted((LOOK / "styles").glob("*.toml"))
BLENDER = resolve_path(load_config(), "blender")
needs_blender = pytest.mark.skipif(not BLENDER.exists(), reason="Blender not installed here")
sys.path.insert(0, str(LOOK))
import worlds  # noqa: E402  numpy only outside Blender


def shape(style: str) -> dict:
    return recipe.resolve_style(recipe.load(LOOK / "styles" / f"{style}.toml"), SCHEMA)["shape"]


# ---- files ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path", FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_mapping_and_style_files_round_trip(path):
    data, text = recipe.load(path), path.read_text(encoding="utf-8")
    dumps = recipe.dumps_mapping if path.parent.name == "mappings" else recipe.dumps_style
    assert dumps(data, SCHEMA, recipe.header(path)) == text


def test_the_look_has_a_mapping_per_method_and_the_stem_tunnels_signals():
    methods = {p.stem for p in (LOOK / "mappings").glob("*.toml")}
    assert methods == {p.stem for p in (ROOT / "blender" / "stem-tunnel" / "mappings").glob("*.toml")}
    stem = recipe.load(ROOT / "blender" / "stem-tunnel" / "look.toml")
    assert set(SCHEMA["signals"]) == set(stem["signals"])          # a recipe means the same on both looks
    for method in methods:                                           # the same sources, per method
        assert recipe.load(LOOK / "mappings" / f"{method}.toml") == \
               recipe.load(ROOT / "blender" / "stem-tunnel" / "mappings" / f"{method}.toml")


def test_the_clockwork_style_is_the_looks_defaults():
    defaults = {t: {k: spec["default"] for k, spec in SCHEMA[t].items()} for t in ("shape", "look")}
    assert recipe.resolve_style(recipe.load(LOOK / "styles" / "clockwork.toml"), SCHEMA) == defaults


def test_a_render_with_the_look_picks_its_files(tmp_path):
    files = look_files(load_config(), "stems", "flythrough", run=tmp_path, style="warp")
    assert files["scene"] == LOOK / "flythrough.blend" and files["script"] == LOOK / "flythrough.py"
    assert files["mapping"] == LOOK / "mappings" / "stems.toml" and files["style"] == LOOK / "styles" / "warp.toml"
    assert files["tuning_dir"] == tmp_path / "tuning" / "flythrough"
    assert look_files(load_config(), "gen", "flythrough")["style"] == LOOK / "styles" / "clockwork.toml"


# ---- the path and the world ----------------------------------------------------------------------------------------

def test_the_cameras_drivers_fly_the_path_the_world_is_built_along():
    p = worlds.path(shape("clockwork"))
    for travel in (0.0, 13.7, 95.9, 250.2):
        s = math.fmod(travel, p["Q"])
        e = {k: eval(v, {"sin": math.sin, "cos": math.cos, "atan": math.atan, "sqrt": math.sqrt,  # noqa: S307
                         "fmod": math.fmod, "travel": travel})
             for k, v in worlds.path_expressions(p, f"fmod(travel, {p['Q']})").items()}
        assert np.allclose([e["x"], e["y"], e["z"]], worlds.centre(s, p), atol=1e-6)
        pitch, yaw = e["pitch"], e["yaw"]                               # Euler ZXY: Ry(yaw) Rx(pitch) (0, 0, -1)
        forward = [-math.cos(pitch) * math.sin(yaw), math.sin(pitch), -math.cos(pitch) * math.cos(yaw)]
        f, up, right = worlds.frames(s, p)
        assert np.allclose(forward, f, atol=1e-6)
        assert np.allclose([math.sin(pitch) * math.sin(yaw), math.cos(pitch), math.sin(pitch) * math.cos(yaw)], up,
                           atol=1e-6)


@pytest.mark.parametrize("style", STYLES)
def test_every_world_repeats_after_its_travel_period(style):
    """What the camera sees from s + Q is what it saw from s: every vertex and every spinner (with its prototype,
    rotation, phase and channel weights) in the first stretch is found again Q further on."""
    geo = worlds.geometry(shape(style))
    q = geo["periods"]["travel"]
    for key in ("walls", "streaks"):
        co = geo[key]["co"]
        if not len(co):
            continue
        near = co[(-co[:, 2] > 0) & (-co[:, 2] < 40)]
        dist, _ = cKDTree(co).query(near - [0, 0, q])
        assert dist.max() < 1e-6, (key, dist.max())
    sp = geo["spinners"]
    near = np.flatnonzero((-sp["co"][:, 2] > 0) & (-sp["co"][:, 2] < 40))
    key = np.column_stack([sp["co"], 1000.0 * sp["proto"]])              # a portal and a slab may share a spot
    dist, idx = cKDTree(key).query(key[near] - [0, 0, q, 0])
    assert dist.max() < 1e-6
    for attr in ("rot", "phase", "wa", "wb", "proto"):
        assert np.allclose(sp[attr][near], sp[attr][idx], atol=1e-9), attr


def _turned(co: np.ndarray, angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.column_stack([c * co[:, 0] - s * co[:, 1], s * co[:, 0] + c * co[:, 1], co[:, 2]])


def _same_after_turn(mesh: worlds.Mesh, angle: float) -> float:
    co = mesh.arrays()["co"]
    return float(cKDTree(co).query(_turned(co, angle))[0].max())


@pytest.mark.parametrize("teeth", worlds.SIZES)
def test_every_gear_repeats_after_the_gear_channels_period(teeth):
    gear = worlds.gear_proto(teeth, worlds.MODULE)
    assert _same_after_turn(gear, 2 * math.pi * worlds.TEETH_PERIOD / teeth) < 1e-6


def test_every_portal_and_crystal_slab_repeats_after_the_portal_period():
    rng = np.random.default_rng(3)
    for name, mesh in (("dial", worlds.dial_proto(6.0, 9.7)), ("ring_gear", worlds.ring_gear_proto(6.0, 9.7)),
                       ("balance", worlds.balance_proto(6.0, 9.7)), ("gate", worlds.gate_proto(6.0, 9.7))):
        assert _same_after_turn(mesh, 2 * math.pi / worlds.PORTAL_ORDER) < 1e-6, name
    for k, mirror in ((6, True), (4, False)):
        for mesh in (worlds.rosette_proto(6.0, 9.7, k, mirror, rng),
                     worlds.shard_proto(10.0, 12.0, k, mirror, 1.0, rng)):
            assert _same_after_turn(mesh, 2 * math.pi / k) < 1e-6
    for style in STYLES:                                 # the portal channel closes on a turn every portal repeats on
        sh = shape(style)
        period = worlds.periods(sh)["portal"]
        orders = ([worlds.PORTAL_ORDER] if sh["portals"] not in ("none", "rosette") else []) + \
                 ([worlds.fold(sh)] if sh["portals"] == "rosette" or sh["shards"] > 0 else [])
        assert all(np.isclose((period * o / (2 * math.pi)) % 1, 0) for o in orders), style


@pytest.mark.parametrize("seed", [1, 2, 7])
def test_gear_trains_mesh(seed):
    """Each gear touches the one it meshes with on their pitch circles, turns the other way at the same tooth rate,
    and puts a gap where that one has a tooth, whatever the trains have turned; no two other gears on a level touch."""
    sh = recipe.resolve_style({"shape": {"seed": seed}}, SCHEMA)["shape"]
    q, half = worlds.path(sh)["Q"], sh["radius"] * math.tan(math.pi / sh["sides"])
    gears = worlds.gear_trains(sh, q, half, np.random.default_rng(seed))
    pairs = [(gears[g["mesh"]], g) for g in gears if g["mesh"] is not None]
    assert len(pairs) > 20
    for a, b in pairs:
        dx, dy = worlds._wrap(b["x"] - a["x"], q), b["y"] - a["y"]
        assert np.isclose(math.hypot(dx, dy), a["rp"] + b["rp"]) and a["dir"] == -b["dir"] and a["chan"] == b["chan"]
        alpha = math.atan2(dy, dx)
        for tau in (0.0, 0.37, 5.2):                                   # teeth the train has turned
            ta = a["phase"] + a["dir"] * 2 * math.pi * tau / a["t"]
            tb = b["phase"] + b["dir"] * 2 * math.pi * tau / b["t"]
            eps = (ta - alpha) % (2 * math.pi / a["t"])                  # a tooth of a, eps past the contact line
            gap = alpha + math.pi - eps * a["t"] / b["t"]                # where b must have a gap
            off = (tb + math.pi / b["t"] - gap) % (2 * math.pi / b["t"])
            assert min(off, 2 * math.pi / b["t"] - off) < 1e-9
        assert abs(b["y"]) <= half - b["ra"] + 1e-9
    meshing = {frozenset((id(a), id(b))) for a, b in pairs}
    for i, a in enumerate(gears):
        for b in gears[i + 1:]:
            if a["level"] == b["level"] and frozenset((id(a), id(b))) not in meshing:
                assert math.hypot(worlds._wrap(b["x"] - a["x"], q), b["y"] - a["y"]) >= a["ra"] + b["ra"]


# ---- in Blender ----------------------------------------------------------------------------------------------------

def _blender(*args, timeout=600):
    out = subprocess.run([str(BLENDER), "-b", *map(str, args)], capture_output=True, text=True, timeout=timeout,
                         env=dict(os.environ))
    lines = out.stdout + out.stderr
    assert "Traceback" not in lines, lines[-3000:]
    return lines


def _line(text, tag):
    return json.loads(next(ln for ln in text.splitlines() if ln.startswith(tag + " ")).split(" ", 1)[1])


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    run_dir, _ = generate("neon_house", 7, use_plugins=False, out=tmp_path_factory.mktemp("gen"), latest=False)
    from datapipe.gen import controls

    controls.save(run_dir)
    return run_dir


@needs_blender
def test_the_camera_flies_the_path(run, tmp_path):
    out = _line(_blender(LOOK / "flythrough.blend", "--python", LOOK / "flythrough.py", "--python",
                         ROOT / "tests" / "fixtures" / "flight_check.py", "--", "--run", run, "--frames-dir", tmp_path,
                         "--mapping", LOOK / "mappings" / "gen.toml", "--no-render"), "FLIGHT_CHECK")
    p = out["path"]
    travelled = [f["travel"] for f in out["frames"]]
    assert travelled == sorted(travelled) and travelled[-1] > p["Q"]  # it moves forward, past a wrap
    for f in out["frames"]:
        s = math.fmod(f["travel"], p["Q"])
        forward, up, _ = worlds.frames(s, p)
        assert np.allclose(f["location"], worlds.centre(s, p), atol=1e-3), f
        assert np.allclose(f["forward"], forward, atol=1e-4), f
        assert np.isclose(math.acos(np.clip(np.dot(f["up"], up), -1, 1)),
                          abs((f["roll"] + math.pi) % (2 * math.pi) - math.pi), atol=1e-3), f


@needs_blender
@pytest.mark.parametrize("style", STYLES)
def test_every_style_closes_the_loop(run, tmp_path, style):
    _blender(LOOK / "flythrough.blend", "--python", LOOK / "flythrough.py", "--", "--run", run, "--frames-dir",
             tmp_path, "--mapping", LOOK / "mappings" / "gen.toml", "--style", LOOK / "styles" / f"{style}.toml",
             "--percent", 20, "--samples", 4, "--frames", "1,481")
    import av

    def read(f):
        with av.open(str(tmp_path / f"frame_{f:04d}.png")) as c:
            return next(c.decode(video=0)).to_ndarray(format="rgb24").astype(float) / 255

    first, seam = read(1), read(481)
    assert first.mean() > 0.01, "black frame"
    assert np.abs(first - seam).mean() < 0.002, style


@needs_blender
def test_a_short_end_to_end_with_the_look(run, tmp_path):
    mp4, report = make(run=run, look="flythrough", preview=True, out_dir=tmp_path, percent=10, eevee_samples=1,
                       progress=lambda *_: None)
    g = report["gates"]
    assert report["look"] == "flythrough" and report["tuning"]["style"].endswith("clockwork.toml")
    assert mp4.name == f"{run.name}_flythrough_preview.mp4"           # beside the method's own look
    assert (run / "scene_baked_flythrough.blend").exists() and not (run / "scene_baked.blend").exists()
    assert g["format"]["ok"] and g["length"]["ok"] and g["seam"]["ok"] and g["sync"]["ok"], g
    assert report["blender"]["shape"]["travel"] == worlds.path(shape("clockwork"))["Q"]
    with pytest.raises(ValueError, match="no tuner"):
        open_tuner(run, look="flythrough")
