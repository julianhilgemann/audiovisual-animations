"""Flythrough: a camera that really flies down a winding tunnel of gears, light streaks or crystals, driven by a
run's controls.json (any method, SPEC §16), rendered headless.

The pipeline calls it (`datapipe short <method> --look flythrough [--style warp]`); by hand:

    blender -b blender/flythrough/flythrough.blend --python blender/flythrough/flythrough.py -- \\
        --run work/<method>/<run> --frames-dir work/<method>/<run>/frames \\
        --mapping blender/flythrough/mappings/<method>.toml [--style blender/flythrough/styles/<name>.toml] \\
        [--percent 50] [--samples 8] [--seam]

Build the template from Blender's factory scene (the look has no reference scene; everything is made here):

    blender -b --factory-startup --python blender/flythrough/flythrough.py -- \\
        --make-template blender/flythrough/flythrough.blend

The camera follows the path of worlds.py with drivers (its location and heading are functions of the baked
``travel``), wrapping by one bend period, so it moves through the scene rather than the scene past it. Gears,
portals and crystal slabs are Geometry Nodes instances turned by baked channels; the walls and streaks are still
meshes. Every reaction is a simple-expression driver on the AudioSignals empty (the run's signals, one key per frame)
and the NeonControls empty (the look's sliders, look.toml), so no Python auto-run is needed.
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
sys.path.insert(0, str(HERE))
from datapipe import mapping, recipe  # noqa: E402  numpy and the standard library only, shared with the pipeline
import worlds  # noqa: E402

TAG = "FLYTHROUGH"             # its progress and result lines (render.py reads them)
CTRL, SIG, CAM = "NeonControls", "AudioSignals", "FlyCam"
PROTOS, NODES, LIGHT = "FlyProtos", "FlySpinners", "FlyLight"
FPS = 60
FRAMES = 480
LEVELS = ("kick", "kick_light", "bass", "energy", "hats", "mids", "bright", "twist")
DEG = 4 * math.pi / 360        # the roll and spin unit of the sliders (as in the stem tunnel)
KICK_AREA = 4.0                # frames under one kick's envelope (3-frame wind-up, 9-frame decay): one tick each
WARP_FULL = 4.0                # segments a second that count as full warp (streaks at full length, lens widest)
SCHEMA = recipe.load(HERE / "look.toml")
MOTION = tuple(k for k, spec in SCHEMA["look"].items() if spec.get("motion"))
SHADER = ("hue_base", "hue_depth", "saturation", "streak_tail", "near_fade", "metal_rough", "walls_glow",
          "gears_glow", "portals_glow", "streaks_glow", "shards_glow")       # sliders the materials read directly
HUE_D, RING_W = 30.0, 4.0      # depth for one turn of the colour wheel at hue_depth 1; width of the light ring
LANTERN_W, SIDE_W, RACE_W = 2200.0, 1500.0, 4000.0                      # watts at slider 1
MARK, MARK_TEXT = "Watermark", "hyperadapted"
MARK_NEAR = 0.1


def main() -> None:
    a = parse_args()
    if a.make_template:
        make_template(a.make_template)
        return
    if a.tune:
        raise SystemExit("flythrough: the tuner panel is the stem tunnel's for now; render with --style instead")
    t0 = time.time()
    scene, ctrl = bpy.context.scene, bpy.data.objects[CTRL]
    controls = json.loads((a.run / "controls.json").read_text(encoding="utf-8"))
    n = _frames[0] = controls["frames"]
    cfg = recipe.load(a.mapping)
    style = recipe.resolve_style(recipe.load(a.style) if a.style else {}, SCHEMA)
    built = apply_style(style)
    levels, closure = bake_run(controls, cfg, ctrl)
    wire(scene, ctrl)
    configure(scene, a.width, a.height, a.percent, a.samples, a.frames_dir, n)
    set_sound(scene, a.run / "mix.wav")
    if a.save_blend:
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
                           for k, v in levels.items() if k in LEVELS + ("warp",)}}
    print(f"{TAG}_RESULT " + json.dumps(summary), flush=True)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(prog="flythrough.py")
    p.add_argument("--run", type=Path, help="a work/<method>/<run> folder with controls.json and mix.wav")
    p.add_argument("--frames-dir", type=Path, help="where frame_0001.png, frame_0002.png ... go")
    p.add_argument("--mapping", type=Path, default=HERE / "mappings" / "gen.toml",
                   help="mappings/<method>.toml: which of the run's sources drive the look")
    p.add_argument("--style", type=Path, help="styles/<name>.toml: the world and the sliders (default: look.toml's)")
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.add_argument("--percent", type=int, default=100)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--seam", action="store_true", help="also render frame n + 1, which must match frame 1")
    p.add_argument("--frames", type=lambda s: [int(f) for f in s.split(",")],
                   help="render only these frames (e.g. 1,481) as frame_<n>.png")
    p.add_argument("--save-blend", type=Path, help="save the baked scene here, to open, scrub and play")
    p.add_argument("--no-render", action="store_true")
    p.add_argument("--tune", action="store_true", help="(the stem tunnel's tuner; not for this look yet)")
    p.add_argument("--method", help="the run's method (the pipeline passes it; unused here)")
    p.add_argument("--save-to", type=Path, help="the run's tuning folder (the pipeline passes it; unused here)")
    p.add_argument("--pipeline-python", help="the pipeline's Python (the pipeline passes it; unused here)")
    p.add_argument("--make-template", type=Path, help="build the template from the factory scene, save it here")
    a = p.parse_args(argv)
    if not a.make_template and not a.tune and not (a.run and a.frames_dir):
        p.error("--run and --frames-dir are required to render")
    return a


# ---- modulators -> look signals and motion -------------------------------------------------------------------------

def look_signals(controls: dict, cfg: dict) -> dict[str, np.ndarray]:
    """The look's 0-1 signals from the run's modulators, as the method's mapping wires them (mapping.py)."""
    return mapping.look_signals(controls, cfg, LEVELS)


