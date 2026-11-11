# Vamp

Vamp plays Ostinato's songs: the song and the sound live on one MicroPython,
and the screens are somewhere else. Ostinato's window and a browser page edit
the song it plays, live, over the network, and a MIDI keyboard on the box plays
the selected track.

Runs on: an ESP32-P4 board, or desktop MicroPython on Linux or Windows. It needs
a General MIDI SoundFont. [Put Vamp on a board](../../docs/guides/put-vamp-on-a-board.md)
has the steps for both, and the options are listed at the top of
[`main.py`](main.py).
