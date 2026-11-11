# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A press of any key, touch or button the board has."""

import time


class Press:
    """Hears the board's touch screen, its keys and its Boot button as one button.

    Call it as often as the program loops. It reads every source each time,
    so a board with none of them simply never reports a press.

    Args:
        board: a `Board`.

    Attributes:
        sources: the names of what it listens to, for a program to report.
    """

    def __init__(self, board):
        self._reads = []
        self.sources = []
        touch = board.eager("touch_read")
        if touch is not None:
            self._reads.append(lambda: bool(touch()))
            self.sources.append("touch")
        keys = board.eager("keypad_read")
        if keys is not None:
            self._reads.append(lambda: bool(keys()))
            self.sources.append("keys")
        button = board.get("boot_button")
        if button is not None:
            self._reads.append(lambda: button.value() == 0)
            self.sources.append("Boot button")
        self._down_at = None

    def down(self):
        """True while anything is pressed."""
        for read in self._reads:
            try:
                if read():
                    return True
            except OSError:
                pass  # a touch controller that missed one read
        return False

    def __call__(self):
        """True once for each new press."""
        if self.down():
            if self._down_at is None:
                self._down_at = time.ticks_ms()
                return True
            return False
        self._down_at = None
        return False

    def held_ms(self):
        """How long the current press has lasted, in ms, or None between presses."""
        if self._down_at is None:
            return None
        return time.ticks_diff(time.ticks_ms(), self._down_at)
