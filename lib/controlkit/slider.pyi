# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
from ._draw import Lamp as Lamp, box as box, fill as fill, label as label, plain as plain
from ._safe import safe as safe
from _typeshed import Incomplete

MAX: int

class Slider:
    theme: Incomplete
    vertical: Incomplete
    value: int
    on_change: Incomplete
    legend_h: Incomplete
    obj: Incomplete
    width: Incomplete
    height: Incomplete
    legend: Incomplete
    cap_w: Incomplete
    cap_h: int
    lamp: Incomplete
    cap: Incomplete
    def __init__(self, parent, x, y, width, height, theme, legend: str = '', vertical: bool = True, value: int = 0, led: bool = False, on_change=None) -> None: ...
    def set_value(self, value) -> None: ...
    def set_led(self, rgb) -> None: ...
