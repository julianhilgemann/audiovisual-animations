# Written by Save Module from modulator.tox so git shows readable diffs. Edit this
# DAT inside modulator in TouchDesigner, then press Save Module; edits here change nothing.

# LFO bank: one LFO per row of the LFO table (the LFOs parameter, or the module's own lfo_table
# when that is empty), each swinging 0-1 around 0.5.
#
# Input 1 is the source bus (audio features, Octatrack channels, clock). sync beat locks an LFO
# to clk_beat with rate = beats per cycle, so the Octatrack's tempo moves it and a MIDI start
# puts it on the downbeat; sync free runs at rate Hz. Any source can modulate it:
# - rate_src speeds the LFO up by rate_amt octaves at full source (negative slows it); a beat
#   LFO steps in whole doublings, so it stays on the grid;
# - depth_src adds depth_amt to depth;
# - reset_src restarts the cycle whenever it rises past 0.5 (a trigger such as a_kick or
#   mt1_trig).
# Shapes: sine, tri, saw (rising), ramp (falling), square, pulse (a quarter of the cycle high),
# sh (a new random level each cycle) and noise (glides between random levels). smooth eases
# the output over that many seconds, which rounds off square, pulse and sh.

import math

_SHAPES = ('sine', 'tri', 'saw', 'ramp', 'square', 'pulse', 'sh', 'noise')

_states = {}

def onSetupParameters(scriptOp):
	return

def onPulse(par):
	return

def onCook(scriptOp):
	bus = scriptOp.inputs[0] if scriptOp.inputs else None
	dt = min(max(absTime.stepSeconds, 1e-4), 0.1)
	beatChan = bus['clk_beat'] if bus is not None else None
	states = _states.setdefault(scriptOp.id, {})
	comp = parent.Mod
	rows = _rows(comp.par.Lfos.eval() or comp.op('lfo_table'))
	scriptOp.clear()
	scriptOp.numSamples = 1
	for row in rows:
		st = states.setdefault(row['name'], {'phase': 0.0, 'anchor': 0.0, 'cycle': 0, 'reset': 0.0, 'out': 0.5, 'beat': None})
		beat = beatChan[0] if beatChan is not None else absTime.seconds * 2.0  # 120 BPM without a clock
		scriptOp.appendChan(row['name'])[0] = _step(row, st, bus, beat, dt)
	for name in list(states):
		if name not in {r['name'] for r in rows}:
			del states[name]
	return

def _rows(table):
	"""lfo_table as a list of dicts, skipping empty and commented (#) rows."""
	if table is None or table.numRows < 2:
		return []
	header = [c.val.strip() for c in table.row(0)]
	rows = []
	for r in range(1, table.numRows):
		row = {h: table[r, i].val.strip() for i, h in enumerate(header)}
		if row.get('name') and not row['name'].startswith('#'):
			rows.append(row)
	return rows

def _num(row, key, default=0.0):
	try:
		return float(row.get(key, '') or default)
	except ValueError:
		return default

def _source(bus, name):
	"""The current value of a bus channel, 0 for an empty or unknown name."""
	if bus is None or not name:
		return 0.0
	chan = bus[name]
	return chan[0] if chan is not None else 0.0

def _step(row, st, bus, beat, dt):
	"""Advance one LFO by one frame and return its output."""
	rate = max(_num(row, 'rate', 1.0), 1e-4)
	octaves = _num(row, 'rate_amt') * _source(bus, row.get('rate_src'))
	depth = min(max(_num(row, 'depth', 1.0) + _num(row, 'depth_amt') * _source(bus, row.get('depth_src')), 0.0), 1.0)
	resetValue = _source(bus, row.get('reset_src'))
	reset = resetValue >= 0.5 and st['reset'] < 0.5
	st['reset'] = resetValue
	offset = _num(row, 'phase')

	if row.get('sync', 'beat') == 'free':
		if reset:
			st['phase'] = 0.0
			st['cycle'] += 1
		st['phase'] += dt * rate * 2.0 ** octaves
		while st['phase'] >= 1.0:
			st['phase'] -= 1.0
			st['cycle'] += 1
		position = st['phase'] + offset
		cycle = st['cycle'] + math.floor(position)
	else:
		if st['beat'] is not None and beat < st['beat'] - 1.0:
			st['anchor'] = 0.0  # the clock restarted (MIDI start) or wrapped
		st['beat'] = beat
		if reset:
			st['anchor'] = beat
		beats = rate / 2.0 ** round(octaves)
		position = (beat - st['anchor']) / beats + offset
		cycle = math.floor(position)
	phase = position % 1.0

	shape = row.get('shape', 'sine')
	if shape == 'tri':
		wave = 1.0 - 4.0 * abs(phase - 0.5)
	elif shape == 'saw':
		wave = 2.0 * phase - 1.0
	elif shape == 'ramp':
		wave = 1.0 - 2.0 * phase
	elif shape == 'square':
		wave = 1.0 if phase < 0.5 else -1.0
	elif shape == 'pulse':
		wave = 1.0 if phase < 0.25 else -1.0
	elif shape == 'sh':
		wave = _random(row['name'], cycle)
	elif shape == 'noise':
		a, b = _random(row['name'], cycle), _random(row['name'], cycle + 1)
		wave = a + (b - a) * (1.0 - math.cos(math.pi * phase)) * 0.5
	else:
		wave = math.sin(2.0 * math.pi * phase)
	target = 0.5 + 0.5 * depth * wave

	smooth = _num(row, 'smooth')
	if smooth > 0.0:
		st['out'] += (target - st['out']) * (1.0 - math.exp(-dt / smooth))
	else:
		st['out'] = target
	return st['out']

def _random(name, cycle):
	"""A repeatable random value in -1..1 for one cycle of one LFO."""
	seed = sum(ord(c) * (i + 1) for i, c in enumerate(name))
	x = math.sin(cycle * 12.9898 + seed * 78.233) * 43758.5453
	return 2.0 * (x - math.floor(x)) - 1.0
