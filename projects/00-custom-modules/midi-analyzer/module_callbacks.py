# Written by Save Module from midi_analyzer.tox so git shows readable diffs. Edit this
# DAT inside midi_analyzer in TouchDesigner, then press Save Module; edits here change nothing.

# Pulse actions of the MIDI analyzer: one dispatcher, one handler per pulse, Save Module among them.

import os

def _learn(comp):
	"""Map the next CC or note that arrives to Learn Name."""
	comp.op('ot_engine').module.Learn(comp)

def _reset(comp):
	"""Forget the stored knob values, notes and counts, and restart the clock."""
	comp.op('ot_engine').module.Reset(comp)

def _restartClock(comp):
	"""Put the clock on beat 0."""
	comp.op('ot_engine').module.RestartClock(comp)

def _saveModule(comp):
	"""Save a clean copy of the module (no bindings to the host, default values) to its External
	.tox Path, with readable text versions beside it when Embody is in the project."""
	path = comp.par.externaltox.eval()
	if not path:
		debug('%s: set the External .tox Path on the Common page first' % comp.name)
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
		# Hosts load the module from this .tox, so their Embody must not copy it into their .tdxn.
		copy.tags.add('tdxn_exclude')
		for part in copy.findChildren(name='envoy_bot_*', includeUtility=True):
			part.destroy()  # the AI assistant's on-screen marker, never part of the module
		copy.save(path)
	finally:
		copy.destroy()
	embody = getattr(op, 'Embody', None)
	if embody is not None:
		_writeSnapshot(comp, path, embody)
	debug('%s: saved' % comp.name, path)

def _generated(comp):
	return ('# Written by Save Module from %s.tox so git shows readable diffs. Edit this\n'
		'# DAT inside %s in TouchDesigner, then press Save Module; edits here change nothing.\n\n') % (comp.name, comp.name)

def _writeSnapshot(comp, path, embody):
	"""Write the saved .tox as text beside it, for git diffs: the network as a .tdxn, each script
	DAT as a .py and each table as a .tsv. Embody's exporter skips /sys, so the .tox is loaded next
	to the module for the export and removed again."""
	folder = os.path.dirname(path)
	snapshot = os.path.splitext(path)[0] + '.tdxn'
	shown = comp.parent().loadTox(path)
	try:
		shown.allowCooking = False
		if 'tdxn_exclude' in shown.tags:
			shown.tags.remove('tdxn_exclude')  # export the module itself, not an excluded shell
		for dat in shown.children:
			if not dat.isDAT or 'tdxn_exclude:dat_content' in dat.tags:
				continue  # runtime content (MIDI logs, generated names) stays out of git
			if dat.isText and dat.text.strip():
				dat.tags.add('tdxn_exclude:dat_content')  # its text goes to its own .py instead
				with open(os.path.join(folder, dat.name + '.py'), 'w', encoding='utf-8', newline='\n') as f:
					f.write(_generated(comp) + dat.text.replace('\r\n', '\n'))
			elif dat.OPType == 'tableDAT':
				dat.tags.add('tdxn_exclude:dat_content')  # and a table to its own .tsv
				with open(os.path.join(folder, dat.name + '.tsv'), 'w', encoding='utf-8', newline='\n') as f:
					f.write(''.join('\t'.join(c.val for c in row) + '\n' for row in dat.rows()))
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
	'Learn': _learn,
	'Reset': _reset,
	'Restartclock': _restartClock,
	'Savemodule': _saveModule,
}

def onPulse(par):
	handler = _PULSES.get(par.name)
	if handler is None:
		debug('%s: no handler for pulse' % par.owner.name, par.name)
		return
	handler(par.owner)
	return
