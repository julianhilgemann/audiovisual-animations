"""
parexec_wavetable: custom-parameter dispatcher for the time_series_wavetable COMP.
Every pulse / value change is routed to TimeSeriesWavetableExt._on<Par>Pulse or
_on<Par>ValueChange when such a handler exists; nothing else lives here.
"""

def onValueChange(par, prev):
	parent.Wavetable.ext.Wavetable.dispatchValueChange(par, prev)
	return

def onPulse(par):
	parent.Wavetable.ext.Wavetable.dispatchPulse(par)
	return
