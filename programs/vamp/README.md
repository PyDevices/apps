# Vamp

Vamp plays Ostinato's songs: the song and the sound live on one MicroPython,
and the screens are somewhere else. Ostinato's window, a browser page and a
board with an 800x480 touch screen edit the song it plays, live, over the
network, and a MIDI keyboard on the box plays the selected track, and records
into it when a screen arms the track and starts a take.

Runs on: an ESP32-P4 board, or desktop MicroPython on Linux or Windows. It needs
a General MIDI SoundFont. [Put Vamp on a board](../../docs/guides/put-vamp-on-a-board.md)
has the steps for both, and the options are listed at the top of
[`main.py`](main.py).
