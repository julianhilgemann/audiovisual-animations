"""Runs inside Blender on the scene a render saved, opened with its scripts allowed (tests/test_tune.py): checks that
the file's text block brought the tuner back on the run as rendered, and where the watermark is on screen, frame by
frame.

    blender -b --enable-autoexec <run>/scene_baked.blend --python tests/fixtures/opened_check.py
"""

import json

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

import stem_tunnel as look
import tuner                       # imported by the file's text block, not by this script

scene, t = bpy.context.scene, bpy.context.scene.datapipe
out = {"panel": hasattr(bpy.types, "DATAPIPE_PT_main"), "run": t.run, "python": tuner._state["python"],
       "clean": tuner.snapshot() == t.saved, "baked": look.baked_digest()}
tuner.rebake_now()                 # what a change in the panel does
out["rebaked"] = look.baked_digest()

out["lens"], out["watermark"] = [], []
for f in range(1, 121, 3):
    scene.frame_set(f)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    cam, mark = (bpy.data.objects[name].evaluated_get(depsgraph) for name in (look.CAM, look.MARK))
    corners = [world_to_camera_view(scene, cam, mark.matrix_world @ Vector(c)) for c in mark.bound_box]
    out["lens"].append(cam.data.lens)
    out["watermark"].append([min(p.x for p in corners), min(p.y for p in corners),
                             max(p.x for p in corners), max(p.y for p in corners)])
print("OPENED_CHECK " + json.dumps(out), flush=True)
