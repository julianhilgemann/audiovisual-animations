"""The tuner (SPEC §6): a Datapipe tab in the 3D view's sidebar (N) to tune one run on the stem tunnel by eye and
ear, then render it with exactly what you tuned.

    uv run datapipe tune stems inbox/stems/mytrack      # analyse, then open the run here
    uv run datapipe tune --run work/midi/latest         # an existing run
    uv run datapipe tune deep                           # the method's latest run

What it edits, and where "Save to run" puts it (the run's tuning folder, which `datapipe short --run` renders with):

    mapping   which of the run's sources drive the look's signals    -> <run>/tuning/stem-tunnel/mapping.toml
    sliders   the look's live values (look.toml [look])              -> style.toml [look]; keyframes: automation.json
    shape     the geometry (look.toml [shape], shapes.py)            -> style.toml [shape]

"Save style as" keeps a style for every song (styles/<name>.toml, `--style <name>`), "Save as method default"
writes mappings/<method>.toml. The panel bakes with stem_tunnel.py's own functions (look_signals, motion, bake,
wire), so the scene you tune and the headless render are keyed identically; a mapping change re-bakes in
milliseconds, a slider that moves the camera or the spins re-bakes its motion, a shape change rebuilds the meshes.

Opened by `stem_tunnel.py --tune` (stem_tunnel.blend in the GUI); the session is saved as <run>/tune.blend so the
template stays untouched. In background mode (tests) nothing waits on timers: call ``flush()`` after a change.
"""

import json
import os
import subprocess
from pathlib import Path

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty,
                       StringProperty)
from bpy.types import Operator, Panel, PropertyGroup

import stem_tunnel as look
from datapipe import recipe

ROOT = look.HERE.parents[1]
SCHEMA = look.SCHEMA
CATEGORY = "Datapipe"
MOTION_KEYS = ("speed_curve", "speed_riser", "roll_twist", "twist_hue", "section_ease")
PREVIEW = {"percent": 50, "samples": 8}             # what F12 renders in the session (the pipeline's --preview)
_state = {"controls": None, "pending": set(), "render": None, "motion": None, "loading": False, "python": None,
          "mapping_head": "", "saved": None, "items": {}}


# ---- state in the scene ------------------------------------------------------------------------------------------

def _changed(kind: str):
    def update(self, context):
        if not _state["loading"]:
            schedule(kind)
    return update


class DATAPIPE_Name(PropertyGroup):
    pass                                             # name only: tracks, curves, sources of the run


class DATAPIPE_Source(PropertyGroup):
    weight: FloatProperty(name="Weight", min=-2.0, max=4.0, soft_min=0.0, soft_max=1.5, precision=2,
                          update=_changed("rebake"), description="How much of this source the signal takes")


class DATAPIPE_Signal(PropertyGroup):
    sources: CollectionProperty(type=DATAPIPE_Source)
    smooth: IntProperty(name="Smooth", min=1, max=240, default=1, update=_changed("rebake"),
                        description="Moving average over this many frames, after the sources are summed (1 = off)")
    smooth_rank: IntProperty(default=-1)           # where the mapping file listed it in [smooth]
    present: BoolProperty(default=False)           # the mapping file had it
    show: BoolProperty(name="Show", default=True)


class DATAPIPE_Hit(PropertyGroup):
    windup: IntProperty(name="Wind-up", min=0, max=30, update=_changed("rebake"),
                        description="Frames the envelope rises before the hit (anticipation)")
    decay: IntProperty(name="Decay", min=1, max=240, default=8, update=_changed("rebake"),
                       description="Frames until the envelope has fallen to 5 % after the hit")


def _motion_changed(key: str):
    def update(self, context):
        if not _state["loading"]:
            keys = [k for k in self.motion_keys.split(",") if k]
            if key not in keys:
                self.motion_keys = ",".join(keys + [key])
            schedule("rebake")
    return update


def _ring_changed(self, context):
    if not _state["loading"]:
        self.ring_set = True
        schedule("rebake")


def _shape_group():
    """The shape's properties, made from look.toml [shape] (an int, a float or a choice each)."""
    ann = {}
    for key, spec in SCHEMA["shape"].items():
        common = {"name": spec["label"], "description": spec["help"], "update": _changed("shape")}
        if "options" in spec:
            ann[key] = EnumProperty(items=[(o, o.title(), "") for o in spec["options"]], default=spec["default"],
                                    **common)
        elif isinstance(spec["default"], int):
            ann[key] = IntProperty(min=spec["min"], max=spec["max"], default=spec["default"], **common)
        else:
            ann[key] = FloatProperty(min=spec["min"], max=spec["max"], default=spec["default"], precision=3, **common)
    return type("DATAPIPE_Shape", (PropertyGroup,), {"__annotations__": ann})


