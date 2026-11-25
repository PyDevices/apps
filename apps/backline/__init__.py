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

A MIDI foot controller can be the pedals, over USB, Bluetooth LE, a 5-pin
cable or a computer's MIDI ports: set ``midi_in`` in the app's settings, or
``$BACKLINE_MIDI`` (``midipedal.open_input`` lists the choices). In the
desk view's editor, the Pedals button shows the four switches: tap one's
button and press the switch to learn it, then make it pedal A or B (it must
send a release: a momentary controller change or a note) or one action:
start, fill, next part, outro, stop or tap tempo. The map is kept in the
app's ``config.json`` (``midipedal.py``).

Songs are songmodel projects in the app's ``songs`` folder, eight styles
to start with. The desk's sparkle button asks for a new one in words ("a
slow 12-bar blues at 72, 4 times through, slowing in the outro") from any
OpenAI-compatible chat server, such as lite-assistant on your own network
or DeepInfra: set ``base_url``, ``key_file`` and ``chat_model`` in
``settings.json`` in the app's data folder (``ask.py``). A song you keep is
saved in that folder's ``songs``. The songs play on Backline's own SoundFont
drum kit, fetched once when the app is installed or first started; the kit
list also has audioinstruments' drum machines and the drum kit of any other
SoundFont in a ``soundfonts`` folder (``kits.py`` says where it looks).

Each view draws from an hmilink panel on the box's own device, so any
other screen can join it the same way.
"""


def main(scope):
    from . import app

    app.start(scope)
