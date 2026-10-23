"""Stem tunnel: the neon lines tunnel, driven by a run's controls.json (any method, SPEC §16), rendered headless.

The pipeline calls it (`datapipe short <method>`); by hand:

    blender -b blender/stem-tunnel/stem_tunnel.blend --python blender/stem-tunnel/stem_tunnel.py -- \\
        --run work/<method>/<run> --frames-dir work/<method>/<run>/frames \\
        --mapping blender/stem-tunnel/mappings/<method>.toml [--style blender/stem-tunnel/styles/<name>.toml] \\
        [--automation <run>/tuning/stem-tunnel/automation.json] [--percent 50] [--samples 8] [--seam]

`datapipe tune` opens the same scene in the Blender GUI with the tuner panel (tuner.py, `--tune`), which bakes with
these same functions, so what you tune is what renders. The scene a render saves (`--save-blend`) carries the panel
too: open it in Blender, allow its scripts, and tune on.

Rebuild the template from the reference scene, e.g. after re-tuning the look in blender/audio-tunnel:

    blender -b blender/audio-tunnel/neon_tunnel_audio.blend --python blender/stem-tunnel/stem_tunnel.py -- \\
        --make-template blender/stem-tunnel/stem_tunnel.blend

Every reaction is a driver on the AudioSignals empty (the run's modulators, baked one key per frame) and the
NeonControls empty (the look's sliders, look.toml). All drivers are simple expressions, so no Python auto-run is
needed (only the panel a saved scene carries is). The geometry comes from shapes.py and the style's [shape].
"""

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from bpy_extras import anim_utils

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
sys.path.insert(0, str(HERE))
from datapipe import mapping, recipe  # noqa: E402  numpy and the standard library only, shared with the pipeline
import shapes  # noqa: E402

CTRL, SIG, CAM = "NeonControls", "AudioSignals", "NeonCam"
TUNNEL = shapes.LAYERS
LAYER_KEYS = {"Tunnel_Walls": "walls", "Tunnel_Portals": "portals", "Tunnel_Outer": "outer"}
FPS = 60
FRAMES = 480                   # a generated loop; a run's own length comes from its controls.json
LEVELS = ("kick", "kick_light", "bass", "energy", "hats", "mids", "bright", "twist")    # 0-1 look signals
DEG = 4 * math.pi / 360        # the roll and spin unit of the look's sliders (as in blender/audio-tunnel)
SCHEMA = recipe.load(HERE / "look.toml")
MOTION = tuple(k for k, spec in SCHEMA["look"].items() if spec.get("motion"))
SHADER = ("hue_base", "hue_depth", "hue_across", "saturation", "line_edges", "line_core", "line_sharp", "fill_glow",
          "wave_amount", "view_far")                                  # look values the material reads directly
EMIT, HUE_D, RING_W, RING_GAIN = 10.0, 14.0, 3.0, 22.0                # the reference look's constants
MARK, MARK_TEXT = "Watermark", "hyperadapted"
MARK_NEAR = 0.1                # the watermark's distance in front of the camera, just past its clip start