DATAPIPE_Shape = _shape_group()


class DATAPIPE_Tuning(PropertyGroup):
    run: StringProperty(name="Run")
    method: StringProperty(name="Method")
    save_to: StringProperty(name="Tuning folder", subtype="DIR_PATH")
    mapping_path: StringProperty(name="Mapping", subtype="FILE_PATH")
    style_path: StringProperty(name="Style", subtype="FILE_PATH")
    signals: CollectionProperty(type=DATAPIPE_Signal)
    hits: CollectionProperty(type=DATAPIPE_Hit)
    tracks: CollectionProperty(type=DATAPIPE_Name)
    curves: CollectionProperty(type=DATAPIPE_Name)
    sources: CollectionProperty(type=DATAPIPE_Name)
    ring_set: BoolProperty(default=False)
    ring_track: StringProperty(name="Ring track", update=_ring_changed,
                               description="The light ring races into the tunnel on this track's hits")
    ring_level: FloatProperty(name="Ring level", min=0.0, max=2.0, default=1.0, update=_ring_changed)
    motion_keys: StringProperty(default="")        # the [motion] keys the file had, in its order, plus changed ones
    speed_curve: StringProperty(name="Speed curve", update=_motion_changed("speed_curve"),
                                description=SCHEMA["recipe"]["speed_curve"])
    speed_riser: FloatProperty(name="Speed by curve", min=0.0, max=20.0, update=_motion_changed("speed_riser"),
                               description=SCHEMA["recipe"]["speed_riser"])
    roll_twist: FloatProperty(name="Twist roll", min=-10.0, max=10.0, update=_motion_changed("roll_twist"),
                              description=SCHEMA["recipe"]["roll_twist"])
    twist_hue: FloatProperty(name="Twist hue", min=-1.0, max=1.0, update=_motion_changed("twist_hue"),
                             description=SCHEMA["recipe"]["twist_hue"])
    section_ease: IntProperty(name="Section ease", min=1, max=240, default=15, update=_motion_changed("section_ease"),
                              description=SCHEMA["recipe"]["section_ease"])
    shape: PointerProperty(type=DATAPIPE_Shape)
    auto_rebuild: BoolProperty(name="Auto", default=True, description="Rebuild the tunnel on every shape change")
    shape_dirty: BoolProperty(default=False)
    shape_info: StringProperty(default="")
    style_name: StringProperty(name="Name", default="my_style")
    dirty: BoolProperty(default=False)
    message: StringProperty(default="")
    render_status: StringProperty(default="")
    render_video: StringProperty(default="")


# ---- loading and saving ------------------------------------------------------------------------------------------

def start(a) -> None:
    """Open a run for tuning (stem_tunnel.py --tune)."""
    register()
    _state["python"] = a.pipeline_python
    run = Path(a.run)
    load_run(run, mapping=a.mapping, style=a.style, automation=a.automation, method=a.method,
             save_to=a.save_to or run / "tuning" / look.HERE.name)
    if not bpy.app.background:
        bpy.ops.wm.save_as_mainfile(filepath=str(run / "tune.blend"), compress=True)
        bpy.app.timers.register(_setup_ui, first_interval=0.3)
        bpy.app.timers.register(_tick, first_interval=1.0, persistent=True)
    print(f"DATAPIPE_TUNER ready {run}", flush=True)


def load_run(run: Path, mapping: Path, style: Path | dict | None = None, automation: Path | None = None,
             method: str | None = None, save_to: Path | None = None) -> None:
    """Bake ``run`` with a mapping file and a style (a file, a resolved style, or None for the defaults)."""
    scene, t = bpy.context.scene, bpy.context.scene.datapipe
    ctrl = bpy.data.objects[look.CTRL]
    controls = json.loads((run / "controls.json").read_text(encoding="utf-8"))
    _state["controls"] = controls
    _state["loading"] = True
    try:
        t.run, t.method = str(run), method or controls.get("method", "gen")
        t.save_to = str(save_to or run / "tuning" / look.HERE.name)
        t.mapping_path = str(mapping)
        if not isinstance(style, dict):
            t.style_path = str(style or "")
        for coll, names in ((t.tracks, controls.get("tracks", {})), (t.curves, controls.get("curves", {})),
                            (t.sources, look.available_sources(controls))):
            coll.clear()
            for name in names:
                coll.add().name = name
        set_mapping(recipe.load(mapping), recipe.header(mapping))
        set_style(style if isinstance(style, dict) else recipe.resolve_style(recipe.load(style) if style else {}, SCHEMA))
        if ctrl.animation_data:
            ctrl.animation_data_clear()
        if automation and Path(automation).exists():
            look.set_automation(ctrl, json.loads(Path(automation).read_text(encoding="utf-8")))
    finally:
        _state["loading"] = False
    rebuild_now()
    look.configure(scene, 1080, 1920, PREVIEW["percent"], PREVIEW["samples"], None, controls["frames"])
    look.set_sound(scene, run / "mix.wav")
    sig = bpy.data.objects[look.SIG]
    for name in look.LEVELS:
        sig.id_properties_ui(name).update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0, precision=2)
    scene.frame_set(1)
    _state["saved"] = snapshot()
    t.dirty, t.message = False, f"Loaded {run.name}"


