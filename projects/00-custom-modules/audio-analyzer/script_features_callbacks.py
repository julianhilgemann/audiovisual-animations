# Written by Save Module from audio_analyzer.tox so git shows readable diffs. Edit this
# DAT inside audio_analyzer in TouchDesigner, then press Save Module; edits here change nothing.

# Audio features of the audio analyzer, one sample per channel, every value 0-1 except the counts.
#
# Input 1 is the spectrum (1024 linear bins from 0 Hz to Nyquist), input 2 the audio itself.
# Levels are measured in dB and normalized against a running peak that falls at Normalize Speed,
# so a quiet microphone and a loud file both fill 0-1; Range sets how many dB below that peak
# read as 0. The peak never falls below Gate + Range (each band offset by its usual distance
# from the overall level, learned while the audio plays), so audio just above the gate reads
# near 0 instead of being blown up. Below the Gate everything falls to 0.
# Onsets are spectral flux peaks above an adaptive threshold (running mean plus a multiple of
# the running deviation), one detector per band group, with a refractory time each. A detector
# with two ranges (the snare: body and noise) needs both to rise at once, so it takes the
# smaller of the two; that keeps hats and basslines from firing it.

import math
import numpy as np

_BANDS = (
	('sub', 20, 60), ('bass', 60, 150), ('lowmid', 150, 400), ('mid', 400, 1000),
	('highmid', 1000, 2500), ('presence', 2500, 6000), ('brilliance', 6000, 12000), ('air', 12000, 20000))
_GROUPS = (('lows', 0, 2), ('mids', 2, 5), ('highs', 5, 8))  # slices of _BANDS
# name, frequency ranges, refractory seconds, sensitivity parameter
_ONSETS = (
	('kick', ((35, 150),), 0.12, 'Kicksens'),
	('snare', ((180, 400), (1500, 5000)), 0.15, 'Snaresens'),
	('hat', ((7000, 16000),), 0.05, 'Hatsens'),
	('onset', ((30, 16000),), 0.08, 'Onsetsens'))
# Starting distance in dB of each band and group from the overall level, measured on a mixed
# electronic track; each adapts to the music over _TILT_TIME seconds.
_TILT = (8.0, 12.0, 3.0, -10.0, -13.0, -18.0, -27.0, -40.0, 10.0, -6.0, -24.0)
_TILT_TIME = 20.0
_LOG_LO, _LOG_HI = math.log2(80.0), math.log2(8000.0)  # frequency span of centroid and rolloff

_states = {}

def onSetupParameters(scriptOp):
	return

def onPulse(par):
	return

def onCook(scriptOp):
	comp = parent.Audio
	values = _analyze(comp, scriptOp)
	scriptOp.clear()
	scriptOp.numSamples = 1
	for name, value in values:
		scriptOp.appendChan(name)[0] = value
	return

