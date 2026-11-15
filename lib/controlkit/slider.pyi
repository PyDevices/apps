# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A fader: a groove, a cap that slides along it, and an optional lamp."""
from collections.abc import Callable
from typing import Any

from .theme import _Theme

MAX: int

class _Lamp:
    rgb: int | None
    def set(self, rgb: int | None) -> None: ...

class Slider:
    """A fader at (`x`, `y`) in `parent`, `width` x `height`, edited 0 to 127."""

    theme: _Theme
    vertical: bool
    value: int
    on_change: Callable[[Slider, int], None] | None
    legend_h: int
    obj: Any
    width: int
    height: int
    legend: Any
    cap_w: int
    cap_h: int
    lamp: _Lamp | None
    cap: Any
    def __init__(
        self,
        parent: Any,
        x: int,
        y: int,
        width: int,
        height: int,
        theme: _Theme,
        legend: str = '',
        vertical: bool = True,
        value: int = 0,
        led: bool = False,
        on_change: Callable[[Slider, int], None] | None = None,
    ) -> None: ...
    def set_value(self, value: float) -> None:
        """Show `value` (0 to 127) without calling `on_change`."""
    def set_led(self, rgb: int | None) -> None:
        """Light the lamp in `rgb`, or darken it with None. No-op without a lamp."""
