# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
from . import sprites as sprites
from ._safe import safe as safe
from _typeshed import Incomplete

LEDS: int
MAX: int

def geometry(width, height, scale): ...

class Encoder:
    panel: Incomplete
    index: Incomplete
    value: int
    enabled: Incomplete
    obj: Incomplete
    legend: Incomplete
    cx: Incomplete
    cy: Incomplete
    pointer: Incomplete
    def __init__(self, panel, parent, index, label, x, y, width, height, geom, theme, enabled: bool = True) -> None: ...
    def set_value(self, value) -> None: ...
    def lit(self): ...