def _analyze(comp, scriptOp):
	"""All features for this frame, as (name, value) pairs in output order."""
	dt = min(max(absTime.stepSeconds, 1e-4), 0.1)
	gain = 10.0 ** (comp.par.Inputgain.eval() / 20.0)
	spectrum = scriptOp.inputs[0] if len(scriptOp.inputs) > 0 else None
	audio = scriptOp.inputs[1] if len(scriptOp.inputs) > 1 else None

	samples = audio.numpyArray() * gain if audio is not None and audio.rate >= 8000 else np.zeros((1, 2))
	nyquist = audio.rate / 2.0 if audio is not None and audio.rate >= 8000 else 22050.0
	mags = spectrum.numpyArray().mean(axis=0) * gain if spectrum is not None and spectrum.numSamples > 8 else np.zeros(1024)

	key = (scriptOp.id, len(mags), nyquist)
	st = _states.get(scriptOp.id)
	if st is None or st.key != key:
		st = _states[scriptOp.id] = _State(key, len(mags), nyquist)
	st.time += dt

	mono = samples.mean(axis=0)
	rms = float(np.sqrt(np.mean(mono * mono)))
	peak = float(np.max(np.abs(mono)))
	rmsDb = 20.0 * math.log10(rms + 1e-9)
	peakDb = 20.0 * math.log10(peak + 1e-9)
	active = rmsDb > comp.par.Gate.eval()

	power = mags * mags
	levelsDb = np.concatenate(([rmsDb, peakDb], 10.0 * np.log10(st.levelWeights @ power + 1e-12)))
	if active:
		span = max(comp.par.Range.eval(), 1.0)
		st.tilt += (np.clip(levelsDb[2:] - rmsDb, -60.0, 30.0) - st.tilt) * (1.0 - math.exp(-dt / _TILT_TIME))
		floor = comp.par.Gate.eval() + span
		floors = np.concatenate(([floor, floor + 3.0], floor + st.tilt))  # a peak sits about 3 dB over the RMS
		st.peakDb = np.maximum(np.maximum(levelsDb, st.peakDb - comp.par.Normspeed.eval() * dt), floors)
		norm = np.clip(1.0 + (levelsDb - st.peakDb) / span, 0.0, 1.0)
	else:
		norm = np.zeros(len(levelsDb))

	attack, release = comp.par.Attack.eval(), comp.par.Release.eval()
	out = []
	out.append(('a_level', st.smooth('level', norm[0], attack, release, dt)))
	out.append(('a_peak', st.smooth('peak', norm[1], 0.0, release * 2.0, dt)))
	out.append(('a_loud', st.smooth('loud', min(max((rmsDb + 60.0) / 60.0, 0.0), 1.0), attack, release, dt)))
	out.append(('a_active', 1.0 if active else 0.0))
	names = [b[0] for b in _BANDS] + [g[0] for g in _GROUPS]
	for i, name in enumerate(names):
		out.append(('a_' + name, st.smooth(name, norm[2 + i], attack, release, dt)))

	spread = power[st.wideMask]
	total = float(spread.sum())
	if active and total > 1e-12:
		centroid = float((st.freqs[st.wideMask] * spread).sum() / total)
		rolloff = float(st.freqs[st.wideMask][min(np.searchsorted(np.cumsum(spread), 0.85 * total), len(spread) - 1)])
		flat = power[st.flatMask] + 1e-12
		flatness = float(np.exp(np.mean(np.log(flat))) / np.mean(flat))
		brightness = _logNorm(centroid)
		rolloffNorm = _logNorm(rolloff)
		flatNorm = min(max(1.0 + math.log10(flatness + 1e-12) / 3.0, 0.0), 1.0)
	else:
		brightness = rolloffNorm = flatNorm = 0.0
	if samples.shape[0] >= 2 and active:
		side = float(np.sqrt(np.mean((samples[0] - samples[1]) ** 2)))
		middle = float(np.sqrt(np.mean((samples[0] + samples[1]) ** 2)))
		width = min(side / (middle + 1e-9), 1.0)
	else:
		width = 0.0
	crest = min(max((peakDb - rmsDb - 3.0) / 15.0, 0.0), 1.0) if active else 0.0
	out.append(('a_centroid', st.smooth('centroid', brightness, 0.05, 0.3, dt)))
	out.append(('a_flatness', st.smooth('flatness', flatNorm, 0.05, 0.3, dt)))
	out.append(('a_rolloff', st.smooth('rolloff', rolloffNorm, 0.05, 0.3, dt)))
	out.append(('a_width', st.smooth('width', width, 0.1, 0.4, dt)))
	out.append(('a_crest', st.smooth('crest', crest, 0.02, 0.3, dt)))

	energy = norm[0]
	st.energyFast += (energy - st.energyFast) * (1.0 - math.exp(-dt / 1.0))
	st.energySlow += (energy - st.energySlow) * (1.0 - math.exp(-dt / max(comp.par.Slowtime.eval(), 0.1)))
	out.append(('a_energy', st.smooth('energy', energy, 0.05, 0.4, dt)))
	out.append(('a_energy_slow', st.energySlow))
	out.append(('a_build', min(max(0.5 + 2.0 * (st.energyFast - st.energySlow), 0.0), 1.0)))

	logMags = np.log1p(100.0 * mags)
	rise = np.maximum(logMags - st.prevLog, 0.0) if active else np.zeros(len(mags))
	st.prevLog = logMags
	riseMeans = st.riseWeights @ rise  # row 0: the whole spectrum, then one row per onset range
	flux = float(riseMeans[0])
	st.fluxPeak = max(flux, st.fluxPeak * math.exp(-dt / 3.0), 1e-3)
	out.append(('a_flux', st.smooth('flux', flux / st.fluxPeak, 0.0, 0.1, dt)))

	decay = math.exp(-dt / max(comp.par.Decay.eval(), 0.01))
	statsRate = 1.0 - math.exp(-dt / 0.5)
	for i, (name, _, refractory, sensPar) in enumerate(_ONSETS):
		odf = float(riseMeans[st.onsetRows[i]].min())
		threshold = st.mu[i] + (4.0 - 3.0 * comp.par[sensPar].eval()) * st.dev[i] + 0.01
		above = odf > threshold
		fire = active and above and not st.above[i] and st.time - st.lastOnset[i] >= refractory
		st.above[i] = above
		st.mu[i] += (odf - st.mu[i]) * statsRate
		st.dev[i] += (abs(odf - st.mu[i]) - st.dev[i]) * statsRate
		st.env[i] *= decay
		if fire:
			st.env[i] = 1.0
			st.count[i] += 1
			st.lastOnset[i] = st.time
		out.append(('a_' + name, 1.0 if fire else 0.0))
		out.append(('a_%s_env' % name, float(st.env[i])))
		out.append(('a_%s_count' % name, float(st.count[i])))
	return out

