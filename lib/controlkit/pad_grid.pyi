# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
from ._draw import box as box, fill as fill, plain as plain
from ._safe import safe as safe
from _typeshed import Incomplete

class PadGrid:
    theme: Incomplete
    cols: Incomplete
    rows: Incomplete
    on_press: Incomplete
    colors: Incomplete
    obj: Incomplete
    def __init__(self, parent, x, y, width, height, theme, cols: int = 8, rows: int = 2, gap: int = 4, on_press=None) -> None: ...
    def set_color(self, index, rgb) -> None: ...
