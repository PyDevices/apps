# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
from ._draw import box as box, fill as fill, label as label, plain as plain
from _typeshed import Incomplete

class LedMeter:
    theme: Incomplete
    vertical: Incomplete
    count: Incomplete
    level: float
    obj: Incomplete
    def __init__(self, parent, x, y, width, height, theme, segments: int = 16, vertical: bool = True, legend: str = '') -> None: ...
    def set_level(self, level) -> None: ...
