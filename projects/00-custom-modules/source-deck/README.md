# source_deck

Video and audio sources with a transport, in one COMP. Pick where the picture and the sound come from, scrub them, and link them when they belong to the same clip.

## Connectors

| Connector | |
|---|---|
| Input 1 (TOP) | External video, used when Video Source is External Input. Black when nothing is wired. |
| Input 2 (CHOP) | External audio, used when Audio Source is External Input. Silence when nothing is wired. |
| Output 1 (TOP) | The chosen video (`out_video`). |
| Output 2 (CHOP) | The chosen audio (`out_audio`), time-sliced at the source's sample rate. |

## Parameters

- **Sources.** Video Source (Camera, Movie File, External Input, YouTube), Camera On, Movie File, YouTube Video Link, Download Video, the download's status and file. The same for audio (Microphone, Audio File, External Input, YouTube). Play to Speakers and Speaker Volume send everything but the microphone to the default audio device.
- **Transport.** Link Audio to Video (Auto (Same Clip), Always, Never) and the read-only Audio Linked. For the video: Play, Position (seconds; the slider spans the clip), Time, Speed, Loop, Restart. For the audio: the same without Speed.
- **Module.** YouTube Folder (default `media/youtube` in the project) and Save Module.

## How the transport works

- The movie players run in Specify Index mode and show Video Position.
- The audio players play sequentially, so the sound stays clean and pauses and jumps fade. They are cued whenever Audio Position moves.
- While linked, the video follows the audio's read position, so the two can't drift apart. Moving, playing, pausing or looping either side does both, and Video Speed changes the audio's speed and pitch too. Linked audio is silent while the video plays backwards. Past the end of a shorter audio, the video carries on alone.
- Auto links the two while they play the same YouTube video or the same file.
- The transport script runs once per frame and costs about 0.02 ms.

## Requirements

- TouchDesigner 2025 (built and tested on 2025.32820).
- For YouTube: yt-dlp and yt-dlp-ejs in the host project's venv (`op.Embody.InstallPackages(['yt-dlp', 'yt-dlp-ejs'])`), and Node.js on the PATH, which yt-dlp uses for YouTube's player scripts. Keep the YouTube Folder out of git.
- Dragging the position fast through a long 720p H.264 download costs 25–50 ms per frame. That's the cost of random access into H.264; normal playback is unaffected.

## Files

| File | |
|---|---|
| `source_deck.tox` | The module. Projects load this through External .tox. |
| `source_deck.tdxn` | Its network as text, written by Save Module. |
| `transport.py`, `youtube_fetch.py`, `deck_callbacks.py` | Its scripts as text, written by Save Module. Edit them inside TouchDesigner, not here. |
