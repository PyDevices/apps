# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""One endless encoder: a knurled cap, its pointer, and a ring of 16 LEDs."""
from typing import Any, Protocol

from .theme import _Theme

LEDS: int
MAX: int
MODES: tuple[str, ...]
MIN_ROOM: int

class _EncoderPanel(Protocol):
    travel: float
    fine: bool
    def default_value(self, index: int) -> int: ...
    def _turned(self, encoder: Encoder, value: int) -> None: ...
    def _focused(self, encoder: Encoder) -> None: ...

def geometry(width: int, height: int, scale: float) -> dict[str, float]:
    """The sizes of one encoder that fits a `width` x `height` cell."""

class Encoder:
    """One macro's encoder, at (`x`, `y`) in `parent`, `width` x `height`."""

    panel: _EncoderPanel
    index: int
    value: int
    enabled: bool
    mode: str
    obj: Any
    legend: Any
    cx: int
    cy: int
    pointer: Any
    def __init__(
        self,
        panel: _EncoderPanel,
        parent: Any,
        index: int,
        label: str,
        x: int,
        y: int,
        width: int,
        height: int,
        geom: dict[str, float],
        theme: _Theme,
        enabled: bool = True,
        mode: str = 'fill',
    ) -> None: ...
    def set_value(self, value: float) -> None:
        """Show `value` (0 to 127). Never reports back to the panel."""
    def lit(self) -> list[int]:
        """How bright each LED is, 0 to 255."""
