"""AudioReactor: the Bundesbank wavetable drone as a camera- and microphone-reactive installation.

Owns the custom-parameter schema of the COMP (get-or-create, never destroys a
user value), the Bundesbank REST API request, the camera background capture and
the parameter dispatcher. The DSP lives in engine/wavetable_lib, camera and
microphone analysis in sense/, the point-cloud visuals in viz/.
"""
from __future__ import annotations

from typing import Optional

API_ROOT = 'https://api.statistiken.bundesbank.de/rest/data/'
DEFAULT_SERIES = 'BBIM1/M.DE.B.A2C.A.B.A.2250.EUR.N'

_STYLE_FAMILY = {'RGB': ('RGB', 'RGBA'), 'XY': ('XY', 'XYZW'), 'XYZ': ('XYZ', 'XYZW')}


def _monitor(channel: str) -> str:
    """Expression that mirrors one sense/null_features channel (0 while it is missing)."""
    return ("float(me.op('sense/null_features')['%s'] or 0) "
            "if me.op('sense/null_features') is not None else 0.0" % channel)


# (page, name, style, label, attributes). Menus list menuNames first so the
# default lands on a valid token. 'default' becomes the value on create only;
# 'expr' is schema-owned and re-applied on every init (read-only monitors).
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
        help='Slide the loop window through the whole history, so the timbre morphs '
             'from 2003 to today like a wavetable scan.')),
    ('Wavetable', 'Scandir', 'Menu', 'Scan Direction', dict(
        menuNames=['pingpong', 'forward', 'backward'],
        menuLabels=['Ping-Pong (back and forth)', 'Forward (wrap to 2003)',
                    'Backward (wrap to today)'], default='pingpong',
        help='How the window travels through history: back and forth, always forward '
             'in time (jumps back to the start at the end), or always backward.')),
    ('Wavetable', 'Scanrate', 'Float', 'Scan Rate (months/s)', dict(
        default=4.0, min=0.0, clampMin=True, normMin=0.0, normMax=24.0,
        help='Months per second the window moves while Scan History is on. Camera '
             'motion adds to it (Sound Mod > Motion -> Scan).')),

    ('Shape', 'Shapemode', 'Menu', 'Shaper', dict(
        menuNames=['soft', 'hard', 'fold', 'crush'],
        menuLabels=['Soft Clip (tanh)', 'Hard Clip', 'Wavefold (sine)', 'Bitcrush'],
        default='soft',
        help='Waveshaper applied to the cycle after normalisation: adds upper harmonics. '
             'Bitcrush maps Drive to bit depth (0 dB = 8 bit, 36 dB = 2 bit).')),
    ('Shape', 'Drive', 'Float', 'Drive (dB)', dict(
        default=9.0, min=0.0, max=48.0, clampMin=True, clampMax=True, normMin=0.0, normMax=36.0,
        help='Gain into the shaper in dB; more drive means more and stronger upper '
             'harmonics. Microphone level adds to it (Sound Mod > Mic -> Drive).')),
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
        help='Drone pitch as a MIDI note number (45 = A2 = 110 Hz, 57 = A3, 69 = A4 = 440 Hz). '
             'The wavetable shape is kept; only the playback rate changes.')),
    ('Pitch', 'Fine', 'Float', 'Fine (cents)', dict(
        default=0.0, min=-100.0, max=100.0, clampMin=True, clampMax=True, normMin=-100.0, normMax=100.0,
        help='Fine tuning in cents (1/100 semitone).')),
    ('Pitch', 'Glide', 'Float', 'Glide (s)', dict(
        default=0.08, min=0.0, max=4.0, clampMin=True, clampMax=True, normMin=0.0, normMax=1.0,
        help='Portamento time: seconds the frequency takes to slide to a new note.')),

    ('Filter', 'Filtertype', 'Menu', 'Filter Type', dict(
        menuNames=['lowpass', 'highpass', 'bandpass', 'bandreject'],
        menuLabels=['Low Pass', 'High Pass', 'Band Pass', 'Band Reject'], default='lowpass',
        help='Response of the audio filter after the shaper.')),
    ('Filter', 'Cutoff', 'Float', 'Cutoff (Hz)', dict(
        default=1200.0, min=20.0, max=20000.0, clampMin=True, clampMax=True, normMin=20.0, normMax=6000.0,
        help='Filter cutoff in Hz before drift and proximity modulation.')),
    ('Filter', 'Resonance', 'Float', 'Resonance', dict(
        default=0.35, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='Boost around the cutoff frequency (0 = none).')),
    ('Filter', 'Rolloff', 'Menu', 'Roll-off', dict(
        menuNames=['12', '24'], menuLabels=['12 dB/oct', '24 dB/oct'], default='24',
        help='Steepness of the filter slope.')),
    ('Filter', 'Drift', 'Float', 'Drift (oct)', dict(
        default=0.6, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=3.0, startSection=True,
        help='Depth of the slow cutoff wander in octaves (0 = static filter). Two '
             'de-synced sines, so the drone keeps breathing with nobody in the room.')),
    ('Filter', 'Driftrate', 'Float', 'Drift Rate (Hz)', dict(
        default=0.05, min=0.001, max=2.0, clampMin=True, clampMax=True, normMin=0.005, normMax=0.5,
        help='Speed of the cutoff wander: cycles per second of the main drift sine.')),

    ('Output', 'Audio', 'Toggle', 'Audio Out', dict(
        default=True, help='Sends the drone to the default audio device.')),
    ('Output', 'Volume', 'Float', 'Volume', dict(
        default=0.3, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='Output gain (linear, 0-1) before the safety limiter.')),

    ('Visual', 'Palette', 'Menu', 'Color Scale', dict(
        menuNames=['inferno', 'magma', 'viridis', 'turbo', 'ice', 'mono'],
        menuLabels=['Inferno', 'Magma', 'Viridis', 'Turbo', 'Ice', 'Mono'], default='inferno',
        help='Color scale the sonogram level is mapped through (quiet -> loud).')),
    ('Visual', 'Paletteshift', 'Float', 'Scale Offset', dict(
        default=0.0, min=-1.0, max=1.0, clampMin=True, clampMax=True, normMin=-0.5, normMax=0.5,
        help='Slides the level along the color scale: positive values show quieter '
             'content brighter, negative values darken everything but the peaks.')),
    ('Visual', 'Contrast', 'Float', 'Level Contrast', dict(
        default=2.0, min=0.2, max=4.0, clampMin=True, clampMax=True, normMin=0.4, normMax=3.0,
        help='Gamma on the sonogram level before the color scale (1 = linear dB; '
             'higher hides the quiet bins and isolates the strong partials).')),
    ('Visual', 'Direction', 'Menu', 'Flow Direction', dict(
        menuNames=['left', 'right', 'up', 'down'],
        menuLabels=['Left', 'Right', 'Up', 'Down'], default='left', startSection=True,
        help='Where the history flows: new sound enters at the opposite edge and '
             'travels this way. Left/Right put frequency on the vertical axis, '
             'Up/Down on the horizontal axis.')),
    ('Visual', 'Speed', 'Float', 'Flow Speed', dict(
        default=1.0, min=0.0, max=6.0, clampMin=True, clampMax=True, normMax=4.0,
        help='Screen crossings per 10 seconds of the sonogram/scope history '
             '(0 = static: nothing travels, the whole field breathes with the live sound).')),
    ('Visual', 'Depth', 'Float', 'Scope Depth', dict(
        default=1.0, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=3.0,
        help='How far the oscilloscope history pushes the cloud in depth.')),
    ('Visual', 'Thickness', 'Float', 'Cloud Thickness', dict(
        default=0.6, min=0.0, max=3.0, clampMin=True, clampMax=True, normMax=2.0,
        help='Depth spacing between the three layers of the cloud (0 = one flat sheet).')),
    ('Visual', 'Scatter', 'Float', 'Scatter', dict(
        default=0.45, min=0.0, max=2.0, clampMin=True, clampMax=True, normMax=1.5,
        help='Fixed random offset of each point, which turns the grid into a cloud.')),
    ('Visual', 'Pointsize', 'Float', 'Point Size', dict(
        default=1.0, min=0.1, max=6.0, clampMin=True, clampMax=True, normMin=0.2, normMax=3.0,
        help='Size multiplier of the rendered points.')),
    ('Visual', 'Dof', 'Float', 'Depth of Field', dict(
        default=1.0, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=3.0,
        help='Blur of points in front of and behind the focus plane (soft bokeh discs). '
             'The mid band of the microphone adds to it.')),
    ('Visual', 'Sway', 'Float', 'Camera Sway', dict(
        default=1.0, min=0.0, max=3.0, clampMin=True, clampMax=True, normMax=2.0, startSection=True,
        help='Amount of the slow, eased camera sway around the cloud (0 = locked camera).')),
    ('Visual', 'Swayspeed', 'Float', 'Sway Speed', dict(
        default=1.0, min=0.0, max=5.0, clampMin=True, clampMax=True, normMax=3.0,
        help='Speed multiplier of the camera sway and of the idle breathing noise.')),
    ('Visual', 'Glow', 'Float', 'Glow', dict(
        default=1.0, min=0.0, max=3.0, clampMin=True, clampMax=True,
        help='Base strength of the bloom (the low band of the microphone adds to it).')),

    ('Reactivity', 'Reach', 'Float', 'Silhouette Reach', dict(
        default=1.0, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=3.0,
        help='How far the points inside a visitor\'s silhouette come toward the screen; '
             'grows with proximity, so a hand close to the camera pulls the cloud to it.')),
    ('Reactivity', 'Imprint', 'Float', 'Silhouette Imprint', dict(
        default=0.5, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='How strongly the silhouette lifts its points up the color scale and enlarges them.')),
    ('Reactivity', 'Ripple', 'Float', 'Motion Ripple', dict(
        default=1.0, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=3.0,
        help='Turbulence the camera motion trail stirs into the cloud where people move.')),
    ('Reactivity', 'Chaos', 'Float', 'Noise Chaos', dict(
        default=1.0, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=3.0, startSection=True,
        help='Master amount for everything the room microphone does to the image: '
             'louder = messier, silence = clear patterns.')),
    ('Reactivity', 'Lowbloom', 'Float', 'Low -> Bloom', dict(
        default=1.0, min=0.0, max=3.0, clampMin=True, clampMax=True,
        help='Low band (< 250 Hz) of the microphone: bloom and a depth pump.')),
    ('Reactivity', 'Midblur', 'Float', 'Mid -> Blur', dict(
        default=1.0, min=0.0, max=3.0, clampMin=True, clampMax=True,
        help='Mid band (250 Hz - 4 kHz) of the microphone: defocus blur and a looser cloud.')),
    ('Reactivity', 'Highjitter', 'Float', 'High -> Jitter', dict(
        default=1.0, min=0.0, max=3.0, clampMin=True, clampMax=True,
        help='High band (> 4 kHz) of the microphone: per-frame point jitter and grain.')),
    ('Reactivity', 'Kick', 'Float', 'Transient -> Kick', dict(
        default=1.0, min=0.0, max=3.0, clampMin=True, clampMax=True,
        help='Sudden sounds (claps, knocks): a radial shock through the cloud and a '
             'brief color split.')),
    ('Reactivity', 'Micsono', 'Float', 'Mic -> Sonogram', dict(
        default=0.6, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='How much of the room sound is written into the sonogram history: the '
             'market noise that covers up the patterns in the data.')),

    ('Sound Mod', 'Proxcutoff', 'Float', 'Proximity -> Cutoff (oct)', dict(
        default=2.0, min=-6.0, max=6.0, clampMin=True, clampMax=True, normMin=-4.0, normMax=4.0,
        help='Octaves the filter opens when a visitor fills the camera frame (negative closes it).')),
    ('Sound Mod', 'Motionscan', 'Float', 'Motion -> Scan (months/s)', dict(
        default=24.0, min=0.0, max=120.0, clampMin=True, clampMax=True, normMax=60.0,
        help='Extra scan speed at full camera motion: moving makes the drone travel '
             'faster through the history.')),
    ('Sound Mod', 'Posstart', 'Float', 'Position -> Window (months)', dict(
        default=48.0, min=0.0, max=240.0, clampMin=True, clampMax=True, normMax=120.0,
        help='Window offset (in months) from walking left to right in front of the '
             'camera: the horizontal position scrubs through the years.')),
    ('Sound Mod', 'Micdrive', 'Float', 'Mic -> Drive (dB)', dict(
        default=4.0, min=0.0, max=24.0, clampMin=True, clampMax=True, normMax=12.0,
        help='Extra shaper drive at full room loudness (the drone gets rougher when the room is loud).')),

    ('Inputs', 'Camera', 'Toggle', 'Camera', dict(
        default=True,
        help='Use the camera (sense/videoin_cam: pick the device there). Off = no silhouette, no motion.')),
    ('Inputs', 'Mirror', 'Toggle', 'Mirror', dict(
        default=True, help='Mirror the camera horizontally so the cloud follows visitors like a mirror.')),
    ('Inputs', 'Keymode', 'Menu', 'Silhouette Key', dict(
        menuNames=['bgdiff', 'dark'],
        menuLabels=['Background Difference', 'Dark on Light (white room)'], default='bgdiff',
        help='How a visitor is separated from the room: difference to a captured '
             'empty-room background, or simply anything darker than a white wall.')),
    ('Inputs', 'Keythreshold', 'Float', 'Key Threshold', dict(
        default=0.12, min=0.0, max=1.0, clampMin=True, clampMax=True, normMax=0.5,
        help='Difference (or darkness) above which a pixel counts as visitor.')),
    ('Inputs', 'Keysoftness', 'Float', 'Key Softness', dict(
        default=0.08, min=0.001, max=0.5, clampMin=True, clampMax=True, normMax=0.3,
        help='Width of the soft edge around the threshold.')),
    ('Inputs', 'Bglearn', 'Float', 'Background Learn (s)', dict(
        default=40.0, min=0.0, max=600.0, clampMin=True, clampMax=True, normMax=120.0,
        help='Time constant in seconds with which the background slowly absorbs the '
             'room (lighting drift, moved furniture). 0 = never learn, only Capture.')),
    ('Inputs', 'Capturebg', 'Pulse', 'Capture Background', dict(
        help='Take the current camera image as the empty-room background. Press it '
             'with nobody in front of the camera.')),
    ('Inputs', 'Motiondecay', 'Float', 'Motion Trail (s)', dict(
        default=0.8, min=0.05, max=5.0, clampMin=True, clampMax=True, normMax=3.0,
        help='Seconds the motion trail takes to fade.')),
    ('Inputs', 'Mic', 'Toggle', 'Microphone', dict(
        default=True, startSection=True,
        help='Use the room microphone (sense/audiodevin_mic: pick the device there).')),
    ('Inputs', 'Micgain', 'Float', 'Mic Gain (dB)', dict(
        default=12.0, min=-24.0, max=48.0, clampMin=True, clampMax=True, normMin=-12.0, normMax=36.0,
        help='Input gain before the band levels are measured.')),
    ('Inputs', 'Floortime', 'Float', 'Floor Adapt (s)', dict(
        default=8.0, min=0.0, max=120.0, clampMin=True, clampMax=True, normMax=30.0,
        help='Time the adaptive floor needs to absorb a constant sound (the drone '
             'from the speakers, air conditioning). Only sound above the floor makes '
             'noise. 0 = no floor.')),
    ('Inputs', 'Micsmooth', 'Float', 'Mic Release (s)', dict(
        default=0.35, min=0.01, max=4.0, clampMin=True, clampMax=True, normMax=2.0,
        help='Release time of the band envelopes (attack is fixed and fast).')),

    ('Monitor', 'Monpresence', 'Float', 'Presence', dict(
        readOnly=True, expr=_monitor('presence'),
        help='Read-only: 0-1, someone is in front of the camera.')),
    ('Monitor', 'Monprox', 'Float', 'Proximity', dict(
        readOnly=True, expr=_monitor('prox'),
        help='Read-only: 0-1, how much of the frame the silhouette fills (closer = higher).')),
    ('Monitor', 'Monposx', 'Float', 'Position X', dict(
        readOnly=True, expr=_monitor('cx'),
        help='Read-only: 0-1, horizontal center of the silhouette (mirrored like the image).')),
    ('Monitor', 'Monmotion', 'Float', 'Motion', dict(
        readOnly=True, expr=_monitor('motion'),
        help='Read-only: 0-1, amount of movement in the camera image.')),
    ('Monitor', 'Monlow', 'Float', 'Mic Low', dict(
        readOnly=True, expr=_monitor('low'), startSection=True,
        help='Read-only: 0-1, low band above the adaptive floor.')),
    ('Monitor', 'Monmid', 'Float', 'Mic Mid', dict(
        readOnly=True, expr=_monitor('mid'),
        help='Read-only: 0-1, mid band above the adaptive floor.')),
    ('Monitor', 'Monhigh', 'Float', 'Mic High', dict(
        readOnly=True, expr=_monitor('high'),
        help='Read-only: 0-1, high band above the adaptive floor.')),
    ('Monitor', 'Montransient', 'Float', 'Mic Transient', dict(
        readOnly=True, expr=_monitor('transient'),
        help='Read-only: 0-1, sudden onsets (fast envelope over slow envelope).')),
]


