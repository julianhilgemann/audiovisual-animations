"""
script_frames: the 3D wavetable stack -- NUM_FRAMES cycles of FRAME_SIZE samples.

Frame k is the cycle of a window starting k / (NUM_FRAMES - 1) of the way
through the history, processed exactly like the playing cycle. Reads no scan
position, so it recooks only when the series or a wavetable setting changes.
"""
import numpy as np

def onCook(scriptOp: scriptCHOP):
	lib = op('wavetable_lib').module
	p = parent.Synth.par
	scriptOp.clear()
	scriptOp.isTimeSlice = False
	scriptOp.numSamples = lib.FRAME_SIZE
	series = op('null_series')
	if not series.numChans or series.numSamples < 8:
		return
	values = series['value_bn'].numpyArray().astype(np.float64)
	_, length, span = lib.window_bounds(len(values), 0.0, p.Length.eval(), None)
	cfg = lib.read_config(p)
	hz = lib.note_to_hz(p.Note.eval(), p.Fine.eval())
	for k in range(lib.NUM_FRAMES):
		start = span * k / float(lib.NUM_FRAMES - 1)
		_, shaped = lib.build_cycle(values, start, length, cfg, hz, size=lib.FRAME_SIZE)
		scriptOp.appendChan('f%02d' % k).vals = shaped.astype(np.float32)
	return
