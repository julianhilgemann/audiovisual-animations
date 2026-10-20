"""MusicVideo: the audioreactor point cloud as a square, audio-file driven music video.

A track (sense/audiofilein_track) is played and analysed (bands, energy, transients,
spectrum, waveform); a video (sense/moviefilein_mod, e.g. a spinning record) is the
modulator: its luma keys a mask that displaces and lights the cloud, its motion stirs it.
The drone engine, the Bundesbank data, the webcam and the microphone of the original
installation are still inside, parked (engine/ and data/ cooking off, devices bypassed).

Owns the music-video parameter schema (get-or-create, never destroys a user value;
the parked installation's parameters stay on their legacy pages at the end), the
restart cue and the parameter dispatcher.
"""
from __future__ import annotations

_STYLE_FAMILY = {'RGB': ('RGB', 'RGBA'), 'XY': ('XY', 'XYZW'), 'XYZ': ('XYZ', 'XYZW')}

# Page order of the COMP: the music video first, the parked installation last.
_PAGE_ORDER = ['Track', 'Modulator', 'Form', 'Camera', 'Visual', 'Reactivity', 'Finish', 'Monitor',
               'Inputs', 'Sound Mod', 'Data', 'Wavetable', 'Shape', 'Pitch', 'Filter', 'Output']


def _monitor(channel: str) -> str:
    """Expression that mirrors one sense/null_features channel (0 while it is missing)."""
    return ("float(me.op('sense/null_features')['%s'] or 0) "
            "if me.op('sense/null_features') is not None else 0.0" % channel)


