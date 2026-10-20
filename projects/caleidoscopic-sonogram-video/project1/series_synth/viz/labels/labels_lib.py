"""
labels_lib -- every text label of the dashboard as [x, y, text] rows, one function per layer.

Geometry is computed in 1920x1080 DESIGN units (origin bottom-left, the Text TOP
spec-DAT convention) and scaled to the dashboard's real resolution on output, so the
same layout serves 1280x720 (Non-Commercial cap) or 1920x1080. Panel geometry comes from viz/layout -- the same table glsl_dashboard
reads -- and plot ranges from viz/axes. This build's spec DAT honours only x, y and
text, so each text style is its own Text TOP (tinted in glsl_dashboard), and right /
centre alignment is computed from Consolas' fixed advance (measured: 0.7331 x pt).

Layers:  axis   tick labels                 (Consolas 11)
         title  panel titles                (Bahnschrift 13)
         dim    captions, legends, labels   (Consolas 12)
         value  numbers + live readouts     (Consolas 12, the only per-frame layer)
         header dashboard title             (Bahnschrift 22)

Shared with glsl_dashboard (keep both in step):
  scope y range +-1.15, 2 cycles across; spectrum and sonogram log f 20 Hz-20 kHz;
  spectrum level -96..0 dB; sonogram span 512 frames / 60 fps; env trail 4 s;
  legends: plot corner, rows 16 px apart starting 12 px inside, swatch 18 px,
  text 24 px after the swatch start (LEGEND_* below and legendRow() in the shader).
"""
import math

import numpy as np

ADVANCE = 0.7331                 # Consolas advance per point (TD 2025.32820, measured)
CENTER = 0.71875                 # baseline offset to the cap centre per point
PT_AXIS, PT_TEXT, PT_TITLE = 11, 12, 13
FMIN, FMAX = 20.0, 20000.0
SONO_SECONDS = 512 / 60.0
ENV_SECONDS = 4.0
SCOPE_RANGE = 1.15
LEGEND_TOP, LEGEND_PITCH, LEGEND_TEXT = 12, 16, 34
LEGENDS = {   # panel: (corner, entries) -- swatch colours live in glsl_dashboard
	'scope': ('tl', ['raw window', 'shaped table', 'audio out', 'playhead']),
	'spectrum': ('tr', ['audio out', 'peak hold', 'table harmonics', 'filter']),
}
ENV_LEGEND_GATE = 'gate'   # the env legend carries live ADSR values, so it lives in _value()
TITLES = {
	'series': 'SOURCE  ·  BUNDESBANK BBIM1  ·  NEW BUSINESS: HOUSING LOANS TO HOUSEHOLDS, GERMANY',
	'stats': 'FULL SERIES',
	'scope': 'OSCILLATOR  ·  TIME DOMAIN',
	'wt3d': 'WAVETABLE 3D  ·  {frames} WINDOWS {first} → {last}',
	'spectrum': 'SPECTRUM  ·  FREQUENCY DOMAIN',
	'sonogram': 'SONOGRAM  ·  FREQUENCY OVER TIME',
	'env': 'ENVELOPES',
}
CAPTIONS = {
	'series': 'EUR bn / month  ·  window = 1 cycle',
	'scope': 'amplitude · phase (1 cycle)',
	'wt3d': 'phase →   history ↓',
	'spectrum': 'dB · Hz (log)',
	'sonogram': 'Hz (log) · seconds',
	'env': 'level · seconds',
}
SERIES_STATS = [('months', 'obs'), ('latest', 'latest'), ('yoy', 'YoY'), ('mean', 'mean/median'),
				('std', 'std dev'), ('min', 'min'), ('max', 'max'), ('cagr', 'CAGR'),
				('vol', 'vol m/m'), ('acf12', 'ACF lag 12'), ('season', 'peak/trough'),
				('drawdown', 'drawdown')]
WINDOW_STATS = ['window', 'length', 'mean/sd', 'trend', 'range', 'crest', 'centroid',
				'annual', 'harmonics', 'time warp', 'pitch', 'level']
STATS_TOP, STATS_PITCH = 48, 19


