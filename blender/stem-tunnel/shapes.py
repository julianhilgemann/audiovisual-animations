"""The stem tunnel's geometry: neon ribbons laid out in patterns on a cross-section, three layers deep.

    walls    the tunnel: K cells around (``symmetry``), one row of cells after another along -Z
    portals  rings you fly through, one every ``portal_every`` rows, between ``portal_inner`` and 0.97 of the radius
    outer    a shell around the walls, ``outer_size`` times the radius

Every pattern is a tile of polylines in the unit square (u around, w along the tunnel or out from the centre), cut
into ribbons as in the reference look (blender/audio-tunnel/neon_audio.py: `_Builder.ribbon`, `build_geometry`),
then laid onto a profile (circle, polygon, star, flower) of perimeter 2 pi R, so the cells keep their size on any
cross-section. Twist turns the cross-section along the tunnel and wave swells it; both are periodic along the
pattern, and ``periods()`` gives the distances and angles after which the picture repeats, which the look uses to
close the loop (stem_tunnel.py `motion`). With the defaults the meshes are the reference look's.

Everything but ``build`` is numpy only, so the tests check the geometry and its periods without Blender.
"""

import math
import random
from fractions import Fraction

import numpy as np

MAXLEN = 0.2                   # ribbons are cut into pieces at most this long, so they bend smoothly
ROWS_MIN = 48                  # rows of walls (the reference look's); more when rows are short
VIEW_MAX = 250.0               # the furthest the camera sees (look.toml view_far's maximum)
RANDOM_ROWS = 4                # a random tiling (truchet) repeats every this many rows
MAX_VERTS = 4_000_000
LAYERS = ("Tunnel_Walls", "Tunnel_Portals", "Tunnel_Outer")


# ---- patterns: (polyline, closed) in the unit square -------------------------------------------------------------

def _arc(cx, cy, r, a0, a1, n=13):
    return [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in np.linspace(a0, a1, n)]


def _square(cx, cy, h):
    return ([(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)], True)


_A = [([(0.0, 0.5), (0.1, 0.5), (0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.3, 0.9), (0.3, 0.3), (0.7, 0.3), (0.7, 0.7),
        (0.5, 0.7)], False),
      ([(0.9, 0.5), (1.0, 0.5)], False), ([(0.5, 0.9), (0.5, 1.0)], False), ([(0.5, 0.0), (0.5, 0.1)], False)]
_a, _b, _lo, _hi = 0.36, 0.64, 0.12, 0.88
_B = [([(_a, _lo), (_b, _lo), (_b, _a), (_hi, _a), (_hi, _b), (_b, _b), (_b, _hi), (_a, _hi), (_a, _b), (_lo, _b),
        (_lo, _a), (_a, _a)], True),
      ([(0.0, 0.5), (_lo, 0.5)], False), ([(_hi, 0.5), (1.0, 0.5)], False), ([(0.5, 0.0), (0.5, _lo)], False),
      ([(0.5, _hi), (0.5, 1.0)], False)]
for _sx in (0, 1):
    for _sy in (0, 1):
        _fx = (lambda u: u) if _sx == 0 else (lambda u: 1 - u)
        _fy = (lambda w: w) if _sy == 0 else (lambda w: 1 - w)
        _B.append(([(_fx(0.1), _fy(0.27)), (_fx(0.1), _fy(0.1)), (_fx(0.27), _fy(0.1))], False))
_H = 1 / 6
_TRUCHET = ([(_arc(0, 0, 0.5, 0, math.pi / 2), False), (_arc(1, 1, 0.5, math.pi, 1.5 * math.pi), False)],
            [(_arc(1, 0, 0.5, math.pi / 2, math.pi), False), (_arc(0, 1, 0.5, -math.pi / 2, 0), False)])
_CIRCUIT = [([(0.25, 0.0), (0.25, 0.3), (0.5, 0.55), (0.5, 0.75), (0.25, 1.0)], False),
            ([(0.75, 0.0), (0.75, 0.4), (0.9, 0.55), (0.9, 0.72)], False), _square(0.9, 0.8, 0.06),
            ([(0.0, 0.88), (0.12, 0.88), (0.2, 0.8)], False), _square(0.25, 0.75, 0.05)]