available_sources = mapping.available_sources


def motion(levels: dict, controls: dict, ctrl, cfg: dict) -> tuple[dict, dict]:
    """Accumulated motion as positions (n + 1 keys), each closed on the loop on the built world's periods unless the
    run says ``close: false``: the flight along the path, the roll, the three gear channels (teeth), the portals'
    turn and the balance wheels' swing phase, and the colour phase. Also ``warp`` (0-1, the flight's speed) and
    ``balance`` (the balance wheels' angle)."""
    n = controls["frames"]
    c = lambda k: float(ctrl[k])  # noqa: E731
    m = cfg.get("motion", {})
    seg = float(ctrl["_segment"])
    riser = np.asarray(controls["curves"].get(m.get("speed_curve", "riser"), np.zeros(n)))
    bpm = float(controls.get("bpm") or 120.0)
    rates = {
        "travel": (seg / FPS * c("speed") * (c("speed_idle") + c("speed_energy") * levels["energy"]
                   + c("speed_kick") * levels["kick"] + float(m.get("speed_riser", 0)) * riser), "_period_travel"),
        "roll": (DEG * (c("roll_idle") + c("roll_bass") * levels["bass"]
                        + float(m.get("roll_twist", 0)) * levels["twist"]), "_period_roll"),
        "tick": (c("tick_idle") / FPS + c("tick_kick") * levels["kick"] / KICK_AREA, "_period_teeth"),
        "drive": ((c("tick_idle") + c("drive_bass") * levels["bass"]) / FPS, "_period_teeth"),
        "whirr": ((c("tick_idle") + c("whirr_hats") * levels["hats"]) / FPS, "_period_teeth"),
        "portal": (DEG * (c("portal_idle") + c("portal_spin_mids") * levels["mids"]), "_period_portal"),
        "swing": (np.full(n, math.pi * bpm / 60 / FPS), "_period_swing"),     # one swing there and back: two beats
        "phase": ((c("color_idle") + c("color_energy") * levels["energy"]) / 360, None),
    }
    tracks, closure = {}, {}
    close = controls.get("close", True)
    for name, (rate, period) in rates.items():
        rate = np.broadcast_to(rate, (n,))
        period = float(ctrl[period]) if period else 1.0
        tracks[name], closure[name] = mapping.close_loop(rate, period) if close else mapping.integrate(rate)
    speed = np.diff(tracks["travel"]) * FPS / seg                              # segments a second, as flown
    warp = mapping.follow(np.clip(speed / WARP_FULL, 0.0, 1.0), 6, 40, controls.get("wrap", True))  # no strobe
    energy = levels["energy"]
    tracks["warp"] = np.append(warp, warp[0])
    tracks["balance"] = (math.radians(c("swing")) * (0.25 + 0.75 * np.append(energy, energy[0]))
                         * np.sin(tracks.pop("swing")))
    return tracks, closure


def loop_keys(levels: dict) -> dict:
    """n + 1 keys per level signal: frame n + 1 repeats frame 1, so the loop's restart is a real keyframe."""
    return {k: np.append(v, v[0]) for k, v in levels.items()}


def bake_run(controls: dict, cfg: dict, ctrl) -> tuple[dict, dict]:
    """Signals and motion from the run and the mapping, keyed on AudioSignals; returns the signals and the closure."""
    levels = look_signals(controls, cfg)
    tracks, closure = motion(levels, controls, ctrl, cfg)
    bake(loop_keys(levels) | tracks)
    levels["warp"] = tracks["warp"][:-1]
    return levels, closure


def bake(values: dict) -> None:
    """One linear key per frame on the AudioSignals empty, replacing whatever was there."""
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


def baked_digest() -> str:
    """A fingerprint of everything baked: every key on AudioSignals, and the built world."""
    from bpy_extras import anim_utils

    h = hashlib.sha256(str(bpy.data.objects[CTRL].get("_built_shape")).encode())
    ad = bpy.data.objects[SIG].animation_data
    bag = anim_utils.animdata_get_channelbag_for_assigned_slot(ad) if ad and ad.action else None
    for fc in sorted(bag.fcurves if bag else [], key=lambda fc: fc.data_path):
        co = np.empty(2 * len(fc.keyframe_points), np.float32)
        fc.keyframe_points.foreach_get("co", co)
        h.update(fc.data_path.encode() + co.tobytes())
    return h.hexdigest()[:16]


# ---- the style: sliders and world ----------------------------------------------------------------------------------

def apply_style(style: dict) -> dict | None:
    """Set the sliders from a resolved style and build its world if the scene has another; returns what a rebuild
    built (None when the world was already there)."""
    ctrl = bpy.data.objects[CTRL]
    for key, value in style["look"].items():
        ctrl[key] = float(value)
    return ensure_shape(style["shape"], ctrl)


