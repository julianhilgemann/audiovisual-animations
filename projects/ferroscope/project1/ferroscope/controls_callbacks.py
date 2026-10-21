# Pulse actions for the FerroScope control panel: one dispatcher, one handler per pulse.

import re

# Built-in preset labels; stored presets are labelled with their own name.
_PRESET_LABELS = {
	'factory': 'Factory Default',
	'mylook': 'My Look (2026-10-12)',
	'blackferro': 'Black Ferrofluid',
	'hexhive': 'Hex Hive',
	'liquidmarble': 'Liquid Marble',
	'mirrorface': 'Mirror Face',
	'sonobars': 'Sonogram Bars',
	'fractalbloom': 'Fractal Bloom',
	'hexmandala': 'Hex Mandala',
}

def _clearSonogram(comp):
	"""Erase the sonogram history."""
	comp.op('feedback_sono').par.resetpulse.pulse()

def _relearnBackground(comp):
	"""Adopt the current camera image as the empty room and clear the pull field."""
	comp.op('feedback_state').par.resetpulse.pulse()

def _openWindow(comp):
	"""Open the output window (Esc over it closes it)."""
	comp.op('window_out').par.winopen.pulse()

def _closeWindow(comp):
	"""Close the output window."""
	comp.op('window_out').par.winclose.pulse()

def _deckPulse(name):
	"""A handler that presses the same pulse on source_deck, the shared module that owns the
	sources, the YouTube downloads and the transport."""
	def press(comp):
		comp.op('source_deck').par[name].pulse()
	return press

def _refreshPresetMenu(comp):
	"""Rebuild the Preset menu from the columns of the presets table."""
	table = comp.op('presets')
	names = [cell.val for cell in table.row(0)[1:]]
	comp.par.Preset.menuNames = names
	comp.par.Preset.menuLabels = [_PRESET_LABELS.get(n, n) for n in names]

def _applyPreset(comp):
	"""Set every parameter listed in the presets table from the chosen preset's column.
	A blank cell leaves that parameter alone (look presets keep calibration that way)."""
	table = comp.op('presets')
	name = comp.par.Preset.eval()
	if table.col(name) is None:
		debug('FerroScope: no preset column named', name)
		return
	for row in range(1, table.numRows):
		par = comp.par[table[row, 0].val]
		cell = table[row, name].val
		if par is None or cell == '':
			continue
		if par.isMenu or par.isString:
			par.val = cell
		elif par.isInt or par.isToggle:
			par.val = int(float(cell))
		else:
			par.val = float(cell)

def _storePreset(comp):
	"""Write every current setting listed in the presets table into a column named by
	New Preset Name (created if new), then add it to the Preset menu and select it."""
	table = comp.op('presets')
	name = re.sub(r'[^a-z0-9]', '', comp.par.Presetname.eval().lower()) or 'mypreset'
	if name == 'factory':
		debug('FerroScope: Factory Default cannot be overwritten; choose another name')
		return
	if table.col(name) is None:
		table.appendCol([name] + [''] * (table.numRows - 1))
	for row in range(1, table.numRows):
		par = comp.par[table[row, 0].val]
		if par is None:
			continue
		value = par.eval()
		if par.isToggle:
			value = int(value)
		table[row, name] = value
	_refreshPresetMenu(comp)
	comp.par.Preset = name

_PULSES = {
	'Resetsono': _clearSonogram,
	'Relearnbg': _relearnBackground,
	'Openwindow': _openWindow,
	'Closewindow': _closeWindow,
	'Videorestart': _deckPulse('Videorestart'),
	'Audiorestart': _deckPulse('Audiorestart'),
	'Videodownload': _deckPulse('Videodownload'),
	'Audiodownload': _deckPulse('Audiodownload'),
	'Applypreset': _applyPreset,
	'Storepreset': _storePreset,
}

def onPulse(par):
	handler = _PULSES.get(par.name)
	if handler is None:
		debug('FerroScope: no handler for pulse', par.name)
		return
	handler(par.owner)
	return