def set_mapping(cfg: dict, head: str) -> None:
    """The mapping file into the panel's properties."""
    t = bpy.context.scene.datapipe
    _state["mapping_head"] = head
    t.signals.clear()
    smooth = list(cfg.get("smooth", {}))
    for name in list(cfg.get("signals", {})) + [s for s in look.LEVELS if s not in cfg.get("signals", {})]:
        s = t.signals.add()
        s.name, s.present = name, name in cfg.get("signals", {})
        for key, weight in cfg.get("signals", {}).get(name, {}).items():
            src = s.sources.add()
            src.name, src.weight = key, weight
        s.smooth = int(cfg.get("smooth", {}).get(name, 1))
        s.smooth_rank = smooth.index(name) if name in smooth else -1
    t.hits.clear()
    for track, shape in cfg.get("hit", {}).items():
        h = t.hits.add()
        h.name, h.windup, h.decay = track, int(shape.get("windup", 0)), int(shape.get("decay", 8))
    ring = cfg.get("ring")
    t.ring_set = ring is not None
    t.ring_track, t.ring_level = (ring or {}).get("track", "kick"), float((ring or {}).get("level", 1.0))
    m = cfg.get("motion", {})
    t.motion_keys = ",".join(k for k in m if k in MOTION_KEYS)
    t.speed_curve = m.get("speed_curve", "riser")
    t.speed_riser, t.roll_twist = float(m.get("speed_riser", 0.0)), float(m.get("roll_twist", 0.0))
    t.twist_hue, t.section_ease = float(m.get("twist_hue", 0.0)), int(m.get("section_ease", 15))


def mapping_from_scene() -> dict:
    """The panel's mapping as a mapping file holds it (what Save writes, what the bake uses)."""
    t = bpy.context.scene.datapipe
    cfg = {}
    if t.ring_set:
        cfg["ring"] = {"track": t.ring_track, "level": round(t.ring_level, 4)}
    cfg["signals"] = {s.name: {src.name: round(src.weight, 4) for src in s.sources}
                      for s in t.signals if s.present or len(s.sources)}
    ranked = sorted((s for s in t.signals if s.smooth > 1), key=lambda s: (s.smooth_rank < 0, s.smooth_rank))
    if ranked:
        cfg["smooth"] = {s.name: s.smooth for s in ranked}
    if len(t.hits):
        cfg["hit"] = {h.name: {"windup": h.windup, "decay": h.decay} for h in t.hits}
    keys = [k for k in t.motion_keys.split(",") if k]
    if keys:
        cfg["motion"] = {k: (getattr(t, k) if isinstance(getattr(t, k), (str, int)) else round(getattr(t, k), 4))
                         for k in keys}
    return cfg


def set_style(style: dict) -> None:
    """A resolved style into the scene: the sliders on NeonControls and the shape into the panel (built by the
    caller with ``rebuild_now``)."""
    ctrl, t = bpy.data.objects[look.CTRL], bpy.context.scene.datapipe
    for key, value in style["look"].items():
        ctrl[key] = float(value)
    was, _state["loading"] = _state["loading"], True
    try:
        for key, value in style["shape"].items():
            setattr(t.shape, key, value)
    finally:
        _state["loading"] = was


def shape_from_scene() -> dict:
    t = bpy.context.scene.datapipe
    return {k: (round(v, 4) if isinstance(v, float) else v) for k in SCHEMA["shape"] for v in [getattr(t.shape, k)]}


def style_from_scene() -> dict:
    ctrl = bpy.data.objects[look.CTRL]
    return {"shape": shape_from_scene(), "look": {k: round(float(ctrl[k]), 4) for k in SCHEMA["look"]}}


def snapshot() -> str:
    """Everything Save writes, to tell whether there is anything unsaved."""
    return json.dumps([mapping_from_scene(), style_from_scene(), look.automation(bpy.data.objects[look.CTRL])],
                      sort_keys=True)


