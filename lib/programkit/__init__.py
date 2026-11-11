# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Reach a board's display, keys and touch from a program that runs without Home.

A program in ``programs/`` runs on any board with the hardware it needs, so it
never names a pin. `Board` finds what the board's ``board_config`` and
``board_peripherals`` offer, `Rows` puts lines of text on whatever display is
there, and `Press` hears a press of any key, touch or button::

    from programkit import Board, Press, Rows

    board = Board()
    rows = Rows(board.display) if board.display else None
    press = Press(board)
    if board.has("audio_out"):
        out = board.get("audio_out")(AudioFormat(44100, 2, 16))

A board with no display has no ``board_config``; `Board` then reads
``board_peripherals`` alone, which is how a headless board describes itself.
"""

from .board import Board
from .press import Press
from .rows import Rows

__all__ = ["Board", "Press", "Rows"]
