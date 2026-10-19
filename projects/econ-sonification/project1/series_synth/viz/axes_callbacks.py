"""
axes: plot ranges shared by glsl_dashboard (uniform expressions) and labels_lib.

One row per value: series y axis (EUR bn, rounded to a tidy step) and the time
axis (whole years around the data). Recooks only when the series changes.
"""
import math

def _nice_step(span: float, ticks: int = 6) -> float:
	raw = span / max(ticks, 1)
	mag = 10.0 ** math.floor(math.log10(raw))
	for m in (1.0, 2.0, 2.5, 5.0, 10.0):
		if raw <= m * mag:
			return m * mag
	return 10.0 * mag

def onCook(scriptOp: scriptDAT):
	scriptOp.clear()
	scriptOp.appendRow(['name', 'value'])
	series = op('../engine/null_series')
	if series is None or series.numSamples < 2 or series['value_bn'] is None:
		rows = {'ymin': 0, 'ymax': 1, 'ystep': 0.5, 'tmin': 0, 'tmax': 1, 't0': 0, 'n': 1, 'tstep': 1}
	else:
		v = series['value_bn'].vals
		t = series['t'].vals
		step = _nice_step(max(v) - min(v))
		span_years = t[-1] - t[0]
		rows = {
			'ymin': math.floor(min(v) / step) * step,
			'ymax': math.ceil(max(v) / step) * step,
			'ystep': step,
			'tmin': math.floor(t[0]),
			'tmax': math.ceil(t[-1] + 1.0 / 24.0),
			't0': t[0],
			'n': len(v),
			'tstep': 1 if span_years <= 12 else (2 if span_years <= 30 else 5),
		}
	for name, value in rows.items():
		scriptOp.appendRow([name, '%.10g' % value])
	return