def save_to_run() -> Path:
    """Write the run's tuning folder: mapping.toml, style.toml and (if any slider is keyframed) automation.json."""
    t = bpy.context.scene.datapipe
    folder = Path(t.save_to)
    head = _state["mapping_head"]
    tuned = f"# Tuned for run {Path(t.run).name} with `datapipe tune`; the look's own is mappings/{t.method}.toml."
    if not head.startswith("# Tuned for run"):
        head = tuned + ("\n#\n" + head if head else "")
    recipe.save(folder / "mapping.toml", recipe.dumps_mapping(mapping_from_scene(), SCHEMA, head))
    recipe.save(folder / "style.toml", recipe.dumps_style(style_from_scene(), SCHEMA,
                                                          f"# Style tuned for run {Path(t.run).name} with `datapipe tune`."))
    keys = look.automation(bpy.data.objects[look.CTRL])
    auto = folder / "automation.json"
    if keys["params"]:
        recipe.save(auto, json.dumps(keys, indent=1) + "\n")
    elif auto.exists():
        auto.unlink()
    t.mapping_path, t.style_path = str(folder / "mapping.toml"), str(folder / "style.toml")
    _state["mapping_head"] = head
    _state["saved"] = snapshot()
    t.dirty, t.message = False, f"Saved to {folder.relative_to(ROOT) if folder.is_relative_to(ROOT) else folder}"
    return folder


# ---- re-baking -----------------------------------------------------------------------------------------------------

def schedule(kind: str) -> None:
    """Re-bake (a mapping or motion change) or rebuild (a shape change) shortly, once, however many changes come."""
    t = bpy.context.scene.datapipe
    if kind == "shape" and not t.auto_rebuild:
        t.shape_dirty = True
        return
    _state["pending"].add("rebuild" if kind == "shape" else "rebake")
    if bpy.app.timers.is_registered(flush):
        bpy.app.timers.unregister(flush)
    bpy.app.timers.register(flush, first_interval=0.35 if "rebuild" in _state["pending"] else 0.12)


def flush() -> None:
    """Do the pending re-bake or rebuild now."""
    pending, _state["pending"] = _state["pending"], set()
    try:
        if "rebuild" in pending:
            rebuild_now()
        elif "rebake" in pending:
            rebake_now()
    except Exception as e:  # noqa: BLE001  a bad value shows in the panel instead of breaking the session
        bpy.context.scene.datapipe.message = f"Error: {e}"
        print(f"DATAPIPE_TUNER error {e!r}", flush=True)
    return None


def rebake_now() -> None:
    scene, ctrl = bpy.context.scene, bpy.data.objects[look.CTRL]
    look.bake_run(_state["controls"], mapping_from_scene(), ctrl)
    _state["motion"] = _motion_state(ctrl)
    scene.frame_set(scene.frame_current)


def rebuild_now() -> None:
    """Build the panel's shape if the scene has another, then re-wire (the travel period is in a driver) and re-bake
    (the loop closes on the new periods)."""
    scene, ctrl, t = bpy.context.scene, bpy.data.objects[look.CTRL], bpy.context.scene.datapipe
    info = look.ensure_shape(shape_from_scene(), ctrl)
    look.wire(scene, ctrl)
    rebake_now()
    t.shape_dirty = False
    if info:
        t.shape_info = f"{info['verts']:,} vertices, built in {info['build_s']:.2f} s"


def _motion_state(ctrl) -> tuple:
    """The sliders the bake integrates (and their keys): when this changes, the motion needs a re-bake."""
    out = []
    for k in look.MOTION:
        fc = look.fcurve(ctrl, k)
        if fc is not None and len(fc.keyframe_points):
            out.append((k, tuple((*kp.co, *kp.handle_left, *kp.handle_right, kp.interpolation)
                                 for kp in fc.keyframe_points)))
        else:
            out.append((k, round(float(ctrl[k]), 6)))
    return tuple(out)


def _on_depsgraph(scene, depsgraph) -> None:
    if _state["loading"] or _state["controls"] is None or not getattr(scene, "datapipe", None) or not scene.datapipe.run:
        return
    ctrl = bpy.data.objects.get(look.CTRL)
    if ctrl is not None and _motion_state(ctrl) != _state["motion"]:
        _state["motion"] = _motion_state(ctrl)
        schedule("rebake")


