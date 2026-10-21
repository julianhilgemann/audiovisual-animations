# =====================================================================
#  NEON AUDIO TUNNEL - live audio-reactive controls
#
#  WHERE:  3D Viewport > sidebar (press N) > "Neon" tab
#    Music ............... choose file / section, then "Apply music"
#    Look & presets ...... Lines / Kaleido / Both, presets, Randomize,
#                          save your own looks
#    Kaleido - ... ....... tunnel, fractal, shapes, colour (live sliders)
#    Lines tunnel shape .. sliders, then "Rebuild tunnel"
#    Live signals ........ what the analysis hears right now
#    ... reacts .......... how strongly the music moves things (live)
#
#  This text registers the panel when the .blend opens. Blender asks
#  first: click "Allow Execution" in the yellow bar. If the Neon tab is
#  still missing: Scripting tab > pick neon_audio.py > Run Script (Alt+P).
#  All slider values live as custom properties on the "NeonControls"
#  object, so they also work (and can be keyframed) without the panel.
# =====================================================================
import bpy, bmesh, aud, math, os, re, json, random
import numpy as np
from mathutils import Vector
from bpy.app.handlers import persistent

FPS = 60
TAU = 2*math.pi
COLL, CTRL, SIG = "NeonTunnel", "NeonControls", "AudioSignals"
TUNNEL_OBJS = ("Tunnel_Walls", "Tunnel_Portals", "Tunnel_Outer")
KSCREEN, KMAT, KCOLL = "Kaleido_Screen", "Kaleido", "KaleidoTunnel"
EMIT, FILL, HUE_D, FADE0, FADE1 = 10.0, 0.015, 14.0, 55.0, 110.0
RING_START, RING_GAIN, RING_W = 2.0, 22.0, 3.0
NSEG = 48
KLEVELS = 4
DEFAULT_AUDIO = "/Users/admin/Desktop/Mulero/03 - Oscar Mulero - Noches De Menta.flac"

# key: (default, min, max, label, tooltip)
P = {
    # --- music (need "Apply music") ---
    "audio_start":      (128.0, 0.0, 3600.0, "Start (s)", "Where in the track the clip starts, in seconds"),
    "audio_length":     (30.0, 2.0, 900.0, "Length (s)", "Clip length in seconds"),
    "kick_sensitivity": (1.0, 0.2, 3.0, "Kick sensitivity", "Higher = more hits are detected as kicks"),
    "kick_length":      (0.12, 0.03, 1.0, "Kick length (s)", "How long each kick hit lasts as a signal"),
    # --- kick ---
    "kick_flash":      (1.0, 0.0, 4.0, "Flash ring", "Brightness of the ring of light that races into the tunnel on every kick"),
    "kick_ring_speed": (3.0, 0.5, 12.0, "Ring speed", "How fast the kick ring travels away from you"),
    "kick_ring_decay": (0.4, 0.05, 2.0, "Ring fade (s)", "How long the kick ring stays visible"),
    "kick_glow":       (1.4, 0.0, 5.0, "Glow burst", "Extra brightness on each kick"),
    "kick_bloom":      (1.0, 0.0, 4.0, "Bloom burst", "Extra glow halo on each kick"),
    "kick_pump":       (0.12, 0.0, 0.6, "Pump", "Lines look: walls push outward. Kaleido: the fractal jumps open on each kick"),
    "kick_squeeze":    (0.10, 0.0, 0.5, "Portal squeeze", "Lines look: portal rings snap inward on each kick"),
    "kick_zoom":       (3.0, 0.0, 10.0, "Zoom punch", "Camera punch-zoom on each kick"),
    "kick_jolt":       (0.05, 0.0, 0.5, "Roll jolt", "The view twists a little on each kick"),
    "speed_kick":      (1.6, 0.0, 6.0, "Speed burst", "Forward speed burst on each kick"),
    # --- bass ---
    "bass_swell": (0.25, 0.0, 1.5, "Swell / twist", "Lines look: outer shell grows. Kaleido: the vortex twists with the bass"),
    "bass_wall":  (0.04, 0.0, 0.5, "Breathe", "Lines look: walls breathe. Kaleido: the fractal breathes with the bass"),
    "bass_haze":  (3.0, 0.0, 15.0, "Haze", "Faint background glow rises with the bass"),
    "roll_bass":  (1.1, 0.0, 5.0, "Roll by bass", "The view rotates faster when the bass is up"),
    # --- hats & mids ---
    "hats_sparkle":     (3.0, 0.0, 10.0, "Sparkle", "Hi-hats make a travelling light wave sparkle"),
    "outer_spin_hats":  (2.0, 0.0, 10.0, "Hats spin / morph", "Lines look: hi-hats spin the outer shell. Kaleido: hi-hats morph the fractal"),
    "portal_spin_mids": (1.0, 0.0, 5.0, "Mids spin / morph", "Lines look: mids spin the portals. Kaleido: mids (synths, snares) morph the fractal"),
    # --- loudness ---
    "glow_base":    (0.45, 0.0, 3.0, "Base glow", "Brightness when the track is quiet"),
    "energy_glow":  (0.8, 0.0, 4.0, "Loudness glow", "Brightness added by overall loudness"),
    "speed_energy": (0.9, 0.0, 4.0, "Loudness speed", "Forward speed added by overall loudness"),
    "color_energy": (1.2, 0.0, 5.0, "Colour cycling", "Colours cycle faster when the track is loud"),
    "color_shift":  (0.25, 0.0, 1.0, "Treble shifts palette", "Bright, trebly sounds shift the colour palette"),
    # --- base motion & look ---
    "speed":           (1.0, 0.0, 5.0, "Overall speed", "Multiplies all forward motion"),
    "speed_idle":      (0.25, 0.0, 3.0, "Idle speed", "Forward speed with no music"),
    "roll_idle":       (0.15, 0.0, 3.0, "Idle roll", "Rotation without bass"),
    "outer_spin_idle": (0.2, 0.0, 3.0, "Idle outer spin", "Lines look: outer shell spin without hi-hats"),
    "color_idle":      (0.2, 0.0, 3.0, "Idle colour cycling", "Colour cycling when the track is quiet"),
    "lens":            (16.0, 6.0, 50.0, "Lens (mm)", "Camera lens: lower = wider / zoomed out"),
    "bloom":           (1.0, 0.0, 3.0, "Bloom", "Overall glow halo around the lines"),
    # --- lines-tunnel shape (need "Rebuild tunnel") ---
    "shape_symmetry":   (1, 1, 8, "Symmetry", "How many times the pattern repeats around the tunnel"),
    "shape_radius":     (5.0, 2.0, 12.0, "Radius", "Tunnel radius"),
    "shape_line_width": (1.0, 0.3, 3.0, "Line width", "Thickness of the neon lines"),
    "shape_outer":      (1.32, 1.05, 2.5, "Outer shell size", "Outer shell radius relative to the tunnel"),
}

# --- kaleidoscope look (all live) ---
KPARAMS = {
    "k_segments":    (6, 1, 24, "Mirrors", "How many mirrored slices around the centre (kaleidoscope)"),
    "k_twist":       (0.0, -3.0, 3.0, "Twist", "Spiral twist - swirls the tunnel into a vortex"),
    "k_perspective": (0.0, 0.0, 1.0, "Perspective", "0 = endless fractal zoom, 1 = straight tube with depth"),
    "k_polygon":     (0.0, 0.0, 1.0, "Polygon tunnel", "0 = round tunnel, 1 = polygon tunnel (6 mirrors = hexagonal rings)"),
    "k_scale":       (1.0, 0.2, 5.0, "Pattern scale", "Size of the base pattern"),
    "k_around":      (1.0, 0.25, 4.0, "Repeat around", "How often the pattern repeats around the circle"),
    "k_density":     (1.0, 0.25, 4.0, "Repeat along", "How many pattern rings along the depth"),
    "k_frac_depth":  (2.0, 0.0, 4.0, "Fractal layers", "How many nested fractal layers (smooth: 1.5 = halfway)"),
    "k_frac_scale":  (1.8, 1.0, 3.0, "Layer zoom", "Size step between nested layers"),
    "k_frac_angle":  (0.4, -3.1416, 3.1416, "Layer rotation", "Rotation between nested layers - the main fractal shape knob"),
    "k_frac_offset": (0.35, 0.0, 1.5, "Layer offset", "Shift between nested layers - changes the fractal shape a lot"),
    "k_level_fade":  (0.85, 0.0, 1.5, "Layer brightness", "Brightness of the nested layers relative to the base"),
    "k_base_layer":  (1.0, 0.0, 1.0, "Base layer", "Brightness of the un-folded base pattern"),
    "k_lines":       (1.0, 0.0, 1.0, "Lines", "Straight crossing lines"),
    "k_hex":         (0.0, 0.0, 1.0, "Hexagons", "Hexagon outlines"),
    "k_rings":       (0.0, 0.0, 1.0, "Circles", "Circle outlines"),
    "k_dots":        (0.0, 0.0, 1.0, "Dots", "Grid of glowing dots"),
    "k_cells":       (0.0, 0.0, 1.0, "Circuit", "Circuit-board panels"),
    "k_line_width":  (0.04, 0.005, 0.3, "Line width", "Thickness of all lines"),
    "k_glow":        (0.5, 0.0, 2.0, "Halo", "Soft glow around the lines"),
    "k_tube":        (0.0, 0.0, 1.0, "Glossy tubes", "0 = flat neon lines, 1 = shiny 3D-looking tubes"),
    "k_hue":         (0.8, 0.0, 1.0, "Hue", "Main colour (0 red, .17 yellow, .33 green, .5 cyan, .67 blue, .8 purple)"),
    "k_hue_range":   (0.25, -1.0, 1.0, "Hue spread (layers)", "Colour difference between nested layers"),
    "k_hue_depth":   (0.05, -0.5, 0.5, "Hue along depth", "Colour change ring by ring - rainbow tunnel"),
    "k_sat":         (0.9, 0.0, 1.0, "Saturation", "Colour intensity"),
    "k_white":       (0.6, 0.0, 1.0, "White-hot cores", "Line centres burn white"),
    "k_bright":      (1.0, 0.0, 12.0, "Brightness", "Overall brightness"),
    "k_core_glow":   (1.0, 0.0, 10.0, "Centre light", "Bright light at the end of the tunnel"),
    "k_core_size":   (0.06, 0.005, 0.5, "Centre size", "Size of the centre light / dark core"),
}
P.update(KPARAMS)
KDEF = {k: p[0] for k, p in KPARAMS.items()}

