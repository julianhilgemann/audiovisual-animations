"""
parexec_caleido: custom-parameter dispatcher for the caleidoscopic_sonogram_video COMP.
Every pulse / value change is routed to CaleidoscopicSonogramVideoExt._on<Par>Pulse or
_on<Par>ValueChange when such a handler exists; nothing else lives here.
The read-only Mon* monitor parameters are excluded (they change every frame).
"""

def onValueChange(par, prev):
	parent.Caleido.ext.Caleido.dispatchValueChange(par, prev)
	return

def onPulse(par):
	parent.Caleido.ext.Caleido.dispatchPulse(par)
	return
