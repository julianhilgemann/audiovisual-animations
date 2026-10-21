# Written by Save Module from source_deck.tox so git shows readable diffs. Edit this
# DAT inside source_deck in TouchDesigner, then press Save Module; edits here change nothing.

# Pulse actions for the source deck: one dispatcher, one handler per pulse.

import os

def _downloadVideo(comp):
	"""Fetch the YouTube Video Link and make it the video source."""
	comp.op('youtube_fetch').module.Download(comp, 'video')

def _downloadAudio(comp):
	"""Fetch the YouTube Audio Link (or the video link) and make it the audio source."""
	comp.op('youtube_fetch').module.Download(comp, 'audio')

def _restartVideo(comp):
	"""Jump the video playhead back to the start (linked audio jumps with it)."""
	comp.op('transport').module.Restart(comp, 'video')

def _restartAudio(comp):
	"""Jump the audio playhead back to the start (linked video jumps with it)."""
	comp.op('transport').module.Restart(comp, 'audio')

def _saveModule(comp):
	"""Save a clean copy of the deck (no bindings to the host, default values) to its External
	.tox Path, with a readable .tdxn snapshot beside it when Embody is in the project."""
	path = comp.par.externaltox.eval()
	if not path:
		debug('Source deck: set the External .tox Path on the Common page first')
		return
	path = os.path.join(project.folder, path)
	copy = op('/sys/quiet').copy(comp, name=comp.name)
	try:
		for par in copy.customPars:
			if par.isPulse:
				continue
			par.bindExpr = ''  # TD keeps bind and expression text even in constant mode
			par.expr = ''
			par.mode = ParMode.CONSTANT
			par.val = par.default
		for name in ('externaltox', 'enableexternaltox', 'reloadcustom'):
			copy.par[name].reset()
		# Hosts load the deck from this .tox, so their Embody must not copy it into their .tdxn.
		copy.tags.add('tdxn_exclude')
		for part in copy.findChildren(name='envoy_bot_*', includeUtility=True):
			part.destroy()  # the AI assistant's on-screen marker, never part of the module
		copy.save(path)
	finally:
		copy.destroy()
	embody = getattr(op, 'Embody', None)
	if embody is not None:
		_writeSnapshot(comp, path, embody)
	debug('Source deck: saved', path)

_GENERATED = ('# Written by Save Module from source_deck.tox so git shows readable diffs. Edit this\n'
	'# DAT inside source_deck in TouchDesigner, then press Save Module; edits here change nothing.\n\n')

def _writeSnapshot(comp, path, embody):
	"""Write the saved .tox as text beside it, for git diffs: the network as a .tdxn and each
	script DAT as a .py. Embody's exporter skips /sys, so the .tox is loaded next to the deck
	for the export and removed again."""
	folder = os.path.dirname(path)
	snapshot = os.path.splitext(path)[0] + '.tdxn'
	shown = comp.parent().loadTox(path)
	try:
		shown.allowCooking = False
		if 'tdxn_exclude' in shown.tags:
			shown.tags.remove('tdxn_exclude')  # export the module itself, not an excluded shell
		for dat in [d for d in shown.children if d.isDAT and d.isText and d.text.strip()]:
			dat.tags.add('tdxn_exclude:dat_content')  # its text goes to its own .py instead
			with open(os.path.join(folder, dat.name + '.py'), 'w', encoding='utf-8', newline='\n') as f:
				f.write(_GENERATED + dat.text.replace('\r\n', '\n'))
		embody.ext.TDXN.ExportNetwork(root_path=shown.path, include_dat_content=False,
			output_file=snapshot, interactive=False)
	finally:
		shown.destroy()
	# Drop the lines that change with every save or host, so a diff shows only real changes.
	with open(snapshot, encoding='utf-8') as f:
		lines = [line for line in f if not line.startswith(('source_file:', 'exported_at:', 'network_path:'))]
	with open(snapshot, 'w', encoding='utf-8', newline='\n') as f:
		f.writelines(lines)

_PULSES = {
	'Videodownload': _downloadVideo,
	'Audiodownload': _downloadAudio,
	'Videorestart': _restartVideo,
	'Audiorestart': _restartAudio,
	'Savemodule': _saveModule,
}

def onPulse(par):
	handler = _PULSES.get(par.name)
	if handler is None:
		debug('Source deck: no handler for pulse', par.name)
		return
	handler(par.owner)
	return
