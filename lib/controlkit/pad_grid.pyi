# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A grid of illuminated pads, each lit in any colour, as a step or session grid."""
from collections.abc import Callable
from typing import Any

from .theme import _Theme

class PadGrid:
    """A grid of `cols` x `rows` pads in `width` x `height` at (`x`, `y`) in `parent`."""

    theme: _Theme
    cols: int
    rows: int
    on_press: Callable[[PadGrid, int], None] | None
    on_down: Callable[[PadGrid, int], None] | None
    on_up: Callable[[PadGrid, int], None] | None
    colors: list[int | None]
    obj: Any
    def __init__(
        self,
        parent: Any,
        x: int,
        y: int,
        width: int,
        height: int,
        theme: _Theme,
        cols: int = 8,
        rows: int = 2,
        gap: int = 4,
        on_press: Callable[[PadGrid, int], None] | None = None,
        on_down: Callable[[PadGrid, int], None] | None = None,
        on_up: Callable[[PadGrid, int], None] | None = None,
    ) -> None: ...
    def set_color(self, index: int, rgb: int | None) -> None:
        """Light pad `index` in `rgb`, or put it out with None."""
    def set_label(self, index: int, text: str, rgb: int | None = None) -> Any:
        """Print `text` in the middle of pad `index`, in `rgb` (the theme's pad text by default)."""
    def pad(self, index: int) -> Any:
        """Pad `index`'s LVGL object."""