def build(layer: str) -> list:
	"""Rows for one text layer ('axis', 'title', 'dim', 'value', 'header')."""
	return {'axis': _axis, 'title': _title, 'dim': _dim, 'value': _value, 'header': _header}[layer]()


# ---- geometry -------------------------------------------------------------------
def _layout():
	return parent.Synth.op('viz/layout')

def _rect(name: str) -> tuple:
	t = _layout()
	return tuple(float(t[name, c]) for c in ('x', 'y', 'w', 'h'))

def _plot(name: str) -> tuple:
	t = _layout()
	x, y, w, h = _rect(name)
	il, ib, ir, it = (float(t[name, c]) for c in ('il', 'ib', 'ir', 'it'))
	return x + il, y + ib, w - il - ir, h - ib - it

def _axes() -> dict:
	t = parent.Synth.op('viz/axes')
	return {t[r, 0].val: float(t[r, 1]) for r in range(1, t.numRows)}

def output_scale() -> float:
	"""Real pixels per design pixel (the dashboard's width / 1920)."""
	return float(parent.Synth.op('viz/glsl_dashboard').par.resolutionw) / 1920.0

def _left(x: float, yc: float, text: str, pt: float) -> list:
	"""Text starting at x, vertically centred on yc (design units in, real pixels out)."""
	s = output_scale()
	return [int(round(x * s)), int(round((yc - CENTER * pt) * s)), text]

def _right(x: float, yc: float, text: str, pt: float) -> list:
	return _left(x - len(text) * ADVANCE * pt, yc, text, pt)

def _center(x: float, yc: float, text: str, pt: float) -> list:
	return _left(x - 0.5 * len(text) * ADVANCE * pt, yc, text, pt)

def _logf(f: float) -> float:
	return math.log(f / FMIN) / math.log(FMAX / FMIN)

def _hz(f: float) -> str:
	return '%gk' % (f / 1000.0) if f >= 1000 else '%g' % f

def _title_y(name: str) -> float:
	x, y, w, h = _rect(name)
	return y + h - 19