def main() -> None:
    a = parse_args()
    if a.make_template:
        make_template(a.make_template)
        return
    if a.tune:
        import tuner

        tuner.start(a)
        return
    t0 = time.time()
    scene, ctrl = bpy.context.scene, bpy.data.objects[CTRL]
    controls = json.loads((a.run / "controls.json").read_text(encoding="utf-8"))
    n = _frames[0] = controls["frames"]
    cfg = recipe.load(a.mapping)
    style = recipe.resolve_style(recipe.load(a.style) if a.style else {}, SCHEMA)
    built = apply_style(style)
    if a.automation:
        set_automation(ctrl, json.loads(a.automation.read_text(encoding="utf-8")))
    levels, closure = bake_run(controls, cfg, ctrl)
    wire(scene, ctrl)
    configure(scene, a.width, a.height, a.percent, a.samples, a.frames_dir, n)
    set_sound(scene, a.run / "mix.wav")
    if a.save_blend:
        import tuner

        tuner.keep(a)
        bpy.ops.wm.save_as_mainfile(filepath=str(a.save_blend), compress=True, copy=True)
    timings = {"bake_s": round(time.time() - t0, 2)}
    if a.frames:
        for f in a.frames:
            scene.frame_set(f)
            scene.render.filepath = str(a.frames_dir / f"frame_{f:04d}.png")
            bpy.ops.render.render(write_still=True)
    elif not a.no_render:
        t1 = time.time()
        bpy.app.handlers.render_post.append(_progress)
        bpy.ops.render.render(animation=True)
        timings["render_s"] = round(time.time() - t1, 1)
        if a.seam:
            scene.frame_set(n + 1)
            scene.render.filepath = str(a.frames_dir / f"seam_{n + 1:04d}.png")
            bpy.ops.render.render(write_still=True)
    summary = {"closure": closure, "timings": timings, "shape": shape_info(ctrl, built), "baked": baked_digest(),
               "signals": {k: [round(float(v.min()), 3), round(float(v.mean()), 3), round(float(v.max()), 3)]
                           for k, v in levels.items() if k in LEVELS}}
    print("STEM_TUNNEL_RESULT " + json.dumps(summary), flush=True)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(prog="stem_tunnel.py")
    p.add_argument("--run", type=Path, help="a work/<method>/<run> folder with controls.json and mix.wav")
    p.add_argument("--frames-dir", type=Path, help="where frame_0001.png, frame_0002.png ... go")
    p.add_argument("--mapping", type=Path, default=HERE / "mappings" / "gen.toml",
                   help="mappings/<method>.toml: which of the run's sources drive the look")
    p.add_argument("--style", type=Path, help="styles/<name>.toml: the shape and the sliders (default: look.toml's)")
    p.add_argument("--automation", type=Path, help="keyframed sliders saved by the tuner (automation.json)")
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.add_argument("--percent", type=int, default=100)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--seam", action="store_true", help="also render frame n + 1, which must match frame 1")
    p.add_argument("--frames", type=lambda s: [int(f) for f in s.split(",")],
                   help="render only these frames (e.g. 1,481) as frame_<n>.png")
    p.add_argument("--save-blend", type=Path, help="save the baked scene here, with the tuner panel, to open and tune")
    p.add_argument("--no-render", action="store_true")
    p.add_argument("--tune", action="store_true", help="open the tuner panel instead of rendering (GUI)")
    p.add_argument("--method", help="the panel: the run's method, for saving its default mapping")
    p.add_argument("--save-to", type=Path, help="the panel: where 'Save to run' writes (the run's tuning folder)")
    p.add_argument("--pipeline-python", help="the panel: the pipeline's Python, for its render buttons")
    p.add_argument("--make-template", type=Path, help="turn the open reference scene into the template, save it here")
    a = p.parse_args(argv)
    if not a.make_template and not a.tune and not (a.run and a.frames_dir):
        p.error("--run and --frames-dir are required to render")
    return a


# ---- modulators -> look signals ------------------------------------------------------------------------------------

def look_signals(controls: dict, cfg: dict) -> dict[str, np.ndarray]:
    """The look's 0-1 signals from the run's modulators, as the method's mapping wires them."""
    n, wrap = controls["frames"], controls.get("wrap", True)
    zeros = np.zeros(n)
    hit_shapes = cfg.get("hit", {})
    ease = int(cfg.get("motion", {}).get("section_ease", 15))

    def source(name: str) -> np.ndarray:
        kind, _, key = name.partition(":")
        if kind == "hit":
            track = controls["tracks"].get(key)
            shape = {**hit_shapes.get("default", {}), **hit_shapes.get(key, {})}
            return (mapping.hit_envelope(track["hits"], n, shape.get("windup", 0), shape.get("decay", 8), wrap=wrap)
                    if track else zeros)
        if kind == "stem":
            return np.asarray(controls["stems"].get(key, {}).get("loud", zeros))
        if kind == "mix":
            return np.asarray(controls["mix"][key])
        if kind == "band":
            return np.asarray(controls.get("bands", {}).get(key, zeros))
        if kind == "curve":
            return np.asarray(controls["curves"].get(key, zeros))
        if kind == "section":
            return section(controls, key, ease)
        if kind == "feature":
            return np.asarray(controls.get("features", {}).get(key, zeros))
        raise ValueError(f"mapping: unknown source {name!r}")

    out = {name: np.clip(sum((w * source(s) for s, w in sources.items()), zeros), 0.0, 1.0)
           for name, sources in cfg["signals"].items()}
    for name, frames in cfg.get("smooth", {}).items():
        out[name] = mapping.smooth(out[name], frames, wrap)
    for name in LEVELS:
        out.setdefault(name, zeros)
    ring_cfg = cfg.get("ring", {})
    ring = controls["tracks"].get(ring_cfg.get("track", "kick"))
    out["kick_age"], last = mapping.since_last_hit(ring["hits"] if ring else [], n, wrap)
    out["kick_last"] = float(ring_cfg.get("level", 1.0)) * last
    out["hue_off"] = float(cfg.get("motion", {}).get("twist_hue", 0.0)) * out["twist"]
    return out


