# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Stills of the coast: each a name, a function that returns SVG text, and a width."""

from wander.scene_coast import draw
from wander.vec import Doc


def _still(view, **options):
    def build():
        doc = Doc()
        draw(doc, **options)
        return doc.svg(view)

    return build


_WIDE = (0, 0, 800, 480)
_MID = (150, 190, 480, 288)
_CLOSE = (262, 270, 250, 150)

STILLS = [
    ("coast_hue_spring", _still(_WIDE, season="spring"), 800),
    ("coast_hue_summer", _still(_WIDE, season="summer"), 800),
    ("coast_hue_autumn", _still(_WIDE, season="autumn"), 800),
    ("coast_hue_winter", _still(_WIDE, season="winter"), 800),
    ("coast_hue_night", _still(_WIDE, season="summer", night=True), 800),
    ("coast_hue_autumn_mid", _still((120, 170, 500, 300), season="autumn"), 800),
    ("coast_hue_winter_close", _still((300, 250, 270, 162), season="winter"), 800),
]