# pick: "one" tile everywhere, "checker" (i + j) % 2, "random" from the seed
WALLS = {
    "maze":     ("checker", [_A, _B]),
    "grid":     ("one", [[([(0.0, 0.0), (1.0, 0.0)], False), ([(0.0, 0.0), (0.0, 1.0)], False),
                          _square(0.5, 0.5, 0.25)]]),
    "diamonds": ("one", [[([(0.0, 0.0), (1.0, 1.0)], False), ([(0.0, 1.0), (1.0, 0.0)], False),
                          ([(0.5, 0.2), (0.8, 0.5), (0.5, 0.8), (0.2, 0.5)], True)]]),
    "chevrons": ("one", [[([(0.0, 0.15), (0.5, 0.45), (1.0, 0.15)], False),
                          ([(0.0, 0.6), (0.5, 0.9), (1.0, 0.6)], False)]]),
    "hexes":    ("one", [[([(0.0, _H), (0.5, 0.0), (1.0, _H)], False), ([(0.0, 0.5), (0.5, 4 * _H), (1.0, 0.5)], False),
                          ([(0.5, 4 * _H), (0.5, 1.0)], False), ([(0.0, _H), (0.0, 0.5)], False)]]),
    "circuit":  ("one", [_CIRCUIT]),
    "stripes":  ("one", [[([(0.0, 0.3), (1.0, 0.3)], False), ([(0.0, 0.7), (1.0, 0.7)], False)]]),
    "rails":    ("one", [[([(0.25, 0.0), (0.25, 1.0)], False), ([(0.75, 0.0), (0.75, 1.0)], False)]]),
    "zigzag":   ("one", [[([(0.0, 0.2), (0.25, 0.45), (0.5, 0.2), (0.75, 0.45), (1.0, 0.2)], False),
                          ([(0.0, 0.6), (0.25, 0.85), (0.5, 0.6), (0.75, 0.85), (1.0, 0.6)], False)]]),
    "truchet":  ("random", list(_TRUCHET)),
    "dots":     ("one", [[_square(0.25, 0.25, 0.06), _square(0.75, 0.75, 0.06)]]),
    "none":     ("one", [[]]),
}
# portals: u around, w from the inner edge (0) to the outer (1)
PORTALS = {
    "crenel": [([(0.0, 0.08), (1.0, 0.08)], False), ([(0.0, 0.92), (1.0, 0.92)], False),
               ([(0, 0.3), (0.125, 0.3), (0.125, 0.7), (0.375, 0.7), (0.375, 0.3), (0.625, 0.3), (0.625, 0.7),
                 (0.875, 0.7), (0.875, 0.3), (1.0, 0.3)], False),
               ([(0.0, 0.08), (0.0, 0.3)], False), ([(0.5, 0.08), (0.5, 0.3)], False), ([(0.25, 0.7), (0.25, 0.92)], False),
               ([(0.75, 0.7), (0.75, 0.92)], False)],
    "rings":  [([(0.0, 0.1), (1.0, 0.1)], False), ([(0.0, 0.9), (1.0, 0.9)], False)],
    "spokes": [([(0.0, 0.1), (1.0, 0.1)], False), ([(0.0, 0.9), (1.0, 0.9)], False)]
              + [([(u, 0.1), (u, 0.9)], False) for u in (0.0, 0.25, 0.5, 0.75)],
    "teeth":  [([(0.0, 0.92), (1.0, 0.92)], False),
               ([(k / 8, 0.25 if k % 2 == 0 else 0.75) for k in range(9)], False)],
    "triple": [([(0.0, w), (1.0, w)], False) for w in (0.15, 0.5, 0.85)],
    "frame":  [([(0.0, 0.9), (1.0, 0.9)], False)],
    "none":   [],
}
OUTER = {
    "ladder": [([(0.2, 0.0), (0.2, 1.0)], False), ([(0.8, 0.0), (0.8, 1.0)], False), ([(0.2, 0.5), (0.8, 0.5)], False)],
    "rails":  [([(0.2, 0.0), (0.2, 1.0)], False), ([(0.8, 0.0), (0.8, 1.0)], False)],
    "helix":  [([(0.0, 0.0), (1.0, 1.0)], False)],
    "grid":   [([(0.0, 0.0), (1.0, 0.0)], False), ([(0.0, 0.0), (0.0, 1.0)], False)],
    "dots":   [_square(0.5, 0.5, 0.06)],
    "none":   [],
}
DEFAULTS = {"profile": "circle", "sides": 6, "corner_round": 0.0, "profile_depth": 0.5, "profile_angle": 0.0,
            "radius": 12.0, "symmetry": 2, "cell_depth": 1.0, "line_width": 0.9359, "walls": "maze",
            "portals": "crenel", "portal_every": 1, "portal_inner": 0.56, "outer_pattern": "ladder",
            "outer_size": 2.2301, "seed": 1, "twist": 0.0, "wave": 0.0, "wave_count": 1}