def _tick():
    """Once a second: whether anything is unsaved, and how a render from the panel is doing."""
    scene = bpy.context.scene
    if not getattr(scene, "datapipe", None) or not scene.datapipe.run:
        return 1.0
    t = scene.datapipe
    dirty = snapshot() != _state["saved"]
    if dirty != t.dirty:
        t.dirty = dirty
    job = _state["render"]
    if job:
        lines = job["log"].read_text(encoding="utf-8", errors="replace").splitlines() if job["log"].exists() else []
        progress = [ln.strip() for ln in lines if ln.strip().startswith("render ")]
        if job["proc"].poll() is None:
            t.render_status = f"{job['kind']}: {progress[-1] if progress else 'starting'}"
        else:
            fails = [ln.split()[1] for ln in lines if ln.strip().startswith("FAIL")]
            video = next((ln.split("->", 1)[1].strip() for ln in reversed(lines) if ln.strip().startswith("->")), "")
            if job["proc"].returncode not in (0, 1) or not video:
                t.render_status = f"{job['kind']} failed (exit {job['proc'].returncode}): see {job['log'].name}"
            else:
                t.render_status = f"{job['kind']} done: " + ("all checks ok" if not fails else "FAIL " + ", ".join(fails))
                t.render_video = video
            _state["render"] = None
        _redraw()
    return 1.0


