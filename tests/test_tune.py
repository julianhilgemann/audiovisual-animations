"""Tuning by hand and the tunnel's shapes (SPEC §6, P5 and P6 on the stem tunnel).

Without Blender: the mapping and style files round-trip in the tuner's canonical form, styles are checked against
look.toml, a render picks its files given > run tuning > look, and every shape repeats exactly after the periods
the look closes its loop on. With Blender: the default shape rebuilds the reference look's meshes, the tuner holds
its files exactly and a run tuned in it renders keyed as tuned, and every style's loop closes.
"""

import json
import math
import os
import shutil
import subprocess
import sys

import numpy as np
import pytest
from scipy.spatial import cKDTree

from datapipe import recipe
from datapipe.config import ROOT, load_config, resolve_path
from datapipe.gen.run import generate
from datapipe.render import look_files

LOOK = ROOT / "blender" / "stem-tunnel"
SCHEMA = recipe.load(LOOK / "look.toml")
FILES = sorted((LOOK / "mappings").glob("*.toml")) + sorted((LOOK / "styles").glob("*.toml"))
BLENDER = resolve_path(load_config(), "blender")
needs_blender = pytest.mark.skipif(not BLENDER.exists(), reason="Blender not installed here")
sys.path.insert(0, str(LOOK))
import shapes  # noqa: E402  numpy only outside Blender


# ---- files ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path", FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_mapping_and_style_files_round_trip(path):
    data, text = recipe.load(path), path.read_text(encoding="utf-8")
    dumps = recipe.dumps_mapping if path.parent.name == "mappings" else recipe.dumps_style
    assert dumps(data, SCHEMA, recipe.header(path)) == text


def test_styles_are_checked_against_the_look():
    recipe.check_style({"shape": {"profile": "star", "sides": 5}, "look": {"lens": 30.0}}, SCHEMA)
    for bad, says in (({"shape": {"profile": "blob"}}, "one of"), ({"shape": {"sides": 2}}, "outside"),
                      ({"shape": {"sides": 4.5}}, "integer"), ({"look": {"zoom": 1.0}}, "unknown key"),
                      ({"colour": {}}, "unknown tables")):
        with pytest.raises(ValueError, match=says):
            recipe.check_style(bad, SCHEMA)


def test_the_default_style_is_the_looks_defaults_and_the_builders():
    defaults = {t: {k: s["default"] for k, s in SCHEMA[t].items()} for t in ("shape", "look")}
    assert recipe.resolve_style(recipe.load(LOOK / "styles" / "default.toml"), SCHEMA) == defaults
    assert recipe.resolve_style({}, SCHEMA) == defaults
    assert shapes.DEFAULTS == defaults["shape"]
    for t in ("shape", "look"):
        for key, spec in SCHEMA[t].items():
            assert spec["help"] and spec["label"], key
            assert spec["default"] in spec["options"] if "options" in spec else spec["min"] <= spec["default"] <= spec["max"]


def test_a_render_takes_the_given_files_then_the_runs_tuning_then_the_looks(tmp_path):
    cfg = load_config()
    run = tmp_path / "run"
    run.mkdir()
    files = look_files(cfg, "stems", run=run)
    assert files["mapping"] == LOOK / "mappings" / "stems.toml" and files["style"] == LOOK / "styles" / "default.toml"
    assert files["automation"] is None and files["origin"] == {"mapping": "look", "style": "look"}
    tuned = run / "tuning" / "stem-tunnel"
    tuned.mkdir(parents=True)
    for name in ("mapping.toml", "style.toml", "automation.json"):
        (tuned / name).write_text("", encoding="utf-8")
    files = look_files(cfg, "stems", run=run)
    assert files["mapping"] == tuned / "mapping.toml" and files["style"] == tuned / "style.toml"
    assert files["automation"] == tuned / "automation.json" and files["origin"] == {"mapping": "run", "style": "run"}
    files = look_files(cfg, "stems", run=run, style="hex_prism", mapping="midi")
    assert files["style"] == LOOK / "styles" / "hex_prism.toml" and files["mapping"] == LOOK / "mappings" / "midi.toml"
    with pytest.raises(FileNotFoundError, match="known: default"):
        look_files(cfg, "stems", style="no_such_style")


