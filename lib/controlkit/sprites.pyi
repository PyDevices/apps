# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The panel's artwork, painted once and shared."""
from typing import Any

from .theme import _Theme

def led_angles(count: int = 16, start: float = 135, sweep: float = 270) -> list[float]:
    """The angle of each LED, in degrees clockwise from three o'clock."""
def knob(geometry: dict[str, float], theme: _Theme) -> Any:
    """The encoder's static art: unlit LEDs, the knob's shadow, skirt and cap."""
def led(lens: float, theme: _Theme) -> tuple[Any, int]:
    """A lit LED: a hot core, its red lens, and a glow round it."""
def small_led(lens: float, rgb: int, theme: _Theme) -> tuple[Any, int]:
    """A lit indicator LED in colour `rgb`, for buttons and the status light."""
def pointer(width: int, length: int, theme: _Theme) -> Any:
    """The cap's pointer, upright: a cream bar with rounded ends."""
def screw(r: float, theme: _Theme) -> tuple[Any, int]:
    """A cross-head screw, sunk flush."""
def texture(rgb: int, brushed: bool = False, size: int = 64) -> Any:
    """A tile of `rgb` with a fine grain, for a faceplate's finish."""