def available_sources(controls: dict) -> list[str]:
    """Every source a mapping can read from this run, as `kind:name`."""
    names = [f"hit:{t}" for t in controls.get("tracks", {})]
    names += [f"stem:{s}" for s in controls.get("stems", {})]
    names += [f"mix:{m}" for m in controls.get("mix", {})]
    names += [f"band:{b}" for b in controls.get("bands", {})]
    names += [f"curve:{c}" for c in controls.get("curves", {})]
    names += [f"section:{s}" for s in dict.fromkeys(s["name"] for s in controls.get("sections", []))]
    names += [f"feature:{f}" for f in controls.get("features", {})]
    return names


def section(controls: dict, name: str, ease: int) -> np.ndarray:
    """1 inside a section of the story, with linear ramps of ``ease`` frames centred on its edges."""
    n = controls["frames"]
    starts = sorted((s["frame"], s["name"]) for s in controls["sections"]) + [(n, "")]
    gate = np.zeros(n)
    for (a, nm), (b, _) in zip(starts, starts[1:]):
        if nm == name:
            gate[a:b] = 1.0
    return mapping.smooth(gate, ease, controls.get("wrap", True))


def motion(levels: dict, controls: dict, ctrl, cfg: dict) -> tuple[dict, dict]:
    """Accumulated motion as positions (n + 1 keys). Unless the run says ``close: false``, each is closed on the
    loop so frame n + 1 is frame 1's picture, on the periods of the built shape (shapes.periods).

    Rates follow the reference look's drivers (blender/audio-tunnel), plus a build curve (the riser) and the twist.
    A keyframed slider counts frame by frame."""
    n = controls["frames"]
    c = lambda k: look_value(ctrl, k, n)  # noqa: E731
    m = cfg.get("motion", {})
    row = float(ctrl["_period_row"])                             # speed counts rows, whatever their length
    riser = np.asarray(controls["curves"].get(m.get("speed_curve", "riser"), np.zeros(n)))
    rates = {
        "travel": (12 * row / 360 * c("speed") * (c("speed_idle") + c("speed_energy") * levels["energy"]
                   + c("speed_kick") * levels["kick"] + float(m.get("speed_riser", 0)) * riser), "_period_travel"),
        "roll": (DEG * (c("roll_idle") + c("roll_bass") * levels["bass"] + float(m.get("roll_twist", 0)) * levels["twist"]),
                 "_period_roll"),
        "outer": (DEG * (c("outer_spin_idle") + c("outer_spin_hats") * levels["hats"]), "_period_outer"),
        "portal": (0.03 * c("portal_spin_mids") * levels["mids"], "_period_portal"),
        "phase": ((c("color_idle") + c("color_energy") * levels["energy"]) / 360, None),
    }
    tracks, closure = {}, {}
    close = controls.get("close", True)
    for name, (rate, period) in rates.items():
        rate = np.broadcast_to(rate, (n,))
        period = float(ctrl[period]) if period else 1.0
        tracks[name], closure[name] = mapping.close_loop(rate, period) if close else mapping.integrate(rate)
    return tracks, closure


def loop_keys(levels: dict) -> dict:
    """n + 1 keys per level signal: frame n + 1 repeats frame 1, so the loop's restart is a real keyframe (and the
    seam check renders frame 1's levels)."""
    return {k: np.append(v, v[0]) for k, v in levels.items()}


def bake_run(controls: dict, cfg: dict, ctrl) -> tuple[dict, dict]:
    """Signals and motion from the run and the mapping, keyed on AudioSignals; returns the signals and the closure."""
    levels = look_signals(controls, cfg)
    tracks, closure = motion(levels, controls, ctrl, cfg)
    bake(loop_keys(levels) | tracks)
    return levels, closure


# ---- the look's sliders, keyframes and shape ---------------------------------------------------------------------

def channelbag(owner):
    ad = owner.animation_data
    return anim_utils.animdata_get_channelbag_for_assigned_slot(ad) if ad and ad.action else None


def fcurve(owner, name: str):
    bag = channelbag(owner)
    return bag.fcurves.find(f'["{name}"]') if bag else None


def look_value(ctrl, name: str, n: int):
    """A slider's value, or its value on every frame 1..n when it is keyframed."""
    fc = fcurve(ctrl, name)
    if fc is None or not len(fc.keyframe_points):
        return float(ctrl[name])
    return np.array([fc.evaluate(f) for f in range(1, n + 1)])


def automation(ctrl) -> dict:
    """The keyframed sliders, as automation.json holds them: every key with its handles and interpolation."""
    out = {}
    bag = channelbag(ctrl)
    for fc in (bag.fcurves if bag else []):
        name = fc.data_path[2:-2] if fc.data_path.startswith('["') else None
        if name not in SCHEMA["look"] or not len(fc.keyframe_points):
            continue
        out[name] = {"extrapolation": fc.extrapolation, "keys": [
            {"co": list(k.co), "interpolation": k.interpolation, "easing": k.easing,
             "left": list(k.handle_left), "right": list(k.handle_right),
             "left_type": k.handle_left_type, "right_type": k.handle_right_type} for k in fc.keyframe_points]}
    return {"version": 1, "params": out}