def _redraw() -> None:
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _setup_ui():
    """Look through the camera with the final look and glow, the Datapipe tab open (neon_audio.py's live view)."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "DOPESHEET_EDITOR":            # the timeline: show the whole run
                main = next((r for r in area.regions if r.type == "WINDOW"), None)
                if main is not None:
                    try:
                        with bpy.context.temp_override(window=window, area=area, region=main):
                            bpy.ops.action.view_all()
                    except RuntimeError:                  # another dope sheet mode: leave it as it is
                        pass
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.shading.type = "RENDERED"
            try:
                space.shading.use_compositor = "CAMERA"      # the glare, as rendered
            except (AttributeError, TypeError):
                pass
            space.overlay.show_overlays = False
            space.show_gizmo = False
            space.show_region_ui = True
            space.region_3d.view_perspective = "CAMERA"
            for region in area.regions:
                if region.type == "UI":
                    region.active_panel_category = CATEGORY
            main = next((r for r in area.regions if r.type == "WINDOW"), None)
            if main is not None:
                with bpy.context.temp_override(window=window, area=area, region=main):
                    bpy.ops.view3d.view_center_camera()
    cam = bpy.data.objects[look.CAM].data
    cam.show_passepartout, cam.passepartout_alpha = True, 1.0
    bpy.context.scene.eevee.taa_samples = 4
    return None


# ---- operators -----------------------------------------------------------------------------------------------------

def _items(kind: str):
    def items(self, context):
        out = [(n.name, n.name, "") for n in getattr(context.scene.datapipe, kind)]
        _state["items"][kind] = out                 # Blender needs the list kept alive
        return out or [("", "(none)", "")]
    return items


class DATAPIPE_OT_add_source(Operator):
    bl_idname, bl_label = "datapipe.add_source", "Add source"
    bl_description = "Add one of the run's sources to this signal"
    bl_property = "source"
    signal: StringProperty()
    source: EnumProperty(items=_items("sources"))

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        s = context.scene.datapipe.signals[self.signal]
        if self.source and self.source not in s.sources:
            src = s.sources.add()
            src.name, src.weight = self.source, 0.5
            schedule("rebake")
        return {"FINISHED"}


class DATAPIPE_OT_remove_source(Operator):
    bl_idname, bl_label = "datapipe.remove_source", "Remove source"
    bl_description = "Take this source out of the signal"
    signal: StringProperty()
    index: IntProperty()

    def execute(self, context):
        context.scene.datapipe.signals[self.signal].sources.remove(self.index)
        schedule("rebake")
        return {"FINISHED"}


class DATAPIPE_OT_add_hit(Operator):
    bl_idname, bl_label = "datapipe.add_hit", "Add hit shape"
    bl_description = "Give one of the run's tracks its own hit envelope"
    bl_property = "track"
    track: EnumProperty(items=_items("tracks"))

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        t = context.scene.datapipe
        if self.track and self.track not in t.hits:
            h = t.hits.add()
            h.name, h.windup, h.decay = self.track, 0, 8
            schedule("rebake")
        return {"FINISHED"}


class DATAPIPE_OT_remove_hit(Operator):
    bl_idname, bl_label = "datapipe.remove_hit", "Remove hit shape"
    bl_description = "This track goes back to the default envelope"
    index: IntProperty()

    def execute(self, context):
        context.scene.datapipe.hits.remove(self.index)
        schedule("rebake")
        return {"FINISHED"}


class DATAPIPE_OT_rebuild(Operator):
    bl_idname, bl_label = "datapipe.rebuild", "Rebuild tunnel"
    bl_description = "Build the tunnel with the shape settings above"

    def execute(self, context):
        rebuild_now()
        return {"FINISHED"}


class DATAPIPE_OT_save_run(Operator):
    bl_idname, bl_label = "datapipe.save_run", "Save to run"
    bl_description = "Write mapping, style and keyframes into the run's tuning folder: `datapipe short --run` renders with them"

    def execute(self, context):
        self.report({"INFO"}, context.scene.datapipe.message if save_to_run() else "")
        return {"FINISHED"}


class DATAPIPE_OT_revert(Operator):
    bl_idname, bl_label = "datapipe.revert", "Revert"
    bl_description = "Reload the mapping, style and keyframes from their files"

    def execute(self, context):
        t = context.scene.datapipe
        auto = Path(t.save_to) / "automation.json"
        load_run(Path(t.run), Path(t.mapping_path), Path(t.style_path) if t.style_path else None,
                 auto if auto.exists() else None, t.method, Path(t.save_to))
        return {"FINISHED"}


class DATAPIPE_OT_load_run(Operator):
    bl_idname, bl_label = "datapipe.load_run", "Load run..."
    bl_description = "Tune another run folder (work/<method>/<run>); the current style stays unless it has its own"
    directory: StringProperty(subtype="DIR_PATH")

    def invoke(self, context, event):
        self.directory = str(Path(context.scene.datapipe.run).parent) + os.sep
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        run = Path(self.directory)
        if (run / "RUN.txt").exists():
            run = run.parent / (run / "RUN.txt").read_text(encoding="utf-8").strip()
        if not (run / "controls.json").exists():
            self.report({"ERROR"}, f"{run} has no controls.json: analyse it first (datapipe analyze)")
            return {"CANCELLED"}
        t = context.scene.datapipe
        method = json.loads((run / "controls.json").read_text(encoding="utf-8")).get("method", "gen")
        tuned = run / "tuning" / Path(t.save_to).name
        mapping = tuned / "mapping.toml" if (tuned / "mapping.toml").exists() else look.HERE / "mappings" / f"{method}.toml"
        style = tuned / "style.toml" if (tuned / "style.toml").exists() else style_from_scene()   # else keep this one
        load_run(run, mapping, style, tuned / "automation.json", method, tuned)
        return {"FINISHED"}


class DATAPIPE_OT_load_style(Operator):
    bl_idname, bl_label = "datapipe.load_style", "Load style"
    bl_description = "Set the shape and every slider from this style (keyframes stay)"
    name: StringProperty()

    def execute(self, context):
        path = look.HERE / "styles" / f"{self.name}.toml"
        set_style(recipe.resolve_style(recipe.load(path), SCHEMA))
        context.scene.datapipe.style_path = str(path)
        rebuild_now()
        return {"FINISHED"}


class DATAPIPE_OT_save_style(Operator):
    bl_idname, bl_label = "datapipe.save_style", "Save style as..."
    bl_description = "Keep this shape and these sliders as styles/<name>.toml, for any song (`--style <name>`)"
    name: StringProperty(name="Name", default="my_style")

    def invoke(self, context, event):
        self.name = context.scene.datapipe.style_name
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in self.name.strip()) or "my_style"
        path = look.HERE / "styles" / f"{name}.toml"
        head = f"# Style \"{name}\", saved by the tuner (`datapipe tune`) from run {Path(context.scene.datapipe.run).name}."
        if path.exists():
            head = recipe.header(path) or head
        recipe.save(path, recipe.dumps_style(style_from_scene(), SCHEMA, head))
        context.scene.datapipe.style_name = name
        self.report({"INFO"}, f"Saved {path.relative_to(ROOT)}")
        return {"FINISHED"}


class DATAPIPE_OT_save_mapping_default(Operator):
    bl_idname, bl_label = "datapipe.save_mapping_default", "Save as method default"
    bl_description = "Write this mapping to mappings/<method>.toml: every new run of this method uses it"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        t = context.scene.datapipe
        path = look.HERE / "mappings" / f"{t.method}.toml"
        recipe.save(path, recipe.dumps_mapping(mapping_from_scene(), SCHEMA, recipe.header(path)))
        self.report({"INFO"}, f"Saved {path.relative_to(ROOT)}")
        return {"FINISHED"}


class DATAPIPE_OT_render(Operator):
    bl_idname, bl_label = "datapipe.render", "Render"
    bl_description = "Save to run, then render, encode and check the Short with the pipeline (datapipe short --run)"
    preview: BoolProperty(default=True)

    def execute(self, context):
        if _state["render"]:
            self.report({"WARNING"}, "A render is already running")
            return {"CANCELLED"}
        if not _state["python"]:
            self.report({"ERROR"}, "No pipeline Python: open the tuner with `datapipe tune`")
            return {"CANCELLED"}
        save_to_run()
        t = context.scene.datapipe
        log = Path(t.run) / "tune_render.log"
        cmd = [_state["python"], "-m", "datapipe.cli", "short", "--run", t.run] + (["--preview"] if self.preview else [])
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH")}
        with open(log, "w", encoding="utf-8") as fh:
            proc = subprocess.Popen(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, env=env)
        _state["render"] = {"proc": proc, "log": log, "kind": "preview" if self.preview else "final"}
        t.render_status, t.render_video = f"{_state['render']['kind']}: starting", ""
        return {"FINISHED"}


class DATAPIPE_OT_open_video(Operator):
    bl_idname, bl_label = "datapipe.open_video", "Open video"
    bl_description = "Play the rendered Short"

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=context.scene.datapipe.render_video)
        return {"FINISHED"}


# ---- panels --------------------------------------------------------------------------------------------------------

class _Panel:
    bl_space_type, bl_region_type, bl_category = "VIEW_3D", "UI", CATEGORY

    @classmethod
    def poll(cls, context):
        return bool(getattr(context.scene, "datapipe", None) and context.scene.datapipe.run)


class DATAPIPE_PT_main(_Panel, Panel):
    bl_label = "Datapipe tuner"

    def draw(self, context):
        lay, sc, t = self.layout, context.scene, context.scene.datapipe
        n = _state["controls"]["frames"] if _state["controls"] else sc.frame_end
        box = lay.box()
        box.label(text=f"{Path(t.run).name}", icon="FILE_FOLDER")
        box.label(text=f"method {t.method}, {n} frames ({n / look.FPS:.1f} s)")
        box.label(text=f"mapping: {_short(t.mapping_path)}")
        box.label(text=f"style: {_short(t.style_path) if t.style_path else 'look.toml defaults'}")
        row = lay.row(align=True)
        row.scale_y = 1.4
        row.operator("screen.frame_jump", text="", icon="REW").end = False
        playing = context.screen.is_animation_playing
        row.operator("screen.animation_play", text="Pause" if playing else "Play", icon="PAUSE" if playing else "PLAY")
        lay.label(text=f"{(sc.frame_current - 1) / look.FPS:.2f} s / {n / look.FPS:.2f} s")
        row = lay.row(align=True)
        row.scale_y = 1.3
        row.operator("datapipe.save_run", icon="FILE_TICK", depress=t.dirty)
        row.operator("datapipe.revert", icon="LOOP_BACK")
        lay.label(text="Unsaved changes" if t.dirty else "Saved", icon="ERROR" if t.dirty else "CHECKMARK")
        row = lay.row(align=True)
        row.operator("datapipe.render", text="Render preview", icon="RENDER_ANIMATION").preview = True
        row.operator("datapipe.render", text="Render final", icon="RENDER_STILL").preview = False
        if t.render_status:
            lay.label(text=t.render_status, icon="TIME")
        if t.render_video:
            lay.operator("datapipe.open_video", icon="PLAY")
        if t.message:
            lay.label(text=t.message, icon="INFO")
        row = lay.row(align=True)
        row.operator("datapipe.load_run", icon="FILEBROWSER")
        row.prop(sc.eevee, "taa_samples", text="Viewport samples")


class DATAPIPE_PT_signals(_Panel, Panel):
    bl_label = "Reactivity: signals"
    bl_parent_id = "DATAPIPE_PT_main"

    def draw(self, context):
        t, sig = context.scene.datapipe, bpy.data.objects[look.SIG]
        col = self.layout.column()
        for s in t.signals:
            box = col.box()
            row = box.row(align=True)
            row.prop(s, "show", text="", icon="TRIA_DOWN" if s.show else "TRIA_RIGHT", emboss=False)
            row.label(text=s.name)
            meter = row.row()
            meter.enabled = False
            if s.name in sig:
                meter.prop(sig, f'["{s.name}"]', text="", slider=True)
            if not s.show:
                continue
            if s.name in SCHEMA["signals"]:
                box.label(text=SCHEMA["signals"][s.name])
            for i, src in enumerate(s.sources):
                row = box.row(align=True)
                row.label(text=src.name)
                row.prop(src, "weight", text="", slider=True)
                op = row.operator("datapipe.remove_source", text="", icon="X")
                op.signal, op.index = s.name, i
            row = box.row(align=True)
            row.operator("datapipe.add_source", icon="ADD").signal = s.name
            row.prop(s, "smooth")


class DATAPIPE_PT_motion(_Panel, Panel):
    bl_label = "Reactivity: hits, ring, motion"
    bl_parent_id = "DATAPIPE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        t, lay = context.scene.datapipe, self.layout
        lay.label(text="Hit envelopes (frames)")
        col = lay.column(align=True)
        for i, h in enumerate(t.hits):
            row = col.row(align=True)
            row.label(text=h.name)
            row.prop(h, "windup", text="Wind-up")
            row.prop(h, "decay", text="Decay")
            row.operator("datapipe.remove_hit", text="", icon="X").index = i
        col.operator("datapipe.add_hit", icon="ADD")
        lay.separator()
        lay.prop_search(t, "ring_track", t, "tracks")
        lay.prop(t, "ring_level", slider=True)
        lay.separator()
        lay.prop_search(t, "speed_curve", t, "curves")
        for key in ("speed_riser", "roll_twist", "twist_hue", "section_ease"):
            lay.prop(t, key)


def _look_panel(group: str, index: int):
    keys = [k for k, spec in SCHEMA["look"].items() if spec["group"] == group]

    def draw(self, context):
        ctrl = bpy.data.objects[look.CTRL]
        col = self.layout.column(align=True)
        for k in keys:
            col.prop(ctrl, f'["{k}"]', text=SCHEMA["look"][k]["label"], slider=True)
        if any(SCHEMA["look"][k].get("motion") for k in keys):
            self.layout.label(text="Speeds and spins re-bake the motion", icon="INFO")

    return type(f"DATAPIPE_PT_look_{index}", (_Panel, Panel), {
        "bl_label": f"Look: {group}", "bl_parent_id": "DATAPIPE_PT_main", "bl_options": {"DEFAULT_CLOSED"},
        "draw": draw})


LOOK_PANELS = [_look_panel(g, i) for i, g in enumerate(dict.fromkeys(s["group"] for s in SCHEMA["look"].values()))]


class DATAPIPE_PT_shape(_Panel, Panel):
    bl_label = "Shape"
    bl_parent_id = "DATAPIPE_PT_main"

    def draw(self, context):
        t, lay = context.scene.datapipe, self.layout
        row = lay.row(align=True)
        row.scale_y = 1.3
        row.operator("datapipe.rebuild", icon="MOD_SCREW", depress=t.shape_dirty)
        row.prop(t, "auto_rebuild", toggle=True)
        if t.shape_info:
            lay.label(text=t.shape_info)
        group = None
        col = lay.column(align=True)
        for key, spec in SCHEMA["shape"].items():
            if spec["group"] != group:
                group = spec["group"]
                col = lay.column(align=True)
                col.label(text=group)
            col.prop(t.shape, key, slider="options" not in spec)


class DATAPIPE_PT_styles(_Panel, Panel):
    bl_label = "Styles and defaults"
    bl_parent_id = "DATAPIPE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        t, lay = context.scene.datapipe, self.layout
        lay.label(text="Load a style (shape and sliders)")
        grid = lay.grid_flow(columns=2, even_columns=True, align=True)
        for path in sorted((look.HERE / "styles").glob("*.toml")):
            grid.operator("datapipe.load_style", text=path.stem).name = path.stem
        lay.operator("datapipe.save_style", icon="ADD")
        lay.operator("datapipe.save_mapping_default", text=f"Save mapping as {t.method} default", icon="EXPORT")


def _short(path: str) -> str:
    p = Path(path)
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


CLASSES = (DATAPIPE_Name, DATAPIPE_Source, DATAPIPE_Signal, DATAPIPE_Hit, DATAPIPE_Shape, DATAPIPE_Tuning,
           DATAPIPE_OT_add_source, DATAPIPE_OT_remove_source, DATAPIPE_OT_add_hit, DATAPIPE_OT_remove_hit,
           DATAPIPE_OT_rebuild, DATAPIPE_OT_save_run, DATAPIPE_OT_revert, DATAPIPE_OT_load_run, DATAPIPE_OT_load_style,
           DATAPIPE_OT_save_style, DATAPIPE_OT_save_mapping_default, DATAPIPE_OT_render, DATAPIPE_OT_open_video,
           DATAPIPE_PT_main, DATAPIPE_PT_signals, DATAPIPE_PT_motion, *LOOK_PANELS, DATAPIPE_PT_shape,
           DATAPIPE_PT_styles)


def register() -> None:
    for cls in CLASSES:
        if hasattr(bpy.types, cls.__name__):
            bpy.utils.unregister_class(getattr(bpy.types, cls.__name__))
        bpy.utils.register_class(cls)
    bpy.types.Scene.datapipe = PointerProperty(type=DATAPIPE_Tuning)
    handlers = bpy.app.handlers.depsgraph_update_post
    for h in [h for h in handlers if getattr(h, "__name__", "") == "_on_depsgraph"]:
        handlers.remove(h)
    handlers.append(_on_depsgraph)
