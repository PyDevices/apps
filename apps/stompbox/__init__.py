# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Stompbox: play a guitar or a WAV clip through an airwindows effect.

The effect's knobs are on screen, built from the plug-in's own parameters. Live
takes the board's input, or a capture device on Windows. On a computer the clips
are in ``$STOMPBOX_CLIPS``, else ``~/music/guitar-clips``; on a board, in
``/sd/guitar-clips``, ``/guitar-clips`` and ``/data/guitar-clips``. It needs a firmware built with audioairwindows.
"""

SAMPLE_RATE = 48000
CHANNELS = 2
BLOCK_FRAMES = 256


def main(scope):
    from touchkit import ui

    try:
        import audioairwindows  # noqa: F401
    except ImportError:
        ui.missing(scope, "missing: audioairwindows",
                   "Stompbox needs a firmware built with the audioairwindows module.")
        return
    from . import app

    app.start(scope)
