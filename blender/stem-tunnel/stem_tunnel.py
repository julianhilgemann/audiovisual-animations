"""Stem tunnel: the neon lines tunnel, driven by a generated run's stems and score, rendered headless.

The pipeline calls it (`datapipe short`); by hand:

    blender -b blender/stem-tunnel/stem_tunnel.blend --python blender/stem-tunnel/stem_tunnel.py -- \\
        --run work/gen/<run> --frames-dir work/gen/<run>/frames [--percent 50] [--samples 8] [--seam]

Rebuild the template from the reference scene, e.g. after re-tuning the look in blender/audio-tunnel:

    blender -b blender/audio-tunnel/neon_tunnel_audio.blend --python blender/stem-tunnel/stem_tunnel.py -- \\
        --make-template blender/stem-tunnel/stem_tunnel.blend

Every reaction is a driver on the AudioSignals empty (the run's modulators, baked one key per frame) and the
NeonControls empty (the look's sliders). All drivers are simple expressions, so no Python auto-run is needed.
"""

import argparse
import json
import math
import sys
import time
import tomllib
from pathlib import Path

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
from datapipe import mapping  # noqa: E402  numpy only, shared with the pipeline

CTRL, SIG, CAM = "NeonControls", "AudioSignals", "NeonCam"
TUNNEL = ("Tunnel_Walls", "Tunnel_Portals", "Tunnel_Outer")
FRAMES, FPS = 480, 60
LEVELS = ("kick", "kick_light", "bass", "energy", "hats", "mids", "bright", "twist")    # 0-1 look signals
DEG = 4 * math.pi / 360        # the roll and spin unit of the look's sliders (as in blender/audio-tunnel)


def main() -> None:
    a = parse_args()
    if a.make_template:
        make_template(a.make_template)
        return
    t0 = time.time()
    controls = json.loads((a.run / "controls.json").read_text(encoding="utf-8"))
    with open(a.mapping, "rb") as fh:
        cfg = tomllib.load(fh)
    scene, ctrl = bpy.context.scene, bpy.data.objects[CTRL]
    levels = look_signals(controls, cfg)
    tracks, closure = motion(levels, controls, ctrl, cfg)
    bake(loop_keys(levels) | tracks)
    wire(scene, ctrl)
    configure(scene, a.width, a.height, a.percent, a.samples, a.frames_dir)
    set_sound(scene, a.run / "mix.wav")
    if a.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(a.save_blend), compress=True, copy=True)
    timings = {"bake_s": round(time.time() - t0, 2)}
    if not a.no_render:
        t1 = time.time()
        bpy.app.handlers.render_post.append(_progress)
        bpy.ops.render.render(animation=True)
        timings["render_s"] = round(time.time() - t1, 1)
        if a.seam:
            scene.frame_set(FRAMES + 1)
            scene.render.filepath = str(a.frames_dir / f"seam_{FRAMES + 1:04d}.png")
            bpy.ops.render.render(write_still=True)
    summary = {"closure": closure, "timings": timings,
               "signals": {k: [round(float(v.min()), 3), round(float(v.mean()), 3), round(float(v.max()), 3)]
                           for k, v in levels.items() if k in LEVELS}}
    print("STEM_TUNNEL_RESULT " + json.dumps(summary), flush=True)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(prog="stem_tunnel.py")
    p.add_argument("--run", type=Path, help="a work/gen/<run> folder with controls.json and mix.wav")
    p.add_argument("--frames-dir", type=Path, help="where frame_0001.png ... frame_0480.png go")
    p.add_argument("--mapping", type=Path, default=HERE / "mapping.toml")
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.add_argument("--percent", type=int, default=100)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--seam", action="store_true", help="also render frame 481, which must match frame 1")
    p.add_argument("--save-blend", type=Path, help="save the baked scene here, to open and scrub")
    p.add_argument("--no-render", action="store_true")
    p.add_argument("--make-template", type=Path, help="turn the open reference scene into the template, save it here")
    a = p.parse_args(argv)
    if not a.make_template and not (a.run and a.frames_dir):
        p.error("--run and --frames-dir are required to render")
    return a


# ---- modulators -> look signals ------------------------------------------------------------------------------------