# ---- profiles: the cross-section, perimeter 2 pi R ---------------------------------------------------------------

class Profile:
    """A closed cross-section of perimeter 2 pi R; ``at(t)`` is the point a fraction t of the way round (t = 0 on
    +X, counter-clockwise), ``symmetry`` its rotational symmetry (0: a circle, any angle)."""

    def __init__(self, shape: dict):
        self.R = float(shape["radius"])
        name, S = shape["profile"], int(shape["sides"])
        self.symmetry = 0 if name == "circle" else S
        self.points = None if name == "circle" else _outline(name, S, float(shape["corner_round"]),
                                                             float(shape["profile_depth"]))
        if self.points is not None:
            closed = np.vstack([self.points, self.points[:1]])
            seg = np.linalg.norm(np.diff(closed, axis=0), axis=1)
            self.points = self.points * (2 * math.pi * self.R / seg.sum())
            closed = np.vstack([self.points, self.points[:1]])
            self.cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(closed, axis=0), axis=1))])
            self.closed = closed

    def at(self, t):
        t = np.asarray(t, dtype=np.float64)
        if self.points is None:
            a = 2 * math.pi * t
            return self.R * np.cos(a), self.R * np.sin(a)
        s = np.mod(t, 1.0) * self.cum[-1]
        return np.interp(s, self.cum, self.closed[:, 0]), np.interp(s, self.cum, self.closed[:, 1])

    def inradius(self) -> float:
        """The closest the cross-section comes to the axis."""
        if self.points is None:
            return self.R
        a, b = self.closed[:-1], self.closed[1:]
        d = b - a
        k = np.clip(-(a * d).sum(1) / np.maximum((d * d).sum(1), 1e-12), 0, 1)
        return float(np.linalg.norm(a + k[:, None] * d, axis=1).min())


def _outline(name: str, S: int, rounding: float, depth: float) -> np.ndarray:
    """Dense points of a unit-sized outline with S-fold symmetry, starting on +X."""
    if name == "flower":
        th = np.linspace(0, 2 * math.pi, S * 96, endpoint=False)
        r = 1 + 0.4 * depth * np.cos(S * th)
        return np.stack([r * np.cos(th), r * np.sin(th)], axis=1)
    if name == "polygon":
        corners = [(math.cos(2 * math.pi * k / S), math.sin(2 * math.pi * k / S)) for k in range(S)]
    elif name == "star":
        inner = 1 - 0.8 * depth
        corners = [(r * math.cos(math.pi * k / S), r * math.sin(math.pi * k / S))
                   for k in range(2 * S) for r in [1.0 if k % 2 == 0 else inner]]
    else:
        raise ValueError(f"shape: unknown profile {name!r}")
    V = np.array(corners)
    if rounding <= 0:
        return V
    pts = []
    n = len(V)
    for k in range(n):                     # each corner becomes a quadratic curve, its middle sample on the corner's axis
        prev, cur, nxt = V[k - 1], V[k], V[(k + 1) % n]
        d = 0.5 * rounding * min(np.linalg.norm(cur - prev), np.linalg.norm(nxt - cur))
        p0 = cur + (prev - cur) / np.linalg.norm(prev - cur) * d
        p2 = cur + (nxt - cur) / np.linalg.norm(nxt - cur) * d
        s = np.linspace(0, 1, 15)[:, None]
        pts.append((1 - s) ** 2 * p0 + 2 * s * (1 - s) * cur + s ** 2 * p2)
    pts = np.vstack(pts)
    return np.roll(pts, -7, axis=0)        # start on the middle of corner 0, which lies on +X


