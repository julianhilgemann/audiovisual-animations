"""
script_window: where the loop window sits right now (one sample per channel).

Input 0: speed_scan (accumulated scan offset in months).
Channels: start, length, span (months), scanfrac (start / span), t0, t1
(decimal years of the window edges), hz (target pitch), kmax (highest harmonic
below Nyquist at that pitch), n (months in the series).
"""

def onCook(scriptOp: scriptCHOP):
	lib = op('wavetable_lib').module
	p = parent.Synth.par
	series = op('null_series')
	n = series.numSamples if series.numChans else 0
	scan = scriptOp.inputs[0][0].eval() if (scriptOp.inputs and p.Scan.eval()) else None
	start, length, span = lib.window_bounds(max(n, 4), p.Start.eval(), p.Length.eval(), scan)
	hz = lib.note_to_hz(p.Note.eval(), p.Fine.eval())
	t_first = float(op('in_series')[1, 't']) if n else 0.0
	values = {
		'start': start, 'length': length, 'span': span,
		'scanfrac': start / span if span > 0 else 0.0,
		't0': t_first + start / 12.0, 't1': t_first + (start + length) / 12.0,
		'hz': hz, 'kmax': lib.harmonic_limit(hz, lib.TABLE_SIZE), 'n': n,
	}
	scriptOp.clear()
	scriptOp.isTimeSlice = False
	scriptOp.numSamples = 1
	for name, value in values.items():
		scriptOp.appendChan(name)[0] = value
	return
