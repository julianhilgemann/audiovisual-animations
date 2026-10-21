# Written by Save Module from modulator.tox so git shows readable diffs. Edit this
# DAT inside modulator in TouchDesigner, then press Save Module; edits here change nothing.

# Modulation matrix: the source bus in, one channel per destination out, in the destination's units.
#
# The tables are the Destinations and Routes parameters, or the module's own destinations and
# routes when those are empty. Each destination has a min, a max, a base and a smoothing time.
# The base is the table's, or, when Bases COMP is set, that COMP's Base<name> parameter on its
# Bases page, which EnsureBases() creates from the table so the bases get sliders that the host
# project saves. Each row of routes adds amount x curve(source) to one destination, measured in
# its 0-1 range, so amount 0.5 moves it half its span. The Depth parameters scale the routes by
# the source's family (a_* audio, lfo* LFOs, clk_* clock, everything else MIDI). The sum is
# clamped to 0-1, smoothed by the destination's smooth seconds and mapped to min-max. Hold
# freezes every destination, Bypass outputs the bases alone.
#
# Curves: lin, sq (slow start), sqrt (fast start), inv (1 - x), bi (2x - 1, so a source centred
# on 0.5, like an LFO, swings the destination both ways around its base) and step (0 or 1 at 0.5).

import math
import re

_CURVES = {
	'lin': lambda x: x,
	'sq': lambda x: x * x,
	'sqrt': lambda x: math.sqrt(max(x, 0.0)),
	'inv': lambda x: 1.0 - x,
	'bi': lambda x: 2.0 * x - 1.0,
	'step': lambda x: 1.0 if x >= 0.5 else 0.0,
}
_DEPTHS = (('a_', 'Audiodepth'), ('lfo', 'Lfodepth'), ('clk_', 'Clockdepth'))

_cache = {}
_states = {}

def onSetupParameters(scriptOp):
	return

def onPulse(par):
	return

def onCook(scriptOp):
	comp = parent.Mod
	bus = scriptOp.inputs[0] if scriptOp.inputs else None
	dt = min(max(absTime.stepSeconds, 1e-4), 0.1)
	destinations, routes, changed = _tables(comp)
	if changed:
		run(EnsureBases, comp, delayFrames=1)  # parameters are not created while cooking
	holder = comp.par.Basescomp.eval()
	state = _states.setdefault(scriptOp.id, {})
	hold, bypass = comp.par.Hold.eval(), comp.par.Bypass.eval()
	master = comp.par.Master.eval()
	depths = {par: comp.par[par].eval() for _, par in _DEPTHS}
	depths['Mididepth'] = comp.par.Mididepth.eval()

	sums = {d['name']: 0.0 for d in destinations}
	if not bypass and bus is not None:
		for source, dest, amount, curve in routes:
			if dest not in sums:
				continue
			chan = bus[source]
			if chan is None:
				continue
			sums[dest] += amount * curve(chan[0]) * master * depths[_family(source)]

	scriptOp.clear()
	scriptOp.numSamples = 1
	for d in destinations:
		name, lo, hi = d['name'], d['min'], d['max']
		span = hi - lo if hi != lo else 1.0
		basePar = holder.par[d['par']] if holder is not None else None
		base = basePar.eval() if basePar is not None else d['base']
		target = min(max((base - lo) / span + sums[name], 0.0), 1.0)
		current = state.get(name, target)
		if not hold:
			tau = d['smooth']
			current = target if tau <= 0.0 else current + (target - current) * (1.0 - math.exp(-dt / tau))
		state[name] = current
		scriptOp.appendChan(name)[0] = lo + current * span
	return

def EnsureBases(comp):
	"""Create or update one Float per destination on the Bases page of Bases COMP (values are left alone)."""
	holder = comp.par.Basescomp.eval()
	if holder is None:
		return
	page = next((p for p in holder.customPages if p.name == 'Bases'), None) or holder.appendCustomPage('Bases')
	for d in _tables(comp)[0]:
		existing = holder.par[d['par']]
		par = existing if existing is not None else page.appendFloat(d['par'], label=d['name'])[0]
		lo, hi = sorted((d['min'], d['max']))
		par.label = d['name']
		par.min, par.max = lo, hi
		par.normMin, par.normMax = lo, hi
		par.clampMin = par.clampMax = True
		par.default = d['base']
		par.help = 'Base value of %s (%s) before modulation, %g to %g. Routes add to it.' % (d['name'], d['target'] or 'see destinations', d['min'], d['max'])
		if existing is None:
			par.val = d['base']

def Destinations(comp):
	"""The destinations table in use: the Destinations parameter, or the module's own."""
	return comp.par.Destinations.eval() or comp.op('destinations')

def Routes(comp):
	"""The routes table in use: the Routes parameter, or the module's own."""
	return comp.par.Routes.eval() or comp.op('routes')

def _parName(name):
	"""Bases parameter for a destination: noise_period -> Basenoiseperiod."""
	return 'Base' + re.sub(r'[^a-z0-9]', '', name.lower())

def _family(source):
	for prefix, par in _DEPTHS:
		if source.startswith(prefix):
			return par
	return 'Mididepth'

def _tables(comp):
	"""destinations and routes parsed (cached until either table's text changes), and whether they changed."""
	destTable, routeTable = Destinations(comp), Routes(comp)
	key = (destTable.path, destTable.text, routeTable.path, routeTable.text)
	cached = _cache.get(comp.id)
	if cached and cached[0] == key:
		return cached[1] + (False,)
	destinations = []
	for row in _dictRows(destTable):
		destinations.append({'name': row['name'], 'par': _parName(row['name']), 'min': _float(row.get('min'), 0.0),
			'max': _float(row.get('max'), 1.0), 'base': _float(row.get('base'), 0.0),
			'smooth': _float(row.get('smooth'), 0.0), 'target': row.get('target', '')})
	routes = []
	for row in _dictRows(routeTable, key='source'):
		curve = _CURVES.get(row.get('curve', 'lin') or 'lin', _CURVES['lin'])
		routes.append((row['source'], row.get('dest', ''), _float(row.get('amount'), 0.0), curve))
	_cache[comp.id] = (key, (destinations, routes))
	return destinations, routes, True

def _dictRows(table, key='name'):
	if table is None or table.numRows < 2:
		return []
	header = [c.val.strip() for c in table.row(0)]
	out = []
	for r in range(1, table.numRows):
		row = {h: table[r, i].val.strip() for i, h in enumerate(header)}
		if row.get(key) and not row[key].startswith('#'):
			out.append(row)
	return out

def _float(text, default):
	try:
		return float(text)
	except (TypeError, ValueError):
		return default
