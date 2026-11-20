# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A row of thin bars, one per band: a small spectrum, or a set of levels."""
from typing import Any, Sequence

from .theme import _Theme

class SpectrumBars:
    """`bands` bars across `width` x `height` at (`x`, `y`) in `parent`."""

    theme: _Theme
    bands: int
    height: int
    fall: float
    floor: int
    rgb: int | None
    obj: Any
    levels: list[float]
    def __init__(
        self,
        parent: Any,
        x: int,
        y: int,
        width: int,
        height: int,
        theme: _Theme,
        bands: int = 16,
        gap: int | None = None,
        color: int | None = None,
        fall: float = 0.08,
        floor: int = 2,
    ) -> None: ...
    def set_color(self, rgb: int) -> None:
        """Draw the bars in `rgb`, ``0xRRGGBB``."""
    def set_levels(self, levels: Sequence[float]) -> None:
        """Move each bar toward its level in `levels`, 0.0 to 1.0."""
    def clear(self) -> None:
        """Drop every bar to the floor at once."""
