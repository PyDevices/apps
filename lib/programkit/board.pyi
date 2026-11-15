# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""What the board offers: its `board_config` if it has one, and its lazy roles."""
from types import ModuleType
from typing import Any

class Board:
    """The board this program runs on."""

    config: ModuleType | None
    peripherals: ModuleType | None
    display: Any
    def __init__(self) -> None: ...
    def has(self, role: str) -> bool:
        """True when the board lists `role` (`"audio_out"`, `"sdcard"`, ...)."""
    def get(self, role: str) -> Any:
        """The role's object, or its factory for the audio roles; None if absent."""
    def eager(self, name: str) -> Any:
        """A `board_config` name such as `touch_read` or `keypad_read`, or None."""