def look_signals(controls: dict, cfg: dict) -> dict[str, np.ndarray]:
    """The look's 0-1 signals from the run's modulators, as mapping.toml wires them."""
    n = controls["frames"]
    zeros = np.zeros(n)
    hit_shapes = cfg.get("hit", {})
    ease = int(cfg.get("motion", {}).get("section_ease", 15))

    def source(name: str) -> np.ndarray:
        kind, _, key = name.partition(":")
        if kind == "hit":
            track = controls["tracks"].get(key)
            shape = {**hit_shapes.get("default", {}), **hit_shapes.get(key, {})}
            return mapping.hit_envelope(track["hits"], n, shape.get("windup", 0), shape.get("decay", 8)) if track else zeros
        if kind == "stem":
            return np.asarray(controls["stems"].get(key, {}).get("loud", zeros))
        if kind == "mix":
            return np.asarray(controls["mix"][key])
        if kind == "curve":
            return np.asarray(controls["curves"].get(key, zeros))
        if kind == "section":
            return section(controls, key, ease)
        raise ValueError(f"mapping.toml: unknown source {name!r}")

    out = {name: np.clip(sum(w * source(s) for s, w in sources.items()), 0.0, 1.0)
           for name, sources in cfg["signals"].items()}
    for name, frames in cfg.get("smooth", {}).items():
        out[name] = mapping.smooth(out[name], frames)
    for name in LEVELS:
        out.setdefault(name, zeros)
    ring_cfg = cfg.get("ring", {})
    ring = controls["tracks"].get(ring_cfg.get("track", "kick"))
    out["kick_age"], last = mapping.since_last_hit(ring["hits"] if ring else [], n)
    out["kick_last"] = float(ring_cfg.get("level", 1.0)) * last
    out["hue_off"] = float(cfg.get("motion", {}).get("twist_hue", 0.0)) * out["twist"]
    return out


def section(controls: dict, name: str, ease: int) -> np.ndarray:
    """1 inside a section of the story, with linear ramps of ``ease`` frames centred on its edges."""
    n = controls["frames"]
    starts = sorted((s["frame"], s["name"]) for s in controls["sections"]) + [(n, "")]
    gate = np.zeros(n)
    for (a, nm), (b, _) in zip(starts, starts[1:]):
        if nm == name:
            gate[a:b] = 1.0
    return mapping.smooth(gate, ease)


def motion(levels: dict, controls: dict, ctrl, cfg: dict) -> tuple[dict, dict]:
    """Accumulated motion as positions (481 keys), each closed on the loop so frame 481 is frame 1's picture.

    Rates follow the reference look's drivers (blender/audio-tunnel), plus the riser and the twist."""
    c = lambda k: float(ctrl[k])  # noqa: E731
    m = cfg.get("motion", {})
    K, R = int(ctrl["_built_K"]), float(ctrl["_built_R"])
    L = 2 * math.pi * R / K                                   # one wall segment, also the portal spacing
    riser = np.asarray(controls["curves"].get("riser", np.zeros(controls["frames"])))
    rates = {
        # name: (rate per frame, period). Walls repeat every 2 segments in depth; around the tunnel the walls
        # repeat every 2 segments (K even) or once round (K odd), portals and the outer shell every segment.
        "travel": (12 * L / 360 * c("speed") * (c("speed_idle") + c("speed_energy") * levels["energy"]
                   + c("speed_kick") * levels["kick"] + float(m.get("speed_riser", 0)) * riser), 2 * L),
        "roll": (DEG * (c("roll_idle") + c("roll_bass") * levels["bass"] + float(m.get("roll_twist", 0)) * levels["twist"]),
                 2 * math.pi if K % 2 else 4 * math.pi / K),
        "outer": (DEG * (c("outer_spin_idle") + c("outer_spin_hats") * levels["hats"]), 2 * math.pi / K),
        "portal": (0.03 * c("portal_spin_mids") * levels["mids"], 2 * math.pi / K),
        "phase": ((c("color_idle") + c("color_energy") * levels["energy"]) / 360, 1.0),
    }
    tracks, closure = {}, {}
    for name, (rate, period) in rates.items():
        tracks[name], closure[name] = mapping.close_loop(rate, period)
    return tracks, closure


def loop_keys(levels: dict) -> dict:
    """481 keys per level signal: frame 481 repeats frame 1, so the loop's restart is a real keyframe."""
    return {k: np.append(v, v[0]) for k, v in levels.items()}


# ---- scene ---------------------------------------------------------------------------------------------------------

