# Written by Save Module from source_deck.tox so git shows readable diffs. Edit this
# DAT inside source_deck in TouchDesigner, then press Save Module; edits here change nothing.

# Transport of the source deck (Transport page): a playhead for the video and one for the
# audio, moving together while the audio is linked. onFrameStart runs it once per frame.
#
# The movie players run in Specify Index mode and show Video Position. The audio players play
# sequentially (clean sound; pauses and jumps fade) and are cued whenever Audio Position is
# moved. While linked audio plays forward, its own read position is the clock the video
# follows, so picture and sound cannot drift apart; past the end of shorter audio the
# video carries on by itself.

import math
import os

_VIDEO_PLAYERS = {'file': 'moviefilein', 'youtube': 'moviefilein_yt'}
_AUDIO_PLAYERS = {'file': 'audiofilein', 'youtube': 'audiofilein_yt'}
_TRACKED = ('Videotime', 'Audiotime', 'Videoplay', 'Audioplay', 'Videoloop', 'Audioloop')
_RESYNC = 0.1  # seconds linked audio may stray from the video before it is cued back

_last = {}  # tracked values after the previous frame, to tell edits from playback

def onFrameStart(frame):
	Tick(parent())
	return

def Tick(comp):
	"""Advance both playheads one frame, apply edits to them and keep the audio player on its playhead."""
	now = absTime.seconds
	step = now - _last.get('now', now)
	_last['now'] = now
	video = _player(comp, _VIDEO_PLAYERS, comp.par.Videosource)
	audio = _player(comp, _AUDIO_PLAYERS, comp.par.Audiosource)
	linked = _isLinked(comp, video, audio)
	_write(comp.par.Linked, int(linked))
	if linked:
		_mirror(comp.par.Videoplay, comp.par.Audioplay)
		_mirror(comp.par.Videoloop, comp.par.Audioloop)

	videoTime = comp.par.Videotime.eval()
	audioTime = comp.par.Audiotime.eval()
	videoMoved = _edited(comp.par.Videotime) or (linked and _last.get('linked') is False)
	audioMoved = _edited(comp.par.Audiotime) or (audio is not None and _last.get('audio', audio.name) != audio.name)
	speed = comp.par.Videospeed.eval()
	ownStep = step * speed if comp.par.Videoplay.eval() else 0.0
	videoLength = video.numSeconds if video else 0.0
	audioLength, audioAt, audioOpen = _audioState(comp, audio)
	audioPlays = audio is not None and comp.par.Audioplay.eval() and (speed > 0 or not linked)
	audioEnded = audioAt >= audioLength - _RESYNC
	# A cue the audio player is still owed. The first frame owes one, because a new or rebuilt
	# network starts its players at 0; a cue waits until the player's file has opened.
	seek = _last.get('seek', True)

	if linked:
		if videoMoved or audioMoved:
			videoTime = videoTime if videoMoved else audioTime
			seek = True
		elif audioPlays and not seek and not audioEnded:
			videoTime = audioAt  # past the end of shorter audio the video carries on alone
		else:
			videoTime += ownStep
			seek = seek or abs(_fit(videoTime, audioLength, comp.par.Audioloop) - audioAt) > _RESYNC
		audioTime = videoTime
	else:
		if video is not None and not videoMoved:
			videoTime += ownStep
		if audioMoved:
			seek = True
		elif audio is not None and not seek:
			audioTime = audioAt

	videoTime = _fit(videoTime, videoLength, comp.par.Videoloop)
	if audio is None:
		seek = False
	else:
		audioTime = _fit(audioTime, audioLength, comp.par.Audioloop)
		if seek and audioOpen:
			audio.par.cuepoint = audioTime
			audio.par.cuepulse.pulse()
			seek = False
	_write(comp.par.Videotime, videoTime)
	_write(comp.par.Audiotime, audioTime)
	_showClock(comp.par.Videotime, comp.par.Videoclock, video, videoLength)
	_showClock(comp.par.Audiotime, comp.par.Audioclock, audio, audioLength)
	for name in _TRACKED:
		_last[name] = comp.par[name].eval()
	_last['linked'] = linked
	_last['audio'] = audio.name if audio else None
	_last['seek'] = seek

def Restart(comp, kind):
	"""Jump kind's playhead ('video' or 'audio') to the start; linked audio and video jump together."""
	if kind == 'video':
		comp.par.Videotime = 0
	else:
		comp.par.Audiotime = 0

def _player(comp, players, source):
	"""The player of the source menu's current choice, or None for a live source."""
	name = players.get(source.eval())
	return comp.op(name) if name else None

def _isLinked(comp, video, audio):
	"""True when the audio playhead follows the video's (Link Audio to Video)."""
	mode = comp.par.Link.eval()
	if video is None or audio is None or mode == 'separate':
		return False
	return mode == 'linked' or _clipOf(video) == _clipOf(audio) != ''

def _clipOf(player):
	"""What a player plays: a YouTube download's video id, otherwise its file's full path."""
	path = player.par.file.eval()
	if not path:
		return ''
	if player.name.endswith('_yt'):
		return os.path.basename(path).split('.')[0]
	return os.path.normcase(os.path.abspath(path))

def _audioState(comp, audio):
	"""Length and read position of the audio player in seconds, and whether its file is open (info_audio)."""
	info = comp.op('info_audio')
	length, at, isOpen = info['file_length'], info['sample'], info['open']
	if audio is None or length is None or at is None or isOpen is None or audio.rate <= 0:
		return 0.0, 0.0, False
	return length.eval() / audio.rate, at.eval() / audio.rate, isOpen.eval() > 0

def _mirror(videoPar, audioPar):
	"""Copy a change of either linked toggle to the other; when both changed, the video's wins."""
	if _edited(audioPar) and not _edited(videoPar):
		_write(videoPar, audioPar.eval())
	else:
		_write(audioPar, videoPar.eval())

def _edited(par):
	"""True when par changed since the previous frame by anything but this transport."""
	return par.name in _last and par.eval() != _last[par.name]

def _fit(seconds, length, loop):
	"""seconds brought inside the clip: wrapped when it loops, held at the ends when not."""
	if length <= 0:
		return max(seconds, 0.0)
	if loop.eval():
		return seconds % length
	return min(max(seconds, 0.0), length)

def _write(par, value):
	"""Set par only when the value differs (every change recooks what reads it)."""
	if par.eval() != value:
		par.val = value

def _showClock(timePar, clockPar, player, length):
	"""Fit the position slider (and a host slider bound to it) to the clip and show position / length as a clock."""
	top = max(1, math.ceil(length))
	for par in (timePar, timePar.bindMaster):
		if isinstance(par, Par) and par.normMax != top:
			par.normMax = top
	if player is None:
		_write(clockPar, 'Live input')
		return
	hours = length >= 3600
	_write(clockPar, '%s / %s' % (_hms(timePar.eval(), hours), _hms(length, hours)))

def _hms(seconds, hours):
	"""seconds as m:ss, or h:mm:ss when hours is True."""
	h, rest = divmod(int(seconds), 3600)
	m, s = divmod(rest, 60)
	if hours:
		return '%d:%02d:%02d' % (h, m, s)
	return '%d:%02d' % (h * 60 + m, s)
