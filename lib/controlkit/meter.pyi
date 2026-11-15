# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""An LED segment meter: a column (or row) of lit segments for a level."""
from typing import Any

from .theme import _Theme

class LedMeter:
    """A meter at (`x`, `y`) in `parent`, `width` x `height`, with `segments` lit in turn."""

    theme: _Theme
    vertical: bool
    count: int
    level: float
    obj: Any
    def __init__(
        self,
        parent: Any,
        x: int,
        y: int,
        width: int,
        height: int,
        theme: _Theme,
        segments: int = 16,
        vertical: bool = True,
        legend: str = '',
    ) -> None: ...
    def set_level(self, level: float) -> None:
        """Light the segments that `level` (0.0 to 1.0) covers."""
