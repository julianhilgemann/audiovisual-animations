# YouTube sources for FerroScope: yt-dlp downloads a link's picture or sound into
# media/youtube/ (one file per video id and stream, so a link fetched before loads
# instantly) and the Sources page plays it through moviefilein_yt / audiofilein_yt.
# yt-dlp runs as a subprocess on a standalone Thread Manager thread that touches no
# TD object; its output lines come back through a queue drained by main-thread hooks.

import os
import queue
import subprocess

_FOLDER = 'media/youtube'

# Video: H.264 at most 720p (inside the 1280 px licence cap, decodes on any GPU).
# Audio: the AAC m4a stream. Single streams need no ffmpeg to merge them.
_KINDS = {
	'video': {'par': 'Video', 'player': 'moviefilein_yt',
		'format': 'bv[vcodec^=avc1][height<=720]/bv[ext=mp4][height<=720]/b[height<=720]'},
	'audio': {'par': 'Audio', 'player': 'audiofilein_yt',
		'format': 'ba[ext=m4a]/ba'},
}

_downloading = set()  # kinds with a download in flight

def Download(comp, kind):
	"""Download the YouTube link for kind ('video' or 'audio'), then switch that source to it."""
	spec = _KINDS[kind]
	status = comp.par[spec['par'] + 'status']
	link = _linkFor(comp, kind)
	if not link:
		status.val = 'Paste a YouTube link first'
		return
	if kind in _downloading:
		status.val = 'Still downloading the previous link'
		return
	folder = os.path.join(project.folder, _FOLDER)
	os.makedirs(folder, exist_ok=True)
	cmd = [
		_venvPython(), '-I', '-X', 'utf8', '-m', 'yt_dlp', link,
		'--no-playlist', '--js-runtimes', 'node', '--color', 'never',
		'--socket-timeout', '20', '--retries', '3', '--no-mtime',
		'--newline', '--progress',
		'--progress-template', 'download:@@PROGRESS %(progress._percent_str)s %(progress._eta_str)s',
		'--print', 'before_dl:@@TITLE %(title)s',
		'--print', 'after_move:@@FILE %(filepath)s',
		'-f', spec['format'],
		'-o', os.path.join(folder, '%(id)s.' + kind + '.%(ext)s'),
	]
	events = queue.Queue()
	result = {'title': '', 'file': '', 'error': '', 'code': None}

	def youtubeProgress():
		_drain(comp, kind, events, result)

	def youtubeDone():
		_finish(comp, kind, events, result)

	def youtubeFailed(error):
		_fail(comp, kind, error)

	manager = op.TDResources.ThreadManager
	task = manager.TDTask(target=_runDownloader, args=(cmd, events),
		RefreshHook=youtubeProgress, SuccessHook=youtubeDone, ExceptHook=youtubeFailed)
	_downloading.add(kind)
	status.val = 'Looking up the link...'
	try:
		manager.EnqueueTask(task, standalone=True)
	except Exception as error:
		_fail(comp, kind, error)

def Restart(comp, kind):
	"""Jump kind's YouTube player to the start; when video and audio play the same
	YouTube clip, restart both so picture and sound stay together."""
	kinds = ('video', 'audio') if SameClip(comp) else (kind,)
	for each in kinds:
		player = comp.op(_KINDS[each]['player'])
		player.par.cuepoint = 0
		player.par.cuepulse.pulse()

def SameClip(comp):
	"""True when Video and Audio Source both play YouTube downloads of the same video."""
	if comp.par.Videosource.eval() != 'youtube' or comp.par.Audiosource.eval() != 'youtube':
		return False
	video = _clipId(comp.par.Videodownloaded.eval())
	return video != '' and video == _clipId(comp.par.Audiodownloaded.eval())

def _linkFor(comp, kind):
	"""The YouTube link for kind; audio falls back to the video link when its own is empty."""
	link = comp.par.Audiolink.eval().strip() if kind == 'audio' else ''
	return link or comp.par.Videolink.eval().strip()

def _clipId(path):
	"""The YouTube video id a downloaded file is named after ('' for no file)."""
	return os.path.basename(path).split('.')[0]

def _venvPython():
	"""The project venv's Python, where yt-dlp is installed."""
	embody = getattr(op, 'Embody', None)
	if embody is not None:
		return embody.VenvPython
	return os.path.join(project.folder, '.venv', 'Scripts', 'python.exe')

def _runDownloader(cmd, events):
	"""WORKER THREAD: run yt-dlp, queue each output line, then its exit code. No TD access."""
	process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
		creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
	for line in process.stdout:
		events.put(('line', line.rstrip()))
	events.put(('exit', process.wait()))

def _drain(comp, kind, events, result):
	"""Main thread, every frame while downloading: read queued yt-dlp lines into result and the status."""
	progress = None
	changed = False
	while True:
		try:
			tag, value = events.get_nowait()
		except queue.Empty:
			break
		changed = True
		if tag == 'exit':
			result['code'] = value
		elif value.startswith('@@PROGRESS '):
			progress = value.split()[1:]
		elif value.startswith('@@TITLE '):
			result['title'] = value[len('@@TITLE '):]
		elif value.startswith('@@FILE '):
			result['file'] = value[len('@@FILE '):]
		elif value.startswith('ERROR'):
			result['error'] = value
	if not changed:
		return
	status = comp.par[_KINDS[kind]['par'] + 'status']
	if progress:
		percent, eta = (progress + ['NA', 'NA'])[:2]
		left = '' if eta == 'NA' else ', %s left' % eta
		status.val = 'Downloading %s%s: %s' % (percent, left, result['title'])
	elif result['title']:
		status.val = 'Downloading: ' + result['title']

def _finish(comp, kind, events, result):
	"""Main thread, once yt-dlp has exited: load the file and switch the source to
	YouTube, or report why it failed."""
	_drain(comp, kind, events, result)
	_downloading.discard(kind)
	spec = _KINDS[kind]
	status = comp.par[spec['par'] + 'status']
	path = result['file']
	if result['code'] != 0 or not path or not os.path.isfile(path):
		status.val = 'Failed: ' + (result['error'] or 'yt-dlp exited with code %s' % result['code'])
		return
	comp.par[spec['par'] + 'downloaded'].val = os.path.relpath(path, project.folder).replace('\\', '/')
	comp.par[spec['par'] + 'source'].val = 'youtube'
	status.val = 'Ready: ' + result['title']
	# Restart once the player has opened the new file, so a clip shared by video and audio starts together.
	run(Restart, comp, kind, delayFrames=15)

def _fail(comp, kind, error):
	"""Main thread: yt-dlp could not be started; report it."""
	_downloading.discard(kind)
	if isinstance(error, tuple):
		error = error[1]
	comp.par[_KINDS[kind]['par'] + 'status'].val = 'Failed: %s' % error