def _date(i: int) -> str:
	"""Month index (0 = first observation) -> 'YYYY-MM'."""
	first = parent.Synth.op('data/clean_series')[1, 'date'].val
	m = int(first[:4]) * 12 + int(first[5:7]) - 1 + int(i)
	return '%04d-%02d' % (m // 12, m % 12 + 1)

def _first_last_year() -> tuple:
	t = parent.Synth.op('data/clean_series')
	return t[1, 'date'].val[:4], t[t.numRows - 1, 'date'].val[:4]


# ---- layers -----------------------------------------------------------------------
def _axis() -> list:
	a = _axes()
	rows = []
	pt = PT_AXIS
	x0, y0, w, h = _plot('series')
	v = a['ymin']
	while v <= a['ymax'] + 1e-6:
		rows.append(_right(x0 - 8, y0 + (v - a['ymin']) / (a['ymax'] - a['ymin']) * h, '%g' % v, pt))
		v += a['ystep']
	year = int(math.ceil(a['tmin'] / a['tstep']) * a['tstep'])
	while year <= a['tmax']:
		rows.append(_center(x0 + (year - a['tmin']) / (a['tmax'] - a['tmin']) * w, y0 - 16, str(year), pt))
		year += int(a['tstep'])
	x0, y0, w, h = _plot('scope')
	for v in (-1.0, -0.5, 0.0, 0.5, 1.0):
		rows.append(_right(x0 - 8, y0 + (v + SCOPE_RANGE) / (2 * SCOPE_RANGE) * h, '%+g' % v if v else '0', pt))
	for c in (0, 0.25, 0.5, 0.75, 1):
		rows.append(_center(x0 + c * w, y0 - 16, '%g' % c, pt))
	x0, y0, w, h = _plot('spectrum')
	for f in (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000):
		rows.append(_center(x0 + _logf(f) * w, y0 - 16, _hz(f), pt))
	for db in (0, -24, -48, -72, -96):
		rows.append(_right(x0 - 8, y0 + (db + 96) / 96.0 * h, str(db), pt))
	x0, y0, w, h = _plot('sonogram')
	for f in (50, 100, 200, 500, 1000, 2000, 5000, 10000):
		rows.append(_right(x0 - 8, y0 + _logf(f) * h, _hz(f), pt))
	for s in (8, 6, 4, 2, 0):
		rows.append(_center(x0 + (1 - s / SONO_SECONDS) * w, y0 - 16, 'now' if s == 0 else '-%d s' % s, pt))
	x0, y0, w, h = _plot('env')
	for v in (0, 0.5, 1):
		rows.append(_right(x0 - 8, y0 + v * h, '%g' % v, pt))
	for s in (4, 3, 2, 1, 0):
		rows.append(_center(x0 + (1 - s / ENV_SECONDS) * w, y0 - 16, 'now' if s == 0 else '-%d s' % s, pt))
	return rows


def _title() -> list:
	first, last = _first_last_year()
	frames = parent.Synth.op('engine/null_frames').numChans
	rows = []
	for name, text in TITLES.items():
		x, y, w, h = _rect(name)
		rows.append(_left(x + 14, _title_y(name), text.format(frames=frames, first=first, last=last), PT_TITLE))
	x, y, w, h = _rect('stats')
	rows.append(_left(x + w / 2 + 8, _title_y('stats'), 'WINDOW → WAVETABLE', PT_TITLE))
	return rows


def _dim() -> list:
	rows = []
	pt = PT_TEXT
	for name, text in CAPTIONS.items():
		x, y, w, h = _rect(name)
		rows.append(_right(x + w - 14, _title_y(name), text, pt))
	for name, (corner, entries) in LEGENDS.items():
		x0, y0, w, h = _plot(name)
		for i, text in enumerate(entries):
			yc = y0 + h - LEGEND_TOP - LEGEND_PITCH * i
			xs = x0 + 10 if corner == 'tl' else x0 + w - 150
			rows.append(_left(xs + LEGEND_TEXT - 10, yc, text, pt))
	x, y, w, h = _rect('stats')
	for i, (_, label) in enumerate(SERIES_STATS):
		rows.append(_left(x + 16, y + h - STATS_TOP - STATS_PITCH * i, label, pt))
	for i, label in enumerate(WINDOW_STATS):
		rows.append(_left(x + w / 2 + 8, y + h - STATS_TOP - STATS_PITCH * i, label, pt))
	x, y, w, h = _rect('header')
	rows.append(_left(x + 440, y + h / 2 - 1,
		'Deutsche Bundesbank time series, monthly EUR mn  →  single-cycle wavetable  →  sound', pt))
	return rows


def _value() -> list:
	rows = []
	pt = PT_TEXT
	synth = parent.Synth
	win = synth.op('engine/script_window')
	values = synth.op('engine/null_series')['value_bn'].numpyArray().astype(np.float64)
	start, length = float(win['start']), int(win['length'])
	hz, kmax = float(win['hz']), int(win['kmax'])
	note = synth.op('engine/wavetable_lib').module.note_name(synth.par.Note.eval() + synth.par.Fine.eval() / 100.0)
	i0 = int(round(start))
	seg = values[i0:i0 + length]
	d0, d1 = _date(i0), _date(i0 + length - 1)

	# stats panel: full series (static) and the current window / table (live)
	x, y, w, h = _rect('stats')
	stats = synth.op('data/stats_series')
	for i, (key, _) in enumerate(SERIES_STATS):
		cell = stats[key, 'short']
		rows.append(_right(x + w / 2 - 12, y + h - STATS_TOP - STATS_PITCH * i, cell.val if cell else '-', pt))
	slope = np.polyfit(np.arange(len(seg)), seg, 1)[0] if len(seg) > 2 else 0.0
	table = synth.op('engine/null_wavetable')['shaped'].numpyArray().astype(np.float64)
	rms = float(np.sqrt(np.mean(table * table))) or 1e-9
	crest = float(np.abs(table).max()) / rms
	harm = synth.op('engine/null_harmonics')
	def centroid(name: str) -> float:
		p = 10.0 ** (harm[name].numpyArray().astype(np.float64) / 10.0)
		return float((np.arange(1, len(p) + 1) * p).sum() / max(p.sum(), 1e-12))
	cycle_months = length if synth.par.Loopmode.eval() == 'forward' else 2 * length - 2
	annual = cycle_months / 12.0
	years_per_s = cycle_months * hz / 12.0
	level = 20.0 * math.log10(max(float(synth.op('engine/analyze_rms')[0]), 1e-6))
	window_values = [
		'%s→%s' % (d0, d1),
		'%d m = 1 cycle' % length,
		'%.1f / %.1f bn' % (seg.mean(), seg.std()),
		'%+.1f %%/yr' % (slope * 12.0 / max(seg.mean(), 1e-9) * 100.0),
		'%.1f–%.1f bn' % (seg.min(), seg.max()),
		'%.2f (%.1f dB)' % (crest, 20.0 * math.log10(crest)),
		'h%.1f → h%.1f' % (centroid('raw_db'), centroid('shaped_db')),
		'h%.1f = %.0f Hz' % (annual, annual * hz),
		'%d < Nyq' % kmax if synth.par.Bandlimit.eval() else 'all (aliasing)',
		'1 s = %s yr' % ('%.1fk' % (years_per_s / 1000.0) if years_per_s >= 1000 else '%.0f' % years_per_s),
		'%s · %.1f Hz' % (note, hz),
		'%+.1f dBFS' % level,
	]
	for i, text in enumerate(window_values):
		rows.append(_right(x + w - 16, y + h - STATS_TOP - STATS_PITCH * i, text, pt))

	# series panel: dates at the window edges
	a = _axes()
	x0, y0, pw, ph = _plot('series')
	def tx(i: float) -> float:
		return x0 + (a['t0'] + i / 12.0 - a['tmin']) / (a['tmax'] - a['tmin']) * pw
	rows.append(_left(tx(start - 0.5) + 6, y0 + ph - 12, d0, pt))
	rows.append(_right(tx(start + length - 0.5) - 6, y0 + ph - 12, d1, pt))

	# 3D panel: which windows are playing
	x, y, w, h = _rect('wt3d')
	rows.append(_left(x + 14, y + 14, 'now playing  %s → %s' % (d0, d1), pt))

	# spectrum: fundamental and filter cutoff markers
	x0, y0, pw, ph = _plot('spectrum')
	cutoff = float(synth.op('engine/expr_cutoff')[0])
	if FMIN <= hz <= FMAX:
		rows.append(_center(x0 + _logf(hz) * pw, y0 + 12, 'f0', pt))
	xc = x0 + _logf(min(max(cutoff, FMIN), FMAX)) * pw
	text = 'fc %.0f Hz' % cutoff
	rows.append(_left(xc + 6, y0 + ph - 82, text, pt) if xc < x0 + pw - 110 else _right(xc - 6, y0 + ph - 82, text, pt))

	# envelopes: side column right of the plot, swatches drawn by glsl_dashboard on rows 0, 1, 4
	x0, y0, pw, ph = _plot('env')
	p = synth.par
	def s(v: float) -> str:
		return ('%.2f' % v).replace('0.', '.', 1) if v < 1 else '%.1f' % v
	side = [ENV_LEGEND_GATE,
			'amp env',
			'  A %s   D %s' % (s(p.Attack.eval()), s(p.Decay.eval())),
			'  S %s   R %s' % (s(p.Sustain.eval()), s(p.Release.eval())),
			'filter env',
			'  A %s   D %s' % (s(p.Fattack.eval()), s(p.Fdecay.eval())),
			'  S %s   R %s' % (s(p.Fsustain.eval()), s(p.Frelease.eval())),
			'  depth %+.1f oct' % p.Envamount.eval(),
			'  fc %.0f Hz' % cutoff]
	for i, text in enumerate(side):
		rows.append(_left(x0 + pw + 14 + LEGEND_TEXT - 10, y0 + ph - LEGEND_TOP - LEGEND_PITCH * i, text, pt))

	# header: live readout
	x, y, w, h = _rect('header')
	gate = float(synth.op('engine/expr_gate')[0]) > 0.5
	rows.append(_right(x + w - 40, y + h / 2 - 1, '%s  %.1f Hz   fc %5.0f Hz   %+5.1f dBFS   gate %s' % (
		note, hz, cutoff, level, 'ON ' if gate else 'off'), pt))
	return rows


def _header() -> list:
	x, y, w, h = _rect('header')
	return [_left(x + 16, y + h / 2, 'MORTGAGE  WAVETABLE', 22)]