def ensure_shape(shape: dict, ctrl, force: bool = False) -> dict | None:
    """Rebuild the world (worlds.py) unless it already has this shape; record its periods and path on NeonControls."""
    signature = json.dumps(shape, sort_keys=True)
    if not force and ctrl.get("_built_shape") == signature:
        return None
    t = time.time()
    geo = worlds.geometry(shape)
    build_world(geo)
    for key, value in geo["periods"].items():
        ctrl[f"_period_{key}"] = float(value)
    for key, value in geo["path"].items():
        ctrl[f"_path_{key}"] = float(value)
    ctrl["_segment"], ctrl["_built_shape"] = float(shape["segment"]), signature
    bpy.data.node_groups[LIGHT].nodes["Fold"].outputs[0].default_value = float(geo["fold"])
    verts = sum(len(geo[k]["co"]) for k in ("walls", "streaks")) + len(geo["spinners"]["co"])
    return {"verts": verts, "instances": len(geo["spinners"]["co"]), "build_s": round(time.time() - t, 2)}


def build_world(geo: dict) -> None:
    """The walls and streaks meshes, the prototypes (one object each in FlyProtos, named so they sort in their
    index order, which Collection Info keeps) and the spinners' points with their attributes."""
    mats = {name: bpy.data.materials[name] for name in worlds.MATERIALS}
    scene_coll = bpy.data.objects[CTRL].users_collection[0]
    protos = bpy.data.collections[PROTOS]
    for ob in list(protos.objects):
        me = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)
    for i, (name, arrays) in enumerate(geo["protos"]):
        me = worlds.to_mesh(f"P{i:02d}_{name}", arrays, mats)
        protos.objects.link(bpy.data.objects.new(me.name, me))
    sp = geo["spinners"]
    attributes = {"proto": ("INT", sp["proto"]), "rot": ("QUATERNION", sp["rot"]), "phase": ("FLOAT", sp["phase"]),
                  "wa": ("FLOAT_VECTOR", sp["wa"]), "wb": ("FLOAT_VECTOR", sp["wb"])}
    meshes = {"Fly_Walls": worlds.to_mesh("Fly_Walls", geo["walls"], mats),
              "Fly_Streaks": worlds.to_mesh("Fly_Streaks", geo["streaks"], mats),
              "Fly_Spinners": worlds.to_mesh("Fly_Spinners", {"co": sp["co"]}, mats, attributes)}
    for name, me in meshes.items():
        ob = bpy.data.objects.get(name)
        if ob is None:
            ob = bpy.data.objects.new(name, me)
            scene_coll.objects.link(ob)
        else:
            old, ob.data = ob.data, me
            if old.users == 0:
                bpy.data.meshes.remove(old)
        me.name = name
    spinners = bpy.data.objects["Fly_Spinners"]
    if NODES not in spinners.modifiers:
        spinners.modifiers.new(NODES, "NODES").node_group = bpy.data.node_groups[NODES]


def shape_info(ctrl, built: dict | None) -> dict:
    out = {k[len("_period_"):]: round(float(ctrl[k]), 6) for k in ctrl.keys() if k.startswith("_period_")}
    if built:
        out.update(rebuilt=True, **built)
    return out


# ---- drivers -------------------------------------------------------------------------------------------------------

