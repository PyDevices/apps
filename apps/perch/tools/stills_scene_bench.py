# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Stills of the workbench: each a name, a function that returns SVG text, and a width."""

from perch.scene_bench import draw
from perch.vec import Doc


def _still(view, **options):
    def build():
        doc = Doc()
        draw(doc, **options)
        return doc.svg(view)

    return build


STILLS = [
    ("bench_hue_wide", _still((0, 0, 800, 480)), 800),
    ("bench_hue_mid", _still((163, 168, 520, 312)), 800),
    ("bench_hue_close", _still((328, 222, 270, 162)), 800),
    ("bench_hue_front", _still((428, 118, 290, 174), pose="front"), 800),
    ("bench_hue_hang", _still((212, 167, 300, 180), pose="hang"), 800),
]
