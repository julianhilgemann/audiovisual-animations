# Written by Save Module from midi_analyzer.tox so git shows readable diffs. Edit this
# DAT inside midi_analyzer in TouchDesigner, then press Save Module; edits here change nothing.

# MIDI engine of the MIDI analyzer. midi_in hands every message to Receive(); script_midi calls
# Cook() once a frame, which turns the state into named channels, one sample each, every value 0-1
# except the counts, clk_bpm, clk_beat, clk_bar and clk_step.
#
# Where the channel names come from:
# - The CC map (the CC Map table; ot_cc inside the module by default, the Octatrack's map from its
#   manual, appendix C). Track rows become t1_<name> to t8_<name>, read on the Audio Track
#   Channels; global rows (crossfader, scenes, MIDI track mutes) are read on any channel.
# - MIDI Track Channels: notes, pitch bend and pressure there become mt1_ to mt8_. The Octatrack
#   only sends notes from its MIDI tracks (and from trig keys pressed live), never from sequenced
#   audio-track trigs.
# - The custom map (the Custom Map table; custom_map inside the module by default) names single
#   notes and extra CCs: other gear, or what Learn adds. Channel 0 means any channel.
#
# Knob CCs are smoothed by CC Smoothing. Notes give a gate (velocity while held), the velocity
# and note number of the last note, a trigger (1 for the frame after a note-on), an envelope that
# jumps to the velocity and decays, and a hit count. The clock locks to MIDI clock and transport
# (start, stop, continue, song position) while ticks arrive and runs at Internal BPM otherwise.
#
# A device only sends a knob's value when the knob moves, so the last values are kept in the
# project's root storage, one entry per analyzer path: module storage is replaced on every reload.

import math
import time
from collections import deque

import numpy as np

_LANE_FIELDS = ('gate', 'vel', 'note', 'trig', 'env', 'count', 'bend', 'press')
_KEY_FIELDS = ('', '_trig', '_env', '_count')
_EXTRA = ('pattern', 'pattern_num', 'pattern_trig', 'scene_trig', 'note_trig', 'note_env')
_CLOCK = ('clk_bpm', 'clk_run', 'clk_ext', 'clk_beat', 'clk_phase', 'clk_bar', 'clk_bar_phase',
	'clk_phrase_phase', 'clk_step', 'clk_beat_trig', 'clk_bar_trig', 'clk_step_trig')
_BEAT_WRAP = 3072.0  # clk_beat wraps here: divisible by 1-4, 6, 8, 12, 16 ... 1024, and small enough for float32
_CLOCK_TIMEOUT = 0.5  # seconds without a tick before the MIDI clock counts as gone
_NOTE_NAMES = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')

_engines = {}

def Receive(comp, data):
	"""Apply one raw MIDI message (status byte first) to the engine of comp."""
	if data:
		_engine(comp).receive(comp, bytes(data))

def Cook(comp, scriptOp):
	"""Write this frame's channels into scriptOp (a Script CHOP) and keep the channel names current."""
	engine = _engine(comp)
	values = engine.cook(comp)
	scriptOp.copyNumpyArray(values.reshape(-1, 1))

def Learn(comp):
	"""Map the next CC or note (Learn Type) that arrives to Learn Name in the custom map."""
	engine = _engine(comp)
	engine.learning = comp.par.Learnname.eval().strip() or 'learn%d' % CustomMap(comp).numRows
	engine.learnType = comp.par.Learntype.eval()
	what = {'cc': 'move a knob', 'note': 'play a note', 'any': 'move a knob or play a note'}[engine.learnType]
	comp.par.Learnstatus = 'Waiting: %s for %s' % (what, engine.learning)

def Reset(comp):
	"""Forget all knob values, notes, counts and the stored values, and restart the clock."""
	root.unstore(_storeKey(comp))
	_engines.pop(comp.id, None)