def wire(scene, ctrl) -> None:
    """(Re)create every driver of the look on the run's signals and the sliders; all must be simple expressions.
    The path's constants come from the built world, so this runs after every rebuild."""
    O = bpy.data.objects
    cam = O[CAM]
    p = {"A": float(ctrl["_path_A"]), "Q": float(ctrl["_path_Q"]), "w": float(ctrl["_path_w"])}
    seg = float(ctrl["_segment"])
    here = f"fmod(travel, {p['Q']:.9g})"
    flown = worlds.path_expressions(p, here)
    race = worlds.path_expressions(p, f"({here} + 1.5 + kick_age*kick_ring_speed*{seg / FPS:.9g})")
    lens = "max(lens - kick_zoom*kick - warp_fov*warp, 4)"
    half = MARK_NEAR * cam.data.sensor_width / 2
    g = bpy.data.node_groups[LIGHT].nodes
    glare = sorted((nd for nd in scene.compositing_node_group.nodes if nd.bl_idname == "CompositorNodeGlare"),
                   key=lambda nd: nd.name)
    gears_in, portals_in = (f'modifiers["{NODES}"].properties.inputs.{_socket_id(NODES, name)}.value'
                            for name in ("Gears", "Portals"))
    specs = [
        (cam, "location", 0, flown["x"]), (cam, "location", 1, flown["y"]), (cam, "location", 2, flown["z"]),
        (cam, "rotation_euler", 0, flown["pitch"]), (cam, "rotation_euler", 1, flown["yaw"]),
        (cam, "rotation_euler", 2, f"roll + kick_jolt*kick + bank*sin({p['w']:.9g}*{here})"),
        (cam.data, "lens", -1, lens), (cam.data, "clip_end", -1, "1.05*view_far + 5"),
        (O[MARK], "scale", 0, f"{half:.6f}/{lens}"), (O[MARK], "scale", 1, f"{half:.6f}/{lens}"),
        (bpy.data.materials[MARK].node_tree.nodes["Opacity"].inputs["Fac"], "default_value", -1, "watermark"),
        (O["RaceLight"], "location", 0, race["x"]), (O["RaceLight"], "location", 1, race["y"]),
        (O["RaceLight"], "location", 2, race["z"]),
        (O["RaceLight"].data, "energy", -1, f"{RACE_W}*kick_flash*kick_last*exp(-kick_age/(kick_ring_decay*60))"),
        (O["Lantern"].data, "energy", -1,
         f"{LANTERN_W}*lantern*(0.7 + lantern_energy*energy + 0.25*kick_glow*kick_light)"),
        (O["Lantern"].data, "color", 1, "1 - 0.28*lantern_warmth"),
        (O["Lantern"].data, "color", 2, "1 - 0.6*lantern_warmth"),
        (O["SideLeft"].data, "energy", -1, f"{SIDE_W}*side_lights*(0.6 + 0.6*energy + 0.3*kick_glow*kick_light)"),
        (O["SideRight"].data, "energy", -1, f"{SIDE_W}*side_lights*(0.6 + 0.6*bass + 0.3*kick_glow*kick_light)"),
        (O["Fly_Spinners"], gears_in, 0, "tick"), (O["Fly_Spinners"], gears_in, 1, "drive"),
        (O["Fly_Spinners"], gears_in, 2, "whirr"),
        (O["Fly_Spinners"], portals_in, 0, "portal"), (O["Fly_Spinners"], portals_in, 1, "balance"),
        (glare[0].inputs["Strength"], "default_value", -1, "0.35*bloom*(0.6 + 0.6*energy + 0.8*kick_bloom*kick_light)"),
        (glare[1].inputs["Strength"], "default_value", -1, "0.15*bloom*(0.5 + 0.8*energy + 1.2*kick_bloom*kick_light)"),
        (scene.world, "mist_settings.start", -1, "0.4*view_far"),
        (scene.world, "mist_settings.depth", -1, "0.6*view_far"),
        (g["Phase"].outputs[0], "default_value", -1, "phase"),
        (g["AU_Gain"].outputs[0], "default_value", -1, "glow_base + energy_glow*energy + kick_glow*kick_light"),
        (g["AU_Hue"].outputs[0], "default_value", -1, "color_shift*bright + 0.04*kick + hue_off"),
        (g["AU_Hats"].outputs[0], "default_value", -1, "hats_sparkle*hats"),
        (g["AU_Bass"].outputs[0], "default_value", -1, "bass_haze*bass"),
        (g["AU_Warp"].outputs[0], "default_value", -1, "warp"),
        (g["AU_RingPos"].outputs[0], "default_value", -1, f"1.5 + kick_age*kick_ring_speed*{seg / FPS:.9g}"),
        (g["AU_RingAmp"].outputs[0], "default_value", -1, "kick_flash*kick_last*exp(-kick_age/(kick_ring_decay*60))"),
    ]
    specs += [(g[f"LK_{k}"].outputs[0], "default_value", -1, k) for k in SHADER]
    sig = O[SIG]
    complex_ = [f"{getattr(o, 'name', o)}.{path}" for o, path, idx, expr in specs
                if not _drive(o, path, idx, expr, sig, ctrl).driver.is_simple_expression]
    if complex_:
        raise RuntimeError(f"drivers that would need Python auto-run: {complex_}")


def _socket_id(group: str, name: str) -> str:
    return next(i.identifier for i in bpy.data.node_groups[group].interface.items_tree
                if i.item_type == "SOCKET" and i.in_out == "INPUT" and i.name == name)


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
            continue                       # functions and constants: fmod, max, exp, sin, atan, sqrt
        v = d.variables.new()
        v.name, v.type = name, "SINGLE_PROP"
        v.targets[0].id_type, v.targets[0].id, v.targets[0].data_path = "OBJECT", target, f'["{name}"]'
    d.expression = expr
    return fc


# ---- scene ---------------------------------------------------------------------------------------------------------

