"""
script_wavetable: the playable single cycle (TABLE_SIZE samples).

Input 0: script_window. Channel 0 'shaped' is what lookup_wave plays (shaped and
band-limited); 'raw' is the normalized window before the shaper, for display.
"""
import numpy as np

def onCook(scriptOp: scriptCHOP):
	lib = op('wavetable_lib').module
	scriptOp.clear()
	scriptOp.isTimeSlice = False
	scriptOp.numSamples = lib.TABLE_SIZE
	shaped = scriptOp.appendChan('shaped')
	raw = scriptOp.appendChan('raw')
	series = op('null_series')
	win = scriptOp.inputs[0] if scriptOp.inputs else None
	if win is None or not series.numChans or series.numSamples < 8:
		return
	values = series['value_bn'].numpyArray().astype(np.float64)
	cfg = lib.read_config(parent.Synth.par)
	r, s = lib.build_cycle(values, win['start'].eval(), int(win['length'].eval()), cfg, win['hz'].eval())
	shaped.vals = s.astype(np.float32)
	raw.vals = r.astype(np.float32)
	return
