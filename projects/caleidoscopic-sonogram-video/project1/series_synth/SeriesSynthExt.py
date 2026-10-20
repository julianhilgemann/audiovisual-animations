"""SeriesSynth: a Bundesbank time series as a playable, visualized wavetable synth.

Owns the custom-parameter schema of the COMP (get-or-create, never destroys a
user value), the Bundesbank REST API request and the parameter dispatcher.
The DSP lives in engine/wavetable_lib, the visuals in viz/.
"""
from __future__ import annotations

from typing import Optional

API_ROOT = 'https://api.statistiken.bundesbank.de/rest/data/'
DEFAULT_SERIES = 'BBIM1/M.DE.B.A2C.A.B.A.2250.EUR.N'

_STYLE_FAMILY = {'RGB': ('RGB', 'RGBA'), 'XY': ('XY', 'XYZW'), 'XYZ': ('XYZ', 'XYZW')}

# (page, name, style, label, attributes). Menus list menuNames first so the
# default lands on a valid token. 'default' becomes the value on create only.
_PAR_SCHEMA = [
    ('Data', 'Seriesid', 'Str', 'Series Key', dict(
        default=DEFAULT_SERIES,
        help='Bundesbank time-series key as FLOW/KEY (statistiken.bundesbank.de). '
             'Default BBIM1/M.DE.B.A2C.A.B.A.2250.EUR.N = new business volume of '
             'housing loans to households, Germany, EUR mn per month.')),
    ('Data', 'Fetch', 'Pulse', 'Fetch Series', dict(
        help='Request the series from the Bundesbank REST API (CSV, asynchronous '
             'Web Client DAT) and rebuild the cleaned numeric table.')),
    ('Data', 'Status', 'Str', 'Status', dict(
        readOnly=True, default='',
        help='Result of the last API request: months parsed and date range, or the HTTP error.')),

    ('Wavetable', 'Start', 'Float', 'Window Start (months)', dict(
        default=0.0, min=0.0, clampMin=True, normMin=0.0, normMax=280.0, startSection=True,
        help='First month of the loop window, counted from the first observation '
             '(0 = Jan 2003). The window is played as ONE cycle of the wavetable. '
             'With Scan on, the scan offset is added to this.')),
    ('Wavetable', 'Length', 'Int', 'Window Length (months)', dict(
        default=96, min=4, clampMin=True, normMin=4, normMax=300,
        help='Months in the loop window (one oscillator cycle). Clipped to the '
             'months available after Window Start.')),
    ('Wavetable', 'Loopmode', 'Menu', 'Loop Mode', dict(
        menuNames=['forward', 'pingpong'],
        menuLabels=['Forward (wrap)', 'Ping-Pong (mirror)'], default='forward',
        help='Forward plays the window start to end and wraps; Ping-Pong plays it '
             'forward then backward, which closes the loop without a jump and '
             'keeps only odd-symmetric content.')),
    ('Wavetable', 'Detrend', 'Menu', 'Detrend', dict(
        menuNames=['mean', 'linear'],
        menuLabels=['Mean (DC only)', 'Linear (close the loop)'], default='linear',
        help='Mean removes only the average (DC). Linear also removes the straight '
             'line from the first to the last month, so the wrap has no step and the '
             'cycle shows the deviation from trend.')),
    ('Wavetable', 'Interp', 'Menu', 'Interpolation', dict(
        menuNames=['step', 'linear', 'cubic'],
        menuLabels=['Step (sample & hold)', 'Linear', 'Cubic (smooth)'], default='cubic',
        help='How the monthly values are resampled to the 2048-sample table. Step '
             'keeps the monthly staircase (bright, buzzy), Cubic is the smoothest.')),
    ('Wavetable', 'Scan', 'Toggle', 'Scan History', dict(
        default=True, startSection=True,
        help='Slide the loop window through the whole history (ping-pong), so the '
             'timbre morphs from 2003 to today like a wavetable scan.')),
    ('Wavetable', 'Scanrate', 'Float', 'Scan Rate (months/s)', dict(
        default=4.0, min=0.0, clampMin=True, normMin=0.0, normMax=24.0,
        help='Months per second the window moves while Scan History is on.')),

    ('Shape', 'Shapemode', 'Menu', 'Shaper', dict(
        menuNames=['soft', 'hard', 'fold', 'crush'],
        menuLabels=['Soft Clip (tanh)', 'Hard Clip', 'Wavefold (sine)', 'Bitcrush'],
        default='soft',
        help='Waveshaper applied to the cycle after normalisation: adds upper harmonics. '
             'Bitcrush maps Drive to bit depth (0 dB = 8 bit, 36 dB = 2 bit).')),
    ('Shape', 'Drive', 'Float', 'Drive (dB)', dict(
        default=9.0, min=0.0, max=48.0, clampMin=True, clampMax=True, normMin=0.0, normMax=36.0,
        help='Gain into the shaper in dB; more drive means more and stronger upper harmonics.')),
    ('Shape', 'Bias', 'Float', 'Asymmetry', dict(
        default=0.0, min=-1.0, max=1.0, clampMin=True, clampMax=True, normMin=-1.0, normMax=1.0,
        help='Offset added before the shaper. Non-zero values clip one side harder '
             'and add even harmonics (DC is removed afterwards).')),
    ('Shape', 'Mix', 'Float', 'Mix', dict(
        default=1.0, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='Dry/wet between the raw cycle (0) and the shaped cycle (1).')),
    ('Shape', 'Bandlimit', 'Toggle', 'Band-limit to Pitch', dict(
        default=True,
        help='Remove harmonics above Nyquist for the current pitch so high notes do '
             'not alias. Off lets aliasing through for a harsher digital sound.')),

    ('Pitch', 'Note', 'Float', 'Note (MIDI)', dict(
        default=45.0, min=12.0, max=108.0, clampMin=True, clampMax=True, normMin=24.0, normMax=84.0,
        help='Oscillator pitch as a MIDI note number (45 = A2 = 110 Hz, 57 = A3, 69 = A4 = 440 Hz). '
             'The wavetable shape is kept; only the playback rate changes.')),
    ('Pitch', 'Fine', 'Float', 'Fine (cents)', dict(
        default=0.0, min=-100.0, max=100.0, clampMin=True, clampMax=True, normMin=-100.0, normMax=100.0,
        help='Fine tuning in cents (1/100 semitone).')),
    ('Pitch', 'Glide', 'Float', 'Glide (s)', dict(
        default=0.08, min=0.0, max=4.0, clampMin=True, clampMax=True, normMin=0.0, normMax=1.0,
        help='Portamento time: seconds the frequency takes to slide to a new note.')),

    ('Gate', 'Gate', 'Momentary', 'Gate (hold to play)', dict(
        help='Opens the gate while held: both envelopes attack, then release when let go.')),
    ('Gate', 'Hold', 'Toggle', 'Hold (drone)', dict(
        default=False, help='Keeps the gate open permanently (drone at sustain level).')),
    ('Gate', 'Autogate', 'Toggle', 'Auto Gate', dict(
        default=True, startSection=True,
        help='Retriggers the envelopes rhythmically at Gate Rate.')),
    ('Gate', 'Gaterate', 'Float', 'Gate Rate (Hz)', dict(
        default=1.0, min=0.05, max=16.0, clampMin=True, clampMax=True, normMin=0.1, normMax=8.0,
        help='Notes per second of the Auto Gate (1.0 = 60 BPM, 2.0 = 120 BPM).')),
    ('Gate', 'Gatelength', 'Float', 'Gate Length', dict(
        default=0.55, min=0.02, max=0.98, clampMin=True, clampMax=True,
        help='Fraction of each Auto Gate period the gate stays open.')),

    ('Amp Env', 'Attack', 'Float', 'Attack (s)', dict(
        default=0.01, min=0.001, max=10.0, clampMin=True, clampMax=True, normMin=0.001, normMax=2.0,
        help='Loudness envelope: seconds from gate-on to full level.')),
    ('Amp Env', 'Decay', 'Float', 'Decay (s)', dict(
        default=0.35, min=0.001, max=10.0, clampMin=True, clampMax=True, normMin=0.001, normMax=2.0,
        help='Loudness envelope: seconds from full level down to the sustain level.')),
    ('Amp Env', 'Sustain', 'Float', 'Sustain', dict(
        default=0.6, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='Loudness envelope: level held while the gate stays open (0-1).')),
    ('Amp Env', 'Release', 'Float', 'Release (s)', dict(
        default=0.5, min=0.001, max=10.0, clampMin=True, clampMax=True, normMin=0.001, normMax=3.0,
        help='Loudness envelope: seconds to fall to silence after the gate closes.')),

    ('Filter', 'Filtertype', 'Menu', 'Filter Type', dict(
        menuNames=['lowpass', 'highpass', 'bandpass', 'bandreject'],
        menuLabels=['Low Pass', 'High Pass', 'Band Pass', 'Band Reject'], default='lowpass',
        help='Response of the 4-pole audio filter after the shaper.')),
    ('Filter', 'Cutoff', 'Float', 'Cutoff (Hz)', dict(
        default=500.0, min=20.0, max=20000.0, clampMin=True, clampMax=True, normMin=20.0, normMax=6000.0,
        help='Filter cutoff in Hz with the filter envelope at zero.')),
    ('Filter', 'Resonance', 'Float', 'Resonance', dict(
        default=0.35, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='Boost around the cutoff frequency (0 = none).')),
    ('Filter', 'Rolloff', 'Menu', 'Roll-off', dict(
        menuNames=['12', '24'], menuLabels=['12 dB/oct', '24 dB/oct'], default='24',
        help='Steepness of the filter slope.')),
    ('Filter', 'Envamount', 'Float', 'Env Amount (oct)', dict(
        default=4.0, min=-8.0, max=8.0, clampMin=True, clampMax=True, normMin=-6.0, normMax=6.0,
        startSection=True,
        help='Octaves the filter envelope moves the cutoff at full level '
             '(cutoff x 2^(amount x env)). Negative values sweep downward.')),
    ('Filter', 'Fattack', 'Float', 'Env Attack (s)', dict(
        default=0.005, min=0.001, max=10.0, clampMin=True, clampMax=True, normMin=0.001, normMax=2.0,
        help='Filter envelope: seconds from gate-on to full level.')),
    ('Filter', 'Fdecay', 'Float', 'Env Decay (s)', dict(
        default=0.45, min=0.001, max=10.0, clampMin=True, clampMax=True, normMin=0.001, normMax=2.0,
        help='Filter envelope: seconds from full level down to the sustain level.')),
    ('Filter', 'Fsustain', 'Float', 'Env Sustain', dict(
        default=0.2, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='Filter envelope: level held while the gate stays open (0-1).')),
    ('Filter', 'Frelease', 'Float', 'Env Release (s)', dict(
        default=0.4, min=0.001, max=10.0, clampMin=True, clampMax=True, normMin=0.001, normMax=3.0,
        help='Filter envelope: seconds to fall back after the gate closes.')),

    ('Output', 'Audio', 'Toggle', 'Audio Out', dict(
        default=True, help='Sends the synth to the default audio device.')),
    ('Output', 'Volume', 'Float', 'Volume', dict(
        default=0.3, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='Output gain (linear, 0-1) before the safety limiter.')),

    ('Visual', 'Orbit', 'Float', 'Camera Orbit', dict(
        default=1.0, min=0.0, max=4.0, clampMin=True, clampMax=True,
        help='Speed multiplier of the eased camera orbit around the 3D wavetable (0 = still).')),
    ('Visual', 'Glow', 'Float', 'Glow', dict(
        default=1.0, min=0.0, max=3.0, clampMin=True, clampMax=True,
        help='Strength of the neon bloom on lines and traces.')),
    ('Visual', 'Slowmo', 'Float', 'Slow-motion Period (s)', dict(
        default=4.0, min=0.5, max=30.0, clampMin=True, clampMax=True, normMin=1.0, normMax=12.0,
        help='Seconds one visual sweep of the playhead takes. The real oscillator runs '
             'at audio rate; the playhead shows the same cycle slowed down.')),
]