# ---- periods -----------------------------------------------------------------------------------------------------

def _lcm(*fs: Fraction) -> Fraction:
    out = fs[0]
    for f in fs[1:]:
        out = Fraction(math.lcm(out.numerator * f.denominator, f.numerator * out.denominator),
                       out.denominator * f.denominator)
    return out


def _pattern_periods(pick: str, K: int) -> tuple[int, int]:
    """(cells around, rows along) after which a wall pattern repeats."""
    if pick == "checker":
        return (2 if K % 2 == 0 else K), 2
    if pick == "random":
        return K, RANDOM_ROWS
    return 1, 1


def twist_steps(shape: dict) -> Fraction:
    """The twist in cells per row, snapped to eighths."""
    return Fraction(round(float(shape["twist"]) * 8), 8)


def periods(shape: dict) -> dict:
    """When the picture repeats: ``travel`` along the tunnel (units), ``roll`` of the camera, ``portal`` and
    ``outer`` spin (radians); plus the row length and the rows of one wave."""
    shape = {**DEFAULTS, **shape}
    K = int(shape["symmetry"])
    row = float(shape["cell_depth"]) * 2 * math.pi * float(shape["radius"]) / K
    pick = WALLS[shape["walls"]][0]
    around_w, rows_w = _pattern_periods(pick, K) if shape["walls"] != "none" else (1, 1)
    rows = math.lcm(rows_w, int(shape["portal_every"]))
    S = 0 if shape["profile"] == "circle" else int(shape["sides"])

    def turn(f: Fraction) -> Fraction:     # a fraction of a turn that also maps the cross-section onto itself
        return f if S == 0 else _lcm(f, Fraction(1, S))

    walls, cell = turn(Fraction(around_w, K)), turn(Fraction(1, K))
    roll = _lcm(walls, cell)
    q = 1
    tw = twist_steps(shape)
    if tw:
        while (tw / K * q * rows / roll).denominator != 1:
            q += 1
            if q > 512:
                raise ValueError(f"shape: twist {float(tw)} never repeats with these cells")
    return {"travel": q * rows * row, "roll": 2 * math.pi * float(roll), "portal": 2 * math.pi * float(cell),
            "outer": 2 * math.pi * float(cell), "row": row, "wave_rows": rows}


# ---- geometry ------------------------------------------------------------------------------------------------------

def ribbon(pts, closed: bool, hw: float, maxlen: float = MAXLEN):
    """A polyline in the plane as a ribbon of half-width ``hw``: left and right edge points and the distance along
    it, cut every ``maxlen`` (the reference look's `_Builder.ribbon`, vectorised)."""
    P = np.asarray(pts, dtype=np.float64)
    keep = np.concatenate([[True], np.linalg.norm(np.diff(P, axis=0), axis=1) > 1e-12])
    P = P[keep]
    if closed:
        P = np.vstack([P, P[:1]])
    seg = np.diff(P, axis=0)
    length = np.linalg.norm(seg, axis=1)
    dirs = seg / length[:, None]
    if closed:
        d0, d1 = np.vstack([dirs[-1:], dirs]), np.vstack([dirs, dirs[:1]])
    else:
        d0, d1 = np.vstack([dirs[:1], dirs]), np.vstack([dirs, dirs[-1:]])
    n0 = np.stack([-d0[:, 1], d0[:, 0]], axis=1)
    n1 = np.stack([-d1[:, 1], d1[:, 0]], axis=1)
    mv = n0 + n1
    flat = np.linalg.norm(mv, axis=1) < 1e-6
    mv[flat] = n0[flat]
    mv /= np.linalg.norm(mv, axis=1)[:, None]
    offs = mv * (hw / np.maximum((mv * n0).sum(1), 0.25))[:, None]
    centre, off, along = [], [], []
    acc = 0.0
    m = len(P)
    for i in range(m - 1):
        steps = max(1, int(math.ceil(length[i] / maxlen)))
        t = np.arange(steps + (1 if i == m - 2 else 0)) / steps
        centre.append(P[i] + (P[i + 1] - P[i]) * t[:, None])
        off.append(offs[i] + (offs[i + 1] - offs[i]) * t[:, None])
        along.append(acc + length[i] * t)
        acc += length[i]
    c, o = np.vstack(centre), np.vstack(off)
    return c + o, c - o, np.concatenate(along)