def set_automation(ctrl, data: dict) -> None:
    """Key the sliders as ``automation()`` saved them (replacing any keys they had)."""
    for name, curve in data.get("params", {}).items():
        if name not in SCHEMA["look"]:
            raise ValueError(f"automation: unknown slider {name!r}")
        ctrl.animation_data_create()
        if ctrl.animation_data.action is None:
            ctrl.animation_data.action = bpy.data.actions.new("NeonControls")
        old = fcurve(ctrl, name)
        if old is not None:
            channelbag(ctrl).fcurves.remove(old)
        fc = ctrl.animation_data.action.fcurve_ensure_for_datablock(ctrl, f'["{name}"]')
        fc.extrapolation = curve.get("extrapolation", "CONSTANT")
        for key in curve["keys"]:
            k = fc.keyframe_points.insert(key["co"][0], key["co"][1], options={"FAST"})
            k.interpolation, k.easing = key["interpolation"], key["easing"]
            k.handle_left_type, k.handle_right_type = key["left_type"], key["right_type"]
            k.handle_left, k.handle_right = key["left"], key["right"]
        fc.update()


def apply_style(style: dict) -> dict | None:
    """Set the sliders from a resolved style and build its shape if the scene has another; returns what a rebuild
    built (None when the shape was already there)."""
    ctrl = bpy.data.objects[CTRL]
    for key, value in style["look"].items():
        ctrl[key] = float(value)
    return ensure_shape(style["shape"], ctrl)


def ensure_shape(shape: dict, ctrl, force: bool = False) -> dict | None:
    """Rebuild the tunnel meshes (shapes.py) unless they already have this shape; record its periods on NeonControls."""
    signature = json.dumps(shape, sort_keys=True)
    if not force and ctrl.get("_built_shape") == signature:
        return None
    t = time.time()
    collection = bpy.data.objects[CTRL].users_collection[0]
    info = shapes.build(shape, bpy.data.materials["NeonLine"], collection)
    for key, value in info["periods"].items():
        ctrl[f"_period_{key}"] = float(value)
    ctrl["_inradius"], ctrl["_built_shape"] = float(info["inradius"]), signature
    for name in TUNNEL:
        ob = bpy.data.objects[name]
        ob.pass_index = 1 if name == "Tunnel_Portals" else 0           # the near fade dims pass index 1
        for prop in ("layer_glow", "layer_hue"):
            if prop not in ob:
                ob[prop] = 0.0
    info["build_s"] = round(time.time() - t, 2)
    return info


def baked_digest() -> str:
    """A fingerprint of everything baked: every key on AudioSignals and NeonControls, and the built shape. The tuner
    and the headless render print it, so a test can see they keyed the scene the same."""
    h = hashlib.sha256(str(bpy.data.objects[CTRL].get("_built_shape")).encode())
    for owner in (bpy.data.objects[SIG], bpy.data.objects[CTRL]):
        bag = channelbag(owner)
        for fc in sorted(bag.fcurves if bag else [], key=lambda fc: fc.data_path):
            co = np.empty(2 * len(fc.keyframe_points), np.float32)
            fc.keyframe_points.foreach_get("co", co)
            h.update(fc.data_path.encode() + co.tobytes())
    return h.hexdigest()[:16]


def shape_info(ctrl, built: dict | None) -> dict:
    out = {k[len("_period_"):]: round(float(ctrl[k]), 6) for k in ctrl.keys() if k.startswith("_period_")}
    if built:
        out.update(rebuilt=True, verts=built["verts"], build_s=built["build_s"])
    return out


# ---- scene ---------------------------------------------------------------------------------------------------------

def bake(values: dict) -> None:
    """One linear key per frame on the AudioSignals empty, replacing whatever was there. Properties that stay are
    kept, so the drivers reading them stay valid while the tuner re-bakes."""
    sig = bpy.data.objects[SIG]
    for k in list(sig.keys()):
        if k not in values:
            del sig[k]
    for k in values:
        if k not in sig:
            sig[k] = 0.0
    sig.animation_data_create()
    old = sig.animation_data.action
    act = bpy.data.actions.new("AudioSignals_run")
    sig.animation_data.action = act
    lin = bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["LINEAR"].value
    for k, arr in values.items():
        n = len(arr)
        co = np.empty(2 * n, np.float32)
        co[0::2] = np.arange(1, n + 1)
        co[1::2] = arr
        fc = act.fcurve_ensure_for_datablock(sig, f'["{k}"]')
        fc.keyframe_points.add(n)
        fc.keyframe_points.foreach_set("co", co)
        fc.keyframe_points.foreach_set("handle_left", co)
        fc.keyframe_points.foreach_set("handle_right", co)
        fc.keyframe_points.foreach_set("interpolation", [lin] * n)
        fc.update()
    if old is not None and old.users == 0:
        bpy.data.actions.remove(old)
    act.name = "AudioSignals"


