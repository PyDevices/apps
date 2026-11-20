# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A round button drawn as a thin ring, with an icon or a short text in it."""
from typing import Any, Callable

from .theme import _Theme

class RingButton:
    """A ring `size` pixels across, its top left at (`x`, `y`) in `parent`."""

    theme: _Theme
    on_press: Callable[[RingButton], Any] | None
    on_hold: Callable[[RingButton, bool], Any] | None
    held: bool
    enabled: bool
    rgb: int | None
    obj: Any
    icon: Any
    text: Any
    def __init__(
        self,
        parent: Any,
        x: int,
        y: int,
        size: int,
        theme: _Theme,
        icon: Any = None,
        text: str = '',
        on_press: Callable[[RingButton], Any] | None = None,
        color: int | None = None,
        ring: int = 1,
        hit: int = 0,
        on_hold: Callable[[RingButton, bool], Any] | None = None,
    ) -> None: ...
    def set_color(self, rgb: int) -> None:
        """Draw the ring and its icon in `rgb`, ``0xRRGGBB``."""
    def set_icon(self, icon: Any) -> None:
        """Show another image source in the ring, such as pause for play."""
    def set_enabled(self, enabled: bool) -> None:
        """A disabled button is dimmed and ignores taps."""
