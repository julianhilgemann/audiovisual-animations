"""
script_scope: trigger-synced oscilloscope -- the last whole cycle of the output.

Input 0: trail_scope = merge of [null_audio, audioosc_phase] over the last 8192
samples at 44.1 kHz. The oscillator ramp (-1..1) drops by ~2 at every cycle
start; the latest two complete cycles are resampled to SCOPE_SIZE points, so the
trace stands still like a triggered hardware scope while the envelopes and the
filter animate it. Channels are read by merge position: the Audio Oscillator
CHOP ignores the Common-page rename, so its ramp keeps the name chan1.
"""
import numpy as np

SCOPE_SIZE = 512

def onCook(scriptOp: scriptCHOP):
	scriptOp.clear()
	scriptOp.isTimeSlice = False
	scriptOp.numSamples = SCOPE_SIZE
	out = scriptOp.appendChan('scope')
	src = scriptOp.inputs[0] if scriptOp.inputs else None
	if src is None or src.numChans < 2 or src.numSamples < 64:
		return
	audio = src[0].numpyArray()      # merge input 0: null_audio
	phase = src[1].numpyArray()      # merge input 1: audioosc_phase ramp
	starts = np.nonzero(np.diff(phase) < -1.0)[0] + 1
	if len(starts) >= 2:
		seg = audio[starts[-2]:starts[-1]]
	else:
		seg = audio[-SCOPE_SIZE:]
	x = np.linspace(0.0, len(seg) - 1.0, SCOPE_SIZE)
	out.vals = np.interp(x, np.arange(len(seg), dtype=np.float64), seg).astype(np.float32)
	return
