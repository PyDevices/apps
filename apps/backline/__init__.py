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
screen are pedals too.

Songs are songmodel projects in the app's ``songs`` folder, eight styles
to start with. Kits are audioinstruments' drum machines, the drum kit of a
SoundFont (``kits.py`` says where it looks) and folders of WAV files.

The floor view (``floor.py``) draws from an hmilink panel on the box's own
device, so any other screen can join it the same way.
"""


def main(scope):
    from . import app

    app.start(scope)
