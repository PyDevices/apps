# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
from ._draw import Lamp as Lamp, box as box, fill as fill, label as label, plain as plain
from ._safe import safe as safe
from _typeshed import Incomplete

class LampButton:
    theme: Incomplete
    toggle: Incomplete
    on: bool
    on_press: Incomplete
    obj: Incomplete
    cap: Incomplete
    lamp: Incomplete
    def __init__(self, parent, x, y, width, height, theme, legend: str = '', toggle: bool = False, lamp=None, on_press=None) -> None: ...
    def set_lamp(self, rgb) -> None: ...
    def set_on(self, on) -> None: ...
