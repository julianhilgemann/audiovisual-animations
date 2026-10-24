"""Run after flythrough.py --no-render: where the camera is and where it looks on a few frames, with the baked travel
and roll, so a test can hold them against worlds.py's path. Prints FLIGHT_CHECK {json}."""

import json

import bpy

scene, cam, sig = bpy.context.scene, bpy.data.objects["FlyCam"], bpy.data.objects["AudioSignals"]
ctrl = bpy.data.objects["NeonControls"]
out = {"path": {k: float(ctrl[f"_path_{k}"]) for k in ("A", "Q", "w")}, "frames": []}
for f in (1, 97, 240, 433):
    scene.frame_set(f)
    m = cam.matrix_world
    out["frames"].append({"frame": f, "travel": float(sig["travel"]), "roll": float(cam.rotation_euler[2]),
                          "location": list(m.translation), "forward": list(-m.col[2].xyz.normalized()),
                          "up": list(m.col[1].xyz.normalized())})
print("FLIGHT_CHECK " + json.dumps(out), flush=True)
