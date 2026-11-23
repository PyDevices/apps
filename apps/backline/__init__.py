# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline: a drum machine you play with your feet.

Pick a song and tap the pedal: the intro plays, then the first groove.
While it plays, tap for a fill, hold to go through a transition to the
next groove, and tap twice to play the outro and stop. The second pedal's
tap plays a crash over the groove, and its hold stops at once. Every
change waits for the bar line, so the band never loses the one.

On a computer the space bar is pedal A and B is pedal B; Left and Right
choose the song while stopped, and K changes the kit. The two lamps on the
screen are pedals too. While a song plays, the status bar shows its part
and tempo; a tap there brings the floor view to the front.

On a screen of 640x400 or more, D (or the button in the corner) swaps the
floor view for the desk view (``desk/``): the same face larger with the
song's form, and an editor whose step grid, kits and mixer change the song
while it plays. Other screens join as desks on port 9300: a browser at
``http://<box>:9300/``, or another computer with ``python -m
backline.desk_main HOST``. ``remote.py`` says how to change the port or turn it off.

The desk view can also go to a TV or a PC across the room, drawn at
1280x720 and cast with castdisplay: set ``cast`` in the app's settings, or
``$BACKLINE_CAST``, to ``windows:HOST`` (a PC's Wireless Display app),
``roku:HOST`` (a Roku's Screen mirroring) or ``companion:HOST`` (the
Companion channel on a Roku). The sound stays on the box (``cast.py``).

Songs are songmodel projects in the app's ``songs`` folder, eight styles
to start with. Kits are audioinstruments' drum machines, the drum kit of a
SoundFont (``kits.py`` says where it looks) and folders of WAV files.

Each view draws from an hmilink panel on the box's own device, so any
other screen can join it the same way.
"""


def main(scope):
    from . import app

    app.start(scope)
