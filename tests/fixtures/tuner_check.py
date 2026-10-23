"""Runs inside Blender after `stem_tunnel.py --tune` (tests/test_tune.py): checks that the tuner holds its files
exactly, tunes a little of everything the way a hand in the panel would, saves to the run and prints what it baked.

    blender -b stem_tunnel.blend --python stem_tunnel.py --python tests/fixtures/tuner_check.py -- --tune --run ...

TUNER_CHECK=roundtrip only checks the round trip; TUNER_CHECK=tune (the default) also tunes and saves.
"""

import json
import os
from pathlib import Path

import bpy

import stem_tunnel as look
import tuner
from datapipe import recipe

t = bpy.context.scene.datapipe
ctrl = bpy.data.objects[look.CTRL]
out = {"signals": [s.name for s in t.signals]}

mapping = Path(t.mapping_path)
out["mapping_text_same"] = recipe.dumps_mapping(tuner.mapping_from_scene(), look.SCHEMA, recipe.header(mapping)) \
    == mapping.read_text(encoding="utf-8")
out["mapping_same"] = tuner.mapping_from_scene() == recipe.load(mapping)
style = recipe.resolve_style(recipe.load(Path(t.style_path)) if t.style_path else {}, look.SCHEMA)
out["style_same"] = tuner.style_from_scene() == style
out["baked_loaded"] = look.baked_digest()

if os.environ.get("TUNER_CHECK", "tune") == "tune":
    t.signals["kick"].sources["hit:kick"].weight = 0.7          # a weight
    bpy.ops.datapipe.add_source(signal="hats", source="mix:loud")   # a new source
    t.signals["hats"].sources["mix:loud"].weight = 0.25
    t.signals["bright"].smooth = 20
    ctrl["speed"] = 0.4                                         # a slider the motion integrates
    ctrl["glow_base"] = 0.9                                     # a slider a driver reads
    ctrl["lens"] = 20.0                                         # keyframed: zoom in over the first two seconds
    ctrl.keyframe_insert('["lens"]', frame=1)
    ctrl["lens"] = 32.0
    ctrl.keyframe_insert('["lens"]', frame=120)
    t.shape.profile, t.shape.sides, t.shape.walls, t.shape.twist = "polygon", 6, "hexes", 0.25
    tuner.flush()                                               # what the timer does in the GUI
    out["shape"] = look.shape_info(ctrl, None)
    out["changed_after_tuning"] = tuner.snapshot() != tuner._state["saved"]
    folder = tuner.save_to_run()
    out["saved"] = sorted(p.name for p in folder.iterdir())
    out["clean_after_save"] = tuner.snapshot() == tuner._state["saved"]
    out["baked"] = look.baked_digest()
    out["lens_keys"] = json.loads((folder / "automation.json").read_text())["params"]["lens"]["keys"].__len__()
print("TUNER_CHECK " + json.dumps(out), flush=True)
