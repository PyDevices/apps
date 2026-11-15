# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A labelled push button with a coloured lamp in its corner."""
from collections.abc import Callable
from typing import Any

from .theme import _Theme

class _Lamp:
    rgb: int | None
    def set(self, rgb: int | None) -> None: ...

class LampButton:
    """A button at (`x`, `y`) in `parent`, `width` x `height` of cap."""

    theme: _Theme
    toggle: bool
    on: bool
    on_press: Callable[[LampButton, bool], None] | None
    obj: Any
    cap: Any
    lamp: _Lamp
    def __init__(
        self,
        parent: Any,
        x: int,
        y: int,
        width: int,
        height: int,
        theme: _Theme,
        legend: str = '',
        toggle: bool = False,
        lamp: int | None = None,
        on_press: Callable[[LampButton, bool], None] | None = None,
    ) -> None: ...
    def set_lamp(self, rgb: int | None) -> None:
        """Set the lamp's colour; None darkens it. A toggle's lamp shows only while it is on."""
    def set_on(self, on: object) -> None:
        """Set the toggle state without calling `on_press`."""
