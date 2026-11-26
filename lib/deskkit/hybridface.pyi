# SPDX-FileCopyrightText: 2026 PyDevices / Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A hybrid watch face in LVGL: analog hands with the time and date in digits."""
from collections.abc import Callable, Sequence
from typing import Any

BACKGROUND: int
CASE: int
CASE_EDGE: int
RING: int
DIAL: int
DIAL_EDGE: int
WINDOW: int
INK: int
DIM_INK: int
TICK: int
ACCENT: int
SHADOW: int

class HybridWatch:
    """The face on `parent`, `size` pixels across, centred."""
    parent: Any
    face: Any
    hands: Any
    digital_time: Any
    digital_date: Any
    layers: dict[str, Any]
    def __init__(self, parent: Any, size: int, read_now: Callable[[], Sequence[int]]) -> None: ...
    def update_time(self) -> None: ...