def configure(scene, width: int, height: int, percent: int, samples: int, frames_dir: Path | None,
              n: int = FRAMES) -> None:
    """Render settings: 60 fps, frames 1-n, 9:16, EEVEE (no shadows: they fall behind what casts them, seen from
    lights that fly with the camera, and cost half the frame), 8-bit RGB PNG frames for the encoder."""
    r = scene.render
    r.engine = "BLENDER_EEVEE"
    r.fps, r.fps_base = FPS, 1.0
    scene.frame_start, scene.frame_end = 1, n
    r.resolution_x, r.resolution_y, r.resolution_percentage = width, height, percent
    scene.eevee.taa_render_samples = samples
    scene.eevee.use_shadows, scene.eevee.use_raytracing = False, False
    r.use_motion_blur = False          # the camera wraps by one bend period: blur would smear that jump
    scene.view_settings.view_transform, scene.view_settings.look = "AgX", "AgX - Punchy"
    bpy.context.view_layer.use_pass_mist = True
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
    """From the factory scene: the camera, the two empties with the sliders, the lights, the materials, the
    spinners' node group, the compositor, the watermark and the world of styles/clockwork.toml, wired to neutral
    signals."""
    scene = bpy.context.scene
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights, bpy.data.node_groups):
        for item in list(block):
            block.remove(item)
    coll = scene.collection
    cam = bpy.data.objects.new(CAM, bpy.data.cameras.new(CAM))
    cam.rotation_mode = "ZXY"                                  # roll about the view, then pitch, then yaw
    cam.data.sensor_width, cam.data.sensor_fit = 36.0, "AUTO"
    cam.data.clip_start, cam.data.clip_end = 0.05, 400.0
    coll.objects.link(cam)
    scene.camera = cam
    ctrl, sig = bpy.data.objects.new(CTRL, None), bpy.data.objects.new(SIG, None)
    for ob in (ctrl, sig):
        coll.objects.link(ob)
    style = recipe.resolve_style(recipe.load(HERE / "styles" / "clockwork.toml"), SCHEMA)
    for key, spec in SCHEMA["look"].items():
        ctrl[key] = float(style["look"][key])
        ctrl.id_properties_ui(key).update(min=spec["min"], max=spec["max"], soft_min=spec["min"], soft_max=spec["max"],
                                          default=spec["default"], precision=3, description=spec["help"])
    build_lights(cam)
    build_materials()
    protos = bpy.data.collections.new(PROTOS)                  # not in the scene: only the node group instances it
    protos.use_fake_user = True
    build_spinner_nodes(protos)
    build_compositor(scene)
    build_world_shader(scene)
    build_watermark(cam)
    ensure_shape(style["shape"], ctrl, force=True)
    silent = {"frames": FRAMES, "sections": [{"name": "hook", "frame": 0}], "tracks": {}, "stems": {}, "curves": {},
              "mix": {"loud": [0.0] * FRAMES, "bright": [0.0] * FRAMES}}
    bake_run(silent, recipe.load(HERE / "mappings" / "gen.toml"), ctrl)
    wire(scene, ctrl)
    configure(scene, 1080, 1920, 100, 32, None)
    set_sound(scene, None)
    scene.frame_set(1)
    bpy.data.orphans_purge(do_recursive=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True)
    print(f"{TAG}_RESULT template saved to {path}", flush=True)


def build_lights(cam) -> None:
    """The lantern the camera carries (it casts the gears' shadows), two coloured side lights flying with it, and
    the racing light each hit of the ring's track launches down the path."""
    def light(name, colour, radius, shadow, parent=None, at=(0.0, 0.0, 0.0)):
        data = bpy.data.lights.new(name, "POINT")
        data.color, data.shadow_soft_size, data.use_shadow = colour, radius, shadow
        ob = bpy.data.objects.new(name, data)
        cam.users_collection[0].objects.link(ob)
        if parent:
            ob.parent = parent
        ob.location = at
        return ob

    light("Lantern", (1.0, 0.9, 0.75), 0.6, True, cam, (0.0, 1.2, 1.5))
    light("SideLeft", (1.0, 0.55, 0.2), 1.0, False, cam, (-5.0, 1.0, -7.0))
    light("SideRight", (0.25, 0.55, 1.0), 1.0, False, cam, (5.0, -1.0, -7.0))
    light("RaceLight", (1.0, 0.85, 0.6), 0.4, False)


class _Nodes:
    """A little builder for shader node trees (materials and the FlyLight group)."""

    def __init__(self, tree):
        self.t, self.N, self.L = tree, tree.nodes, tree.links

    def node(self, kind, **inputs):
        nd = self.N.new(kind)
        for key, v in inputs.items():
            self.put(nd.inputs[key], v)
        return nd

    def put(self, socket, v):
        if isinstance(v, (int, float)) or (isinstance(v, tuple) and not hasattr(v, "node")):
            socket.default_value = v
        elif v is not None:
            self.L.new(v, socket)

    def m(self, op, a, b=None, c=None):
        nd = self.N.new("ShaderNodeMath")
        nd.operation = op
        for socket, v in zip(nd.inputs, (a, b, c)):
            self.put(socket, v)
        return nd.outputs[0]

    def value(self, name, default=0.0):
        nd = self.N.new("ShaderNodeValue")
        nd.name = nd.label = name
        nd.outputs[0].default_value = default
        return nd.outputs[0]


