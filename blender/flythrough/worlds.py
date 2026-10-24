"""The flythrough's geometry: a winding tunnel the camera really flies along, and the worlds that line it.

The tunnel follows a path that bends left and right and up and down,

    x = A sin(w s),  y = A/2 sin(2 w s + PHI),  z = -s,      A = bend x radius,  w = 2 pi / Q,

which repeats after Q = bend_segments x segment. Everything along it is generated for one Q and tiled, so the
picture at s + Q is the picture at s: the camera (flythrough.py `wire`) flies the same path with drivers
(``path_expressions``) and wraps by Q, which nobody can see. Around the path the content repeats ``fold`` times
(``mirror`` reflects each wedge too, as a kaleidoscope does).

Layers (look.toml [shape] picks and sizes them):

    Fly_Walls     static: the movement's plates with bridges, screws and glowing seams, or a grid of light lines
    Fly_Streaks   static: warp streaks along the path; the shader shows as much of each as the speed asks for
    Fly_Spinners  points that a Geometry Nodes modifier turns into instances of the prototypes (gears, dial rings,
                  ring gears, balance wheels, rosettes, gates, crystal slabs), each turned about its own axle by
                  the baked channels: angle = phase + wa . (tick, drive, whirr) + wb . (portal, balance, 0)

Gears mesh: every train shares one tooth rate, so a gear turns 2 pi / T per tooth, the next one the other way, and
their phases put a tooth of one into a gap of the other. A gear's teeth, spokes and pinion all repeat after
``TEETH_PERIOD`` teeth, so the gear channels close on that.

Everything but ``to_mesh`` is numpy only, so the tests check the geometry and its periods without Blender.
"""

import math

import numpy as np

PHI = 0.9                      # the vertical bend's phase against the horizontal one
VIEW_MAX = 160.0               # the furthest the camera sees (look.toml view_far's maximum)
BACK = 24.0                    # geometry kept behind the camera, for what it sees at the edges of the frame
TEETH_PERIOD = 12              # every gear repeats after this many teeth (spokes = T / 12, pinion = T / 6)
SIZES = (12, 24, 36, 48, 60, 72)                    # gear teeth
MODULE = 0.1                   # tooth size at radius 10 and gear_size 1: pitch radius = module x teeth / 2
LEVEL_Z, LEVEL_GAP, GEAR_TH = 0.35, 0.75, 0.18      # gear heights above the plate, gear thickness
PORTAL_ORDER = 12              # dial rings, ring gears, balance wheels and gates repeat 12 times around
MATERIALS = ("Brass", "Steel", "Blued", "Ruby", "Plate", "Seam", "Enamel", "Lume", "Neon", "Gate", "Crystal",
             "Streak")


# ---- the path ----------------------------------------------------------------------------------------------------

def path(shape: dict) -> dict:
    q = shape["bend_segments"] * shape["segment"]
    return {"A": shape["bend"] * shape["radius"], "Q": q, "w": 2 * math.pi / q}


def centre(s, p: dict) -> np.ndarray:
    s = np.asarray(s, np.float64)
    return np.stack([p["A"] * np.sin(p["w"] * s), p["A"] / 2 * np.sin(2 * p["w"] * s + PHI), -s], axis=-1)