# ---- shapes --------------------------------------------------------------------------------------------------------

def test_the_default_shape_is_the_reference_looks():
    geo = shapes.geometry({})
    L = 2 * math.pi * 12 / 2                                     # one wall segment of the reference look (K 2, R 12)
    p = geo["periods"]
    assert np.isclose(p["travel"], 2 * L) and np.isclose(p["roll"], 2 * math.pi)
    assert np.isclose(p["portal"], math.pi) and np.isclose(p["outer"], math.pi)
    assert [len(m["co"]) for m in geo["meshes"].values()] == [174816, 99960, 121728]     # the reference meshes


def test_every_profile_has_the_perimeter_of_its_circle():
    for name, sides in (("polygon", 3), ("polygon", 6), ("star", 5), ("flower", 8)):
        for rounding in (0.0, 0.7):
            prof = shapes.Profile({**shapes.DEFAULTS, "profile": name, "sides": sides, "corner_round": rounding})
            x, y = prof.at(np.linspace(0, 1, 20001))
            assert np.isclose(np.hypot(np.diff(x), np.diff(y)).sum(), 2 * math.pi * 12, rtol=1e-3), (name, rounding)
            assert 0 < prof.inradius() < 12 * 1.3
            x0, y0 = prof.at(np.array([0.1]))                    # S-fold symmetric: a turn of 1/S is 1/S of the way
            x1, y1 = prof.at(np.array([0.1 + 1 / sides]))
            a = 2 * math.pi / sides
            assert np.allclose([x1[0], y1[0]], [x0[0] * math.cos(a) - y0[0] * math.sin(a),
                                                x0[0] * math.sin(a) + y0[0] * math.cos(a)], atol=1e-6)


SHAPES = [recipe.load(p).get("shape", {}) for p in sorted((LOOK / "styles").glob("*.toml"))] + [
    {"symmetry": 3},                                             # odd cells: the maze repeats only once round
    {"symmetry": 4, "twist": -0.375, "walls": "zigzag", "portal_every": 3},
    {"profile": "polygon", "sides": 3, "symmetry": 6, "twist": 1.0, "wave": 0.2, "wave_count": 3},
    {"profile": "star", "sides": 6, "symmetry": 4, "walls": "truchet", "cell_depth": 0.5, "seed": 3},
]


@pytest.mark.parametrize("shape", SHAPES, ids=lambda s: ",".join(f"{k}={v}" for k, v in s.items()) or "default")
def test_every_shape_repeats_after_its_periods(shape):
    """Flying one travel period on, the tunnel is where it was, and turning by a layer's period lands it on itself:
    the motion closes on these, so the seam can't jump."""
    geo = shapes.geometry(shape)
    p, layers = geo["periods"], geo["meshes"]
    row = p["row"]
    for name, period in (("Tunnel_Walls", p["roll"]), ("Tunnel_Portals", p["portal"]), ("Tunnel_Outer", p["outer"])):
        co = layers[name]["co"]
        if not len(co):
            continue
        tree = cKDTree(co)
        z0 = -row                                                # whole rows; the tunnel reaches a period past them
        window = co[(co[:, 2] < z0) & (co[:, 2] > z0 - max(2, p["wave_rows"]) * row)]
        assert len(window), name
        shifted = window - [0.0, 0.0, p["travel"]]
        assert tree.query(shifted)[0].max() < 2e-3, f"{name} does not repeat after {p['travel']:.3f}"
        c, s = math.cos(period), math.sin(period)
        turned = window @ np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
        assert tree.query(turned)[0].max() < 2e-3, f"{name} does not repeat turned by {period:.4f}"


def test_twist_waits_until_the_turn_is_a_symmetry():
    base = shapes.periods({"symmetry": 2})
    assert np.isclose(shapes.periods({"symmetry": 2, "twist": 0.25})["travel"], 4 * base["travel"])
    assert shapes.twist_steps({"twist": 0.3}) == 0.25 + 0.0      # snapped to eighths