def build_light_group() -> None:
    """FlyLight: the shared shader values, driven once: the glowing colour (hue from the colour phase, depth and the
    music, turned by an input), the brightness gain, the racing light's ring along the view, the near fade, the warp,
    the built world's fold (set by ``ensure_shape``) and the sliders the materials read."""
    ng = bpy.data.node_groups.new(LIGHT, "ShaderNodeTree")
    ng.interface.new_socket("Hue", in_out="INPUT", socket_type="NodeSocketFloat")
    outputs = ["Color", "Gain", "Ring", "Near", "Warp", "Hats", "Bass", "Fold"] + [f"LK_{k}" for k in SHADER]
    for name in outputs:
        ng.interface.new_socket(name, in_out="OUTPUT", socket_type="NodeSocketColor" if name == "Color"
                                else "NodeSocketFloat")
    b = _Nodes(ng)
    gi, go = b.node("NodeGroupInput"), b.node("NodeGroupOutput")
    vals = {k: b.value(k, d) for k, d in (("Phase", 0.0), ("AU_Gain", 1.0), ("AU_Hue", 0.0), ("AU_Hats", 0.0),
                                           ("AU_Bass", 0.0), ("AU_Warp", 0.0), ("AU_RingPos", 1000.0),
                                           ("AU_RingAmp", 0.0), ("Fold", 1.0))}
    lk = {k: b.value(f"LK_{k}", SCHEMA["look"][k]["default"]) for k in SHADER}
    camd = b.node("ShaderNodeCameraData")
    depth = camd.outputs["View Distance"]
    hue = b.m("ADD", b.m("ADD", vals["Phase"], b.m("MULTIPLY", b.m("DIVIDE", depth, HUE_D), lk["hue_depth"])),
              b.m("ADD", b.m("ADD", vals["AU_Hue"], lk["hue_base"]), gi.outputs["Hue"]))
    hsv = b.node("ShaderNodeCombineColor")
    hsv.mode = "HSV"
    b.put(hsv.inputs[0], b.m("FRACT", hue))
    b.put(hsv.inputs[1], lk["saturation"])
    hsv.inputs[2].default_value = 1.0
    dd = b.m("DIVIDE", b.m("SUBTRACT", depth, vals["AU_RingPos"]), RING_W)
    ring = b.m("MULTIPLY", vals["AU_RingAmp"], b.m("EXPONENT", b.m("MULTIPLY", b.m("MULTIPLY", dd, dd), -1.0)))
    near = b.node("ShaderNodeMapRange", Value=camd.outputs["View Z Depth"],
                  **{"From Min": b.m("MULTIPLY", lk["near_fade"], 0.25), "From Max": b.m("ADD", lk["near_fade"], 0.001),
                     "To Min": 0.0, "To Max": 1.0})
    near.interpolation_type, near.clamp = "SMOOTHSTEP", True
    for name, socket in (("Color", hsv.outputs[0]), ("Gain", vals["AU_Gain"]), ("Ring", ring),
                         ("Near", near.outputs["Result"]), ("Warp", vals["AU_Warp"]), ("Hats", vals["AU_Hats"]),
                         ("Bass", vals["AU_Bass"]), ("Fold", vals["Fold"])):
        b.put(go.inputs[name], socket)
    for k in SHADER:
        b.put(go.inputs[f"LK_{k}"], lk[k])