def wire(scene, ctrl) -> None:
    """(Re)create every driver of the look on the run's signals and the sliders; all must be simple expressions."""
    O = bpy.data.objects
    cam, walls, portals, outer = O[CAM], O["Tunnel_Walls"], O["Tunnel_Portals"], O["Tunnel_Outer"]
    per = float(ctrl["_period_travel"])
    nodes = bpy.data.materials["NeonLine"].node_tree.nodes
    glare = sorted((nd for nd in scene.compositing_node_group.nodes if nd.bl_idname == "CompositorNodeGlare"),
                   key=lambda nd: nd.name)
    lens = "max(lens - kick_zoom*kick, 2)"
    half = MARK_NEAR * cam.data.sensor_width / 2       # half the frame's height at the watermark, times the lens
    specs = [
        (cam, "location", 0, "cam_orbit*_inradius*cos(roll)"),
        (cam, "location", 1, "cam_orbit*_inradius*sin(roll)"),
        (cam, "location", 2, f"-fmod(travel, {per:.8f})"),
        (cam, "rotation_euler", 2, "roll + kick_jolt*kick"),
        (cam.data, "lens", -1, lens),
        (O[MARK], "scale", 0, f"{half:.6f}/{lens}"),             # the watermark keeps its size through the zoom
        (O[MARK], "scale", 1, f"{half:.6f}/{lens}"),
        (bpy.data.materials[MARK].node_tree.nodes["Opacity"].inputs["Fac"], "default_value", -1, "watermark"),
        (portals, "rotation_euler", 2, "portal"),
        (outer, "rotation_euler", 2, "-outer"),
        (glare[0].inputs["Strength"], "default_value", -1, "0.42*bloom*(0.6 + 0.6*energy + 0.8*kick_bloom*kick_light)"),
        (glare[1].inputs["Strength"], "default_value", -1, "0.18*bloom*(0.5 + 0.8*energy + 1.2*kick_bloom*kick_light)"),
        (nodes["LoopTime"].outputs[0], "default_value", -1, "phase"),
        (nodes["AU_Gain"].outputs[0], "default_value", -1, "glow_base + energy_glow*energy + kick_glow*kick_light"),
        (nodes["AU_Hue"].outputs[0], "default_value", -1, "color_shift*bright + 0.04*kick + hue_off"),
        (nodes["AU_Hats"].outputs[0], "default_value", -1, "hats_sparkle*hats"),
        (nodes["AU_Bass"].outputs[0], "default_value", -1, "bass_haze*bass"),
        (nodes["AU_RingPos"].outputs[0], "default_value", -1, "2 + kick_age*kick_ring_speed"),
        (nodes["AU_RingAmp"].outputs[0], "default_value", -1, "kick_flash*kick_last*exp(-kick_age/(kick_ring_decay*60))"),
        (nodes["NearFade"].inputs["From Min"], "default_value", -1, "0.25*near_fade"),
        (nodes["NearFade"].inputs["From Max"], "default_value", -1, "near_fade + 0.001"),
    ]
    specs += [(nodes[f"LK_{k}"].outputs[0], "default_value", -1, k) for k in SHADER]
    for ob in (walls, portals, outer):
        layer = LAYER_KEYS[ob.name]
        specs += [(ob, '["layer_glow"]', -1, f"{layer}_glow"), (ob, '["layer_hue"]', -1, f"{layer}_hue")]
    for i in (0, 1):
        specs += [(walls, "scale", i, "1 + kick_pump*kick + bass_wall*bass"),
                  (portals, "scale", i, "1 - kick_squeeze*kick"),
                  (outer, "scale", i, "1 + bass_swell*bass")]
    sig = O[SIG]
    complex_ = [f"{getattr(o, 'name', o)}.{path}" for o, path, idx, expr in specs
                if not _drive(o, path, idx, expr, sig, ctrl).driver.is_simple_expression]
    if complex_:
        raise RuntimeError(f"drivers that would need Python auto-run: {complex_}")