def bake(values: dict) -> None:
    """One linear key per frame on the AudioSignals empty, replacing whatever was there."""
    sig = bpy.data.objects[SIG]
    for k in list(sig.keys()):
        del sig[k]
    for k in values:
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
    """(Re)create every driver of the look on the run's signals; all must be simple expressions."""
    O = bpy.data.objects
    cam, walls, portals, outer = O[CAM], O["Tunnel_Walls"], O["Tunnel_Portals"], O["Tunnel_Outer"]
    K, R = int(ctrl["_built_K"]), float(ctrl["_built_R"])
    per = 2 * (2 * math.pi * R / K)
    nodes = bpy.data.materials["NeonLine"].node_tree.nodes
    glare = sorted((nd for nd in scene.compositing_node_group.nodes if nd.bl_idname == "CompositorNodeGlare"),
                   key=lambda nd: nd.name)
    specs = [
        (cam, "location", 2, f"-fmod(travel, {per:.8f})"),
        (cam, "rotation_euler", 2, "roll + kick_jolt*kick"),
        (cam.data, "lens", -1, "max(lens - kick_zoom*kick, 2)"),
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
            continue                       # functions and constants: fmod, max, exp
        v = d.variables.new()
        v.name, v.type = name, "SINGLE_PROP"
        v.targets[0].id_type, v.targets[0].id, v.targets[0].data_path = "OBJECT", target, f'["{name}"]'
    d.expression = expr
    return fc


def configure(scene, width: int, height: int, percent: int, samples: int, frames_dir: Path | None) -> None:
    """Render settings: 60 fps, frames 1-480, 9:16, EEVEE, 8-bit RGB PNG frames for the encoder."""
    r = scene.render
    r.fps, r.fps_base = FPS, 1.0
    scene.frame_start, scene.frame_end = 1, FRAMES
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


def make_template(path: Path) -> None:
    """From the reference scene: keep the lines look and its sliders, drop the kaleidoscope, the old audio wiring
    and the UI script, wire the drivers to neutral signals and save."""
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
    for key in ("audio_file", "audio_start", "audio_length", "_track_seconds", "kick_sensitivity", "kick_length",
                "_looks") + tuple(k for k in ctrl.keys() if k.startswith("k_")):
        if key in ctrl:
            del ctrl[key]
    ctrl["look_mode"] = 0
    add_near_fade(ctrl)
    silent = {"frames": FRAMES, "sections": [{"name": "hook", "frame": 0}], "tracks": {}, "stems": {}, "curves": {},
              "mix": {"loud": [0.0] * FRAMES, "bright": [0.0] * FRAMES}}
    with open(HERE / "mapping.toml", "rb") as fh:
        cfg = tomllib.load(fh)
    levels = look_signals(silent, cfg)
    tracks, _ = motion(levels, silent, ctrl, cfg)
    bake(loop_keys(levels) | tracks)
    wire(scene, ctrl)
    configure(scene, 1080, 1920, 100, 32, None)
    set_sound(scene, None)
    scene.frame_set(1)
    bpy.data.orphans_purge(do_recursive=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True)
    print(f"STEM_TUNNEL_RESULT template saved to {path}", flush=True)


def add_near_fade(ctrl) -> None:
    """Portals fade out as they come within `near_fade` of the camera plane (view Z depth), so a portal dissolves as
    the camera flies through it instead of sweeping bright across the whole frame: those passes were the loop's
    flashes (a 0.13-0.17 rise in mean luminance each). Only the portals (pass index 1) fade; walls and the outer
    shell keep the reference look."""
    if "near_fade" not in ctrl:
        ctrl["near_fade"] = 55.0
    ctrl.id_properties_ui("near_fade").update(
        min=0.0, max=120.0, soft_min=0.0, soft_max=80.0, default=55.0, precision=1,
        description="Portals fade out within this distance of the camera plane (0 = off), so flying through them doesn't flash")
    bpy.data.objects["Tunnel_Portals"].pass_index = 1
    nt = bpy.data.materials["NeonLine"].node_tree
    if "NearFade" in nt.nodes:
        return
    emission = next(nd for nd in nt.nodes if nd.bl_idname == "ShaderNodeEmission")
    camera = next(nd for nd in nt.nodes if nd.bl_idname == "ShaderNodeCameraData")
    info = nt.nodes.new("ShaderNodeObjectInfo")
    fade = nt.nodes.new("ShaderNodeMapRange")
    fade.name = fade.label = "NearFade"
    fade.interpolation_type, fade.clamp = "SMOOTHSTEP", True
    fade.inputs["To Min"].default_value, fade.inputs["To Max"].default_value = 0.0, 1.0
    nt.links.new(camera.outputs["View Z Depth"], fade.inputs["Value"])

    def math(op, a, b):
        nd = nt.nodes.new("ShaderNodeMath")
        nd.operation = op
        for socket, v in zip(nd.inputs, (a, b)):
            if isinstance(v, float):
                socket.default_value = v
            else:
                nt.links.new(v, socket)
        return nd.outputs[0]

    dim = math("MULTIPLY", info.outputs["Object Index"], math("SUBTRACT", 1.0, fade.outputs["Result"]))
    strength = emission.inputs["Strength"].links[0].from_socket
    nt.links.new(math("MULTIPLY", strength, math("SUBTRACT", 1.0, dim)), emission.inputs["Strength"])


def _progress(scene, *_):
    print(f"STEM_TUNNEL frame {scene.frame_current}/{FRAMES}", flush=True)


main()