PRESETS = {
    "Neon web": {},
    "Hex lattice": dict(k_polygon=1, k_lines=0.6, k_hex=1, k_frac_depth=2, k_frac_scale=2.0, k_frac_angle=0.0, k_frac_offset=0.3,
                        k_hue=0.0, k_hue_range=0.35, k_hue_depth=0.03, k_sat=1.0, k_white=0.15, k_glow=0.25, k_tube=0.5,
                        k_line_width=0.03, k_bright=1.2, k_core_glow=0.0, k_density=0.8),
    "Circuit": dict(k_cells=1, k_lines=0.4, k_frac_depth=0.0, k_scale=0.6, k_density=0.8, k_hue=0.32, k_hue_depth=0.08, k_white=0.15,
                    k_sat=1.0, k_glow=0.12, k_line_width=0.015, k_bright=1.6, k_perspective=0.85, k_segments=4, k_twist=0.5,
                    k_core_glow=0.0, k_around=2.0),
    "Dot tunnel": dict(k_lines=0, k_dots=1, k_segments=4, k_frac_depth=0, k_hue_depth=0.15, k_core_glow=4.0, k_core_size=0.1,
                       k_perspective=0.6, k_density=3.0, k_around=3.0, k_glow=0.5, k_white=0.2, k_sat=1.0, k_bright=1.3),
    "Purple vortex": dict(k_lines=1, k_rings=0, k_frac_depth=1.0, k_frac_angle=0.5, k_twist=1.6, k_segments=6, k_tube=1.0,
                          k_line_width=0.16, k_glow=0.25, k_white=0.3, k_hue=0.8, k_hue_range=-0.2, k_sat=0.9, k_bright=0.9,
                          k_core_glow=2.0, k_core_size=0.05),
    "Crystal star": dict(k_segments=6, k_lines=1, k_hex=0.5, k_frac_depth=3, k_frac_scale=1.6, k_frac_angle=0.25, k_frac_offset=0.25,
                         k_hue=0.5, k_hue_range=0.5, k_sat=1.0, k_white=0.3, k_glow=0.2, k_line_width=0.035, k_tube=0.6,
                         k_bright=1.1, k_core_glow=1.5, k_polygon=0.5),
}

MUSIC = ["audio_start", "audio_length", "kick_sensitivity", "kick_length"]
SHAPE = ["shape_symmetry", "shape_radius", "shape_line_width", "shape_outer"]
GROUPS = {
    "kick":   ["kick_flash", "kick_ring_speed", "kick_ring_decay", "kick_glow", "kick_bloom",
               "kick_pump", "kick_squeeze", "kick_zoom", "kick_jolt", "speed_kick"],
    "bass":   ["bass_swell", "bass_wall", "bass_haze", "roll_bass"],
    "hats":   ["hats_sparkle", "outer_spin_hats", "portal_spin_mids"],
    "energy": ["glow_base", "energy_glow", "speed_energy", "color_energy", "color_shift"],
    "base":   ["speed", "speed_idle", "roll_idle", "outer_spin_idle", "color_idle", "lens", "bloom"],
    "kpattern": ["k_segments", "k_twist", "k_perspective", "k_polygon", "k_scale", "k_around", "k_density",
                 "k_frac_depth", "k_frac_scale", "k_frac_angle", "k_frac_offset", "k_level_fade", "k_base_layer"],
    "kshapes":  ["k_lines", "k_hex", "k_rings", "k_dots", "k_cells", "k_line_width", "k_glow", "k_tube"],
    "kcolour":  ["k_hue", "k_hue_range", "k_hue_depth", "k_sat", "k_white", "k_bright", "k_core_glow", "k_core_size"],
}
LIVE = [k for g in ("kick", "bass", "hats", "energy", "base") for k in GROUPS[g]]
METERS = [("kick", "Kick"), ("bass", "Bass"), ("energy", "Loudness"), ("hats", "Hi-hats"),
          ("mids", "Mids"), ("bright", "Treble / brightness")]
SIG_KEYS = ["kick", "bass", "energy", "hats", "mids", "bright", "kick_age", "kick_last",
            "cum_energy", "cum_kick", "cum_bass", "cum_hats", "cum_mids"]
KAUD = ["A_KZ", "A_ROT", "A_HUE", "A_GAIN", "A_SPARK", "A_HAZE", "A_RPOS", "A_RAMP", "A_MORPH", "A_PUMP", "A_TWIST"]

# ============================ audio analysis ============================
_CACHE = {}