def _drive(owner, path: str, index: int, expr: str, sig, ctrl):
    try:
        owner.driver_remove(path, index)
    except Exception:  # noqa: BLE001  no driver there yet
        pass
    fc = owner.driver_add(path, index) if index >= 0 else owner.driver_add(path)
    for modifier in list(fc.modifiers):
        fc.modifiers.remove(modifier)
    d = fc.driver
    d.type = "SCRIPTED"
    for v in list(d.variables):
        d.variables.remove(v)
    words = {w for w in "".join(ch if ch.isalnum() or ch == "_" else " " for ch in expr).split() if not w[0].isdigit()}
    for name in sorted(words):
        target = sig if name in sig.keys() else ctrl if name in ctrl.keys() else None
        if target is None:
            continue                       # functions and constants: fmod, max, exp, cos
        v = d.variables.new()
        v.name, v.type = name, "SINGLE_PROP"
        v.targets[0].id_type, v.targets[0].id, v.targets[0].data_path = "OBJECT", target, f'["{name}"]'
    d.expression = expr
    return fc


def configure(scene, width: int, height: int, percent: int, samples: int, frames_dir: Path | None,
              n: int = FRAMES) -> None:
    """Render settings: 60 fps, frames 1-n, 9:16, EEVEE, 8-bit RGB PNG frames for the encoder."""
    r = scene.render
    r.fps, r.fps_base = FPS, 1.0
    scene.frame_start, scene.frame_end = 1, n
    r.resolution_x, r.resolution_y, r.resolution_percentage = width, height, percent
    scene.eevee.taa_render_samples = samples
    r.use_motion_blur = False          # the camera wraps by one wall period: blur would smear that jump
    ims = r.image_settings
    ims.media_type = "IMAGE"
    ims.file_format = "PNG"
    ims.color_mode, ims.color_depth, ims.compression = "RGB", "8", 15
    r.filepath = str(frames_dir / "frame_") if frames_dir else "//frames/frame_"
    r.use_file_extension, r.use_overwrite, r.use_placeholder = True, True, False
    r.use_compositing, r.use_sequencer = True, False


def set_sound(scene, wav: Path | None) -> None:
    """The run's mix as a sound strip at frame 1, so the saved scene plays in sync (the MP4's audio is muxed later)."""
    se = scene.sequence_editor or scene.sequence_editor_create()
    for strip in list(se.strips_all):
        se.strips.remove(strip)
    if wav is not None:
        se.strips.new_sound("mix", str(wav), 1, 1)
        scene.sync_mode = "AUDIO_SYNC"
    for sound in list(bpy.data.sounds):
        if sound.users == 0:
            bpy.data.sounds.remove(sound)


# ---- the template --------------------------------------------------------------------------------------------------

def make_template(path: Path) -> None:
    """From the reference scene: keep the lines look and its sliders (at styles/default.toml's values), drop the
    kaleidoscope, the old audio wiring and the UI script, rebuild the material and the meshes with this look's code,
    add the watermark, wire the drivers to neutral signals and save."""
    scene, ctrl = bpy.context.scene, bpy.data.objects[CTRL]
    for text in list(bpy.data.texts):
        bpy.data.texts.remove(text)
    for name in ("Kaleido_Screen",):
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    if "KaleidoTunnel" in bpy.data.collections:
        bpy.data.collections.remove(bpy.data.collections["KaleidoTunnel"])
    if "Kaleido" in bpy.data.materials:
        bpy.data.materials.remove(bpy.data.materials["Kaleido"])
    for name in TUNNEL:
        bpy.data.objects[name].hide_render = bpy.data.objects[name].hide_viewport = False
    for key in [k for k in ctrl.keys() if k not in SCHEMA["look"]]:
        del ctrl[key]                                                    # music, kaleido and old shape settings
    style = recipe.resolve_style(recipe.load(HERE / "styles" / "default.toml"), SCHEMA)
    for key, spec in SCHEMA["look"].items():
        ctrl[key] = float(style["look"][key])
        ctrl.id_properties_ui(key).update(min=spec["min"], max=spec["max"], soft_min=spec["min"], soft_max=spec["max"],
                                          default=spec["default"], precision=3, description=spec["help"])
    build_material()
    ensure_shape(style["shape"], ctrl, force=True)
    build_watermark(bpy.data.objects[CAM])
    silent = {"frames": FRAMES, "sections": [{"name": "hook", "frame": 0}], "tracks": {}, "stems": {}, "curves": {},
              "mix": {"loud": [0.0] * FRAMES, "bright": [0.0] * FRAMES}}
    bake_run(silent, recipe.load(HERE / "mappings" / "gen.toml"), ctrl)
    wire(scene, ctrl)
    configure(scene, 1080, 1920, 100, 32, None)
    set_sound(scene, None)
    scene.frame_set(1)
    bpy.data.orphans_purge(do_recursive=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True)
    print(f"STEM_TUNNEL_RESULT template saved to {path}", flush=True)