def build_materials() -> None:
    """The look's materials: lit metals (brass, steel, blued steel, the plates with their Geneva stripes, enamel)
    and glowing ones (ruby, seams, lume, light lines, crystal, streaks), all reading FlyLight."""
    build_light_group()
    for name in worlds.MATERIALS:
        mat = bpy.data.materials.new(name)
        mat.use_fake_user = True                                     # a style may use any of them, the template not
        b = _Nodes(mat.node_tree)
        b.N.clear()
        out = b.node("ShaderNodeOutputMaterial")
        fl = b.node("ShaderNodeGroup")
        fl.node_tree = bpy.data.node_groups[LIGHT]
        rough = fl.outputs["LK_metal_rough"]
        gain = fl.outputs["Gain"]
        if name in ("Brass", "Steel", "Blued", "Plate", "Enamel"):
            colour, metal, r = {"Brass": ((0.86, 0.6, 0.28, 1), 1.0, 1.0), "Steel": ((0.6, 0.62, 0.66, 1), 1.0, 0.6),
                                "Blued": ((0.08, 0.18, 0.8, 1), 1.0, 0.8), "Plate": ((0.42, 0.44, 0.47, 1), 1.0, 1.6),
                                "Enamel": ((0.01, 0.015, 0.04, 1), 0.0, 0.25)}[name]
            bsdf = b.node("ShaderNodeBsdfPrincipled", **{"Base Color": colour, "Metallic": metal})
            roughness = b.m("MULTIPLY", rough, r)
            if name == "Plate":                                      # Geneva stripes: bands at 30 degrees, brushed
                uv = b.node("ShaderNodeUVMap")
                uv.uv_map = "UVMap"
                sep = b.node("ShaderNodeSeparateXYZ")
                b.put(sep.inputs[0], uv.outputs["UV"])
                k = b.m("ADD", b.m("MULTIPLY", sep.outputs["X"], 0.5), b.m("MULTIPLY", sep.outputs["Y"], 0.866))
                stripe = b.m("MULTIPLY", b.m("ADD", b.m("SINE", b.m("MULTIPLY", k, 2 * math.pi / 1.4)), 1.0), 0.5)
                roughness = b.m("MULTIPLY", roughness, b.m("ADD", 0.45, b.m("MULTIPLY", stripe, 0.9)))
            b.put(bsdf.inputs["Roughness"], b.m("MINIMUM", roughness, 1.0))
            b.put(out.inputs["Surface"], bsdf.outputs[0])
            continue
        emi = b.node("ShaderNodeEmission")
        colour = fl.outputs["Color"]
        if name == "Ruby":
            b.put(emi.inputs["Color"], (1.0, 0.03, 0.06, 1.0))
            strength = b.m("MULTIPLY", b.m("MULTIPLY", gain, fl.outputs["LK_gears_glow"]), 1.6)
        elif name == "Seam":
            strength = b.m("MULTIPLY", b.m("MULTIPLY", b.m("MULTIPLY", gain, fl.outputs["LK_walls_glow"]),
                                           b.m("ADD", 1.0, fl.outputs["Bass"])), 4.0)
            strength = b.m("ADD", strength, b.m("MULTIPLY", fl.outputs["Ring"], 12.0))
        elif name == "Lume":
            mix = b.node("ShaderNodeMix", Factor=0.25)
            mix.data_type = "RGBA"
            b.put(mix.inputs[6], (0.85, 1.0, 0.8, 1.0))
            b.put(mix.inputs[7], colour)
            colour = mix.outputs[2]
            strength = b.m("MULTIPLY", b.m("MULTIPLY", gain, fl.outputs["LK_portals_glow"]),
                           b.m("ADD", 2.0, b.m("MULTIPLY", fl.outputs["Bass"], 1.5)))
            strength = b.m("MULTIPLY", b.m("ADD", strength, b.m("MULTIPLY", fl.outputs["Ring"], 8.0)),
                           fl.outputs["Near"])
        elif name in ("Neon", "Gate"):
            uv = b.node("ShaderNodeUVMap")
            uv.uv_map = "UVMap"
            sep = b.node("ShaderNodeSeparateXYZ")
            b.put(sep.inputs[0], uv.outputs["UV"])
            line = b.m("POWER", b.m("MAXIMUM", b.m("SUBTRACT", 1.0, b.m("ABSOLUTE", b.m("MULTIPLY", b.m(
                "SUBTRACT", sep.outputs["Y"], 0.5), 2.0))), 0.0), 1.5)
            layer = fl.outputs["LK_walls_glow" if name == "Neon" else "LK_portals_glow"]
            strength = b.m("MULTIPLY", b.m("MULTIPLY", b.m("MULTIPLY", gain, layer), line), 5.0)
            strength = b.m("ADD", strength, b.m("MULTIPLY", b.m("MULTIPLY", fl.outputs["Ring"], line), 15.0))
            if name == "Gate":
                strength = b.m("MULTIPLY", strength, fl.outputs["Near"])
        elif name == "Crystal":
            uv = b.node("ShaderNodeUVMap")
            uv.uv_map = "UVMap"
            sep = b.node("ShaderNodeSeparateXYZ")
            b.put(sep.inputs[0], uv.outputs["UV"])
            u, v = sep.outputs["X"], sep.outputs["Y"]
            edge = b.m("MINIMUM", b.m("MINIMUM", u, v), b.m("SUBTRACT", b.m("SUBTRACT", 1.0, u), v))
            glow = b.m("ADD", 0.035, b.m("MULTIPLY", b.m("EXPONENT", b.m("MULTIPLY", edge, -45.0)), 1.4))
            tex = b.node("ShaderNodeTexCoord")
            sxyz = b.node("ShaderNodeSeparateXYZ")
            b.put(sxyz.inputs[0], tex.outputs["Object"])
            angle = b.m("DIVIDE", b.m("ARCTAN2", sxyz.outputs["Y"], sxyz.outputs["X"]), 2 * math.pi)
            fold = b.node("ShaderNodeGroup")                         # a second FlyLight: one can't feed itself
            fold.node_tree = bpy.data.node_groups[LIGHT]
            wedge = b.m("FRACT", b.m("MULTIPLY", angle, fold.outputs["Fold"]))       # colours repeat every wedge,
            mirrored = b.m("SUBTRACT", 1.0, b.m("ABSOLUTE", b.m("SUBTRACT", b.m("MULTIPLY", wedge, 2.0), 1.0)))
            b.put(fl.inputs["Hue"], b.m("MULTIPLY", mirrored, 0.45))                 # mirrored like the shapes
            wave = b.m("SINE", b.m("MULTIPLY", b.m("ADD", sxyz.outputs["Z"], b.m("MULTIPLY", mirrored, 7.0)), 3.0))
            sparkle = b.m("ADD", 1.0, b.m("MULTIPLY", fl.outputs["Hats"], b.m("POWER", b.m("MAXIMUM", wave, 0.0), 6.0)))
            strength = b.m("MULTIPLY", b.m("MULTIPLY", b.m("MULTIPLY", gain, fl.outputs["LK_shards_glow"]), glow), 2.2)
            strength = b.m("MULTIPLY", b.m("ADD", b.m("MULTIPLY", strength, sparkle),
                                           b.m("MULTIPLY", fl.outputs["Ring"], b.m("MULTIPLY", glow, 6.0))),
                           fl.outputs["Near"])
        elif name == "Streak":
            uv = b.node("ShaderNodeUVMap")
            uv.uv_map = "UVMap"
            sep = b.node("ShaderNodeSeparateXYZ")
            b.put(sep.inputs[0], uv.outputs["UV"])
            u = sep.outputs["X"]
            b.put(fl.inputs["Hue"], b.m("MULTIPLY", sep.outputs["Y"], 0.35))
            frac = b.m("ADD", 0.02, b.m("MULTIPLY", fl.outputs["Warp"], fl.outputs["LK_streak_tail"]))
            tail = b.m("POWER", b.m("MAXIMUM", b.m("SUBTRACT", 1.0, b.m("DIVIDE", u, frac)), 0.0), 1.5)
            mix = b.node("ShaderNodeMix", Factor=0.3)
            mix.data_type = "RGBA"
            b.put(mix.inputs[6], colour)
            b.put(mix.inputs[7], (1.0, 1.0, 1.0, 1.0))
            colour = mix.outputs[2]
            flicker = b.m("ADD", 1.0, b.m("MULTIPLY", fl.outputs["Hats"],
                                          b.m("FRACT", b.m("MULTIPLY", sep.outputs["Y"], 7.13))))
            strength = b.m("MULTIPLY", b.m("MULTIPLY", b.m("MULTIPLY", gain, fl.outputs["LK_streaks_glow"]), tail),
                           b.m("MULTIPLY", flicker, 2.5))
        if name != "Ruby":
            b.put(emi.inputs["Color"], colour)
        b.put(emi.inputs["Strength"], strength)
        b.put(out.inputs["Surface"], emi.outputs[0])


