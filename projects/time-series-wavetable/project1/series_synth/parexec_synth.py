"""
parexec_synth: custom-parameter dispatcher for the SeriesSynth COMP.
Every pulse / value change is routed to SeriesSynthExt._on<Par>Pulse or
_on<Par>ValueChange when such a handler exists; nothing else lives here.
"""

def onValueChange(par, prev):
	parent.Synth.ext.SeriesSynth.dispatchValueChange(par, prev)
	return

def onPulse(par):
	parent.Synth.ext.SeriesSynth.dispatchPulse(par)
	return
