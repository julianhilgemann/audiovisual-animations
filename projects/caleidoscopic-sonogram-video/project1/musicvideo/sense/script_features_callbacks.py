"""
script_features: what the track and the modulator video are doing, as 0-1 control channels.

Input 0: merge_bands = the track (mono) split into low / mid / high (audio rate,
time-sliced, so this cook sees this frame's samples).
Input 1: topto_stats = video mask summary (r area, g mean x, b mean y, a mean motion).

Track: band RMS (+ Analysis Gain) -> dBFS -> 0-1 over a 60 dB window. An adaptive
floor rises slowly (Floor Adapt) and drops fast, so a loud master still moves the
image: only what rises above the floor counts. Band envelopes: fast attack, Band
Release. transient = fast minus slow envelope of the raw levels (kicks, snares).
energy = slow (about 2 s) follower of the raw level WITHOUT the floor, so it follows
the structure of the track (breakdown low, drop high).
Video: presence gate from the mask area, prox = area stretched to 0-1,
cx / cy smoothed (mirrored with Mirror), motion smoothed.

Channels: low mid high level transient energy presence prox cx cy motion.
Envelope state lives in a module dict between cooks (reset when this DAT reloads).
"""
import math

import numpy as np

BANDS = ('low', 'mid', 'high')
WINDOW_DB = 60.0
CHANNELS = ('low', 'mid', 'high', 'level', 'transient', 'energy', 'presence', 'prox', 'cx', 'cy', 'motion')
_state = {}


def _follow(prev: float, target: float, up_s: float, down_s: float, dt: float) -> float:
	"""One-pole follower with separate rise and fall time constants (seconds)."""
	tau = up_s if target > prev else down_s
	return prev + (target - prev) * (1.0 - math.exp(-dt / max(tau, 1e-4)))


def _track(scriptOp, p, s: dict, dt: float) -> dict:
	"""Band levels and onsets, each normalised against the track's own running floor and peak."""
	bands_in = scriptOp.inputs[0] if len(scriptOp.inputs) > 0 else None
	release = p.Release.eval()
	if not p.Play.eval() or bands_in is None or bands_in.numChans < 3 or bands_in.numSamples < 1:
		out = {}
		for b in BANDS:
			s['out_' + b] = _follow(s.get('out_' + b, 0.0), 0.0, 0.02, release, dt)
			out[b] = s['out_' + b]
		s['trans'] = _follow(s.get('trans', 0.0), 0.0, 0.005, 0.2, dt)
		s['energy'] = _follow(s.get('energy', 0.0), 0.0, 1.2, 2.5, dt)
		out.update(level=max(out.values()), transient=s['trans'], energy=s['energy'])
		return out
	gain = 10.0 ** (p.Trackgain.eval() / 20.0)
	floor_t = p.Adapt.eval()
	out = {}
	raw = []
	onset = 0.0
	for i, band in enumerate(BANDS):
		x = bands_in[i].numpyArray()
		rms = float(np.sqrt(np.mean(np.square(x)))) * gain
		lvl = min(1.0, max(0.0, (20.0 * math.log10(rms + 1e-9) + WINDOW_DB) / WINDOW_DB))
		raw.append(lvl)
		env = _follow(s.get('env_' + band, lvl), lvl, 0.015, release, dt)
		s['env_' + band] = env
		# floor: slow rise (Floor Adapt), quick fall; peak: instant rise, slow decay toward the floor
		fl = _follow(s.get('floor_' + band, env), env, floor_t, 0.5, dt) if floor_t > 0.0 else 0.0
		s['floor_' + band] = fl
		pk = max(env, _follow(s.get('peak_' + band, env), fl, 0.0, 4.0, dt))
		s['peak_' + band] = pk
		out[band] = min(1.0, max(0.0, (env - fl) / max(0.04, pk - fl))) if floor_t > 0.0 else env
		# onset: rise of a fast envelope over a slow one, per band (the low band counts most)
		fast = _follow(s.get('fast_' + band, lvl), lvl, 0.01, 0.06, dt)
		slow = _follow(s.get('slow_' + band, lvl), lvl, 0.12, 0.12, dt)
		s['fast_' + band], s['slow_' + band] = fast, slow
		onset += (0.6, 0.25, 0.15)[i] * max(0.0, fast - slow)
	bands = [out[b] for b in BANDS]
	out['level'] = min(1.0, 0.6 * max(bands) + 0.4 * sum(bands) / 3.0)
	# adaptive onset threshold: only onsets well above the track's usual onset count
	mean_o = _follow(s.get('mean_o', onset), onset, 1.5, 1.5, dt)
	s['mean_o'] = mean_o
	peak_o = max(onset, _follow(s.get('peak_o', onset), mean_o, 0.0, 3.0, dt))
	s['peak_o'] = peak_o
	hit = min(1.0, max(0.0, (onset - 1.6 * mean_o) / max(0.02, peak_o - 1.6 * mean_o)))
	trans = _follow(s.get('trans', 0.0), hit, 0.004, 0.18, dt)
	s['trans'] = trans
	out['transient'] = trans
	loud = min(1.0, max(0.0, (0.5 * raw[0] + 0.3 * raw[1] + 0.2 * raw[2] - 0.45) / 0.45))
	s['energy'] = _follow(s.get('energy', 0.0), loud, 1.2, 2.5, dt)
	out['energy'] = s['energy']
	return out


def _video(scriptOp, p, s: dict, dt: float) -> dict:
	vid = scriptOp.inputs[1] if len(scriptOp.inputs) > 1 else None
	area = mx = my = motion = 0.0
	if p.Modon.eval() and vid is not None and vid.numChans >= 4:
		area, mx, my, motion = (float(vid[i][0]) for i in range(4))
	if p.Modmirror.eval():
		mx = 1.0 - mx
	seen = area > 0.005
	presence = _follow(s.get('presence', 0.0), min(1.0, max(0.0, (area - 0.015) / 0.04)), 0.15, 0.8, dt)
	prox = _follow(s.get('prox', 0.0), min(1.0, area * 2.5), 0.2, 0.6, dt)
	cx = _follow(s.get('cx', 0.5), mx if seen else 0.5, 0.25, 0.25 if seen else 1.5, dt)
	cy = _follow(s.get('cy', 0.5), my if seen else 0.5, 0.25, 0.25 if seen else 1.5, dt)
	mot = _follow(s.get('motion', 0.0), min(1.0, motion * 8.0), 0.05, 0.5, dt)
	s.update(presence=presence, prox=prox, cx=cx, cy=cy, motion=mot)
	return {'presence': presence, 'prox': prox, 'cx': cx, 'cy': cy, 'motion': mot}


def onCook(scriptOp: scriptCHOP):
	p = parent.Reactor.par
	dt = 1.0 / max(1.0, float(project.cookRate))
	s = _state.setdefault(scriptOp.path, {})
	values = _track(scriptOp, p, s, dt)
	values.update(_video(scriptOp, p, s, dt))
	scriptOp.clear()
	scriptOp.isTimeSlice = False
	scriptOp.numSamples = 1
	for name in CHANNELS:
		scriptOp.appendChan(name)[0] = values[name]
	return