class SeriesSynthExt:
    """Bundesbank series -> playable wavetable: parameter schema, API fetch, dispatch."""

    def __init__(self, ownerComp: COMP) -> None:
        self.ownerComp = ownerComp
        self.ensurePars()

    def onInitTD(self) -> None:
        """Nothing deferred: the network is static and the data persists in data/raw_csv."""
        return

    def onDestroyTD(self) -> None:
        """No timers or threads to release."""
        return

    # ---- Tier 1: public API ------------------------------------------------
    def Fetch(self) -> Optional[int]:
        """Request the configured series from the Bundesbank REST API (asynchronous)."""
        web = self.ownerComp.op('data/webclient_bbk')
        if web is None:
            self._setStatus('error: data/webclient_bbk is missing')
            return None
        key = self.ownerComp.par.Seriesid.eval().strip().strip('/')
        url = API_ROOT + key + '?format=csv&lang=en'
        self._setStatus('requesting ' + key)
        return web.request(url, 'GET', timeout=15000)

    # ---- Tier 2: wiring (callbacks of this COMP's own DATs) -----------------
    def ensurePars(self) -> None:
        """Get-or-create every custom parameter in _PAR_SCHEMA; values stay the user's."""
        for page_name, name, style, label, attrs in _PAR_SCHEMA:
            self._ensurePar(page_name, name, style, label, attrs)

    def handleResponse(self, statusCode: dict, data: bytes) -> None:
        """Store the CSV body in data/raw_csv and report the cleaned row count."""
        code = statusCode.get('code')
        if code != 200:
            self._setStatus('HTTP %s %s' % (code, statusCode.get('message', '')))
            return
        text = data.decode('utf-8-sig', errors='replace')
        self.ownerComp.op('data/raw_csv').text = text
        clean = self.ownerComp.op('data/clean_series')
        clean.cook(force=True)
        months = clean.numRows - 1
        if months < 4:
            self._setStatus('error: only %d numeric months parsed' % max(months, 0))
            return
        self._setStatus('%d months %s .. %s' % (months, clean[1, 'date'], clean[months, 'date']))

    def dispatchPulse(self, par: Par) -> None:
        """Route a custom pulse to its _on<Par>Pulse handler, if one exists."""
        handler = getattr(self, '_on%sPulse' % par.name, None)
        if callable(handler):
            handler(par)

    def dispatchValueChange(self, par: Par, prev) -> None:
        """Route a custom value change to its _on<Par>ValueChange handler, if one exists."""
        handler = getattr(self, '_on%sValueChange' % par.name, None)
        if callable(handler):
            handler(par, prev)

    # ---- Tier 3: private --------------------------------------------------
    def _onFetchPulse(self, par: Par) -> None:
        self.Fetch()

    def _setStatus(self, text: str) -> None:
        self.ownerComp.par.Status.val = text
        debug('SeriesSynth:', text)

    def _ensurePage(self, name: str):
        for page in self.ownerComp.customPages:
            if page.name == name:
                return page
        return self.ownerComp.appendCustomPage(name)

    def _ensurePar(self, page_name: str, name: str, style: str, label: str, attrs: dict) -> Par:
        comp = self.ownerComp
        found = [p for p in comp.customPars if p.tupletName == name]
        created = not found
        if created:
            getattr(self._ensurePage(page_name), 'append' + style)(name, label=label)
            found = [p for p in comp.customPars if p.tupletName == name]
        elif found[0].style not in _STYLE_FAMILY.get(style, (style,)):
            raise ValueError('par %s is %s, schema says %s -- refusing to replace it'
                             % (name, found[0].style, style))
        par = found[0]
        par.label = label
        for key, value in attrs.items():
            setattr(par, key, value)
        if created and 'default' in attrs:
            par.val = attrs['default']
        return par
