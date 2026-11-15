# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Vamp: a headless groovebox. One MicroPython holds the song, runs the
sequencer and makes the sound; any screen in the room is its front panel.

- `vamp.engine`: the sound, every SoundFont track on one sampler, with
  notes sequenced ahead so they land on their exact frame.
- `vamp.device`: the song as an hmilink device, which Ostinato's window
  and the browser page drive over TCP.
- `vamp.main`: the program, on a board or desktop MicroPython.
- `vamp.panel`, `vamp.panel_view`, `vamp.panel_main`: a front panel for a
  box, on an 800x480 touch screen or in a desktop window.

The song is `songmodel.model`'s, the same one Ostinato edits.
"""


def run(*args):
    """Start the box, with ``vamp.main``'s options as strings."""
    from vamp import main

    return main.main(list(args))


def run_panel(*args):
    """Start the front panel on this board's screen, with ``vamp.panel_main``'s
    options as strings: ``vamp.run_panel("192.168.1.50")``."""
    from vamp import panel_main

    return panel_main.main(list(args))
