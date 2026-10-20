"""
parexec_sonogram: custom-parameter dispatcher for the touch_the_sonogram COMP.
Every pulse / value change is routed to TouchTheSonogramExt._on<Par>Pulse or
_on<Par>ValueChange when such a handler exists; nothing else lives here.
The read-only Mon* monitor parameters are excluded (they change every frame).
"""

def onValueChange(par, prev):
	parent.Sonogram.ext.Sonogram.dispatchValueChange(par, prev)
	return

def onPulse(par):
	parent.Sonogram.ext.Sonogram.dispatchPulse(par)
	return