def frames(s, p: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Forward, up and right along the path: forward is the tangent, up is world Y made square to it (as the camera's
    yaw-then-pitch makes it), right = forward x up."""
    s = np.asarray(s, np.float64)
    f = np.stack([p["A"] * p["w"] * np.cos(p["w"] * s), p["A"] * p["w"] * np.cos(2 * p["w"] * s + PHI),
                  -np.ones_like(s)], axis=-1)
    f /= np.linalg.norm(f, axis=-1, keepdims=True)
    up = np.array([0.0, 1.0, 0.0]) - f[..., 1:2] * f
    up /= np.linalg.norm(up, axis=-1, keepdims=True)
    return f, up, np.cross(f, up)


def path_expressions(p: dict, s: str) -> dict:
    """The path as simple driver expressions of ``s`` (a distance along it): location and the camera's pitch and yaw
    (Euler ZXY: roll about the view, then pitch, then yaw), matching ``centre`` and ``frames``."""
    a, w = p["A"], p["w"]
    dx, dy = f"{a * w:.9g}*cos({w:.9g}*{s})", f"{a * w:.9g}*cos({2 * w:.9g}*{s} + {PHI})"
    return {"x": f"{a:.9g}*sin({w:.9g}*{s})", "y": f"{a / 2:.9g}*sin({2 * w:.9g}*{s} + {PHI})", "z": f"-({s})",
            "pitch": f"atan({dy}/sqrt(1 + {dx}*{dx}))", "yaw": f"-atan({dx})"}


def quaternions(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """(w, x, y, z) rotations whose matrices have the given columns."""
    m = np.stack([x, y, z], axis=-1)
    q = np.empty((len(m), 4))
    tr = m[:, 0, 0] + m[:, 1, 1] + m[:, 2, 2]
    for i, (r, t) in enumerate(zip(m, tr)):
        if t > 0:
            k = 2 * math.sqrt(t + 1)
            q[i] = (k / 4, (r[2, 1] - r[1, 2]) / k, (r[0, 2] - r[2, 0]) / k, (r[1, 0] - r[0, 1]) / k)
        else:
            j = int(np.argmax(np.diag(r)))
            a, b = (j + 1) % 3, (j + 2) % 3
            k = 2 * math.sqrt(1 + r[j, j] - r[a, a] - r[b, b])
            v = np.empty(3)
            v[j], v[a], v[b] = k / 4, (r[a, j] + r[j, a]) / k, (r[b, j] + r[j, b]) / k
            q[i] = ((r[b, a] - r[a, b]) / k, *v)
    return q * np.where(q[:, :1] < 0, -1, 1)


def tiles(s0: np.ndarray, q: float, extent: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Copies of items at ``s0`` (in [0, Q)) every Q, for as far as the camera sees from anywhere in [0, Q); returns
    which item each copy is and its distance."""
    shifts = np.arange(-math.ceil(BACK / q) - 1, math.ceil((q + VIEW_MAX) / q) + 1) * q
    s = (s0[None, :] + shifts[:, None]).ravel()
    item = np.tile(np.arange(len(s0)), len(shifts))
    keep = (s + extent >= -BACK) & (s - extent <= q + VIEW_MAX)
    return item[keep], s[keep]


# ---- periods -----------------------------------------------------------------------------------------------------

def fold(shape: dict) -> int:
    """How many times the content repeats around the tunnel: plates need it to divide their number."""
    k = int(shape["fold"])
    return math.gcd(k, int(shape["sides"])) if shape["walls"] == "plates" else k


def periods(shape: dict) -> dict:
    """After what the picture repeats: ``travel`` (one bend period), the gear channels in teeth, the portal channel
    in radians (dial rings and gates repeat 12 times around, rosettes and crystal slabs ``fold`` times) and the
    balance's swing. The roll closes on whole turns: the content repeats ``fold`` times around, but the bends ahead
    and the coloured lights flying with the camera don't."""
    k = fold(shape)
    orders = [PORTAL_ORDER] if shape["portals"] not in ("none", "rosette") else []
    orders += [k] if shape["portals"] == "rosette" or shape["shards"] > 0 else []
    order = math.gcd(*orders) if orders else 1
    return {"travel": path(shape)["Q"], "roll": 2 * math.pi, "teeth": float(TEETH_PERIOD),
            "portal": 2 * math.pi / order, "swing": 2 * math.pi}


# ---- meshes ------------------------------------------------------------------------------------------------------

class Mesh:
    """Faces of 3 or 4 corners, a material per face (by name), one UV per vertex."""

    def __init__(self):
        self.co, self.uv, self.faces, self.sizes, self.mat, self.n = [], [], [], [], [], 0
        self.names: list[str] = []

    def add(self, co, faces, mat: str, uv=None) -> None:
        co, faces = np.asarray(co, np.float64), np.asarray(faces, np.int64)
        if mat not in self.names:
            self.names.append(mat)
        self.co.append(co)
        self.uv.append(np.zeros((len(co), 2)) if uv is None else np.asarray(uv, np.float64))
        self.faces.append((faces + self.n).ravel())
        self.sizes.append(np.full(len(faces), faces.shape[1]))
        self.mat.append(np.full(len(faces), self.names.index(mat)))
        self.n += len(co)

    def add_faces(self, faces, mat: str) -> None:
        """Faces on vertices already added, by their index in the whole mesh."""
        faces = np.asarray(faces, np.int64)
        if mat not in self.names:
            self.names.append(mat)
        self.faces.append(faces.ravel())
        self.sizes.append(np.full(len(faces), faces.shape[1]))
        self.mat.append(np.full(len(faces), self.names.index(mat)))

    def place(self, a: dict, co: np.ndarray) -> None:
        """Add another mesh's ``arrays()`` with its vertices moved to ``co``."""
        base, offsets = self.n, np.concatenate([[0], np.cumsum(a["sizes"])])
        self.co.append(np.asarray(co, np.float64))
        self.uv.append(a["uv"])
        self.n += len(co)
        for size in (3, 4):
            for i, name in enumerate(a["names"]):
                sel = np.flatnonzero((a["sizes"] == size) & (a["mat"] == i))
                if len(sel):
                    self.add_faces(a["faces"][offsets[sel][:, None] + np.arange(size)] + base, name)

    def arrays(self) -> dict:
        if not self.co:
            return {"co": np.zeros((0, 3)), "uv": np.zeros((0, 2)), "faces": np.zeros(0, np.int64),
                    "sizes": np.zeros(0, np.int64), "mat": np.zeros(0, np.int64), "names": list(self.names)}
        return {"co": np.concatenate(self.co), "uv": np.concatenate(self.uv), "faces": np.concatenate(self.faces),
                "sizes": np.concatenate(self.sizes), "mat": np.concatenate(self.mat), "names": list(self.names)}


def _circle(r, n: int, a0: float = 0.0) -> np.ndarray:
    a = a0 + np.arange(n) * 2 * math.pi / n
    r = np.broadcast_to(np.asarray(r, np.float64), a.shape)
    return np.stack([r * np.cos(a), r * np.sin(a)], axis=-1)


def band(m: Mesh, outer: np.ndarray, inner: np.ndarray, z0: float, z1: float, mat: str, walls=True,
         bottom=True) -> None:
    """A ring between two closed outlines of the same length, from z0 to z1: top, bottom (unless it always faces
    the plate), outer and inner walls."""
    k = len(outer)
    i, j = np.arange(k), (np.arange(k) + 1) % k
    co = np.concatenate([np.column_stack([outer, np.full(k, z1)]), np.column_stack([inner, np.full(k, z1)]),
                         np.column_stack([outer, np.full(k, z0)]), np.column_stack([inner, np.full(k, z0)])])
    faces = [np.stack([i, j, k + j, k + i], 1)]
    if bottom:
        faces.append(np.stack([2 * k + i, 3 * k + i, 3 * k + j, 2 * k + j], 1))
    if walls:
        faces += [np.stack([2 * k + i, 2 * k + j, j, i], 1), np.stack([3 * k + i, k + i, k + j, 3 * k + j], 1)]
    uv = np.concatenate([np.column_stack([np.arange(k) / k, np.full(k, w)]) for w in (1.0, 0.0, 1.0, 0.0)])
    m.add(co, np.concatenate(faces), mat, uv)


def prism(m: Mesh, outline: np.ndarray, z0: float, z1: float, mat: str, offset=(0.0, 0.0), bottom=True) -> None:
    """A solid from a closed outline that is star-shaped about its centre: walls and two fan caps (or only the top
    one)."""
    k = len(outline)
    o = np.asarray(outline) + np.asarray(offset)
    c = o.mean(axis=0)
    i, j = np.arange(k), (np.arange(k) + 1) % k
    co = np.concatenate([np.column_stack([o, np.full(k, z1)]), np.column_stack([o, np.full(k, z0)]),
                         [[*c, z1], [*c, z0]]])
    start = m.n
    m.add(co, np.stack([k + i, k + j, j, i], 1), mat)
    m.add_faces(np.stack([i, j, np.full(k, 2 * k)], 1) + start, mat)
    if bottom:
        m.add_faces(np.stack([k + j, k + i, np.full(k, 2 * k + 1)], 1) + start, mat)


def bar(m: Mesh, angle: float, r0: float, r1: float, width: float, z0: float, z1: float, mat: str) -> None:
    """A box from radius r0 to r1 at ``angle``, ``width`` wide, open underneath (it always sits on something)."""
    c, s = math.cos(angle), math.sin(angle)
    d, n = np.array([c, s]), np.array([-s, c]) * width / 2
    prism(m, np.array([d * r0 - n, d * r1 - n, d * r1 + n, d * r0 + n]), z0, z1, mat, bottom=False)


def teeth(t: int, module: float, inward: bool = False, per_tooth: int = 5, radius: float | None = None) -> np.ndarray:
    """A toothed outline, tooth 0 centred on +X: rounded tips and flanks between the root and the tip circle around
    the pitch circle (module x teeth / 2, or ``radius``). ``inward`` points the teeth to the centre (a ring gear)."""
    rp = radius if radius is not None else module * t / 2
    a = np.arange(t * per_tooth) * 2 * math.pi / (t * per_tooth)
    g = np.clip(((0.5 + 0.5 * np.cos(t * a)) - 0.28) / 0.44, 0.0, 1.0)
    g = g * g * (3 - 2 * g)
    r = rp - 1.2 * module + 2.2 * module * g if not inward else rp + 1.2 * module - 2.2 * module * g
    return np.stack([r * np.cos(a), r * np.sin(a)], axis=-1)


# ---- prototypes: what the spinners instance ----------------------------------------------------------------------

def gear_proto(t: int, module: float) -> Mesh:
    """A watch wheel of ``t`` teeth: rim, hub and t / 12 spokes (solid under 36 teeth), a pinion of t / 6 leaves on
    top, the arbor through it and a ruby cap jewel in a gold setting. Tooth 0 on +X, the axle along +Z. Nothing that
    always faces the plate gets a face."""
    m, th = Mesh(), GEAR_TH
    rp = module * t / 2
    outline = teeth(t, module)
    hub = max(0.2 * rp, 3.2 * module)
    turn = t // TEETH_PERIOD if t >= 36 else 2         # the gear turns 1 / turn round per period: circles keep it

    def around(n: int) -> int:
        return turn * math.ceil(n / turn)

    if t >= 36:
        rim = rp - 1.2 * module - max(2.4 * module, 0.07 * rp)
        band(m, outline, _circle(rim, len(outline)), 0.0, th, "Brass", bottom=False)
        band(m, _circle(hub, around(24)), _circle(0.45 * hub, around(24)), -0.02, th + 0.02, "Brass", bottom=False)
        spokes = t // TEETH_PERIOD
        for k in range(spokes):
            bar(m, 2 * math.pi * k / spokes, 0.85 * hub, rim + 0.6 * module, max(0.1 * rp, 2 * module), 0.02,
                th - 0.02, "Brass")
    else:
        band(m, outline, _circle(0.35 * rp, len(outline)), 0.0, th, "Steel" if t <= 12 else "Brass", bottom=False)
    top = th
    if t >= 36:
        top = th + 0.5
        prism(m, teeth(t // 6, module), th, top, "Steel", bottom=False)
    prism(m, _circle(min(0.07, 0.5 * hub), around(8)), -0.4, top + 0.12, "Steel", bottom=False)
    band(m, _circle(0.3 * min(1.0, rp / 1.2) + 0.08, around(20)), _circle(0.17, around(20)), top, top + 0.07, "Brass",
         bottom=False)
    prism(m, _circle(0.17, around(12)), top, top + 0.1, "Ruby", bottom=False)
    return m


def dial_proto(ri: float, ro: float) -> Mesh:
    """A chapter ring: dark enamel with 60 minute ticks and 12 batons of lume, gold edges. Faces +Z."""
    m = Mesh()
    band(m, _circle(ro, 240), _circle(ri, 240), 0.0, 0.12, "Enamel")
    band(m, _circle(ro + 0.18, 240), _circle(ro, 240), -0.05, 0.3, "Brass")
    band(m, _circle(ri, 240), _circle(ri - 0.12, 240), -0.05, 0.22, "Brass")
    w = ro - ri
    for k in range(60):
        a = 2 * math.pi * k / 60
        if k % 5:
            bar(m, a, ro - 0.2 * w, ro - 0.06 * w, 0.045 * w, 0.12, 0.15, "Lume")
        else:
            bar(m, a, ro - 0.5 * w, ro - 0.06 * w, 0.12 * w, 0.12, 0.17, "Lume")
    return m


def ring_gear_proto(ri: float, ro: float) -> Mesh:
    """A wheel with 144 teeth on the inside, which you fly through, with 12 blued screws."""
    m = Mesh()
    t = 144
    module = 2 * ri / t
    inner = teeth(t, module, inward=True, per_tooth=5, radius=ri)
    band(m, _circle(ro, len(inner)), inner, 0.0, 0.35, "Brass")
    for k in range(PORTAL_ORDER):
        a = 2 * math.pi * (k + 0.5) / PORTAL_ORDER
        c = np.array([math.cos(a), math.sin(a)]) * (ri + ro) / 2
        prism(m, _circle(0.22, 16, a), 0.35, 0.45, "Blued", offset=c)
    return m


def balance_proto(ri: float, ro: float) -> Mesh:
    """A balance wheel's rim with 12 gold timing screws on its outside, rocking back and forth."""
    m = Mesh()
    r1 = ri + 0.35 * (ro - ri)
    band(m, _circle(r1, 192), _circle(ri, 192), 0.0, 0.4, "Brass")
    for k in range(PORTAL_ORDER):
        a = 2 * math.pi * k / PORTAL_ORDER
        bar(m, a, r1 - 0.05, r1 + 0.5, 0.3, 0.05, 0.35, "Brass")
        bar(m, a, r1 + 0.5, r1 + 0.75, 0.45, 0.02, 0.38, "Blued")
    band(m, _circle(ro, 192), _circle(ro - 0.25, 192), -0.1, 0.1, "Seam")
    return m


def gate_proto(ri: float, ro: float) -> Mesh:
    """A hoop of 12 light arcs with gaps, flat to the camera."""
    m = Mesh()
    r = 0.5 * (ri + ro)
    for k in range(PORTAL_ORDER):
        a0 = 2 * math.pi * k / PORTAL_ORDER
        a = a0 + np.linspace(0.06, 2 * math.pi / PORTAL_ORDER - 0.06, 12)
        outer = np.stack([np.cos(a), np.sin(a)], -1) * (r + 0.18)
        inner = np.stack([np.cos(a), np.sin(a)], -1) * (r - 0.18)
        i = np.arange(len(a) - 1)
        co = np.concatenate([np.column_stack([outer, np.zeros(len(a))]), np.column_stack([inner, np.zeros(len(a))])])
        uv = np.concatenate([np.column_stack([np.linspace(0, 1, len(a)), np.ones(len(a))]),
                             np.column_stack([np.linspace(0, 1, len(a)), np.zeros(len(a))])])
        m.add(co, np.stack([i, i + 1, len(a) + i + 1, len(a) + i], 1), "Gate", uv)
    return m


def rosette_proto(ri: float, ro: float, k: int, mirror: bool, rng) -> Mesh:
    """Crystal petals between ri and ro, ``k`` wedges around, each mirrored when ``mirror`` (a kaleidoscope)."""
    m = Mesh()
    petals = []
    for _ in range(3):
        a0 = rng.uniform(0.1, 0.9) * math.pi / k
        r0, r1 = ri + rng.uniform(0.0, 0.3) * (ro - ri), ro - rng.uniform(0.0, 0.25) * (ro - ri)
        petals.append((a0, r0, r1, rng.uniform(0.05, 0.16) * (ro - ri), rng.uniform(0.0, 0.6)))
    for w in range(k):
        for flip in ((1, -1) if mirror else (1,)):
            for a0, r0, r1, wd, z in petals:
                a = 2 * math.pi * w / k + flip * a0
                d, n = np.array([math.cos(a), math.sin(a)]), np.array([-math.sin(a), math.cos(a)])
                mid = d * (r0 + r1) / 2
                pts = np.array([d * r0, mid + n * wd, d * r1, mid - n * wd])
                co = np.column_stack([pts, [z, z + 0.1, z, z + 0.1]])
                m.add(co, [[0, 1, 2], [0, 2, 3]], "Crystal", [[0, 0], [1, 0], [0, 1], [1, 0]])
    return m


def shard_proto(radius: float, depth: float, k: int, mirror: bool, density: float, rng) -> Mesh:
    """A slab of the kaleidoscope, ``depth`` long along +Z: crystal shards between 0.32 and 0.95 of the radius in one
    wedge, mirrored inside it when ``mirror``, repeated ``k`` times around."""
    m = Mesh()
    count = max(1, round(density * 26 / k * 6))
    half = math.pi / k if mirror else 2 * math.pi / k
    shards = []
    for _ in range(count):
        r = radius * math.sqrt(rng.uniform(0.32 ** 2, 0.95 ** 2))
        a, z = rng.uniform(0.0, half), rng.uniform(0.0, depth)
        size = radius * rng.uniform(0.04, 0.15)
        corners = []
        for j in range(3):
            t = 2 * math.pi * j / 3 + rng.uniform(-0.5, 0.5)
            corners.append((r + size * math.cos(t), a + size * math.sin(t) / max(r, 1e-3) * 0.8,
                            z + size * rng.uniform(-0.8, 0.8)))
        shards.append(corners)
    for w in range(k):
        for flip in ((1, -1) if mirror else (1,)):
            for corners in shards:
                co = [(r * math.cos(2 * math.pi * w / k + flip * a), r * math.sin(2 * math.pi * w / k + flip * a), z)
                      for r, a, z in corners]
                m.add(co, [[0, 1, 2]], "Crystal", [[0, 0], [1, 0], [0, 1]])
    return m


# ---- gear trains ---------------------------------------------------------------------------------------------------

def _wrap(d: np.ndarray, q: float) -> np.ndarray:
    return (d + q / 2) % q - q / 2


def gear_trains(shape: dict, q: float, half: float, rng) -> list[dict]:
    """Gear trains on one plate (x along the tunnel in [0, Q), y across in [-half, half]), ``gear_levels`` deep:
    chains of meshing wheels, each tangent to the last on its pitch circle and turned so their teeth interlock.
    Each chain turns with one channel: 0 tick (the kick's escapement), 1 drive (bass), 2 whirr (hats); ``mesh`` is
    the index of the gear a gear meshes with (None for the first of a chain)."""
    module = MODULE * shape["gear_size"] * shape["radius"] / 10
    sizes = [t for t in SIZES if module * t / 2 + 1.3 * module < half - 0.15]
    gears: list[dict] = []

    def free(x, y, ra, level, skip=None):
        for g in gears:
            if g["level"] != level or g is skip:
                continue
            if math.hypot(_wrap(x - g["x"], q), y - g["y"]) < ra + g["ra"] + 0.12:
                return False
        return True

    for level in range(int(shape["gear_levels"])):
        target, area, tries = shape["gears"] * 0.5 * q * 2 * half, 0.0, 0
        while area < target and tries < 600:
            tries += 1
            t = int(rng.choice(sizes, p=_weights(sizes)))
            rp = module * t / 2
            ra = rp + 1.2 * module
            x, y = rng.uniform(0, q), rng.uniform(-half + ra, half - ra) if half > ra else 0.0
            if not free(x, y, ra, level):
                continue
            chan = int(rng.choice(3, p=[0.45, 0.35, 0.2]))
            g = {"x": x, "y": y, "t": t, "rp": rp, "ra": ra, "level": level, "chan": chan, "dir": 1.0,
                 "phase": rng.uniform(0, 2 * math.pi / t), "mesh": None}
            gears.append(g)
            area += math.pi * rp * rp
            for _ in range(int(rng.integers(2, 7))):
                grown = False
                for _attempt in range(14):
                    t2 = int(rng.choice(sizes, p=_weights(sizes)))
                    rp2 = module * t2 / 2
                    ra2 = rp2 + 1.2 * module
                    a = rng.uniform(-math.pi, math.pi)
                    x2, y2 = g["x"] + (g["rp"] + rp2) * math.cos(a), g["y"] + (g["rp"] + rp2) * math.sin(a)
                    if abs(y2) > half - ra2 or not free(x2 % q, y2, ra2, level, skip=g):
                        continue
                    eps = (g["phase"] - a) % (2 * math.pi / g["t"])
                    phase = a + math.pi - eps * g["t"] / t2 - math.pi / t2
                    g = {"x": x2 % q, "y": y2, "t": t2, "rp": rp2, "ra": ra2, "level": level, "chan": chan,
                         "dir": -g["dir"], "phase": phase, "mesh": len(gears) - 1}
                    gears.append(g)
                    area += math.pi * rp2 * rp2
                    grown = True
                    break
                if not grown:
                    break
    return gears


def _weights(sizes: list[int]) -> np.ndarray:
    w = np.array([{12: 0.6, 24: 0.9, 36: 1.0, 48: 1.0, 60: 0.8, 72: 0.6}[t] for t in sizes])
    return w / w.sum()


# ---- the whole world ---------------------------------------------------------------------------------------------

def geometry(shape: dict) -> dict:
    """Walls, streaks, the spinners' points and their prototypes, as arrays, plus the periods."""
    rng = np.random.default_rng(int(shape["seed"]))
    p = path(shape)
    q, radius, sides, k = p["Q"], shape["radius"], int(shape["sides"]), fold(shape)
    half = radius * math.tan(math.pi / sides)
    module = MODULE * shape["gear_size"] * radius / 10
    protos: list[tuple[str, Mesh]] = []
    points = {"s": [], "phi": [], "kind": [], "lift": [], "plate_y": [], "proto": [], "phase": [], "wa": [], "wb": []}

    def proto(name: str, mesh: Mesh) -> int:
        protos.append((name, mesh))
        return len(protos) - 1

    # gears: one layout per plate of a wedge, the same on every wedge
    if shape["gears"] > 0 and shape["walls"] == "plates":
        gear_index = {t: proto(f"gear_{t:03d}", gear_proto(t, module)) for t in SIZES}
        per_wedge = sides // k
        for plate in range(per_wedge):
            for g in gear_trains(shape, q, half, rng):
                wa = [0.0, 0.0, 0.0]
                wa[g["chan"]] = g["dir"] * 2 * math.pi / g["t"]
                for w in range(k):
                    points["s"].append(g["x"])
                    points["phi"].append(_plate_angle(w * per_wedge + plate, sides))
                    points["kind"].append("gear")
                    points["lift"].append(LEVEL_Z + g["level"] * LEVEL_GAP)
                    points["plate_y"].append(g["y"])
                    points["proto"].append(gear_index[g["t"]])
                    points["phase"].append(g["phase"])
                    points["wa"].append(wa)
                    points["wb"].append([0.0, 0.0, 0.0])

    # portals: one every portal_every segments, alternating their turn
    ri, ro = shape["portal_inner"] * radius, 0.97 * radius
    if shape["portals"] != "none":
        kinds = {"clockwork": ("dial", "ring_gear", "balance")}.get(shape["portals"], (shape["portals"],))
        made = {}
        for name in kinds:
            if name == "dial":
                made[name] = proto("portal_dial", dial_proto(ri, ro))
            elif name == "ring_gear":
                made[name] = proto("portal_ring_gear", ring_gear_proto(ri, ro))
            elif name == "balance":
                made[name] = proto("portal_balance", balance_proto(ri, ro))
            elif name == "gate":
                made[name] = proto("portal_gate", gate_proto(ri, ro))
            elif name == "rosette":
                made[name] = proto("portal_rosette", rosette_proto(ri, ro, k, bool(shape["mirror"]), rng))
        step = shape["segment"] * shape["portal_every"]
        count = max(1, round(q / step))
        for j in range(count):
            name = kinds[j % len(kinds)]
            sign = 1.0 if j % 2 == 0 else -1.0
            points["s"].append(j * q / count)
            points["phi"].append(0.0)
            points["kind"].append("portal")
            points["lift"].append(0.0)
            points["plate_y"].append(0.0)
            points["proto"].append(made[name])
            points["phase"].append(0.0)
            if name == "ring_gear":
                points["wa"].append([sign * 2 * math.pi / 144, 0.0, 0.0])
                points["wb"].append([0.0, 0.0, 0.0])
            elif name == "balance":
                points["wa"].append([0.0, 0.0, 0.0])
                points["wb"].append([0.0, sign, 0.0])
            else:
                points["wa"].append([0.0, 0.0, 0.0])
                points["wb"].append([sign, 0.0, 0.0])

    # the kaleidoscope: slabs of mirrored crystal, one per segment, turning against their neighbours
    if shape["shards"] > 0:
        slabs = [proto(f"shards_{i}", shard_proto(radius, shape["segment"], k, bool(shape["mirror"]),
                                                  shape["shards"], rng)) for i in range(3)]
        count = max(1, round(q / shape["segment"]))
        for j in range(count):
            points["s"].append(j * q / count)
            points["phi"].append(0.0)
            points["kind"].append("slab")
            points["lift"].append(0.0)
            points["plate_y"].append(0.0)
            points["proto"].append(slabs[j % len(slabs)])
            points["phase"].append(0.0)
            points["wa"].append([0.0, 0.0, 0.0])
            points["wb"].append([(1.0, -2.0, 1.0, -1.0)[j % 4], 0.0, 0.0])

    spinners = _place(points, p, radius, q)
    walls = walls_mesh(shape, p, half, rng)
    streaks = streaks_mesh(shape, p, rng)
    return {"walls": walls.arrays(), "streaks": streaks.arrays(), "spinners": spinners,
            "protos": [(name, m.arrays()) for name, m in protos], "periods": periods(shape), "path": p,
            "fold": k}


def _plate_angle(i: int, sides: int) -> float:
    return -math.pi / 2 + 2 * math.pi * i / sides


def _place(points: dict, p: dict, radius: float, q: float) -> dict:
    """The spinners' points tiled along the path: location, rotation (gears face the axis, X along the tunnel;
    portals face the camera; slabs point down the tunnel), and their phases and channel weights."""
    if not points["s"]:
        return {"co": np.zeros((0, 3)), "rot": np.zeros((0, 4)), "proto": np.zeros(0, np.int64),
                "phase": np.zeros(0), "wa": np.zeros((0, 3)), "wb": np.zeros((0, 3))}
    s0 = np.asarray(points["s"])
    item, s = tiles(s0, q, extent=radius)
    f, up, right = frames(s, p)
    c = centre(s, p)
    phi = np.asarray(points["phi"])[item][:, None]
    kind = np.asarray(points["kind"])[item]
    out = np.cos(phi) * right + np.sin(phi) * up
    across = -np.sin(phi) * right + np.cos(phi) * up
    lift = np.asarray(points["lift"])[item][:, None]
    y = np.asarray(points["plate_y"])[item][:, None]
    gear = (kind == "gear")[:, None]
    z_axis = np.where(gear, -out, np.where((kind == "portal")[:, None], -f, f))
    x_axis = np.where(gear, f, right)
    co = c + np.where(gear, (radius - lift) * out - y * across, 0.0)
    y_axis = np.cross(z_axis, x_axis)
    return {"co": co, "rot": quaternions(x_axis, y_axis, z_axis), "proto": np.asarray(points["proto"])[item],
            "phase": np.asarray(points["phase"])[item], "wa": np.asarray(points["wa"])[item],
            "wb": np.asarray(points["wb"])[item]}


def walls_mesh(shape: dict, p: dict, half: float, rng) -> Mesh:
    """The static lining: ``plates`` (the movement's mainplate, one flat plate a side, with glowing seams, bridges
    across each plate and blued screws), ``grid`` (lines of light along and around the tunnel) or nothing."""
    m, q, radius, sides = Mesh(), p["Q"], shape["radius"], int(shape["sides"])
    s = np.arange(-BACK, q + VIEW_MAX + 2.0, 2.0)
    f, up, right = frames(s, p)
    c = centre(s, p)
    k = fold(shape)
    if shape["walls"] == "plates":
        for i in range(sides):
            phi = _plate_angle(i, sides)
            out = math.cos(phi) * right + math.sin(phi) * up
            across = -math.sin(phi) * right + math.cos(phi) * up
            _strip(m, c + radius * out, across, half, s, "Plate", metric=True)
            corner = phi + math.pi / sides
            out_c = math.cos(corner) * right + math.sin(corner) * up
            across_c = -math.sin(corner) * right + math.cos(corner) * up
            _strip(m, c + (radius / math.cos(math.pi / sides) - 0.12) * out_c, across_c, 0.07, s, "Seam")
        lift = LEVEL_Z + shape["gear_levels"] * LEVEL_GAP + 0.05
        per_wedge = sides // k
        for plate in range(per_wedge):
            spots = []
            for j in range(int(round(q / shape["segment"]))):
                spots.append(j * shape["segment"] + rng.uniform(0.2, 0.8) * shape["segment"])
            for w in range(k):
                i = w * per_wedge + plate
                for s0 in spots:
                    _bridge(m, p, i, sides, radius, half, s0, lift)
    elif shape["walls"] == "grid":
        lines = 2 * k * max(1, round(sides / k))
        for j in range(lines):
            phi = 2 * math.pi * j / lines
            out = math.cos(phi) * right + math.sin(phi) * up
            across = -math.sin(phi) * right + math.cos(phi) * up
            _strip(m, c + radius * out, across, 0.05, s, "Neon")
        ring_s = np.arange(-BACK, q + VIEW_MAX + 2.0, shape["segment"] / 4)
        rf, rup, rright = frames(ring_s, p)
        rc = centre(ring_s, p)
        a = np.linspace(0, 2 * math.pi, 97)
        for n in range(len(ring_s)):
            d = np.cos(a)[:, None] * rright[n] + np.sin(a)[:, None] * rup[n]
            pts = rc[n] + radius * d
            i = np.arange(len(a) - 1)
            co = np.concatenate([pts - 0.04 * rf[n], pts + 0.04 * rf[n]])
            uv = np.column_stack([np.full(2 * len(a), ring_s[n]), np.repeat([0.0, 1.0], len(a))])
            m.add(co, np.stack([i, i + 1, len(a) + i + 1, len(a) + i], 1), "Neon", uv)
    return m


def _strip(m: Mesh, mid: np.ndarray, across: np.ndarray, half: float, s: np.ndarray, mat: str, metric=False):
    """A ribbon along the path through ``mid``, ``half`` wide to each side along ``across``. Its UV runs along the
    path in units, and across it from 0 to 1, or in units too when ``metric`` (the plates' stripes)."""
    n = len(s)
    i = np.arange(n - 1)
    co = np.concatenate([mid - half * across, mid + half * across])
    v = np.repeat([-half, half], n) if metric else np.repeat([0.0, 1.0], n)
    uv = np.column_stack([np.tile(s, 2), v])
    m.add(co, np.stack([i, n + i, n + i + 1, i + 1], 1), mat, uv)


def _bridge(m: Mesh, p: dict, plate: int, sides: int, radius: float, half: float, s0: float, lift: float) -> None:
    """A bridge across a plate at ``s0``, ``lift`` above it, with a blued screw at each end; tiled every Q."""
    _, s = tiles(np.array([s0]), p["Q"], extent=2.0)
    f, up, right = frames(s, p)
    c = centre(s, p)
    phi = _plate_angle(plate, sides)
    out = math.cos(phi) * right + math.sin(phi) * up
    across = -math.sin(phi) * right + math.cos(phi) * up
    local = Mesh()
    bar(local, math.pi / 2, -0.94 * half, 0.94 * half, 0.9, 0.0, 0.22, "Steel")
    for y in (-0.8 * half, 0.8 * half):
        prism(local, _circle(0.24, 16), 0.22, 0.3, "Blued", offset=(0.0, y))
    a = local.arrays()
    for n in range(len(s)):
        x_axis, z_axis = f[n], -out[n]
        y_axis = np.cross(z_axis, x_axis)
        origin = c[n] + (radius - lift) * out[n]
        m.place(a, origin + a["co"][:, :1] * x_axis + a["co"][:, 1:2] * y_axis + a["co"][:, 2:3] * z_axis)


def streaks_mesh(shape: dict, p: dict, rng) -> Mesh:
    """Warp streaks: ``streaks`` ribbons per bend period, between 0.4 and 1.6 of the radius (``fold`` times around,
    mirrored when ``mirror``), each ``streak_length`` long along the path, its UV running 0 at its head (the end
    nearest the camera) to 1 at its tail."""
    m = Mesh()
    count = int(shape["streaks"])
    if count <= 0:
        return m
    q, radius, k = p["Q"], shape["radius"], fold(shape)
    mirror = bool(shape["mirror"])
    per = max(1, count // (k * (2 if mirror else 1)))
    wedge = 2 * math.pi / k
    s0 = rng.uniform(0, q, per)
    r = radius * np.sqrt(rng.uniform(0.4 ** 2, 1.6 ** 2, per))
    a = rng.uniform(0, wedge / 2 if mirror else wedge, per)
    hue = rng.uniform(0, 1, per)
    length = shape["streak_length"]
    angles = np.concatenate([w * wedge + f * a for w in range(k) for f in ((1, -1) if mirror else (1,))])
    s0 = np.tile(s0, len(angles) // per)
    r = np.tile(r, len(angles) // per)
    hue = np.tile(hue, len(angles) // per)
    item, s_start = tiles(s0, q, extent=length)
    steps = 7
    u = np.linspace(0, 1, steps)
    s = s_start[:, None] + u[None, :] * length                           # (n, steps)
    f, up, right = frames(s.ravel(), p)
    c = centre(s.ravel(), p)
    ang = angles[item].repeat(steps)
    rr = r[item].repeat(steps)[:, None]
    out = np.cos(ang)[:, None] * right + np.sin(ang)[:, None] * up
    across = -np.sin(ang)[:, None] * right + np.cos(ang)[:, None] * up
    width = 0.006 * radius + 0.004 * rr
    mid = c + rr * out
    n = len(item)
    co = np.concatenate([mid - width * across, mid + width * across])
    uv = np.column_stack([np.tile(u, n * 2), np.concatenate([hue[item].repeat(steps)] * 2)])
    base = np.arange(n)[:, None] * steps + np.arange(steps - 1)[None, :]
    base = base.ravel()
    total = n * steps
    m.add(co, np.stack([base, base + 1, total + base + 1, total + base], 1), "Streak", uv)
    return m


# ---- in Blender ----------------------------------------------------------------------------------------------------

def to_mesh(name: str, a: dict, materials: dict, attributes: dict | None = None):
    """A Blender mesh from ``Mesh.arrays()`` (or points only, with ``attributes``)."""
    import bpy

    me = bpy.data.meshes.new(name)
    nv, nf = len(a["co"]), len(a.get("sizes", []))
    me.vertices.add(nv)
    me.vertices.foreach_set("co", np.ascontiguousarray(a["co"], np.float32).ravel())
    if nf:
        sizes = a["sizes"].astype(np.int32)
        me.loops.add(int(sizes.sum()))
        me.polygons.add(nf)
        me.loops.foreach_set("vertex_index", a["faces"].astype(np.int32))
        me.polygons.foreach_set("loop_start", np.concatenate([[0], np.cumsum(sizes)[:-1]]).astype(np.int32))
        for mat in a["names"]:
            me.materials.append(materials[mat])
        me.polygons.foreach_set("material_index", a["mat"].astype(np.int32))
        uv = me.uv_layers.new(name="UVMap")
        uv.uv.foreach_set("vector", np.ascontiguousarray(a["uv"][a["faces"]], np.float32).ravel())
    for key, (kind, values) in (attributes or {}).items():
        at = me.attributes.new(key, kind, "POINT")
        field = "value" if kind in ("FLOAT", "INT", "QUATERNION") else "vector"
        at.data.foreach_set(field, np.ascontiguousarray(values, np.int32 if kind == "INT" else np.float32).ravel())
    me.update(calc_edges=True)
    return me