class _Layer:
    """Collects ribbons as arrays: vertices, quads, and per-loop UVs (UVMap: along, across; Info: hue, strength)."""

    def __init__(self):
        self.co, self.quads, self.uv, self.info = [], [], [], []
        self.count = 0

    def add(self, left, right, along, hue: float, strength: float):
        """``left`` and ``right``: (instances, points, 3) arrays of the same ribbon laid out many times."""
        c, q, _ = left.shape
        self.co.append(np.concatenate([left, right], axis=1).reshape(-1, 3))
        i = np.arange(q - 1)
        quad = np.stack([i, q + i, q + i + 1, i + 1], axis=1)              # left i, right i, right i+1, left i+1
        base = self.count + 2 * q * np.arange(c)
        self.quads.append((base[:, None, None] + quad[None]).reshape(-1, 4))
        uv = np.stack([np.stack([along[:-1], np.zeros(q - 1)], 1), np.stack([along[:-1], np.ones(q - 1)], 1),
                       np.stack([along[1:], np.ones(q - 1)], 1), np.stack([along[1:], np.zeros(q - 1)], 1)], axis=1)
        self.uv.append(np.broadcast_to(uv, (c, q - 1, 4, 2)).reshape(-1, 2))
        self.info.append(np.broadcast_to([hue, strength], (c * (q - 1) * 4, 2)))
        self.count += 2 * q * c

    def arrays(self) -> dict:
        if not self.co:
            return {"co": np.zeros((0, 3)), "quads": np.zeros((0, 4), np.int64), "uv": np.zeros((0, 2)),
                    "info": np.zeros((0, 2))}
        return {"co": np.vstack(self.co), "quads": np.vstack(self.quads), "uv": np.vstack(self.uv),
                "info": np.vstack(self.info)}