def build_spinner_nodes(protos) -> None:
    """FlySpinners: instance the prototype each point names (attribute ``proto``), turned to its frame (``rot``),
    then about its own axle by phase + wa . Gears + wb . Portals (the baked channels, driven onto the modifier)."""
    ng = bpy.data.node_groups.new(NODES, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Gears", in_out="INPUT", socket_type="NodeSocketVector")
    ng.interface.new_socket("Portals", in_out="INPUT", socket_type="NodeSocketVector")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")

    def attr(name, kind):
        nd = N.new("GeometryNodeInputNamedAttribute")
        nd.data_type = kind
        nd.inputs["Name"].default_value = name
        return nd.outputs["Attribute"]

    info = N.new("GeometryNodeCollectionInfo")
    info.inputs["Collection"].default_value = protos
    info.inputs["Separate Children"].default_value = True
    info.inputs["Reset Children"].default_value = True
    put = N.new("GeometryNodeInstanceOnPoints")
    put.inputs["Pick Instance"].default_value = True
    L.new(gi.outputs["Geometry"], put.inputs["Points"])
    L.new(info.outputs["Instances"], put.inputs["Instance"])
    L.new(attr("proto", "INT"), put.inputs["Instance Index"])
    L.new(attr("rot", "QUATERNION"), put.inputs["Rotation"])
    angle = attr("phase", "FLOAT")
    for weights, channels in (("wa", "Gears"), ("wb", "Portals")):
        dot = N.new("ShaderNodeVectorMath")
        dot.operation = "DOT_PRODUCT"
        L.new(attr(weights, "FLOAT_VECTOR"), dot.inputs[0])
        L.new(gi.outputs[channels], dot.inputs[1])
        add = N.new("ShaderNodeMath")
        add.operation = "ADD"
        L.new(angle, add.inputs[0])
        L.new(dot.outputs["Value"], add.inputs[1])
        angle = add.outputs[0]
    xyz = N.new("ShaderNodeCombineXYZ")
    L.new(angle, xyz.inputs["Z"])
    euler = N.new("FunctionNodeEulerToRotation")
    L.new(xyz.outputs[0], euler.inputs["Euler"])
    turn = N.new("GeometryNodeRotateInstances")
    turn.inputs["Local Space"].default_value = True
    L.new(put.outputs["Instances"], turn.inputs["Instances"])
    L.new(euler.outputs["Rotation"], turn.inputs["Rotation"])
    L.new(turn.outputs["Instances"], go.inputs["Geometry"])


def build_compositor(scene) -> None:
    """Mist darkens the far end into the dark (before the glow, so it doesn't bloom), then two blooms."""
    ng = bpy.data.node_groups.new("FlyCompositor", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    scene.compositing_node_group = ng
    bpy.context.view_layer.use_pass_mist = True
    N, L = ng.nodes, ng.links
    rl, out = N.new("CompositorNodeRLayers"), N.new("NodeGroupOutput")
    fade = N.new("ShaderNodeMix")
    fade.data_type = "RGBA"
    L.new(rl.outputs["Mist"], fade.inputs["Factor"])
    L.new(rl.outputs["Image"], fade.inputs[6])
    fade.inputs[7].default_value = (0.0, 0.0, 0.0, 1.0)
    last = fade.outputs[2]
    for name, threshold, size in (("Glare", 1.0, 0.42), ("Glare.001", 1.5, 0.8)):
        g = N.new("CompositorNodeGlare")
        g.name = name
        g.inputs["Type"].default_value, g.inputs["Quality"].default_value = "Bloom", "High"
        g.inputs["Threshold"].default_value, g.inputs["Size"].default_value = threshold, size
        L.new(last, g.inputs["Image"])
        last = g.outputs["Image"]
    L.new(last, out.inputs["Image"])


def build_world_shader(scene) -> None:
    """A near-black world, faintly blue, for the metals to reflect; the mist that fades the tunnel's far end."""
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value, bg.inputs["Strength"].default_value = (0.006, 0.008, 0.014, 1.0), 1.0
    world.mist_settings.falloff = "QUADRATIC"


def build_watermark(cam) -> None:
    """MARK_TEXT in white at the top centre, at the `watermark` slider's opacity, held still on screen (as in the
    stem tunnel: a text object just in front of the camera, parented to it, scaled against the lens)."""
    cu = bpy.data.curves.get(MARK) or bpy.data.curves.new(MARK, "FONT")
    cu.body, cu.align_x, cu.align_y = MARK_TEXT, "CENTER", "CENTER"
    cu.size, cu.space_character, cu.offset_y = 0.035, 1.3, 0.86
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


_frames = [FRAMES]


def _progress(scene, *_):
    print(f"{TAG} frame {scene.frame_current}/{_frames[0]}", flush=True)


if __name__ == "__main__":
    sys.modules.setdefault("flythrough", sys.modules[__name__])
    main()