# (page, name, style, label, attributes). 'default' becomes the value on create only;
# 'expr' is schema-owned and re-applied on every init. Parameters inherited from the
# installation (Visual, Reactivity, Monitor) keep their page; their label and help are
# re-stated here for what they do in the music video.
_PAR_SCHEMA = [
    # ---- Track
    ('Track', 'Audiofile', 'File', 'Audio File', dict(
        default='',
        help='The track (wav, aif, mp3). Empty = the TouchDesigner sample track. It is '
             'played out and analysed: bands, energy, transients, spectrum and waveform drive everything.')),
    ('Track', 'Play', 'Toggle', 'Play', dict(
        default=True, help='Play the track (and the modulator video). Off pauses both.')),
    ('Track', 'Restart', 'Pulse', 'Restart', dict(
        help='Jump the track and the modulator video back to the start.')),
    ('Track', 'Loop', 'Toggle', 'Loop', dict(
        default=True, help='Start the track again when it ends.')),
    ('Track', 'Trackvolume', 'Float', 'Volume', dict(
        default=0.8, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='Playback volume to the default audio device (analysis is not affected).')),
    ('Track', 'Trackgain', 'Float', 'Analysis Gain (dB)', dict(
        default=0.0, min=-24.0, max=24.0, clampMin=True, clampMax=True, normMin=-12.0, normMax=12.0,
        startSection=True,
        help='Gain before the band levels are measured: raise it for a quiet master, lower it for a loud one.')),
    ('Track', 'Specgain', 'Float', 'Spectrum Gain (dB)', dict(
        default=0.0, min=-24.0, max=24.0, clampMin=True, clampMax=True, normMin=-12.0, normMax=12.0,
        help='Gain of the spectrum written into the sonogram history (brightness of the frequency content).')),
    ('Track', 'Adapt', 'Float', 'Floor Adapt (s)', dict(
        default=6.0, min=0.0, max=60.0, clampMin=True, clampMax=True, normMax=20.0,
        help='Time the adaptive floor needs to absorb a constant level, so a loud master still '
             'moves the image: only what rises above the floor counts. 0 = absolute levels.')),
    ('Track', 'Release', 'Float', 'Band Release (s)', dict(
        default=0.25, min=0.01, max=4.0, clampMin=True, clampMax=True, normMax=1.0,
        help='Release time of the band envelopes (attack is fixed and fast).')),

    # ---- Modulator video
    ('Modulator', 'Videofile', 'File', 'Video File', dict(
        default='',
        help='The modulator video (a spinning record, any footage). Empty = the TouchDesigner '
             'sample countdown. It is never shown directly: it keys a mask that displaces and lights the cloud.')),
    ('Modulator', 'Modon', 'Toggle', 'Video On', dict(
        default=True, help='Use the modulator video. Off = no mask, no motion.')),
    ('Modulator', 'Modspeed', 'Float', 'Video Speed', dict(
        default=1.0, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=2.0,
        help='Playback speed of the video.')),
    ('Modulator', 'Spinreact', 'Float', 'Low -> Video Speed', dict(
        default=0.6, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=2.0,
        help='The low band speeds the video up (the record spins faster on the kick).')),
    ('Modulator', 'Modkey', 'Menu', 'Key', dict(
        menuNames=['luma', 'dark', 'bgdiff'],
        menuLabels=['Bright parts', 'Dark parts', 'Difference to background'], default='luma',
        startSection=True,
        help='What of the video becomes the mask: its bright parts, its dark parts, or the '
             'difference to a learned background.')),
    ('Modulator', 'Modthreshold', 'Float', 'Key Threshold', dict(
        default=0.35, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='Brightness (or difference) at the middle of the soft key.')),
    ('Modulator', 'Modsoftness', 'Float', 'Key Softness', dict(
        default=0.2, min=0.001, max=0.5, clampMin=True, clampMax=True,
        help='Width of the soft edge of the key: wide = greyscale mask, narrow = hard silhouette.')),
    ('Modulator', 'Modtrail', 'Float', 'Motion Trail (s)', dict(
        default=0.4, min=0.05, max=5.0, clampMin=True, clampMax=True, normMax=2.0,
        help='Seconds the motion trail of the video takes to fade.')),
    ('Modulator', 'Modmirror', 'Toggle', 'Mirror', dict(
        default=False, help='Mirror the video horizontally.')),
    ('Modulator', 'Vidshow', 'Float', 'Video in Points', dict(
        default=0.5, min=0.0, max=1.0, clampMin=True, clampMax=True, startSection=True,
        help='How much the mask lights the points: 0 = the sound alone sets brightness, 1 = the '
             'video is drawn by the points.')),
    ('Modulator', 'Ghost', 'Float', 'Video Ghost', dict(
        default=0.0, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='Faint monochrome overlay of the video itself behind the cloud.')),

    # ---- Form
    ('Form', 'Form', 'Menu', 'Form', dict(
        menuNames=['sheet', 'tunnel', 'disc'],
        menuLabels=['Sheet (sonogram wall)', 'Tunnel (fly through)', 'Disc (record)'], default='tunnel',
        help='Shape the history is laid out in. Sheet: time across the screen. Tunnel: time is depth, '
             'the sound comes at the camera and the frequencies wrap around. Disc: time is the angle, '
             'frequency the radius, like grooves on a record.')),
    ('Form', 'Morph', 'Float', 'Morph', dict(
        default=1.0, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='Blend from the sheet (0) to the chosen form (1). Animate it for transitions.')),
    ('Form', 'Symmetry', 'Int', 'Symmetry', dict(
        default=1, min=1, max=12, clampMin=True, clampMax=True, normMin=1, normMax=8,
        help='Mirrors the frequency axis N times around the tunnel or disc (kaleidoscope). 1 = none.')),
    ('Form', 'Tunnellength', 'Float', 'Tunnel Length', dict(
        default=30.0, min=4.0, max=80.0, clampMin=True, clampMax=True, normMin=8.0, normMax=60.0,
        help='Depth of the tunnel in world units (the camera sits 5.4 in front of the origin).')),
    ('Form', 'Twist', 'Float', 'Twist', dict(
        default=0.6, min=-4.0, max=4.0, clampMin=True, clampMax=True, normMin=-2.0, normMax=2.0,
        startSection=True,
        help='Turns of twist along the history (tunnel, disc); the mid band adds Mid -> Twist.')),
    ('Form', 'Twistreact', 'Float', 'Mid -> Twist', dict(
        default=0.5, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=2.0,
        help='Extra twist from the mid band.')),
    ('Form', 'Lowpump', 'Float', 'Low -> Pump', dict(
        default=1.0, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=2.0,
        help='The low band inflates the form (tunnel radius, disc and sheet depth).')),
    ('Form', 'Warp', 'Float', 'Warp', dict(
        default=1.0, min=0.0, max=6.0, clampMin=True, clampMax=True, normMax=3.0,
        help='4D noise that bends the whole form; the track energy scales it up.')),

    # ---- Camera
    ('Camera', 'Distance', 'Float', 'Distance', dict(
        default=5.4, min=0.2, max=20.0, clampMin=True, clampMax=True, normMin=1.0, normMax=12.0,
        help='Camera distance from the origin; the camera orbits the origin. Small values put it inside the cloud.')),
    ('Camera', 'Tilt', 'Float', 'Tilt (deg)', dict(
        default=-9.0, min=-90.0, max=90.0, clampMin=True, clampMax=True, normMin=-60.0, normMax=60.0,
        help='Base pitch of the camera (negative = looking down onto the form).')),
    ('Camera', 'Fov', 'Float', 'Field of View (deg)', dict(
        default=50.0, min=10.0, max=120.0, clampMin=True, clampMax=True, normMin=20.0, normMax=100.0,
        help='Lens: small = long lens, flat and graphic; large = wide, deep perspective.')),
    ('Camera', 'Push', 'Float', 'Energy -> Push', dict(
        default=0.5, min=0.0, max=2.0, clampMin=True, clampMax=True, startSection=True,
        help='The camera dollies in when the track is loud (drops) and backs off in breakdowns.')),
    ('Camera', 'Flyreact', 'Float', 'Energy -> Fly', dict(
        default=1.0, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=2.0,
        help='Track energy speeds up the flow of the history (the flight through the tunnel).')),
    ('Camera', 'Shake', 'Float', 'Transient -> Shake', dict(
        default=0.5, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=2.0,
        help='Camera jolt on transients (kicks, snares).')),
    ('Camera', 'Fovpunch', 'Float', 'Transient -> Zoom', dict(
        default=0.3, min=0.0, max=2.0, clampMin=True, clampMax=True,
        help='Short wide-angle punch of the lens on transients.')),
    ('Camera', 'Roll', 'Float', 'Roll', dict(
        default=0.3, min=0.0, max=3.0, clampMin=True, clampMax=True, normMax=2.0,
        help='Slow roll swing of the camera; the track energy speeds it up.')),
    ('Visual', 'Sway', 'Float', 'Orbit', dict(
        default=1.0, min=0.0, max=3.0, clampMin=True, clampMax=True, normMax=2.0,
        help='Amount of the slow, eased camera orbit around the origin (0 = locked camera).')),
    ('Visual', 'Swayspeed', 'Float', 'Orbit Speed', dict(
        default=1.0, min=0.0, max=5.0, clampMin=True, clampMax=True, normMax=3.0,
        help='Speed of the camera orbit, the roll and the idle breathing noise.')),
    ('Visual', 'Speed', 'Float', 'Flow Speed', dict(
        default=1.0, min=0.0, max=6.0, clampMin=True, clampMax=True, normMax=4.0,
        help='Base travel speed of the history: screen crossings (sheet), flight (tunnel) or turns '
             '(disc) per 10 s. Energy -> Fly adds to it. 0 = static, the field breathes in place.')),

    # ---- Visual (inherited, re-described)
    ('Visual', 'Palette', 'Menu', 'Color Scale', dict(
        menuNames=['inferno', 'magma', 'viridis', 'turbo', 'ice', 'mono', 'steel', 'signal'],
        menuLabels=['Inferno', 'Magma', 'Viridis', 'Turbo', 'Ice', 'Mono (warm white)',
                    'Steel (neutral white)', 'Signal (white, red peaks)'], default='steel',
        help='Color scale the sonogram level is mapped through (quiet -> loud). Steel and Mono are '
             'monochrome; Signal keeps one red accent on the loudest peaks.')),
    ('Visual', 'Depth', 'Float', 'Waveform Depth', dict(
        default=1.0, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=3.0,
        help='How far the waveform history displaces the form (depth on the sheet and disc, radius in the tunnel).')),
    ('Visual', 'Glow', 'Float', 'Glow', dict(
        default=1.0, min=0.0, max=3.0, clampMin=True, clampMax=True,
        help='Base strength of the bloom (the low band adds Low -> Bloom).')),
    ('Visual', 'Dof', 'Float', 'Depth of Field', dict(
        default=1.0, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=3.0,
        help='Blur of points in front of and behind the focus plane (soft bokeh discs). The mid band adds to it.')),

    # ---- Reactivity (inherited, re-described)
    ('Reactivity', 'Reach', 'Float', 'Video Displace', dict(
        default=1.0, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=3.0,
        help='How far the points inside the video mask come toward the camera: the video is embossed into the form.')),
    ('Reactivity', 'Imprint', 'Float', 'Video Imprint', dict(
        default=0.5, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='How strongly the video mask lifts its points up the color scale and enlarges them.')),
    ('Reactivity', 'Ripple', 'Float', 'Video Motion Ripple', dict(
        default=1.0, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=3.0,
        help='Turbulence the motion in the video stirs into the cloud.')),
    ('Reactivity', 'Chaos', 'Float', 'Chaos', dict(
        default=1.0, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=3.0,
        help='Master amount of the band reactions below: higher = the track tears the image apart more.')),
    ('Reactivity', 'Lowbloom', 'Float', 'Low -> Bloom', dict(
        default=1.0, min=0.0, max=3.0, clampMin=True, clampMax=True,
        help='Low band (< 250 Hz): bloom and a depth pump.')),
    ('Reactivity', 'Midblur', 'Float', 'Mid -> Blur', dict(
        default=1.0, min=0.0, max=3.0, clampMin=True, clampMax=True,
        help='Mid band (250 Hz - 4 kHz): defocus blur and a looser cloud.')),
    ('Reactivity', 'Highjitter', 'Float', 'High -> Jitter', dict(
        default=1.0, min=0.0, max=3.0, clampMin=True, clampMax=True,
        help='High band (> 4 kHz): per-frame point jitter, grain and glitch.')),
    ('Reactivity', 'Kick', 'Float', 'Transient -> Kick', dict(
        default=1.0, min=0.0, max=3.0, clampMin=True, clampMax=True,
        help='Transients (kicks, snares): a radial shock through the cloud, a colour split, strobe and invert.')),
    ('Reactivity', 'Micsono', 'Float', 'Transient Layer', dict(
        default=0.6, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='How much of the fast (instant) spectrum is written over the smoothed one: crisp hits in the history.')),

    # ---- Finish
    ('Finish', 'Exposure', 'Float', 'Exposure', dict(
        default=1.0, min=0.0, max=4.0, clampMin=True, clampMax=True, normMax=2.5,
        help='Gain before the filmic tone map.')),
    ('Finish', 'Crush', 'Float', 'Black Crush', dict(
        default=0.06, min=0.0, max=0.5, clampMin=True, clampMax=True, normMax=0.3,
        help='Black point after the tone map: everything below it goes to pure black (harder contrast).')),
    ('Finish', 'Gamma', 'Float', 'Contrast Curve', dict(
        default=1.25, min=0.3, max=3.0, clampMin=True, clampMax=True, normMin=0.5, normMax=2.5,
        help='Power curve after the black crush (> 1 deepens the mids, light on dark).')),
    ('Finish', 'Saturation', 'Float', 'Saturation', dict(
        default=0.0, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='0 = strict monochrome (the Signal accent survives), 1 = the full color scale.')),
    ('Finish', 'Trails', 'Float', 'Trails', dict(
        default=0.55, min=0.0, max=0.97, clampMin=True, clampMax=True, startSection=True,
        help='Light trails: how much of the previous frame survives (0 = none, 0.97 = long smear).')),
    ('Finish', 'Strobe', 'Float', 'Strobe', dict(
        default=0.25, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='White flash on strong transients.')),
    ('Finish', 'Invert', 'Float', 'Invert', dict(
        default=0.0, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='Negative flash on the strongest transients (dark on light for a frame).')),
    ('Finish', 'Glitch', 'Float', 'Glitch', dict(
        default=0.3, min=0.0, max=1.0, clampMin=True, clampMax=True,
        help='Horizontal slice displacement driven by the high band and transients.')),
    ('Finish', 'Grain', 'Float', 'Grain', dict(
        default=0.5, min=0.0, max=2.0, clampMin=True, clampMax=True,
        help='Film grain amount (the high band adds to it).')),

    # ---- Monitor (read-only)
    ('Monitor', 'Monlow', 'Float', 'Low', dict(
        readOnly=True, expr=_monitor('low'), help='Read-only: 0-1, low band above the adaptive floor.')),
    ('Monitor', 'Monmid', 'Float', 'Mid', dict(
        readOnly=True, expr=_monitor('mid'), help='Read-only: 0-1, mid band above the adaptive floor.')),
    ('Monitor', 'Monhigh', 'Float', 'High', dict(
        readOnly=True, expr=_monitor('high'), help='Read-only: 0-1, high band above the adaptive floor.')),
    ('Monitor', 'Montransient', 'Float', 'Transient', dict(
        readOnly=True, expr=_monitor('transient'), help='Read-only: 0-1, onsets (fast envelope over slow envelope).')),
    ('Monitor', 'Monenergy', 'Float', 'Energy', dict(
        readOnly=True, expr=_monitor('energy'),
        help='Read-only: 0-1, slow loudness of the track (breakdown low, drop high).')),
    ('Monitor', 'Monpresence', 'Float', 'Video Mask', dict(
        readOnly=True, expr=_monitor('presence'), help='Read-only: 0-1, the video mask is present.')),
    ('Monitor', 'Monprox', 'Float', 'Video Coverage', dict(
        readOnly=True, expr=_monitor('prox'), help='Read-only: 0-1, how much of the frame the mask covers.')),
    ('Monitor', 'Monposx', 'Float', 'Video Mask X', dict(
        readOnly=True, expr=_monitor('cx'), help='Read-only: 0-1, horizontal center of the mask.')),
    ('Monitor', 'Monmotion', 'Float', 'Video Motion', dict(
        readOnly=True, expr=_monitor('motion'), help='Read-only: 0-1, amount of movement in the video.')),
    ('Monitor', 'Montime', 'Float', 'Track Time (s)', dict(
        readOnly=True,
        expr="float(me.op('sense/audiofilein_track').par.index.eval()) if me.op('sense/audiofilein_track') is not None else 0.0",
        help='Read-only: playback position of the track in seconds.')),
]


