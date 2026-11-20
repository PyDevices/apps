# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A rate and level envelope drawn as a curve, with the edited stage lit and a playhead."""
from collections.abc import Sequence
from typing import Any

from .theme import _Theme

class EnvelopeView:
    """An envelope of `stages` rates and levels at (`x`, `y`) in `parent`, `width` x `height`."""

    theme: _Theme
    stages: int
    sustain: int | None
    maximum: int
    selected: int | None
    position: tuple[int, float] | None
    rates: list[int]
    levels: list[int]
    obj: Any
    def __init__(
        self,
        parent: Any,
        x: int,
        y: int,
        width: int,
        height: int,
        theme: _Theme,
        stages: int = 4,
        sustain: int | None = None,
        maximum: int = 127,
        legend: str = '',
        rates: Sequence[int] | None = None,
        levels: Sequence[int] | None = None,
    ) -> None: ...
    def set_values(self, rates: Sequence[int], levels: Sequence[int]) -> None:
        """Draw the envelope with these `rates` and `levels`, one of each per stage."""
    def set_rate(self, stage: int, value: int) -> None:
        """Give `stage` the rate `value`."""
    def set_level(self, stage: int, value: int) -> None:
        """Give `stage` the level `value`."""
    def set_selected(self, stage: int | None) -> None:
        """Light `stage` as the one being edited, or none with None."""
    def set_position(self, stage: int | None, fraction: float = 0.0) -> None:
        """Show the playhead `fraction` (0.0 to 1.0) of the way through `stage`, or hide it with None."""
    def points(self) -> list[tuple[float, float]]:
        """Where the curve turns, as (x, y) in this control: its start, then the end of each stage."""
    def playhead(self) -> tuple[float, float] | None:
        """Where the playhead is, as (x, y) in this control, or None when it is hidden."""
