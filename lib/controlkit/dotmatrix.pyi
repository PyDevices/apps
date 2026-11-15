# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
from . import font5x7 as font5x7
from ._safe import safe as safe
from _typeshed import Incomplete

class DotMatrix:
    columns: Incomplete
    pitch: Incomplete
    cell_w: Incomplete
    cell_h: Incomplete
    width: Incomplete
    height: Incomplete
    obj: Incomplete
    def __init__(self, parent, columns, lines, pitch, theme) -> None: ...
    def text(self, line): ...
    def set_line(self, line, text) -> None: ...
