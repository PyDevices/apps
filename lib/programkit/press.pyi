# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A press of any key, touch or button the board has."""
from .board import Board

class Press:
    """Hears the board's touch screen, its keys and its Boot button as one button."""

    sources: list[str]
    def __init__(self, board: Board) -> None: ...
    def down(self) -> bool:
        """True while anything is pressed."""
    def __call__(self) -> bool:
        """True once for each new press."""
    def held_ms(self) -> int | None:
        """How long the current press has lasted, in ms, or None between presses."""
