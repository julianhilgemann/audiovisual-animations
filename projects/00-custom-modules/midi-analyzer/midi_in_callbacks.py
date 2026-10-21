# Written by Save Module from midi_analyzer.tox so git shows readable diffs. Edit this
# DAT inside midi_analyzer in TouchDesigner, then press Save Module; edits here change nothing.

# Every MIDI message from midi_in, clock ticks included, goes to ot_engine.

def onReceiveMIDI(dat, event):
	op('ot_engine').module.Receive(parent.Midi, event.byteData)
	return
