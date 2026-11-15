# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Stills of the chameleon from other sides: each a name, a function that returns SVG text, and a width."""

from wander import mascot_chameleon
from wander.chameleon_views import above, at, back, front, limb, path, three_quarter
from wander.mascot_chameleon import NAVY
from wander.vec import Doc, rect


def _study(view, draw_it, **pose):
    def build():
        doc = Doc()
        doc.add(rect(-2000, -2000, 4000, 4000, NAVY))
        doc.add(draw_it(doc, **pose))
        return doc.svg(view)

    return build


def _turnaround():
    doc = Doc()
    doc.add(rect(-2000, -2000, 4000, 4000, NAVY))
    # one long twig under all four
    doc.add(limb(-900, 12, 830, 5, 0.004, 19, 13, 0x7A5440))
    doc.add(path("M-890 15Q0 24 826 9", None, 0x5B3B2E, 4, opacity=0.8))
    doc.add(path("M-820 5Q-300 9 300 3", None, 0x9C7257, 2.6))
    doc.add(at(-640, 0, mascot_chameleon.draw(doc, colors="leaf", perch=None)))
    doc.add(at(-180, 0, three_quarter(doc, colors="leaf", perch=None)))
    doc.add(at(230, 0, front(doc, colors="leaf", perch=None)))
    doc.add(at(650, 0, back(doc, colors="leaf", perch=None)))
    return doc.svg((-920, -330, 1780, 420))


_FULL = (-254, -326, 508, 420)

STILLS = [
    ("chameleon_front", _study(_FULL, front, look=(0.3, 0.15), look_other=(-0.3, 0.15)), 920),
    ("chameleon_front_face", _study((-150, -310, 300, 250), front, look=(0.4, 0.2), look_other=(0.6, -0.5), perch=None), 900),
    ("chameleon_front_happy", _study(_FULL, front, mood="happy", colors="brand", hand=1, perch="wire"), 920),
    ("chameleon_three_quarter", _study(_FULL, three_quarter, colors="sunset", look=(0.5, 0.2), look_far=(0.8, -0.3)), 920),
    ("chameleon_back", _study(_FULL, back, colors="board", perch="wire"), 920),
    ("chameleon_above", _study((-290, -240, 580, 480), above, colors="leaf", look=(0.7, -0.3), look_other=(0.2, 0.6)), 920),
    ("chameleon_turnaround", _turnaround, 1600),
]
