"""
parexec_reactor: custom-parameter dispatcher for the AudioReactor COMP.
Every pulse / value change is routed to AudioReactorExt._on<Par>Pulse or
_on<Par>ValueChange when such a handler exists; nothing else lives here.
The read-only Mon* monitor parameters are excluded (they change every frame).
"""

def onValueChange(par, prev):
	parent.Reactor.ext.Reactor.dispatchValueChange(par, prev)
	return

def onPulse(par):
	parent.Reactor.ext.Reactor.dispatchPulse(par)
	return
