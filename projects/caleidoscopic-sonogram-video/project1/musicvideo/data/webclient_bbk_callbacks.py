"""
webclientDAT callbacks -- every hook runs on the MAIN thread.
The response body is handed to the SeriesSynth extension, which stores it in
raw_csv; clean_series parses it from there.
"""
from typing import Dict, Any

def onConnect(dat: webclientDAT, id: int):
	return

def onDisconnect(dat: webclientDAT, id: int):
	return

def onResponse(dat: webclientDAT, statusCode: Dict[str, Any],
			   headerDict: Dict[str, str], data: bytes, id: int):
	parent.Reactor.ext.Reactor.handleResponse(statusCode, data)
	return

def onError(dat: webclientDAT, id: int, url: str, error: Exception):
	parent.Reactor.ext.Reactor.handleResponse({'code': -1, 'message': str(error)}, b'')
	return
