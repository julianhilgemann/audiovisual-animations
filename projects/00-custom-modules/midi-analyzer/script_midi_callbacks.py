# Written by Save Module from midi_analyzer.tox so git shows readable diffs. Edit this
# DAT inside midi_analyzer in TouchDesigner, then press Save Module; edits here change nothing.

# Script CHOP of the MIDI analyzer: one sample per channel from ot_engine, every frame (the
# Frame parameter follows absTime.frame). rename_midi gives the channels their names.

def onSetupParameters(scriptOp):
	return

def onPulse(par):
	return

def onCook(scriptOp):
	op('ot_engine').module.Cook(parent.Midi, scriptOp)
	return