def CcMap(comp):
	"""The CC map in use: the CC Map table, or the module's own ot_cc."""
	return comp.par.Ccmap.eval() or comp.op('ot_cc')

def CustomMap(comp):
	"""The custom map in use: the Custom Map table, or the module's own custom_map."""
	return comp.par.Custommap.eval() or comp.op('custom_map')

def _storeKey(comp):
	return 'midi_analyzer_values:' + comp.path

def RestartClock(comp):
	"""Put the clock back on beat 0 (the next MIDI start or song position does the same)."""
	engine = _engine(comp)
	engine.beat = engine.prevBeat = 0.0

def _engine(comp):
	engine = _engines.get(comp.id)
	if engine is None:
		engine = _engines[comp.id] = _Engine(comp)
	return engine

def _channels(text, count=8):
	"""Parse a list of MIDI channels ('1 2 3 ...'); missing or invalid entries are 0 (off)."""
	out = []
	for token in text.replace(',', ' ').split()[:count]:
		try:
			ch = int(token)
		except ValueError:
			ch = 0
		out.append(ch if 1 <= ch <= 16 else 0)
	return out + [0] * (count - len(out))

def _noteName(note):
	return '%s%d' % (_NOTE_NAMES[note % 12], note // 12 - 1)

class _Layout:
	"""Channel names and the lookups from incoming messages to output slots."""
	def __init__(self, comp):
		self.names = []
		kinds = []
		self.cc = {}  # (channel, cc) -> slots; channel 0 matches any channel
		def add(name, kind='calc'):
			self.names.append(name)
			kinds.append(kind)
			return len(self.names) - 1

		spec = [(int(r[0].val), r[1].val, r[2].val, r[3].val) for r in CcMap(comp).rows()[1:] if r[0].val.strip().isdigit()]
		for t, ch in enumerate(_channels(comp.par.Trackchannels.eval())):
			for cc, name, scope, kind in spec:
				if scope == 'track':
					slot = add('t%d_%s' % (t + 1, name), kind)
					if ch:
						self.cc.setdefault((ch, cc), []).append(slot)
		for cc, name, scope, kind in spec:
			if scope != 'track':
				self.cc.setdefault((0, cc), []).append(add(name, kind))

		self.lanes = []
		self.laneChannels = {}  # channel -> lane indices
		for k, ch in enumerate(_channels(comp.par.Midichannels.eval())):
			self.lanes.append({f: add('mt%d_%s' % (k + 1, f)) for f in _LANE_FIELDS})
			if ch:
				self.laneChannels.setdefault(ch, []).append(k)

		self.keys = []
		self.keyNotes = {}  # (channel, note) -> key indices; channel 0 matches any channel
		for row in CustomMap(comp).rows()[1:]:
			name, kind = row[0].val.strip(), row[1].val.strip().lower()
			if not name or name.startswith('#'):
				continue
			try:
				ch, number = int(row[2].val or 0), int(row[3].val or 0)
			except ValueError:
				continue
			if kind == 'note':
				self.keyNotes.setdefault((ch, number), []).append(len(self.keys))
				self.keys.append({f: add(name + f) for f in _KEY_FIELDS})
			elif kind == 'cc':
				self.cc.setdefault((ch, number), []).append(add(name, 'knob'))

		self.extra = {n: add(n) for n in _EXTRA}
		self.clock = {n: add(n) for n in _CLOCK}
		kinds = np.array(kinds)
		self.knob = kinds == 'knob'
		self.switch = kinds == 'switch'
		self.scene = kinds == 'scene'
		self.stored = self.knob | self.switch | self.scene

class _Engine:
	def __init__(self, comp):
		self.signature = None
		self.learning = None
		self.learnType = 'cc'
		self.learned = {}  # name -> value of the CC just learned, applied once the new layout exists
		self.lastCook = time.perf_counter()
		self.lastSave = 0.0
		self.dirty = False
		self.lastStatus = ''
		self.lastStatusTime = 0.0
		self.layout = None
		# clock
		self.tickTimes = deque(maxlen=96)
		self.lastTick = -1e9
		self.posTicks = 0
		self.running = None  # unknown until the first start, continue or stop
		self.resync = True
		self.beat = 0.0
		self.prevBeat = 0.0
		self.bpm = 120.0
		self.pattern = 0
		self.patternTrig = 0
		self.sceneTrig = 0
		self.noteTrig = 0
		self.noteEnv = 0.0
		self._relayout(comp)

	def _relayout(self, comp):
		if self.layout is not None:
			self._storeValues(comp)
		self.layout = _Layout(comp)
		n = len(self.layout.names)
		self.target = np.zeros(n)
		self.value = np.zeros(n)
		self.lanes = [{'held': {}, 'vel': 0.0, 'note': 0.0, 'trig': 0, 'env': 0.0, 'count': 0, 'bend': 0.5, 'press': 0.0} for _ in self.layout.lanes]
		self.keys = [{'held': 0, 'vel': 0.0, 'trig': 0, 'env': 0.0, 'count': 0} for _ in self.layout.keys]
		stored = dict(root.fetch(_storeKey(comp), {}, search=False), **self.learned)
		self.learned = {}
		index = {name: i for i, name in enumerate(self.layout.names)}
		for name, v in stored.items():
			i = index.get(name)
			if i is not None and self.layout.stored[i]:
				self.target[i] = self.value[i] = v
		comp.op('channel_names').text = ' '.join(self.layout.names)
		self.signature = self._signature(comp)

	def _signature(self, comp):
		return (comp.par.Trackchannels.eval(), comp.par.Midichannels.eval(), CcMap(comp).text, CustomMap(comp).text)

	def _storeValues(self, comp):
		"""Keep the knob, switch and scene values in root storage, so they survive a reload or a new layout."""
		layout = self.layout
		root.store(_storeKey(comp), {layout.names[i]: float(self.target[i]) for i in np.flatnonzero(layout.stored) if self.target[i] != 0.0})
		self.lastSave, self.dirty = time.perf_counter(), False

	def receive(self, comp, data):
		status = data[0]
		if status >= 0xF0:
			self._realtime(status, data)
			return
		kind, ch = status & 0xF0, (status & 0x0F) + 1
		a = data[1] if len(data) > 1 else 0
		b = data[2] if len(data) > 2 else 0
		layout = self.layout
		if kind == 0x90 and b > 0:
			if self.learning and self.learnType != 'cc':
				self._learnRow(comp, 'note', ch, a)
			vel = b / 127.0
			for k in layout.laneChannels.get(ch, ()):
				lane = self.lanes[k]
				lane['held'][a] = vel
				lane['vel'], lane['note'] = vel, a / 127.0
				lane['trig'] += 1
				lane['count'] += 1
				lane['env'] = max(lane['env'], vel)
			keys = layout.keyNotes.get((ch, a), []) + layout.keyNotes.get((0, a), [])
			for k in keys:
				key = self.keys[k]
				key['held'], key['vel'] = 1, vel
				key['trig'] += 1
				key['count'] += 1
				key['env'] = max(key['env'], vel)
			self.noteTrig += 1
			self.noteEnv = max(self.noteEnv, vel)
			targets = ['mt%d' % (k + 1) for k in layout.laneChannels.get(ch, ())] + [layout.names[layout.keys[k]['']] for k in keys]
			self._monitor(comp, 'ch%d note %s (%d) vel %d' % (ch, _noteName(a), a, b), targets)
		elif kind == 0x80 or kind == 0x90:
			for k in layout.laneChannels.get(ch, ()):
				self.lanes[k]['held'].pop(a, None)
			for k in layout.keyNotes.get((ch, a), []) + layout.keyNotes.get((0, a), []):
				self.keys[k]['held'] = 0
		elif kind == 0xB0:
			if self.learning and self.learnType != 'note':
				self.learned[self.learning] = b / 127.0
				self._learnRow(comp, 'cc', ch, a)
			slots = layout.cc.get((ch, a), []) + layout.cc.get((0, a), [])
			for i in slots:
				if layout.switch[i]:
					self.target[i] = 1.0 if b > 0 else 0.0
				elif layout.scene[i]:
					self.target[i] = min(b, 15) / 15.0
					self.sceneTrig += 1
				else:
					self.target[i] = b / 127.0
				if not layout.knob[i]:
					self.value[i] = self.target[i]
			self.dirty = self.dirty or bool(slots)
			self._monitor(comp, 'ch%d CC %d = %d' % (ch, a, b), [layout.names[i] for i in slots])
		elif kind == 0xC0:
			self.pattern = a
			self.patternTrig += 1
			self._monitor(comp, 'ch%d program %d' % (ch, a), ['pattern'])
		elif kind == 0xE0:
			for k in layout.laneChannels.get(ch, ()):
				self.lanes[k]['bend'] = ((b << 7) | a) / 16383.0
		elif kind == 0xD0:
			for k in layout.laneChannels.get(ch, ()):
				self.lanes[k]['press'] = a / 127.0

	def _realtime(self, status, data):
		if status == 0xF8:
			now = time.perf_counter()
			self.tickTimes.append(now)
			self.lastTick = now
			if self.running:
				self.posTicks += 1
		elif status == 0xFA:
			self.running, self.posTicks, self.resync = True, 0, True
		elif status == 0xFB:
			self.running, self.resync = True, True
		elif status == 0xFC:
			self.running = False
		elif status == 0xF2 and len(data) >= 3:
			self.posTicks, self.resync = ((data[2] << 7) | data[1]) * 6, True  # song position counts 16ths

	def _learnRow(self, comp, kind, ch, number):
		name, self.learning = self.learning, None
		table = CustomMap(comp)
		row = [name, kind, str(ch), str(number)]
		for r in range(1, table.numRows):
			if table[r, 0].val.strip() == name:
				table.replaceRow(r, row)
				break
		else:
			table.appendRow(row)
		comp.par.Learnstatus = 'Mapped %s to %s %d on channel %d' % (name, kind.upper() if kind == 'cc' else kind, number, ch)

	def _monitor(self, comp, text, targets):
		comp.par.Lastevent = '%s -> %s' % (text, ', '.join(targets) if targets else 'not mapped')

	def cook(self, comp):
		if self._signature(comp) != self.signature:
			self._relayout(comp)
		layout = self.layout
		now = time.perf_counter()
		dt = min(max(now - self.lastCook, 1e-4), 0.1)
		self.lastCook = now

		smooth = comp.par.Ccsmooth.eval()
		alpha = 1.0 if smooth <= 0 else 1.0 - math.exp(-dt / smooth)
		self.value[layout.knob] += (self.target[layout.knob] - self.value[layout.knob]) * alpha
		out = self.value.copy()

		decay = math.exp(-dt / max(comp.par.Envdecay.eval(), 0.01))
		for lane, slots in zip(self.lanes, layout.lanes):
			lane['env'] *= decay
			out[slots['gate']] = max(lane['held'].values()) if lane['held'] else 0.0
			out[slots['vel']] = lane['vel']
			out[slots['note']] = lane['note']
			out[slots['trig']] = 1.0 if lane['trig'] else 0.0
			out[slots['env']] = lane['env']
			out[slots['count']] = lane['count']
			out[slots['bend']] = lane['bend']
			out[slots['press']] = lane['press']
			lane['trig'] = 0
		for key, slots in zip(self.keys, layout.keys):
			key['env'] *= decay
			out[slots['']] = key['vel'] if key['held'] else 0.0
			out[slots['_trig']] = 1.0 if key['trig'] else 0.0
			out[slots['_env']] = key['env']
			out[slots['_count']] = key['count']
			key['trig'] = 0
		self.noteEnv *= decay
		extra = layout.extra
		out[extra['pattern']] = self.pattern / 127.0
		out[extra['pattern_num']] = self.pattern
		out[extra['pattern_trig']] = 1.0 if self.patternTrig else 0.0
		out[extra['scene_trig']] = 1.0 if self.sceneTrig else 0.0
		out[extra['note_trig']] = 1.0 if self.noteTrig else 0.0
		out[extra['note_env']] = self.noteEnv
		self.patternTrig = self.sceneTrig = self.noteTrig = 0

		self._clock(comp, now, dt, out)
		if self.dirty and now - self.lastSave > 2.0:
			self._storeValues(comp)
		return out.astype(np.float32)

	def _clock(self, comp, now, dt, out):
		source = comp.par.Clocksource.eval()
		external = now - self.lastTick < _CLOCK_TIMEOUT
		useMidi = source == 'midi' or (source == 'auto' and external)
		if useMidi and len(self.tickTimes) >= 12:
			times = np.array(self.tickTimes)
			idx = np.arange(len(times))
			secondsPerTick = np.polyfit(idx, times, 1)[0]  # regression evens out ticks that arrive in per-frame batches
			measured = 60.0 / (24.0 * secondsPerTick) if secondsPerTick > 1e-4 else self.bpm
			if abs(measured - self.bpm) > 8.0:
				self.bpm = measured
			else:
				self.bpm += (measured - self.bpm) * (1.0 - math.exp(-dt / 1.0))
		elif not useMidi:
			self.bpm = comp.par.Internalbpm.eval()
		rate = self.bpm / 60.0

		if useMidi and self.running:
			fraction = min((now - self.lastTick) * rate * 24.0, 1.0) if external else 0.0
			target = (self.posTicks + fraction) / 24.0
			self.beat += dt * rate
			error = target - self.beat
			if self.resync or abs(error) > 0.5:
				self.beat, self.prevBeat, self.resync = target, target, False
			else:
				self.beat += error * 0.2
			running = 1.0
		elif useMidi:
			running = 0.0
			if not comp.par.Freezestopped.eval():
				self.beat += dt * rate
		else:
			running = 1.0
			self.beat += dt * rate

		perBar = max(int(comp.par.Beatsperbar.eval()), 1)
		beat, prev = self.beat, self.prevBeat
		self.prevBeat = beat
		clock = self.layout.clock
		out[clock['clk_bpm']] = self.bpm
		out[clock['clk_run']] = running
		out[clock['clk_ext']] = 1.0 if external else 0.0
		out[clock['clk_beat']] = beat % _BEAT_WRAP
		out[clock['clk_phase']] = beat % 1.0
		out[clock['clk_bar']] = math.floor(beat / perBar)
		out[clock['clk_bar_phase']] = (beat % perBar) / perBar
		out[clock['clk_phrase_phase']] = (beat % (4 * perBar)) / (4 * perBar)
		out[clock['clk_step']] = math.floor(beat * 4.0) % (4 * perBar)
		forward = beat > prev
		out[clock['clk_beat_trig']] = 1.0 if forward and math.floor(beat) != math.floor(prev) else 0.0
		out[clock['clk_bar_trig']] = 1.0 if forward and math.floor(beat / perBar) != math.floor(prev / perBar) else 0.0
		out[clock['clk_step_trig']] = 1.0 if forward and math.floor(beat * 4.0) != math.floor(prev * 4.0) else 0.0

		if useMidi and not external:
			status = 'Waiting for MIDI clock'
		elif useMidi:
			transport = {True: 'playing', False: 'stopped', None: 'transport unknown until the next start'}[self.running]
			status = 'MIDI clock, %.1f BPM, %s' % (self.bpm, transport)
		else:
			status = 'Internal clock, %.1f BPM' % self.bpm
		if status != self.lastStatus and now - self.lastStatusTime > 0.5:
			comp.par.Clockstatus = status
			self.lastStatus, self.lastStatusTime = status, now
