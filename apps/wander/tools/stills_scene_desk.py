# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Stills of the desk: each a name, a function that returns SVG text, and a width."""

from wander.scene_desk import draw
from wander.vec import Doc


def _still(view, **options):
    def build():
        doc = Doc()
        draw(doc, **options)
        return doc.svg(view)

    return build


STILLS = [
    ("desk_hue_wide", _still((0, 0, 800, 480), look=(0.0, 0.1), look_far=(0.9, -0.5)), 800),
    ("desk_hue_mid", _still((0, 180, 490, 294), look=(0.0, 0.1), look_far=(0.9, -0.5)), 980),
    ("desk_hue_hello", _still((5, 222, 310, 186), pose="front", wave=1, look=(0.0, 0.1)), 900),
    ("desk_hue_thinking", _still((150, -112, 480, 288), spot="monitor", pose="side", mood="curious", nod=10, look=(0.5, 0.8), look_far=(0.0, 0.0), bubble=True), 960),
    ("desk_hue_evening", _still((0, 0, 800, 480), time="evening", pose="sit", wave=1, look=(0.0, 0.1), look_far=(0.8, -0.4)), 800),
    ("desk_hue_night", _still((0, 0, 800, 480), time="night", pose="sleep"), 800),
    ("desk_hue_coffee", _still((0, 180, 490, 294), time="evening", pose="hold", prop="mug", mood="happy", look=(0.2, 0.0)), 980),
]