def _weights(masks):
	"""One row per mask that averages the masked bins (an empty mask averages to 0)."""
	rows = np.array(masks, dtype=np.float64)
	return rows / np.maximum(rows.sum(axis=1, keepdims=True), 1.0)

def _logNorm(freq):
	"""A frequency on a log scale from 80 Hz (0) to 8 kHz (1)."""
	return min(max((math.log2(max(freq, 1.0)) - _LOG_LO) / (_LOG_HI - _LOG_LO), 0.0), 1.0)

class _State:
	"""Per-operator memory between frames: running peaks, smoothers and onset detectors."""
	def __init__(self, key, bins, nyquist):
		self.key = key
		freqs = (np.arange(bins) + 1) * nyquist / bins  # measured: bin k peaks at about (k + 1) * Nyquist / bins
		self.freqs = freqs
		bands = [(freqs >= lo) & (freqs < hi) for _, lo, hi in _BANDS]
		groups = [np.any(bands[a:b], axis=0) for _, a, b in _GROUPS]
		self.levelWeights = _weights(bands + groups)
		self.wideMask = (freqs >= 30) & (freqs < 16000)
		self.flatMask = (freqs >= 200) & (freqs < 8000)
		riseMasks = [self.wideMask]
		self.onsetRows = []
		for _, ranges, _, _ in _ONSETS:
			self.onsetRows.append(list(range(len(riseMasks), len(riseMasks) + len(ranges))))
			riseMasks += [(freqs >= lo) & (freqs < hi) for lo, hi in ranges]
		self.riseWeights = _weights(riseMasks)
		self.peakDb = np.full(2 + len(_BANDS) + len(_GROUPS), -120.0)
		self.tilt = np.array(_TILT)
		self.prevLog = np.zeros(bins)
		self.fluxPeak = 1e-3
		self.energyFast = 0.0
		self.energySlow = 0.0
		n = len(_ONSETS)
		self.mu = np.zeros(n)
		self.dev = np.zeros(n)
		self.above = np.zeros(n, bool)
		self.lastOnset = np.full(n, -1e9)
		self.env = np.zeros(n)
		self.count = np.zeros(n)
		self.time = 0.0
		self.values = {}

	def smooth(self, name, target, attack, release, dt):
		"""One-pole smoothing with separate rise (attack) and fall (release) times in seconds."""
		current = self.values.get(name, 0.0)
		tau = attack if target > current else release
		current = target if tau <= 0.0 else current + (target - current) * (1.0 - math.exp(-dt / tau))
		self.values[name] = current
		return current
