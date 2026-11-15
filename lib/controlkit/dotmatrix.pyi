# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A character LCD in the style of a 16x2 dot-matrix module."""
from typing import Any

from .theme import _Theme

class DotMatrix:
    """A dot-matrix display of `columns` x `lines` characters inside `parent`."""

    columns: int
    pitch: int
    cell_w: int
    cell_h: int
    width: int
    height: int
    obj: Any
    def __init__(self, parent: Any, columns: int, lines: int, pitch: int, theme: _Theme) -> None: ...
    def text(self, line: int) -> str:
        """What line `line` shows now, padded to the display's width."""
    def set_line(self, line: int, text: object) -> None:
        """Show `text` on line `line`, cut or padded to the display's width."""