class MusicVideoExt:
    """Audio-file + video-modulated point cloud: parameter schema, restart cue, dispatch."""

    def __init__(self, ownerComp: COMP) -> None:
        self.ownerComp = ownerComp
        self.ensurePars()

    def onInitTD(self) -> None:
        """Nothing deferred: the track and the video start by themselves."""
        return

    def onDestroyTD(self) -> None:
        """No timers or threads to release."""
        return

    # ---- Tier 1: public API ------------------------------------------------
    def Restart(self) -> None:
        """Cue the track and the modulator video back to their start."""
        for name in ('sense/audiofilein_track', 'sense/moviefilein_mod'):
            o = self.ownerComp.op(name)
            if o is None:
                debug('MusicVideo: %s is missing' % name)
                continue
            o.par.cuepoint = 0
            o.par.cuepulse.pulse()

    def CaptureBackground(self) -> None:
        """Take the current video frame as the background of the Difference key."""
        fb = self.ownerComp.op('sense/feedback_bg')
        if fb is None:
            debug('MusicVideo: sense/feedback_bg is missing')
            return
        fb.par.resetpulse.pulse()

    # ---- Tier 2: wiring (callbacks of this COMP's own DATs) -----------------
    def ensurePars(self) -> None:
        """Get-or-create every custom parameter in _PAR_SCHEMA, then order the pages."""
        for page_name, name, style, label, attrs in _PAR_SCHEMA:
            self._ensurePar(page_name, name, style, label, attrs)
        present = [p.name for p in self.ownerComp.customPages]
        order = [n for n in _PAGE_ORDER if n in present] + [n for n in present if n not in _PAGE_ORDER]
        if order != present:
            self.ownerComp.sortCustomPages(*order)

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
    def _onRestartPulse(self, par: Par) -> None:
        self.Restart()

    def _onCapturebgPulse(self, par: Par) -> None:
        self.CaptureBackground()

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
