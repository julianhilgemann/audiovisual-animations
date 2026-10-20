"""
script_window: where the loop window sits right now (one sample per channel).

Input 0: speed_scan (accumulated scan offset in months; its rate already holds
the scan direction and the camera-motion boost).
The visitor's horizontal position (select_features cx, gated by presence)
offsets Window Start by up to +-Posstart months.
Channels: start, length, span (months), scanfrac (start / span), t0, t1
(decimal years of the window edges), hz (target pitch), n (months in the series).
"""

def onCook(scriptOp: scriptCHOP):
	lib = op('wavetable_lib').module
	p = parent.Reactor.par
	series = op('null_series')
	n = series.numSamples if series.numChans else 0
	feat = op('select_features')
	offset = 0.0
	if feat is not None and feat.numChans:
		cx = feat['cx'].eval() if feat['cx'] is not None else 0.5
		presence = feat['presence'].eval() if feat['presence'] is not None else 0.0
		offset = p.Posstart.eval() * (cx - 0.5) * 2.0 * presence
	scan = scriptOp.inputs[0][0].eval() if scriptOp.inputs else None
	if not p.Scan.eval() and abs(scan or 0.0) < 1e-6:
		scan = None
	wrap = p.Scandir.eval() != 'pingpong'
	start, length, span = lib.window_bounds(max(n, 4), p.Start.eval() + offset, p.Length.eval(), scan, wrap)
	hz = lib.note_to_hz(p.Note.eval(), p.Fine.eval())
	t_first = float(op('in_series')[1, 't']) if n else 0.0
	values = {
		'start': start, 'length': length, 'span': span,
		'scanfrac': start / span if span > 0 else 0.0,
		't0': t_first + start / 12.0, 't1': t_first + (start + length) / 12.0,
		'hz': hz, 'n': n,
	}
	scriptOp.clear()
	scriptOp.isTimeSlice = False
	scriptOp.numSamples = 1
	for name, value in values.items():
		scriptOp.appendChan(name)[0] = value
	return
