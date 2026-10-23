"""Runs inside Blender on blender/audio-tunnel/neon_tunnel_audio.blend (tests/test_tune.py): shapes.py at the
reference scene's own shape settings must rebuild the meshes its builder (neon_audio.py build_geometry) made."""

import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils.kdtree import KDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "blender" / "stem-tunnel"))
import shapes  # noqa: E402

ctrl = bpy.data.objects["NeonControls"]
shape = {"symmetry": int(ctrl["_built_K"]), "radius": float(ctrl["_built_R"]),
         "line_width": float(ctrl["shape_line_width"]), "outer_size": float(ctrl["shape_outer"])}
out = {}
for name, m in shapes.geometry(shape)["meshes"].items():
    me = bpy.data.objects[name].data
    ref = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", ref)
    ref = ref.reshape(-1, 3)
    tree = KDTree(len(ref))
    for i, v in enumerate(ref):
        tree.insert(v, i)
    tree.balance()
    far = max(tree.find(v)[2] for v in m["co"])
    out[name] = {"verts": [len(ref), len(m["co"])], "faces": [len(me.polygons), len(m["quads"])], "max_dist": far}
print("MESH_PARITY " + json.dumps(out), flush=True)