def _stft(x, sr, nfft=2048):
    hop = sr/FPS; n = int(len(x)/hop); centers = (np.arange(n)*hop).astype(np.int64)
    pad = nfft//2; xp = np.pad(x, (pad, pad)); win = np.hanning(nfft).astype(np.float32)
    M = np.empty((n, nfft//2+1), np.float32); ar = np.arange(nfft)
    for i0 in range(0, n, 2000):
        idx = centers[i0:i0+2000]
        M[i0:i0+len(idx)] = np.abs(np.fft.rfft(xp[idx[:, None]+ar[None, :]]*win, axis=1))
    return M, np.fft.rfftfreq(nfft, 1/sr)
def _band(M, f, lo, hi): m = (f >= lo) & (f < hi); return (M[:, m]**2).sum(1)
def _db(e): return 10*np.log10(e+1e-10)
def _follow(x, att, rel):
    a = math.exp(-1/(att*FPS)) if att > 0 else 0.0; r = math.exp(-1/(rel*FPS))
    y = np.empty(len(x), np.float32); p = 0.0
    for i in range(len(x)):
        v = float(x[i]); c = a if v > p else r; p = c*p+(1-c)*v; y[i] = p
    return y
def _norm(x, lo=5, hi=98):
    a, b = np.percentile(x, [lo, hi]); return np.clip((x-a)/(b-a+1e-9), 0, 1).astype(np.float32)
def _flux(Lv, lag=2):
    d = np.zeros_like(Lv); d[lag:] = Lv[lag:]-Lv[:-lag]; return np.maximum(d, 0)
def _movavg(x, n):
    n = max(1, int(n)); k = np.ones(n)/n
    return np.convolve(np.pad(x, (n//2, n-1-n//2), mode="edge"), k, mode="valid")
def _cum0(a): return np.concatenate([[0.0], np.cumsum(a[:-1])])

def analyze_full(path, sens, klen):
    key = (path, os.path.getmtime(path), round(float(sens), 4), round(float(klen), 4))
    if _CACHE.get("key") == key:
        return _CACHE["data"]
    snd = aud.Sound(path); sr = int(snd.specs[0])
    x = np.ascontiguousarray(snd.rechannel(1).data()[:, 0], dtype=np.float32)
    if len(x) < 2*sr:
        raise RuntimeError("Audio file is too short or could not be decoded")
    M, f = _stft(x, sr); n = len(M)
    Lk = _db(_band(M, f, 35, 120)); fk = _flux(Lk, 2)
    thr = (_movavg(fk, FPS)*1.6 + 1.5)/max(float(sens), 0.05); floor = np.percentile(Lk, 35)
    ev = []; last = -999
    for i in range(6, n-6):
        if fk[i] >= fk[i-6:i+7].max() and fk[i] > thr[i] and Lk[i] > floor and i-last >= 14:
            ev.append(i); last = i
    ev = np.array(ev, dtype=np.int64); imp = np.zeros(n, np.float32)
    if len(ev): imp[ev] = np.clip(fk[ev]/np.percentile(fk[ev], 90), 0.25, 1.0)
    dk = math.exp(-1/(max(float(klen), 0.01)*FPS))
    kick = np.zeros(n, np.float32); age = np.zeros(n, np.float32); lamp = np.zeros(n, np.float32)
    e = 0.0; a = 100000.0; la = 0.0
    for i in range(n):
        v = float(imp[i]); e = max(e*dk, v); kick[i] = e
        if v > 0: a = 0.0; la = v
        else: a = min(a+1.0, 100000.0)
        age[i] = a; lamp[i] = la
    bass = _norm(_follow(_db(_band(M, f, 40, 200)), 0.03, 0.30))
    energy = _norm(_follow(_movavg(_db(_band(M, f, 20, 16000)), 0.25*FPS), 0.15, 0.6))
    Lh = _db(_band(M, f, 6000, 16000)); hats = _norm(_follow(_flux(Lh, 1)*_norm(Lh, 20, 98), 0, 0.07), 5, 99)
    Lm = _db(_band(M, f, 1000, 4000)); mids = _norm(_follow(_flux(Lm, 2)*_norm(Lm, 20, 98), 0, 0.10), 5, 99)
    m = (f >= 100) & (f < 16000); Pw = M[:, m]**2
    cen = (Pw*f[m]).sum(1)/(Pw.sum(1)+1e-10)
    bright = _norm(_movavg(np.log2(cen+1), FPS), 5, 95)
    data = dict(kick=kick, bass=bass, energy=energy, hats=hats, mids=mids, bright=bright,
                kick_age=age, kick_last=lamp, events=ev)
    _CACHE.clear(); _CACHE["key"] = key; _CACHE["data"] = data
    return data

def best_start(full, length):
    """Most dynamic section: lots of kicks, big loudness swings, active hats."""
    n = len(full["kick"]); W = int(round(length*FPS))
    if W >= n: return 0.0
    starts = np.arange(0, n-W+1, FPS)
    def wsum(x):
        c = np.concatenate([[0.0], np.cumsum(np.asarray(x, np.float64))]); return c[starts+W]-c[starts]
    km = np.zeros(n); km[full["events"]] = 1
    em = wsum(full["energy"])/W; es = np.sqrt(np.maximum(wsum(np.asarray(full["energy"], np.float64)**2)/W-em**2, 0))
    sc = np.minimum(wsum(km)/(1.83*length), 1.0) + 2.5*es + 0.6*wsum(full["hats"])/W + 0.3*em
    return float(starts[int(np.argmax(sc))]/FPS)

def window(full, start, length):
    n = len(full["kick"]); N = max(FPS, min(int(round(length*FPS)), n))
    i0 = max(0, min(int(round(start*FPS)), n-N))
    S = {k: np.asarray(full[k][i0:i0+N], np.float64) for k in SIG_KEYS[:8]}
    for k in ("energy", "kick", "bass", "hats", "mids"):
        S["cum_"+k] = _cum0(S[k])
    ev = full["events"]; nk = int(((ev >= i0) & (ev < i0+N)).sum())
    return S, N, i0, nk

# ============================ scene plumbing ============================
def get_ctrl(): return bpy.data.objects.get(CTRL)

def ensure_controls():
    col = bpy.data.collections.get(COLL)
    ctrl = get_ctrl()
    if ctrl is None:
        ctrl = bpy.data.objects.new(CTRL, None)
        ctrl.empty_display_size = 0.2; ctrl.hide_render = True
        (col or bpy.context.scene.collection).objects.link(ctrl)
    if "audio_file" not in ctrl: ctrl["audio_file"] = DEFAULT_AUDIO
    if "_built_K" not in ctrl: ctrl["_built_K"] = 1
    if "_built_R" not in ctrl: ctrl["_built_R"] = 5.0
    if "look_mode" not in ctrl: ctrl["look_mode"] = 0
    for k, (dv, lo, hi, lab, tip) in P.items():
        if k not in ctrl: ctrl[k] = dv
        ui = ctrl.id_properties_ui(k)
        if isinstance(dv, int):
            ui.update(min=lo, max=hi, soft_min=lo, soft_max=hi, default=dv, description=tip)
        else:
            ui.update(min=lo, max=hi, soft_min=lo, soft_max=hi, default=dv, description=tip, precision=2)
    return ctrl

def bake(S, N):
    col = bpy.data.collections.get(COLL)
    sig = bpy.data.objects.get(SIG)
    if sig is None:
        sig = bpy.data.objects.new(SIG, None)
        sig.empty_display_type = "SPHERE"; sig.empty_display_size = 0.25; sig.hide_render = True
        (col or bpy.context.scene.collection).objects.link(sig)
    for k in list(sig.keys()):
        if k not in S: del sig[k]
    for k in S:
        if k not in sig: sig[k] = 0.0
    for k, _ in METERS:
        sig.id_properties_ui(k).update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0, precision=2)
    sig.animation_data_create()
    old = sig.animation_data.action
    act = bpy.data.actions.new("AudioSignals_new")
    sig.animation_data.action = act
    lin = bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["LINEAR"].value
    frames = np.arange(1, N+1, dtype=np.float32)
    for k, arr in S.items():
        fc = act.fcurve_ensure_for_datablock(sig, '["%s"]' % k)
        fc.keyframe_points.add(N)
        co = np.empty(2*N, np.float32); co[0::2] = frames; co[1::2] = arr
        fc.keyframe_points.foreach_set("co", co)
        fc.keyframe_points.foreach_set("handle_left", co); fc.keyframe_points.foreach_set("handle_right", co)
        fc.keyframe_points.foreach_set("interpolation", [lin]*N)
        fc.update()
    if old is not None and old.users == 0:
        bpy.data.actions.remove(old)
    act.name = "AudioSignals"
    return sig

def set_strip(scene, path, i0, N):
    se = scene.sequence_editor or scene.sequence_editor_create()
    for st in list(se.strips_all):
        if st.name.startswith("AudioTrack"): se.strips.remove(st)
    strip = se.strips.new_sound("AudioTrack", path, 1, 1)
    if hasattr(strip, "content_start"):
        strip.content_start = 1 - i0; strip.left_handle = 1; strip.right_handle = N + 1
    else:
        strip.frame_start = 1 - i0; strip.frame_final_start = 1; strip.frame_final_end = N + 1
    for s in list(bpy.data.sounds):
        if s.users == 0: bpy.data.sounds.remove(s)

def set_output(scene, path, start):
    r = scene.render; ims = r.image_settings
    ims.media_type = "VIDEO"; ims.file_format = "FFMPEG"
    r.ffmpeg.format = "MPEG4"; r.ffmpeg.codec = "H264"
    r.ffmpeg.constant_rate_factor = "HIGH"; r.ffmpeg.ffmpeg_preset = "GOOD"
    r.ffmpeg.audio_codec = "AAC"; r.ffmpeg.audio_bitrate = 320
    r.ffmpeg.audio_channels = "STEREO"; r.ffmpeg.audio_mixrate = 48000
    tag = re.sub(r"[^A-Za-z0-9]+", "_", os.path.splitext(os.path.basename(path))[0]).strip("_").lower()[:40]
    r.filepath = "//audio/neon_%s_%ds_" % (tag, int(start))
    r.use_compositing = True

def analyze_apply(scene, find_best=False):
    ctrl = ensure_controls()
    path = bpy.path.abspath(ctrl.get("audio_file", ""))
    if not os.path.isfile(path):
        raise RuntimeError("Audio file not found: " + path)
    full = analyze_full(path, ctrl["kick_sensitivity"], ctrl["kick_length"])
    if find_best:
        ctrl["audio_start"] = best_start(full, float(ctrl["audio_length"]))
    S, N, i0, nk = window(full, float(ctrl["audio_start"]), float(ctrl["audio_length"]))
    ctrl["audio_start"] = i0/FPS; ctrl["audio_length"] = N/FPS
    ctrl["_track_seconds"] = len(full["kick"])/FPS
    bake(S, N)
    scene.render.fps = FPS; scene.render.fps_base = 1.0
    scene.frame_start = 1; scene.frame_end = N
    cur = scene.frame_current if 1 <= scene.frame_current <= N else 1
    set_strip(scene, path, i0, N); scene.sync_mode = "AUDIO_SYNC"
    set_output(scene, path, i0/FPS)
    bad = setup_drivers(scene)
    scene.frame_set(cur)
    return {"kicks": nk, "seconds": N/FPS, "start": i0/FPS, "not_simple": bad}

def refresh(scene=None):
    scene = scene or bpy.context.scene
    ctrl = get_ctrl()
    if ctrl is not None: ctrl.update_tag()
    scene.frame_set(scene.frame_current)

# ============================ drivers ============================
def drive(owner, path, expr, index=-1):
    sig, ctrl = bpy.data.objects[SIG], bpy.data.objects[CTRL]
    try: owner.driver_remove(path, index)
    except Exception: pass
    fc = owner.driver_add(path, index) if index >= 0 else owner.driver_add(path)
    for mdf in list(fc.modifiers): fc.modifiers.remove(mdf)
    d = fc.driver; d.type = "SCRIPTED"
    for v in list(d.variables): d.variables.remove(v)
    for nm in sorted(set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", expr))):
        if nm in SIG_KEYS: tgt = sig
        elif nm in P: tgt = ctrl
        else: continue
        v = d.variables.new(); v.name = nm; v.type = "SINGLE_PROP"
        t = v.targets[0]; t.id_type = "OBJECT"; t.id = tgt; t.data_path = '["%s"]' % nm
    d.expression = expr
    return fc

def setup_drivers(scene):
    ctrl = bpy.data.objects[CTRL]
    K = int(ctrl.get("_built_K", 1)); R = float(ctrl.get("_built_R", 5.0))
    L = 2*math.pi*R/K; PER = 2*L; SB = 12*L/360; RB = 4*math.pi/360
    O = bpy.data.objects
    cam = O.get("NeonCam") or scene.camera
    fcs = []
    walls, portals, outer = O.get("Tunnel_Walls"), O.get("Tunnel_Portals"), O.get("Tunnel_Outer")
    travel = "%.8f*speed*(speed_idle*(frame-1) + speed_energy*cum_energy + speed_kick*cum_kick)" % SB
    fcs += [drive(cam, "location", "-fmod(%s, %.8f)" % (travel, PER), 2),
            drive(cam, "rotation_euler", "%.8f*(roll_idle*(frame-1) + roll_bass*cum_bass) + kick_jolt*kick" % RB, 2),
            drive(cam.data, "lens", "max(lens - kick_zoom*kick, 2)")]
    if walls and portals and outer:
        fcs += [drive(portals, "rotation_euler", "0.03*portal_spin_mids*cum_mids", 2),
                drive(outer, "rotation_euler", "-%.8f*(outer_spin_idle*(frame-1) + outer_spin_hats*cum_hats)" % RB, 2)]
        for i in (0, 1):
            fcs += [drive(walls, "scale", "1 + kick_pump*kick + bass_wall*bass", i),
                    drive(portals, "scale", "1 - kick_squeeze*kick", i),
                    drive(outer, "scale", "1 + bass_swell*bass", i)]
    ng = scene.compositing_node_group
    if ng:
        gl = sorted([nd for nd in ng.nodes if nd.bl_idname == "CompositorNodeGlare"], key=lambda nd: nd.name)
        if len(gl) >= 1: fcs.append(drive(gl[0].inputs["Strength"], "default_value", "0.42*bloom*(0.6 + 0.6*energy + 0.8*kick_bloom*kick)"))
        if len(gl) >= 2: fcs.append(drive(gl[1].inputs["Strength"], "default_value", "0.18*bloom*(0.5 + 0.8*energy + 1.2*kick_bloom*kick)"))
    fcs += build_material()
    kmat = bpy.data.materials.get(KMAT)
    if kmat is not None and kmat.node_tree is not None:
        knt = kmat.node_tree
        if knt.animation_data: knt.animation_data_clear()
        for k in KPARAMS:
            nd = knt.nodes.get("K_" + k)
            if nd: fcs.append(drive(nd.outputs[0], "default_value", k))
        aexpr = {
            "A_KZ": "0.015*speed*(speed_idle*(frame-1) + speed_energy*cum_energy + speed_kick*cum_kick)",
            "A_ROT": "%.8f*(roll_idle*(frame-1) + roll_bass*cum_bass) + kick_jolt*kick" % RB,
            "A_HUE": "%.8f*(color_idle*(frame-1) + color_energy*cum_energy) + color_shift*bright + 0.04*kick" % (1/360),
            "A_GAIN": "0.35 + 0.5*(glow_base + energy_glow*energy + kick_glow*kick)",
            "A_SPARK": "hats_sparkle*hats",
            "A_HAZE": "bass_haze*bass",
            "A_RPOS": "0.01*kick_age*kick_ring_speed",
            "A_RAMP": "kick_flash*kick_last*exp(-kick_age/(kick_ring_decay*60))",
            "A_MORPH": "0.002*portal_spin_mids*cum_mids + 0.0004*outer_spin_hats*cum_hats",
            "A_PUMP": "kick_pump*kick + bass_wall*bass",
            "A_TWIST": "0.5*bass_swell*bass",
        }
        for a, ex in aexpr.items():
            nd = knt.nodes.get(a)
            if nd: fcs.append(drive(nd.outputs[0], "default_value", ex))
    return [fc.data_path for fc in fcs if not fc.driver.is_simple_expression]

# ============================ lines-tunnel material ============================
def build_material():
    mat = bpy.data.materials.get("NeonLine") or bpy.data.materials.new("NeonLine")
    nt = mat.node_tree
    if nt.animation_data: nt.animation_data_clear()
    N_ = nt.nodes; LN = nt.links; N_.clear()
    def Mth(op, a, b=None):
        nd = N_.new("ShaderNodeMath"); nd.operation = op
        for idx, v in enumerate((a, b)):
            if v is None: continue
            if isinstance(v, (int, float)): nd.inputs[idx].default_value = v
            else: LN.new(v, nd.inputs[idx])
        return nd.outputs[0]
    def Val(name, label, dv=0.0):
        nd = N_.new("ShaderNodeValue"); nd.name = name; nd.label = label; nd.outputs[0].default_value = dv; return nd
    out = N_.new("ShaderNodeOutputMaterial"); emi = N_.new("ShaderNodeEmission")
    uvn = N_.new("ShaderNodeUVMap"); uvn.uv_map = "UVMap"; infn = N_.new("ShaderNodeUVMap"); infn.uv_map = "Info"
    sep = N_.new("ShaderNodeSeparateXYZ"); LN.new(uvn.outputs["UV"], sep.inputs[0])
    sepi = N_.new("ShaderNodeSeparateXYZ"); LN.new(infn.outputs["UV"], sepi.inputs[0])
    camd = N_.new("ShaderNodeCameraData")
    tval = Val("LoopTime", "Colour phase"); gain = Val("AU_Gain", "Audio: brightness", 1.0)
    hats_v = Val("AU_Hats", "Audio: sparkle"); hue_v = Val("AU_Hue", "Audio: hue offset")
    rpos_v = Val("AU_RingPos", "Audio: kick ring distance", 1000.0); ramp_v = Val("AU_RingAmp", "Audio: kick ring strength")
    bass_v = Val("AU_Bass", "Audio: haze")
    v = sep.outputs["Y"]; depth = camd.outputs["View Distance"]; t = tval.outputs[0]
    def line(c, w): return Mth("POWER", Mth("MAXIMUM", Mth("SUBTRACT", 1.0, Mth("DIVIDE", Mth("ABSOLUTE", Mth("SUBTRACT", v, c)), w)), 0.0), 1.6)
    e1 = line(0.1, 0.09); e2 = line(0.9, 0.09); core = line(0.5, 0.14)
    lines = Mth("ADD", Mth("ADD", e1, e2), Mth("MULTIPLY", core, 1.3))
    mask = Mth("ADD", lines, Mth("MULTIPLY", FILL, Mth("ADD", 1.0, bass_v.outputs[0])))
    hue = Mth("FRACT", Mth("ADD", Mth("ADD", Mth("ADD", Mth("ADD", t, Mth("DIVIDE", depth, HUE_D)), Mth("MULTIPLY", v, 0.18)), sepi.outputs["X"]), hue_v.outputs[0]))
    dd = Mth("DIVIDE", Mth("SUBTRACT", depth, rpos_v.outputs[0]), RING_W)
    ring = Mth("MULTIPLY", ramp_v.outputs[0], Mth("EXPONENT", Mth("MULTIPLY", Mth("MULTIPLY", dd, dd), -1.0)))
    sat = Mth("MULTIPLY", Mth("SUBTRACT", 1.0, Mth("MULTIPLY", core, 0.55)), Mth("SUBTRACT", 1.0, Mth("MULTIPLY", Mth("MINIMUM", ring, 1.0), 0.75)))
    comb = N_.new("ShaderNodeCombineColor"); comb.mode = "HSV"
    LN.new(hue, comb.inputs[0]); LN.new(sat, comb.inputs[1]); comb.inputs[2].default_value = 1.0
    fade = N_.new("ShaderNodeMapRange"); fade.interpolation_type = "SMOOTHSTEP"; fade.clamp = True
    LN.new(depth, fade.inputs["Value"])
    fade.inputs["From Min"].default_value = FADE0; fade.inputs["From Max"].default_value = FADE1
    fade.inputs["To Min"].default_value = 1.0; fade.inputs["To Max"].default_value = 0.0
    fo = fade.outputs["Result"]
    wave = Mth("SINE", Mth("MULTIPLY", Mth("SUBTRACT", Mth("DIVIDE", depth, 12.0), Mth("MULTIPLY", t, 6.0)), 2*math.pi))
    spark = Mth("MULTIPLY", hats_v.outputs[0], Mth("POWER", Mth("MAXIMUM", wave, 0.0), 8.0))
    pulse = Mth("ADD", Mth("ADD", 0.72, Mth("MULTIPLY", wave, 0.28)), spark)
    base = Mth("MULTIPLY", Mth("MULTIPLY", Mth("MULTIPLY", Mth("MULTIPLY", Mth("MULTIPLY", mask, EMIT), fo), sepi.outputs["Y"]), pulse), gain.outputs[0])
    flash = Mth("MULTIPLY", Mth("MULTIPLY", Mth("MULTIPLY", Mth("MULTIPLY", lines, ring), RING_GAIN), fo), sepi.outputs["Y"])
    LN.new(comb.outputs[0], emi.inputs["Color"]); LN.new(Mth("ADD", base, flash), emi.inputs["Strength"])
    LN.new(emi.outputs[0], out.inputs["Surface"])
    return [drive(tval.outputs[0], "default_value", "%.8f*(color_idle*(frame-1) + color_energy*cum_energy)" % (1/360)),
            drive(gain.outputs[0], "default_value", "glow_base + energy_glow*energy + kick_glow*kick"),
            drive(hue_v.outputs[0], "default_value", "color_shift*bright + 0.04*kick"),
            drive(hats_v.outputs[0], "default_value", "hats_sparkle*hats"),
            drive(bass_v.outputs[0], "default_value", "bass_haze*bass"),
            drive(rpos_v.outputs[0], "default_value", "2 + kick_age*kick_ring_speed"),
            drive(ramp_v.outputs[0], "default_value", "kick_flash*kick_last*exp(-kick_age/(kick_ring_decay*60))")]

# ============================ kaleidoscope material ============================
class _NB:
    """Tiny helper for building shader node graphs."""
    def __init__(self, nt):
        self.nt = nt; self.N = nt.nodes; self.L = nt.links; self.i = 0
    def new(self, t):
        n = self.N.new(t); n.location = ((self.i % 30)*190, -(self.i // 30)*230); self.i += 1; return n
    def _set(self, sock, v):
        if v is None: return
        if isinstance(v, (int, float)):
            dv = sock.default_value
            try:
                ln = len(dv); sock.default_value = tuple([float(v)]*ln)
            except TypeError:
                sock.default_value = float(v)
        elif isinstance(v, tuple):
            sock.default_value = v
        else:
            self.L.new(v, sock)
    def m(self, op, a, b=None, c=None):
        n = self.new("ShaderNodeMath"); n.operation = op
        for i, v in enumerate((a, b, c)): self._set(n.inputs[i], v)
        return n.outputs[0]
    def v(self, op, a, b=None, c=None):
        n = self.new("ShaderNodeVectorMath"); n.operation = op
        for i, val in enumerate((a, b, c)): self._set(n.inputs[i], val)
        return n.outputs["Value"] if op in ("LENGTH", "DOT_PRODUCT", "DISTANCE") else n.outputs["Vector"]
    def sep(self, vec):
        n = self.new("ShaderNodeSeparateXYZ"); self.L.new(vec, n.inputs[0]); return n.outputs[0], n.outputs[1], n.outputs[2]
    def comb(self, x, y, z=0.0):
        n = self.new("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)): self._set(n.inputs[i], v)
        return n.outputs[0]
    def rot(self, vec, ang):
        n = self.new("ShaderNodeVectorRotate"); n.rotation_type = "Z_AXIS"
        self.L.new(vec, n.inputs["Vector"]); self._set(n.inputs["Angle"], ang); return n.outputs[0]
    def hsv(self, h, s, v):
        n = self.new("ShaderNodeCombineColor"); n.mode = "HSV"
        for i, x in enumerate((h, s, v)): self._set(n.inputs[i], x)
        return n.outputs[0]
    def noise(self, vec):
        n = self.new("ShaderNodeTexWhiteNoise"); n.noise_dimensions = "3D"; self.L.new(vec, n.inputs["Vector"]); return n.outputs["Value"]
    def val(self, name, dv):
        n = self.new("ShaderNodeValue"); n.name = name; n.label = name; n.outputs[0].default_value = dv; return n.outputs[0]
    def smooth(self, x, a, b):
        n = self.new("ShaderNodeMapRange"); n.interpolation_type = "SMOOTHSTEP"; n.clamp = True
        self._set(n.inputs["Value"], x); self._set(n.inputs["From Min"], a); self._set(n.inputs["From Max"], b)
        n.inputs["To Min"].default_value = 0.0; n.inputs["To Max"].default_value = 1.0
        return n.outputs["Result"]

def _k_distance(B, q, w):
    """Distance to the nearest enabled shape (lines / hexagons / circles / dots / circuit)."""
    qx, qy, _ = B.sep(q)
    ax = B.m("ABSOLUTE", qx); ay = B.m("ABSOLUTE", qy)
    d_line = B.m("MINIMUM", ax, ay)
    hx = B.m("MAXIMUM", B.m("ADD", B.m("MULTIPLY", ax, 0.8660254), B.m("MULTIPLY", ay, 0.5)), ay)
    d_hex = B.m("ABSOLUTE", B.m("SUBTRACT", hx, 0.4))
    d_ring = B.m("ABSOLUTE", B.m("SUBTRACT", B.v("LENGTH", q), 0.4))
    dq = B.v("SUBTRACT", B.v("FRACTION", B.v("ADD", B.v("MULTIPLY", q, 3.0), (0.5, 0.5, 0.0))), (0.5, 0.5, 0.0))
    d_dot = B.m("DIVIDE", B.m("MAXIMUM", B.m("SUBTRACT", B.v("LENGTH", dq), 0.12), 0.0), 3.0)
    cq = B.v("MULTIPLY", q, 4.0)
    f = B.v("SUBTRACT", B.v("FRACTION", cq), (0.5, 0.5, 0.0))
    fx, fy, _ = B.sep(f)
    mx = B.m("MAXIMUM", B.m("ABSOLUTE", fx), B.m("ABSOLUTE", fy))
    rnd = B.noise(B.v("FLOOR", cq))
    inner = B.m("ABSOLUTE", B.m("SUBTRACT", mx, B.m("MULTIPLY", rnd, 0.45)))
    d_cell = B.m("DIVIDE", B.m("MINIMUM", B.m("SUBTRACT", 0.5, mx), inner), 4.0)
    d = None
    for dd, k in ((d_line, "lines"), (d_hex, "hex"), (d_ring, "rings"), (d_dot, "dots"), (d_cell, "cells")):
        de = B.m("ADD", B.m("DIVIDE", dd, w[k]), w["pen_" + k])
        d = de if d is None else B.m("MINIMUM", d, de)
    return d

def _k_glow(B, x, K):
    core = B.m("POWER", B.m("MAXIMUM", B.m("SUBTRACT", 1.0, x), 0.0), 1.5)
    hk = B.m("DIVIDE", -1.0, B.m("MAXIMUM", B.m("MULTIPLY", K["k_glow"], 1.5), 0.05))
    halo = B.m("EXPONENT", B.m("MULTIPLY", B.m("MINIMUM", x, 60.0), hk))
    tube = B.m("SQRT", B.m("MAXIMUM", B.m("SUBTRACT", 1.0, B.m("MULTIPLY", x, x)), 0.0))
    spec = B.m("POWER", tube, 14.0)
    gn = B.m("ADD", core, B.m("MULTIPLY", halo, 0.5))
    gt = B.m("ADD", B.m("ADD", B.m("MULTIPLY", tube, 0.35), B.m("MULTIPLY", spec, 1.5)), B.m("MULTIPLY", halo, 0.12))
    g = B.m("ADD", gn, B.m("MULTIPLY", B.m("SUBTRACT", gt, gn), K["k_tube"]))
    hot = B.m("MAXIMUM", B.m("POWER", core, 4.0), spec)
    return g, B.m("MULTIPLY", hot, K["k_white"])

def build_kaleido_material():
    mat = bpy.data.materials.get(KMAT) or bpy.data.materials.new(KMAT)
    if mat.node_tree is None: mat.use_nodes = True
    nt = mat.node_tree
    if nt.animation_data: nt.animation_data_clear()
    nt.nodes.clear()
    B = _NB(nt)
    K = {k: B.val("K_" + k, float(p[0])) for k, p in KPARAMS.items()}
    A = {a: B.val(a, 1.0 if a == "A_GAIN" else 0.0) for a in KAUD}
    tc = B.new("ShaderNodeTexCoord")
    px, py, _ = B.sep(tc.outputs["Object"])
    # screen position (y = -1..1 at a 16 mm lens) -> polar
    x = B.m("DIVIDE", px, 1.125); y = B.m("DIVIDE", py, 1.125)
    r = B.m("MAXIMUM", B.v("LENGTH", B.comb(x, y)), 1e-4)
    a0 = B.m("ARCTAN2", y, x)
    zlog = B.m("MULTIPLY", B.m("LOGARITHM", r, math.e), -1.0)
    zper = B.m("SUBTRACT", B.m("DIVIDE", 1.0, r), 1.0)
    zmap = B.m("ADD", zlog, B.m("MULTIPLY", B.m("SUBTRACT", zper, zlog), K["k_perspective"]))
    # twist + rotation, then kaleidoscope mirror fold
    twist = B.m("ADD", K["k_twist"], A["A_TWIST"])
    a = B.m("ADD", B.m("ADD", a0, A["A_ROT"]), B.m("MULTIPLY", twist, zmap))
    seg = B.m("DIVIDE", TAU, B.m("MAXIMUM", K["k_segments"], 1.0))
    half = B.m("MULTIPLY", seg, 0.5)
    am = B.m("ABSOLUTE", B.m("SUBTRACT", B.m("FLOORED_MODULO", a, seg), half))
    U = B.m("DIVIDE", am, half)
    # polygon tunnel: effective radius r*cos(angle) gives straight-edged rings
    re_ = B.m("MULTIPLY", r, B.m("ADD", 1.0, B.m("MULTIPLY", K["k_polygon"], B.m("SUBTRACT", B.m("MAXIMUM", B.m("COSINE", am), 0.05), 1.0))))
    zl2 = B.m("MULTIPLY", B.m("LOGARITHM", re_, math.e), -1.0)
    zp2 = B.m("SUBTRACT", B.m("DIVIDE", 1.0, re_), 1.0)
    zv = B.m("ADD", zl2, B.m("MULTIPLY", B.m("SUBTRACT", zp2, zl2), K["k_perspective"]))
    V = B.m("MULTIPLY", B.m("ADD", B.m("DIVIDE", zv, half), A["A_KZ"]), K["k_density"])
    qx0 = B.m("SUBTRACT", B.m("FRACT", B.m("ADD", B.m("MULTIPLY", U, K["k_around"]), 0.5)), 0.5)
    q = B.v("MULTIPLY", B.comb(qx0, B.m("SUBTRACT", B.m("FRACT", V), 0.5)), K["k_scale"])
    w = {}
    for k in ("lines", "hex", "rings", "dots", "cells"):
        w[k] = B.m("MAXIMUM", K["k_" + k], 0.001)
        inv = B.m("SUBTRACT", 1.0, K["k_" + k])
        w["pen_" + k] = B.m("MULTIPLY", B.m("MULTIPLY", B.m("MULTIPLY", inv, inv), inv), 3.0)
    off = B.m("MULTIPLY", K["k_frac_offset"], B.m("ADD", 1.0, B.m("MULTIPLY", A["A_PUMP"], 2.0)))
    offv = B.comb(off, B.m("MULTIPLY", off, 0.75))
    ang = B.m("ADD", K["k_frac_angle"], A["A_MORPH"])
    FS = K["k_frac_scale"]
    total = None
    for i in range(KLEVELS + 1):
        if i > 0:   # fractal fold: mirror, shift, rotate, zoom
            q = B.v("MULTIPLY", B.rot(B.v("SUBTRACT", B.v("ABSOLUTE", q), offv), ang), FS)
        d = _k_distance(B, q, w)
        width = K["k_line_width"] if i == 0 else B.m("MULTIPLY", K["k_line_width"], B.m("POWER", FS, float(i)))
        g, white = _k_glow(B, B.m("DIVIDE", d, width), K)
        hue = B.m("FRACT", B.m("ADD", B.m("ADD", B.m("ADD", K["k_hue"], A["A_HUE"]), B.m("MULTIPLY", K["k_hue_range"], i/KLEVELS)), B.m("MULTIPLY", K["k_hue_depth"], V)))
        sat = B.m("MULTIPLY", K["k_sat"], B.m("SUBTRACT", 1.0, B.m("MINIMUM", white, 1.0)))
        if i == 0:
            W = K["k_base_layer"]
        else:
            W = B.m("MULTIPLY", B.m("MINIMUM", B.m("MAXIMUM", B.m("SUBTRACT", K["k_frac_depth"], float(i - 1)), 0.0), 1.0), B.m("POWER", K["k_level_fade"], float(i)))
        col = B.v("MULTIPLY", B.hsv(hue, sat, 1.0), B.m("MULTIPLY", g, W))
        total = col if total is None else B.v("ADD", total, col)
    CS = K["k_core_size"]
    cfade = B.smooth(r, B.m("MULTIPLY", CS, 0.5), B.m("MULTIPLY", CS, 2.5))
    rz = B.m("DIVIDE", B.m("SUBTRACT", zmap, A["A_RPOS"]), 0.3)
    flash = B.m("ADD", 1.0, B.m("MULTIPLY", B.m("MULTIPLY", A["A_RAMP"], 1.2), B.m("EXPONENT", B.m("MULTIPLY", B.m("MULTIPLY", rz, rz), -1.0))))
    wave = B.m("POWER", B.m("MAXIMUM", B.m("SINE", B.m("MULTIPLY", B.m("SUBTRACT", B.m("MULTIPLY", V, 0.5), B.m("MULTIPLY", A["A_HUE"], 4.0)), TAU)), 0.0), 8.0)
    spark = B.m("ADD", 1.0, B.m("MULTIPLY", A["A_SPARK"], wave))
    norm = B.m("DIVIDE", 1.0, B.m("ADD", 1.0, B.m("MULTIPLY", B.m("MULTIPLY", K["k_frac_depth"], K["k_level_fade"]), 0.6)))
    gain = B.m("MULTIPLY", B.m("MULTIPLY", B.m("MULTIPLY", B.m("MULTIPLY", B.m("MULTIPLY", A["A_GAIN"], K["k_bright"]), flash), spark), cfade), norm)
    total = B.v("MULTIPLY", total, gain)
    hue0 = B.m("FRACT", B.m("ADD", K["k_hue"], A["A_HUE"]))
    core = B.v("MULTIPLY", B.hsv(hue0, B.m("MULTIPLY", K["k_sat"], 0.5), 1.0), B.m("MULTIPLY", K["k_core_glow"], B.m("EXPONENT", B.m("DIVIDE", B.m("MULTIPLY", r, -1.0), CS))))
    haze = B.v("MULTIPLY", B.hsv(B.m("FRACT", B.m("ADD", hue0, 0.5)), K["k_sat"], 1.0), B.m("MULTIPLY", B.m("MULTIPLY", A["A_HAZE"], 0.03), cfade))
    colr = B.v("ADD", B.v("ADD", total, core), haze)
    emi = B.new("ShaderNodeEmission"); B.L.new(colr, emi.inputs["Color"]); emi.inputs["Strength"].default_value = 1.0
    out = B.new("ShaderNodeOutputMaterial"); B.L.new(emi.outputs[0], out.inputs["Surface"])
    return mat

def ensure_kaleido(scene, rebuild_material=False):
    """Screen-filling plane parked far behind the lines tunnel, parented to the camera."""
    cam = bpy.data.objects.get("NeonCam") or scene.camera
    col = bpy.data.collections.get(KCOLL)
    if col is None:
        col = bpy.data.collections.new(KCOLL); scene.collection.children.link(col)
    ob = bpy.data.objects.get(KSCREEN)
    if ob is None:
        S = 6.0
        me = bpy.data.meshes.new(KSCREEN)
        me.from_pydata([(-S, -S, 0), (S, -S, 0), (S, S, 0), (-S, S, 0)], [], [(0, 1, 2, 3)])
        ob = bpy.data.objects.new(KSCREEN, me); col.objects.link(ob)
    ob.parent = cam; ob.matrix_parent_inverse.identity()
    ob.location = (0.0, 0.0, -400.0); ob.rotation_euler = (0.0, 0.0, 0.0); ob.scale = (400.0, 400.0, 400.0)
    mat = bpy.data.materials.get(KMAT)
    if mat is None or rebuild_material:
        mat = build_kaleido_material()
    if not ob.data.materials or ob.data.materials[0] != mat:
        ob.data.materials.clear(); ob.data.materials.append(mat)
    return ob

def apply_mode(mode):
    ctrl = ensure_controls(); ctrl["look_mode"] = int(mode)
    lines = mode in (0, 2); kal = mode in (1, 2)
    for n in TUNNEL_OBJS:
        o = bpy.data.objects.get(n)
        if o: o.hide_viewport = not lines; o.hide_render = not lines
    ks = bpy.data.objects.get(KSCREEN)
    if ks: ks.hide_viewport = not kal; ks.hide_render = not kal

def apply_look(values, base_defaults=True):
    ctrl = ensure_controls()
    vals = dict(KDEF) if base_defaults else {}
    vals.update(values)
    for k, v in vals.items():
        if k not in KPARAMS: continue
        lo, hi = KPARAMS[k][1], KPARAMS[k][2]
        if isinstance(KPARAMS[k][0], int): ctrl[k] = int(min(max(round(v), lo), hi))
        else: ctrl[k] = float(min(max(v, lo), hi))
    refresh()

def random_look():
    Rn = random.Random()
    v = dict(KDEF)
    v["k_segments"] = Rn.choice([3, 4, 5, 6, 6, 8, 8, 10, 12])
    v["k_twist"] = Rn.uniform(-1.6, 1.6) if Rn.random() < 0.5 else 0.0
    v["k_perspective"] = Rn.choice([0.0, 0.0, 0.3, 0.6, 0.85])
    v["k_polygon"] = 1.0 if Rn.random() < 0.35 else 0.0
    v["k_scale"] = Rn.uniform(0.5, 1.5); v["k_around"] = Rn.choice([1, 1, 1, 2, 3]); v["k_density"] = Rn.uniform(0.6, 2.0)
    v["k_frac_depth"] = Rn.uniform(0.0, 3.5); v["k_frac_scale"] = Rn.uniform(1.4, 2.4); v["k_frac_angle"] = Rn.uniform(-1.5, 1.5)
    v["k_frac_offset"] = Rn.uniform(0.15, 0.6); v["k_level_fade"] = Rn.uniform(0.6, 1.0)
    shapes = ["k_lines", "k_hex", "k_rings", "k_dots", "k_cells"]
    for s in shapes: v[s] = 0.0
    a = Rn.choice(shapes); v[a] = 1.0
    if Rn.random() < 0.6:
        v[Rn.choice([s for s in shapes if s != a])] = Rn.uniform(0.3, 0.8)
    v["k_line_width"] = Rn.uniform(0.015, 0.06); v["k_glow"] = Rn.uniform(0.1, 0.6)
    v["k_tube"] = Rn.uniform(0.5, 1.0) if Rn.random() < 0.3 else 0.0
    v["k_hue"] = Rn.random(); v["k_hue_range"] = Rn.uniform(-0.6, 0.6)
    v["k_hue_depth"] = 0.0 if Rn.random() < 0.5 else Rn.uniform(-0.15, 0.15)
    v["k_sat"] = Rn.uniform(0.85, 1.0); v["k_white"] = Rn.uniform(0.1, 0.5); v["k_bright"] = Rn.uniform(1.0, 1.3)
    v["k_core_glow"] = Rn.uniform(0.0, 3.0); v["k_core_size"] = Rn.uniform(0.03, 0.12)
    if v["k_dots"] >= 1.0: v["k_white"] = 0.2
    return v

def saved_looks(ctrl):
    try: return json.loads(ctrl.get("_looks", "{}"))
    except Exception: return {}

# ============================ lines-tunnel geometry ============================
def _perp(d): return Vector((-d.y, d.x))

class _Builder:
    def __init__(self, name, col):
        self.name = name; self.col = col; self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap"); self.info = self.bm.loops.layers.uv.new("Info")
    def ribbon(self, pts, closed, hw, mapper, hue_off, strength, maxlen=0.2):
        P_ = [Vector(p) for p in pts]
        if closed: P_.append(P_[0].copy())
        m = len(P_); offs = []
        for i in range(m):
            if closed:
                prev = P_[i-1] if i > 0 else P_[-2]; nxt = P_[i+1] if i < m-1 else P_[1]
                d0 = (P_[i]-prev).normalized(); d1 = (nxt-P_[i]).normalized()
            elif i == 0: d0 = d1 = (P_[1]-P_[0]).normalized()
            elif i == m-1: d0 = d1 = (P_[-1]-P_[-2]).normalized()
            else: d0 = (P_[i]-P_[i-1]).normalized(); d1 = (P_[i+1]-P_[i]).normalized()
            n0, n1 = _perp(d0), _perp(d1); mv = n0 + n1
            if mv.length < 1e-6: mv = n0.copy()
            mv.normalize(); offs.append(mv * (hw / max(mv.dot(n0), 0.25)))
        Ls, Rs, Us = [], [], []; acc = 0.0
        for i in range(m-1):
            a, b = P_[i], P_[i+1]; seg = (b-a).length
            steps = max(1, int(math.ceil(seg/maxlen)))
            for s in range(steps + (1 if i == m-2 else 0)):
                t = s/steps; c = a.lerp(b, t); o = offs[i].lerp(offs[i+1], t)
                Ls.append(c+o); Rs.append(c-o); Us.append(acc + seg*t)
            acc += seg
        bm = self.bm
        lv = [bm.verts.new(mapper(p.x, p.y)) for p in Ls]; rv = [bm.verts.new(mapper(p.x, p.y)) for p in Rs]
        for i in range(len(lv)-1):
            f = bm.faces.new((lv[i], rv[i], rv[i+1], lv[i+1]))
            for loop, uvv in zip(f.loops, ((Us[i], 0.0), (Us[i], 1.0), (Us[i+1], 1.0), (Us[i+1], 0.0))):
                loop[self.uv].uv = uvv; loop[self.info].uv = (hue_off, strength)
    def finish(self, mat):
        me = bpy.data.meshes.new(self.name); self.bm.to_mesh(me); self.bm.free()
        me.materials.append(mat); ob = bpy.data.objects.new(self.name, me); self.col.objects.link(ob); return ob

def _scale(poly, sx, sy, ox, oy): return [((ox+u)*sx, (oy+w)*sy) for (u, w) in poly]

_A = [([(0.0,0.5),(0.1,0.5),(0.1,0.1),(0.9,0.1),(0.9,0.9),(0.3,0.9),(0.3,0.3),(0.7,0.3),(0.7,0.7),(0.5,0.7)], False),
      ([(0.9,0.5),(1.0,0.5)], False), ([(0.5,0.9),(0.5,1.0)], False), ([(0.5,0.0),(0.5,0.1)], False)]
_a, _b, _lo, _hi = 0.36, 0.64, 0.12, 0.88
_B = [([(_a,_lo),(_b,_lo),(_b,_a),(_hi,_a),(_hi,_b),(_b,_b),(_b,_hi),(_a,_hi),(_a,_b),(_lo,_b),(_lo,_a),(_a,_a)], True),
      ([(0.0,0.5),(_lo,0.5)], False), ([(_hi,0.5),(1.0,0.5)], False), ([(0.5,0.0),(0.5,_lo)], False), ([(0.5,_hi),(0.5,1.0)], False)]
for _sx in (0, 1):
    for _sy in (0, 1):
        _fx = (lambda u: u) if _sx == 0 else (lambda u: 1-u); _fy = (lambda w: w) if _sy == 0 else (lambda w: 1-w)
        _B.append(([(_fx(0.1), _fy(0.27)), (_fx(0.1), _fy(0.1)), (_fx(0.27), _fy(0.1))], False))
_PORTAL = [([(0.0,0.08),(1.0,0.08)], False), ([(0.0,0.92),(1.0,0.92)], False),
           ([(0,0.3),(0.125,0.3),(0.125,0.7),(0.375,0.7),(0.375,0.3),(0.625,0.3),(0.625,0.7),(0.875,0.7),(0.875,0.3),(1.0,0.3)], False),
           ([(0.0,0.08),(0.0,0.3)], False), ([(0.5,0.08),(0.5,0.3)], False), ([(0.25,0.7),(0.25,0.92)], False), ([(0.75,0.7),(0.75,0.92)], False)]
_OUTER = [([(0.2,0.0),(0.2,1.0)], False), ([(0.8,0.0),(0.8,1.0)], False), ([(0.2,0.5),(0.8,0.5)], False)]

def build_geometry(K, R, lw, outer_ratio):
    K = max(1, int(K)); ARC = 2*math.pi*R/K; L = ARC; Z0 = 2*L
    col = bpy.data.collections.get(COLL)
    mat = bpy.data.materials.get("NeonLine") or bpy.data.materials.new("NeonLine")
    for name in TUNNEL_OBJS:
        ob = bpy.data.objects.get(name)
        if ob:
            me = ob.data; bpy.data.objects.remove(ob, do_unlink=True)
            if me is not None and me.users == 0: bpy.data.meshes.remove(me)
    hw_wall, hw_portal, hw_outer = 0.15*lw, 0.10*lw, 0.08*lw
    walls = _Builder("Tunnel_Walls", col)
    for j in range(NSEG):
        for i in range(K):
            for k, (poly, closed) in enumerate(_A if (i + j) % 2 == 0 else _B):
                Rk = R - 0.004*k
                walls.ribbon(_scale(poly, ARC, L, i, j), closed, hw_wall,
                             lambda x, y, Rk=Rk: Vector((Rk*math.cos(x/R), Rk*math.sin(x/R), Z0 - y)), 0.03*k, 1.0)
    walls.finish(mat)
    r_in, r_out = 0.56*R, 0.97*R; r_mid = 0.5*(r_in + r_out); arc_mid = 2*math.pi*r_mid/K
    portals = _Builder("Tunnel_Portals", col)
    for j in range(NSEG+1):
        for i in range(K):
            for k, (poly, closed) in enumerate(_PORTAL):
                zk = Z0 - j*L + 0.004*k
                pts = [((i+u)*arc_mid, r_in + w*(r_out-r_in)) for (u, w) in poly]
                portals.ribbon(pts, closed, hw_portal,
                               lambda x, y, zk=zk: Vector((y*math.cos(x/r_mid), y*math.sin(x/r_mid), zk)), 0.12 + 0.02*k, 1.25)
    portals.finish(mat)
    R2 = outer_ratio*R; ARC2 = 2*math.pi*R2/K
    outer = _Builder("Tunnel_Outer", col)
    for j in range(NSEG):
        for i in range(K):
            for k, (poly, closed) in enumerate(_OUTER):
                outer.ribbon(_scale(poly, ARC2, L, i, j), closed, hw_outer,
                             lambda x, y: Vector((R2*math.cos(x/R2), R2*math.sin(x/R2), Z0 - y)), 0.5, 0.45)
    outer.finish(mat)

def rebuild(scene):
    ctrl = ensure_controls()
    K = int(ctrl["shape_symmetry"]); R = float(ctrl["shape_radius"])
    build_geometry(K, R, float(ctrl["shape_line_width"]), float(ctrl["shape_outer"]))
    ctrl["_built_K"] = K; ctrl["_built_R"] = R
    bad = setup_drivers(scene)
    apply_mode(int(ctrl.get("look_mode", 0)))
    scene.frame_set(scene.frame_current)
    return bad

# ============================ live view ============================
def configure_live_view(win):
    for area in win.screen.areas:
        if area.type != "VIEW_3D": continue
        sp = area.spaces.active
        sp.shading.type = "RENDERED"
        try: sp.shading.use_compositor = "CAMERA"
        except Exception: pass
        ov = sp.overlay; ov.show_overlays = True
        for attr in ("show_floor", "show_axis_x", "show_axis_y", "show_axis_z", "show_cursor", "show_extras", "show_text",
                     "show_stats", "show_outline_selected", "show_object_origins", "show_relationship_lines", "show_bones",
                     "show_motion_paths", "show_annotation", "show_ortho_grid", "show_wireframes"):
            if hasattr(ov, attr):
                try: setattr(ov, attr, False)
                except Exception: pass
        sp.show_gizmo = False
        sp.show_region_toolbar = False
        sp.show_region_ui = True
        sp.region_3d.view_perspective = "CAMERA"
        for reg in area.regions:
            if reg.type == "UI":
                try: reg.active_panel_category = "Neon"
                except Exception: pass
        rw = next((r for r in area.regions if r.type == "WINDOW"), None)
        if rw is not None:
            with bpy.context.temp_override(window=win, area=area, region=rw):
                bpy.ops.view3d.view_center_camera()
        area.tag_redraw()
    cam = win.scene.camera
    if cam is not None:
        cam.data.show_passepartout = True; cam.data.passepartout_alpha = 1.0

# ============================ operators ============================
def _fmt(s): return "%d:%05.2f" % (s // 60, s % 60)

class NEON_OT_setup(bpy.types.Operator):
    bl_idname = "neon.setup"; bl_label = "Set up audio reactivity"
    bl_description = "Create the controls, analyse the audio and wire everything up"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        try:
            ensure_controls(); ensure_kaleido(context.scene); analyze_apply(context.scene)
            apply_mode(int(get_ctrl().get("look_mode", 0))); configure_live_view(context.window)
        except Exception as e:
            self.report({"ERROR"}, str(e)); return {"CANCELLED"}
        return {"FINISHED"}

class NEON_OT_analyze(bpy.types.Operator):
    bl_idname = "neon.analyze"; bl_label = "Apply music"
    bl_description = "Re-analyse the audio with the settings above (file, start, length, kick settings)"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        try: info = analyze_apply(context.scene)
        except Exception as e:
            self.report({"ERROR"}, str(e)); return {"CANCELLED"}
        self.report({"INFO"}, "%d kicks in %.0f s, starting %s into the track" % (info["kicks"], info["seconds"], _fmt(info["start"])))
        return {"FINISHED"}

class NEON_OT_find_section(bpy.types.Operator):
    bl_idname = "neon.find_section"; bl_label = "Find the best part"
    bl_description = "Pick the most dynamic section of the track (kicks, drops, hats) for the chosen length"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        try: info = analyze_apply(context.scene, find_best=True)
        except Exception as e:
            self.report({"ERROR"}, str(e)); return {"CANCELLED"}
        self.report({"INFO"}, "Using %s - %s of the track" % (_fmt(info["start"]), _fmt(info["start"] + info["seconds"])))
        return {"FINISHED"}

class NEON_OT_choose_audio(bpy.types.Operator):
    bl_idname = "neon.choose_audio"; bl_label = "Choose audio file..."
    bl_description = "Pick an mp3 / wav / flac / aiff / ogg file; the best part is selected automatically"
    bl_options = {"REGISTER", "UNDO"}
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.mp3;*.wav;*.flac;*.ogg;*.aif;*.aiff;*.m4a;*.aac", options={"HIDDEN"})
    def invoke(self, context, event):
        ctrl = get_ctrl()
        if ctrl is not None and ctrl.get("audio_file"): self.filepath = ctrl["audio_file"]
        context.window_manager.fileselect_add(self); return {"RUNNING_MODAL"}
    def execute(self, context):
        ctrl = ensure_controls(); prev = ctrl.get("audio_file", "")
        ctrl["audio_file"] = bpy.path.abspath(self.filepath)
        try: info = analyze_apply(context.scene, find_best=True)
        except Exception as e:
            ctrl["audio_file"] = prev; self.report({"ERROR"}, str(e)); return {"CANCELLED"}
        self.report({"INFO"}, "Loaded. Using %s - %s of the track" % (_fmt(info["start"]), _fmt(info["start"] + info["seconds"])))
        return {"FINISHED"}

class NEON_OT_rebuild(bpy.types.Operator):
    bl_idname = "neon.rebuild"; bl_label = "Rebuild tunnel"
    bl_description = "Regenerate the lines tunnel with the shape settings above (takes a moment)"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        try: rebuild(context.scene)
        except Exception as e:
            self.report({"ERROR"}, str(e)); return {"CANCELLED"}
        return {"FINISHED"}

class NEON_OT_live_view(bpy.types.Operator):
    bl_idname = "neon.live_view"; bl_label = "Live view"
    bl_description = "Look through the camera with the final look and glow (fixes the view if you got lost)"
    def execute(self, context):
        configure_live_view(context.window); return {"FINISHED"}

class NEON_OT_reset(bpy.types.Operator):
    bl_idname = "neon.reset"; bl_label = "Reset reactions"
    bl_description = "Put all audio-reaction sliders back to their defaults (does not touch the look)"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        ctrl = ensure_controls()
        for k in LIVE: ctrl[k] = P[k][0]
        refresh(context.scene)
        return {"FINISHED"}

class NEON_OT_mode(bpy.types.Operator):
    bl_idname = "neon.mode"; bl_label = "Look"
    bl_description = "Lines = neon lines tunnel, Kaleido = kaleidoscope fractal tunnel, Both = lines in front of the kaleidoscope"
    bl_options = {"REGISTER", "UNDO"}
    mode: bpy.props.IntProperty(default=1)
    def execute(self, context):
        if self.mode in (1, 2): ensure_kaleido(context.scene)
        apply_mode(self.mode)
        if self.mode in (1, 2): setup_drivers(context.scene)
        refresh(context.scene)
        return {"FINISHED"}

class NEON_OT_preset(bpy.types.Operator):
    bl_idname = "neon.preset"; bl_label = "Preset"
    bl_description = "Load this kaleidoscope look (all Kaleido sliders)"
    bl_options = {"REGISTER", "UNDO"}
    name: bpy.props.StringProperty()
    def execute(self, context):
        if self.name not in PRESETS: return {"CANCELLED"}
        apply_look(PRESETS[self.name]); return {"FINISHED"}

class NEON_OT_randomize(bpy.types.Operator):
    bl_idname = "neon.randomize"; bl_label = "Randomize"
    bl_description = "Roll a random kaleidoscope look (Ctrl+Z goes back, Save look keeps it)"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        apply_look(random_look()); return {"FINISHED"}

class NEON_OT_save_look(bpy.types.Operator):
    bl_idname = "neon.save_look"; bl_label = "Save look"
    bl_description = "Store the current Kaleido sliders under a name (saved inside this .blend)"
    bl_options = {"REGISTER", "UNDO"}
    name: bpy.props.StringProperty(name="Name", default="My look")
    def invoke(self, context, event):
        n = len(saved_looks(get_ctrl())) + 1; self.name = "My look %d" % n
        return context.window_manager.invoke_props_dialog(self)
    def execute(self, context):
        ctrl = ensure_controls(); looks = saved_looks(ctrl)
        looks[self.name.strip() or "My look"] = {k: (int(ctrl[k]) if isinstance(KPARAMS[k][0], int) else float(ctrl[k])) for k in KPARAMS}
        ctrl["_looks"] = json.dumps(looks)
        self.report({"INFO"}, "Saved look '%s'" % self.name); return {"FINISHED"}

class NEON_OT_apply_look(bpy.types.Operator):
    bl_idname = "neon.apply_look"; bl_label = "Load look"
    bl_description = "Load this saved look"
    bl_options = {"REGISTER", "UNDO"}
    name: bpy.props.StringProperty()
    def execute(self, context):
        looks = saved_looks(get_ctrl())
        if self.name not in looks: return {"CANCELLED"}
        apply_look(looks[self.name]); return {"FINISHED"}

class NEON_OT_delete_look(bpy.types.Operator):
    bl_idname = "neon.delete_look"; bl_label = "Delete look"
    bl_description = "Delete this saved look"
    bl_options = {"REGISTER", "UNDO"}
    name: bpy.props.StringProperty()
    def execute(self, context):
        ctrl = get_ctrl(); looks = saved_looks(ctrl); looks.pop(self.name, None)
        ctrl["_looks"] = json.dumps(looks); return {"FINISHED"}

# ============================ panel ============================
def _knobs(layout, ctrl, keys):
    col = layout.column(align=True)
    for k in keys:
        col.prop(ctrl, '["%s"]' % k, text=P[k][3], slider=True)

def _mode():
    c = get_ctrl(); return int(c.get("look_mode", 0)) if c is not None else 0

class NEON_PT_main(bpy.types.Panel):
    bl_space_type = "VIEW_3D"; bl_region_type = "UI"; bl_category = "Neon"; bl_label = "Neon Audio Tunnel"
    def draw(self, context):
        lay = self.layout; sc = context.scene; ctrl = get_ctrl()
        if ctrl is None or bpy.data.objects.get(SIG) is None:
            lay.operator("neon.setup", icon="PLAY_SOUND"); return
        row = lay.row(align=True); row.scale_y = 1.6
        row.operator("screen.frame_jump", text="", icon="REW").end = False
        playing = context.screen.is_animation_playing
        row.operator("screen.animation_play", text="Pause" if playing else "Play", icon="PAUSE" if playing else "PLAY")
        t = (sc.frame_current - sc.frame_start)/FPS; tot = (sc.frame_end - sc.frame_start + 1)/FPS
        lay.label(text="%s / %s   (track %s)" % (_fmt(t), _fmt(tot), _fmt(float(ctrl.get("audio_start", 0)) + t)))
        row = lay.row(align=True)
        row.operator("neon.live_view", icon="CAMERA_DATA")
        row.operator("neon.reset", icon="LOOP_BACK")

class _Sub:
    bl_space_type = "VIEW_3D"; bl_region_type = "UI"; bl_category = "Neon"; bl_parent_id = "NEON_PT_main"
    @classmethod
    def poll(cls, context): return get_ctrl() is not None and bpy.data.objects.get(SIG) is not None

class NEON_PT_music(_Sub, bpy.types.Panel):
    bl_label = "Music"
    def draw(self, context):
        lay = self.layout; ctrl = get_ctrl()
        box = lay.box()
        box.label(text=os.path.basename(ctrl.get("audio_file", "")) or "No audio file", icon="SOUND")
        ts = ctrl.get("_track_seconds")
        if ts: box.label(text="Track length " + _fmt(ts)[:-3])
        box.operator("neon.choose_audio", icon="FILEBROWSER")
        _knobs(lay, ctrl, MUSIC[:2])
        lay.operator("neon.find_section", icon="VIEWZOOM")
        _knobs(lay, ctrl, MUSIC[2:])
        r = lay.row(); r.scale_y = 1.4; r.operator("neon.analyze", icon="FILE_REFRESH")
        lay.label(text="Changes in this box need Apply music", icon="INFO")

class NEON_PT_look(_Sub, bpy.types.Panel):
    bl_label = "Look & presets"
    def draw(self, context):
        lay = self.layout; ctrl = get_ctrl(); mode = _mode()
        row = lay.row(align=True); row.scale_y = 1.4
        for i, lab in enumerate(("Lines", "Kaleido", "Both")):
            op = row.operator("neon.mode", text=lab, depress=(mode == i)); op.mode = i
        if mode == 0:
            lay.label(text="Switch to Kaleido or Both for presets", icon="INFO"); return
        grid = lay.grid_flow(columns=2, even_columns=True, align=True)
        for name in PRESETS:
            grid.operator("neon.preset", text=name).name = name
        row = lay.row(align=True); row.scale_y = 1.3
        row.operator("neon.randomize", icon="SHADERFX")
        row.operator("neon.save_look", icon="ADD")
        looks = saved_looks(ctrl)
        if looks:
            box = lay.box(); box.label(text="My looks")
            for n in sorted(looks):
                r = box.row(align=True)
                r.operator("neon.apply_look", text=n).name = n
                r.operator("neon.delete_look", text="", icon="X").name = n

class _KSub(_Sub):
    @classmethod
    def poll(cls, context): return _Sub.poll(context) and _mode() in (1, 2)

class NEON_PT_kpattern(_KSub, bpy.types.Panel):
    bl_label = "Kaleido - tunnel & fractal"
    def draw(self, context): _knobs(self.layout, get_ctrl(), GROUPS["kpattern"])

class NEON_PT_kshapes(_KSub, bpy.types.Panel):
    bl_label = "Kaleido - shapes"
    def draw(self, context): _knobs(self.layout, get_ctrl(), GROUPS["kshapes"])

class NEON_PT_kcolour(_KSub, bpy.types.Panel):
    bl_label = "Kaleido - colour & light"
    def draw(self, context): _knobs(self.layout, get_ctrl(), GROUPS["kcolour"])

class NEON_PT_shape(_Sub, bpy.types.Panel):
    bl_label = "Lines tunnel - shape"; bl_options = {"DEFAULT_CLOSED"}
    @classmethod
    def poll(cls, context): return _Sub.poll(context) and _mode() in (0, 2)
    def draw(self, context):
        lay = self.layout; ctrl = get_ctrl()
        _knobs(lay, ctrl, SHAPE)
        r = lay.row(); r.scale_y = 1.4; r.operator("neon.rebuild", icon="MOD_SCREW")
        lay.label(text="Shape changes need Rebuild tunnel", icon="INFO")

class NEON_PT_signals(_Sub, bpy.types.Panel):
    bl_label = "Live signals (what it hears)"; bl_options = {"DEFAULT_CLOSED"}
    def draw(self, context):
        sig = bpy.data.objects.get(SIG); col = self.layout.column(align=True)
        for k, lab in METERS:
            col.prop(sig, '["%s"]' % k, text=lab, slider=True)

class NEON_PT_kick(_Sub, bpy.types.Panel):
    bl_label = "Kick reacts"; bl_options = {"DEFAULT_CLOSED"}
    def draw(self, context): _knobs(self.layout, get_ctrl(), GROUPS["kick"])

class NEON_PT_bass(_Sub, bpy.types.Panel):
    bl_label = "Bass reacts"; bl_options = {"DEFAULT_CLOSED"}
    def draw(self, context): _knobs(self.layout, get_ctrl(), GROUPS["bass"])

class NEON_PT_hats(_Sub, bpy.types.Panel):
    bl_label = "Hi-hats & mids react"; bl_options = {"DEFAULT_CLOSED"}
    def draw(self, context): _knobs(self.layout, get_ctrl(), GROUPS["hats"])

class NEON_PT_energy(_Sub, bpy.types.Panel):
    bl_label = "Loudness reacts"; bl_options = {"DEFAULT_CLOSED"}
    def draw(self, context): _knobs(self.layout, get_ctrl(), GROUPS["energy"])

class NEON_PT_base(_Sub, bpy.types.Panel):
    bl_label = "Base motion"; bl_options = {"DEFAULT_CLOSED"}
    def draw(self, context): _knobs(self.layout, get_ctrl(), GROUPS["base"])

# ============================ registration ============================
@persistent
def neon_ui_redraw(scene, depsgraph=None):
    try:
        for w in bpy.context.window_manager.windows:
            for a in w.screen.areas:
                if a.type == "VIEW_3D":
                    for r in a.regions:
                        if r.type == "UI": r.tag_redraw()
    except Exception:
        pass

CLASSES = (NEON_OT_setup, NEON_OT_analyze, NEON_OT_find_section, NEON_OT_choose_audio, NEON_OT_rebuild,
           NEON_OT_live_view, NEON_OT_reset, NEON_OT_mode, NEON_OT_preset, NEON_OT_randomize, NEON_OT_save_look,
           NEON_OT_apply_look, NEON_OT_delete_look,
           NEON_PT_main, NEON_PT_music, NEON_PT_look, NEON_PT_kpattern, NEON_PT_kshapes, NEON_PT_kcolour,
           NEON_PT_shape, NEON_PT_signals, NEON_PT_kick, NEON_PT_bass, NEON_PT_hats, NEON_PT_energy, NEON_PT_base)

def register():
    for name in ("NEON_PT_base", "NEON_PT_energy", "NEON_PT_hats", "NEON_PT_bass", "NEON_PT_kick", "NEON_PT_signals",
                 "NEON_PT_shape", "NEON_PT_kcolour", "NEON_PT_kshapes", "NEON_PT_kpattern", "NEON_PT_look", "NEON_PT_music"):
        old = getattr(bpy.types, name, None)
        if old is not None:
            try: bpy.utils.unregister_class(old)
            except Exception: pass
    for c in reversed(CLASSES):
        old = getattr(bpy.types, c.__name__, None)
        if old is not None:
            try: bpy.utils.unregister_class(old)
            except Exception: pass
    for c in CLASSES:
        bpy.utils.register_class(c)
    hs = bpy.app.handlers.frame_change_post
    for h in [h for h in hs if getattr(h, "__name__", "") == "neon_ui_redraw"]: hs.remove(h)
    hs.append(neon_ui_redraw)

register()
