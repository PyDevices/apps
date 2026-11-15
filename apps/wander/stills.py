# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The stills: each a name, a function that returns SVG text, and a width."""

import crab
from vec import Doc, rect


def _study(view, **pose):
    def build():
        doc = Doc()
        bg = doc.linear([(0, 0x123A5E), (1, 0x0B2A4A)])
        doc.add(rect(-1000, -1000, 2000, 2000, bg))
        doc.add(crab.draw(doc, **pose))
        return doc.svg(view)

    return build


STILLS = [
    ("study_full", _study((-230, -340, 460, 380)), 920),
    ("study_face", _study((-10, -230, 180, 150)), 900),
    ("study_happy", _study((-230, -340, 460, 380), mood="happy", wave=40, shell="night"), 920),
    ("study_goggles", _study((-230, -340, 460, 380), mood="curious", wave=15, shell="rose", wear="goggles", look=(0.8, 0.5)), 920),
    ("study_sleepy", _study((-230, -340, 460, 380), mood="sleepy", shell="moss", look=(0.1, 0.8)), 920),
]
