"""
script_harmonics: harmonic spectrum of the current cycle (NUM_HARMONICS samples).

Input 0: null_wavetable. Sample k is harmonic k+1, in dB relative to the
strongest harmonic of that channel (floor -90 dB).
"""
import numpy as np

def onCook(scriptOp: scriptCHOP):
	lib = op('wavetable_lib').module
	src = scriptOp.inputs[0] if scriptOp.inputs else None
	scriptOp.clear()
	scriptOp.isTimeSlice = False
	scriptOp.numSamples = lib.NUM_HARMONICS
	if src is None or src.numSamples < 2 * lib.NUM_HARMONICS:
		return
	for name in ('shaped', 'raw'):
		if src[name] is not None:
			db = lib.harmonics_db(src[name].numpyArray().astype(np.float64))
			scriptOp.appendChan(name + '_db').vals = db.astype(np.float32)
	return