# ---- in Blender ----------------------------------------------------------------------------------------------------

def _blender(*args, env=None, timeout=600):
    out = subprocess.run([str(BLENDER), "-b", *map(str, args)], capture_output=True, text=True, timeout=timeout,
                         env={**os.environ, **(env or {})})
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
def test_the_default_shape_rebuilds_the_reference_meshes():
    out = _line(_blender(ROOT / "blender" / "audio-tunnel" / "neon_tunnel_audio.blend", "--python",
                         ROOT / "tests" / "fixtures" / "mesh_parity.py"), "MESH_PARITY")
    for name, m in out.items():
        assert m["verts"][0] == m["verts"][1] and m["faces"][0] == m["faces"][1], (name, m)
        assert m["max_dist"] < 1e-3, (name, m)                   # float32 at z = -1700: 0.00024


@needs_blender
def test_a_run_tuned_in_the_panel_renders_as_tuned(run, tmp_path):
    files = look_files(load_config(), "gen", run=run)
    tuned = files["tuning_dir"]
    shutil.rmtree(tuned, ignore_errors=True)
    check = _line(_blender(files["scene"], "--python", files["script"], "--python", ROOT / "tests" / "fixtures" / "tuner_check.py",
                           "--", "--tune", "--run", run, "--mapping", files["mapping"], "--style", files["style"],
                           "--method", "gen", "--save-to", tuned), "TUNER_CHECK")
    assert check["mapping_text_same"] and check["mapping_same"] and check["style_same"], check   # holds its files exactly
    assert check["changed_after_tuning"] and check["clean_after_save"], check
    assert check["saved"] == ["automation.json", "mapping.toml", "style.toml"] and check["lens_keys"] == 2
    saved = recipe.load(tuned / "mapping.toml")
    assert saved["signals"]["kick"]["hit:kick"] == 0.7 and saved["signals"]["hats"]["mix:loud"] == 0.25
    assert saved["smooth"]["bright"] == 20
    style = recipe.load(tuned / "style.toml")
    assert style["shape"]["profile"] == "polygon" and style["shape"]["walls"] == "hexes" and style["look"]["speed"] == 0.4

    files = look_files(load_config(), "gen", run=run)            # what `datapipe short --run` now picks
    assert files["origin"] == {"mapping": "run", "style": "run"} and files["automation"]
    frames = tmp_path / "frames"
    frames.mkdir()
    rendered = _line(_blender(files["scene"], "--python", files["script"], "--", "--run", run, "--frames-dir", frames,
                              "--mapping", files["mapping"], "--style", files["style"], "--automation",
                              files["automation"], "--no-render"), "STEM_TUNNEL_RESULT")
    assert rendered["baked"] == check["baked"]                   # keyed exactly as in the panel
    assert rendered["shape"]["rebuilt"] and np.isclose(rendered["shape"]["roll"], math.pi)


@needs_blender
@pytest.mark.parametrize("style", sorted(p.stem for p in (LOOK / "styles").glob("*.toml")))
def test_every_style_closes_the_loop(run, tmp_path, style):
    frames = tmp_path / "frames"
    frames.mkdir()
    out = _line(_blender(LOOK / "stem_tunnel.blend", "--python", LOOK / "stem_tunnel.py", "--", "--run", run,
                         "--frames-dir", frames, "--mapping", LOOK / "mappings" / "gen.toml", "--style",
                         LOOK / "styles" / f"{style}.toml", "--percent", 20, "--samples", 4, "--frames", "1,481"),
                "STEM_TUNNEL_RESULT")
    import av

    def read(f):
        with av.open(str(frames / f"frame_{f:04d}.png")) as c:
            return next(c.decode(video=0)).to_ndarray(format="rgb24").astype(float) / 255

    first, seam = read(1), read(481)
    assert first.mean() > 0.01, "black frame"
    assert np.abs(first - seam).mean() < 0.002, (style, out["closure"])