def geometry(shape: dict) -> dict:
    """The three layers' meshes as arrays, plus the periods and sizes the look needs (see ``periods``)."""
    shape = {**DEFAULTS, **shape}
    prof = Profile(shape)
    per = periods(shape)
    K, R, lw = int(shape["symmetry"]), float(shape["radius"]), float(shape["line_width"])
    ARC, L = 2 * math.pi * R / K, per["row"]
    Z0 = 2 * L
    nrows = max(ROWS_MIN, int(math.ceil((per["travel"] + VIEW_MAX) / L)) + 4)
    turn0 = math.radians(float(shape["profile_angle"]))
    twist = float(twist_steps(shape)) / K * 2 * math.pi / L             # radians per unit along the tunnel
    wave, waves = float(shape["wave"]), int(shape["wave_count"])
    wave_len = per["wave_rows"] * L

    def place(t, scale, along, z):
        """Cross-section point a fraction t round, scaled, at distance ``along`` from the start, at height z."""
        x, y = prof.at(t)
        if wave:
            scale = scale * (1 + wave * np.sin(2 * math.pi * waves * along / wave_len))
        x, y = x * scale, y * scale
        angle = turn0 + twist * along
        if np.any(angle):
            ca, sa = np.cos(angle), np.sin(angle)
            x, y = x * ca - y * sa, x * sa + y * ca
        return np.stack(np.broadcast_arrays(x, y, z), axis=-1)

    layers = {name: _Layer() for name in LAYERS}
    pick, tiles = WALLS[shape["walls"]]
    rng = random.Random(int(shape["seed"]))
    table = [[rng.randrange(len(tiles)) for _ in range(RANDOM_ROWS)] for _ in range(K)]
    cells = {}
    for j in range(nrows):
        for i in range(K):
            k = 0 if pick == "one" else (i + j) % 2 if pick == "checker" else table[i][j % RANDOM_ROWS]
            cells.setdefault(k, []).append((i, j))
    for k_tile, where in cells.items():
        ij = np.array(where, dtype=np.float64)
        for k, (poly, closed) in enumerate(tiles[k_tile]):
            left, right, along = ribbon([(u * ARC, w * L) for u, w in poly], closed, 0.15 * lw)
            Rk = R - 0.004 * k
            out = []
            for edge in (left, right):
                X = ij[:, :1] * ARC + edge[None, :, 0]
                Y = ij[:, 1:] * L + edge[None, :, 1]
                out.append(place(X / (K * ARC), Rk / R, Y, Z0 - Y))
            layers["Tunnel_Walls"].add(out[0], out[1], along, 0.03 * k, 1.0)

    r_in, r_out = float(shape["portal_inner"]) * R, 0.97 * R
    arc_mid = 2 * math.pi * 0.5 * (r_in + r_out) / K
    every = int(shape["portal_every"])
    rows_p = np.arange(0, nrows + 1, every, dtype=np.float64)
    ij = np.array([(i, j) for j in rows_p for i in range(K)], dtype=np.float64)
    for k, (poly, closed) in enumerate(PORTALS[shape["portals"]]):
        left, right, along = ribbon([(u * arc_mid, r_in + w * (r_out - r_in)) for u, w in poly], closed, 0.10 * lw)
        out = []
        for edge in (left, right):
            X = ij[:, :1] * arc_mid + edge[None, :, 0]
            depth = ij[:, 1:] * L
            out.append(place(X / (K * arc_mid), edge[None, :, 1] / R, depth, Z0 - depth + 0.004 * k))
        layers["Tunnel_Portals"].add(out[0], out[1], along, 0.12 + 0.02 * k, 1.25)

    R2 = float(shape["outer_size"]) * R
    ARC2 = 2 * math.pi * R2 / K
    ij = np.array([(i, j) for j in range(nrows) for i in range(K)], dtype=np.float64)
    for poly, closed in OUTER[shape["outer_pattern"]]:
        left, right, along = ribbon([(u * ARC2, w * L) for u, w in poly], closed, 0.08 * lw)
        out = []
        for edge in (left, right):
            X = ij[:, :1] * ARC2 + edge[None, :, 0]
            Y = ij[:, 1:] * L + edge[None, :, 1]
            out.append(place(X / (K * ARC2), R2 / R, Y, Z0 - Y))
        layers["Tunnel_Outer"].add(out[0], out[1], along, 0.5, 0.45)

    meshes = {name: layer.arrays() for name, layer in layers.items()}
    verts = sum(len(m["co"]) for m in meshes.values())
    if verts > MAX_VERTS:
        raise ValueError(f"shape: {verts:,} vertices is too many (at most {MAX_VERTS:,}); fewer cells, longer rows "
                         f"or a smaller radius")
    inner = prof.inradius() * (1 - wave)
    return {"meshes": meshes, "periods": per, "inradius": inner, "rows": nrows, "verts": verts}


# ---- Blender -------------------------------------------------------------------------------------------------------

def build(shape: dict, material, collection) -> dict:
    """(Re)build the three tunnel meshes in place: an existing object keeps its drivers and properties and gets the
    new mesh; returns the periods and sizes (``geometry`` without the arrays)."""
    import bpy

    geo = geometry(shape)
    for name, m in geo["meshes"].items():
        me = bpy.data.meshes.new(name)
        nv, nf = len(m["co"]), len(m["quads"])
        me.vertices.add(nv)
        me.loops.add(4 * nf)
        me.polygons.add(nf)
        me.vertices.foreach_set("co", m["co"].astype(np.float32).ravel())
        me.polygons.foreach_set("loop_start", np.arange(0, 4 * nf, 4, dtype=np.int32))
        me.polygons.foreach_set("vertices", m["quads"].astype(np.int32).ravel())
        me.update(calc_edges=True)
        for layer, data in (("UVMap", m["uv"]), ("Info", m["info"])):
            me.uv_layers.new(name=layer).uv.foreach_set("vector", np.ascontiguousarray(data, np.float32).ravel())
        me.materials.append(material)
        ob = bpy.data.objects.get(name)
        if ob is None:
            ob = bpy.data.objects.new(name, me)
            collection.objects.link(ob)
        else:
            old, ob.data = ob.data, me
            if old.users == 0:
                bpy.data.meshes.remove(old)
        me.name = name
    return {k: v for k, v in geo.items() if k != "meshes"}
