"""
script_features: what the room is doing, as 0-1 control channels (one sample each).

Input 0: merge_bands = the microphone split into low / mid / high (audio rate,
time-sliced, so this cook sees this frame's samples).
Input 1: topto_stats = camera summary (r area, g mean x, b mean y, a mean motion).

Microphone: band RMS (+ Mic Gain) -> dBFS -> 0-1 over a 60 dB window. An adaptive
floor rises slowly (Floor Adapt) and drops fast, so constant sound -- the drone
coming back from the speakers, room tone -- is absorbed and only sound ABOVE it
counts. Band envelopes: fast attack, Mic Release. transient = fast minus slow
envelope of the raw levels (claps, knocks, plosives).
Camera: presence gate from the silhouette area, prox = area stretched to 0-1,
cx / cy smoothed (mirrored with Mirror), motion smoothed.

Channels: low mid high level transient presence prox cx cy motion.
Envelope state lives in a module dict between cooks (reset when this DAT reloads).
"""
import math

import numpy as np

BANDS = ('low', 'mid', 'high')
WINDOW_DB = 60.0
_state = {}


def _follow(prev: float, target: float, up_s: float, down_s: float, dt: float) -> float:
	"""One-pole follower with separate rise and fall time constants (seconds)."""
	tau = up_s if target > prev else down_s
	return prev + (target - prev) * (1.0 - math.exp(-dt / max(tau, 1e-4)))


def _mic(scriptOp, p, s: dict, dt: float) -> dict:
	mic = scriptOp.inputs[0] if len(scriptOp.inputs) > 0 else None
	out = {'low': 0.0, 'mid': 0.0, 'high': 0.0, 'level': 0.0, 'transient': 0.0}
	if not p.Mic.eval() or mic is None or mic.numChans < 3 or mic.numSamples < 1:
		for key in [k for k in s if k.split('_')[0] in ('floor', 'env', 'fast', 'slow', 'trans')]:
			del s[key]
		return out
	gain = 10.0 ** (p.Micgain.eval() / 20.0)
	floor_t = p.Floortime.eval()
	release = p.Micsmooth.eval()
	jump = 0.0
	for i, band in enumerate(BANDS):
		x = mic[i].numpyArray()
		rms = float(np.sqrt(np.mean(np.square(x)))) * gain
		lvl = min(1.0, max(0.0, (20.0 * math.log10(rms + 1e-9) + WINDOW_DB) / WINDOW_DB))
		fl = _follow(s.get('floor_' + band, lvl), lvl, floor_t, 0.6, dt) if floor_t > 0.0 else 0.0
		s['floor_' + band] = fl
		excess = max(0.0, lvl - fl - 0.02) / max(0.05, 1.0 - fl)
		env = _follow(s.get('env_' + band, 0.0), excess, 0.03, release, dt)
		s['env_' + band] = env
		fast = _follow(s.get('fast_' + band, lvl), lvl, 0.005, 0.08, dt)
		slow = _follow(s.get('slow_' + band, lvl), lvl, 0.25, 0.25, dt)
		s['fast_' + band], s['slow_' + band] = fast, slow
		jump = max(jump, fast - slow)
		out[band] = min(1.0, 1.5 * env)
	bands = [out[b] for b in BANDS]
	out['level'] = min(1.0, 0.6 * max(bands) + 0.4 * sum(bands) / 3.0)
	trans = _follow(s.get('trans', 0.0), min(1.0, max(0.0, jump - 0.04) * 5.0), 0.005, 0.25, dt)
	s['trans'] = trans
	out['transient'] = trans
	return out


def _camera(scriptOp, p, s: dict, dt: float) -> dict:
	cam = scriptOp.inputs[1] if len(scriptOp.inputs) > 1 else None
	area = mx = my = motion = 0.0
	if p.Camera.eval() and cam is not None and cam.numChans >= 4:
		area, mx, my, motion = (float(cam[i][0]) for i in range(4))
	if p.Mirror.eval():
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
	values = _mic(scriptOp, p, s, dt)
	values.update(_camera(scriptOp, p, s, dt))
	scriptOp.clear()
	scriptOp.isTimeSlice = False
	scriptOp.numSamples = 1
	for name in ('low', 'mid', 'high', 'level', 'transient', 'presence', 'prox', 'cx', 'cy', 'motion'):
		scriptOp.appendChan(name)[0] = values[name]
	return