def build_material() -> None:
    """The NeonLine emission material of the reference look (blender/audio-tunnel/neon_audio.py build_material):
    two thin edge lines and a glowing core across every ribbon, coloured by depth, faded with distance, a sparkle
    wave and the light ring. Its constants are Value nodes driven by the sliders (LK_<name>, look.toml), each layer
    adds its own glow and hue (object properties layer_glow, layer_hue), and the portals (pass index 1) fade out
    near the camera plane (NearFade): portals sweeping past the camera were the reference loop's flashes, a 0.13-0.17
    rise in mean luminance each."""
    mat = bpy.data.materials.get("NeonLine") or bpy.data.materials.new("NeonLine")
    nt = mat.node_tree
    if nt.animation_data:
        nt.animation_data_clear()
    N, links = nt.nodes, nt.links
    N.clear()

    def M(op, a, b=None):
        nd = N.new("ShaderNodeMath")
        nd.operation = op
        for socket, v in zip(nd.inputs, (a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                socket.default_value = v
            else:
                links.new(v, socket)
        return nd.outputs[0]

    def value(name, label, default=0.0):
        nd = N.new("ShaderNodeValue")
        nd.name, nd.label = name, label
        nd.outputs[0].default_value = default
        return nd.outputs[0]

    def attribute(name):
        nd = N.new("ShaderNodeAttribute")
        nd.attribute_type, nd.attribute_name = "OBJECT", name
        return nd.outputs["Fac"]

    out, emi = N.new("ShaderNodeOutputMaterial"), N.new("ShaderNodeEmission")
    uvn, infn = N.new("ShaderNodeUVMap"), N.new("ShaderNodeUVMap")
    uvn.uv_map, infn.uv_map = "UVMap", "Info"
    sep, sepi = N.new("ShaderNodeSeparateXYZ"), N.new("ShaderNodeSeparateXYZ")
    links.new(uvn.outputs["UV"], sep.inputs[0])
    links.new(infn.outputs["UV"], sepi.inputs[0])
    camd, objinfo = N.new("ShaderNodeCameraData"), N.new("ShaderNodeObjectInfo")
    t, gain = value("LoopTime", "Colour phase"), value("AU_Gain", "Audio: brightness", 1.0)
    hats, hue_audio = value("AU_Hats", "Audio: sparkle"), value("AU_Hue", "Audio: hue offset")
    ring_pos, ring_amp = value("AU_RingPos", "Audio: ring distance", 1000.0), value("AU_RingAmp", "Audio: ring strength")
    bass = value("AU_Bass", "Audio: haze")
    lk = {k: value(f"LK_{k}", SCHEMA["look"][k]["label"], SCHEMA["look"][k]["default"]) for k in SHADER}
    layer_glow, layer_hue = attribute("layer_glow"), attribute("layer_hue")
    v, depth = sep.outputs["Y"], camd.outputs["View Distance"]

    def line(c, w):
        return M("POWER", M("MAXIMUM", M("SUBTRACT", 1.0, M("DIVIDE", M("ABSOLUTE", M("SUBTRACT", v, c)), w)), 0.0),
                 lk["line_sharp"])

    e1, e2, core = line(0.1, 0.09), line(0.9, 0.09), line(0.5, 0.14)
    lines = M("ADD", M("MULTIPLY", M("ADD", e1, e2), lk["line_edges"]), M("MULTIPLY", core, lk["line_core"]))
    mask = M("ADD", lines, M("MULTIPLY", lk["fill_glow"], M("ADD", 1.0, bass)))
    hue = M("ADD", M("ADD", t, M("MULTIPLY", M("DIVIDE", depth, HUE_D), lk["hue_depth"])),
            M("MULTIPLY", M("MULTIPLY", v, 0.18), lk["hue_across"]))
    hue = M("FRACT", M("ADD", M("ADD", M("ADD", hue, sepi.outputs["X"]), hue_audio), M("ADD", lk["hue_base"], layer_hue)))
    dd = M("DIVIDE", M("SUBTRACT", depth, ring_pos), RING_W)
    ring = M("MULTIPLY", ring_amp, M("EXPONENT", M("MULTIPLY", M("MULTIPLY", dd, dd), -1.0)))
    sat = M("MULTIPLY", M("SUBTRACT", 1.0, M("MULTIPLY", core, 0.55)),
            M("SUBTRACT", 1.0, M("MULTIPLY", M("MINIMUM", ring, 1.0), 0.75)))
    comb = N.new("ShaderNodeCombineColor")
    comb.mode = "HSV"
    links.new(hue, comb.inputs[0])
    links.new(M("MULTIPLY", sat, lk["saturation"]), comb.inputs[1])
    comb.inputs[2].default_value = 1.0
    fade = N.new("ShaderNodeMapRange")
    fade.interpolation_type, fade.clamp = "SMOOTHSTEP", True
    links.new(depth, fade.inputs["Value"])
    links.new(M("MULTIPLY", lk["view_far"], 0.5), fade.inputs["From Min"])
    links.new(lk["view_far"], fade.inputs["From Max"])
    fade.inputs["To Min"].default_value, fade.inputs["To Max"].default_value = 1.0, 0.0
    fo = fade.outputs["Result"]
    wave = M("SINE", M("MULTIPLY", M("SUBTRACT", M("DIVIDE", depth, 12.0), M("MULTIPLY", t, 6.0)), 2 * math.pi))
    spark = M("MULTIPLY", hats, M("POWER", M("MAXIMUM", wave, 0.0), 8.0))
    pulse = M("ADD", M("ADD", M("SUBTRACT", 1.0, lk["wave_amount"]), M("MULTIPLY", wave, lk["wave_amount"])), spark)
    strength = M("MULTIPLY", M("MULTIPLY", M("MULTIPLY", M("MULTIPLY", M("MULTIPLY", mask, EMIT), fo),
                                                       sepi.outputs["Y"]), pulse), gain)
    flash = M("MULTIPLY", M("MULTIPLY", M("MULTIPLY", M("MULTIPLY", lines, ring), RING_GAIN), fo), sepi.outputs["Y"])
    near = N.new("ShaderNodeMapRange")
    near.name = near.label = "NearFade"
    near.interpolation_type, near.clamp = "SMOOTHSTEP", True
    near.inputs["To Min"].default_value, near.inputs["To Max"].default_value = 0.0, 1.0
    links.new(camd.outputs["View Z Depth"], near.inputs["Value"])
    dim = M("MULTIPLY", objinfo.outputs["Object Index"], M("SUBTRACT", 1.0, near.outputs["Result"]))
    strength = M("MULTIPLY", M("MULTIPLY", M("ADD", strength, flash), M("SUBTRACT", 1.0, dim)), layer_glow)
    links.new(comb.outputs[0], emi.inputs["Color"])
    links.new(strength, emi.inputs["Strength"])
    links.new(emi.outputs[0], out.inputs["Surface"])


def build_watermark(cam) -> None:
    """MARK_TEXT in white at the top centre, at the `watermark` slider's opacity: a text object MARK_NEAR in front of
    the camera and parented to it, so it holds still on screen while the view rolls. Its units are half the frame's
    height (wire scales it against the lens, which also keeps it still through the kick's zoom punch)."""
    cu = bpy.data.curves.get(MARK) or bpy.data.curves.new(MARK, "FONT")
    cu.body, cu.align_x, cu.align_y = MARK_TEXT, "CENTER", "CENTER"
    cu.size, cu.space_character, cu.offset_y = 0.035, 1.3, 0.86      # Blender's own sans, letter-spaced, at the top
    ob = bpy.data.objects.get(MARK) or bpy.data.objects.new(MARK, cu)
    if not ob.users_collection:
        cam.users_collection[0].objects.link(ob)
    ob.parent, ob.matrix_parent_inverse = cam, ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
    ob.location, ob.rotation_euler = (0.0, 0.0, -MARK_NEAR), (0.0, 0.0, 0.0)
    ob.hide_select = True
    mat = bpy.data.materials.get(MARK) or bpy.data.materials.new(MARK)
    mat.surface_render_method = "BLENDED"
    nt = mat.node_tree
    nt.nodes.clear()
    out, mix = nt.nodes.new("ShaderNodeOutputMaterial"), nt.nodes.new("ShaderNodeMixShader")
    clear, emi = nt.nodes.new("ShaderNodeBsdfTransparent"), nt.nodes.new("ShaderNodeEmission")
    mix.name = mix.label = "Opacity"
    emi.inputs["Color"].default_value, emi.inputs["Strength"].default_value = (1.0, 1.0, 1.0, 1.0), 1.0
    nt.links.new(clear.outputs[0], mix.inputs[1])
    nt.links.new(emi.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    cu.materials.clear()
    cu.materials.append(mat)


_frames = [FRAMES]                 # the run's frame count, for the progress line


def _progress(scene, *_):
    print(f"STEM_TUNNEL frame {scene.frame_current}/{_frames[0]}", flush=True)


if __name__ == "__main__":
    sys.modules.setdefault("stem_tunnel", sys.modules[__name__])       # tuner.py imports this module, not a copy
    main()