class AudioReactorExt:
    """Wavetable drone + camera/mic sensing + point cloud: parameter schema, API fetch, dispatch."""

    def __init__(self, ownerComp: COMP) -> None:
        self.ownerComp = ownerComp
        self.ensurePars()

    def onInitTD(self) -> None:
        """Capture the camera background once the camera has warmed up (deferred, idempotent)."""
        run('args[0].postInit()', self, delayFrames=180)

    def postInit(self) -> None:
        """Deferred start-up: take the empty-room background (children exist again after a TDXN rebuild)."""
        if self.ownerComp.par.Camera.eval():
            self.CaptureBackground()

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

    def CaptureBackground(self) -> None:
        """Take the current camera frame as the empty-room background of the silhouette key."""
        fb = self.ownerComp.op('sense/feedback_bg')
        if fb is None:
            debug('AudioReactor: sense/feedback_bg is missing')
            return
        fb.par.resetpulse.pulse()

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

    def _onCapturebgPulse(self, par: Par) -> None:
        self.CaptureBackground()

    def _setStatus(self, text: str) -> None:
        self.ownerComp.par.Status.val = text
        debug('AudioReactor:', text)

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
            if key == 'expr':
                if par.expr != value:
                    par.expr = value
                continue
            setattr(par, key, value)
        if created and 'default' in attrs:
            par.val = attrs['default']
        return par
