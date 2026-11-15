# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Stills of the chameleon holding things: each a name, a function that returns SVG text, and a width."""

from perch.chameleon_props import NAVY, ORDER, PROPS, _BOX, at, hold, rect
from perch.vec import Doc


def _sheet():
    doc = Doc()
    cols, cw, ch = 6, 236, 250
    rows = (len(ORDER) + cols - 1) // cols
    doc.add(rect(-10, -10, cols * cw + 20, rows * ch + 20, NAVY))
    for i, name in enumerate(ORDER):
        cx = (i % cols) * cw + cw / 2
        cy = (i // cols) * ch + ch / 2
        if i // cols == rows - 1:
            # centre the short last row
            cx += (cols * rows - len(ORDER)) * cw / 2
        left, top, right, bottom = _BOX[name]
        scale = min((cw - 64) / (right - left), (ch - 64) / (bottom - top), 1.5)
        doc.add(rect(cx - cw / 2 + 10, cy - ch / 2 + 10, cw - 20, ch - 20, 0x0F3558, r=18))
        doc.add(at(cx - (left + right) / 2 * scale, cy - (top + bottom) / 2 * scale, PROPS[name][0](0), scale=scale))
    return doc.svg((0, 0, cols * cw, rows * ch))


def _holding(prop, view=None, **options):
    def build():
        doc = Doc()
        doc.add(rect(-1000, -1000, 2000, 2000, NAVY))
        doc.add(hold(doc, prop, **options))
        return doc.svg(view or _FULL)

    return build


_FULL = (-250, -350, 570, 471)

STILLS = [
    ("chameleon_props_sheet", _sheet, 1416),
    ("chameleon_holds_iron", _holding("iron", colors="leaf", mood="calm", look=(0.9, 0.3), look_far=(0.8, 0.2)), 920),
    ("chameleon_holds_magnifier", _holding("magnifier", colors="sunset", mood="curious", look=(0.95, 0.35), look_far=(-0.5, -0.5)), 920),
    ("chameleon_holds_sparkler", _holding("sparkler", wear="party_hat", colors="brand", mood="happy", perch="wire"), 920),
    ("chameleon_holds_board", _holding("board", colors="board", mood="calm", look=(0.9, 0.5), look_far=(0.6, 0.6), perch="wire"), 920),
    ("chameleon_holds_umbrella", _holding("umbrella", size=1.5, colors="leaf", mood="calm", look=(0.2, -0.9), look_far=(0.3, -0.8)), 920),
    ("chameleon_holds_mug", _holding("mug", colors="sunset", mood="sleepy", look=(0.6, 0.6)), 920),
    ("chameleon_holds_lantern", _holding("lantern", colors="brand", mood="calm", look=(0.9, -0.3), look_far=(0.8, -0.3), perch="wire"), 920),
    ("chameleon_holds_flag", _holding("flag", colors="leaf", mood="happy"), 920),
    ("chameleon_holds_wire", _holding("wire", colors="board", mood="calm", look=(0.9, -0.2), look_far=(0.9, -0.3), perch="wire"), 920),
    ("chameleon_holds_flower", _holding("flower", colors="leaf", mood="happy"), 920),
    ("chameleon_holds_plane", _holding("plane", lean=62, colors="brand", mood="calm", look=(0.9, -0.4), look_far=(0.9, -0.4)), 920),
    ("chameleon_holds_balloon", _holding("balloon", colors="sunset", mood="happy", look=(0.4, -0.8)), 920),
]
